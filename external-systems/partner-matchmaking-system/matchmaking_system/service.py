"""Phase 5 matchmaking workflows built on top of partner-search and persona-memory-sync."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping

from .partner_search_client import run_partner_search
from .persona_memory_client import sync_persona_memory
from .storage import json_dumps, json_loads, row_to_dict


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


def current_time(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return current_time(value).isoformat(sep=" ")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def bool_to_int(value: bool) -> int:
    return 1 if value else 0


def member_is_available(member: Mapping[str, Any]) -> bool:
    return member.get("status") == ACTIVE_MEMBER_STATUS and bool(member.get("is_still_searching"))


def generate_member_id() -> str:
    return f"pool-{uuid.uuid4().hex[:12]}"


def generate_case_id() -> str:
    return f"case-{uuid.uuid4().hex[:12]}"


def generate_feedback_id() -> str:
    return f"feedback-{uuid.uuid4().hex[:12]}"


def pair_key_for(member_a_id: str, member_b_id: str) -> str:
    low_id, high_id = sorted([str(member_a_id), str(member_b_id)])
    return f"{low_id}:{high_id}"


def candidate_snapshot_hash(result: Mapping[str, Any]) -> str:
    return hashlib.sha256(json_dumps(dict(result)).encode("utf-8")).hexdigest()


def inflate_pool_member(member: dict[str, Any] | None) -> dict[str, Any] | None:
    if not member:
        return member
    inflated = dict(member)
    inflated["self_profile"] = json_loads(inflated.pop("self_profile_json"), {})
    inflated["search_criteria"] = json_loads(inflated.pop("search_criteria_json"), {})
    inflated["allowed_channels"] = json_loads(inflated.pop("allowed_channels_json"), [])
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
    return inflated


def inflate_case(case: dict[str, Any] | None) -> dict[str, Any] | None:
    if not case:
        return case
    return dict(case)


def inflate_feedback(feedback: dict[str, Any] | None) -> dict[str, Any] | None:
    if not feedback:
        return feedback
    inflated = dict(feedback)
    inflated["persona_patch"] = json_loads(inflated.pop("persona_patch_json"), {})
    inflated["raw_payload"] = json_loads(inflated.pop("raw_payload_json"), {})
    inflated["persona_sync_result"] = json_loads(inflated.pop("persona_sync_result_json"), {})
    return inflated


def get_pool_member(conn, member_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM matchmaking_pool_members WHERE member_id = ?",
        (member_id,),
    ).fetchone()
    member = inflate_pool_member(row_to_dict(row))
    if not member:
        raise ValueError(f"Unknown pool member: {member_id}")
    return member


def get_pool_member_by_user_key(conn, source: str, user_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM matchmaking_pool_members
        WHERE source = ? AND user_key = ?
        """,
        (source, user_key),
    ).fetchone()
    return inflate_pool_member(row_to_dict(row))


def find_pool_member_by_source_profile(conn, source: str, profile_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM matchmaking_pool_members
        WHERE source = ? AND self_id = ?
        """,
        (source, profile_id),
    ).fetchone()
    return inflate_pool_member(row_to_dict(row))


def list_pool_members(conn, *, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
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
        FROM matchmaking_pool_members
        {where_clause}
        ORDER BY created_at ASC, member_id ASC
        """,
        params,
    ).fetchall()
    return [inflate_pool_member(row_to_dict(row)) for row in rows]


