"""Match case lifecycle: open, contact, reply, feedback, and cleanup."""

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
from chat_system.conversations import get_or_create_conversation, ROLE_AGENT, ROLE_HUMAN, CONV_KIND_DM, LAYOUT_ROLE_ASSISTANT_DM_A, LAYOUT_ROLE_ASSISTANT_DM_B

SearchRunner = Callable[..., dict[str, Any]]
PersonaSyncRunner = Callable[[Mapping[str, Any]], dict[str, Any]]
sync_persona_memory = apply_persona_patch

from .matchmaking_inflate import (
    ACTIVE_MEMBER_STATUS,
    FINAL_CASE_STATUSES,
    OPEN_CASE_STATUSES,
    LedgerMirrorEntry,
    _append_pair_event_to_ledger,
    _flush_ledger_mirror,
    _matchmaking_relation_key_for_members,
    inflate_case,
    inflate_feedback,
    member_is_available,
)
from .pairs import (
    _daily_case_cap,
    _day_bounds,
    _evaluate_pair_state,
    _pair_has_open_case,
    _update_pair_status,
    count_member_cases_today_for_members,
    get_edges_among_members,
    get_pair,
    list_match_case_events,
    list_pairs,
    members_with_open_cases,
)
from .pool_members import get_pool_member, get_pool_members_by_ids, list_active_pool_members

def get_agent_participant_id(conn, case_id: str) -> str | None:
    """获取案例中的agent participant ID，如果没有则返回固定的虚拟agent ID"""
    # 尝试从现有的会话中获取agent ID
    from chat_system.conversations import list_case_conversations
    conversations = list_case_conversations(conn, case_id)
    for conv in conversations or []:
        for member in conv.get("members") or []:
            if member.get("member_role") == ROLE_AGENT:
                return str(member.get("participant_id") or "").strip()

    # 如果没有找到，返回固定的虚拟agent ID
    # TODO: 应该从配置或数据库中获取真实的agent ID
    return "usr-virt-agent-00001"


def _create_assistant_dm_conversations(
    conn,
    *,
    case_id: str,
    pair_key: str,
    member_low: dict[str, Any],
    member_high: dict[str, Any],
    now: datetime | None = None,
) -> None:
    """创建助手私信会话（assistant_dm_a 和 assistant_dm_b）"""
    ts = current_time(now)
    relation_key = _matchmaking_relation_key_for_members(member_low, member_high)

    # 获取或创建 agent participant ID
    agent_participant_id = get_agent_participant_id(conn, case_id)
    if not agent_participant_id:
        return

    # 获取用户的 user_key (participant ID)
    member_low_user_key = str(member_low.get("user_key") or "").strip()
    member_high_user_key = str(member_high.get("user_key") or "").strip()

    if not member_low_user_key or not member_high_user_key:
        # 如果没有 user_key，使用 member_id 作为临时方案
        member_low_user_key = str(member_low.get("member_id") or "").strip()
        member_high_user_key = str(member_high.get("member_id") or "").strip()

    if not member_low_user_key or not member_high_user_key:
        return

    # 创建 assistant_dm_a 会话（member_low 和 agent）
    try:
        get_or_create_conversation(
            conn,
            case_id=case_id,
            relation_key=relation_key,
            channel_key=f"assistant_dm_{member_low_user_key}",
            conversation_kind=CONV_KIND_DM,
            member_specs=[
                {"participant_id": member_low_user_key, "member_role": ROLE_HUMAN, "can_read": True, "can_send": True},
                {"participant_id": agent_participant_id, "member_role": ROLE_AGENT, "can_read": True, "can_send": True},
            ],
            metadata={"layout_role": LAYOUT_ROLE_ASSISTANT_DM_A, "participant_a_id": member_low_user_key},
            now=ts,
        )
    except Exception as e:
        # 创建失败时记录错误，但不中断流程
        print(f"创建 assistant_dm_a 会话失败: {e}")

    # 创建 assistant_dm_b 会话（member_high 和 agent）
    try:
        get_or_create_conversation(
            conn,
            case_id=case_id,
            relation_key=relation_key,
            channel_key=f"assistant_dm_{member_high_user_key}",
            conversation_kind=CONV_KIND_DM,
            member_specs=[
                {"participant_id": member_high_user_key, "member_role": ROLE_HUMAN, "can_read": True, "can_send": True},
                {"participant_id": agent_participant_id, "member_role": ROLE_AGENT, "can_read": True, "can_send": True},
            ],
            metadata={"layout_role": LAYOUT_ROLE_ASSISTANT_DM_B, "participant_b_id": member_high_user_key},
            now=ts,
        )
    except Exception as e:
        # 创建失败时记录错误，但不中断流程
        print(f"创建 assistant_dm_b 会话失败: {e}")


