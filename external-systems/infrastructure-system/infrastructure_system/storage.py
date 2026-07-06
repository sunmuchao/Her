"""Infrastructure storage: outbox_events and async_jobs tables."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_INFRASTRUCTURE_MYSQL_DSN = os.environ.get(
    "HER_INFRASTRUCTURE_DB", "mysql://root@127.0.0.1:3307/her_infrastructure"
)

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from her_external_systems import build_external_storage_helpers, schema_table_names
from outer_system_mysql_schema import ASYNC_JOB_TABLE

# Default DSN from environment
DEFAULT_INFRASTRUCTURE_MYSQL_DSN = os.environ.get(
    "HER_INFRASTRUCTURE_DB", "mysql://root@127.0.0.1:3307/her_infrastructure"
)


def _outbox_events_table():
    """Create outbox_events table definition."""
    from outer_system_mysql_schema import ColumnDef, IndexDef, TableDef, UniqueKeyDef

    return TableDef(
        name="outbox_events",
        columns=(
            ColumnDef("outbox_id", "BIGINT", nullable=False, auto_increment=True),
            ColumnDef("canonical_event_id", "VARCHAR(64)", nullable=False),
            ColumnDef("aggregate_type", "VARCHAR(32)", nullable=False),
            ColumnDef("aggregate_id", "VARCHAR(191)", nullable=False),
            ColumnDef("event_type", "VARCHAR(64)", nullable=False),
            ColumnDef("source_service", "VARCHAR(64)", nullable=False),
            ColumnDef("canonical_event_json", "LONGTEXT", nullable=False),
            ColumnDef("source_row_table", "VARCHAR(64)", nullable=False),
            ColumnDef("source_row_id", "BIGINT", nullable=True),
            ColumnDef("publish_status", "VARCHAR(32)", nullable=False),
            ColumnDef("created_at", "DATETIME", nullable=False),
            ColumnDef("published_at", "DATETIME", nullable=True),
        ),
        primary_key=("outbox_id",),
        uniques=(
            UniqueKeyDef(("canonical_event_id",), name="uniq_infra_outbox_canonical_event_id"),
        ),
        indexes=(
            IndexDef(("publish_status", "created_at"), "idx_infra_outbox_pending_time"),
            IndexDef(("source_service", "publish_status", "created_at"), "idx_infra_outbox_service_status"),
        ),
    )


# Define tables
INFRASTRUCTURE_TABLES = (
    _outbox_events_table(),
    ASYNC_JOB_TABLE,
)

# Build helper functions using shared infrastructure
connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="infrastructure",
    target="infrastructure",
    table_names=schema_table_names("infrastructure"),
    default_dsn=DEFAULT_INFRASTRUCTURE_MYSQL_DSN,
)


__all__ = [
    "DEFAULT_INFRASTRUCTURE_MYSQL_DSN",
    "INFRASTRUCTURE_TABLES",
    "connect_db",
    "initialize_database",
    "reset_all_tables",
]