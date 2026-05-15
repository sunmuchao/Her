"""Helpers for verification notification records and filters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .storage import inflate_json_columns, json_dumps, row_to_dict

DELIVERY_CHANNEL_IN_APP = "in_app"
DELIVERY_STATUS_RECORDED = "recorded"


def _normalize_metadata(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def parse_statuses(value: list[str] | tuple[str, ...] | str | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    else:
        parts = [str(part).strip() for part in value]
    normalized = [part for part in parts if part]
    return normalized or None


def _inflate_notification(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}, _normalize_metadata))


def list_verification_notifications(
    conn,
    *,
    submission_id: str | None = None,
    user_id: str | None = None,
    notification_types: list[str] | tuple[str, ...] | str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if submission_id:
        clauses.append("submission_id = ?")
        params.append(str(submission_id))
    if user_id:
        clauses.append("user_id = ?")
        params.append(str(user_id))
    normalized_types = parse_statuses(notification_types)
    if normalized_types:
        placeholders = ", ".join(["?"] * len(normalized_types))
        clauses.append(f"notification_type IN ({placeholders})")
        params.extend(normalized_types)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM verification_notifications
        {where}
        ORDER BY created_at DESC, notification_id DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_notification(row_to_dict(row)) for row in rows if row]


def create_verification_notification(
    conn,
    *,
    submission_id: str,
    user_id: str,
    notification_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any] | None,
    now: datetime,
) -> int:
    conn.execute(
        """
        INSERT INTO verification_notifications (
          submission_id, user_id, notification_type, delivery_channel, delivery_status,
          title, body, metadata_json, created_at, sent_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            str(user_id),
            str(notification_type),
            DELIVERY_CHANNEL_IN_APP,
            DELIVERY_STATUS_RECORDED,
            title,
            body,
            json_dumps(_normalize_metadata(metadata)),
            now,
            now,
        ),
    )
    return int(conn.lastrowid)


def notification_already_recorded(
    conn,
    *,
    submission_id: str,
    notification_type: str,
) -> bool:
    clauses = ["submission_id = ?", "notification_type = ?"]
    params: list[Any] = [submission_id, notification_type]
    row = conn.execute(
        f"""
        SELECT notification_id
        FROM verification_notifications
        WHERE {' AND '.join(clauses)}
        ORDER BY notification_id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return bool(row)
