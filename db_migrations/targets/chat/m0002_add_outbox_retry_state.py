"""Add retry-state columns for chat outbox delivery."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


OUTBOX_RETRY_STATE_PATCH = _schema.TableDef(
    name="outbox_events",
    columns=(
        _schema.ColumnDef("publish_attempts", "INT DEFAULT 0", nullable=False),
        _schema.ColumnDef("last_attempt_at", "DATETIME"),
        _schema.ColumnDef("next_retry_at", "DATETIME"),
        _schema.ColumnDef("last_error", "TEXT"),
    ),
    primary_key=("outbox_id",),
    indexes=(
        _schema.IndexDef(("publish_status", "next_retry_at", "outbox_id"), "idx_outbox_retry_due"),
    ),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table_columns(mysql_conn, OUTBOX_RETRY_STATE_PATCH, prefix=None)
    _schema.ensure_indexes(mysql_conn, OUTBOX_RETRY_STATE_PATCH, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (OUTBOX_RETRY_STATE_PATCH,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0002_add_outbox_retry_state",
    description="Add retry state to chat outbox events",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
