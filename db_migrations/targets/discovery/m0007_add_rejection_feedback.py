"""Add rejection feedback and working criteria adjustment tables."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _rejection_feedback_tables() -> tuple[_schema.TableDef, ...]:
    """Return the two new tables for rejection feedback collection."""
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name in (
            "discovery_rejection_feedbacks",
            "discovery_working_criteria_adjustments",
        )
    )


MIGRATION = MigrationSpec(
    migration_id="0007_rejection_feedback_tables",
    description="Add rejection feedback collection and working criteria adjustment tables",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_rejection_feedback_tables()),
    validate_fn=validate_system_schema(_rejection_feedback_tables()),
)