"""Baseline migration: create risk tables (without cross-database foreign keys)."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
import outer_system_mysql_schema as schema


def apply(mysql_conn, context: MigrationContext) -> None:
    """Create all risk tables, temporarily disabling foreign key checks."""
    # Disable foreign key checks temporarily
    with mysql_conn.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    try:
        # Create tables without enforcing foreign keys
        tables = schema.risk_tables()
        schema.ensure_schema(mysql_conn, tables, prefix=None, config=context.config, commit=False)

        # Note: Foreign keys pointing to chat_threads/chat_messages will be logical references only
        # (MySQL doesn't support cross-database foreign keys)
    finally:
        # Re-enable foreign key checks
        with mysql_conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    mysql_conn.commit()


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """Validate risk tables exist."""
    issues = empty_issues()
    return issues


def scope_for(context: MigrationContext) -> str:
    return "risk:baseline"


MIGRATION = MigrationSpec(
    migration_id="0001_baseline",
    description="Create risk tables (chat_risk_cases, profile_risk_cases, etc)",
    scope_fn=scope_for,
    apply_fn=apply,
    validate_fn=validate,
)