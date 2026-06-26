"""Unified relation/case/event ledger built from canonical cross-system events."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from match_domain import (
    AGGREGATE_CASE,
    MatchEvent,
    ProfileRef,
    canonical_case_status_value,
    match_event_from_mapping,
    profile_ref_to_dict,
    reduce_case_ledger,
    reduce_relation_ledger,
)

from .storage import json_dumps, json_loads, row_to_dict


OPEN_LEDGER_CASE_STATUSES = frozenset(
    {
        "pending_contact",
        "pending_outreach",
        "awaiting_reply",
        "accepted",
    }
)


def relation_id_from_key(relation_key: str) -> str:
    digest = hashlib.sha1(str(relation_key).encode("utf-8")).hexdigest()[:20]
    return f"rel-{digest}"


def _bounded_aggregate_id(value: str | None, *, limit: int = 191) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) <= limit:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    prefix_limit = max(limit - len(digest) - 1, 1)
    return f"{raw[:prefix_limit]}:{digest}"


def _event_payload(event: MatchEvent) -> dict[str, Any]:
    return dict(event.payload or {})


def _normalize_profile_ref(value: ProfileRef | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, ProfileRef):
        return profile_ref_to_dict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("profile ref must be ProfileRef or mapping")


def _upsert_relation_shell(
    conn,
    *,
    relation_id: str,
    relation_key: str,
    owner_profile_ref: dict[str, Any] | None,
    target_profile_ref: dict[str, Any] | None,
    occurred_at: str,
) -> None:
    existing = conn.execute(
        "SELECT * FROM match_relations WHERE relation_id = ?",
        (relation_id,),
    ).fetchone()
    if existing:
        updates: list[str] = ["updated_at = ?", "last_event_at = ?"]
        params: list[Any] = [occurred_at, occurred_at]
        if owner_profile_ref:
            updates.append("owner_profile_ref_json = ?")
            params.append(json_dumps(owner_profile_ref))
        if target_profile_ref:
            updates.append("target_profile_ref_json = ?")
            params.append(json_dumps(target_profile_ref))
        params.append(relation_id)
        conn.execute(
            f"UPDATE match_relations SET {', '.join(updates)} WHERE relation_id = ?",
            params,
        )
        return
    conn.execute(
        """
        INSERT INTO match_relations (
          relation_id,
          relation_key,
          owner_profile_ref_json,
          target_profile_ref_json,
          relation_status,
          current_phase,
          active_case_id,
          active_case_type,
          active_case_status,
          latest_chat_thread_id,
          last_chat_message_at,
          source_summary_json,
          last_event_type,
          last_event_at,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, NULL, ?, ?, ?)
        """,
        (
            relation_id,
            relation_key,
            json_dumps(owner_profile_ref) if owner_profile_ref else None,
            json_dumps(target_profile_ref) if target_profile_ref else None,
            "new",
            "new",
            json_dumps({}),
            occurred_at,
            occurred_at,
            occurred_at,
        ),
    )


def _derive_case_identity(event: MatchEvent, explicit_case_id: str | None, explicit_case_type: str | None) -> tuple[str | None, str | None]:
    payload = _event_payload(event)
    case_id = str(explicit_case_id or payload.get("case_id") or "").strip() or None
    case_type = str(explicit_case_type or payload.get("case_type") or "").strip() or None
    if event.aggregate_type == AGGREGATE_CASE and case_id is None:
        case_id = str(event.aggregate_id)
    return case_id, case_type


def _load_relation_events(conn, relation_id: str) -> list[MatchEvent]:
    rows = conn.execute(
        """
        SELECT canonical_event_json
        FROM match_relation_events
        WHERE relation_id = ?
        ORDER BY occurred_at ASC, ledger_event_id ASC
        """,
        (relation_id,),
    ).fetchall()
    events: list[MatchEvent] = []
    for row in rows:
        canon = json_loads(row.get("canonical_event_json"), {})
        if isinstance(canon, Mapping):
            events.append(match_event_from_mapping(canon))
    return events


def _load_case_events(conn, case_id: str) -> list[MatchEvent]:
    rows = conn.execute(
        """
        SELECT canonical_event_json
        FROM match_relation_events
        WHERE case_id = ?
        ORDER BY occurred_at ASC, ledger_event_id ASC
        """,
        (case_id,),
    ).fetchall()
    events: list[MatchEvent] = []
    for row in rows:
        canon = json_loads(row.get("canonical_event_json"), {})
        if isinstance(canon, Mapping):
            events.append(match_event_from_mapping(canon))
    return events


def _upsert_case_projection(
    conn,
    *,
    relation_id: str,
    event: MatchEvent,
    case_id: str,
    case_type: str,
    owner_service: str,
) -> None:
    occurred_at = str(event.occurred_at.isoformat(sep=" "))
    existing = row_to_dict(
        conn.execute("SELECT * FROM match_relation_cases WHERE case_id = ?", (case_id,)).fetchone()
    )
    case_events = _load_case_events(conn, case_id)
    reduced = reduce_case_ledger(case_events)
    close_reason = None
    payload = _event_payload(event)
    if event.event_type == "case_closed":
        close_reason = payload.get("close_reason")
    elif event.event_type.startswith("case_closed_"):
        close_reason = event.event_type.removeprefix("case_closed_")
    closed_at = occurred_at if reduced.status.value == "closed" else None
    opened_at = existing.get("opened_at") if existing else occurred_at
    metadata = {
        "owner_service": owner_service,
        "latest_payload": payload,
    }
    if existing:
        conn.execute(
            """
            UPDATE match_relation_cases
            SET case_status = ?,
                close_reason = COALESCE(?, close_reason),
                linked_aggregate_type = ?,
                linked_aggregate_id = ?,
                latest_event_type = ?,
                closed_at = COALESCE(?, closed_at),
                last_event_at = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (
                reduced.status.value,
                close_reason,
                event.aggregate_type,
                _bounded_aggregate_id(event.aggregate_id),
                event.event_type,
                closed_at,
                occurred_at,
                json_dumps(metadata),
                occurred_at,
                case_id,
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO match_relation_cases (
          case_id,
          relation_id,
          case_type,
          owner_service,
          case_status,
          close_reason,
          linked_aggregate_type,
          linked_aggregate_id,
          latest_event_type,
          opened_at,
          closed_at,
          last_event_at,
          metadata_json,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            relation_id,
            case_type,
            owner_service,
            reduced.status.value,
            close_reason,
            event.aggregate_type,
            _bounded_aggregate_id(event.aggregate_id),
            event.event_type,
            opened_at,
            closed_at,
            occurred_at,
            json_dumps(metadata),
            occurred_at,
            occurred_at,
        ),
    )


