"""MySQL storage for the Phase 3/4 external recommendation system."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RECOMMENDATION_MYSQL_DSN = os.environ.get(
    "PARTNER_RECOMMENDATION_DB", "mysql://root@127.0.0.1:3307/her_recommendation"
)
DEFAULT_RECOMMENDATION_ROLEPLAY_MYSQL_DSN = os.environ.get(
    "PARTNER_RECOMMENDATION_ROLEPLAY_DB",
    "mysql://root@127.0.0.1:3307/her_recommendation_roleplay",
)
DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN = os.environ.get(
    "PARTNER_RECOMMENDATION_TEST_DB", "mysql://root@127.0.0.1:3307/her_recommendation_test"
)

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

import outer_system_mysql_schema as _schema  # noqa: E402

from outer_mysql_compat import (  # noqa: E402
    MySQLCompatConnection,
    connect_mysql_repo_db,
    json_dumps,
    json_loads,
    row_to_dict,
)


def connect_db(dsn: str) -> MySQLCompatConnection:
    return connect_mysql_repo_db(dsn, subsystem_name="Recommendation")


def initialize_database(conn: MySQLCompatConnection) -> None:
    _schema.ensure_database(conn.config)
    _schema.ensure_schema(conn._conn, _schema.recommendation_tables(), prefix=None, config=conn.config)
    conn.commit()


def reset_all_tables(conn: MySQLCompatConnection) -> None:
    """Delete all rows (respects FKs). Useful for tests and deterministic roleplay runs."""
    _schema.clear_tables(conn._conn, _schema.recommendation_tables(), prefix=None)
    conn.commit()


__all__ = [
    "DEFAULT_RECOMMENDATION_MYSQL_DSN",
    "DEFAULT_RECOMMENDATION_ROLEPLAY_MYSQL_DSN",
    "DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN",
    "MySQLCompatConnection",
    "connect_db",
    "initialize_database",
    "json_dumps",
    "json_loads",
    "reset_all_tables",
    "row_to_dict",
]
