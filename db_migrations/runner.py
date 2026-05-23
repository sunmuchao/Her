"""Versioned schema migrations for Her MySQL databases."""

from __future__ import annotations

import importlib
import os
import pkgutil
import re
from typing import Any, Mapping

import outer_system_mysql_schema as _schema

from .core import (
    DEFAULT_INIT_MODE,
    INIT_MODE_ENV,
    MIGRATION_TABLE,
    MIGRATION_TABLE_NAME,
    VALID_INIT_MODES,
    MigrationContext,
    MigrationSpec,
    SchemaMigrationError,
    SchemaValidationError,
    TargetDefinition,
    empty_issues,
    merge_issues,
)


TARGETS: dict[str, TargetDefinition] = {
    "recommendation": TargetDefinition(
        env_var="PARTNER_RECOMMENDATION_DB",
        package="db_migrations.targets.recommendation",
    ),
    "matchmaking": TargetDefinition(
        env_var="PARTNER_MATCHMAKING_DB",
        package="db_migrations.targets.matchmaking",
    ),
    "chat": TargetDefinition(
        env_var="PARTNER_CHAT_DB",
        package="db_migrations.targets.chat",
    ),
    "discovery": TargetDefinition(
        env_var="PARTNER_DISCOVERY_DB",
        package="db_migrations.targets.discovery",
    ),
    "persona": TargetDefinition(
        env_var="PERSONA_MEMORY_MYSQL_SOURCE",
        package="db_migrations.targets.persona",
    ),
    "relationship_ledger": TargetDefinition(
        env_var="HER_RELATION_LEDGER_DB",
        package="db_migrations.targets.relationship_ledger",
    ),
}
_MIGRATION_MODULE_RE = re.compile(r"m\d{4}_[a-z0-9_]+$")


def resolve_init_mode(mode: str | None = None) -> str:
    resolved = str(mode or os.environ.get(INIT_MODE_ENV, DEFAULT_INIT_MODE)).strip().lower()
    if resolved not in VALID_INIT_MODES:
        valid = ", ".join(sorted(VALID_INIT_MODES))
        raise ValueError(f"Unsupported {INIT_MODE_ENV} value: {resolved!r}. Expected one of: {valid}.")
    return resolved


def target_env_var(target: str) -> str:
    return _target_definition(target).env_var


def resolve_target_source(target: str, explicit_source: str | None = None, *, environ: Mapping[str, str] | None = None) -> str:
    if explicit_source and str(explicit_source).strip():
        return str(explicit_source).strip()
    env_var = target_env_var(target)
    env = os.environ if environ is None else environ
    value = env.get(env_var)
    if value and str(value).strip():
        return str(value).strip()
    raise ValueError(f"Missing DSN for {target}. Pass it explicitly or set {env_var}.")


def load_target_migrations(target: str) -> tuple[MigrationSpec, ...]:
    definition = _target_definition(target)
    package = importlib.import_module(definition.package)
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        raise SchemaMigrationError(f"Migration package has no __path__: {definition.package}")

    migrations: list[MigrationSpec] = []
    seen_ids: set[str] = set()
    for modinfo in sorted(pkgutil.iter_modules(package_path), key=lambda item: item.name):
        if not _MIGRATION_MODULE_RE.fullmatch(modinfo.name):
            continue
        module = importlib.import_module(f"{definition.package}.{modinfo.name}")
        migration = getattr(module, "MIGRATION", None)
        if not isinstance(migration, MigrationSpec):
            raise SchemaMigrationError(f"Migration module missing MIGRATION spec: {definition.package}.{modinfo.name}")
        if migration.migration_id in seen_ids:
            raise SchemaMigrationError(f"Duplicate migration id for {target}: {migration.migration_id}")
        migrations.append(migration)
        seen_ids.add(migration.migration_id)
    return tuple(sorted(migrations, key=lambda item: item.migration_id))