def _project_relation_current_phase(
    *,
    relation_status: str,
    active_case: dict[str, Any] | None,
    latest_chat_thread_id: str | None,
    last_chat_message_at: str | None,
) -> str:
    if last_chat_message_at:
        return "chat_active"
    if latest_chat_thread_id:
        return "chat_opened"
    if active_case:
        return "case_active"
    return relation_status


def _refresh_relation_projection(
    conn,
    *,
    relation_id: str,
    relation_key: str,
    event: MatchEvent,
    owner_profile_ref: dict[str, Any] | None,
    target_profile_ref: dict[str, Any] | None,
) -> None:
    relation_events = _load_relation_events(conn, relation_id)
    reduced = reduce_relation_ledger(relation_events)
    active_case = None
    if reduced.active_match_case_id:
        active_case = row_to_dict(
            conn.execute(
                "SELECT * FROM match_relation_cases WHERE case_id = ?",
                (reduced.active_match_case_id,),
            ).fetchone()
        )
    if active_case is None:
        active_case = row_to_dict(
            conn.execute(
                """
                SELECT *
                FROM match_relation_cases
                WHERE relation_id = ?
                  AND case_status IN ('pending_contact', 'pending_outreach', 'awaiting_reply', 'accepted')
                ORDER BY last_event_at DESC, case_id DESC
                LIMIT 1
                """,
                (relation_id,),
            ).fetchone()
        )
    existing = row_to_dict(conn.execute("SELECT * FROM match_relations WHERE relation_id = ?", (relation_id,)).fetchone())
    payload = _event_payload(event)
    latest_chat_thread_id = existing.get("latest_chat_thread_id") if existing else None
    last_chat_message_at = existing.get("last_chat_message_at") if existing else None
    if event.event_type == "chat.thread.opened":
        latest_chat_thread_id = str(payload.get("thread_id") or event.aggregate_id)
    if event.event_type == "chat.message.created":
        last_chat_message_at = event.occurred_at.isoformat(sep=" ")
        latest_chat_thread_id = str(payload.get("thread_id") or event.aggregate_id)
    source_summary = json_loads((existing or {}).get("source_summary_json"), {})
    source_summary.update(
        {
            "latest_source_service": event.source_service,
            "latest_aggregate_type": event.aggregate_type,
            "latest_aggregate_id": event.aggregate_id,
        }
    )
    conn.execute(
        """
        UPDATE match_relations
        SET owner_profile_ref_json = COALESCE(?, owner_profile_ref_json),
            target_profile_ref_json = COALESCE(?, target_profile_ref_json),
            relation_status = ?,
            current_phase = ?,
            active_case_id = ?,
            active_case_type = ?,
            active_case_status = ?,
            latest_chat_thread_id = ?,
            last_chat_message_at = ?,
            source_summary_json = ?,
            last_event_type = ?,
            last_event_at = ?,
            updated_at = ?
        WHERE relation_id = ?
        """,
        (
            json_dumps(owner_profile_ref) if owner_profile_ref else None,
            json_dumps(target_profile_ref) if target_profile_ref else None,
            reduced.status.value,
            _project_relation_current_phase(
                relation_status=reduced.status.value,
                active_case=active_case,
                latest_chat_thread_id=latest_chat_thread_id,
                last_chat_message_at=last_chat_message_at,
            ),
            None if active_case is None else active_case.get("case_id"),
            None if active_case is None else active_case.get("case_type"),
            None if active_case is None else active_case.get("case_status"),
            latest_chat_thread_id,
            last_chat_message_at,
            json_dumps(source_summary),
            event.event_type,
            event.occurred_at.isoformat(sep=" "),
            event.occurred_at.isoformat(sep=" "),
            relation_id,
        ),
    )


