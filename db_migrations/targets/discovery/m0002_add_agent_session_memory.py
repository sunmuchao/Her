"""Discovery schema migration for agent session memory."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _agent_session_memory_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name == "discovery_agent_session_memory_items"
    )


MIGRATION = MigrationSpec(
    migration_id="0002_add_agent_session_memory",
    description="Add discovery agent session memory table",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_agent_session_memory_tables()),
    validate_fn=validate_system_schema(_agent_session_memory_tables()),
)