def initialize_target_database(
    mysql_conn: Any,
    *,
    target: str,
    config: dict[str, Any] | None = None,
    mode: str | None = None,
    source: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    init_mode = resolve_init_mode(mode)
    if init_mode == "migrate":
        return upgrade_target_database(
            mysql_conn,
            target=target,
            config=config,
            source=source,
            options=options,
        )
    return validate_target_database(
        mysql_conn,
        target=target,
        config=config,
        source=source,
        options=options,
    )


def upgrade_target_database(
    mysql_conn: Any,
    *,
    target: str,
    config: dict[str, Any] | None = None,
    source: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_conn = _raw_connection(mysql_conn)
    resolved_config = _resolve_config(mysql_conn, config)
    resolved_source = source or getattr(mysql_conn, "source", None)
    context = MigrationContext(target=target, config=resolved_config, source=resolved_source, options=dict(options or {}))
    migrations = load_target_migrations(target)
    _schema.ensure_database(resolved_config)

    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        _schema.ensure_schema(raw_conn, (MIGRATION_TABLE,), prefix=None, config=resolved_config, commit=False)
        for migration in migrations:
            scope = migration.scope_for(context)
            checksum = migration.checksum_for(context)
            existing = _get_migration_row(raw_conn, scope=scope, migration_id=migration.migration_id)
            if existing is not None:
                existing_checksum = str(existing.get("checksum") or "")
                if existing_checksum and existing_checksum != checksum:
                    raise SchemaMigrationError(
                        f"Checksum mismatch for {target}:{scope}:{migration.migration_id}. "
                        f"Database has {existing_checksum}, code expects {checksum}."
                    )
                skipped.append(
                    {
                        "scope": scope,
                        "migration_id": migration.migration_id,
                        "description": migration.description,
                        "applied_at": existing.get("applied_at"),
                    }
                )
                continue
            migration.apply_fn(raw_conn, context)
            _insert_migration_row(
                raw_conn,
                scope=scope,
                migration_id=migration.migration_id,
                checksum=checksum,
                description=migration.description,
            )
            applied.append(
                {
                    "scope": scope,
                    "migration_id": migration.migration_id,
                    "description": migration.description,
                }
            )
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise

    return {
        "target": target,
        "mode": "migrate",
        "applied": applied,
        "already_applied": skipped,
    }


def validate_target_database(
    mysql_conn: Any,
    *,
    target: str,
    config: dict[str, Any] | None = None,
    source: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status = get_migration_status(
        mysql_conn,
        target=target,
        config=config,
        source=source,
        options=options,
    )
    if not status["ok"]:
        raise SchemaValidationError(target, status["issues"])
    return status


def get_migration_status(
    mysql_conn: Any,
    *,
    target: str,
    config: dict[str, Any] | None = None,
    source: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_conn = _raw_connection(mysql_conn)
    resolved_config = _resolve_config(mysql_conn, config)
    resolved_source = source or getattr(mysql_conn, "source", None)
    context = MigrationContext(target=target, config=resolved_config, source=resolved_source, options=dict(options or {}))
    migrations = load_target_migrations(target)
    issues = empty_issues()

    migration_table_issues = _schema.validate_schema(raw_conn, (MIGRATION_TABLE,), prefix=None)
    merge_issues(issues, migration_table_issues)

    rows = _list_migration_rows(raw_conn) if MIGRATION_TABLE_NAME not in issues["missing_tables"] else []
    row_by_key = {
        (str(row.get("scope") or ""), str(row.get("migration_id") or "")): row
        for row in rows
    }

    expected_keys = set()
    planned: list[dict[str, Any]] = []
    for migration in migrations:
        scope = migration.scope_for(context)
        migration_key = (scope, migration.migration_id)
        expected_keys.add(migration_key)
        checksum = migration.checksum_for(context)
        row = row_by_key.get(migration_key)
        if row is None:
            issues["missing_migrations"].append(f"{scope}:{migration.migration_id}")
        else:
            existing_checksum = str(row.get("checksum") or "")
            if existing_checksum != checksum:
                issues["checksum_mismatches"].append(
                    f"{scope}:{migration.migration_id}:{existing_checksum}->{checksum}"
                )
        merge_issues(issues, migration.validate_fn(raw_conn, context))
        planned.append(
            {
                "scope": scope,
                "migration_id": migration.migration_id,
                "description": migration.description,
                "expected_checksum": checksum,
                "applied_at": None if row is None else row.get("applied_at"),
            }
        )

    for scope, migration_id in sorted(set(row_by_key) - expected_keys):
        issues["unexpected_migrations"].append(f"{scope}:{migration_id}")

    return {
        "target": target,
        "mode": "validate",
        "ok": not any(issues.values()),
        "migrations": planned,
        "issues": issues,
    }


def _target_definition(target: str) -> TargetDefinition:
    definition = TARGETS.get(target)
    if definition is None:
        valid = ", ".join(sorted(TARGETS))
        raise ValueError(f"Unsupported migration target: {target!r}. Expected one of: {valid}.")
    return definition


def _raw_connection(mysql_conn: Any) -> Any:
    driver_connection = getattr(mysql_conn, "driver_connection", None)
    if driver_connection is not None:
        return driver_connection
    return mysql_conn


def _resolve_config(mysql_conn: Any, config: dict[str, Any] | None) -> dict[str, Any]:
    if config is not None:
        return dict(config)
    resolved = getattr(mysql_conn, "config", None)
    if resolved is None:
        raise ValueError("MySQL config is required when passing a raw database connection.")
    return dict(resolved)


def _list_migration_rows(mysql_conn: Any) -> list[dict[str, Any]]:
    if not _schema.table_exists(mysql_conn, MIGRATION_TABLE_NAME):
        return []
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            f"SELECT scope, migration_id, checksum, description, applied_at "
            f"FROM {_schema.quote_mysql_ident(MIGRATION_TABLE_NAME)} "
            "ORDER BY scope, migration_id"
        )
        return list(cursor.fetchall() or [])


def _get_migration_row(mysql_conn: Any, *, scope: str, migration_id: str) -> dict[str, Any] | None:
    if not _schema.table_exists(mysql_conn, MIGRATION_TABLE_NAME):
        return None
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            f"SELECT scope, migration_id, checksum, description, applied_at "
            f"FROM {_schema.quote_mysql_ident(MIGRATION_TABLE_NAME)} "
            "WHERE scope = %s AND migration_id = %s "
            "LIMIT 1",
            (scope, migration_id),
        )
        return cursor.fetchone()


def _insert_migration_row(
    mysql_conn: Any,
    *,
    scope: str,
    migration_id: str,
    checksum: str,
    description: str,
) -> None:
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {_schema.quote_mysql_ident(MIGRATION_TABLE_NAME)} "
            "(scope, migration_id, checksum, description, applied_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (scope, migration_id, checksum, description),
        )
