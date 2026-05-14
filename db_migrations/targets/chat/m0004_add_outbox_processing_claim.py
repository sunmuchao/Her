"""Add processing-claim columns for chat outbox workers."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


OUTBOX_PROCESSING_PATCH = _schema.TableDef(
    name="outbox_events",
    columns=(
        _schema.ColumnDef("processing_token", "VARCHAR(64)"),
        _schema.ColumnDef("processing_started_at", "DATETIME"),
        _schema.ColumnDef("processing_worker", "VARCHAR(191)"),
    ),
    primary_key=("outbox_id",),
    indexes=(
        _schema.IndexDef(("publish_status", "processing_started_at", "outbox_id"), "idx_outbox_processing_timeout"),
        _schema.IndexDef(("processing_token",), "idx_outbox_processing_token"),
    ),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table_columns(mysql_conn, OUTBOX_PROCESSING_PATCH, prefix=None)
    _schema.ensure_indexes(mysql_conn, OUTBOX_PROCESSING_PATCH, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (OUTBOX_PROCESSING_PATCH,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0004_add_outbox_processing_claim",
    description="Add processing claim state to chat outbox events",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