def append_event(
    conn,
    *,
    event: MatchEvent,
    relation_key: str,
    owner_profile_ref: ProfileRef | Mapping[str, Any] | None = None,
    target_profile_ref: ProfileRef | Mapping[str, Any] | None = None,
    case_id: str | None = None,
    case_type: str | None = None,
) -> dict[str, Any]:
    relation_key = str(relation_key or "").strip()
    if not relation_key:
        raise ValueError("relation_key is required")
    relation_id = relation_id_from_key(relation_key)
    owner_ref_dict = _normalize_profile_ref(owner_profile_ref)
    target_ref_dict = _normalize_profile_ref(target_profile_ref)
    occurred_at = event.occurred_at.isoformat(sep=" ")
    _upsert_relation_shell(
        conn,
        relation_id=relation_id,
        relation_key=relation_key,
        owner_profile_ref=owner_ref_dict,
        target_profile_ref=target_ref_dict,
        occurred_at=occurred_at,
    )
    derived_case_id, derived_case_type = _derive_case_identity(event, case_id, case_type)
    conn.execute(
        """
        INSERT IGNORE INTO match_relation_events (
          relation_id,
          canonical_event_id,
          aggregate_type,
          aggregate_id,
          case_id,
          case_type,
          event_type,
          source_service,
          actor_type,
          actor_id,
          canonical_event_json,
          event_payload_json,
          occurred_at,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relation_id,
            event.event_id,
            event.aggregate_type,
            event.aggregate_id,
            derived_case_id,
            derived_case_type,
            event.event_type,
            event.source_service,
            event.actor_type,
            event.actor_id,
            json_dumps(event.to_dict()),
            json_dumps(_event_payload(event)),
            occurred_at,
            occurred_at,
        ),
    )
    if conn.execute(
        "SELECT * FROM match_relation_events WHERE canonical_event_id = ?",
        (event.event_id,),
    ).fetchone() is None:
        conn.commit()
        return get_relation(conn, relation_id)
    if derived_case_id and derived_case_type:
        _upsert_case_projection(
            conn,
            relation_id=relation_id,
            event=event,
            case_id=derived_case_id,
            case_type=derived_case_type,
            owner_service=event.source_service,
        )
    _refresh_relation_projection(
        conn,
        relation_id=relation_id,
        relation_key=relation_key,
        event=event,
        owner_profile_ref=owner_ref_dict,
        target_profile_ref=target_ref_dict,
    )
    conn.commit()
    return get_relation(conn, relation_id)


def get_relation(conn, relation_id: str) -> dict[str, Any] | None:
    row = row_to_dict(conn.execute("SELECT * FROM match_relations WHERE relation_id = ?", (relation_id,)).fetchone())
    if not row:
        return None
    row["owner_profile_ref"] = json_loads(row.pop("owner_profile_ref_json"), None)
    row["target_profile_ref"] = json_loads(row.pop("target_profile_ref_json"), None)
    row["source_summary"] = json_loads(row.pop("source_summary_json"), {})
    row["events"] = list_events_for_relation(conn, relation_id)
    row["cases"] = list_cases_for_relation(conn, relation_id)
    if not row["cases"]:
        row["cases"] = _synthesized_cases_from_events(row["events"])
    if not row.get("active_case_id"):
        active_case = next(
            (
                case
                for case in row["cases"]
                if str(case.get("case_status") or "") in OPEN_LEDGER_CASE_STATUSES
            ),
            None,
        )
        if active_case:
            row["active_case_id"] = active_case.get("case_id")
            row["active_case_type"] = active_case.get("case_type")
            row["active_case_status"] = active_case.get("case_status")
            if not row.get("current_phase") or row.get("current_phase") == row.get("relation_status"):
                row["current_phase"] = "case_active"
    return row


def get_relation_by_key(conn, relation_key: str) -> dict[str, Any] | None:
    relation_id = relation_id_from_key(relation_key)
    return get_relation(conn, relation_id)


def list_relations(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT relation_id FROM match_relations ORDER BY last_event_at DESC, relation_id DESC",
        (),
    ).fetchall()
    return [item for item in (get_relation(conn, str(row["relation_id"])) for row in rows) if item]


def list_relations_for_profile_refs(
    conn,
    profile_refs: list[str],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    refs = [str(ref).strip() for ref in profile_refs if str(ref).strip()]
    if not refs:
        return []
    safe_limit = max(int(limit), 1)
    placeholders = ", ".join(["?"] * len(refs))
    rows = conn.execute(
        f"""
        SELECT relation_id
        FROM match_relations
        WHERE owner_profile_ref_json IN ({placeholders})
           OR target_profile_ref_json IN ({placeholders})
        ORDER BY last_event_at DESC, relation_id DESC
        LIMIT ?
        """,
        (*refs, *refs, safe_limit),
    ).fetchall()
    return [item for item in (get_relation(conn, str(row["relation_id"])) for row in rows) if item]


def build_relation_dashboard(conn) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT relation_status, current_phase, COUNT(*) AS relation_count
        FROM match_relations
        GROUP BY relation_status, current_phase
        ORDER BY relation_status ASC, current_phase ASC
        """
    ).fetchall()
    by_status: dict[str, int] = {}
    by_phase: dict[str, int] = {}
    matrix: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        relation_status = str(row["relation_status"] or "")
        current_phase = str(row["current_phase"] or "")
        count = int(row["relation_count"] or 0)
        total += count
        by_status[relation_status] = by_status.get(relation_status, 0) + count
        by_phase[current_phase] = by_phase.get(current_phase, 0) + count
        matrix.append(
            {
                "relation_status": relation_status,
                "current_phase": current_phase,
                "relation_count": count,
            }
        )
    case_rows = conn.execute(
        """
        SELECT case_type, case_status, COUNT(*) AS case_count
        FROM match_relation_cases
        GROUP BY case_type, case_status
        ORDER BY case_type ASC, case_status ASC
        """
    ).fetchall()
    case_matrix = [
        {
            "case_type": str(row["case_type"] or ""),
            "case_status": str(row["case_status"] or ""),
            "case_count": int(row["case_count"] or 0),
        }
        for row in case_rows
    ]
    return {
        "relation_total": total,
        "by_status": by_status,
        "by_phase": by_phase,
        "status_phase_matrix": matrix,
        "case_status_matrix": case_matrix,
    }


