"""Phase 3 outer-system recommendation workflows built on top of partner-search."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from ._path_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain import (  # noqa: E402
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
)
from partner_search import load_self_profile, normalize_persona_profile, search_profiles  # noqa: E402
from her_time_utils import bool_to_int, current_time, format_dt, parse_dt  # noqa: E402

from .direct_greet_gate import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
    normalize_recommendation_mode,
    review_candidate_for_proactive_delivery,
)
from .criteria_compiler import build_effective_search_request
from .storage import json_dumps, json_loads, row_to_dict

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
run_partner_search = search_profiles

def generate_subscription_id() -> str:
    return f"saved-search-{uuid.uuid4().hex[:12]}"


def generate_card_id() -> str:
    return f"card-{uuid.uuid4().hex[:12]}"


def build_initial_request(
    *,
    source: str,
    criteria: dict[str, Any],
    self_profile: dict[str, Any] | None,
    self_id: int | None,
    table_name: str | None,
    photos_table_name: str | None,
    limit_count: int,
    photo_preview_count: int = 0,
) -> dict[str, Any]:
    return {
        "source": source,
        "criteria": dict(criteria or {}),
        "self_profile": dict(self_profile or {}) or None,
        "self_id": self_id,
        "table_name": table_name,
        "photos_table_name": photos_table_name,
        "limit": limit_count,
        "photo_preview_count": photo_preview_count,
        "include_source": True,
        "include_text": False,
    }


def normalize_subscription_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    return dict(overrides or {})


def load_requester_profile(
    *,
    source: str,
    self_id: int | None,
    table_name: str | None = None,
    self_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the latest requester profile row for persona-driven refreshes."""

    if self_id is None:
        return self_profile

    try:
        profile = load_self_profile(
            source=source,
            self_id=self_id,
            table_name=table_name,
        )
        return normalize_persona_profile(
            profile,
            fallback_profile=self_profile,
        )
    except Exception:
        return normalize_persona_profile(
            self_profile,
            fallback_profile=self_profile,
        )


def resolve_subscription_persona_profile(subscription: dict[str, Any]) -> dict[str, Any] | None:
    stored_profile = json_loads(subscription.get("self_profile_json"), None)
    if subscription.get("self_id") is None:
        return stored_profile
    return load_requester_profile(
        source=subscription["source"],
        self_id=int(subscription["self_id"]),
        table_name=subscription.get("table_name"),
        self_profile=stored_profile,
    )


