"""Add auth/account tables to the chat database."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

AUTH_TABLE_NAMES = {
    "user_accounts",
    "user_account_identities",
    "auth_otp_challenges",
    "auth_sessions",
    "auth_login_events",
    "user_onboarding_profiles",
    "wechat_accounts",
}


def _auth_tables():
    return tuple(table for table in _schema.chat_tables() if table.name in AUTH_TABLE_NAMES)


def apply(mysql_conn, _context: MigrationContext) -> None:
    tables = _auth_tables()
    for table in tables:
        if not _schema.table_exists(mysql_conn, table.name):
            _schema.ensure_table(mysql_conn, table, prefix=None, config=_context.config)
        _schema.ensure_table_columns(mysql_conn, table, prefix=None)
        _schema.ensure_unique_keys(mysql_conn, table, prefix=None)
        _schema.ensure_indexes(mysql_conn, table, prefix=None)
    mysql_conn.commit()


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, _auth_tables(), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0006_add_auth_tables",
    description="Add auth and account tables to chat",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
