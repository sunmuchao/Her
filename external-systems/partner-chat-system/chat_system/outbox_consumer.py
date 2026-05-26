"""Consume pending chat outbox rows: emit pipeline funnel + mark published."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from match_domain.outbox_runtime import consume_outbox_batch

from .assistant_sessions import (
    enqueue_agent_task,
    get_or_create_agent_session,
    is_public_followup_active,
    record_agent_session_user_activity,
)

ASSISTANT_DM_CHANNEL_KEYS = {"assistant_dm_a", "assistant_dm_b"}


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


def chat_outbox_event_handler(
    conn,
    payload: dict[str, Any],
    row: dict[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    del row
    return _maybe_enqueue_agent_task_from_event(conn, payload, now=now)


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
    batch = consume_outbox_batch(
        conn,
        system="chat",
        limit=limit,
        now=now,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
        max_attempts=max_attempts,
        claim_timeout_seconds=claim_timeout_seconds,
        worker_name=worker_name,
        handler=chat_outbox_event_handler,
    )
    refs = list(batch.get("handler_results") or [])
    batch["agent_tasks_enqueued"] = len([item for item in refs if item])
    batch["agent_task_refs"] = refs
    return batch


__all__ = ["chat_outbox_event_handler", "consume_chat_outbox_batch"]
