"""Add database-configurable auth phone role bindings."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

TABLE_NAME = "auth_phone_role_bindings"


def _table():
    return tuple(table for table in _schema.chat_tables() if table.name == TABLE_NAME)


def apply(mysql_conn, _context: MigrationContext) -> None:
    tables = _table()
    for table in tables:
        if not _schema.table_exists(mysql_conn, table.name):
            _schema.ensure_table(mysql_conn, table, prefix=None, config=_context.config)
        _schema.ensure_table_columns(mysql_conn, table, prefix=None)
        _schema.ensure_unique_keys(mysql_conn, table, prefix=None)
        _schema.ensure_indexes(mysql_conn, table, prefix=None)
    mysql_conn.commit()


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, _table(), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0008_add_auth_phone_role_bindings",
    description="Add database-configurable auth phone role bindings",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
