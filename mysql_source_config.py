"""Shared MySQL source parsing helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}


def parse_mysql_source_config(
    source_dsn: str,
    *,
    source_label: str = "MySQL source",
    table_name: str | None = None,
    photos_table_name: str | None = None,
    default_table_name: str | None = None,
    default_photos_table_name: str | None = None,
    default_charset: str = "utf8mb4",
    default_host: str = "127.0.0.1",
    default_port: int = 3306,
    include_source: bool = False,
) -> dict[str, Any]:
    parsed = urlparse(str(source_dsn))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        raise ValueError(f"Unsupported {source_label}: {source_dsn}")

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError(f"{source_label} must include a database name.")

    query = parse_qs(parsed.query)
    config: dict[str, Any] = {
        "host": parsed.hostname or default_host,
        "port": parsed.port or default_port,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": database,
        "table": table_name or query.get("table", [default_table_name])[0],
        "photos_table": photos_table_name or query.get("photos_table", [default_photos_table_name])[0],
        "charset": query.get("charset", [default_charset])[0],
    }
    if include_source:
        config["source"] = str(source_dsn)

    unix_socket = query.get("unix_socket", [None])[0]
    if unix_socket:
        config["unix_socket"] = unquote(unix_socket)

    return config
