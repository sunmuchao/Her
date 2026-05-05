"""Unified envelope for recommendation (proxy intro) and matchmaking case streams."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .adapters import build_canonical_event
from .ids import correlation_case_event, idempotency_case_event
from .ledger import AGGREGATE_CASE
from .model import CaseType, MatchEvent


CASE_EVENT_PAYLOAD_SCHEMA = "match_domain.case_event/v1"


def case_event_time_bucket(occurred_at: datetime) -> str:
    """Stable time bucket for case-event idempotency keys (matches service ``format_dt``)."""

    return occurred_at.replace(microsecond=0).isoformat(sep=" ")


def build_case_aggregate_event(
    *,
    event_type: str,
    case_id: str,
    case_type: CaseType | str,
    source_service: str,
    actor_type: str,
    actor_id: str,
    occurred_at: datetime,
    entity_ids: Mapping[str, str],
    payload: Mapping[str, Any] | None = None,
    trace_id: str | None = None,
) -> MatchEvent:
    """
    Build a ``MatchEvent`` for aggregate ``case`` with shared payload contract.

    ``case_type`` string doubles as the correlation/idempotency *subsystem* tag
    (``proxy_intro`` vs ``matchmaking``), matching :func:`correlation_case_event`.
    """

    ct = case_type.value if isinstance(case_type, CaseType) else str(case_type)
    occurred = occurred_at.replace(microsecond=0)
    merged_payload = dict(payload or {})
    merged_payload["schema"] = CASE_EVENT_PAYLOAD_SCHEMA
    merged_payload["case_type"] = ct
    return build_canonical_event(
        event_type=event_type,
        aggregate_type=AGGREGATE_CASE,
        aggregate_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source_service=source_service,
        correlation_id=correlation_case_event(case_id, ct, event_type, trace_id=trace_id),
        idempotency_key=idempotency_case_event(case_id, ct, event_type, case_event_time_bucket(occurred)),
        occurred_at=occurred,
        payload=merged_payload,
        entity_ids=dict(entity_ids),
        trace_id=trace_id,
    )


__all__ = [
    "CASE_EVENT_PAYLOAD_SCHEMA",
    "build_case_aggregate_event",
    "case_event_time_bucket",
]
