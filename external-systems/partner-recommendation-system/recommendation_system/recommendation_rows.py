"""Profile recommendation rows, gates, actions, and user reviews."""

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

from .recommendation_transactions import commit_recommendation_transaction
from .subscriptions import get_subscription, list_subscriptions_by_ids


_SUBSCRIPTION_RECOMMENDATION_FIELDS = (
    "source",
    "self_id",
    "subscription_overrides_json",
    "recommendation_mode",
    "max_review_candidates_per_refresh",
    "min_direct_greet_score",
    "auto_reject_on_follow_up_questions",
    "auto_reject_on_risk_flags",
    "daily_notification_cap",
    "quiet_hours_start",
    "quiet_hours_end",
    "title",
)

_PROFILE_RECOMMENDATION_COLUMNS = (
    "recommendation_id",
    "subscription_id",
    "requester_id",
    "candidate_id",
    "candidate_name",
    "score",
    "fit_score",
    "confidence_score",
    "risk_score",
    "delivery_status",
    "delivery_reason",
    "first_seen_at",
    "last_seen_at",
    "notified_at",
    "cooling_until",
    "last_action_type",
    "matched_on_json",
    "risk_flags_json",
    "latest_payload_json",
    "final_review_status",
    "final_review_reason",
    "final_review_score",
    "final_review_payload_json",
    "reviewed_at",
    "candidate_snapshot_hash",
    "user_review_status",
    "user_review_reason",
    "user_review_payload_json",
    "user_reviewed_at",
    "relation_key",
    "owner_profile_ref_json",
    "target_profile_ref_json",
    "active_match_case_id",
    "active_case_status",
    "gate_outcome",
    "gate_reason_codes_json",
    "gate_owner_service",
    "gate_details_ref",
    "gate_evaluated_at",
    "latest_card_id",
    "rule_provenance_json",
)


def _record_appearance_feedback_from_recommendation(
    *,
    subscription: dict[str, Any],
    recommendation: dict[str, Any],
    event_type: str,
    event_weight: float,
    scene: str,
) -> None:
    try:
        from match_domain.appearance_features import (
            rebuild_user_preference_from_history,
            record_feedback_event,
            refresh_profile_photo_features,
        )

        source_dsn = str(
            os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
            or subscription.get("source")
            or ""
        ).strip()
        user_key = str(subscription.get("requester_id") or recommendation.get("requester_id") or "").strip()
        profile_id = int(subscription.get("self_id") or 0) or None
        candidate_id = int(recommendation.get("candidate_id") or 0)
        if not source_dsn or not user_key or candidate_id <= 0:
            return
        refresh_profile_photo_features(
            source_dsn=source_dsn,
            profile_source_dsn=str(subscription.get("source") or "").strip() or None,
            profile_id=candidate_id,
        )
        record_feedback_event(
            source_dsn=source_dsn,
            user_key=user_key,
            profile_id=int(profile_id or 0),
            candidate_profile_id=candidate_id,
            event_type=event_type,
            event_weight=event_weight,
            scene=scene,
            metadata={
                "source": scene,
                "subscription_id": subscription.get("subscription_id"),
                "recommendation_id": recommendation.get("recommendation_id"),
            },
        )
        rebuild_user_preference_from_history(
            source_dsn=source_dsn,
            user_key=user_key,
            profile_id=profile_id,
            scene=scene,
        )
    except Exception:
        return

PROFILE_RECOMMENDATION_SELECT_SQL = ", ".join(_PROFILE_RECOMMENDATION_COLUMNS)


def _merge_recommendation_subscription_fields(
    recommendation: dict[str, Any],
    subscription: dict[str, Any] | None,
) -> dict[str, Any]:
    if not subscription:
        return recommendation
    merged = dict(recommendation)
    for field in _SUBSCRIPTION_RECOMMENDATION_FIELDS:
        if field in subscription and field not in merged:
            merged[field] = subscription[field]
    if "subscription_title" not in merged and subscription.get("title") is not None:
        merged["subscription_title"] = subscription.get("title")
    return merged

