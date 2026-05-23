"""Baseline relationship-ledger schema migration."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.helpers import apply_system_schema, baseline_migration, default_scope, validate_system_schema


MIGRATION = baseline_migration(
    description="Baseline relationship ledger schema",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_schema.relationship_ledger_tables()),
    validate_fn=validate_system_schema(_schema.relationship_ledger_tables()),
)

