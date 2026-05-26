"""Add criteria_snapshots table for compile audit (§13.1.2)."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _criteria_snapshot_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.recommendation_tables()
        if table.name == "criteria_snapshots"
    )


MIGRATION = MigrationSpec(
    migration_id="0006_add_criteria_snapshots",
    description="Add criteria_snapshots table for compile audit",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_criteria_snapshot_tables()),
    validate_fn=validate_system_schema(_criteria_snapshot_tables()),
)
