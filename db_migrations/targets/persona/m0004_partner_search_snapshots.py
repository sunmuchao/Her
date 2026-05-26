"""Add partner_search_snapshots table for criteria result persistence (§10.3 performance)."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

PARTNER_SEARCH_SNAPSHOTS = _schema.TableDef(
    name="partner_search_snapshots",
    columns=(
        _schema.ColumnDef("criteria_hash", "VARCHAR(64)", nullable=False),
        _schema.ColumnDef("search_run_json", "LONGTEXT", nullable=False),
        _schema.ColumnDef("expires_at", "DATETIME", nullable=False),
        _schema.ColumnDef("updated_at", "DATETIME", nullable=False),
    ),
    primary_key=("criteria_hash",),
    indexes=(
        _schema.IndexDef(("expires_at",), "idx_partner_search_snapshots_expires"),
    ),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table(mysql_conn, PARTNER_SEARCH_SNAPSHOTS, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (PARTNER_SEARCH_SNAPSHOTS,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0004_partner_search_snapshots",
    description="Persist hot partner_search criteria runs (materialized snapshot store)",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
