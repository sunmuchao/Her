"""Saved-search subscriptions, search runs, and refresh scheduling."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

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
from partner_search import search_profiles  # noqa: E402
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
from .recommendation_search import run_partner_search

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


def load_requester_profile_row(
    *,
    source: str,
    self_id: int | None,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    if self_id is None:
        return None
    try:
        from . import service

        return service.load_self_profile(
            source=source,
            self_id=self_id,
            table_name=table_name,
        )
    except Exception:
        return None


def resolve_subscription_compile_inputs(
    subscription: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    profile_row = load_requester_profile_row(
        source=subscription["source"],
        self_id=int(subscription["self_id"]) if subscription.get("self_id") is not None else None,
        table_name=subscription.get("table_name"),
    )
    persona_row = None
    requester_id = subscription.get("requester_id")
    if requester_id is not None:
        try:
            from match_domain.persona_loader import load_persona_row

            persona_row = load_persona_row(
                source=subscription["source"],
                user_key=str(requester_id),
            )
        except Exception:
            persona_row = None
    if persona_row is None:
        stored_profile = json_loads(subscription.get("self_profile_json"), None)
        if isinstance(stored_profile, dict):
            persona_row = stored_profile
    return profile_row, persona_row


def resolve_subscription_persona_profile(subscription: dict[str, Any]) -> dict[str, Any] | None:
    """Backward-compatible persona dict for audit payloads (collected fields only)."""

    profile_row, persona_row = resolve_subscription_compile_inputs(subscription)
    from match_domain.collected_profile import merge_collected_for_compile

    base = dict(persona_row or json_loads(subscription.get("self_profile_json"), None) or {})
    collected = merge_collected_for_compile(profile_row=profile_row, persona_row=persona_row)
    if collected or base:
        return {**base, **collected}
    return None


def load_requester_profile(
    *,
    source: str,
    self_id: int | None,
    table_name: str | None = None,
    self_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Deprecated: use load_requester_profile_row + load_persona_row for compile."""

    profile_row = load_requester_profile_row(
        source=source,
        self_id=self_id,
        table_name=table_name,
    )
    if profile_row is None:
        return self_profile

    from match_domain.collected_profile import extract_collected_statements
    from match_domain.reciprocal_preferences import enrich_record_for_reciprocal

    enriched = enrich_record_for_reciprocal(profile_row)
    merged = {**enriched, **extract_collected_statements(enriched)}
    for nested_key in ("matcher_preferences", "matcher_risks"):
        nested = enriched.get(nested_key)
        if isinstance(nested, dict):
            for key, value in nested.items():
                if key in merged or value in (None, "", [], {}):
                    continue
                merged[key] = value
    last_active_at = merged.get("last_active_at")
    if isinstance(last_active_at, datetime):
        merged["last_active_at"] = format_dt(last_active_at)
    return merged


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
        run["recommendation_status_counts"] = dict(run["status_counts"])
        run["review_status_counts"] = dict(run["review_counts"])
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
    commit_recommendation_transaction(conn)
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


