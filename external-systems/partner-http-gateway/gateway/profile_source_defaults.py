"""Resolve default partner profile MySQL source from gateway environment."""

from __future__ import annotations

import os

from profile_source_refs import resolve_profile_source


def default_profile_source() -> tuple[str, str]:
    for key in (
        "HER_PROFILE_SOURCE_DSN",
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
    ):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        source_dsn, table_name = resolve_profile_source(raw)
        if source_dsn and table_name:
            return source_dsn, table_name
    raise ValueError(
        "Profile source is not configured. Set HER_DISCOVERY_PROFILE_SOURCE or HER_PROFILE_SOURCE_DSN."
    )


def body_with_default_profile_source(body: dict) -> dict:
    merged = dict(body)
    source_dsn = str(merged.get("source_dsn") or merged.get("source") or "").strip()
    if source_dsn:
        return merged
    dsn, table_name = default_profile_source()
    merged["source_dsn"] = dsn
    if not str(merged.get("source_table_name") or merged.get("table_name") or "").strip():
        merged["source_table_name"] = table_name
    return merged
