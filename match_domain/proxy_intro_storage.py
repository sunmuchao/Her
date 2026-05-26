"""Proxy-intro case storage (matchmaking DB only)."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

STORAGE_MATCHMAKING = "matchmaking"


@dataclass(frozen=True)
class ProxyIntroTableNames:
    cases: str
    events: str
    attempts: str


def storage_backend() -> str:
    raw = os.environ.get("HER_PROXY_INTRO_STORAGE", STORAGE_MATCHMAKING).strip().lower()
    if raw and raw != STORAGE_MATCHMAKING:
        warnings.warn(
            f"HER_PROXY_INTRO_STORAGE={raw!r} is ignored; proxy intro uses matchmaking storage only.",
            DeprecationWarning,
            stacklevel=2,
        )
    return STORAGE_MATCHMAKING


def use_matchmaking_storage() -> bool:
    return True


def table_names() -> ProxyIntroTableNames:
    return ProxyIntroTableNames(
        cases="proxy_intro_cases",
        events="proxy_intro_case_events",
        attempts="proxy_intro_case_outreach_attempts",
    )


def event_source_service() -> str:
    return "matchmaking-system"


def storage_adapter_label() -> str:
    return "matchmaking-db"


def _should_query_cases_on_conn(conn) -> bool:
    database = str((getattr(conn, "config", None) or {}).get("database") or "")
    return "matchmaking" in database


def open_proxy_intro_case_connection(recommendation_conn):
    """Return a connection that stores proxy-intro cases for this recommendation DB."""

    if _should_query_cases_on_conn(recommendation_conn):
        return recommendation_conn
    import os

    from matchmaking_system.storage import (  # noqa: PLC0415
        DEFAULT_MATCHMAKING_MYSQL_DSN,
        connect_db,
    )

    dsn = os.environ.get("PARTNER_MATCHMAKING_DB") or DEFAULT_MATCHMAKING_MYSQL_DSN
    return connect_db(dsn)


__all__ = [
    "STORAGE_MATCHMAKING",
    "ProxyIntroTableNames",
    "event_source_service",
    "open_proxy_intro_case_connection",
    "storage_adapter_label",
    "storage_backend",
    "table_names",
    "use_matchmaking_storage",
]
