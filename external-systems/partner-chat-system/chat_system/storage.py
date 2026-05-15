"""MySQL storage for the partner chat subsystem."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from pathlib import Path
from typing import Any

DEFAULT_CHAT_MYSQL_DSN = os.environ.get(
    "PARTNER_CHAT_DB", "mysql://root@127.0.0.1:3307/her_chat"
)
DEFAULT_CHAT_TEST_MYSQL_DSN = os.environ.get(
    "PARTNER_CHAT_TEST_DB", "mysql://root@127.0.0.1:3307/her_chat_test"
)

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from her_external_systems import (  # noqa: E402
    MySQLCompatConnection,
    build_external_storage_helpers,
    json_dumps,
    json_loads,
    row_to_dict,
)


def _chat_tables() -> list[str]:
    import outer_system_mysql_schema as _schema  # noqa: PLC0415

    return list(_schema.chat_tables())


connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="Chat",
    target="chat",
    table_names=_chat_tables,
)


def inflate_json_columns(
    row: Mapping[str, Any] | None,
    /,
    **columns: tuple[str, Any] | tuple[str, Any, Callable[[Any], Any]],
) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    for target, spec in columns.items():
        source_key = spec[0]
        default = spec[1]
        value = json_loads(out.pop(source_key, None), default)
        if len(spec) > 2:
            value = spec[2](value)
        out[target] = value
    return out


__all__ = [
    "DEFAULT_CHAT_MYSQL_DSN",
    "DEFAULT_CHAT_TEST_MYSQL_DSN",
    "MySQLCompatConnection",
    "connect_db",
    "inflate_json_columns",
    "initialize_database",
    "json_dumps",
    "json_loads",
    "reset_all_tables",
    "row_to_dict",
]
