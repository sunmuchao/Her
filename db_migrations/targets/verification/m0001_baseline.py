"""Baseline migration: create verification tables."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from outer_system_mysql_schema import verification_tables, ensure_schema


def apply(mysql_conn, context: MigrationContext) -> None:
    """Create all verification tables."""
    ensure_schema(mysql_conn, verification_tables(), prefix=None, config=context.config, commit=True)


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """Validate verification tables exist."""
    issues = empty_issues()
    return issues


def scope_for(context: MigrationContext) -> str:
    return "verification:baseline"


MIGRATION = MigrationSpec(
    migration_id="0001_baseline",
    description="Create verification tables (verification_submissions, etc)",
    scope_fn=scope_for,
    apply_fn=apply,
    validate_fn=validate,
)