"""Outer orchestration for empty-result opt-in on top of partner-search."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .direct_greet_gate import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
)
from .search_client import run_partner_search
from .service import create_subscription


SearchRunner = Callable[..., dict[str, Any]]

DEFAULT_NO_MATCH_OPT_IN_PROMPT = "是否需要如果有合适的我主动通知你？"


def build_search_request(
    *,
    source: str | Sequence[str] | None,
    criteria: Mapping[str, Any] | None = None,
    self_profile: Mapping[str, Any] | None = None,
    self_id: int | None = None,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    limit: int = 10,
    photo_preview_count: int = 0,
    include_source: bool = False,
    include_text: bool = False,
) -> dict[str, Any]:
    return {
        "source": source,
        "criteria": dict(criteria or {}),
        "self_profile": dict(self_profile or {}) or None,
        "self_id": self_id,
        "table_name": table_name,
        "photos_table_name": photos_table_name,
        "limit": limit,
        "photo_preview_count": photo_preview_count,
        "include_source": include_source,
        "include_text": include_text,
    }


def detect_result_count(search_response: Mapping[str, Any]) -> int:
    if "result_count" in search_response:
        return int(search_response.get("result_count") or 0)
    return len(search_response.get("results") or [])


def detect_has_match(search_response: Mapping[str, Any], result_count: int) -> bool:
    if "has_match" in search_response:
        return bool(search_response.get("has_match"))
    return result_count > 0


def normalize_subscription_source(source: Any) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, Sequence):
        normalized = [item for item in source if item]
        if len(normalized) == 1:
            return str(normalized[0])
        raise ValueError("Saved-search opt-in currently requires a single resolved source.")
    raise ValueError("Saved-search opt-in requires a source value.")


def run_search_session(
    *,
    source: str | Sequence[str] | None,
    criteria: Mapping[str, Any] | None = None,
    self_profile: Mapping[str, Any] | None = None,
    self_id: int | None = None,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    limit: int = 10,
    photo_preview_count: int = 0,
    include_source: bool = False,
    include_text: bool = False,
    search_runner: SearchRunner = run_partner_search,
) -> dict[str, Any]:
    search_request = build_search_request(
        source=source,
        criteria=criteria,
        self_profile=self_profile,
        self_id=self_id,
        table_name=table_name,
        photos_table_name=photos_table_name,
        limit=limit,
        photo_preview_count=photo_preview_count,
        include_source=include_source,
        include_text=include_text,
    )
    search_response = search_runner(**search_request)
    result_count = detect_result_count(search_response)
    has_match = detect_has_match(search_response, result_count)
    needs_opt_in_prompt = (not has_match) and result_count == 0

    return {
        "search_request": search_request,
        "search_response": search_response,
        "has_match": has_match,
        "result_count": result_count,
        "needs_opt_in_prompt": needs_opt_in_prompt,
        "opt_in_prompt": DEFAULT_NO_MATCH_OPT_IN_PROMPT if needs_opt_in_prompt else None,
    }


def subscribe_after_opt_in(
    conn,
    *,
    requester_id: int,
    search_request: Mapping[str, Any],
    subscription_overrides: Mapping[str, Any] | None = None,
    title: str | None = None,
    top_k: int = 5,
    min_notify_score: int = 40,
    daily_notification_cap: int = 2,
    quiet_hours_start: int = 22,
    quiet_hours_end: int = 9,
    refresh_interval_hours: int = 24,
    skip_cooldown_days: int = 30,
    recommendation_mode: str = DEFAULT_RECOMMENDATION_MODE,
    direct_greet_profile: Mapping[str, Any] | None = None,
    max_review_candidates_per_refresh: int = DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    min_direct_greet_score: int = DEFAULT_MIN_DIRECT_GREET_SCORE,
    auto_reject_on_follow_up_questions: bool = True,
    auto_reject_on_risk_flags: bool = True,
) -> dict[str, Any]:
    return create_subscription(
        conn,
        requester_id=requester_id,
        source=normalize_subscription_source(search_request.get("source")),
        criteria=search_request.get("criteria") or {},
        subscription_overrides=dict(subscription_overrides or {}),
        self_profile=search_request.get("self_profile"),
        self_id=search_request.get("self_id"),
        title=title,
        table_name=search_request.get("table_name"),
        photos_table_name=search_request.get("photos_table_name"),
        limit_count=int(search_request.get("limit") or 10),
        initial_request=dict(search_request or {}),
        top_k=top_k,
        min_notify_score=min_notify_score,
        daily_notification_cap=daily_notification_cap,
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
        refresh_interval_hours=refresh_interval_hours,
        skip_cooldown_days=skip_cooldown_days,
        recommendation_mode=recommendation_mode,
        direct_greet_profile=dict(direct_greet_profile or {}),
        max_review_candidates_per_refresh=max_review_candidates_per_refresh,
        min_direct_greet_score=min_direct_greet_score,
        auto_reject_on_follow_up_questions=auto_reject_on_follow_up_questions,
        auto_reject_on_risk_flags=auto_reject_on_risk_flags,
    )


def handle_opt_in_decision(
    conn,
    *,
    requester_id: int,
    search_session: Mapping[str, Any],
    user_opted_in: bool,
    title: str | None = None,
    top_k: int = 5,
    min_notify_score: int = 40,
    daily_notification_cap: int = 2,
    quiet_hours_start: int = 22,
    quiet_hours_end: int = 9,
    refresh_interval_hours: int = 24,
    skip_cooldown_days: int = 30,
    recommendation_mode: str = DEFAULT_RECOMMENDATION_MODE,
    direct_greet_profile: Mapping[str, Any] | None = None,
    max_review_candidates_per_refresh: int = DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    min_direct_greet_score: int = DEFAULT_MIN_DIRECT_GREET_SCORE,
    auto_reject_on_follow_up_questions: bool = True,
    auto_reject_on_risk_flags: bool = True,
    subscription_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not search_session.get("needs_opt_in_prompt"):
        raise ValueError("Opt-in decision is only valid for empty-result search sessions.")

    if not user_opted_in:
        return {
            "created_subscription": False,
            "subscription": None,
        }

    subscription = subscribe_after_opt_in(
        conn,
        requester_id=requester_id,
        search_request=search_session.get("search_request") or {},
        title=title,
        top_k=top_k,
        min_notify_score=min_notify_score,
        daily_notification_cap=daily_notification_cap,
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
        refresh_interval_hours=refresh_interval_hours,
        skip_cooldown_days=skip_cooldown_days,
        recommendation_mode=recommendation_mode,
        direct_greet_profile=direct_greet_profile,
        max_review_candidates_per_refresh=max_review_candidates_per_refresh,
        min_direct_greet_score=min_direct_greet_score,
        auto_reject_on_follow_up_questions=auto_reject_on_follow_up_questions,
        auto_reject_on_risk_flags=auto_reject_on_risk_flags,
        subscription_overrides=subscription_overrides,
    )
    return {
        "created_subscription": True,
        "subscription": subscription,
    }
