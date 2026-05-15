"""Chat threads and participant messages."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from her_time_utils import current_time

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from match_domain.outbox import append_outbox_pending
from match_domain.trace_context import get_trace_id
from observability import (
    CHAT_FUNNEL_MESSAGE_SEND,
    CHAT_FUNNEL_THREAD_OPEN,
    funnel_stage,
)

from .events import chat_message_created_event, chat_thread_opened_event
from .persona_jobs import maybe_enqueue_persona_sync_job
from .risk import assert_message_allowed, maybe_capture_message_risk_signal
from .storage import inflate_json_columns, json_dumps, row_to_dict

VIS_DYADIC = "dyadic"
VIS_OWNER_ONLY = "owner_only"
VIS_SYSTEM = "system"
SRC_USER = "user"
SRC_SYSTEM = "system"


def _generate_thread_id() -> str:
    return f"cht-{uuid.uuid4().hex[:16]}"


def _inflate_thread(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def _inflate_message(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def get_thread(conn, thread_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_threads WHERE thread_id = ? LIMIT 1",
        (thread_id,),
    )
    return _inflate_thread(row_to_dict(cur.fetchone()))


def get_thread_by_case(conn, case_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_threads WHERE case_id = ? LIMIT 1",
        (case_id,),
    )
    return _inflate_thread(row_to_dict(cur.fetchone()))


def get_or_create_thread(
    conn,
    *,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    existing = get_thread_by_case(conn, case_id)
    if existing:
        return existing

    ts = current_time(now)
    thread_id = _generate_thread_id()
    try:
        conn.execute(
            """
            INSERT INTO chat_threads (
              thread_id, case_id, relation_key, status,
              participant_a_id, participant_b_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                case_id,
                relation_key,
                "open",
                participant_a_id,
                participant_b_id,
                json_dumps(metadata or {}),
                ts,
                ts,
            ),
        )
        append_outbox_pending(
            conn,
            event=chat_thread_opened_event(
                thread_id=thread_id,
                case_id=case_id,
                relation_key=relation_key,
                participant_a_id=participant_a_id,
                participant_b_id=participant_b_id,
                occurred_at=ts,
            ),
            source_row_table="chat_threads",
            source_row_id=None,
            created_at_str=ts.isoformat(sep=" "),
        )
        conn.commit()
        funnel_stage(
            system="chat",
            stage=CHAT_FUNNEL_THREAD_OPEN,
            trace_id=get_trace_id(),
            case_id=case_id,
            thread_id=thread_id,
            relation_key=relation_key,
        )
    except IntegrityError:
        conn.rollback()
        existing2 = get_thread_by_case(conn, case_id)
        if existing2:
            return existing2
        raise

    created = get_thread(conn, thread_id)
    assert created is not None
    return created


def _is_participant(thread: dict[str, Any], user_id: str) -> bool:
    return user_id in {thread["participant_a_id"], thread["participant_b_id"]}


def _message_visible_to_requester(
    row: dict[str, Any],
    thread: dict[str, Any],
    requester_id: str,
) -> bool:
    vis = str(row.get("visibility") or "")
    if vis in {VIS_DYADIC, VIS_SYSTEM}:
        return _is_participant(thread, requester_id)
    if vis != VIS_OWNER_ONLY:
        return False
    if str(row.get("message_recipient_id") or "") != str(requester_id):
        return False
    return str(row.get("author_id") or "") == str(requester_id)


def _select_message_batch(
    conn,
    thread: dict[str, Any],
    requester_id: str,
    *,
    fetch_limit: int,
    before_message_id: int | None,
    dyadic_only: bool,
) -> list[dict[str, Any]]:
    params: list[Any] = [str(thread["thread_id"])]
    before_clause = ""
    if before_message_id is not None:
        before_clause = "AND message_id < ?"
        params.append(int(before_message_id))

    if dyadic_only:
        sql = f"""
            SELECT * FROM chat_messages
            WHERE thread_id = ?
              {before_clause}
              AND visibility = ?
            ORDER BY message_id DESC
            LIMIT ?
        """
        params.extend([VIS_DYADIC, fetch_limit])
    else:
        sql = f"""
            SELECT * FROM chat_messages
            WHERE thread_id = ?
              {before_clause}
              AND (
                visibility IN (?, ?)
                OR (visibility = ? AND message_recipient_id = ?)
              )
            ORDER BY message_id DESC
            LIMIT ?
        """
        params.extend([VIS_DYADIC, VIS_SYSTEM, VIS_OWNER_ONLY, str(requester_id), fetch_limit])

    cur = conn.execute(sql, tuple(params))
    out: list[dict[str, Any]] = []
    for raw in cur.fetchall():
        row = _inflate_message(row_to_dict(raw))
        if row:
            out.append(row)
    return out


