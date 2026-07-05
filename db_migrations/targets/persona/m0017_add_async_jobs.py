"""Add persisted async jobs table for persona photo workflows."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from async_jobs.queue import ASYNC_JOB_TABLE
from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


def apply(mysql_conn, _context: MigrationContext) -> None:
    if not _schema.table_exists(mysql_conn, ASYNC_JOB_TABLE.name):
        _schema.ensure_table(mysql_conn, ASYNC_JOB_TABLE, prefix=None, config=_context.config)
    _schema.ensure_table_columns(mysql_conn, ASYNC_JOB_TABLE, prefix=None)
    _schema.ensure_indexes(mysql_conn, ASYNC_JOB_TABLE, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (ASYNC_JOB_TABLE,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0017_add_async_jobs",
    description="Add persisted async jobs to persona",
    scope_fn=persona_scope,
    apply_fn=apply,
    validate_fn=validate,
)
