"""Operational helpers for moderation playback, appeals, batch review, and dashboards."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

from partner_moderation import get_active_moderation_state, list_moderation_states

from .fraud_graph import build_fraud_network_overview, list_fraud_network_profiles
from .risk import (
    RISK_STATUS_ACTION_APPLIED,
    RISK_STATUS_DISMISSED,
    RISK_STATUS_RESOLVED,
    current_time,
    get_risk_case,
    list_meeting_feedback,
    list_member_reports,
    list_risk_signals,
    review_risk_case,
)
from .storage import inflate_json_columns, json_dumps, row_to_dict

APPEAL_STATUS_SUBMITTED = "submitted"
APPEAL_STATUS_UNDER_REVIEW = "under_review"
APPEAL_STATUS_UPHELD = "upheld"
APPEAL_STATUS_REJECTED = "rejected"


def _inflate_risk_appeal(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, evidence=("evidence_json", {}))


def get_risk_appeal(conn, appeal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM chat_risk_appeals
        WHERE appeal_id = ?
        LIMIT 1
        """,
        (int(appeal_id),),
    ).fetchone()
    return _inflate_risk_appeal(row_to_dict(row))


def list_risk_appeals(
    conn,
    *,
    statuses: Iterable[Any] | None = None,
    risk_case_id: str | None = None,
    subject_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    normalized_statuses = _unique_ordered(statuses or [])
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"appeal_status IN ({placeholders})")
        params.extend(normalized_statuses)
    if risk_case_id:
        clauses.append("risk_case_id = ?")
        params.append(_as_text(risk_case_id))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM chat_risk_appeals
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_risk_appeal(row_to_dict(row)) for row in rows if row]


