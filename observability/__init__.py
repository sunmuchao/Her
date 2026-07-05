"""Structured pipeline logs: funnels, metrics, and alert signals (JSON lines on logger her.pipeline)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from her_runtime_context import get_actor_context, get_trace_id, normalize_actor_roles

_LOGGER = logging.getLogger("her.pipeline")


def _base_fields() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "her_schema": "1",
    }
    trace_id = get_trace_id()
    if trace_id:
        payload["trace_id"] = trace_id
    actor = get_actor_context()
    if actor is not None:
        payload["actor_id"] = actor.actor_id
        payload["actor_roles"] = list(actor.actor_roles)
        if actor.auth_source:
            payload["actor_auth_source"] = actor.auth_source
        if actor.token_id:
            payload["actor_token_id"] = actor.token_id
        if actor.reason:
            payload["actor_reason"] = actor.reason
    return payload


def emit_pipeline_record(**fields: Any) -> None:
    """Emit one JSON object per log line for Loki/ELK-style ingestion."""
    payload = {**_base_fields(), **fields}
    text = json.dumps(payload, ensure_ascii=False, default=str)
    level_name = (os.environ.get("HER_PIPELINE_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    _LOGGER.log(level, text)


def funnel_stage(
    *,
    system: str,
    stage: str,
    **extra: Any,
) -> None:
    """Funnel step: system=recommendation|matchmaking|chat, stage=canonical step name."""
    emit_pipeline_record(her_kind="funnel", funnel_system=system, funnel_stage=stage, **extra)


def metric_gauge(name: str, value: int | float, **tags: Any) -> None:
    emit_pipeline_record(her_kind="metric", metric=name, value=value, **tags)


def alert_signal(
    alert_id: str,
    message: str,
    *,
    severity: str = "warning",
    **context: Any,
) -> None:
    emit_pipeline_record(
        her_kind="alert",
        alert_id=alert_id,
        alert_severity=severity,
        alert_message=message,
        **context,
    )


def audit_event(
    *,
    action: str,
    resource_type: str,
    outcome: str,
    resource_id: str | int | None = None,
    reason: str | None = None,
    actor_id: str | None = None,
    actor_roles: str | list[str] | tuple[str, ...] | None = None,
    impersonated_owner_id: str | int | None = None,
    **context: Any,
) -> None:
    payload: dict[str, Any] = {
        "her_kind": "audit",
        "audit_action": action,
        "resource_type": resource_type,
        "outcome": outcome,
        **context,
    }
    if resource_id is not None:
        payload["resource_id"] = str(resource_id)
    if reason:
        payload["reason"] = reason
    if actor_id:
        payload["actor_id"] = str(actor_id)
    if actor_roles is not None:
        payload["actor_roles"] = list(normalize_actor_roles(actor_roles))
    if impersonated_owner_id is not None:
        payload["impersonated_owner_id"] = str(impersonated_owner_id)
    emit_pipeline_record(**payload)


# --- Recommendation funnel (canonical stages) ---
RECOMMENDATION_FUNNEL_REFRESH = "refresh"
RECOMMENDATION_FUNNEL_REVIEW_PENDING = "review_pending"
RECOMMENDATION_FUNNEL_PENDING_DELIVERY = "pending_delivery"
RECOMMENDATION_FUNNEL_DELIVERED = "delivered"
RECOMMENDATION_FUNNEL_ACTION = "action"
RECOMMENDATION_FUNNEL_PROXY_INTRO = "proxy_intro"

# --- Matchmaking funnel ---
MATCHMAKING_FUNNEL_MEMBER = "member"
MATCHMAKING_FUNNEL_EDGE = "edge"
MATCHMAKING_FUNNEL_PAIR = "pair"
MATCHMAKING_FUNNEL_CASE = "case"
MATCHMAKING_FUNNEL_FIRST_ACCEPT = "first_accept"
MATCHMAKING_FUNNEL_SECOND_ACCEPT = "second_accept"
MATCHMAKING_FUNNEL_MUTUAL_ACCEPT = "mutual_accept"

# --- Chat funnel ---
CHAT_FUNNEL_THREAD_OPEN = "thread_open"
CHAT_FUNNEL_MESSAGE_SEND = "message_send"
CHAT_FUNNEL_PERSONA_JOB_ENQUEUED = "persona_job_enqueued"
CHAT_FUNNEL_OUTBOX_DISPATCHED = "outbox_dispatched"

from .photo_search_metrics import (  # noqa: E402
    PHOTO_SEARCH_BUCKETS,
    compare_photo_search_bucket_effect,
    emit_photo_search_event,
    resolve_photo_search_experiment_bucket,
    summarize_photo_search_events,
)

__all__ = [
    "CHAT_FUNNEL_MESSAGE_SEND",
    "CHAT_FUNNEL_OUTBOX_DISPATCHED",
    "CHAT_FUNNEL_PERSONA_JOB_ENQUEUED",
    "CHAT_FUNNEL_THREAD_OPEN",
    "MATCHMAKING_FUNNEL_CASE",
    "MATCHMAKING_FUNNEL_EDGE",
    "MATCHMAKING_FUNNEL_FIRST_ACCEPT",
    "MATCHMAKING_FUNNEL_MEMBER",
    "MATCHMAKING_FUNNEL_MUTUAL_ACCEPT",
    "MATCHMAKING_FUNNEL_PAIR",
    "MATCHMAKING_FUNNEL_SECOND_ACCEPT",
    "PHOTO_SEARCH_BUCKETS",
    "RECOMMENDATION_FUNNEL_ACTION",
    "RECOMMENDATION_FUNNEL_DELIVERED",
    "RECOMMENDATION_FUNNEL_PENDING_DELIVERY",
    "RECOMMENDATION_FUNNEL_PROXY_INTRO",
    "RECOMMENDATION_FUNNEL_REFRESH",
    "RECOMMENDATION_FUNNEL_REVIEW_PENDING",
    "alert_signal",
    "audit_event",
    "compare_photo_search_bucket_effect",
    "emit_photo_search_event",
    "emit_pipeline_record",
    "funnel_stage",
    "metric_gauge",
    "resolve_photo_search_experiment_bucket",
    "summarize_photo_search_events",
]
