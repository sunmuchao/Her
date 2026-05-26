"""Proxy-intro case storage backend selection (recommendation vs matchmaking DB)."""

from __future__ import annotations

import os
from dataclasses import dataclass


STORAGE_RECOMMENDATION = "recommendation"
STORAGE_MATCHMAKING = "matchmaking"


@dataclass(frozen=True)
class ProxyIntroTableNames:
    cases: str
    events: str
    attempts: str


def storage_backend() -> str:
    raw = os.environ.get("HER_PROXY_INTRO_STORAGE", STORAGE_MATCHMAKING).strip().lower()
    if raw in {STORAGE_RECOMMENDATION, STORAGE_MATCHMAKING}:
        return raw
    return STORAGE_MATCHMAKING


def use_matchmaking_storage() -> bool:
    return storage_backend() == STORAGE_MATCHMAKING


def table_names() -> ProxyIntroTableNames:
    if use_matchmaking_storage():
        return ProxyIntroTableNames(
            cases="proxy_intro_cases",
            events="proxy_intro_case_events",
            attempts="proxy_intro_case_outreach_attempts",
        )
    return ProxyIntroTableNames(
        cases="match_cases",
        events="match_case_events",
        attempts="match_case_outreach_attempts",
    )


def event_source_service() -> str:
    return "matchmaking-system" if use_matchmaking_storage() else "recommendation-system"


def storage_adapter_label() -> str:
    return "matchmaking-db" if use_matchmaking_storage() else "recommendation-db"


__all__ = [
    "STORAGE_MATCHMAKING",
    "STORAGE_RECOMMENDATION",
    "ProxyIntroTableNames",
    "event_source_service",
    "storage_adapter_label",
    "storage_backend",
    "table_names",
    "use_matchmaking_storage",
]