def get_match_case(conn, case_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM match_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    case = inflate_case(row_to_dict(row), conn=conn)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    return case


def _list_match_case_events_for_cases(conn, case_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    normalized = [str(case_id).strip() for case_id in case_ids if str(case_id or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM match_case_events
        WHERE case_id IN ({placeholders})
        ORDER BY occurred_at ASC, event_id ASC
        """,
        tuple(normalized),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {case_id: [] for case_id in normalized}
    for row in rows:
        row_dict = row_to_dict(row)
        case_id = str(row_dict.get("case_id") or "").strip()
        if case_id:
            grouped.setdefault(case_id, []).append(row_dict)
    return grouped


def _list_match_cases_by_ids(
    conn,
    case_ids: Iterable[str],
    *,
    members_by_id: Mapping[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized = [str(case_id).strip() for case_id in case_ids if str(case_id or "").strip()]
    if not normalized:
        return []
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM match_cases
        WHERE case_id IN ({placeholders})
        """,
        tuple(normalized),
    ).fetchall()
    row_map = {
        str(case_row["case_id"]): row_to_dict(case_row)
        for case_row in rows
        if row_to_dict(case_row).get("case_id") is not None
    }
    events_by_case_id = _list_match_case_events_for_cases(conn, normalized)
    out: list[dict[str, Any]] = []
    for case_id in normalized:
        case_row = row_map.get(case_id)
        if not case_row:
            continue
        first_member = None
        second_member = None
        if members_by_id is not None:
            first_member = members_by_id.get(str(case_row.get("first_contact_member_id") or "").strip())
            second_member = members_by_id.get(str(case_row.get("second_contact_member_id") or "").strip())
        inflated = inflate_case(
            case_row,
            conn=None if first_member is not None and second_member is not None else conn,
            event_rows=events_by_case_id.get(case_id, []),
            member_low=first_member,
            member_high=second_member,
        )
        if inflated:
            out.append(inflated)
    return out


def _record_case_event(
    conn,
    *,
    case_id: str,
    pair_key: str,
    event_type: str,
    actor_member_id: str | None = None,
    first_contact_member_id: str | None = None,
    second_contact_member_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
    first_contact_member: Mapping[str, Any] | None = None,
    second_contact_member: Mapping[str, Any] | None = None,
) -> None:
    event_now = current_time(now)
    relation_key = None
    owner_profile_ref = None
    target_profile_ref = None
    if first_contact_member_id and second_contact_member_id:
        member_low = first_contact_member or get_pool_member(conn, str(first_contact_member_id))
        member_high = second_contact_member or get_pool_member(conn, str(second_contact_member_id))
        relation_key = _matchmaking_relation_key_for_members(member_low, member_high)
        owner_profile_ref = pool_member_profile_ref(member_low)
        target_profile_ref = pool_member_profile_ref(member_high)
    event = build_case_aggregate_event(
        event_type=event_type,
        case_id=case_id,
        case_type=CaseType.MATCHMAKING,
        source_service="matchmaking-system",
        actor_type="member" if actor_member_id else "system",
        actor_id=str(actor_member_id or "system"),
        occurred_at=event_now,
        payload={"pair_key": pair_key, **dict(payload or {})},
        entity_ids=bundle_matchmaking_case_entities(
            case_id=case_id,
            pair_key=pair_key,
            first_contact_member_id=first_contact_member_id,
            second_contact_member_id=second_contact_member_id,
        ),
    )
    occurred_str = format_dt(event_now)
    domain_payload = dict(payload or {})
    conn.execute(
        """
        INSERT INTO match_case_events (
          case_id,
          pair_key,
          event_type,
          actor_member_id,
          canonical_event_json,
          payload_json,
          occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            pair_key,
            event_type,
            actor_member_id,
            json_dumps(event.to_dict()),
            json_dumps(domain_payload),
            occurred_str,
        ),
    )
    append_outbox_pending(
        conn,
        event=event,
        source_row_table="match_case_events",
        source_row_id=conn.lastrowid or None,
        created_at_str=occurred_str,
    )
    if relation_key:
        entry: LedgerMirrorEntry = {
            "event": event,
            "relation_key": relation_key,
            "owner_profile_ref": owner_profile_ref,
            "target_profile_ref": target_profile_ref,
            "case_id": case_id,
            "case_type": CaseType.MATCHMAKING.value,
        }
        if ledger_mirror is not None:
            ledger_mirror.append(entry)
        else:
            append_event_to_default_ledger(**entry)


def open_match_cases(
    conn,
    *,
    now: datetime | None = None,
    case_expires_hours: int = 72,
) -> list[dict[str, Any]]:
    now = current_time(now)
    ledger_mirror: list[LedgerMirrorEntry] = []
    created_case_ids: list[str] = []
    pairs = list_pairs(conn, statuses=["eligible"], attach_profile_refs=False)
    if not pairs:
        conn.commit()
        _flush_ledger_mirror(ledger_mirror)
        metric_gauge("matchmaking.cases.opened_batch", 0)
        return []

    member_ids: set[str] = set()
    for pair in pairs:
        member_ids.add(str(pair["member_low_id"]))
        member_ids.add(str(pair["member_high_id"]))
    members_by_id = get_pool_members_by_ids(conn, member_ids)
    edges_by_direction = get_edges_among_members(conn, member_ids)
    open_case_member_ids = members_with_open_cases(conn, member_ids)
    cases_today_by_member = count_member_cases_today_for_members(conn, member_ids, now=now)

    for pair in pairs:
        pair_key = pair["pair_key"]
        member_low = members_by_id.get(str(pair["member_low_id"]))
        member_high = members_by_id.get(str(pair["member_high_id"]))
        if member_low is None:
            raise ValueError(f"Unknown pool member: {pair['member_low_id']}")
        if member_high is None:
            raise ValueError(f"Unknown pool member: {pair['member_high_id']}")
        if not member_is_available(member_low) or not member_is_available(member_high):
            _update_pair_status(
                conn,
                pair_key,
                pair_status="blocked",
                block_reason="member_not_active"
                if member_low["status"] != ACTIVE_MEMBER_STATUS or member_high["status"] != ACTIVE_MEMBER_STATUS
                else "member_not_searching",
                now=now,
                ledger_mirror=ledger_mirror,
            )
            continue

        low_to_high = edges_by_direction.get((member_low["member_id"], member_high["member_id"]))
        high_to_low = edges_by_direction.get((member_high["member_id"], member_low["member_id"]))
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
                ledger_mirror=ledger_mirror,
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
                ledger_mirror=ledger_mirror,
            )
            continue

        if (
            member_low["member_id"] in open_case_member_ids
            or member_high["member_id"] in open_case_member_ids
        ):
            continue
        if cases_today_by_member.get(member_low["member_id"], 0) >= _daily_case_cap(member_low):
            continue
        if cases_today_by_member.get(member_high["member_id"], 0) >= _daily_case_cap(member_high):
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
              case_type,
              status,
              first_contact_member_id,
              second_contact_member_id,
              expires_at,
              created_at,
              updated_at
            ) VALUES (?, ?, 'system', ?, 'pending_first_contact', ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                pair_key,
                CaseType.MATCHMAKING.value,
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
            first_contact_member_id=first_contact_member_id,
            second_contact_member_id=second_contact_member_id,
            payload={"initiator_type": "system"},
            now=now,
            ledger_mirror=ledger_mirror,
            first_contact_member=member_low,
            second_contact_member=member_high,
        )
        _append_pair_event_to_ledger(
            pair_event_type="pair_case_opened",
            member_low=member_low,
            member_high=member_high,
            pair_key=pair_key,
            now=now,
            actor_type="system",
            actor_id="system",
            payload={"case_id": case_id, "case_type": CaseType.MATCHMAKING.value},
            ledger_mirror=ledger_mirror,
        )
        funnel_stage(
            system="matchmaking",
            stage=MATCHMAKING_FUNNEL_CASE,
            case_id=case_id,
            pair_key=pair_key,
        )
        # 创建助手私信会话
        _create_assistant_dm_conversations(
            conn,
            case_id=case_id,
            pair_key=pair_key,
            member_low=member_low,
            member_high=member_high,
            now=now,
        )
        created_case_ids.append(case_id)
    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
    metric_gauge("matchmaking.cases.opened_batch", len(created_case_ids))
    return _list_match_cases_by_ids(conn, created_case_ids, members_by_id=members_by_id)


def dispatch_case_contact(
    conn,
    case_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    ledger_mirror: list[LedgerMirrorEntry] = []
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
            first_contact_member_id=case["first_contact_member_id"],
            second_contact_member_id=case["second_contact_member_id"],
            now=now,
            ledger_mirror=ledger_mirror,
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
            first_contact_member_id=case["first_contact_member_id"],
            second_contact_member_id=case["second_contact_member_id"],
            now=now,
            ledger_mirror=ledger_mirror,
        )
    else:
        raise ValueError(f"Case {case_id} cannot dispatch outreach from status {case['status']}.")
    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
    return get_match_case(conn, case_id)


def _apply_pair_cooling(
    conn,
    pair_key: str,
    *,
    days: int,
    reason: str,
    now: datetime,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
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
    pair = get_pair(conn, pair_key)
    if pair:
        _append_pair_event_to_ledger(
            pair_event_type="pair_cooling",
            member_low=get_pool_member(conn, pair["member_low_id"]),
            member_high=get_pool_member(conn, pair["member_high_id"]),
            pair_key=pair_key,
            now=now,
            actor_type="system",
            actor_id="system",
            payload={"block_reason": reason, "cooling_until": format_dt(cooling_until)},
            ledger_mirror=ledger_mirror,
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
    ledger_mirror: list[LedgerMirrorEntry] = []
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
                first_contact_member_id=case["first_contact_member_id"],
                second_contact_member_id=case["second_contact_member_id"],
                now=now,
            )
            funnel_stage(
                system="matchmaking",
                stage=MATCHMAKING_FUNNEL_FIRST_ACCEPT,
                case_id=case_id,
                pair_key=case["pair_key"],
                member_id=member_id,
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
                ledger_mirror=ledger_mirror,
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type=f"first_reply_{normalized_reply}",
                actor_member_id=member_id,
                first_contact_member_id=case["first_contact_member_id"],
                second_contact_member_id=case["second_contact_member_id"],
                now=now,
                ledger_mirror=ledger_mirror,
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
            pair = get_pair(conn, case["pair_key"])
            if pair:
                _append_pair_event_to_ledger(
                    pair_event_type="pair_mutual_accept",
                    member_low=get_pool_member(conn, pair["member_low_id"]),
                    member_high=get_pool_member(conn, pair["member_high_id"]),
                    pair_key=case["pair_key"],
                    now=now,
                    actor_type="member",
                    actor_id=str(member_id),
                    payload={"case_id": case_id},
                    ledger_mirror=ledger_mirror,
                )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type="second_reply_accepted",
                actor_member_id=member_id,
                first_contact_member_id=case["first_contact_member_id"],
                second_contact_member_id=case["second_contact_member_id"],
                now=now,
                ledger_mirror=ledger_mirror,
            )
            funnel_stage(
                system="matchmaking",
                stage=MATCHMAKING_FUNNEL_SECOND_ACCEPT,
                case_id=case_id,
                pair_key=case["pair_key"],
                member_id=member_id,
            )
            funnel_stage(
                system="matchmaking",
                stage=MATCHMAKING_FUNNEL_MUTUAL_ACCEPT,
                case_id=case_id,
                pair_key=case["pair_key"],
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
                ledger_mirror=ledger_mirror,
            )
            _record_case_event(
                conn,
                case_id=case_id,
                pair_key=case["pair_key"],
                event_type=f"second_reply_{normalized_reply}",
                actor_member_id=member_id,
                first_contact_member_id=case["first_contact_member_id"],
                second_contact_member_id=case["second_contact_member_id"],
                now=now,
                ledger_mirror=ledger_mirror,
            )
    else:
        raise ValueError(f"Case {case_id} cannot record a reply from status {case['status']}.")
    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
    return get_match_case(conn, case_id)


def close_stale_cases(
    conn,
    *,
    now: datetime | None = None,
    timeout_cooling_days: int = 30,
) -> dict[str, Any]:
    now = current_time(now)
    ledger_mirror: list[LedgerMirrorEntry] = []
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
            ledger_mirror=ledger_mirror,
        )
        _record_case_event(
            conn,
            case_id=case["case_id"],
            pair_key=case["pair_key"],
            event_type="case_expired",
            first_contact_member_id=case["first_contact_member_id"],
            second_contact_member_id=case["second_contact_member_id"],
            now=now,
            ledger_mirror=ledger_mirror,
        )
        case_ids.append(case["case_id"])
    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
    return {"closed_count": len(case_ids), "case_ids": case_ids}


def revalidate_member_matches(
    conn,
    member_id: str,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    ledger_mirror: list[LedgerMirrorEntry] = []
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
                first_contact_member_id=case["first_contact_member_id"],
                second_contact_member_id=case["second_contact_member_id"],
                payload={"reason": reason},
                now=now,
                ledger_mirror=ledger_mirror,
            )
    conn.commit()
    _flush_ledger_mirror(ledger_mirror)
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
    feedback_event = build_canonical_event(
        event_type=f"feedback_{feedback_type or feedback_kind}",
        aggregate_type="member_feedback",
        aggregate_id=feedback_id,
        actor_type="member",
        actor_id=member_id,
        source_service="matchmaking-system",
        correlation_id=correlation_member_feedback(feedback_id),
        idempotency_key=idempotency_feedback(feedback_id),
        occurred_at=now,
        payload={
            "member_id": member_id,
            "feedback_kind": feedback_kind,
            "feedback_type": feedback_type,
            "feedback_text": feedback_text,
            **dict(raw_payload or {}),
        },
        entity_ids={"pool_member": entity_id_pool_member(member_id)},
    )
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
            json_dumps(merge_payload_with_event(raw_payload, feedback_event)),
            format_dt(now),
            format_dt(now),
        ),
    )

    if new_status:
        from .pool_members import set_pool_member_status

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
