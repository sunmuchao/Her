"""JSON inflation and ledger helpers for matchmaking entities."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain import (  # noqa: E402
    CaseType,
    append_outbox_pending,
    build_canonical_event,
    build_case_aggregate_event,
    bundle_matchmaking_case_entities,
    canonical_pair_key_for_members,
    canonical_pair_status,
    correlation_member_feedback,
    entity_id_pair,
    entity_id_pool_member,
    format_correlation_id,
    idempotency_feedback,
    match_events_from_case_event_rows,
    matchmaking_relation_key,
    merge_payload_with_event,
    pool_member_profile_ref,
    profile_ref_to_dict,
    reduce_case_ledger,
)
from partner_search import search_profiles  # noqa: E402
from match_domain.search_visibility import run_partner_search as _run_partner_search  # noqa: E402
from match_domain.snapshot_hash import candidate_snapshot_hash  # noqa: E402
from profile_service import apply_persona_patch  # noqa: E402
from her_time_utils import bool_to_int, current_time, format_dt, parse_dt  # noqa: E402

from .identifiers import generate_case_id, generate_feedback_id, generate_member_id, pair_key_for
from .storage import json_dumps, json_loads, row_to_dict

from observability import (  # noqa: E402
    MATCHMAKING_FUNNEL_CASE,
    MATCHMAKING_FUNNEL_EDGE,
    MATCHMAKING_FUNNEL_FIRST_ACCEPT,
    MATCHMAKING_FUNNEL_MEMBER,
    MATCHMAKING_FUNNEL_MUTUAL_ACCEPT,
    MATCHMAKING_FUNNEL_PAIR,
    MATCHMAKING_FUNNEL_SECOND_ACCEPT,
    alert_signal,
    funnel_stage,
    metric_gauge,
)
from relationship_ledger.runtime import append_event_to_default_ledger

SearchRunner = Callable[..., dict[str, Any]]
PersonaSyncRunner = Callable[[Mapping[str, Any]], dict[str, Any]]

ACTIVE_MEMBER_STATUS = "active_single"
OPEN_CASE_STATUSES = {
    "pending_first_contact",
    "awaiting_first_reply",
    "pending_second_contact",
    "awaiting_second_reply",
}
FINAL_CASE_STATUSES = {"mutual_accept", "declined", "timed_out", "closed"}
LedgerMirrorEntry = dict[str, Any]


def member_is_available(member: Mapping[str, Any]) -> bool:
    return member.get("status") == ACTIVE_MEMBER_STATUS and bool(member.get("is_still_searching"))


def inflate_pool_member(member: dict[str, Any] | None) -> dict[str, Any] | None:
    if not member:
        return member
    inflated = dict(member)
    inflated["self_profile"] = json_loads(inflated.pop("self_profile_json"), {})
    inflated["search_criteria"] = json_loads(inflated.pop("search_criteria_json"), {})
    inflated["allowed_channels"] = json_loads(inflated.pop("allowed_channels_json"), [])
    inflated["profile_ref"] = profile_ref_to_dict(pool_member_profile_ref(inflated))
    return inflated


def inflate_edge(edge: dict[str, Any] | None) -> dict[str, Any] | None:
    if not edge:
        return edge
    inflated = dict(edge)
    inflated["payload"] = json_loads(inflated.pop("payload_json"), {})
    return inflated


def inflate_pair(pair: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pair:
        return pair
    inflated = dict(pair)
    inflated["latest_payload"] = json_loads(inflated.pop("latest_payload_json"), {})
    inflated["canonical_pair_status"] = canonical_pair_status(inflated.get("pair_status")).value
    return inflated


def inflate_case(case: dict[str, Any] | None, *, conn=None) -> dict[str, Any] | None:
    if not case:
        return case
    inflated = dict(case)
    inflated["case_type"] = inflated.get("case_type") or CaseType.MATCHMAKING.value
    cid = inflated.get("case_id")
    ledger_events = []
    if conn is not None and cid:
        from .pairs import list_match_case_events

        event_rows = list_match_case_events(conn, str(cid))
        ledger_events = match_events_from_case_event_rows(event_rows)
    inflated["case_ledger_event_count"] = len(ledger_events)
    reduced = reduce_case_ledger(ledger_events)
    inflated["canonical_case_status"] = reduced.status.value
    if conn is not None:
        first_id = inflated.get("first_contact_member_id")
        second_id = inflated.get("second_contact_member_id")
        if first_id and second_id:
            try:
                from .pool_members import get_pool_member

                member_low = get_pool_member(conn, str(first_id))
                member_high = get_pool_member(conn, str(second_id))
                inflated["relation_key"] = matchmaking_relation_key(member_low, member_high)
                inflated["canonical_pair_key"] = canonical_pair_key_for_members(member_low, member_high)
                inflated["owner_profile_ref"] = profile_ref_to_dict(pool_member_profile_ref(member_low))
                inflated["target_profile_ref"] = profile_ref_to_dict(pool_member_profile_ref(member_high))
            except ValueError:
                pass
    return inflated


def inflate_feedback(feedback: dict[str, Any] | None) -> dict[str, Any] | None:
    if not feedback:
        return feedback
    inflated = dict(feedback)
    inflated["persona_patch"] = json_loads(inflated.pop("persona_patch_json"), {})
    inflated["raw_payload"] = json_loads(inflated.pop("raw_payload_json"), {})
    inflated["persona_sync_result"] = json_loads(inflated.pop("persona_sync_result_json"), {})
    return inflated


def _attach_pair_profile_refs(conn, pair: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pair:
        return pair
    from .pool_members import get_pool_member

    member_low = get_pool_member(conn, pair["member_low_id"])
    member_high = get_pool_member(conn, pair["member_high_id"])
    pair["member_low_profile_ref"] = member_low["profile_ref"]
    pair["member_high_profile_ref"] = member_high["profile_ref"]
    pair["canonical_pair_key"] = canonical_pair_key_for_members(member_low, member_high)
    return pair


def _matchmaking_relation_key_for_members(
    member_low: Mapping[str, Any],
    member_high: Mapping[str, Any],
) -> str:
    return matchmaking_relation_key(member_low, member_high)


def _flush_ledger_mirror(entries: list[LedgerMirrorEntry]) -> None:
    for entry in entries:
        append_event_to_default_ledger(**entry)


def _append_pair_event_to_ledger(
    *,
    pair_event_type: str,
    member_low: Mapping[str, Any],
    member_high: Mapping[str, Any],
    pair_key: str,
    now: datetime,
    actor_type: str,
    actor_id: str,
    payload: Mapping[str, Any] | None = None,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
) -> None:
    relation_key = _matchmaking_relation_key_for_members(member_low, member_high)
    event = build_canonical_event(
        event_type=pair_event_type,
        aggregate_type="relation",
        aggregate_id=relation_key,
        actor_type=actor_type,
        actor_id=actor_id,
        source_service="matchmaking-system",
        correlation_id=format_correlation_id(entity_id_pair(pair_key), pair_event_type, format_dt(now)),
        idempotency_key=f"her:idem:{entity_id_pair(pair_key)}:{pair_event_type}:{format_dt(now)}",
        occurred_at=now,
        payload={
            "pair_key": pair_key,
            **dict(payload or {}),
        },
        entity_ids={
            "pair": entity_id_pair(pair_key),
            "member_low": entity_id_pool_member(str(member_low["member_id"])),
            "member_high": entity_id_pool_member(str(member_high["member_id"])),
        },
    )
    entry: LedgerMirrorEntry = {
        "event": event,
        "relation_key": relation_key,
        "owner_profile_ref": pool_member_profile_ref(member_low),
        "target_profile_ref": pool_member_profile_ref(member_high),
    }
    if ledger_mirror is not None:
        ledger_mirror.append(entry)
        return
    append_event_to_default_ledger(
        event=event,
        relation_key=relation_key,
        owner_profile_ref=pool_member_profile_ref(member_low),
        target_profile_ref=pool_member_profile_ref(member_high),
    )

