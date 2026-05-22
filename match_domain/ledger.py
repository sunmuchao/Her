"""Relation / case ledger: ordered MatchEvent streams reduce to canonical state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from .model import CaseStatus, MatchEvent, RelationStatus

AGGREGATE_RELATION = "relation"
AGGREGATE_PAIR = "pair"
AGGREGATE_CASE = "case"


def relation_status_from_row_snapshot(
    *,
    delivery_status: str | None,
    delivery_reason: str | None = None,
    last_action_type: str | None = None,
    active_match_case_id: str | None = None,
) -> tuple[RelationStatus, str | None]:
    """Derive relation state from a profile_recommendations row snapshot (ledger event payload)."""

    active = str(active_match_case_id).strip() if active_match_case_id else None
    if active:
        return RelationStatus.PROXY_INTRO_ACTIVE, active
    ds = delivery_status
    reason = str(delivery_reason or "").strip()
    if ds == "escalated_to_case":
        if reason == "proxy_intro_handoff_completed":
            return RelationStatus.CLOSED, None
        return RelationStatus.PROXY_INTRO_ACTIVE, None
    if ds == "cooled_down":
        return RelationStatus.COOLING, None
    if ds == "saved_by_user":
        return RelationStatus.SAVED, None
    if ds == "direct_greet_started":
        return RelationStatus.DIRECT_GREET_STARTED, None
    if last_action_type == "skip":
        return RelationStatus.SKIPPED, None
    if ds:
        return RelationStatus.RECOMMENDED, None
    return RelationStatus.NEW, None


def sort_ledger_events(events: Iterable[MatchEvent]) -> list[MatchEvent]:
    """Stable total order for replay.

    ``relation_state_revision`` sorts after other events at the same ``occurred_at``
    so row snapshots apply after semantic actions recorded in the same second.
    """

    def _key(e: MatchEvent) -> tuple:
        revision_rank = 1 if e.event_type == "relation_state_revision" else 0
        return (e.occurred_at, revision_rank, e.event_id)

    return sorted(tuple(events), key=_key)


def _parse_occurred_at(raw: str) -> datetime:
    if not raw:
        raise ValueError("occurred_at is required")
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "T" in s:
        return datetime.fromisoformat(s)
    # MatchEvent.to_dict uses isoformat(sep=" ")
    if " " in s and len(s) >= 10:
        return datetime.fromisoformat(s.replace(" ", "T", 1))
    return datetime.fromisoformat(s)


def match_event_from_mapping(data: Mapping[str, Any]) -> MatchEvent:
    """Rebuild MatchEvent from ``canonical_event`` dict (e.g. in action payload)."""

    occurred = data["occurred_at"]
    if isinstance(occurred, datetime):
        occurred_at = occurred.replace(microsecond=0)
    else:
        occurred_at = _parse_occurred_at(str(occurred))
    payload = data.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise TypeError("canonical_event.payload must be a mapping")
    tid = data.get("trace_id")
    return MatchEvent(
        event_id=str(data["event_id"]),
        event_type=str(data["event_type"]),
        aggregate_type=str(data["aggregate_type"]),
        aggregate_id=str(data["aggregate_id"]),
        actor_type=str(data["actor_type"]),
        actor_id=str(data["actor_id"]),
        source_service=str(data["source_service"]),
        correlation_id=str(data["correlation_id"]),
        occurred_at=occurred_at,
        payload=dict(payload),
        idempotency_key=data.get("idempotency_key"),
        version=int(data.get("version") or 1),
        trace_id=str(tid).strip() if tid else None,
    )


def match_event_from_merged_action_payload(payload: Mapping[str, Any] | None) -> MatchEvent | None:
    """Extract embedded canonical event from ``merge_payload_with_event`` JSON."""

    if not payload:
        return None
    raw = payload.get("canonical_event")
    if not isinstance(raw, Mapping):
        return None
    try:
        return match_event_from_mapping(raw)
    except (KeyError, TypeError, ValueError):
        return None


def match_events_from_action_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    payload_loader: Any = None,
) -> list[MatchEvent]:
    """
    Build ordered MatchEvents from recommendation_actions rows.

    Each row must provide ``action_payload_json`` (str) or ``action_payload`` (dict).
    """

    events: list[MatchEvent] = []
    for row in rows:
        payload: Mapping[str, Any] | None
        if "action_payload" in row:
            payload = row["action_payload"]  # type: ignore[assignment]
        else:
            raw = row.get("action_payload_json")
            if payload_loader is not None:
                payload = payload_loader(raw)
            elif isinstance(raw, str):
                import json

                payload = json.loads(raw) if raw else {}
            elif isinstance(raw, Mapping):
                payload = dict(raw)
            else:
                payload = {}
        evt = match_event_from_merged_action_payload(payload or {})
        if evt is not None:
            events.append(evt)
    return sort_ledger_events(events)


def match_events_from_case_event_rows(rows: Sequence[Mapping[str, Any]]) -> list[MatchEvent]:
    """Parse MatchEvents from match_case_events rows (prefer ``canonical_event_json``, else merged payload)."""

    events: list[MatchEvent] = []
    for row in rows:
        evt: MatchEvent | None = None
        canon_raw = row.get("canonical_event_json")
        if canon_raw is not None and str(canon_raw).strip():
            import json

            if isinstance(canon_raw, str):
                data = json.loads(canon_raw)
            elif isinstance(canon_raw, Mapping):
                data = dict(canon_raw)
            else:
                data = None
            if isinstance(data, Mapping):
                try:
                    evt = match_event_from_mapping(data)
                except (KeyError, TypeError, ValueError):
                    evt = None
        if evt is None:
            payload = row.get("payload")
            if isinstance(payload, str):
                import json

                payload = json.loads(payload) if payload else {}
            if not isinstance(payload, Mapping):
                payload = {}
            evt = match_event_from_merged_action_payload(payload)
        if evt is not None:
            events.append(evt)
    return sort_ledger_events(events)


@dataclass(frozen=True)
class RelationLedgerState:
    status: RelationStatus
    active_match_case_id: str | None = None
    last_event_type: str | None = None


def reduce_relation_ledger(events: Sequence[MatchEvent]) -> RelationLedgerState:
    """
    Fold a relation aggregate event stream into canonical RelationStatus.

    Event types mirror recommendation-system recommendation_actions / proxy intro flows.
    """

    ordered = sort_ledger_events(events)
    status = RelationStatus.NEW
    active_case: str | None = None
    last_type: str | None = None

    for evt in ordered:
        if evt.aggregate_type != AGGREGATE_RELATION:
            continue
        t = evt.event_type
        last_type = t
        payload = evt.payload

        if t == "review_skip":
            status, active_case = RelationStatus.SKIPPED, None
        elif t == "review_save":
            status, active_case = RelationStatus.SAVED, None
        elif t == "review_direct_greet":
            status, active_case = RelationStatus.RECOMMENDED, None
        elif t == "skip":
            status, active_case = RelationStatus.SKIPPED, None
        elif t == "save":
            status, active_case = RelationStatus.SAVED, None
        elif t == "direct_greet":
            status, active_case = RelationStatus.DIRECT_GREET_STARTED, None
        elif t == "relation_state_revision":
            st, ac = relation_status_from_row_snapshot(
                delivery_status=payload.get("delivery_status"),
                delivery_reason=payload.get("delivery_reason"),
                last_action_type=payload.get("last_action_type"),
                active_match_case_id=payload.get("active_match_case_id"),
            )
            status, active_case = st, ac
        elif t == "request_proxy_intro":
            case_id = payload.get("case_id")
            active_case = str(case_id) if case_id else active_case
            status = RelationStatus.PROXY_INTRO_ACTIVE
        elif t == "proxy_intro_reply_accepted":
            status = RelationStatus.PROXY_INTRO_ACTIVE
        elif t == "proxy_intro_reply_declined":
            status, active_case = RelationStatus.COOLING, None
        elif t == "proxy_intro_timed_out":
            status, active_case = RelationStatus.COOLING, None
        elif t.startswith("proxy_intro_closed_"):
            reason = t.removeprefix("proxy_intro_closed_")
            active_case = None
            if reason == "handoff_completed":
                status = RelationStatus.CLOSED
            elif reason in {"requester_cancelled", "duplicate_merged"}:
                status = RelationStatus.SAVED
            elif reason == "delivery_failed":
                status = RelationStatus.COOLING
            else:
                status = RelationStatus.CLOSED
        else:
            # Unknown relation events do not clear proxy-intro state
            pass

    return RelationLedgerState(
        status=status,
        active_match_case_id=active_case,
        last_event_type=last_type,
    )


@dataclass
class CaseLedgerState:
    status: CaseStatus = CaseStatus.CLOSED
    last_event_type: str | None = None


def reduce_case_ledger(events: Sequence[MatchEvent]) -> CaseLedgerState:
    """
    Fold a case aggregate stream (proxy intro or matchmaking) into CaseStatus.
    """

    state = CaseLedgerState(status=CaseStatus.CLOSED)
    ordered = sort_ledger_events(events)

    for evt in ordered:
        if evt.aggregate_type != AGGREGATE_CASE:
            continue
        t = evt.event_type
        state.last_event_type = t

        if t == "case_created":
            state.status = CaseStatus.PENDING_CONTACT
        elif t in {"outreach_sent", "first_contact_sent"}:
            state.status = CaseStatus.AWAITING_REPLY
        elif t == "reply_accepted":
            state.status = CaseStatus.ACCEPTED
        elif t == "reply_declined":
            state.status = CaseStatus.DECLINED
        elif t in {"case_timed_out", "case_expired"}:
            state.status = CaseStatus.TIMED_OUT
        elif t == "case_closed" or t.startswith("case_closed_"):
            state.status = CaseStatus.CLOSED
        elif t == "second_contact_sent":
            state.status = CaseStatus.AWAITING_REPLY
        elif t == "first_reply_accepted":
            state.status = CaseStatus.PENDING_CONTACT
        elif t == "second_reply_accepted":
            state.status = CaseStatus.ACCEPTED
        elif t in {
            "first_reply_decline",
            "second_reply_decline",
        }:
            state.status = CaseStatus.DECLINED
        elif t in {
            "first_reply_timeout",
            "second_reply_timeout",
        }:
            state.status = CaseStatus.TIMED_OUT

    return state


__all__ = [
    "AGGREGATE_CASE",
    "AGGREGATE_PAIR",
    "AGGREGATE_RELATION",
    "CaseLedgerState",
    "RelationLedgerState",
    "match_event_from_mapping",
    "match_event_from_merged_action_payload",
    "match_events_from_action_rows",
    "match_events_from_case_event_rows",
    "reduce_case_ledger",
    "reduce_relation_ledger",
    "relation_status_from_row_snapshot",
    "sort_ledger_events",
]
