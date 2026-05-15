"""Discovery schema migration for view snapshots."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _view_snapshot_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name == "discovery_view_snapshots"
    )


MIGRATION = MigrationSpec(
    migration_id="0004_add_view_snapshots",
    description="Add discovery view snapshots table",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_view_snapshot_tables()),
    validate_fn=validate_system_schema(_view_snapshot_tables()),
)
