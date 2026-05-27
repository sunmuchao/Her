"""Add discovery_profile_update_requests for confirmed profile edits."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


def _profile_update_table() -> tuple[_schema.TableDef, ...]:
    return tuple(
        table
        for table in _schema.discovery_tables()
        if table.name == "discovery_profile_update_requests"
    )


MIGRATION = MigrationSpec(
    migration_id="0006_profile_update_requests",
    description="Add discovery profile update confirmation requests",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_profile_update_table()),
    validate_fn=validate_system_schema(_profile_update_table()),
)
