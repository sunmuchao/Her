"""Helpers for building migration specs."""

from __future__ import annotations

from typing import Any, Sequence

import outer_system_mysql_schema as _schema

from .core import MigrationContext, MigrationSpec, ScopeFn, TargetApplyFn, TargetValidateFn


def get_persona_schema_tools():
    from persona_memory_sync import schema_tools  # noqa: PLC0415

    return schema_tools


def default_scope(context: MigrationContext) -> str:
    return context.target


def apply_system_schema(tables: Sequence[_schema.TableDef]) -> TargetApplyFn:
    def _apply(mysql_conn: Any, context: MigrationContext) -> None:
        _schema.ensure_schema(mysql_conn, tables, prefix=None, config=context.config, commit=False)

    return _apply


def validate_system_schema(tables: Sequence[_schema.TableDef]) -> TargetValidateFn:
    def _validate(mysql_conn: Any, _context: MigrationContext) -> dict[str, list[str]]:
        return _schema.validate_schema(mysql_conn, tables, prefix=None)

    return _validate


def apply_persona_schema(mysql_conn: Any, context: MigrationContext) -> None:
    schema_tools = get_persona_schema_tools()
    schema_tools.ensure_persona_schema(
        mysql_conn,
        source=context.source,
        persona_table=context.options.get("persona_table"),
        observation_table=context.options.get("observation_table"),
        profile_table=context.options.get("profile_table"),
        public_view=context.options.get("public_view"),
        commit=False,
    )


def validate_persona_schema(mysql_conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    schema_tools = get_persona_schema_tools()
    return schema_tools.validate_persona_schema(
        mysql_conn,
        source=context.source,
        persona_table=context.options.get("persona_table"),
        observation_table=context.options.get("observation_table"),
        profile_table=context.options.get("profile_table"),
        public_view=context.options.get("public_view"),
    )


def persona_scope(context: MigrationContext) -> str:
    schema_tools = get_persona_schema_tools()
    return schema_tools.build_persona_scope(
        source=context.source,
        persona_table=context.options.get("persona_table"),
        observation_table=context.options.get("observation_table"),
        profile_table=context.options.get("profile_table"),
        public_view=context.options.get("public_view"),
    )


def baseline_migration(
    *,
    description: str,
    scope_fn: ScopeFn,
    apply_fn: TargetApplyFn,
    validate_fn: TargetValidateFn,
) -> MigrationSpec:
    return MigrationSpec(
        migration_id="0001_baseline",
        description=description,
        scope_fn=scope_fn,
        apply_fn=apply_fn,
        validate_fn=validate_fn,
    )
