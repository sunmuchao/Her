"""Helpers for spawning worker DB connections that match a parent connection."""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote


def dsn_from_connection(conn: Any) -> str | None:
    stored = getattr(conn, "dsn", None)
    if stored:
        return str(stored)
    config = getattr(conn, "config", None)
    if not isinstance(config, dict):
        return None
    database = str(config.get("database") or "").strip()
    if not database:
        return None
    host = str(config.get("host") or "127.0.0.1")
    port = int(config.get("port") or 3306)
    user = str(config.get("user") or "root")
    password = str(config.get("password") or "")
    if password:
        auth = f"{quote(user, safe='')}:{quote(password, safe='')}@"
    else:
        auth = f"{quote(user, safe='')}@"
    return f"mysql://{auth}{host}:{port}/{database}"


def worker_connect_factory(
    parent_conn: Any,
    default_connect: Callable[[str | None], Any],
) -> Callable[[], Any]:
    parent_dsn = dsn_from_connection(parent_conn)

    def _connect() -> Any:
        return default_connect(parent_dsn)

    return _connect