def list_search_runs_for_subscription(conn, subscription_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM saved_search_runs
        WHERE subscription_id = ?
        ORDER BY created_at DESC, run_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    runs = []
    for row in rows:
        run = row_to_dict(row)
        run["persona_profile"] = json_loads(run.pop("persona_profile_json"), {})
        run["effective_criteria"] = json_loads(run.pop("effective_criteria_json"), {})
        run["search_request"] = json_loads(run.pop("search_request_json"), {})
        run["top_candidate_ids"] = json_loads(run.pop("top_candidate_ids_json"), [])
        run["status_counts"] = json_loads(run.pop("status_counts_json"), {})
        run["review_counts"] = json_loads(run.pop("review_counts_json"), {})
        run["rule_provenance"] = json_loads(run.pop("rule_provenance_json", None), {})
        runs.append(run)
    return runs


def record_search_run(
    conn,
    *,
    subscription: dict[str, Any],
    persona_profile: dict[str, Any] | None,
    search_request: dict[str, Any],
    effective_criteria: dict[str, Any],
    results: list[dict[str, Any]],
    status_counts: dict[str, int],
    review_counts: dict[str, int],
    now: datetime,
    rule_provenance: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO saved_search_runs (
          subscription_id,
          requester_id,
          source,
          table_name,
          photos_table_name,
          self_id,
          persona_profile_json,
          effective_criteria_json,
          search_request_json,
          result_count,
          top_candidate_ids_json,
          status_counts_json,
          review_counts_json,
          rule_provenance_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subscription["subscription_id"],
            subscription["requester_id"],
            subscription["source"],
            subscription.get("table_name"),
            subscription.get("photos_table_name"),
            subscription.get("self_id"),
            json_dumps(persona_profile or {}),
            json_dumps(effective_criteria),
            json_dumps(search_request),
            len(results),
            json_dumps([result.get("id") for result in results if result.get("id") is not None]),
            json_dumps(status_counts),
            json_dumps(review_counts),
            json_dumps(rule_provenance),
            format_dt(now),
        ),
    )


def update_subscription_overrides(
    conn,
    subscription_id: str,
    overrides: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    conn.execute(
        """
        UPDATE saved_search_subscriptions
        SET subscription_overrides_json = ?,
            updated_at = ?
        WHERE subscription_id = ?
        """,
        (
            json_dumps(normalize_subscription_overrides(overrides)),
            format_dt(now),
            subscription_id,
        ),
    )
    conn.commit()
    return get_subscription(conn, subscription_id)


def get_subscription(conn, subscription_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM saved_search_subscriptions WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    subscription = row_to_dict(row)
    if not subscription:
        raise ValueError(f"Unknown subscription: {subscription_id}")
    return subscription


def list_recommendations_for_subscription(conn, subscription_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM profile_recommendations
        WHERE subscription_id = ?
        ORDER BY score DESC, last_seen_at DESC, recommendation_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    return [inflate_recommendation(row_to_dict(row), conn=conn) for row in rows]


def list_in_app_cards(conn, requester_id: int | None = None, unread_only: bool = False) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if requester_id is not None:
        clauses.append("requester_id = ?")
        params.append(requester_id)
    if unread_only:
        clauses.append("card_status = 'unread'")
    where_clause = ""
    if clauses:
        where_clause = "WHERE " + " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT *
        FROM in_app_recommendation_cards
        {where_clause}
        ORDER BY delivered_at DESC, card_id DESC
        """,
        params,
    ).fetchall()
    cards = []
    for row in rows:
        card = row_to_dict(row)
        card["payload"] = json_loads(card.pop("payload_json"), {})
        cards.append(card)
    return cards


def mark_in_app_cards_read(
    conn,
    *,
    requester_id: int,
    card_ids: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Set ``card_status`` to ``read`` and ``read_at`` for the given cards owned by ``requester_id``."""

    now = current_time(now)
    ts = format_dt(now)
    updated = 0
    for raw in card_ids:
        cid = str(raw).strip()
        if not cid:
            continue
        res = conn.execute(
            """
            UPDATE in_app_recommendation_cards
            SET card_status = 'read', read_at = ?
            WHERE card_id = ? AND requester_id = ?
            """,
            (ts, cid, int(requester_id)),
        )
        updated += res.rowcount
    conn.commit()
    return {"updated_count": updated, "requester_id": int(requester_id)}


def create_subscription(
    conn,
    *,
    requester_id: int,
    source: str,
    criteria: dict[str, Any],
    subscription_overrides: dict[str, Any] | None = None,
    self_profile: dict[str, Any] | None = None,
    self_id: int | None = None,
    title: str | None = None,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    limit_count: int = 10,
    top_k: int = 5,
    min_notify_score: int = 40,
    daily_notification_cap: int = 2,
    quiet_hours_start: int = 22,
    quiet_hours_end: int = 9,
    refresh_interval_hours: int = 24,
    skip_cooldown_days: int = 30,
    recommendation_mode: str = DEFAULT_RECOMMENDATION_MODE,
    direct_greet_profile: dict[str, Any] | None = None,
    max_review_candidates_per_refresh: int = DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    min_direct_greet_score: int = DEFAULT_MIN_DIRECT_GREET_SCORE,
    auto_reject_on_follow_up_questions: bool = True,
    auto_reject_on_risk_flags: bool = True,
    status: str = "active",
    is_still_searching: bool = True,
    subscription_id: str | None = None,
    initial_request: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    created_at = format_dt(now)
    subscription_id = subscription_id or generate_subscription_id()
    title = title or f"持续留意 {requester_id}"
    initial_request = initial_request or build_initial_request(
        source=source,
        criteria=criteria,
        self_profile=self_profile,
        self_id=self_id,
        table_name=table_name,
        photos_table_name=photos_table_name,
        limit_count=limit_count,
    )
    conn.execute(
        """
        INSERT INTO saved_search_subscriptions (
          subscription_id,
          requester_id,
          title,
          status,
          is_still_searching,
          source,
          table_name,
          photos_table_name,
          search_criteria_json,
          initial_request_json,
          subscription_overrides_json,
          self_profile_json,
          self_id,
          limit_count,
          top_k,
          min_notify_score,
          daily_notification_cap,
          quiet_hours_start,
          quiet_hours_end,
          refresh_interval_hours,
          skip_cooldown_days,
          recommendation_mode,
          direct_greet_profile_json,
          max_review_candidates_per_refresh,
          min_direct_greet_score,
          auto_reject_on_follow_up_questions,
          auto_reject_on_risk_flags,
          last_result_count,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
          subscription_id,
          requester_id,
          title,
          status,
          bool_to_int(is_still_searching),
          source,
          table_name,
          photos_table_name,
          json_dumps(criteria),
          json_dumps(initial_request),
          json_dumps(normalize_subscription_overrides(subscription_overrides)),
          json_dumps(self_profile or {}),
          self_id,
          limit_count,
          top_k,
          min_notify_score,
          daily_notification_cap,
          quiet_hours_start,
          quiet_hours_end,
          refresh_interval_hours,
          skip_cooldown_days,
          normalize_recommendation_mode(recommendation_mode),
          json_dumps(direct_greet_profile or {}),
          max_review_candidates_per_refresh,
          min_direct_greet_score,
          bool_to_int(auto_reject_on_follow_up_questions),
          bool_to_int(auto_reject_on_risk_flags),
          created_at,
          created_at,
        ),
    )
    conn.commit()
    return get_subscription(conn, subscription_id)


def is_subscription_due(subscription: dict[str, Any], now: datetime) -> bool:
    if subscription["status"] != "active" or not subscription["is_still_searching"]:
        return False
    last_refreshed_at = parse_dt(subscription.get("last_refreshed_at"))
    if last_refreshed_at is None:
        return True
    interval = timedelta(hours=int(subscription.get("refresh_interval_hours") or 24))
    return now >= last_refreshed_at + interval


def list_due_subscriptions(conn, now: datetime | None = None, subscription_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    now = current_time(now)
    if subscription_ids:
        subscription_ids = list(subscription_ids)
        placeholders = ", ".join(["?"] * len(subscription_ids))
        rows = conn.execute(
            f"""
            SELECT *
            FROM saved_search_subscriptions
            WHERE subscription_id IN ({placeholders})
            ORDER BY requester_id ASC, subscription_id ASC
            """,
            subscription_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM saved_search_subscriptions
            ORDER BY requester_id ASC, subscription_id ASC
            """
        ).fetchall()
    return [subscription for subscription in (row_to_dict(row) for row in rows) if is_subscription_due(subscription, now)]


def load_subscription_search_args(
    subscription: dict[str, Any],
    *,
    persona_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = build_effective_search_request(subscription, persona_profile=persona_profile)
    request["include_source"] = True
    request["include_text"] = False
    request["moderation_dsn"] = os.environ.get("HER_CHAT_MODERATION_DB") or os.environ.get("PARTNER_CHAT_DB")
    return request


def candidate_snapshot_hash(result: dict[str, Any]) -> str:
    return hashlib.sha256(json_dumps(result).encode("utf-8")).hexdigest()


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
) -> dict[str, Any]:
    ledger_events = []
    rid = recommendation.get("recommendation_id")
    if conn is not None and rid is not None:
        rows = list_recommendation_actions_for_recommendation(conn, int(rid))
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
    return recommendation


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
) -> None:
    relation_key = recommendation.get("relation_key")
    if not relation_key:
        relation_key = recommendation_relation_key(subscription, int(recommendation["candidate_id"]))
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
            "last_action_type": recommendation_row.get("last_action_type"),
            "active_match_case_id": recommendation_row.get("active_match_case_id"),
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
            return ("proxy_intro_in_progress", "proxy_intro_case_active")
        delivery_status = existing.get("delivery_status")
        if delivery_status in {"proxy_intro_accepted", "proxy_intro_handed_off"}:
            return (delivery_status, existing.get("delivery_reason") or "proxy_intro_already_resolved")
        if delivery_status in {"proxy_intro_declined", "proxy_intro_timed_out"}:
            cooling_until = parse_dt(existing.get("cooling_until"))
            if cooling_until and now < cooling_until:
                return (delivery_status, existing.get("delivery_reason") or "proxy_intro_cooling_active")

    skip_cooldown_expired = False
    if existing and existing.get("last_action_type") == "save":
        return ("saved_by_user", "user_saved_candidate")
    if existing and existing.get("last_action_type") == "direct_greet":
        return ("direct_greeted", "user_started_direct_greet")
    if existing and existing.get("last_action_type") == "skip":
        cooling_until = parse_dt(existing.get("cooling_until"))
        if cooling_until and now < cooling_until:
            return ("cooled_down", "skip_cooldown_active")
        skip_cooldown_expired = True

    if int(result.get("score") or 0) < int(subscription.get("min_notify_score") or 0):
        return ("suppressed_low_score", "score_below_notify_threshold")

    if existing and existing.get("notified_at") and not skip_cooldown_expired:
        return ("already_delivered", "candidate_already_notified")

    recommendation_mode = normalize_recommendation_mode(subscription.get("recommendation_mode"))
    final_review_status = final_review["status"]
    if recommendation_mode == "direct_greet_only":
        if final_review_status == "review_deferred":
            return ("review_deferred", final_review["reason"])
        if final_review_status == "rejected":
            return ("rejected_by_gate", final_review["reason"])
        if final_review_status == "save_only":
            return ("save_only", final_review["reason"])
        if final_review_status == "direct_greet_ready":
            user_review_status = (existing or {}).get("user_review_status")
            if user_review_status == "direct_greet":
                return ("pending_delivery", "user_review_direct_greet")
            if user_review_status == "save":
                return ("save_only", "user_review_save")
            if user_review_status == "skip":
                return ("review_skipped", "user_review_skip")
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
    return _hydrate_recommendation_relation_metadata(inflated, conn=conn)


def get_recommendation(conn, subscription_id: str, candidate_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM profile_recommendations
        WHERE subscription_id = ? AND candidate_id = ?
        """,
        (subscription_id, candidate_id),
    ).fetchone()
    row_dict = row_to_dict(row)
    if not row_dict:
        return None
    return inflate_recommendation(row_dict, conn=conn)


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
    )
    prev_delivery_status = (existing or {}).get("delivery_status")
    delivery_status, delivery_reason = normalize_delivery_status(existing, result, subscription, now, final_review)
    payload_json = json_dumps(result)
    matched_on_json = json_dumps(result.get("matched_on") or [])
    risk_flags_json = json_dumps(result.get("risk_flags") or [])
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
                rule_provenance_json = ?
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
              rule_provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    conn.commit()
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
    return out


def _refresh_subscription_core(
    conn,
    subscription_id: str,
    *,
    now: datetime,
    search_runner: SearchRunner,
    persona_resolver: PersonaResolver,
) -> dict[str, Any]:
    subscription = get_subscription(conn, subscription_id)
    persona_profile = persona_resolver(subscription)
    search_request = load_subscription_search_args(subscription, persona_profile=persona_profile)
    rule_provenance = build_subscription_refresh_provenance(
        subscription_id=subscription_id,
        persona_profile=persona_profile,
        search_request=search_request,
    )
    response = search_runner(**search_request)
    results = list(response.get("results") or [])[: int(subscription.get("top_k") or 5)]

    status_counts: dict[str, int] = {}
    review_counts: dict[str, int] = {}
    for index, result in enumerate(results, start=1):
        recommendation = upsert_recommendation(
            conn,
            subscription,
            result,
            now,
            review_rank=index,
            rule_provenance=rule_provenance,
        )
        status = recommendation["delivery_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        review_status = recommendation["final_review_status"]
        review_counts[review_status] = review_counts.get(review_status, 0) + 1

    record_search_run(
        conn,
        subscription=subscription,
        persona_profile=persona_profile,
        search_request=search_request,
        effective_criteria=dict(search_request.get("criteria") or {}),
        results=results,
        status_counts=status_counts,
        review_counts=review_counts,
        now=now,
        rule_provenance=rule_provenance,
    )
    conn.execute(
        """
        UPDATE saved_search_subscriptions
        SET last_refreshed_at = ?, last_result_count = ?, updated_at = ?
        WHERE subscription_id = ?
        """,
        (
            format_dt(now),
            len(results),
            format_dt(now),
            subscription_id,
        ),
    )
    conn.commit()

    return {
        "subscription_id": subscription_id,
        "requester_id": subscription["requester_id"],
        "title": subscription["title"],
        "searched_at": format_dt(now),
        "result_count": len(results),
        "status_counts": status_counts,
        "review_counts": review_counts,
    }


def refresh_subscription(
    conn,
    subscription_id: str,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
    persona_resolver: PersonaResolver = resolve_subscription_persona_profile,
) -> dict[str, Any]:
    now = current_time(now)
    try:
        out = _refresh_subscription_core(
            conn,
            subscription_id,
            now=now,
            search_runner=search_runner,
            persona_resolver=persona_resolver,
        )
    except Exception as exc:
        alert_signal(
            "recommendation.refresh_failed",
            str(exc),
            severity="error",
            subscription_id=subscription_id,
            error_type=type(exc).__name__,
        )
        raise
    funnel_stage(
        system="recommendation",
        stage=RECOMMENDATION_FUNNEL_REFRESH,
        subscription_id=subscription_id,
        result_count=out["result_count"],
        status_counts=out.get("status_counts"),
    )
    metric_gauge("recommendation.refresh.result_count", out["result_count"], subscription_id=subscription_id)
    return out


def refresh_due_subscriptions(
    conn,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
    persona_resolver: PersonaResolver = resolve_subscription_persona_profile,
    subscription_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    due_subscriptions = list_due_subscriptions(conn, now=now, subscription_ids=subscription_ids)
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for subscription in due_subscriptions:
        sid = subscription["subscription_id"]
        try:
            out = _refresh_subscription_core(
                conn,
                sid,
                now=now,
                search_runner=search_runner,
                persona_resolver=persona_resolver,
            )
            summaries.append(out)
            funnel_stage(
                system="recommendation",
                stage=RECOMMENDATION_FUNNEL_REFRESH,
                subscription_id=sid,
                result_count=out["result_count"],
                status_counts=out.get("status_counts"),
            )
            metric_gauge("recommendation.refresh.result_count", out["result_count"], subscription_id=sid)
        except Exception as exc:
            errors.append(
                {"subscription_id": sid, "error": str(exc), "error_type": type(exc).__name__},
            )
            alert_signal(
                "recommendation.refresh_failed",
                str(exc),
                severity="error",
                subscription_id=sid,
                error_type=type(exc).__name__,
            )
    return {"summaries": summaries, "errors": errors}


def within_quiet_hours(now: datetime, quiet_hours_start: int, quiet_hours_end: int) -> bool:
    if quiet_hours_start == quiet_hours_end:
        return False
    if quiet_hours_start < quiet_hours_end:
        return quiet_hours_start <= now.hour < quiet_hours_end
    return now.hour >= quiet_hours_start or now.hour < quiet_hours_end


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def count_cards_delivered_today(conn, requester_id: int, now: datetime) -> int:
    day_start, day_end = day_bounds(now)
    row = conn.execute(
        """
        SELECT COUNT(*) AS delivered_count
        FROM in_app_recommendation_cards
        WHERE requester_id = ?
          AND delivered_at >= ?
          AND delivered_at < ?
        """,
        (requester_id, format_dt(day_start), format_dt(day_end)),
    ).fetchone()
    return int(row["delivered_count"]) if row else 0


def recommendation_verified_label(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    label = payload.get("verified_label")
    if label:
        return str(label)
    trust_summary = payload.get("trust_summary") or {}
    if isinstance(trust_summary, dict) and trust_summary.get("verified_label"):
        return str(trust_summary["verified_label"])
    level = str(profile.get("verified_level") or "").strip().lower()
    labels = {
        "basic": "基础认证",
        "photo": "照片认证",
        "id": "实名认证",
        "offline": "线下核验",
    }
    return labels.get(level)


def recommendation_photo_verification_label(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    label = payload.get("photo_verification_label")
    if label:
        return str(label)
    trust_summary = payload.get("trust_summary") or {}
    if isinstance(trust_summary, dict) and trust_summary.get("photo_verification_label"):
        return str(trust_summary["photo_verification_label"])
    level = str(payload.get("photo_verification_level") or trust_summary.get("photo_verification_level") or "").strip().lower()
    labels = {
        "uploaded": "普通上传照片",
        "human_verified": "真人照片认证",
        "live_video_verified": "活体自拍视频认证",
        "offline_verified": "线下核验照片",
    }
    return labels.get(level)


def recommendation_trust_headline(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    trust_summary = payload.get("trust_summary") or {}
    if isinstance(trust_summary, dict):
        headline = trust_summary.get("headline")
        if headline:
            return str(headline)
    elif trust_summary:
        return str(trust_summary)

    verified_label = recommendation_verified_label(payload, profile)
    if verified_label:
        return verified_label
    return None


def build_in_app_card(recommendation: dict[str, Any], subscription_title: str) -> dict[str, Any]:
    payload = recommendation.get("latest_payload") or {}
    profile = payload.get("profile") or {}
    matched_on = payload.get("matched_on") or []
    risk_flags = payload.get("risk_flags") or []
    follow_up_questions = payload.get("follow_up_questions") or []
    caution_items = payload.get("caution_items") or []
    trust_actions = payload.get("trust_actions") or []
    trust_headline = recommendation_trust_headline(payload, profile)
    verified_label = recommendation_verified_label(payload, profile)
    photo_label = recommendation_photo_verification_label(payload, profile)

    title = f"发现新的合适对象：{payload.get('name') or recommendation.get('candidate_name')}"
    subtitle_parts = [
        subscription_title,
        f"score={payload.get('score', recommendation.get('score', 0))}",
        f"{profile.get('age', '未知')}岁",
        profile.get("city") or "城市未知",
    ]
    if profile.get("job"):
        subtitle_parts.append(profile.get("job"))
    if photo_label:
        subtitle_parts.append(photo_label)
    if verified_label:
        subtitle_parts.append(verified_label)

    body_lines = []
    if trust_headline:
        body_lines.append("可信度：" + trust_headline)
    if caution_items:
        body_lines.append("谨慎点：" + "；".join(str(item) for item in caution_items[:2]))
    if matched_on:
        body_lines.append("匹配点：" + "；".join(matched_on[:3]))
    if risk_flags:
        body_lines.append("风险点：" + "；".join(risk_flags[:2]))
    if follow_up_questions:
        body_lines.append("建议确认：" + "；".join(follow_up_questions[:2]))
    if trust_actions:
        body_lines.append("建议先做：" + "；".join(str(item) for item in trust_actions[:2]))
    if not body_lines:
        body_lines.append("命中了订阅条件，建议进入资料页继续确认。")

    return {
        "card_type": "partner_recommendation",
        "title": title,
        "subtitle": " | ".join(str(part) for part in subtitle_parts if part),
        "body": "\n".join(body_lines),
        "cta_actions": [
            {"id": "save", "label": "先收藏"},
            {"id": "skip", "label": "先跳过"},
            {"id": "direct_greet", "label": "直接打招呼"},
            {"id": "request_proxy_intro", "label": "替我去问"},
        ],
        "result_snapshot": payload,
        "rule_provenance": recommendation.get("rule_provenance") or {},
    }


def deliver_in_app_recommendations(conn, *, now: datetime | None = None) -> dict[str, Any]:
    now = current_time(now)
    rows = conn.execute(
        """
        SELECT
          r.*,
          s.title AS subscription_title,
          s.daily_notification_cap,
          s.quiet_hours_start,
          s.quiet_hours_end
        FROM profile_recommendations AS r
        JOIN saved_search_subscriptions AS s
          ON s.subscription_id = r.subscription_id
        WHERE r.delivery_status = 'pending_delivery'
          AND s.status = 'active'
          AND s.is_still_searching = 1
        ORDER BY r.requester_id ASC, r.score DESC, r.first_seen_at ASC
        """
    ).fetchall()

    delivered_count = 0
    held_quiet_hours = 0
    held_daily_cap = 0
    delivered_today_cache: dict[int, int] = {}
    subscription_cache: dict[str, dict[str, Any]] = {}

    for raw_row in rows:
        recommendation = inflate_recommendation(row_to_dict(raw_row), conn=conn)
        requester_id = int(recommendation["requester_id"])
        if within_quiet_hours(
            now,
            int(recommendation["quiet_hours_start"]),
            int(recommendation["quiet_hours_end"]),
        ):
            held_quiet_hours += 1
            continue

        delivered_today = delivered_today_cache.get(requester_id)
        if delivered_today is None:
            delivered_today = count_cards_delivered_today(conn, requester_id, now)
        if delivered_today >= int(recommendation["daily_notification_cap"]):
            held_daily_cap += 1
            delivered_today_cache[requester_id] = delivered_today
            continue

        card = build_in_app_card(recommendation, recommendation["subscription_title"])
        card_id = generate_card_id()
        conn.execute(
            """
            INSERT INTO in_app_recommendation_cards (
              card_id,
              subscription_id,
              recommendation_id,
              requester_id,
              candidate_id,
              card_status,
              title,
              subtitle,
              body,
              payload_json,
              created_at,
              delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                recommendation["subscription_id"],
                recommendation["recommendation_id"],
                requester_id,
                recommendation["candidate_id"],
                "unread",
                card["title"],
                card["subtitle"],
                card["body"],
                json_dumps(card),
                format_dt(now),
                format_dt(now),
            ),
        )
        conn.execute(
            """
            UPDATE profile_recommendations
            SET delivery_status = 'delivered',
                delivery_reason = 'in_app_card_created',
                notified_at = ?,
                latest_card_id = ?
            WHERE recommendation_id = ?
            """,
            (format_dt(now), card_id, recommendation["recommendation_id"]),
        )
        sid = recommendation["subscription_id"]
        if sid not in subscription_cache:
            subscription_cache[sid] = get_subscription(conn, sid)
        row = conn.execute(
            "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
            (recommendation["recommendation_id"],),
        ).fetchone()
        rec_row = row_to_dict(row)
        if rec_row:
            append_relation_state_revision_event(
                conn,
                subscription=subscription_cache[sid],
                recommendation_row=rec_row,
                now=now,
            )
        delivered_today_cache[requester_id] = delivered_today + 1
        delivered_count += 1
        funnel_stage(
            system="recommendation",
            stage=RECOMMENDATION_FUNNEL_DELIVERED,
            subscription_id=recommendation["subscription_id"],
            recommendation_id=int(recommendation["recommendation_id"]),
            candidate_id=int(recommendation["candidate_id"]),
            card_id=card_id,
        )

    conn.commit()
    metric_gauge("recommendation.deliver.delivered_count", delivered_count)
    metric_gauge("recommendation.deliver.held_quiet_hours", held_quiet_hours)
    metric_gauge("recommendation.deliver.held_daily_cap", held_daily_cap)
    return {
        "delivered_count": delivered_count,
        "held_quiet_hours": held_quiet_hours,
        "held_daily_cap": held_daily_cap,
    }


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
        new_status = "direct_greeted"

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
    conn.commit()
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
        delivery_status = "save_only"
        delivery_reason = "user_review_save"
    else:
        user_review_status = "skip"
        delivery_status = "review_skipped"
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
    conn.commit()
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