def submit_risk_appeal(
    conn,
    risk_case_id: str,
    appellant_id: str,
    *,
    reason_text: str,
    evidence: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    risk_case = get_risk_case(conn, risk_case_id)
    if not risk_case:
        raise ValueError("risk case not found")
    moderation_state = get_active_moderation_state(
        conn,
        subject_user_id=risk_case.get("subject_user_id"),
        source_dsn=risk_case.get("evidence_summary", {}).get("source_dsn"),
        source_table_name=risk_case.get("evidence_summary", {}).get("source_table_name"),
        profile_id=risk_case.get("evidence_summary", {}).get("profile_id"),
    )
    ts = current_time(now)
    conn.execute(
        """
        INSERT INTO chat_risk_appeals (
          risk_case_id, subject_key, subject_user_id, appellant_id, appeal_status,
          reason_text, evidence_json, resolution_note, resolver_id, created_at, updated_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            risk_case_id,
            (moderation_state or {}).get("subject_key"),
            risk_case.get("subject_user_id"),
            _as_text(appellant_id),
            APPEAL_STATUS_SUBMITTED,
            _as_text(reason_text),
            json_dumps(dict(evidence or {})),
            None,
            None,
            ts,
            ts,
            None,
        ),
    )
    conn.commit()
    appeal = get_risk_appeal(conn, int(conn.lastrowid))
    assert appeal is not None
    return appeal


def review_risk_appeal(
    conn,
    appeal_id: int,
    resolver_id: str,
    *,
    appeal_status: str,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_risk_appeal(conn, int(appeal_id))
    if not current:
        raise ValueError("risk appeal not found")
    normalized_status = _as_text(appeal_status)
    if normalized_status not in {
        APPEAL_STATUS_SUBMITTED,
        APPEAL_STATUS_UNDER_REVIEW,
        APPEAL_STATUS_UPHELD,
        APPEAL_STATUS_REJECTED,
    }:
        raise ValueError("invalid appeal_status")
    ts = current_time(now)
    conn.execute(
        """
        UPDATE chat_risk_appeals
        SET appeal_status = ?,
            resolution_note = ?,
            resolver_id = ?,
            updated_at = ?,
            resolved_at = ?
        WHERE appeal_id = ?
        """,
        (
            normalized_status,
            resolution_note,
            _as_text(resolver_id),
            ts,
            ts if normalized_status in {APPEAL_STATUS_UPHELD, APPEAL_STATUS_REJECTED} else None,
            int(appeal_id),
        ),
    )
    if normalized_status == APPEAL_STATUS_UPHELD:
        risk_case = get_risk_case(conn, current["risk_case_id"])
        if risk_case and risk_case["status"] not in {RISK_STATUS_DISMISSED, RISK_STATUS_RESOLVED}:
            review_risk_case(
                conn,
                current["risk_case_id"],
                _as_text(resolver_id),
                status=RISK_STATUS_RESOLVED,
                resolution_note=resolution_note or "申诉成立，解除原限制",
                now=ts,
            )
    conn.commit()
    updated = get_risk_appeal(conn, int(appeal_id))
    assert updated is not None
    return updated


def batch_review_risk_cases(
    conn,
    *,
    risk_case_ids: Iterable[Any],
    resolver_id: str,
    status: str,
    applied_action: str | None = None,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    reviewed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for raw_case_id in risk_case_ids:
        risk_case_id = _as_text(raw_case_id)
        if not risk_case_id:
            continue
        try:
            reviewed.append(
                review_risk_case(
                    conn,
                    risk_case_id,
                    _as_text(resolver_id),
                    status=status,
                    applied_action=applied_action,
                    resolution_note=resolution_note,
                    now=ts,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "risk_case_id": risk_case_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
    return {"reviewed": reviewed, "errors": errors}


def build_risk_case_playback(conn, risk_case_id: str) -> dict[str, Any]:
    risk_case = get_risk_case(conn, risk_case_id)
    if not risk_case:
        raise ValueError("risk case not found")
    moderation_state = get_active_moderation_state(
        conn,
        subject_user_id=risk_case.get("subject_user_id"),
        source_dsn=risk_case.get("evidence_summary", {}).get("source_dsn"),
        source_table_name=risk_case.get("evidence_summary", {}).get("source_table_name"),
        profile_id=risk_case.get("evidence_summary", {}).get("profile_id"),
    )
    return {
        "risk_case": risk_case,
        "reports": list_member_reports(conn, risk_case_id=risk_case_id, limit=100),
        "signals": list_risk_signals(conn, subject_user_id=risk_case.get("subject_user_id"), limit=200),
        "meeting_feedback": list_meeting_feedback(
            conn,
            thread_id=risk_case.get("thread_id"),
            counterpart_user_id=risk_case.get("subject_user_id"),
            limit=100,
        ),
        "appeals": list_risk_appeals(conn, risk_case_id=risk_case_id, limit=100),
        "moderation_state": moderation_state,
        "fraud_network": build_fraud_network_overview(conn, risk_case.get("subject_user_id")),
    }


def build_risk_weekly_dashboard(
    conn,
    *,
    now: datetime | None = None,
    days: int = 7,
) -> dict[str, Any]:
    end_at = current_time(now)
    start_at = end_at - timedelta(days=max(int(days), 1))
    case_rows = conn.execute(
        """
        SELECT *
        FROM chat_risk_cases
        WHERE created_at >= ? AND created_at < ?
        ORDER BY created_at ASC
        """,
        (start_at, end_at),
    ).fetchall()
    risk_cases = [get_risk_case(conn, row_to_dict(row)["risk_case_id"]) for row in case_rows if row]
    risk_cases = [item for item in risk_cases if item]
    appeals = list_risk_appeals(conn, limit=500)
    appeals_in_window = [
        item
        for item in appeals
        if start_at <= datetime.fromisoformat(_as_text(item.get("created_at"))) < end_at
    ]
    subjects = [_as_text(item.get("subject_user_id")) for item in risk_cases if _as_text(item.get("subject_user_id"))]
    unique_subjects = {item for item in subjects if item}
    repeat_subjects = {item for item in unique_subjects if subjects.count(item) >= 2}
    reviewed_cases = [item for item in risk_cases if item.get("status") in {RISK_STATUS_ACTION_APPLIED, RISK_STATUS_DISMISSED, RISK_STATUS_RESOLVED}]
    confirmed_cases = [item for item in reviewed_cases if item.get("status") == RISK_STATUS_ACTION_APPLIED]
    dismissed_cases = [item for item in reviewed_cases if item.get("status") == RISK_STATUS_DISMISSED]
    upheld_appeals = [item for item in appeals_in_window if item.get("appeal_status") == APPEAL_STATUS_UPHELD]
    rejected_appeals = [item for item in appeals_in_window if item.get("appeal_status") == APPEAL_STATUS_REJECTED]
    active_states = list_moderation_states(conn, moderation_status="active", limit=500)
    network_profiles = list_fraud_network_profiles(conn, minimum_score=1, limit=500)
    high_risk_networks = [item for item in network_profiles if int(item.get("graph_risk_score") or 0) >= 60]
    severity_breakdown: dict[str, int] = {}
    action_breakdown: dict[str, int] = {}
    network_action_breakdown: dict[str, int] = {}
    for item in risk_cases:
        severity = _as_text(item.get("severity")) or "unknown"
        severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1
        action = _as_text(item.get("applied_action") or item.get("recommended_action")) or "none"
        action_breakdown[action] = action_breakdown.get(action, 0) + 1
    for item in network_profiles:
        action = _as_text(item.get("applied_action") or item.get("recommended_action")) or "none"
        network_action_breakdown[action] = network_action_breakdown.get(action, 0) + 1
    confirmed_rate = round(len(confirmed_cases) / max(len(reviewed_cases), 1), 4)
    false_positive_rate = round(len(upheld_appeals) / max(len(reviewed_cases), 1), 4)
    recurrence_rate = round(len(repeat_subjects) / max(len(unique_subjects), 1), 4)
    return {
        "window_start": start_at.isoformat(sep=" "),
        "window_end": end_at.isoformat(sep=" "),
        "days": int(days),
        "risk_case_count": len(risk_cases),
        "reviewed_case_count": len(reviewed_cases),
        "confirmed_case_count": len(confirmed_cases),
        "dismissed_case_count": len(dismissed_cases),
        "appeal_count": len(appeals_in_window),
        "appeal_upheld_count": len(upheld_appeals),
        "appeal_rejected_count": len(rejected_appeals),
        "active_moderation_state_count": len(active_states),
        "fraud_network_profile_count": len(network_profiles),
        "high_risk_network_count": len(high_risk_networks),
        "severity_breakdown": severity_breakdown,
        "action_breakdown": action_breakdown,
        "network_action_breakdown": network_action_breakdown,
        "confirmed_rate": confirmed_rate,
        "false_positive_rate": false_positive_rate,
        "recurrence_rate": recurrence_rate,
        "repeat_subject_count": len(repeat_subjects),
    }


__all__ = [
    "build_risk_case_playback",
    "build_risk_weekly_dashboard",
    "batch_review_risk_cases",
    "get_risk_appeal",
    "list_risk_appeals",
    "review_risk_appeal",
    "submit_risk_appeal",
]
