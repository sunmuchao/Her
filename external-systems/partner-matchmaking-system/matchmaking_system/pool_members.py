"""Matchmaking pool member CRUD and search refresh."""

from __future__ import annotations

import json
import os
import random
import time
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

from .matchmaking_inflate import ACTIVE_MEMBER_STATUS, inflate_pool_member, member_is_available
from .matchmaking_search import run_partner_search

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


def find_pool_members_by_source_profiles(
    conn,
    source: str,
    profile_ids: Iterable[int],
) -> dict[int, dict[str, Any]]:
    normalized = [int(item) for item in profile_ids]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM matchmaking_pool_members
        WHERE source = ? AND self_id IN ({placeholders})
        """,
        [source, *normalized],
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        member = inflate_pool_member(row_to_dict(row))
        if member and member.get("self_id") is not None:
            out[int(member["self_id"])] = member
    return out


def get_pool_members_by_ids(conn, member_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item).strip() for item in member_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM matchmaking_pool_members
        WHERE member_id IN ({placeholders})
        """,
        normalized,
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        member = inflate_pool_member(row_to_dict(row))
        if member and member.get("member_id"):
            out[str(member["member_id"])] = member
    return out


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
        out = get_pool_member(conn, member_id)
        return out

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
    out = get_pool_member(conn, member_id)
    return out


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
        from .matchmaking_cases import revalidate_member_matches

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
        "moderation_dsn": os.environ.get("HER_CHAT_MODERATION_DB") or os.environ.get("PARTNER_CHAT_DB"),
    }


def _is_deadlock_error(exc: BaseException) -> bool:
    text = str(exc)
    return "1213" in text or "Deadlock" in text


def _refresh_pool_member_once(
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

    from .pairs import get_edges_for_owner_candidates

    response = search_runner(**load_pool_member_search_args(member))
    results = list(response.get("results") or [])
    active_candidate_member_ids: list[str] = []
    synced_count = 0

    candidate_profile_ids = [
        int(result.get("id"))
        for result in results
        if result.get("id") is not None
    ]
    candidates_by_profile_id = find_pool_members_by_source_profiles(
        conn,
        member["source"],
        candidate_profile_ids,
    )
    eligible_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for result in results:
        candidate_id = result.get("id")
        if candidate_id is None:
            continue
        candidate_member = candidates_by_profile_id.get(int(candidate_id))
        if not candidate_member or candidate_member["member_id"] == member_id:
            continue
        if candidate_member["status"] != ACTIVE_MEMBER_STATUS or not candidate_member["is_still_searching"]:
            continue
        eligible_candidates.append((result, candidate_member))

    edges_by_candidate_id = get_edges_for_owner_candidates(
        conn,
        member_id,
        [candidate["member_id"] for _, candidate in eligible_candidates],
    )

    for result, candidate_member in eligible_candidates:
        active_candidate_member_ids.append(candidate_member["member_id"])
        existing = edges_by_candidate_id.get(candidate_member["member_id"])
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
    funnel_stage(
        system="matchmaking",
        stage=MATCHMAKING_FUNNEL_MEMBER,
        member_id=member_id,
        result_count=len(results),
        edge_count=synced_count,
    )
    if synced_count:
        funnel_stage(
            system="matchmaking",
            stage=MATCHMAKING_FUNNEL_EDGE,
            member_id=member_id,
            edge_count=synced_count,
            result_count=len(results),
        )
    metric_gauge("matchmaking.pool_scan.result_count", len(results), member_id=member_id)
    metric_gauge("matchmaking.pool_scan.edge_count", synced_count, member_id=member_id)
    return {
        "member_id": member_id,
        "user_key": member["user_key"],
        "skipped": False,
        "result_count": len(results),
        "edge_count": synced_count,
    }


def refresh_pool_member(
    conn,
    member_id: str,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
) -> dict[str, Any]:
    last_error: BaseException | None = None
    for attempt in range(3):
        try:
            return _refresh_pool_member_once(
                conn,
                member_id,
                now=now,
                search_runner=search_runner,
            )
        except Exception as exc:
            last_error = exc
            if _is_deadlock_error(exc) and attempt < 2:
                try:
                    conn.rollback()
                except Exception:
                    pass
                time.sleep(0.05 * (attempt + 1) + random.random() * 0.05)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"refresh_pool_member failed for {member_id}")


