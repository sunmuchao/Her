"""MySQL storage for the unified relationship ledger."""

from __future__ import annotations

import os

from her_external_systems import (
    MySQLCompatConnection,
    build_external_storage_helpers,
    json_dumps,
    json_loads,
    row_to_dict,
    schema_table_names,
)


DEFAULT_RELATION_LEDGER_MYSQL_DSN = os.environ.get(
    "HER_RELATION_LEDGER_DB",
    "mysql://root@127.0.0.1:3307/her_relationship_ledger",
)
DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN = os.environ.get(
    "HER_RELATION_LEDGER_TEST_DB",
    "mysql://root@127.0.0.1:3307/her_relationship_ledger_test",
)


connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="RelationshipLedger",
    target="relationship_ledger",
    table_names=schema_table_names("relationship_ledger_tables"),
)


__all__ = [
    "DEFAULT_RELATION_LEDGER_MYSQL_DSN",
    "DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN",
    "MySQLCompatConnection",
    "connect_db",
    "initialize_database",
    "json_dumps",
    "json_loads",
    "reset_all_tables",
    "row_to_dict",
]

