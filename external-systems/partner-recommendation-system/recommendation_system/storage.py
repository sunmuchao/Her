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

from her_external_systems import (  # noqa: E402
    MySQLCompatConnection,
    build_external_storage_helpers,
    json_dumps,
    json_loads,
    row_to_dict,
    schema_table_names,
)


connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="Recommendation",
    target="recommendation",
    table_names=schema_table_names("recommendation_tables"),
    default_dsn=DEFAULT_RECOMMENDATION_MYSQL_DSN,
)


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
