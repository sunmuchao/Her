"""Consume pending chat outbox rows: emit pipeline funnel + mark published."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from match_domain.trace_context import get_trace_id
from observability import CHAT_FUNNEL_OUTBOX_DISPATCHED, alert_signal, funnel_stage

from .assistant_sessions import (
    enqueue_agent_task,
    get_or_create_agent_session,
    is_public_followup_active,
    record_agent_session_user_activity,
)
from .outbox_admin import (
    claim_pending_outbox_batch,
    mark_claimed_outbox_rows_published,
    mark_outbox_row_retry_pending,
)

ASSISTANT_DM_CHANNEL_KEYS = {"assistant_dm_a", "assistant_dm_b"}


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def _maybe_enqueue_agent_task_from_event(conn, payload: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    event_type = str(payload.get("event_type") or "").strip()
    if event_type != "chat.conversation.message.created":
        return None
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        return None
    if str(event_payload.get("source") or "").strip() != "user":
        return None

    case_id = str(event_payload.get("case_id") or "").strip()
    conversation_id = str(event_payload.get("conversation_id") or "").strip()
    channel_key = str(event_payload.get("channel_key") or "").strip()
    author_id = str(payload.get("actor_id") or "").strip()
    message_id = int(event_payload.get("message_id") or 0)
    if not case_id or not conversation_id or not channel_key or not author_id or message_id <= 0:
        return None

    session = get_or_create_agent_session(
        conn,
        case_id=case_id,
        triggered_by_message_id=message_id,
        now=now,
    )
    if channel_key not in ASSISTANT_DM_CHANNEL_KEYS:
        if not is_public_followup_active(session):
            record_agent_session_user_activity(
                conn,
                str(session["session_id"]),
                trigger_message_id=message_id,
                now=now,
            )
            return None
        task = enqueue_agent_task(
            conn,
            session_id=str(session["session_id"]),
            case_id=case_id,
            trigger_conversation_id=conversation_id,
            trigger_message_id=message_id,
            trigger_author_id=author_id,
            trigger_channel_key=channel_key,
            now=now,
        )
        return {
            "session_id": session["session_id"],
            "task_id": task["task_id"],
        }
    task = enqueue_agent_task(
        conn,
        session_id=str(session["session_id"]),
        case_id=case_id,
        trigger_conversation_id=conversation_id,
        trigger_message_id=message_id,
        trigger_author_id=author_id,
        trigger_channel_key=channel_key,
        now=now,
    )
    return {
        "session_id": session["session_id"],
        "task_id": task["task_id"],
    }


def consume_chat_outbox_batch(
    conn,
    *,
    limit: int = 100,
    now=None,
    retry_delay_seconds: int = 60,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int | None = None,
    max_attempts: int = 3,
    claim_timeout_seconds: int = 300,
    worker_name: str | None = None,
) -> dict[str, Any]:
    claim_token = uuid.uuid4().hex
    resolved_worker_name = str(worker_name or "").strip() or "chat-outbox-worker"
    ids: list[int] = []
    ts = _ts(now)
    agent_tasks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    retry_scheduled = 0
    failed = 0
    claim_result = claim_pending_outbox_batch(
        conn,
        limit=limit,
        claim_token=claim_token,
        worker_name=resolved_worker_name,
        now=ts,
        claim_timeout_seconds=claim_timeout_seconds,
        stale_retry_delay_seconds=retry_delay_seconds,
        max_attempts=max_attempts,
    )
    rows = list(claim_result.get("rows") or [])
    stale_recovered = int(claim_result.get("stale_recovered") or 0)
    for r in rows:
        oid = int(r["outbox_id"])
        payload: dict[str, Any] = {}
        raw = r.get("canonical_event_json")
        if raw:
            try:
                payload = json.loads(str(raw))
            except json.JSONDecodeError:
                payload = {}
        event_type = payload.get("event_type") or r.get("event_type")
        case_id = None
        if isinstance(payload.get("payload"), dict):
            case_id = payload["payload"].get("case_id")
        funnel_stage(
            system="chat",
            stage=CHAT_FUNNEL_OUTBOX_DISPATCHED,
            trace_id=get_trace_id(),
            outbox_id=oid,
            event_type=event_type,
            aggregate_id=r.get("aggregate_id"),
            case_id=case_id,
            source_row_table=r.get("source_row_table"),
            source_row_id=r.get("source_row_id"),
        )
        try:
            task_info = _maybe_enqueue_agent_task_from_event(conn, payload, now=ts)
        except Exception as exc:
            retry_state = mark_outbox_row_retry_pending(
                conn,
                oid,
                error=str(exc),
                now=ts,
                retry_delay_seconds=retry_delay_seconds,
                retry_backoff_multiplier=retry_backoff_multiplier,
                retry_max_delay_seconds=retry_max_delay_seconds,
                max_attempts=max_attempts,
                processing_token=claim_token,
            )
            status = str(retry_state.get("status") or "")
            if status == "retry_pending":
                retry_scheduled += 1
            elif status == "failed":
                failed += 1
            alert_signal(
                "chat.outbox_dispatch_failed",
                str(exc),
                severity="warning",
                worker_name=resolved_worker_name,
                outbox_id=oid,
                event_type=event_type,
                error_type=type(exc).__name__,
                publish_attempts=int(retry_state.get("publish_attempts") or 0),
                next_retry_at=retry_state.get("next_retry_at"),
            )
            errors.append(
                {
                    "outbox_id": oid,
                    "error": str(exc),
                    "status": status,
                    "publish_attempts": int(retry_state.get("publish_attempts") or 0),
                    "retry_delay_seconds": int(retry_state.get("retry_delay_seconds") or 0),
                    "next_retry_at": retry_state.get("next_retry_at"),
                }
            )
            continue
        ids.append(oid)
        if task_info:
            agent_tasks.append(task_info)
    marked = mark_claimed_outbox_rows_published(conn, ids, now=ts, processing_token=claim_token)
    conn.commit()
    return {
        "worker_name": resolved_worker_name,
        "claimed": len(rows),
        "examined": len(rows),
        "marked_published": marked,
        "agent_tasks_enqueued": len(agent_tasks),
        "agent_task_refs": agent_tasks,
        "retry_scheduled": retry_scheduled,
        "failed": failed,
        "stale_recovered": stale_recovered,
        "errors": errors,
    }


__all__ = ["consume_chat_outbox_batch"]