def build_cross_system_funnel_dashboard(conn) -> dict[str, Any]:
    relation_rows = conn.execute(
        """
        SELECT relation_status, current_phase, COUNT(*) AS relation_count
        FROM match_relations
        GROUP BY relation_status, current_phase
        ORDER BY relation_status ASC, current_phase ASC
        """
    ).fetchall()
    relation_stages = {
        "relation_total": 0,
        "relationship_established": 0,
        "case_active": 0,
        "chat_opened": 0,
        "chat_active": 0,
        "cooling": 0,
        "closed": 0,
    }
    relation_stage_matrix: list[dict[str, Any]] = []
    for row in relation_rows:
        relation_status = str(row["relation_status"] or "")
        current_phase = str(row["current_phase"] or "")
        count = int(row["relation_count"] or 0)
        relation_stages["relation_total"] += count
        if relation_status in {"recommended", "saved", "direct_greet_started", "proxy_intro_active", "matched"}:
            relation_stages["relationship_established"] += count
        if current_phase == "case_active":
            relation_stages["case_active"] += count
        if current_phase == "chat_opened":
            relation_stages["chat_opened"] += count
        if current_phase == "chat_active":
            relation_stages["chat_active"] += count
        if relation_status == "cooling":
            relation_stages["cooling"] += count
        if relation_status == "closed":
            relation_stages["closed"] += count
        relation_stage_matrix.append(
            {
                "relation_status": relation_status,
                "current_phase": current_phase,
                "relation_count": count,
            }
        )

    case_rows = conn.execute(
        """
        SELECT case_type, case_status, COUNT(*) AS case_count
        FROM match_relation_cases
        GROUP BY case_type, case_status
        ORDER BY case_type ASC, case_status ASC
        """
    ).fetchall()
    case_stages = {
        "case_total": 0,
        "proxy_intro_cases": 0,
        "matchmaking_cases": 0,
        "pending_contact": 0,
        "awaiting_reply": 0,
        "accepted": 0,
        "declined": 0,
        "timed_out": 0,
        "closed": 0,
    }
    case_stage_matrix: list[dict[str, Any]] = []
    for row in case_rows:
        case_type = str(row["case_type"] or "")
        case_status = str(row["case_status"] or "")
        count = int(row["case_count"] or 0)
        case_stages["case_total"] += count
        if case_type == "proxy_intro":
            case_stages["proxy_intro_cases"] += count
        if case_type == "matchmaking":
            case_stages["matchmaking_cases"] += count
        if case_status in case_stages:
            case_stages[case_status] += count
        case_stage_matrix.append(
            {
                "case_type": case_type,
                "case_status": case_status,
                "case_count": count,
            }
        )

    return {
        "relation_stages": relation_stages,
        "case_stages": case_stages,
        "relation_stage_matrix": relation_stage_matrix,
        "case_stage_matrix": case_stage_matrix,
    }


