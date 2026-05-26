"""Add proxy-intro case tables to matchmaking database."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationSpec
from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema


_PROXY_INTRO_TABLES = _schema.proxy_intro_matchmaking_tables()


MIGRATION = MigrationSpec(
    migration_id="0004_add_proxy_intro_cases",
    description="Add proxy-intro case tables to matchmaking",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_PROXY_INTRO_TABLES),
    validate_fn=validate_system_schema(_PROXY_INTRO_TABLES),
)