def list_active_pool_members(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM matchmaking_pool_members
        WHERE status = ? AND is_still_searching = 1
        ORDER BY created_at ASC, member_id ASC
        """,
        (ACTIVE_MEMBER_STATUS,),
    ).fetchall()
    return [inflate_pool_member(row_to_dict(row)) for row in rows]


def create_pool_member(
    conn,
    *,
    user_key: str,
    source: str,
    search_criteria: Mapping[str, Any],
    self_profile: Mapping[str, Any] | None = None,
    self_id: int | None = None,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    status: str = ACTIVE_MEMBER_STATUS,
    is_still_searching: bool = True,
    allowed_channels: Iterable[str] | None = None,
    min_pair_score: int = 80,
    daily_case_cap: int = 1,
    refresh_interval_hours: int = 24,
    limit_count: int = 10,
    member_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    created_at = format_dt(now)
    existing = get_pool_member_by_user_key(conn, source, user_key)
    if existing:
        member_id = existing["member_id"]
        conn.execute(
            """
            UPDATE matchmaking_pool_members
            SET table_name = ?,
                photos_table_name = ?,
                self_id = ?,
                self_profile_json = ?,
                search_criteria_json = ?,
                status = ?,
                is_still_searching = ?,
                allowed_channels_json = ?,
                min_pair_score = ?,
                daily_case_cap = ?,
                refresh_interval_hours = ?,
                limit_count = ?,
                needs_refresh = 1,
                updated_at = ?
            WHERE member_id = ?
            """,
            (
                table_name,
                photos_table_name,
                self_id,
                json_dumps(dict(self_profile or {})),
                json_dumps(dict(search_criteria or {})),
                status,
                bool_to_int(is_still_searching),
                json_dumps(list(allowed_channels or [])),
                int(min_pair_score),
                int(daily_case_cap),
                int(refresh_interval_hours),
                int(limit_count),
                created_at,
                member_id,
            ),
        )
        conn.commit()
        return get_pool_member(conn, member_id)

    member_id = member_id or generate_member_id()
    conn.execute(
        """
        INSERT INTO matchmaking_pool_members (
          member_id,
          user_key,
          source,
          table_name,
          photos_table_name,
          self_id,
          self_profile_json,
          search_criteria_json,
          status,
          is_still_searching,
          allowed_channels_json,
          min_pair_score,
          daily_case_cap,
          refresh_interval_hours,
          limit_count,
          last_scanned_at,
          last_state_reason,
          needs_refresh,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1, ?, ?)
        """,
        (
            member_id,
            user_key,
            source,
            table_name,
            photos_table_name,
            self_id,
            json_dumps(dict(self_profile or {})),
            json_dumps(dict(search_criteria or {})),
            status,
            bool_to_int(is_still_searching),
            json_dumps(list(allowed_channels or [])),
            int(min_pair_score),
            int(daily_case_cap),
            int(refresh_interval_hours),
            int(limit_count),
            created_at,
            created_at,
        ),
    )
    conn.commit()
    return get_pool_member(conn, member_id)


def set_pool_member_status(
    conn,
    member_id: str,
    *,
    status: str,
    is_still_searching: bool | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    member = get_pool_member(conn, member_id)
    still_searching = member["is_still_searching"] if is_still_searching is None else is_still_searching
    conn.execute(
        """
        UPDATE matchmaking_pool_members
        SET status = ?,
            is_still_searching = ?,
            last_state_reason = ?,
            needs_refresh = 1,
            updated_at = ?
        WHERE member_id = ?
        """,
        (
            status,
            bool_to_int(bool(still_searching)),
            reason,
            format_dt(now),
            member_id,
        ),
    )
    conn.commit()
    updated_member = get_pool_member(conn, member_id)
    if not member_is_available(updated_member):
        revalidate_member_matches(
            conn,
            member_id,
            reason=reason or "member_unavailable",
            now=now,
        )
        updated_member = get_pool_member(conn, member_id)
    return updated_member


def is_pool_member_due(member: Mapping[str, Any], now: datetime) -> bool:
    if member.get("status") != ACTIVE_MEMBER_STATUS or not member.get("is_still_searching"):
        return False
    if member.get("needs_refresh"):
        return True
    last_scanned_at = parse_dt(member.get("last_scanned_at"))
    if last_scanned_at is None:
        return True
    interval = timedelta(hours=int(member.get("refresh_interval_hours") or 24))
    return now >= last_scanned_at + interval


def list_due_pool_members(
    conn,
    *,
    now: datetime | None = None,
    member_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    now = current_time(now)
    if member_ids:
        requested = list(member_ids)
        placeholders = ", ".join(["?"] * len(requested))
        rows = conn.execute(
            f"""
            SELECT *
            FROM matchmaking_pool_members
            WHERE member_id IN ({placeholders})
            ORDER BY created_at ASC, member_id ASC
            """,
            requested,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM matchmaking_pool_members
            ORDER BY created_at ASC, member_id ASC
            """
        ).fetchall()
    members = [inflate_pool_member(row_to_dict(row)) for row in rows]
    return [member for member in members if is_pool_member_due(member, now)]