def refresh_active_pool(
    conn,
    *,
    now: datetime | None = None,
    search_runner: SearchRunner = run_partner_search,
    member_ids: Iterable[str] | None = None,
    max_workers: int | None = None,
) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from her_env import env_int
    from her_parallel_db import worker_connect_factory

    from .storage import connect_db

    now = current_time(now)
    due_members = list_due_pool_members(conn, now=now, member_ids=member_ids)
    if not due_members:
        return []

    worker_count = (
        int(max_workers)
        if max_workers is not None
        else env_int("MATCHMAKING_POOL_REFRESH_MAX_WORKERS", 1)
    )
    worker_count = max(1, worker_count)
    connect_worker = worker_connect_factory(conn, connect_db)

    def _refresh_one(member: Mapping[str, Any]) -> dict[str, Any]:
        mid = str(member["member_id"])
        worker_conn = connect_worker()
        try:
            return refresh_pool_member(
                worker_conn,
                mid,
                now=now,
                search_runner=search_runner,
            )
        finally:
            worker_conn.close()

    summaries: list[dict[str, Any]] = []
    if worker_count <= 1 or len(due_members) <= 1:
        for member in due_members:
            mid = member["member_id"]
            try:
                summaries.append(
                    refresh_pool_member(
                        conn,
                        mid,
                        now=now,
                        search_runner=search_runner,
                    )
                )
            except Exception as exc:
                alert_signal(
                    "matchmaking.refresh_failed",
                    str(exc),
                    severity="error",
                    member_id=mid,
                    error_type=type(exc).__name__,
                )
                summaries.append(
                    {
                        "member_id": mid,
                        "user_key": member.get("user_key"),
                        "skipped": True,
                        "reason": "refresh_failed",
                        "error": str(exc),
                        "edge_count": 0,
                        "result_count": 0,
                    }
                )
        return summaries

    summaries_by_member_id: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(worker_count, len(due_members))) as executor:
        future_to_member = {
            executor.submit(_refresh_one, member): member for member in due_members
        }
        for future in as_completed(future_to_member):
            member = future_to_member[future]
            mid = str(member["member_id"])
            try:
                summaries_by_member_id[mid] = future.result()
            except Exception as exc:
                alert_signal(
                    "matchmaking.refresh_failed",
                    str(exc),
                    severity="error",
                    member_id=mid,
                    error_type=type(exc).__name__,
                )
                summaries_by_member_id[mid] = {
                    "member_id": mid,
                    "user_key": member.get("user_key"),
                    "skipped": True,
                    "reason": "refresh_failed",
                    "error": str(exc),
                    "edge_count": 0,
                    "result_count": 0,
                }
    _retry_failed_pool_refreshes(
        conn,
        due_members,
        summaries_by_member_id,
        now=now,
        search_runner=search_runner,
    )
    return [summaries_by_member_id[str(member["member_id"])] for member in due_members]


def _summary_needs_deadlock_retry(summary: Mapping[str, Any]) -> bool:
    if not summary.get("skipped") or summary.get("reason") != "refresh_failed":
        return False
    return _is_deadlock_error(Exception(str(summary.get("error") or "")))


def _retry_failed_pool_refreshes(
    conn,
    due_members: list[Mapping[str, Any]],
    summaries_by_member_id: dict[str, dict[str, Any]],
    *,
    now: datetime,
    search_runner: SearchRunner,
) -> None:
    for member in due_members:
        mid = str(member["member_id"])
        summary = summaries_by_member_id.get(mid)
        if summary is None or not _summary_needs_deadlock_retry(summary):
            continue
        try:
            summaries_by_member_id[mid] = refresh_pool_member(
                conn,
                mid,
                now=now,
                search_runner=search_runner,
            )
        except Exception as exc:
            alert_signal(
                "matchmaking.refresh_failed",
                str(exc),
                severity="error",
                member_id=mid,
                error_type=type(exc).__name__,
            )
            summaries_by_member_id[mid] = {
                "member_id": mid,
                "user_key": member.get("user_key"),
                "skipped": True,
                "reason": "refresh_failed",
                "error": str(exc),
                "edge_count": 0,
                "result_count": 0,
            }