def _list_messages_for_requester(
    conn,
    thread: dict[str, Any],
    requester_id: str,
    *,
    limit: int,
    before_message_id: int | None,
    dyadic_only: bool,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    fetch_limit = min(max(lim * 3, 100), 1000)
    cursor_before = before_message_id
    visible_desc: list[dict[str, Any]] = []

    while len(visible_desc) < lim:
        batch = _select_message_batch(
            conn,
            thread,
            requester_id,
            fetch_limit=fetch_limit,
            before_message_id=cursor_before,
            dyadic_only=dyadic_only,
        )
        if not batch:
            break
        for row in batch:
            if dyadic_only or _message_visible_to_requester(row, thread, requester_id):
                visible_desc.append(row)
                if len(visible_desc) >= lim:
                    break
        if len(batch) < fetch_limit:
            break
        cursor_before = min(int(row["message_id"]) for row in batch)

    return list(reversed(visible_desc[:lim]))


def list_messages(
    conn,
    thread_id: str,
    requester_id: str,
    *,
    limit: int = 50,
    before_message_id: int | None = None,
) -> list[dict[str, Any]]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, requester_id):
        raise ValueError("requester is not a participant of this thread")
    return _list_messages_for_requester(
        conn,
        thread,
        requester_id,
        limit=limit,
        before_message_id=before_message_id,
        dyadic_only=False,
    )


def post_message(
    conn,
    thread_id: str,
    author_id: str,
    body: str,
    *,
    visibility: str = VIS_DYADIC,
    source: str = SRC_USER,
    client_msg_id: str | None = None,
    message_recipient_id: str | None = None,
    reply_to_message_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")

    author = str(author_id or "")
    if not author:
        raise ValueError("author_id is required")
    if visibility not in (VIS_DYADIC, VIS_OWNER_ONLY, VIS_SYSTEM):
        raise ValueError("invalid visibility")
    if visibility == VIS_OWNER_ONLY and not message_recipient_id:
        raise ValueError("message_recipient_id is required for owner_only messages")

    if visibility == VIS_SYSTEM:
        if source != SRC_SYSTEM:
            raise ValueError("system messages must use source=system")
    else:
        if not _is_participant(thread, author):
            raise ValueError("author is not a participant")
        if visibility == VIS_DYADIC:
            assert_message_allowed(conn, thread_id, author)
            if source != SRC_USER:
                raise ValueError("invalid source for user dyadic message")
        else:
            if source != SRC_USER:
                raise ValueError("participants may only post owner_only messages with source=user")
            if str(message_recipient_id or "") != author:
                raise ValueError("owner_only messages must be addressed to the author")

    ts = current_time(now)
    cmid = (client_msg_id or "").strip() or None
    if cmid:
        cmid = cmid[:191]
        cur = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE thread_id = ? AND client_msg_id = ? LIMIT 1
            """,
            (thread_id, cmid),
        )
        existing = _inflate_message(row_to_dict(cur.fetchone()))
        if existing:
            return dict(existing)

    try:
        conn.execute(
            """
            INSERT INTO chat_messages (
              thread_id, author_id, message_recipient_id, visibility, source, body,
              client_msg_id, reply_to_message_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                author,
                message_recipient_id,
                visibility,
                source,
                body,
                cmid,
                reply_to_message_id,
                json_dumps(metadata or {}),
                ts,
            ),
        )
        inserted_id = int(conn.lastrowid)
        conn.execute(
            "UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?",
            (ts, thread_id),
        )
        append_outbox_pending(
            conn,
            event=chat_message_created_event(
                thread_id=thread_id,
                case_id=str(thread["case_id"]),
                message_id=inserted_id,
                author_id=author,
                body=body,
                visibility=visibility,
                source=source,
                occurred_at=ts,
            ),
            source_row_table="chat_messages",
            source_row_id=inserted_id,
            created_at_str=ts.isoformat(sep=" "),
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()
        if cmid:
            cur = conn.execute(
                """
                SELECT * FROM chat_messages
                WHERE thread_id = ? AND client_msg_id = ? LIMIT 1
                """,
                (thread_id, cmid),
            )
            existing = _inflate_message(row_to_dict(cur.fetchone()))
            if existing:
                return dict(existing)
        raise

    cur = conn.execute("SELECT * FROM chat_messages WHERE message_id = ? LIMIT 1", (inserted_id,))
    row = _inflate_message(row_to_dict(cur.fetchone()))
    assert row is not None

    if visibility == VIS_DYADIC:
        maybe_capture_message_risk_signal(
            conn,
            thread_id=thread_id,
            message_id=inserted_id,
            author_id=author,
            body=body,
            now=ts,
        )

    try:
        maybe_enqueue_persona_sync_job(
            conn,
            thread,
            message_id=inserted_id,
            author_id=author,
            body=body,
            visibility=visibility,
            source=source,
            message_recipient_id=message_recipient_id,
            metadata=metadata,
            ts=ts,
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()

    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_MESSAGE_SEND,
        trace_id=get_trace_id(),
        case_id=str(thread["case_id"]),
        thread_id=thread_id,
        message_id=inserted_id,
        visibility=visibility,
        source=source,
        author_id=author,
    )
    return dict(row)


__all__ = [
    "SRC_SYSTEM",
    "SRC_USER",
    "VIS_DYADIC",
    "VIS_OWNER_ONLY",
    "VIS_SYSTEM",
    "current_time",
    "get_or_create_thread",
    "get_thread",
    "get_thread_by_case",
    "list_messages",
    "post_message",
]