def load_pool_member_search_args(member: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": member["source"],
        "table_name": member.get("table_name"),
        "photos_table_name": member.get("photos_table_name"),
        "criteria": member.get("search_criteria") or {},
        "self_profile": member.get("self_profile") or None,
        "self_id": member.get("self_id"),
        "limit": int(member.get("limit_count") or 10),
        "include_source": True,
        "include_text": False,
    }


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


def list_pairs(conn, *, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
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
    return [inflate_pair(row_to_dict(row)) for row in rows]


def get_pair(conn, pair_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM matchmaking_pairs
        WHERE pair_key = ?
        """,
        (pair_key,),
    ).fetchone()
    return inflate_pair(row_to_dict(row))


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
    return [inflate_case(row_to_dict(row)) for row in rows]


def get_match_case(conn, case_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM match_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    case = inflate_case(row_to_dict(row))
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    return case


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
        event["payload"] = json_loads(event.pop("payload_json"), {})
        events.append(event)
    return events


def list_feedback_events(conn, member_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM matchmaking_feedback_events
        WHERE member_id = ?
        ORDER BY created_at DESC, feedback_id DESC
        """,
        (member_id,),
    ).fetchall()
    return [inflate_feedback(row_to_dict(row)) for row in rows]


def _record_case_event(
    conn,
    *,
    case_id: str,
    pair_key: str,
    event_type: str,
    actor_member_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO match_case_events (
          case_id,
          pair_key,
          event_type,
          actor_member_id,
          payload_json,
          occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            pair_key,
            event_type,
            actor_member_id,
            json_dumps(dict(payload or {})),
            format_dt(current_time(now)),
        ),
    )


def refresh_pool_member(
    conn,
    member_id: str,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
) -> dict[str, Any]:
    now = current_time(now)
    member = get_pool_member(conn, member_id)
    if member["status"] != ACTIVE_MEMBER_STATUS or not member["is_still_searching"]:
        return {
            "member_id": member_id,
            "user_key": member["user_key"],
            "skipped": True,
            "reason": "member_not_active",
            "edge_count": 0,
        }

    response = search_runner(**load_pool_member_search_args(member))
    results = list(response.get("results") or [])
    active_candidate_member_ids: list[str] = []
    synced_count = 0

    for result in results:
        candidate_id = result.get("id")
        if candidate_id is None:
            continue
        candidate_member = find_pool_member_by_source_profile(
            conn,
            member["source"],
            int(candidate_id),
        )
        if not candidate_member or candidate_member["member_id"] == member_id:
            continue
        if candidate_member["status"] != ACTIVE_MEMBER_STATUS or not candidate_member["is_still_searching"]:
            continue
        active_candidate_member_ids.append(candidate_member["member_id"])
        existing = get_edge(conn, member_id, candidate_member["member_id"])
        snapshot_hash = candidate_snapshot_hash(result)
        payload_json = json_dumps(dict(result))
        if existing:
            conn.execute(
                """
                UPDATE matchmaking_edges
                SET score = ?,
                    fit_score = ?,
                    confidence_score = ?,
                    risk_score = ?,
                    edge_status = 'active',
                    edge_reason = 'candidate_in_latest_results',
                    snapshot_hash = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE edge_id = ?
                """,
                (
                    int(result.get("score") or 0),
                    int(result.get("fit_score") or 0),
                    int(result.get("confidence_score") or 0),
                    int(result.get("risk_score") or 0),
                    snapshot_hash,
                    payload_json,
                    format_dt(now),
                    existing["edge_id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO matchmaking_edges (
                  owner_member_id,
                  candidate_member_id,
                  score,
                  fit_score,
                  confidence_score,
                  risk_score,
                  edge_status,
                  edge_reason,
                  snapshot_hash,
                  payload_json,
                  discovered_at,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'new_candidate', ?, ?, ?, ?)
                """,
                (
                    member_id,
                    candidate_member["member_id"],
                    int(result.get("score") or 0),
                    int(result.get("fit_score") or 0),
                    int(result.get("confidence_score") or 0),
                    int(result.get("risk_score") or 0),
                    snapshot_hash,
                    payload_json,
                    format_dt(now),
                    format_dt(now),
                ),
            )
        synced_count += 1

    if active_candidate_member_ids:
        placeholders = ", ".join(["?"] * len(active_candidate_member_ids))
        conn.execute(
            f"""
            UPDATE matchmaking_edges
            SET edge_status = 'stale',
                edge_reason = 'not_in_latest_results',
                updated_at = ?
            WHERE owner_member_id = ?
              AND candidate_member_id NOT IN ({placeholders})
            """,
            [format_dt(now), member_id, *active_candidate_member_ids],
        )
    else:
        conn.execute(
            """
            UPDATE matchmaking_edges
            SET edge_status = 'stale',
                edge_reason = 'not_in_latest_results',
                updated_at = ?
            WHERE owner_member_id = ?
            """,
            (format_dt(now), member_id),
        )

    conn.execute(
        """
        UPDATE matchmaking_pool_members
        SET last_scanned_at = ?,
            needs_refresh = 0,
            updated_at = ?
        WHERE member_id = ?
        """,
        (format_dt(now), format_dt(now), member_id),
    )
    conn.commit()
    return {
        "member_id": member_id,
        "user_key": member["user_key"],
        "skipped": False,
        "result_count": len(results),
        "edge_count": synced_count,
    }


def refresh_active_pool(
    conn,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
    member_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    now = current_time(now)
    due_members = list_due_pool_members(conn, now=now, member_ids=member_ids)
    return [
        refresh_pool_member(
            conn,
            member["member_id"],
            now=now,
            search_runner=search_runner,
        )
        for member in due_members
    ]


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
        )
        updated_pair_keys.append(pair["pair_key"])

    conn.commit()
    return [get_pair(conn, pair_key) for pair_key in updated_pair_keys]


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _count_member_cases_today(conn, member_id: str, now: datetime) -> int:
    day_start, day_end = _day_bounds(now)
    row = conn.execute(
        """
        SELECT COUNT(*) AS case_count
        FROM match_cases
        WHERE created_at >= ?
          AND created_at < ?
          AND (first_contact_member_id = ? OR second_contact_member_id = ?)
        """,
        (format_dt(day_start), format_dt(day_end), member_id, member_id),
    ).fetchone()
    return int(row["case_count"]) if row else 0


def _member_has_open_case(conn, member_id: str) -> bool:
    placeholders = ", ".join(["?"] * len(OPEN_CASE_STATUSES))
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS open_count
        FROM match_cases
        WHERE status IN ({placeholders})
          AND (first_contact_member_id = ? OR second_contact_member_id = ?)
        """,
        [*OPEN_CASE_STATUSES, member_id, member_id],
    ).fetchone()
    return bool(row and row["open_count"])


def open_match_cases(
    conn,
    *,
    now: datetime | None = None,
    case_expires_hours: int = 72,
) -> list[dict[str, Any]]:
    now = current_time(now)
    created_case_ids: list[str] = []
    for pair in list_pairs(conn, statuses=["eligible"]):
        pair_key = pair["pair_key"]
        member_low = get_pool_member(conn, pair["member_low_id"])
        member_high = get_pool_member(conn, pair["member_high_id"])
        if not member_is_available(member_low) or not member_is_available(member_high):
            _update_pair_status(
                conn,
                pair_key,
                pair_status="blocked",
                block_reason="member_not_active"
                if member_low["status"] != ACTIVE_MEMBER_STATUS or member_high["status"] != ACTIVE_MEMBER_STATUS
                else "member_not_searching",
                now=now,
            )
            continue

        low_to_high = get_edge(conn, member_low["member_id"], member_high["member_id"])
        high_to_low = get_edge(conn, member_high["member_id"], member_low["member_id"])
        if (
            not low_to_high
            or not high_to_low
            or low_to_high["edge_status"] != "active"
            or high_to_low["edge_status"] != "active"
        ):
            _update_pair_status(
                conn,
                pair_key,
                pair_status="stale",
                block_reason="reciprocal_edge_missing",
                now=now,
            )
            continue

        pair_score = min(int(low_to_high.get("score") or 0), int(high_to_low.get("score") or 0))
        min_required_score = max(
            int(member_low.get("min_pair_score") or 0),
            int(member_high.get("min_pair_score") or 0),
        )
        pair_status, block_reason = _evaluate_pair_state(
            conn,
            pair=pair,
            pair_score=pair_score,
            min_required_score=min_required_score,
            member_low=member_low,
            member_high=member_high,
            low_to_high=low_to_high,
            high_to_low=high_to_low,
            now=now,
        )
        if pair_status != "eligible":
            _update_pair_status(
                conn,
                pair_key,
                pair_status=pair_status,
                block_reason=block_reason,
                now=now,
            )
            continue

        if _member_has_open_case(conn, member_low["member_id"]) or _member_has_open_case(conn, member_high["member_id"]):
            continue
        if _count_member_cases_today(conn, member_low["member_id"], now) >= _daily_case_cap(member_low):
            continue
        if _count_member_cases_today(conn, member_high["member_id"], now) >= _daily_case_cap(member_high):
            continue

        case_id = generate_case_id()
        first_contact_member_id = member_low["member_id"]
        second_contact_member_id = member_high["member_id"]
        conn.execute(
            """
            INSERT INTO match_cases (
              case_id,
              pair_key,
              initiator_type,
              status,
              first_contact_member_id,
              second_contact_member_id,
              expires_at,
              created_at,
              updated_at
            ) VALUES (?, ?, 'system', 'pending_first_contact', ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                pair_key,
                first_contact_member_id,
                second_contact_member_id,
                format_dt(now + timedelta(hours=case_expires_hours)),
                format_dt(now),
                format_dt(now),
            ),
        )
        conn.execute(
            """
            UPDATE matchmaking_pairs
            SET pair_status = 'case_opened',
                block_reason = 'open_case_exists',
                updated_at = ?
            WHERE pair_key = ?
            """,
            (format_dt(now), pair_key),
        )
        _record_case_event(
            conn,
            case_id=case_id,
            pair_key=pair_key,
            event_type="case_created",
            payload={"initiator_type": "system"},
            now=now,
        )
        created_case_ids.append(case_id)
    conn.commit()
    return [get_match_case(conn, case_id) for case_id in created_case_ids]


def dispatch_case_contact(
    conn,
    case_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    case = get_match_case(conn, case_id)
    if case["status"] == "pending_first_contact":
        conn.execute(
            """
            UPDATE match_cases
            SET status = 'awaiting_first_reply',
                first_contacted_at = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (format_dt(now), format_dt(now), case_id),
        )
        _record_case_event(
            conn,
            case_id=case_id,
            pair_key=case["pair_key"],
            event_type="first_contact_sent",
            actor_member_id=case["first_contact_member_id"],
            now=now,
        )
    elif case["status"] == "pending_second_contact":
        conn.execute(
            """
            UPDATE match_cases
            SET status = 'awaiting_second_reply',
                second_contacted_at = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (format_dt(now), format_dt(now), case_id),
        )
        _record_case_event(
            conn,
            case_id=case_id,
            pair_key=case["pair_key"],
            event_type="second_contact_sent",
            actor_member_id=case["second_contact_member_id"],
            now=now,
        )
    else:
        raise ValueError(f"Case {case_id} cannot dispatch outreach from status {case['status']}.")
    conn.commit()
    return get_match_case(conn, case_id)


def _apply_pair_cooling(
    conn,
    pair_key: str,
    *,
    days: int,
    reason: str,
    now: datetime,
) -> None:
    cooling_until = now + timedelta(days=days)
    conn.execute(
        """
        UPDATE matchmaking_pairs
        SET pair_status = 'cooling',
            block_reason = ?,
            cooling_until = ?,
            updated_at = ?
        WHERE pair_key = ?
        """,
        (reason, format_dt(cooling_until), format_dt(now), pair_key),
    )


def record_case_reply(
    conn,
    case_id: str,
    *,
    member_id: str,
    reply_type: str,
    now: datetime | None = None,
    decline_cooling_days: int = 60,
    timeout_cooling_days: int = 30,
) -> dict[str, Any]:
    now = current_time(now)
    case = get_match_case(conn, case_id)
    normalized_reply = str(reply_type).strip().lower()
    if normalized_reply not in {"accept", "decline", "timeout"}:
        raise ValueError(f"Unsupported reply type: {reply_type}")

    if case["status"] == "awaiting_first_reply":
        if member_id != case["first_contact_member_id"]:
            raise ValueError("First reply must come from the first-contact member.")
        if normalized_reply == "accept":
            conn.execute(
                """
                UPDATE match_cases
                SET first_reply_status = 'accepted',
                    status = 'pending_second_contact',
                    updated_at = ?
                WHERE case_id = ?
                """,
                (format_dt(now), case_id),
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type="first_reply_accepted",
                actor_member_id=member_id,
                now=now,
            )
        else:
            final_status = "declined" if normalized_reply == "decline" else "timed_out"
            cooling_days = decline_cooling_days if normalized_reply == "decline" else timeout_cooling_days
            conn.execute(
                """
                UPDATE match_cases
                SET first_reply_status = ?,
                    status = ?,
                    closed_reason = ?,
                    updated_at = ?
                WHERE case_id = ?
                """,
                (
                    "declined" if normalized_reply == "decline" else "timed_out",
                    final_status,
                    f"first_contact_{normalized_reply}",
                    format_dt(now),
                    case_id,
                ),
            )
            _apply_pair_cooling(
                conn,
                case["pair_key"],
                days=cooling_days,
                reason=f"first_contact_{normalized_reply}",
                now=now,
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type=f"first_reply_{normalized_reply}",
                actor_member_id=member_id,
                now=now,
            )
    elif case["status"] == "awaiting_second_reply":
        if member_id != case["second_contact_member_id"]:
            raise ValueError("Second reply must come from the second-contact member.")
        if normalized_reply == "accept":
            conn.execute(
                """
                UPDATE match_cases
                SET second_reply_status = 'accepted',
                    status = 'mutual_accept',
                    updated_at = ?
                WHERE case_id = ?
                """,
                (format_dt(now), case_id),
            )
            conn.execute(
                """
                UPDATE matchmaking_pairs
                SET pair_status = 'mutual_accept',
                    block_reason = NULL,
                    updated_at = ?
                WHERE pair_key = ?
                """,
                (format_dt(now), case["pair_key"]),
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type="second_reply_accepted",
                actor_member_id=member_id,
                now=now,
            )
        else:
            final_status = "declined" if normalized_reply == "decline" else "timed_out"
            cooling_days = decline_cooling_days if normalized_reply == "decline" else timeout_cooling_days
            conn.execute(
                """
                UPDATE match_cases
                SET second_reply_status = ?,
                    status = ?,
                    closed_reason = ?,
                    updated_at = ?
                WHERE case_id = ?
                """,
                (
                    "declined" if normalized_reply == "decline" else "timed_out",
                    final_status,
                    f"second_contact_{normalized_reply}",
                    format_dt(now),
                    case_id,
                ),
            )
            _apply_pair_cooling(
                conn,
                case["pair_key"],
                days=cooling_days,
                reason=f"second_contact_{normalized_reply}",
                now=now,
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type=f"second_reply_{normalized_reply}",
                actor_member_id=member_id,
                now=now,
            )
    else:
        raise ValueError(f"Case {case_id} cannot record a reply from status {case['status']}.")
    conn.commit()
    return get_match_case(conn, case_id)


def close_stale_cases(
    conn,
    *,
    now: datetime | None = None,
    timeout_cooling_days: int = 30,
) -> dict[str, Any]:
    now = current_time(now)
    placeholders = ", ".join(["?"] * len(OPEN_CASE_STATUSES))
    rows = conn.execute(
        f"""
        SELECT *
        FROM match_cases
        WHERE status IN ({placeholders})
          AND expires_at IS NOT NULL
          AND expires_at < ?
        """,
        [*OPEN_CASE_STATUSES, format_dt(now)],
    ).fetchall()
    case_ids: list[str] = []
    for row in rows:
        case = inflate_case(row_to_dict(row))
        conn.execute(
            """
            UPDATE match_cases
            SET status = 'timed_out',
                closed_reason = 'case_expired',
                updated_at = ?
            WHERE case_id = ?
            """,
            (format_dt(now), case["case_id"]),
        )
        _apply_pair_cooling(
            conn,
            case["pair_key"],
            days=timeout_cooling_days,
            reason="case_expired",
            now=now,
        )
        _record_case_event(
            conn,
            case_id=case["case_id"],
            pair_key=case["pair_key"],
            event_type="case_expired",
            now=now,
        )
        case_ids.append(case["case_id"])
    conn.commit()
    return {"closed_count": len(case_ids), "case_ids": case_ids}


def revalidate_member_matches(
    conn,
    member_id: str,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    member = get_pool_member(conn, member_id)
    related_rows = conn.execute(
        """
        SELECT DISTINCT
          CASE
            WHEN owner_member_id = ? THEN candidate_member_id
            ELSE owner_member_id
          END AS related_member_id
        FROM matchmaking_edges
        WHERE owner_member_id = ? OR candidate_member_id = ?
        """,
        (member_id, member_id, member_id),
    ).fetchall()
    refresh_member_ids = {member_id}
    refresh_member_ids.update(
        row["related_member_id"]
        for row in related_rows
        if row["related_member_id"] and row["related_member_id"] != member_id
    )
    placeholders = ", ".join(["?"] * len(refresh_member_ids))
    conn.execute(
        f"""
        UPDATE matchmaking_pool_members
        SET needs_refresh = 1,
            updated_at = ?
        WHERE member_id IN ({placeholders})
        """,
        [format_dt(now), *sorted(refresh_member_ids)],
    )
    conn.execute(
        """
        UPDATE matchmaking_edges
        SET edge_status = 'stale',
            edge_reason = ?,
            updated_at = ?
        WHERE owner_member_id = ? OR candidate_member_id = ?
        """,
        (reason, format_dt(now), member_id, member_id),
    )
    rows = conn.execute(
        """
        SELECT pair_key
        FROM matchmaking_pairs
        WHERE member_low_id = ? OR member_high_id = ?
        """,
        (member_id, member_id),
    ).fetchall()
    pair_keys = [row["pair_key"] for row in rows]
    if pair_keys:
        placeholders = ", ".join(["?"] * len(pair_keys))
        conn.execute(
            f"""
            UPDATE matchmaking_pairs
            SET pair_status = 'needs_revalidation',
                block_reason = ?,
                updated_at = ?
            WHERE pair_key IN ({placeholders})
            """,
            [reason, format_dt(now), *pair_keys],
        )
        case_rows = conn.execute(
            f"""
            SELECT *
            FROM match_cases
            WHERE pair_key IN ({placeholders})
              AND status IN ({", ".join(["?"] * len(OPEN_CASE_STATUSES))})
            """,
            [*pair_keys, *OPEN_CASE_STATUSES],
        ).fetchall()
        for row in case_rows:
            case = inflate_case(row_to_dict(row))
            conn.execute(
                """
                UPDATE match_cases
                SET status = 'closed',
                    closed_reason = ?,
                    updated_at = ?
                WHERE case_id = ?
                """,
                ("member_feedback_requires_revalidation", format_dt(now), case["case_id"]),
            )
            _record_case_event(
                conn,
                case_id=case["case_id"],
                pair_key=case["pair_key"],
                event_type="case_closed_for_revalidation",
                actor_member_id=member_id,
                payload={"reason": reason},
                now=now,
            )
    conn.commit()
    return {
        "member_id": member_id,
        "user_key": member["user_key"],
        "refresh_member_ids": sorted(refresh_member_ids),
        "pair_keys": pair_keys,
        "reason": reason,
    }


def record_feedback(
    conn,
    *,
    member_id: str,
    feedback_kind: str,
    feedback_type: str,
    feedback_text: str | None = None,
    raw_payload: Mapping[str, Any] | None = None,
    persona_patch: Mapping[str, Any] | None = None,
    source_type: str = "explicit",
    evidence_text: str | None = None,
    conversation_ref: str | None = None,
    confidence_score: int | None = None,
    new_status: str | None = None,
    now: datetime | None = None,
    persona_sync_runner: PersonaSyncRunner = sync_persona_memory,
) -> dict[str, Any]:
    now = current_time(now)
    member = get_pool_member(conn, member_id)
    feedback_id = generate_feedback_id()
    conn.execute(
        """
        INSERT INTO matchmaking_feedback_events (
          feedback_id,
          member_id,
          feedback_kind,
          feedback_type,
          feedback_text,
          persona_patch_json,
          raw_payload_json,
          persona_sync_result_json,
          synced_to_persona_memory,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', 0, ?, ?)
        """,
        (
            feedback_id,
            member_id,
            feedback_kind,
            feedback_type,
            feedback_text,
            json_dumps(dict(persona_patch or {})),
            json_dumps(dict(raw_payload or {})),
            format_dt(now),
            format_dt(now),
        ),
    )

    if new_status:
        set_pool_member_status(
            conn,
            member_id,
            status=new_status,
            reason=feedback_type,
            now=now,
        )

    persona_sync_result: dict[str, Any] = {}
    synced_to_persona_memory = False
    if persona_patch:
        persona_sync_result = persona_sync_runner(
            {
                "source": member["source"],
                "user_key": member["user_key"],
                "source_type": source_type,
                "patch": dict(persona_patch),
                "confidence_score": confidence_score,
                "evidence_text": evidence_text or feedback_text,
                "conversation_ref": conversation_ref,
                "sync_profile": True,
            }
        )
        synced_to_persona_memory = True

    conn.execute(
        """
        UPDATE matchmaking_feedback_events
        SET persona_sync_result_json = ?,
            synced_to_persona_memory = ?,
            updated_at = ?
        WHERE feedback_id = ?
        """,
        (
            json_dumps(persona_sync_result),
            bool_to_int(synced_to_persona_memory),
            format_dt(now),
            feedback_id,
        ),
    )

    reason = "member_feedback"
    if feedback_type:
        reason = f"feedback:{feedback_type}"
    revalidate_member_matches(conn, member_id, reason=reason, now=now)
    return inflate_feedback(
        row_to_dict(
            conn.execute(
                "SELECT * FROM matchmaking_feedback_events WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        )
    )
