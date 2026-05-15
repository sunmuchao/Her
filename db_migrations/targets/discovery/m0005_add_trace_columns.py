"""Discovery schema migration for trace correlation columns."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _trace_column_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name in {
            "discovery_agent_turns",
            "discovery_agent_tool_calls",
            "discovery_view_snapshots",
        }
    )


MIGRATION = MigrationSpec(
    migration_id="0005_add_trace_columns",
    description="Add discovery trace correlation columns",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_trace_column_tables()),
    validate_fn=validate_system_schema(_trace_column_tables()),
)
