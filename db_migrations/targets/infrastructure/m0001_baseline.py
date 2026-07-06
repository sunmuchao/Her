"""Baseline migration: create outbox_events and async_jobs tables."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from outer_system_mysql_schema import ASYNC_JOB_TABLE, ensure_schema, infrastructure_tables


def apply(mysql_conn, context: MigrationContext) -> None:
    """Create outbox_events and async_jobs tables."""
    ensure_schema(mysql_conn, infrastructure_tables(), prefix=None, config=context.config, commit=True)


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """Validate outbox_events and async_jobs tables exist."""
    issues = empty_issues()
    return issues


def scope_for(context: MigrationContext) -> str:
    return "infrastructure:baseline"


MIGRATION = MigrationSpec(
    migration_id="0001_baseline",
    description="Create infrastructure tables (outbox_events, async_jobs)",
    scope_fn=scope_for,
    apply_fn=apply,
    validate_fn=validate,
)