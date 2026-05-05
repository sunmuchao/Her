"""Match-domain shaped events for chat outbox rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from match_domain.ids import correlation_member_feedback, entity_id_case, format_correlation_id
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

def chat_member_report_submitted_event(
    *,
    thread_id: str,
    case_id: str,
    report_id: int,
    reporter_id: str,
    reported_user_id: str,
    report_type: str,
    severity: str,
    signal_codes: list[str],
    risk_case_id: str,
    occurred_at: datetime,
) -> MatchEvent:
    actor_type = "system" if reporter_id == "system" else "user"
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="member.report.submitted",
        aggregate_type="chat_thread",
        aggregate_id=thread_id,
        actor_type=actor_type,
        actor_id=reporter_id,
        source_service="chat_system",
        correlation_id=correlation_member_feedback(str(report_id), trace_id=get_trace_id()),
        occurred_at=occurred_at,
        payload={
            "thread_id": thread_id,
            "case_id": case_id,
            "report_id": report_id,
            "reported_user_id": reported_user_id,
            "report_type": report_type,
            "severity": severity,
            "signal_codes": list(signal_codes),
            "risk_case_id": risk_case_id,
        },
        trace_id=get_trace_id(),
    )


def chat_risk_case_event(
    *,
    event_type: str,
    risk_case_id: str,
    case_id: str,
    thread_id: str,
    subject_user_id: str,
    severity: str,
    recommended_action: str,
    report_count: int,
    occurred_at: datetime,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type=event_type,
        aggregate_type="risk_case",
        aggregate_id=risk_case_id,
        actor_type="system",
        actor_id="chat_system",
        source_service="chat_system",
        correlation_id=format_correlation_id(get_trace_id(), entity_id_case(case_id), risk_case_id),
        occurred_at=occurred_at,
        payload={
            "risk_case_id": risk_case_id,
            "thread_id": thread_id,
            "case_id": case_id,
            "subject_user_id": subject_user_id,
            "severity": severity,
            "recommended_action": recommended_action,
            "report_count": report_count,
        },
        trace_id=get_trace_id(),
    )


def chat_risk_case_reviewed_event(
    *,
    risk_case_id: str,
    case_id: str,
    thread_id: str,
    resolver_id: str,
    status: str,
    applied_action: str | None,
    occurred_at: datetime,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="risk.case.reviewed",
        aggregate_type="risk_case",
        aggregate_id=risk_case_id,
        actor_type="user",
        actor_id=resolver_id,
        source_service="chat_system",
        correlation_id=format_correlation_id(get_trace_id(), entity_id_case(case_id), risk_case_id, "review"),
        occurred_at=occurred_at,
        payload={
            "risk_case_id": risk_case_id,
            "thread_id": thread_id,
            "case_id": case_id,
            "status": status,
            "applied_action": applied_action,
        },
        trace_id=get_trace_id(),
    )


def chat_risk_signal_detected_event(
    *,
    signal_id: int,
    thread_id: str,
    case_id: str,
    subject_user_id: str,
    signal_code: str,
    severity: str,
    source_type: str,
    occurred_at: datetime,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="risk.signal.detected",
        aggregate_type="risk_signal",
        aggregate_id=str(signal_id),
        actor_type="system",
        actor_id="chat_system",
        source_service="chat_system",
        correlation_id=format_correlation_id(get_trace_id(), entity_id_case(case_id), str(signal_id)),
        occurred_at=occurred_at,
        payload={
            "signal_id": int(signal_id),
            "thread_id": thread_id,
            "case_id": case_id,
            "subject_user_id": subject_user_id,
            "signal_code": signal_code,
            "severity": severity,
            "source_type": source_type,
        },
        trace_id=get_trace_id(),
    )


def chat_meeting_feedback_submitted_event(
    *,
    feedback_id: int,
    thread_id: str,
    case_id: str,
    reviewer_id: str,
    counterpart_user_id: str,
    derived_report_ids: list[int],
    occurred_at: datetime,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type="member.meeting_feedback.submitted",
        aggregate_type="chat_thread",
        aggregate_id=thread_id,
        actor_type="user",
        actor_id=reviewer_id,
        source_service="chat_system",
        correlation_id=correlation_member_feedback(str(feedback_id), trace_id=get_trace_id()),
        occurred_at=occurred_at,
        payload={
            "feedback_id": int(feedback_id),
            "thread_id": thread_id,
            "case_id": case_id,
            "counterpart_user_id": counterpart_user_id,
            "derived_report_ids": [int(item) for item in derived_report_ids],
        },
        trace_id=get_trace_id(),
    )


__all__ = [
    "chat_member_report_submitted_event",
    "chat_meeting_feedback_submitted_event",
    "chat_message_created_event",
    "chat_risk_case_event",
    "chat_risk_case_reviewed_event",
    "chat_risk_signal_detected_event",
    "chat_thread_opened_event",
]
