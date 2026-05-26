"""Directed edges, mutual pairs, and pair state evaluation."""

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

from .matchmaking_inflate import (
    ACTIVE_MEMBER_STATUS,
    OPEN_CASE_STATUSES,
    LedgerMirrorEntry,
    _append_pair_event_to_ledger,
    _attach_pair_profile_refs,
    _flush_ledger_mirror,
    _matchmaking_relation_key_for_members,
    inflate_case,
    inflate_edge,
    inflate_pair,
    member_is_available,
)
from .pool_members import get_pool_member, get_pool_members_by_ids, list_active_pool_members

def get_edge(conn, owner_member_id: str, candidate_member_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM matchmaking_edges
        WHERE owner_member_id = ? AND candidate_member_id = ?
        """,
        (owner_member_id, candidate_member_id),
    ).fetchone()
    return inflate_edge(row_to_dict(row))


def get_edges_for_owner_candidates(
    conn,
    owner_member_id: str,
    candidate_member_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    normalized = [str(item).strip() for item in candidate_member_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM matchmaking_edges
        WHERE owner_member_id = ?
          AND candidate_member_id IN ({placeholders})
        """,
        [owner_member_id, *normalized],
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        edge = inflate_edge(row_to_dict(row))
        if edge and edge.get("candidate_member_id"):
            out[str(edge["candidate_member_id"])] = edge
    return out


def get_edges_among_members(
    conn,
    member_ids: Iterable[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    normalized = [str(item).strip() for item in member_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM matchmaking_edges
        WHERE owner_member_id IN ({placeholders})
          AND candidate_member_id IN ({placeholders})
        """,
        [*normalized, *normalized],
    ).fetchall()
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        edge = inflate_edge(row_to_dict(row))
        if not edge:
            continue
        owner_id = str(edge.get("owner_member_id") or "").strip()
        candidate_id = str(edge.get("candidate_member_id") or "").strip()
        if owner_id and candidate_id:
            out[(owner_id, candidate_id)] = edge
    return out


def list_active_edges(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM matchmaking_edges
        WHERE edge_status = 'active'
        ORDER BY score DESC, owner_member_id ASC, candidate_member_id ASC
        """
    ).fetchall()
    return [inflate_edge(row_to_dict(row)) for row in rows]


def list_pairs(
    conn,
    *,
    statuses: Iterable[str] | None = None,
    attach_profile_refs: bool = True,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_clause = ""
    if statuses:
        normalized = list(statuses)
        placeholders = ", ".join(["?"] * len(normalized))
        where_clause = f"WHERE pair_status IN ({placeholders})"
        params.extend(normalized)
    rows = conn.execute(
        f"""
        SELECT *
        FROM matchmaking_pairs
        {where_clause}
        ORDER BY pair_score DESC, pair_key ASC
        """,
        params,
    ).fetchall()
    inflated_pairs = [inflate_pair(row_to_dict(row)) for row in rows]
    if not attach_profile_refs:
        return inflated_pairs
    return [_attach_pair_profile_refs(conn, pair) for pair in inflated_pairs]


def get_pair(conn, pair_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM matchmaking_pairs
        WHERE pair_key = ?
        """,
        (pair_key,),
    ).fetchone()
    return _attach_pair_profile_refs(conn, inflate_pair(row_to_dict(row)))


def list_match_cases(conn, *, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_clause = ""
    if statuses:
        normalized = list(statuses)
        placeholders = ", ".join(["?"] * len(normalized))
        where_clause = f"WHERE status IN ({placeholders})"
        params.extend(normalized)
    rows = conn.execute(
        f"""
        SELECT *
        FROM match_cases
        {where_clause}
        ORDER BY created_at DESC, case_id DESC
        """,
        params,
    ).fetchall()
    return [inflate_case(row_to_dict(row), conn=conn) for row in rows]

def list_match_case_events(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_case_events
        WHERE case_id = ?
        ORDER BY occurred_at ASC, event_id ASC
        """,
        (case_id,),
    ).fetchall()
    events = []
    for row in rows:
        event = row_to_dict(row)
        canon_raw = event.pop("canonical_event_json", None)
        payload = json_loads(event.pop("payload_json"), {})
        if canon_raw is not None and (not isinstance(canon_raw, str) or str(canon_raw).strip()):
            canon_obj = json.loads(canon_raw) if isinstance(canon_raw, str) else canon_raw
            if isinstance(canon_obj, dict):
                payload = {**payload, "canonical_event": canon_obj}
        event["payload"] = payload
        events.append(event)
    return events


def _pair_block_reason(
    member_a: Mapping[str, Any],
    member_b: Mapping[str, Any],
    edge_ab: Mapping[str, Any],
    edge_ba: Mapping[str, Any],
) -> str | None:
    if member_a["status"] != ACTIVE_MEMBER_STATUS or member_b["status"] != ACTIVE_MEMBER_STATUS:
        return "member_not_active"
    if not member_a["is_still_searching"] or not member_b["is_still_searching"]:
        return "member_not_searching"
    payloads = [edge_ab.get("payload") or {}, edge_ba.get("payload") or {}]
    if any(payload.get("risk_flags") for payload in payloads):
        return "risk_flags_present"
    if any(payload.get("follow_up_questions") for payload in payloads):
        return "follow_up_questions_present"
    if any(payload.get("missing_fields") for payload in payloads):
        return "missing_fields_present"
    if any(payload.get("self_profile_gaps") for payload in payloads):
        return "self_profile_gaps_present"
    return None


def _pair_has_open_case(conn, pair_key: str) -> bool:
    placeholders = ", ".join(["?"] * len(OPEN_CASE_STATUSES))
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS open_count
        FROM match_cases
        WHERE pair_key = ?
          AND status IN ({placeholders})
        """,
        [pair_key, *OPEN_CASE_STATUSES],
    ).fetchone()
    return bool(row and row["open_count"])


def _daily_case_cap(member: Mapping[str, Any]) -> int:
    raw_cap = member.get("daily_case_cap")
    if raw_cap is None:
        return 1
    return max(int(raw_cap), 0)


def _update_pair_status(
    conn,
    pair_key: str,
    *,
    pair_status: str,
    block_reason: str | None,
    now: datetime,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE matchmaking_pairs
        SET pair_status = ?,
            block_reason = ?,
            updated_at = ?
        WHERE pair_key = ?
        """,
        (pair_status, block_reason, format_dt(now), pair_key),
    )
    pair = get_pair(conn, pair_key)
    if pair:
        member_low = get_pool_member(conn, pair["member_low_id"])
        member_high = get_pool_member(conn, pair["member_high_id"])
        _append_pair_event_to_ledger(
            pair_event_type=f"pair_{pair_status}",
            member_low=member_low,
            member_high=member_high,
            pair_key=pair_key,
            now=now,
            actor_type="system",
            actor_id="system",
            payload={"block_reason": block_reason},
            ledger_mirror=ledger_mirror,
        )


def _evaluate_pair_state(
    conn,
    *,
    pair: Mapping[str, Any] | None,
    pair_score: int,
    min_required_score: int,
    member_low: Mapping[str, Any],
    member_high: Mapping[str, Any],
    low_to_high: Mapping[str, Any],
    high_to_low: Mapping[str, Any],
    now: datetime,
) -> tuple[str, str | None]:
    existing_status = pair.get("pair_status") if pair else None
    if existing_status == "mutual_accept":
        return "mutual_accept", None
    if existing_status == "case_opened" and pair and _pair_has_open_case(conn, pair["pair_key"]):
        return "case_opened", "open_case_exists"

    cooling_until_dt = parse_dt(pair.get("cooling_until")) if pair else None
    if cooling_until_dt and now < cooling_until_dt:
        return "cooling", "pair_cooling_active"
    if pair_score < min_required_score:
        return "below_threshold", "pair_score_below_threshold"

    block_reason = _pair_block_reason(member_low, member_high, low_to_high, high_to_low)
    if block_reason:
        return "blocked", block_reason
    return "eligible", None


def build_mutual_pairs(
    conn,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = current_time(now)
    ledger_mirror: list[LedgerMirrorEntry] = []
    edges = list_active_edges(conn)
    edge_by_direction = {
        (edge["owner_member_id"], edge["candidate_member_id"]): edge
        for edge in edges
    }
    processed: set[str] = set()
    updated_pair_keys: list[str] = []

    for (owner_member_id, candidate_member_id), edge_ab in edge_by_direction.items():
        reciprocal_key = (candidate_member_id, owner_member_id)
        if reciprocal_key not in edge_by_direction:
            continue
        pair_key = pair_key_for(owner_member_id, candidate_member_id)
        if pair_key in processed:
            continue
        processed.add(pair_key)
        edge_ba = edge_by_direction[reciprocal_key]
        member_low_id, member_high_id = sorted([owner_member_id, candidate_member_id])
        if member_low_id == owner_member_id:
            low_to_high = edge_ab
            high_to_low = edge_ba
        else:
            low_to_high = edge_ba
            high_to_low = edge_ab

        member_low = get_pool_member(conn, member_low_id)
        member_high = get_pool_member(conn, member_high_id)
        pair_score = min(
            int(low_to_high.get("score") or 0),
            int(high_to_low.get("score") or 0),
        )
        min_required_score = max(
            int(member_low.get("min_pair_score") or 0),
            int(member_high.get("min_pair_score") or 0),
        )
        pair_status = "eligible"
        block_reason = None
        existing = get_pair(conn, pair_key)
        pair_status, block_reason = _evaluate_pair_state(
            conn,
            pair=existing,
            pair_score=pair_score,
            min_required_score=min_required_score,
            member_low=member_low,
            member_high=member_high,
            low_to_high=low_to_high,
            high_to_low=high_to_low,
            now=now,
        )
        cooling_until = existing.get("cooling_until") if existing else None

        latest_payload = {
            "member_low": {"member_id": member_low_id, "user_key": member_low["user_key"]},
            "member_high": {"member_id": member_high_id, "user_key": member_high["user_key"]},
            "low_to_high": low_to_high.get("payload") or {},
            "high_to_low": high_to_low.get("payload") or {},
            "min_required_score": min_required_score,
        }
        if existing:
            conn.execute(
                """
                UPDATE matchmaking_pairs
                SET score_low_to_high = ?,
                    score_high_to_low = ?,
                    pair_score = ?,
                    pair_status = ?,
                    block_reason = ?,
                    latest_payload_json = ?,
                    updated_at = ?
                WHERE pair_key = ?
                """,
                (
                    int(low_to_high.get("score") or 0),
                    int(high_to_low.get("score") or 0),
                    pair_score,
                    pair_status,
                    block_reason,
                    json_dumps(latest_payload),
                    format_dt(now),
                    pair_key,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO matchmaking_pairs (
                  pair_key,
                  member_low_id,
                  member_high_id,
                  score_low_to_high,
                  score_high_to_low,
                  pair_score,
                  pair_status,
                  block_reason,
                  cooling_until,
                  latest_payload_json,
                  created_at,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pair_key,
                    member_low_id,
                    member_high_id,
                    int(low_to_high.get("score") or 0),
                    int(high_to_low.get("score") or 0),
                    pair_score,
                    pair_status,
                    block_reason,
                    cooling_until,
                    json_dumps(latest_payload),
                    format_dt(now),
                    format_dt(now),
                ),
            )
        updated_pair_keys.append(pair_key)
        pair_row = get_pair(conn, pair_key)
        if pair_row:
            member_low_live = get_pool_member(conn, pair_row["member_low_id"])
            member_high_live = get_pool_member(conn, pair_row["member_high_id"])
            _append_pair_event_to_ledger(
                pair_event_type=f"pair_{pair_status}",
                member_low=member_low_live,
                member_high=member_high_live,
                pair_key=pair_key,
                now=now,
                actor_type="system",
                actor_id="system",
                payload={"pair_score": pair_score, "block_reason": block_reason},
                ledger_mirror=ledger_mirror,
            )

    for pair in list_pairs(conn):
        if pair["pair_key"] in processed:
            continue
        if pair["pair_status"] == "mutual_accept":
            continue
        if pair["pair_status"] == "case_opened" and _pair_has_open_case(conn, pair["pair_key"]):
            continue

        cooling_until_dt = parse_dt(pair.get("cooling_until"))
        if pair["pair_status"] == "cooling" and cooling_until_dt and now < cooling_until_dt:
            continue

        member_low = get_pool_member(conn, pair["member_low_id"])
        member_high = get_pool_member(conn, pair["member_high_id"])
        if (
            pair["pair_status"] == "needs_revalidation"
            and (member_low.get("needs_refresh") or member_high.get("needs_refresh"))
        ):
            continue

        block_reason = "reciprocal_edge_missing"
        if member_low["status"] != ACTIVE_MEMBER_STATUS or member_high["status"] != ACTIVE_MEMBER_STATUS:
            block_reason = "member_not_active"
        elif not member_low["is_still_searching"] or not member_high["is_still_searching"]:
            block_reason = "member_not_searching"

        _update_pair_status(
            conn,
            pair["pair_key"],
            pair_status="stale",
            block_reason=block_reason,
            now=now,
            ledger_mirror=ledger_mirror,
        )
        updated_pair_keys.append(pair["pair_key"])

    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
    row_elig = conn.execute(
        "SELECT COUNT(*) AS c FROM matchmaking_pairs WHERE pair_status = 'eligible'",
    ).fetchone()
    row_mutual = conn.execute(
        "SELECT COUNT(*) AS c FROM matchmaking_pairs WHERE pair_status = 'mutual_accept'",
    ).fetchone()
    eligible_total = int(row_elig["c"]) if row_elig else 0
    mutual_total = int(row_mutual["c"]) if row_mutual else 0
    funnel_stage(
        system="matchmaking",
        stage=MATCHMAKING_FUNNEL_PAIR,
        pairs_updated=len(updated_pair_keys),
        eligible_pairs_total=eligible_total,
        mutual_pairs_total=mutual_total,
    )
    metric_gauge("matchmaking.pairs.updated_batch", len(updated_pair_keys))
    metric_gauge("matchmaking.pairs.eligible_total", eligible_total)
    metric_gauge("matchmaking.pairs.mutual_total", mutual_total)
    return [get_pair(conn, pair_key) for pair_key in updated_pair_keys]


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _count_member_cases_today(conn, member_id: str, now: datetime) -> int:
    return count_member_cases_today_for_members(conn, [member_id], now=now).get(member_id, 0)


def count_member_cases_today_for_members(
    conn,
    member_ids: Iterable[str],
    *,
    now: datetime,
) -> dict[str, int]:
    normalized = [str(item).strip() for item in member_ids if str(item or "").strip()]
    if not normalized:
        return {}
    day_start, day_end = _day_bounds(now)
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT first_contact_member_id AS member_id, second_contact_member_id AS other_member_id
        FROM match_cases
        WHERE created_at >= ?
          AND created_at < ?
          AND (
            first_contact_member_id IN ({placeholders})
            OR second_contact_member_id IN ({placeholders})
          )
        """,
        [
            format_dt(day_start),
            format_dt(day_end),
            *normalized,
            *normalized,
        ],
    ).fetchall()
    member_set = set(normalized)
    counts: dict[str, int] = {member_id: 0 for member_id in normalized}
    for row in rows:
        first_id = str(row["member_id"] or "").strip()
        second_id = str(row["other_member_id"] or "").strip()
        if first_id in member_set:
            counts[first_id] = counts.get(first_id, 0) + 1
        if second_id in member_set:
            counts[second_id] = counts.get(second_id, 0) + 1
    return counts


def _member_has_open_case(conn, member_id: str) -> bool:
    return member_id in members_with_open_cases(conn, [member_id])


def members_with_open_cases(conn, member_ids: Iterable[str]) -> set[str]:
    normalized = [str(item).strip() for item in member_ids if str(item or "").strip()]
    if not normalized:
        return set()
    status_placeholders = ", ".join(["?"] * len(OPEN_CASE_STATUSES))
    member_placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT first_contact_member_id AS member_id
        FROM match_cases
        WHERE status IN ({status_placeholders})
          AND first_contact_member_id IN ({member_placeholders})
        UNION
        SELECT second_contact_member_id AS member_id
        FROM match_cases
        WHERE status IN ({status_placeholders})
          AND second_contact_member_id IN ({member_placeholders})
        """,
        [*OPEN_CASE_STATUSES, *normalized, *OPEN_CASE_STATUSES, *normalized],
    ).fetchall()
    return {str(row["member_id"]).strip() for row in rows if row and row["member_id"]}

