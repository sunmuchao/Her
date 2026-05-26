"""Proxy-intro case lifecycle owned by matchmaking-system."""

from __future__ import annotations

from typing import Any

from match_domain.proxy_intro_storage import storage_adapter_label, use_matchmaking_storage
from recommendation_system.proxy_intro import (  # noqa: E402
    close_match_case as _close_match_case,
    close_timed_out_match_cases,
    create_match_case as _create_match_case,
    dispatch_match_case_outreach as _dispatch_match_case_outreach,
    dispatch_pending_match_cases,
    get_active_match_case_for_recommendation,
    get_latest_match_case_for_recommendation,
    get_legacy_proxy_intro_case,
    get_match_case as _get_match_case_raw,
    list_match_case_events,
    list_match_case_outreach_attempts,
    list_match_cases_for_recommendation,
    record_match_case_reply as _record_match_case_reply,
)

PROXY_INTRO_OWNER_SERVICE = "matchmaking-system"
PROXY_INTRO_STORAGE_ADAPTER = storage_adapter_label()


def _tag_proxy_intro_case(case: dict[str, Any] | None) -> dict[str, Any] | None:
    if not case:
        return None
    tagged = dict(case)
    tagged["owner_service"] = PROXY_INTRO_OWNER_SERVICE
    tagged["storage_adapter"] = PROXY_INTRO_STORAGE_ADAPTER
    return tagged


def create_match_case(case_conn, *, recommendation_conn=None, **kwargs: Any) -> dict[str, Any]:
    return _tag_proxy_intro_case(
        _create_match_case(case_conn, recommendation_conn=recommendation_conn, **kwargs)
    )


def dispatch_match_case_outreach(case_conn, *, recommendation_conn=None, **kwargs: Any) -> dict[str, Any]:
    return _tag_proxy_intro_case(
        _dispatch_match_case_outreach(case_conn, recommendation_conn=recommendation_conn, **kwargs)
    )


def record_match_case_reply(case_conn, *, recommendation_conn=None, **kwargs: Any) -> dict[str, Any]:
    return _tag_proxy_intro_case(
        _record_match_case_reply(case_conn, recommendation_conn=recommendation_conn, **kwargs)
    )


def close_match_case(case_conn, *, recommendation_conn=None, **kwargs: Any) -> dict[str, Any]:
    return _tag_proxy_intro_case(
        _close_match_case(case_conn, recommendation_conn=recommendation_conn, **kwargs)
    )


def get_match_case(
    case_conn,
    case_id: str,
    *,
    recommendation_conn=None,
    allow_legacy_read: bool = True,
) -> dict[str, Any] | None:
    case = _tag_proxy_intro_case(
        _get_match_case_raw(
            case_conn,
            case_id,
            recommendation_conn=recommendation_conn,
        )
    )
    if case or not allow_legacy_read or not use_matchmaking_storage():
        return case
    rec = recommendation_conn or case_conn
    legacy = get_legacy_proxy_intro_case(rec, case_id)
    return _tag_proxy_intro_case(legacy)


__all__ = [
    "PROXY_INTRO_OWNER_SERVICE",
    "PROXY_INTRO_STORAGE_ADAPTER",
    "close_match_case",
    "close_timed_out_match_cases",
    "create_match_case",
    "dispatch_match_case_outreach",
    "dispatch_pending_match_cases",
    "get_active_match_case_for_recommendation",
    "get_latest_match_case_for_recommendation",
    "get_match_case",
    "list_match_case_events",
    "list_match_case_outreach_attempts",
    "list_match_cases_for_recommendation",
    "record_match_case_reply",
]
