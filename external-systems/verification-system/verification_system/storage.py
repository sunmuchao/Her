"""Verification storage: identity verification, photo verification submissions, etc."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_VERIFICATION_MYSQL_DSN = os.environ.get(
    "HER_VERIFICATION_DB", "mysql://root@127.0.0.1:3307/her_verification"
)

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from her_external_systems import build_external_storage_helpers, schema_table_names

connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="verification",
    target="verification",
    table_names=schema_table_names("verification"),
    default_dsn=DEFAULT_VERIFICATION_MYSQL_DSN,
)

__all__ = [
    "DEFAULT_VERIFICATION_MYSQL_DSN",
    "connect_db",
    "initialize_database",
    "reset_all_tables",
]