def list_cases_for_relation(conn, relation_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_relation_cases
        WHERE relation_id = ?
        ORDER BY last_event_at DESC, case_id DESC
        """,
        (relation_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        if not item:
            continue
        item["metadata"] = json_loads(item.pop("metadata_json"), {})
        out.append(item)
    return out


def list_events_for_relation(conn, relation_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_relation_events
        WHERE relation_id = ?
        ORDER BY occurred_at ASC, ledger_event_id ASC
        """,
        (relation_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        if not item:
            continue
        item["canonical_event"] = json_loads(item.pop("canonical_event_json"), {})
        item["event_payload"] = json_loads(item.pop("event_payload_json"), {})
        out.append(item)
    return out


def _synthesized_cases_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[MatchEvent]] = {}
    case_types: dict[str, str | None] = {}
    last_event_types: dict[str, str | None] = {}
    last_event_at: dict[str, str | None] = {}
    for item in events:
        case_id = str(item.get("case_id") or "").strip()
        payload = item.get("event_payload") or {}
        if not case_id:
            case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            continue
        canonical = item.get("canonical_event") or {}
        if isinstance(canonical, Mapping):
            grouped.setdefault(case_id, []).append(match_event_from_mapping(canonical))
        case_types[case_id] = str(item.get("case_type") or payload.get("case_type") or "").strip() or None
        last_event_types[case_id] = str(item.get("event_type") or "").strip() or None
        last_event_at[case_id] = str(item.get("occurred_at") or "").strip() or None
    out: list[dict[str, Any]] = []
    for case_id, case_events in grouped.items():
        reduced = reduce_case_ledger(case_events)
        out.append(
            {
                "case_id": case_id,
                "case_type": case_types.get(case_id),
                "case_status": reduced.status.value,
                "latest_event_type": last_event_types.get(case_id),
                "last_event_at": last_event_at.get(case_id),
                "metadata": {"source": "event_fallback"},
            }
        )
    out.sort(key=lambda item: (str(item.get("last_event_at") or ""), str(item.get("case_id") or "")), reverse=True)
    return out


def get_relation_by_case_id(conn, case_id: str) -> dict[str, Any] | None:
    case_id = str(case_id or "").strip()
    if not case_id:
        return None
    row = conn.execute(
        """
        SELECT relation_id
        FROM match_relation_cases
        WHERE case_id = ?
        ORDER BY last_event_at DESC, case_id DESC
        LIMIT 1
        """,
        (case_id,),
    ).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT relation_id
            FROM match_relation_events
            WHERE case_id = ?
            ORDER BY occurred_at DESC, ledger_event_id DESC
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()
    if not row:
        return None
    return get_relation(conn, str(row["relation_id"]))


def get_relation_for_lookup_keys(
    conn,
    lookup_keys: list[str | None],
    *,
    case_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if case_id:
        relation = get_relation_by_case_id(conn, case_id)
        if relation:
            return relation, str(relation.get("relation_key") or "")
    seen: set[str] = set()
    for raw_key in lookup_keys:
        key = str(raw_key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        relation = get_relation_by_key(conn, key)
        if relation and (relation.get("events") or relation.get("cases")):
            return relation, key
    for raw_key in lookup_keys:
        key = str(raw_key or "").strip()
        if not key or key in seen:
            continue
        relation = get_relation_by_key(conn, key)
        if relation:
            return relation, key
    return None, None


def build_unified_timeline_from_ledger(relation: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = list(relation.get("events") or [])
    timeline: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, Mapping):
            continue
        canonical = item.get("canonical_event") or {}
        timeline.append(
            {
                "source": "relationship_ledger",
                "occurred_at": item.get("occurred_at"),
                "event_type": item.get("event_type"),
                "source_service": item.get("source_service"),
                "case_id": item.get("case_id"),
                "case_type": item.get("case_type"),
                "aggregate_type": item.get("aggregate_type"),
                "aggregate_id": item.get("aggregate_id"),
                "actor_type": item.get("actor_type"),
                "actor_id": item.get("actor_id"),
                "canonical_event": canonical,
            }
        )
    timeline.sort(key=lambda row: (str(row.get("occurred_at") or ""), str(row.get("event_type") or "")))
    return timeline


def summarize_ledger_relation_for_timeline(relation: Mapping[str, Any]) -> dict[str, Any]:
    from match_domain.boundary import case_progress_owner

    active_case = next(
        (
            case
            for case in (relation.get("cases") or [])
            if str(case.get("case_status") or "") in OPEN_LEDGER_CASE_STATUSES
        ),
        None,
    )
    return {
        "relation_key": relation.get("relation_key"),
        "relation_status": relation.get("relation_status"),
        "current_phase": relation.get("current_phase"),
        "recommendation_status_owner": "recommendation",
        "case_progress_owner": case_progress_owner(active_case) if active_case else None,
        "case_progress_status": canonical_case_status_value(
            active_case.get("case_status") if active_case else relation.get("active_case_status")
        ),
        "active_case_id": relation.get("active_case_id"),
        "active_case_type": relation.get("active_case_type"),
        "active_case_status": canonical_case_status_value(relation.get("active_case_status")),
        "latest_chat_thread_id": relation.get("latest_chat_thread_id"),
        "event_count": len(relation.get("events") or []),
        "case_count": len(relation.get("cases") or []),
    }


__all__ = [
    "append_event",
    "build_cross_system_funnel_dashboard",
    "build_relation_dashboard",
    "build_unified_timeline_from_ledger",
    "get_relation",
    "get_relation_by_case_id",
    "get_relation_by_key",
    "get_relation_for_lookup_keys",
    "list_cases_for_relation",
    "list_events_for_relation",
    "list_relations",
    "list_relations_for_profile_refs",
    "relation_id_from_key",
    "summarize_ledger_relation_for_timeline",
]
