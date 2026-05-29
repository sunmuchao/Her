"""Call session management for audio/video calls between matched users."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from her_time_utils import current_time

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from .storage import inflate_json_columns, json_dumps, row_to_dict


CALL_STATUS_PENDING = "pending"
CALL_STATUS_ACTIVE = "active"
CALL_STATUS_ENDED = "ended"

CALL_TYPE_AUDIO = "audio"
CALL_TYPE_VIDEO = "video"


def _generate_call_id() -> str:
    return f"call-{uuid.uuid4().hex[:16]}"


def _generate_room_id() -> str:
    return f"room-{uuid.uuid4().hex[:16]}"


def _inflate_call_session(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return row


def create_call_session(
    conn,
    *,
    case_id: str,
    conversation_id: str | None = None,
    caller_id: str,
    callee_id: str,
    call_type: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a new call session with pending status.

    Generates call_id and room_id automatically.
    """
    if call_type not in (CALL_TYPE_AUDIO, CALL_TYPE_VIDEO):
        raise ValueError(f"invalid call_type: {call_type}")

    ts = current_time(now)
    call_id = _generate_call_id()
    room_id = _generate_room_id()

    try:
        conn.execute(
            """
            INSERT INTO call_sessions (
                call_id, case_id, conversation_id, caller_id, callee_id,
                call_type, room_id, status, started_at, ended_at,
                duration_seconds, end_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                case_id,
                conversation_id,
                caller_id,
                callee_id,
                call_type,
                room_id,
                CALL_STATUS_PENDING,
                None,
                None,
                None,
                None,
                ts,
            ),
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()
        raise ValueError(f"call session already exists for case_id={case_id}")

    session = get_call_session(conn, call_id)
    assert session is not None
    return session


def get_call_session(conn, call_id: str) -> dict[str, Any] | None:
    """Get a call session by call_id."""
    cur = conn.execute(
        "SELECT * FROM call_sessions WHERE call_id = ? LIMIT 1",
        (call_id,),
    )
    return _inflate_call_session(row_to_dict(cur.fetchone()))


def get_call_session_by_case(conn, case_id: str) -> dict[str, Any] | None:
    """Get the active call session for a case."""
    cur = conn.execute(
        """
        SELECT * FROM call_sessions
        WHERE case_id = ? AND status IN (?, ?)
        ORDER BY created_at DESC LIMIT 1
        """,
        (case_id, CALL_STATUS_PENDING, CALL_STATUS_ACTIVE),
    )
    return _inflate_call_session(row_to_dict(cur.fetchone()))


def update_call_status(
    conn,
    call_id: str,
    status: str,
    *,
    started_at: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Update call session status (e.g., pending -> active)."""
    if status not in (CALL_STATUS_PENDING, CALL_STATUS_ACTIVE, CALL_STATUS_ENDED):
        raise ValueError(f"invalid status: {status}")

    session = get_call_session(conn, call_id)
    if not session:
        raise ValueError(f"call session not found: {call_id}")

    ts = current_time(now)
    update_fields = ["status = ?", "updated_at = ?"]
    update_values = [status, ts]

    if status == CALL_STATUS_ACTIVE and started_at is None:
        started_at = ts
    if started_at is not None:
        update_fields.append("started_at = ?")
        update_values.append(started_at)

    conn.execute(
        f"UPDATE call_sessions SET {', '.join(update_fields)} WHERE call_id = ?",
        tuple(update_values + [call_id]),
    )
    conn.commit()

    return get_call_session(conn, call_id)


def end_call_session(
    conn,
    call_id: str,
    *,
    end_reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """End a call session, recording duration and end reason."""
    session = get_call_session(conn, call_id)
    if not session:
        raise ValueError(f"call session not found: {call_id}")

    ts = current_time(now)
    started_at = session.get("started_at")

    duration_seconds = None
    if started_at:
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        duration_seconds = int((ts - started_at).total_seconds())

    conn.execute(
        """
        UPDATE call_sessions
        SET status = ?, ended_at = ?, duration_seconds = ?, end_reason = ?, updated_at = ?
        WHERE call_id = ?
        """,
        (
            CALL_STATUS_ENDED,
            ts,
            duration_seconds,
            end_reason,
            ts,
            call_id,
        ),
    )
    conn.commit()

    return get_call_session(conn, call_id)


def list_call_sessions_by_case(
    conn,
    case_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List all call sessions for a case."""
    cur = conn.execute(
        """
        SELECT * FROM call_sessions
        WHERE case_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (case_id, limit),
    )
    sessions: list[dict[str, Any]] = []
    for raw in cur.fetchall():
        session = _inflate_call_session(row_to_dict(raw))
        if session:
            sessions.append(session)
    return sessions


def list_active_calls_for_user(
    conn,
    user_id: str,
    *,
    as_caller: bool = True,
    as_callee: bool = True,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List active/pending calls for a user."""
    conditions: list[str] = []
    params: list[Any] = []

    if as_caller:
        conditions.append("caller_id = ?")
        params.append(user_id)
    if as_callee:
        conditions.append("callee_id = ?")
        params.append(user_id)

    if not conditions:
        return []

    where_clause = f"({' OR '.join(conditions)}) AND status IN (?, ?)"
    params.extend([CALL_STATUS_PENDING, CALL_STATUS_ACTIVE])

    cur = conn.execute(
        f"""
        SELECT * FROM call_sessions
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        tuple(params + [limit]),
    )
    sessions: list[dict[str, Any]] = []
    for raw in cur.fetchall():
        session = _inflate_call_session(row_to_dict(raw))
        if session:
            sessions.append(session)
    return sessions


__all__ = [
    "CALL_STATUS_ACTIVE",
    "CALL_STATUS_ENDED",
    "CALL_STATUS_PENDING",
    "CALL_TYPE_AUDIO",
    "CALL_TYPE_VIDEO",
    "create_call_session",
    "end_call_session",
    "get_call_session",
    "get_call_session_by_case",
    "list_active_calls_for_user",
    "list_call_sessions_by_case",
    "update_call_status",
]