def list_subscriptions_by_ids(conn, subscription_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item).strip() for item in subscription_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM saved_search_subscriptions
        WHERE subscription_id IN ({placeholders})
        """,
        tuple(normalized),
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        subscription = row_to_dict(row)
        subscription_id = str(subscription.get("subscription_id") or "").strip()
        if subscription_id:
            grouped[subscription_id] = subscription
    return grouped


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
    commit_recommendation_transaction(conn)
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
    profile_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile_row is None or persona_profile is None:
        resolved_profile, resolved_persona = resolve_subscription_compile_inputs(subscription)
        profile_row = profile_row if profile_row is not None else resolved_profile
        persona_profile = persona_profile if persona_profile is not None else resolved_persona
    request = build_effective_search_request(
        subscription,
        persona_profile=persona_profile,
        profile_row=profile_row,
    )
    request["include_source"] = True
    request["include_text"] = False
    request["moderation_dsn"] = os.environ.get("HER_CHAT_MODERATION_DB") or os.environ.get("PARTNER_CHAT_DB")
    return request


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
    compiled = dict(search_request.get("compiled") or {})
    from match_domain.experiment_bucket import resolve_experiment_bucket_for_subscription

    experiment_bucket = resolve_experiment_bucket_for_subscription(subscription, conn=conn)
    rule_provenance = build_subscription_refresh_provenance(
        subscription_id=subscription_id,
        persona_profile=persona_profile,
        search_request=search_request,
        subscription=subscription,
        conn=conn,
        experiment_bucket=experiment_bucket,
    )
    if compiled.get("source_map"):
        rule_provenance = {
            **rule_provenance,
            "source_map": compiled.get("source_map"),
            "criteria_hash": compiled.get("criteria_hash"),
        }
    from match_domain.experiment_bucket import profile_id_from_subscription
    from match_domain.search_rule_context import search_rule_context

    search_payload = {
        key: value
        for key, value in search_request.items()
        if key not in {"rule_resolution", "compiled"}
    }
    with search_rule_context(
        experiment_bucket=experiment_bucket,
        profile_id=profile_id_from_subscription(subscription),
        conn=conn,
    ):
        response = search_runner(**search_payload)
    results = list(response.get("results") or [])[: int(subscription.get("top_k") or 5)]

    status_counts: dict[str, int] = {}
    review_counts: dict[str, int] = {}
    first_recommendation_id: int | None = None
    for index, result in enumerate(results, start=1):
        from .recommendation_rows import upsert_recommendation

        recommendation = upsert_recommendation(
            conn,
            subscription,
            result,
            now,
            review_rank=index,
            rule_provenance=rule_provenance,
        )
        if index == 1:
            first_recommendation_id = int(recommendation["recommendation_id"])
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
    if compiled:
        try:
            from match_domain.criteria_snapshots import save_compiled_snapshot

            save_compiled_snapshot(
                compiled,
                scene="recommendation_refresh",
                profile_id=int(subscription.get("self_id") or 0) or None,
                requester_id=int(subscription.get("requester_id") or 0) or None,
                subscription_id=str(subscription.get("subscription_id") or ""),
                recommendation_id=first_recommendation_id,
            )
        except Exception:  # noqa: BLE001
            pass
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
    commit_recommendation_transaction(conn)

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
    max_workers: int | None = None,
) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from her_env import env_int
    from her_parallel_db import worker_connect_factory

    from .storage import connect_db

    now = current_time(now)
    due_subscriptions = list_due_subscriptions(conn, now=now, subscription_ids=subscription_ids)
    if not due_subscriptions:
        return {"summaries": [], "errors": []}

    worker_count = (
        int(max_workers)
        if max_workers is not None
        else env_int("RECOMMENDATION_REFRESH_MAX_WORKERS", 1)
    )
    worker_count = max(1, worker_count)
    connect_worker = worker_connect_factory(conn, connect_db)

    def _refresh_one(subscription: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        sid = str(subscription["subscription_id"])
        worker_conn = connect_worker()
        try:
            out = _refresh_subscription_core(
                worker_conn,
                sid,
                now=now,
                search_runner=search_runner,
                persona_resolver=persona_resolver,
            )
            return out, None
        except Exception as exc:
            return None, {
                "subscription_id": sid,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        finally:
            worker_conn.close()

    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if worker_count <= 1 or len(due_subscriptions) <= 1:
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

    results_by_subscription_id: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
    with ThreadPoolExecutor(max_workers=min(worker_count, len(due_subscriptions))) as executor:
        future_to_subscription = {
            executor.submit(_refresh_one, subscription): subscription
            for subscription in due_subscriptions
        }
        for future in as_completed(future_to_subscription):
            subscription = future_to_subscription[future]
            sid = str(subscription["subscription_id"])
            try:
                out, error = future.result()
                results_by_subscription_id[sid] = (out, error)
            except Exception as exc:
                results_by_subscription_id[sid] = (
                    None,
                    {
                        "subscription_id": sid,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

    for subscription in due_subscriptions:
        sid = str(subscription["subscription_id"])
        out, error = results_by_subscription_id.get(sid, (None, None))
        if error is not None:
            errors.append(error)
            alert_signal(
                "recommendation.refresh_failed",
                str(error["error"]),
                severity="error",
                subscription_id=sid,
                error_type=error.get("error_type"),
            )
            continue
        if out is None:
            continue
        summaries.append(out)
        funnel_stage(
            system="recommendation",
            stage=RECOMMENDATION_FUNNEL_REFRESH,
            subscription_id=sid,
            result_count=out["result_count"],
            status_counts=out.get("status_counts"),
        )
        metric_gauge("recommendation.refresh.result_count", out["result_count"], subscription_id=sid)
    return {"summaries": summaries, "errors": errors}


# Avoid circular import: refresh calls upsert after rows module loads.
