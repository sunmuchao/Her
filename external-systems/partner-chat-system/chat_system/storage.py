"""MySQL storage for the partner chat subsystem."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CHAT_MYSQL_DSN = os.environ.get(
    "PARTNER_CHAT_DB", "mysql://root@127.0.0.1:3307/her_chat"
)
DEFAULT_CHAT_TEST_MYSQL_DSN = os.environ.get(
    "PARTNER_CHAT_TEST_DB", "mysql://root@127.0.0.1:3307/her_chat_test"
)

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from db_migrations import initialize_target_database  # noqa: E402
import outer_system_mysql_schema as _schema  # noqa: E402

from outer_mysql_compat import (  # noqa: E402
    MySQLCompatConnection,
    connect_mysql_repo_db,
    json_dumps,
    json_loads,
    row_to_dict,
)


def connect_db(dsn: str) -> MySQLCompatConnection:
    return connect_mysql_repo_db(dsn, subsystem_name="Chat")


def initialize_database(conn: MySQLCompatConnection, *, mode: str | None = None) -> None:
    initialize_target_database(conn, target="chat", mode=mode)


def reset_all_tables(conn: MySQLCompatConnection) -> None:
    _schema.clear_tables(conn._conn, _schema.chat_tables(), prefix=None)
    conn.commit()


__all__ = [
    "DEFAULT_CHAT_MYSQL_DSN",
    "DEFAULT_CHAT_TEST_MYSQL_DSN",
    "MySQLCompatConnection",
    "connect_db",
    "initialize_database",
    "json_dumps",
    "json_loads",
    "reset_all_tables",
    "row_to_dict",
]
