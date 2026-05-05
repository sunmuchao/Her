"""Match-domain shaped events for chat outbox rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from match_domain.ids import entity_id_case, format_correlation_id
from match_domain.model import MatchEvent
from match_domain.trace_context import get_trace_id


def chat_message_created_event(
    *,
    thread_id: str,
    case_id: str,
    message_id: int,
    author_id: str,
    body: str,
    visibility: str,
    source: str,
    occurred_at: datetime,
) -> MatchEvent:
    actor_type = "agent" if author_id == "assistant" else "user"
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="chat.message.created",
        aggregate_type="chat_thread",
        aggregate_id=thread_id,
        actor_type=actor_type,
        actor_id=author_id,
        source_service="chat_system",
        correlation_id=format_correlation_id(get_trace_id(), entity_id_case(case_id)),
        occurred_at=occurred_at,
        payload={
            "thread_id": thread_id,
            "case_id": case_id,
            "message_id": message_id,
            "visibility": visibility,
            "source": source,
            "body_preview": (body or "")[:512],
        },
        trace_id=get_trace_id(),
    )


def chat_thread_opened_event(
    *,
    thread_id: str,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    occurred_at: datetime,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="chat.thread.opened",
        aggregate_type="chat_thread",
        aggregate_id=thread_id,
        actor_type="system",
        actor_id="chat_system",
        source_service="chat_system",
        correlation_id=format_correlation_id(get_trace_id(), entity_id_case(case_id)),
        occurred_at=occurred_at,
        payload={
            "thread_id": thread_id,
            "case_id": case_id,
            "relation_key": relation_key,
            "participant_a_id": participant_a_id,
            "participant_b_id": participant_b_id,
        },
        trace_id=get_trace_id(),
    )


__all__ = ["chat_message_created_event", "chat_thread_opened_event"]
