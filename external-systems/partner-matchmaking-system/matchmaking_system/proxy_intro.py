"""Proxy-intro case lifecycle owned by matchmaking-system."""

from __future__ import annotations

from typing import Any

from match_domain.proxy_intro_storage import storage_adapter_label
from .proxy_intro_core import (  # noqa: E402
    close_match_case as _close_match_case,
    close_timed_out_match_cases,
    create_match_case as _create_match_case,
    dispatch_match_case_outreach as _dispatch_match_case_outreach,
    dispatch_pending_match_cases,
    get_active_match_case_for_recommendation,
    get_latest_match_case_for_recommendation,
    get_match_case as _get_match_case_raw,
    list_match_case_events,
    list_match_case_outreach_attempts,
    list_match_cases_for_participant,
    list_match_cases_for_recommendation,
    mark_case_as_viewed as _mark_case_as_viewed,  # ✅ 新增
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


def mark_case_as_viewed(case_conn, *, recommendation_conn=None, **kwargs: Any) -> dict[str, Any]:
    """标记被动推荐为已查看状态"""
    return _tag_proxy_intro_case(
        _mark_case_as_viewed(case_conn, recommendation_conn=recommendation_conn, **kwargs)
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
    del allow_legacy_read
    return _tag_proxy_intro_case(
        _get_match_case_raw(
            case_conn,
            case_id,
            recommendation_conn=recommendation_conn,
        )
    )


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
    "list_match_cases_for_participant",
    "list_match_cases_for_recommendation",
    "record_match_case_reply",
]
