"""Structured pipeline logs: funnels, metrics, and alert signals (JSON lines on logger her.pipeline)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger("her.pipeline")


def _base_fields() -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "her_schema": "1",
    }


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
CHAT_FUNNEL_ASSISTANT_INVOKE = "assistant_invoke"
CHAT_FUNNEL_DRAFT_ADOPT = "draft_adopt"
CHAT_FUNNEL_PERSONA_JOB_ENQUEUED = "persona_job_enqueued"
CHAT_FUNNEL_OUTBOX_DISPATCHED = "outbox_dispatched"