def list_recommendations_for_subscription(
    conn,
    subscription_id: str,
    *,
    preloaded_actions_by_recommendation_id: dict[int, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
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
    row_dicts = [row_to_dict(row) for row in rows]
    if not row_dicts:
        return []
    if preloaded_actions_by_recommendation_id is None:
        preloaded_actions_by_recommendation_id = list_recommendation_actions_for_recommendations(
            conn,
            [
                int(row_dict["recommendation_id"])
                for row_dict in row_dicts
                if row_dict.get("recommendation_id") is not None
            ],
        )
    subscription = list_subscriptions_by_ids(conn, [subscription_id]).get(subscription_id)
    inflated: list[dict[str, Any]] = []
    for row_dict in row_dicts:
        row_dict = _merge_recommendation_subscription_fields(row_dict, subscription)
        rid = row_dict.get("recommendation_id")
        preloaded = None
        if preloaded_actions_by_recommendation_id is not None and rid is not None:
            preloaded = preloaded_actions_by_recommendation_id.get(int(rid))
        inflated.append(
            inflate_recommendation(
                row_dict,
                conn=conn,
                preloaded_action_rows=preloaded,
            )
        )
    return inflated


def list_recommendation_actions_for_recommendations(
    conn,
    recommendation_ids: Iterable[int],
) -> dict[int, list[dict[str, Any]]]:
    normalized = [int(item) for item in recommendation_ids]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT action_id, subscription_id, recommendation_id, requester_id, candidate_id,
               action_type, action_payload_json, occurred_at
        FROM recommendation_actions
        WHERE recommendation_id IN ({placeholders})
        ORDER BY recommendation_id ASC, occurred_at ASC, action_id ASC
        """,
        normalized,
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = row_to_dict(row)
        rid = int(row_dict["recommendation_id"])
        grouped.setdefault(rid, []).append(row_dict)
    return grouped


def list_recommendation_actions_for_recommendation(
    conn,
    recommendation_id: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT action_id, subscription_id, recommendation_id, requester_id, candidate_id,
               action_type, action_payload_json, occurred_at
        FROM recommendation_actions
        WHERE recommendation_id = ?
        ORDER BY occurred_at ASC, action_id ASC
        """,
        (int(recommendation_id),),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def _hydrate_recommendation_relation_metadata(
    recommendation: dict[str, Any],
    *,
    conn=None,
    preloaded_action_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger_events = []
    rid = recommendation.get("recommendation_id")
    if rid is not None:
        if preloaded_action_rows is not None:
            rows = preloaded_action_rows
        elif conn is not None:
            rows = list_recommendation_actions_for_recommendation(conn, int(rid))
        else:
            rows = []
        if rows:
            ledger_events = match_events_from_action_rows(
                rows,
                payload_loader=lambda raw: json_loads(raw, {}),
            )
    recommendation["relation_ledger_event_count"] = len(ledger_events)
    reduced = reduce_relation_ledger(ledger_events)
    recommendation["canonical_relation_status"] = reduced.status.value
    if reduced.active_match_case_id:
        recommendation["relation_ledger_active_match_case_id"] = reduced.active_match_case_id
    else:
        recommendation.pop("relation_ledger_active_match_case_id", None)
    _apply_recommendation_boundary_projection(recommendation, conn=conn)
    return recommendation


def _derive_recommendation_phase(delivery_status: str | None) -> str | None:
    phase_map = {
        "review_pending": "review_queue",
        "pending_delivery": "delivery_queue",
        "delivered": "delivered",
        "direct_greet_started": "direct_greet",
        "saved_by_user": "saved",
        "cooled_down": "cooldown",
        "suppressed": "suppressed",
        "escalated_to_case": "case_handoff",
    }
    return phase_map.get(str(delivery_status or "").strip() or None)


def _derive_case_progress_status(recommendation: dict[str, Any]) -> str | None:
    active_case_status = canonical_case_status_value(recommendation.get("active_case_status"))
    if active_case_status:
        return active_case_status
    if recommendation.get("delivery_status") != "escalated_to_case":
        return None
    canonical_relation_status = str(recommendation.get("canonical_relation_status") or "").strip()
    if canonical_relation_status == "closed":
        return "closed"
    return "historical"


def _apply_review_projection(recommendation: dict[str, Any], *, conn=None) -> None:
    review_policy_source = recommendation
    if "subscription_overrides_json" not in recommendation and conn is not None:
        subscription_id = str(recommendation.get("subscription_id") or "").strip()
        if subscription_id:
            try:
                review_policy_source = get_subscription(conn, subscription_id)
            except Exception:
                review_policy_source = recommendation
    review_policy = resolve_review_policy(review_policy_source)
    recommendation["review_policy"] = review_policy
    recommendation["system_review_decision"] = recommendation.get("final_review_status")
    recommendation["system_review_reason"] = recommendation.get("final_review_reason")
    recommendation["user_review_decision"] = recommendation.get("user_review_status")
    recommendation["user_review_reason_detail"] = recommendation.get("user_review_reason")
    recommendation["review_policy_owner"] = "recommendation"
    recommendation["requires_user_review"] = (
        review_policy["recommendation_mode"] == "direct_greet_only"
        and recommendation.get("final_review_status") == "direct_greet_ready"
    )
    if recommendation.get("user_review_status") in {"direct_greet", "save", "skip"}:
        recommendation["review_decision_stage"] = "user_decided"
    elif recommendation.get("user_review_status") == "pending_review":
        recommendation["review_decision_stage"] = "awaiting_user_review"
    else:
        recommendation["review_decision_stage"] = "system_decided"


def _apply_recommendation_boundary_projection(recommendation: dict[str, Any], *, conn=None) -> None:
    recommendation["recommendation_status"] = recommendation.get("delivery_status")
    recommendation["recommendation_phase"] = _derive_recommendation_phase(
        recommendation.get("delivery_status")
    )
    recommendation["case_progress_status"] = _derive_case_progress_status(recommendation)
    recommendation["recommendation_status_owner"] = "recommendation"
    recommendation["case_progress_owner"] = (
        "matchmaking" if recommendation.get("case_progress_status") is not None else None
    )
    _apply_review_projection(recommendation, conn=conn)


def insert_recommendation_action(
    conn,
    *,
    subscription: dict[str, Any],
    recommendation: dict[str, Any],
    action_type: str,
    actor_type: str,
    actor_id: str | None = None,
    now: datetime,
    action_payload: dict[str, Any] | None = None,
    client_idempotency_key: str | None = None,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
) -> None:
    relation_key = recommendation.get("relation_key")
    if not relation_key:
        relation_key = recommendation_relation_key(subscription, int(recommendation["candidate_id"]))
    owner_profile_ref = recommendation.get("owner_profile_ref") or json_loads(
        recommendation.get("owner_profile_ref_json"),
        None,
    )
    target_profile_ref = recommendation.get("target_profile_ref") or json_loads(
        recommendation.get("target_profile_ref_json"),
        None,
    )
    rid = int(recommendation["recommendation_id"])
    idem_key = (
        idempotency_client_relation_action(rid, client_idempotency_key)
        if client_idempotency_key
        else idempotency_relation_action(rid, action_type, format_dt(now))
    )
    event = build_canonical_event(
        event_type=action_type,
        aggregate_type="relation",
        aggregate_id=relation_key,
        actor_type=actor_type,
        actor_id=str(actor_id or subscription["requester_id"]),
        source_service="recommendation-system",
        correlation_id=correlation_relation_action(rid, action_type),
        idempotency_key=idem_key,
        occurred_at=now,
        payload={
            "subscription_id": subscription["subscription_id"],
            "recommendation_id": recommendation["recommendation_id"],
            "candidate_id": recommendation["candidate_id"],
            **dict(action_payload or {}),
        },
        entity_ids=bundle_recommendation_action_entities(
            subscription=subscription,
            relation_key=relation_key,
            recommendation_id=rid,
            candidate_id=int(recommendation["candidate_id"]),
        ),
    )
    conn.execute(
        """
        INSERT INTO recommendation_actions (
          subscription_id,
          recommendation_id,
          requester_id,
          candidate_id,
          action_type,
          action_payload_json,
          client_idempotency_key,
          occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subscription["subscription_id"],
            recommendation["recommendation_id"],
            recommendation["requester_id"],
            recommendation["candidate_id"],
            action_type,
            json_dumps(merge_payload_with_event(action_payload, event)),
            str(client_idempotency_key).strip() if client_idempotency_key else None,
            format_dt(now),
        ),
    )
    entry: LedgerMirrorEntry = {
        "event": event,
        "relation_key": str(relation_key),
        "owner_profile_ref": owner_profile_ref,
        "target_profile_ref": target_profile_ref,
    }
    if ledger_mirror is not None:
        ledger_mirror.append(entry)
    else:
        defer_ledger_event(conn, entry)


def append_relation_state_revision_event(
    conn,
    *,
    subscription: dict[str, Any],
    recommendation_row: dict[str, Any],
    now: datetime,
) -> None:
    insert_recommendation_action(
        conn,
        subscription=subscription,
        recommendation=recommendation_row,
        action_type="relation_state_revision",
        actor_type="system",
        actor_id="system",
        now=now,
        action_payload={
            "delivery_status": recommendation_row.get("delivery_status"),
            "delivery_reason": recommendation_row.get("delivery_reason"),
            "last_action_type": recommendation_row.get("last_action_type"),
            "active_match_case_id": recommendation_row.get("active_match_case_id"),
            "active_case_status": recommendation_row.get("active_case_status"),
            "rule_provenance": json_loads(recommendation_row.get("rule_provenance_json"), {}),
        },
    )


# Backward-compatible alias for older internal imports.
_recommendation_action_insert = insert_recommendation_action


def normalize_delivery_status(
    existing: dict[str, Any] | None,
    result: dict[str, Any],
    subscription: dict[str, Any],
    now: datetime,
    final_review: dict[str, Any],
) -> tuple[str, str]:
    if existing:
        active_match_case_id = existing.get("active_match_case_id")
        if active_match_case_id:
            return ("escalated_to_case", "proxy_intro_case_active")

    skip_cooldown_expired = False
    if existing and existing.get("delivery_status") == "cooled_down":
        cooling_until = parse_dt(existing.get("cooling_until"))
        if cooling_until and now < cooling_until:
            return ("cooled_down", existing.get("delivery_reason") or "cooldown_active")
    if existing and existing.get("last_action_type") == "save":
        return ("saved_by_user", "user_saved_candidate")
    if existing and existing.get("last_action_type") == "direct_greet":
        return ("direct_greet_started", "user_started_direct_greet")
    if existing and existing.get("last_action_type") == "skip":
        cooling_until = parse_dt(existing.get("cooling_until"))
        if cooling_until and now < cooling_until:
            return ("cooled_down", "skip_cooldown_active")
        skip_cooldown_expired = True

    if int(result.get("score") or 0) < int(subscription.get("min_notify_score") or 0):
        return ("suppressed", "score_below_notify_threshold")

    if existing and existing.get("notified_at") and not skip_cooldown_expired:
        return ("delivered", "candidate_already_notified")

    recommendation_mode = normalize_recommendation_mode(subscription.get("recommendation_mode"))
    final_review_status = final_review["status"]
    if recommendation_mode == "direct_greet_only":
        if final_review_status == "review_deferred":
            return ("review_pending", final_review["reason"])
        if final_review_status == "rejected":
            return ("suppressed", final_review["reason"])
        if final_review_status == "save_only":
            return ("review_pending", final_review["reason"])
        if final_review_status == "direct_greet_ready":
            user_review_status = (existing or {}).get("user_review_status")
            if user_review_status == "direct_greet":
                return ("pending_delivery", "user_review_direct_greet")
            if user_review_status == "save":
                return ("saved_by_user", "user_review_save")
            if user_review_status == "skip":
                return ("cooled_down", "user_review_skip")
            return ("review_pending", final_review["reason"])

    if skip_cooldown_expired:
        return ("pending_delivery", "skip_cooldown_expired")
    if existing and existing.get("delivery_status") == "pending_delivery":
        return ("pending_delivery", "still_pending_delivery")
    return ("pending_delivery", "new_candidate")


def inflate_recommendation(
    recommendation: dict[str, Any],
    *,
    conn=None,
    preloaded_action_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not recommendation:
        return recommendation
    inflated = dict(recommendation)
    inflated["matched_on"] = json_loads(inflated.pop("matched_on_json"), [])
    inflated["risk_flags"] = json_loads(inflated.pop("risk_flags_json"), [])
    inflated["latest_payload"] = json_loads(inflated.pop("latest_payload_json"), {})
    inflated["final_review_payload"] = json_loads(inflated.pop("final_review_payload_json"), {})
    inflated["user_review_payload"] = json_loads(inflated.pop("user_review_payload_json"), {})
    inflated["owner_profile_ref"] = json_loads(inflated.pop("owner_profile_ref_json", None), {})
    inflated["target_profile_ref"] = json_loads(inflated.pop("target_profile_ref_json", None), {})
    inflated["rule_provenance"] = json_loads(inflated.pop("rule_provenance_json", None), {})
    inflated["gate_reason_codes"] = json_loads(inflated.pop("gate_reason_codes_json", None), [])
    if inflated.get("gate_outcome"):
        inflated["gate_decision"] = {
            "outcome": inflated.get("gate_outcome"),
            "reason_codes": inflated.get("gate_reason_codes") or [],
            "owner_service": inflated.get("gate_owner_service"),
            "details_ref": inflated.get("gate_details_ref"),
            "evaluated_at": inflated.get("gate_evaluated_at"),
        }
    return _hydrate_recommendation_relation_metadata(
        inflated,
        conn=conn,
        preloaded_action_rows=preloaded_action_rows,
    )


def get_recommendation(conn, subscription_id: str, candidate_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT """
        + PROFILE_RECOMMENDATION_SELECT_SQL
        + """
        FROM profile_recommendations
        WHERE subscription_id = ? AND candidate_id = ?
        """,
        (subscription_id, candidate_id),
    ).fetchone()
    row_dict = row_to_dict(row)
    if not row_dict:
        return None
    subscription = list_subscriptions_by_ids(conn, [subscription_id]).get(subscription_id)
    return inflate_recommendation(
        _merge_recommendation_subscription_fields(row_dict, subscription),
        conn=conn,
    )


def get_recommendation_by_id(conn, recommendation_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT """
        + PROFILE_RECOMMENDATION_SELECT_SQL
        + """
        FROM profile_recommendations
        WHERE recommendation_id = ?
        """,
        (int(recommendation_id),),
    ).fetchone()
    row_dict = row_to_dict(row)
    if not row_dict:
        return None
    subscription_id = str(row_dict.get("subscription_id") or "").strip()
    subscription = list_subscriptions_by_ids(conn, [subscription_id]).get(subscription_id)
    return inflate_recommendation(
        _merge_recommendation_subscription_fields(row_dict, subscription),
        conn=conn,
    )


def upsert_recommendation(
    conn,
    subscription: dict[str, Any],
    result: dict[str, Any],
    now: datetime,
    *,
    review_rank: int,
    rule_provenance: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = result.get("id")
    if candidate_id is None:
        raise ValueError("Structured search results must contain a candidate id for Phase 3 history tracking.")

    existing = get_recommendation(conn, subscription["subscription_id"], int(candidate_id))
    final_review = review_candidate_for_proactive_delivery(
        subscription,
        result,
        review_rank=review_rank,
        conn=conn,
    )
    prev_delivery_status = (existing or {}).get("delivery_status")
    delivery_status, delivery_reason = normalize_delivery_status(existing, result, subscription, now, final_review)
    gate_decision = evaluate_recommendation_gate(
        candidate_id=int(candidate_id),
        final_review=final_review,
        risk_flags=list(result.get("risk_flags") or []),
    )
    gate_fields = recommendation_row_gate_fields(gate_decision)
    payload_json = json_dumps(result)
    matched_on_json = json_dumps(result.get("matched_on") or [])
    risk_flags_json = json_dumps([] if gate_fields.get("gate_details_ref") else (result.get("risk_flags") or []))
    final_review_payload_json = json_dumps(final_review.get("payload") or {})
    reviewed_at = format_dt(now)
    snapshot_hash = candidate_snapshot_hash(result)
    snapshot_changed = bool(existing and existing.get("candidate_snapshot_hash") != snapshot_hash)
    user_review_status = (existing or {}).get("user_review_status") or "not_requested"
    user_review_reason = (existing or {}).get("user_review_reason")
    user_review_payload = (existing or {}).get("user_review_payload") or {}
    user_reviewed_at = (existing or {}).get("user_reviewed_at")
    recommendation_mode = normalize_recommendation_mode(subscription.get("recommendation_mode"))
    owner_profile_ref, target_profile_ref = recommendation_relation_refs(subscription, int(candidate_id))
    relation_key = recommendation_relation_key(subscription, int(candidate_id))
    owner_profile_ref_json = json_dumps(profile_ref_to_dict(owner_profile_ref))
    target_profile_ref_json = json_dumps(profile_ref_to_dict(target_profile_ref))
    rule_provenance_json = json_dumps(rule_provenance)

    if recommendation_mode == "direct_greet_only" and final_review["status"] == "direct_greet_ready":
        if snapshot_changed or user_review_status in {"not_requested", "pending_review"}:
            user_review_status = "pending_review"
            user_review_reason = "awaiting_real_user_review"
            user_review_payload = {}
            user_reviewed_at = None
    else:
        user_review_status = "not_requested"
        user_review_reason = None
        user_review_payload = {}
        user_reviewed_at = None
    user_review_payload_json = json_dumps(user_review_payload)

    if existing:
        conn.execute(
            """
            UPDATE profile_recommendations
            SET candidate_name = ?,
                score = ?,
                fit_score = ?,
                confidence_score = ?,
                risk_score = ?,
                delivery_status = ?,
                delivery_reason = ?,
                last_seen_at = ?,
                matched_on_json = ?,
                risk_flags_json = ?,
                latest_payload_json = ?,
                final_review_status = ?,
                final_review_reason = ?,
                final_review_score = ?,
                final_review_payload_json = ?,
                reviewed_at = ?,
                candidate_snapshot_hash = ?,
                user_review_status = ?,
                user_review_reason = ?,
                user_review_payload_json = ?,
                user_reviewed_at = ?,
                relation_key = ?,
                owner_profile_ref_json = ?,
                target_profile_ref_json = ?,
                rule_provenance_json = ?,
                gate_outcome = ?,
                gate_reason_codes_json = ?,
                gate_owner_service = ?,
                gate_details_ref = ?,
                gate_evaluated_at = ?
            WHERE recommendation_id = ?
            """,
            (
                result.get("name") or "未命名",
                int(result.get("score") or 0),
                int(result.get("fit_score") or 0),
                int(result.get("confidence_score") or 0),
                int(result.get("risk_score") or 0),
                delivery_status,
                delivery_reason,
                format_dt(now),
                matched_on_json,
                risk_flags_json,
                payload_json,
                final_review["status"],
                final_review["reason"],
                int(final_review.get("score") or 0),
                final_review_payload_json,
                reviewed_at,
                snapshot_hash,
                user_review_status,
                user_review_reason,
                user_review_payload_json,
                user_reviewed_at,
                relation_key,
                owner_profile_ref_json,
                target_profile_ref_json,
                rule_provenance_json,
                gate_fields["gate_outcome"],
                gate_fields["gate_reason_codes_json"],
                gate_fields["gate_owner_service"],
                gate_fields["gate_details_ref"],
                format_dt(gate_fields["gate_evaluated_at"]),
                existing["recommendation_id"],
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO profile_recommendations (
              subscription_id,
              requester_id,
              candidate_id,
              candidate_name,
              score,
              fit_score,
              confidence_score,
              risk_score,
              delivery_status,
              delivery_reason,
              first_seen_at,
              last_seen_at,
              matched_on_json,
              risk_flags_json,
              latest_payload_json,
              final_review_status,
              final_review_reason,
              final_review_score,
              final_review_payload_json,
              reviewed_at,
              candidate_snapshot_hash,
              user_review_status,
              user_review_reason,
              user_review_payload_json,
              user_reviewed_at,
              relation_key,
              owner_profile_ref_json,
              target_profile_ref_json,
              rule_provenance_json,
              gate_outcome,
              gate_reason_codes_json,
              gate_owner_service,
              gate_details_ref,
              gate_evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription["subscription_id"],
                subscription["requester_id"],
                int(candidate_id),
                result.get("name") or "未命名",
                int(result.get("score") or 0),
                int(result.get("fit_score") or 0),
                int(result.get("confidence_score") or 0),
                int(result.get("risk_score") or 0),
                delivery_status,
                delivery_reason,
                format_dt(now),
                format_dt(now),
                matched_on_json,
                risk_flags_json,
                payload_json,
                final_review["status"],
                final_review["reason"],
                int(final_review.get("score") or 0),
                final_review_payload_json,
                reviewed_at,
                snapshot_hash,
                user_review_status,
                user_review_reason,
                user_review_payload_json,
                user_reviewed_at,
                relation_key,
                owner_profile_ref_json,
                target_profile_ref_json,
                rule_provenance_json,
                gate_fields["gate_outcome"],
                gate_fields["gate_reason_codes_json"],
                gate_fields["gate_owner_service"],
                gate_fields["gate_details_ref"],
                format_dt(gate_fields["gate_evaluated_at"]),
            ),
        )
    rec_id = int(existing["recommendation_id"]) if existing else int(conn.lastrowid)
    row = conn.execute(
        "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
        (rec_id,),
    ).fetchone()
    rec_row = row_to_dict(row)
    if rec_row:
        append_relation_state_revision_event(conn, subscription=subscription, recommendation_row=rec_row, now=now)
    commit_recommendation_transaction(conn)
    out = get_recommendation(conn, subscription["subscription_id"], int(candidate_id))
    if out:
        rid = int(out["recommendation_id"])
        if delivery_status == "review_pending" and prev_delivery_status != "review_pending":
            funnel_stage(
                system="recommendation",
                stage=RECOMMENDATION_FUNNEL_REVIEW_PENDING,
                subscription_id=subscription["subscription_id"],
                recommendation_id=rid,
                candidate_id=int(candidate_id),
                delivery_reason=delivery_reason,
            )
        if delivery_status == "pending_delivery" and prev_delivery_status != "pending_delivery":
            funnel_stage(
                system="recommendation",
                stage=RECOMMENDATION_FUNNEL_PENDING_DELIVERY,
                subscription_id=subscription["subscription_id"],
                recommendation_id=rid,
                candidate_id=int(candidate_id),
                delivery_reason=delivery_reason,
            )

            # ✅ 新增：SSE推送通知用户（主动推荐）
            # 当系统生成推荐卡片后，立即通知用户
            _push_active_recommendation_notification(
                recommendation=out,
                subscription=subscription,
                now=now,
            )

    return out


def _push_active_recommendation_notification(
    recommendation: dict[str, Any] | None,
    subscription: dict[str, Any],
    now: datetime,
) -> None:
    """推送主动推荐通知给用户（通过SSE）。

    Args:
        recommendation: 推荐数据
        subscription: 订阅数据
        now: 当前时间
    """
    import httpx
    import logging
    from her_env import env_first

    logger = logging.getLogger(__name__)

    if not recommendation:
        return

    sse_server_url = env_first(
        "SSE_SERVER_URL",
        "http://localhost:8081",
    )

    # 获取用户的profile_id（订阅的requester_id）
    target_profile_id = subscription.get("requester_id")
    if not target_profile_id:
        return

    # 获取候选人的profile_id
    candidate_id = recommendation.get("candidate_id")

    try:
        push_url = f"{sse_server_url}/internal/push/recommendation"
        payload = {
            "profile_id": target_profile_id,  # 接收通知的用户
            "event_type": "active_recommendation",  # 主动推荐
            "recommendation_id": recommendation.get("recommendation_id"),
            "candidate_id": candidate_id,
            "subscription_id": subscription.get("subscription_id"),
            "message": "系统为你推荐了一位候选人",
            "timestamp": now.isoformat(),
        }

        # 异步推送（不阻塞主流程）
        with httpx.Client(timeout=2.0) as client:
            response = client.post(push_url, json=payload)
            if response.status_code == 200:
                logger.info(
                    f"[SSE Push] 主动推荐通知已推送: target={target_profile_id}, candidate={candidate_id}"
                )
            else:
                logger.warning(
                    f"[SSE Push] 推送失败: status={response.status_code}, target={target_profile_id}"
                )
    except Exception as e:
        # 推送失败不影响主流程，只记录日志
        logger.warning(
            f"[SSE Push] 推送异常: {e}, target={target_profile_id}"
        )


def record_recommendation_action(
    conn,
    *,
    subscription_id: str,
    candidate_id: int,
    action_type: str,
    actor_id: str | None = None,
    now: datetime | None = None,
    action_payload: dict[str, Any] | None = None,
    client_idempotency_key: str | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    subscription = get_subscription(conn, subscription_id)
    recommendation = get_recommendation(conn, subscription_id, int(candidate_id))
    if not recommendation:
        raise ValueError(f"Unknown recommendation for subscription={subscription_id} candidate_id={candidate_id}")

    ck = str(client_idempotency_key).strip() if client_idempotency_key else ""
    if ck:
        dup = conn.execute(
            """
            SELECT 1 AS o FROM recommendation_actions
            WHERE recommendation_id = ? AND client_idempotency_key = ?
            LIMIT 1
            """,
            (int(recommendation["recommendation_id"]), ck),
        ).fetchone()
        if dup:
            out = get_recommendation(conn, subscription_id, int(candidate_id))
            if isinstance(out, dict):
                out = {**out, "idempotent_replay": True}
            return out

    allowed_actions = {"skip", "save", "direct_greet"}
    if action_type not in allowed_actions:
        raise ValueError(f"Unsupported action_type: {action_type}")

    cooling_until = recommendation.get("cooling_until")
    new_status = recommendation["delivery_status"]
    if action_type == "skip":
        cooling_until = format_dt(now + timedelta(days=int(subscription.get("skip_cooldown_days") or 30)))
        new_status = "cooled_down"
    elif action_type == "save":
        cooling_until = None
        new_status = "saved_by_user"
    elif action_type == "direct_greet":
        cooling_until = None
        new_status = "direct_greet_started"

    _recommendation_action_insert(
        conn,
        subscription=subscription,
        recommendation=recommendation,
        action_type=action_type,
        actor_type="user",
        actor_id=actor_id,
        now=now,
        action_payload=action_payload,
        client_idempotency_key=ck or None,
    )
    conn.execute(
        """
        UPDATE profile_recommendations
        SET delivery_status = ?,
            delivery_reason = ?,
            last_action_type = ?,
            cooling_until = ?
        WHERE recommendation_id = ?
        """,
        (
            new_status,
            f"user_action_{action_type}",
            action_type,
            cooling_until,
            recommendation["recommendation_id"],
        ),
    )
    row = conn.execute(
        "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
        (recommendation["recommendation_id"],),
    ).fetchone()
    rec_row = row_to_dict(row)
    if rec_row:
        append_relation_state_revision_event(conn, subscription=subscription, recommendation_row=rec_row, now=now)
    commit_recommendation_transaction(conn)
    _record_appearance_feedback_from_recommendation(
        subscription=subscription,
        recommendation=recommendation,
        event_type=action_type,
        event_weight={"skip": -2.0, "save": 2.5, "direct_greet": 4.0}.get(action_type, 0.0),
        scene="recommendation_action",
    )
    out = get_recommendation(conn, subscription_id, int(candidate_id))
    funnel_stage(
        system="recommendation",
        stage=RECOMMENDATION_FUNNEL_ACTION,
        subscription_id=subscription_id,
        recommendation_id=int(recommendation["recommendation_id"]),
        candidate_id=int(candidate_id),
        action_type=action_type,
        trace_id=get_trace_id(),
    )
    return out


def record_user_review(
    conn,
    *,
    subscription_id: str,
    candidate_id: int,
    review_type: str,
    actor_id: str | None = None,
    now: datetime | None = None,
    review_payload: dict[str, Any] | None = None,
    client_idempotency_key: str | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    subscription = get_subscription(conn, subscription_id)
    recommendation = get_recommendation(conn, subscription_id, int(candidate_id))
    if not recommendation:
        raise ValueError(f"Unknown recommendation for subscription={subscription_id} candidate_id={candidate_id}")

    ck = str(client_idempotency_key).strip() if client_idempotency_key else ""
    if ck:
        dup = conn.execute(
            """
            SELECT 1 AS o FROM recommendation_actions
            WHERE recommendation_id = ? AND client_idempotency_key = ?
            LIMIT 1
            """,
            (int(recommendation["recommendation_id"]), ck),
        ).fetchone()
        if dup:
            out = get_recommendation(conn, subscription_id, int(candidate_id))
            if isinstance(out, dict):
                out = {**out, "idempotent_replay": True}
            return out

    if recommendation.get("notified_at"):
        raise ValueError("User review must happen before delivery.")
    if recommendation.get("final_review_status") != "direct_greet_ready":
        raise ValueError("User review is only valid after the rule gate passes direct_greet_ready.")

    allowed_reviews = {"skip", "save", "direct_greet"}
    if review_type not in allowed_reviews:
        raise ValueError(f"Unsupported review_type: {review_type}")

    if review_type == "direct_greet":
        user_review_status = "direct_greet"
        delivery_status = "pending_delivery"
        delivery_reason = "user_review_direct_greet"
    elif review_type == "save":
        user_review_status = "save"
        delivery_status = "saved_by_user"
        delivery_reason = "user_review_save"
    else:
        user_review_status = "skip"
        delivery_status = "cooled_down"
        delivery_reason = "user_review_skip"

    _recommendation_action_insert(
        conn,
        subscription=subscription,
        recommendation=recommendation,
        action_type=f"review_{review_type}",
        actor_type="user",
        actor_id=actor_id,
        now=now,
        action_payload=review_payload,
        client_idempotency_key=ck or None,
    )
    conn.execute(
        """
        UPDATE profile_recommendations
        SET user_review_status = ?,
            user_review_reason = ?,
            user_review_payload_json = ?,
            user_reviewed_at = ?,
            delivery_status = ?,
            delivery_reason = ?
        WHERE recommendation_id = ?
        """,
        (
            user_review_status,
            delivery_reason,
            json_dumps(review_payload or {}),
            format_dt(now),
            delivery_status,
            delivery_reason,
            recommendation["recommendation_id"],
        ),
    )
    row = conn.execute(
        "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
        (recommendation["recommendation_id"],),
    ).fetchone()
    rec_row = row_to_dict(row)
    if rec_row:
        append_relation_state_revision_event(conn, subscription=subscription, recommendation_row=rec_row, now=now)
    commit_recommendation_transaction(conn)
    _record_appearance_feedback_from_recommendation(
        subscription=subscription,
        recommendation=recommendation,
        event_type=f"review_{review_type}",
        event_weight={"skip": -2.5, "save": 2.5, "direct_greet": 4.0}.get(review_type, 0.0),
        scene="recommendation_review",
    )
    out = get_recommendation(conn, subscription_id, int(candidate_id))
    if review_type == "direct_greet":
        funnel_stage(
            system="recommendation",
            stage=RECOMMENDATION_FUNNEL_PENDING_DELIVERY,
            subscription_id=subscription_id,
            recommendation_id=int(recommendation["recommendation_id"]),
            candidate_id=int(candidate_id),
            source="user_review",
            delivery_reason=delivery_reason,
        )
    return out
