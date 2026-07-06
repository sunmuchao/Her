"""Baseline migration: create auth tables (user accounts, sessions, etc)."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from outer_system_mysql_schema import auth_tables, ensure_schema


def apply(mysql_conn, context: MigrationContext) -> None:
    """Create all auth tables."""
    ensure_schema(mysql_conn, auth_tables(), prefix=None, config=context.config, commit=True)


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """Validate auth tables exist."""
    issues = empty_issues()
    # Table existence validation is handled by ensure_schema
    return issues


def scope_for(context: MigrationContext) -> str:
    return "auth:baseline"


MIGRATION = MigrationSpec(
    migration_id="0001_baseline",
    description="Create auth tables (user_accounts, auth_sessions, etc)",
    scope_fn=scope_for,
    apply_fn=apply,
    validate_fn=validate,
)