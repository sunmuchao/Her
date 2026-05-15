"""Discovery schema migration for tool call audit."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _tool_call_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name == "discovery_agent_tool_calls"
    )


MIGRATION = MigrationSpec(
    migration_id="0003_add_tool_call_audit",
    description="Add discovery agent tool call audit table",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_tool_call_tables()),
    validate_fn=validate_system_schema(_tool_call_tables()),
)
