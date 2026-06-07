"""Recommendation conversion funnel views and timelines."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from ._path_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain import (  # noqa: E402
    CaseType,
    build_canonical_event,
    build_subscription_refresh_provenance,
    bundle_recommendation_action_entities,
    correlation_relation_action,
    get_trace_id,
    idempotency_client_relation_action,
    idempotency_relation_action,
    match_events_from_action_rows,
    merge_payload_with_event,
    profile_ref_to_dict,
    recommendation_relation_key,
    recommendation_relation_refs,
    reduce_relation_ledger,
    canonical_case_status_value,
)
from match_domain.gate_runner import evaluate_recommendation_gate, recommendation_row_gate_fields  # noqa: E402
from match_domain.search_visibility import run_partner_search as _run_partner_search  # noqa: E402
from match_domain.snapshot_hash import candidate_snapshot_hash  # noqa: E402
from partner_search import load_self_profile, search_profiles  # noqa: E402
from her_time_utils import bool_to_int, current_time, format_dt, parse_dt  # noqa: E402

from .direct_greet_gate import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
    normalize_recommendation_mode,
    resolve_review_policy,
    review_candidate_for_proactive_delivery,
)
from match_domain.criteria_compiler import build_effective_search_request
from .storage import json_dumps, json_loads, row_to_dict
from relationship_ledger.runtime import (
    LedgerMirrorEntry,
    commit_conn_with_ledger,
    defer_ledger_event,
    try_get_relation_by_key,
)
from observability import (  # noqa: E402
    RECOMMENDATION_FUNNEL_ACTION,
    RECOMMENDATION_FUNNEL_DELIVERED,
    RECOMMENDATION_FUNNEL_PENDING_DELIVERY,
    RECOMMENDATION_FUNNEL_REFRESH,
    RECOMMENDATION_FUNNEL_REVIEW_PENDING,
    alert_signal,
    funnel_stage,
    metric_gauge,
)

SearchRunner = Callable[..., dict[str, Any]]
PersonaResolver = Callable[[dict[str, Any]], Optional[dict[str, Any]]]

from .recommendation_rows import (
    PROFILE_RECOMMENDATION_SELECT_SQL,
    inflate_recommendation,
    _merge_recommendation_subscription_fields,
    list_recommendation_actions_for_recommendation,
    list_recommendation_actions_for_recommendations,
    list_recommendations_for_subscription,
)
from .subscriptions import list_subscriptions_by_ids

def _inflate_recommendation_action_row(action: dict[str, Any]) -> dict[str, Any]:
    inflated = dict(action)
    inflated["action_payload"] = json_loads(inflated.pop("action_payload_json", None), {})
    return inflated


def _classify_conversion_stage(
    recommendation: dict[str, Any],
    *,
    latest_case: dict[str, Any] | None,
    action_types: set[str],
) -> tuple[str, str]:
    from match_domain.boundary import case_status_owner

    if latest_case:
        latest_case_status = str(latest_case.get("case_status") or "").strip()
        if latest_case_status:
            owner = case_status_owner(str(latest_case.get("case_type") or ""))
            return (f"case_{latest_case_status}", owner)
    if "request_proxy_intro" in action_types:
        return ("case_requested", case_status_owner(CaseType.PROXY_INTRO.value))
    recommendation_phase = str(recommendation.get("recommendation_phase") or "").strip()
    if recommendation_phase:
        return (recommendation_phase, "recommendation")
    recommendation_status = str(recommendation.get("recommendation_status") or "").strip()
    if recommendation_status:
        return (recommendation_status, "recommendation")
    return ("unknown", "system")


def _timeline_from_ledger_relation(relation: dict[str, Any]) -> list[dict[str, Any]]:
    from relationship_ledger.service import build_unified_timeline_from_ledger

    return [
        {
            "source": "relationship_ledger",
            "event_type": item.get("event_type"),
            "occurred_at": item.get("occurred_at"),
            "case_id": item.get("case_id"),
            "payload": item.get("canonical_event") or {},
        }
        for item in build_unified_timeline_from_ledger(relation)
    ]


def build_recommendation_conversion_view(
    conn,
    recommendation: dict[str, Any],
    *,
    preloaded_action_rows: list[dict[str, Any]] | None = None,
    preloaded_cases: list[dict[str, Any]] | None = None,
    preloaded_events_by_case_id: dict[str, list[dict[str, Any]]] | None = None,
    case_conn=None,
    owns_case_conn: bool | None = None,
) -> dict[str, Any]:
    from match_domain.proxy_intro_storage import open_proxy_intro_case_connection

    from .proxy_intro import list_match_case_events, list_match_cases_for_recommendation

    recommendation_id = int(recommendation["recommendation_id"])
    relation_key = str(recommendation.get("relation_key") or "").strip()
    ledger_relation = try_get_relation_by_key(relation_key) if relation_key else None
    if preloaded_action_rows is not None:
        action_rows = preloaded_action_rows
    else:
        action_rows = list_recommendation_actions_for_recommendation(conn, recommendation_id)
    actions = [_inflate_recommendation_action_row(row) for row in action_rows]
    if case_conn is None:
        case_conn = open_proxy_intro_case_connection(conn)
        owns_case_conn = case_conn is not conn
    elif owns_case_conn is None:
        owns_case_conn = case_conn is not conn
    if preloaded_cases is not None:
        cases = list(preloaded_cases)
    else:
        cases = list_match_cases_for_recommendation(
            case_conn,
            recommendation_id,
            recommendation_conn=conn,
        )
    latest_case = cases[0] if cases else None
    latest_action = actions[-1] if actions else None
    action_types = {
        str(action.get("action_type") or "").strip()
        for action in actions
        if str(action.get("action_type") or "").strip()
    }
    db_latest_case = latest_case
    if ledger_relation and ledger_relation.get("events"):
        ledger_cases = list(ledger_relation.get("cases") or [])
        ledger_latest = ledger_cases[0] if ledger_cases else None
        if ledger_latest:
            latest_case = dict(ledger_latest)
            if db_latest_case and not str(latest_case.get("case_type") or "").strip():
                latest_case["case_type"] = db_latest_case.get("case_type")
        action_types = {
            str(item.get("event_type") or "").strip()
            for item in ledger_relation.get("events") or []
            if str(item.get("event_type") or "").strip()
        }
        action_types.update(
            str(action.get("action_type") or "").strip()
            for action in actions
            if str(action.get("action_type") or "").strip()
        )
    conversion_stage, stage_owner = _classify_conversion_stage(
        recommendation,
        latest_case=latest_case,
        action_types=action_types,
    )
    if ledger_relation and ledger_relation.get("events"):
        timeline = _timeline_from_ledger_relation(ledger_relation)
        timeline_source = "relationship_ledger"
    else:
        timeline_source = "domain_fallback"
        timeline = [
            {
                "source": "recommendation_action",
                "event_type": action["action_type"],
                "occurred_at": action["occurred_at"],
                "payload": action.get("action_payload") or {},
            }
            for action in actions
        ]
        for case in reversed(cases):
            case_id = str(case["case_id"])
            if preloaded_events_by_case_id is not None:
                case_events = list(preloaded_events_by_case_id.get(case_id) or [])
            else:
                case_events = list_match_case_events(case_conn, case_id)
            for event in case_events:
                timeline.append(
                    {
                        "source": "match_case_event",
                        "case_id": case["case_id"],
                        "event_type": event["event_type"],
                        "from_status": event.get("from_status"),
                        "to_status": event.get("to_status"),
                        "occurred_at": event["occurred_at"],
                        "actor_type": event.get("actor_type"),
                        "payload": event.get("payload") or {},
                    }
                )
        timeline.sort(
            key=lambda item: (
                str(item.get("occurred_at") or ""),
                0 if item.get("source") == "recommendation_action" else 1,
                str(item.get("event_type") or ""),
            )
        )
    view = {
        "subscription_id": recommendation["subscription_id"],
        "recommendation_id": recommendation_id,
        "requester_id": recommendation["requester_id"],
        "candidate_id": recommendation["candidate_id"],
        "candidate_name": recommendation.get("candidate_name"),
        "recommendation_status": recommendation.get("recommendation_status"),
        "recommendation_phase": recommendation.get("recommendation_phase"),
        "review_policy": recommendation.get("review_policy") or {},
        "final_review_status": recommendation.get("final_review_status"),
        "system_review_decision": recommendation.get("system_review_decision"),
        "system_review_reason": recommendation.get("system_review_reason"),
        "user_review_status": recommendation.get("user_review_status"),
        "user_review_decision": recommendation.get("user_review_decision"),
        "user_review_reason_detail": recommendation.get("user_review_reason_detail"),
        "review_decision_stage": recommendation.get("review_decision_stage"),
        "requires_user_review": recommendation.get("requires_user_review"),
        "conversion_stage": conversion_stage,
        "conversion_stage_owner": stage_owner,
        "latest_action_type": latest_action.get("action_type") if latest_action else None,
        "latest_action_at": latest_action.get("occurred_at") if latest_action else None,
        "action_count": len(actions),
        "action_types": [action["action_type"] for action in actions],
        "case_count": len(cases),
        "active_match_case_id": recommendation.get("active_match_case_id"),
        "case_progress_status": recommendation.get("case_progress_status"),
        "latest_case_id": latest_case.get("case_id") if latest_case else None,
        "latest_case_status": latest_case.get("case_status") if latest_case else None,
        "latest_case_close_reason": latest_case.get("close_reason") if latest_case else None,
        "timeline": timeline,
        "timeline_source": timeline_source,
    }
    if owns_case_conn:
        case_conn.close()
    return view


def list_recommendation_conversion_views_for_subscription(
    conn,
    subscription_id: str,
) -> list[dict[str, Any]]:
    recommendation_rows = conn.execute(
        """
        SELECT """
        + PROFILE_RECOMMENDATION_SELECT_SQL
        + """
        FROM profile_recommendations
        WHERE subscription_id = ?
        ORDER BY score DESC, last_seen_at DESC, recommendation_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    if not recommendation_rows:
        return []

    recommendation_ids = []
    row_dicts = [row_to_dict(row) for row in recommendation_rows]
    subscriptions_by_id = list_subscriptions_by_ids(
        conn,
        [str(row_dict.get("subscription_id") or "").strip() for row_dict in row_dicts],
    )
    for row_dict in row_dicts:
        recommendation_ids.append(int(row_dict["recommendation_id"]))
    actions_by_recommendation_id = list_recommendation_actions_for_recommendations(conn, recommendation_ids)
    recommendations = [
        inflate_recommendation(
            _merge_recommendation_subscription_fields(
                row_dict,
                subscriptions_by_id.get(str(row_dict.get("subscription_id") or "").strip()),
            ),
            conn=conn,
            preloaded_action_rows=actions_by_recommendation_id.get(int(row_dict["recommendation_id"])),
        )
        for row_dict in row_dicts
    ]

    from match_domain.proxy_intro_storage import open_proxy_intro_case_connection

    from .proxy_intro import list_match_case_events_for_cases, list_match_cases_for_recommendations

    case_conn = open_proxy_intro_case_connection(conn)
    owns_case_conn = case_conn is not conn
    try:
        cases_by_recommendation_id = list_match_cases_for_recommendations(
            case_conn,
            recommendation_ids,
            recommendation_conn=conn,
            include_ledger_events=False,
        )
        all_case_ids = [
            str(case["case_id"])
            for cases in cases_by_recommendation_id.values()
            for case in cases
            if case.get("case_id") is not None
        ]
        events_by_case_id = list_match_case_events_for_cases(case_conn, all_case_ids)
        return [
            build_recommendation_conversion_view(
                conn,
                recommendation,
                preloaded_action_rows=actions_by_recommendation_id.get(
                    int(recommendation["recommendation_id"]),
                    [],
                ),
                preloaded_cases=cases_by_recommendation_id.get(
                    int(recommendation["recommendation_id"]),
                    [],
                ),
                preloaded_events_by_case_id=events_by_case_id,
                case_conn=case_conn,
                owns_case_conn=False,
            )
            for recommendation in recommendations
        ]
    finally:
        if owns_case_conn:
            case_conn.close()
