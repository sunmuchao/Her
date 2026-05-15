"""Shared helpers for DSN/table source references."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


def resolve_profile_source(
    source_dsn: str | None,
    source_table_name: str | None = None,
) -> tuple[str | None, str | None]:
    dsn = str(source_dsn or "").strip() or None
    if not dsn:
        return None, None
    explicit = str(source_table_name or "").strip() or None
    if explicit:
        return dsn, explicit
    parsed = urlparse(dsn)
    query = parse_qs(parsed.query)
    table_name = query.get("table", [None])[0]
    normalized = str(table_name or "").strip()
    return dsn, unquote(normalized) if normalized else None


def build_source_file_ref(source_dsn: str | None, source_table_name: str | None = None) -> str:
    dsn = str(source_dsn or "").strip()
    if not dsn:
        return ""
    table_name = str(source_table_name or "").strip()
    return f"{dsn}#{table_name}" if table_name else dsn


def split_source_file_ref(source_ref: str | None) -> tuple[str, str | None]:
    normalized = str(source_ref or "").strip()
    if not normalized:
        return "", None
    source_dsn, separator, table_name = normalized.rpartition("#")
    if not separator:
        return normalized, None
    return source_dsn, table_name or None
