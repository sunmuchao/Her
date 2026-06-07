"""Session and task persistence for the triggered matchmaker agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

from her_time_utils import coerce_dt as _coerce_dt, current_time

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from .conversations import (
    ROLE_AGENT,
    ROLE_HUMAN,
    get_conversation_by_case_and_key,
    list_case_conversations,
)
from .storage import inflate_json_columns, json_dumps, row_to_dict

SESSION_STATUS_OPEN = "open"
SESSION_STATUS_CLOSED = "closed"

TASK_REASON_USER_MESSAGE = "user_message"
TASK_REASON_OPENING_PROBE = "opening_probe"
TASK_REASON_SILENCE_PROBE = "silence_probe"
TASK_REASON_POST_CHAT_REVIEW = "post_chat_review"
TASK_REASON_POST_CHAT_FOLLOWUP_A = "post_chat_followup_a"
TASK_REASON_POST_CHAT_FOLLOWUP_B = "post_chat_followup_b"

PUBLIC_FOLLOWUP_MODE_OPENING = "opening"
PUBLIC_FOLLOWUP_MODE_SILENCE = "silence"
PUBLIC_FOLLOWUP_MODES = {PUBLIC_FOLLOWUP_MODE_OPENING, PUBLIC_FOLLOWUP_MODE_SILENCE}

TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

POST_CHAT_PHASES = {"post_chat_ready", "post_chat_followup", "post_chat_completed"}


def _generate_session_id() -> str:
    return f"ags-{uuid.uuid4().hex[:16]}"


def _inflate_session(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, state=("state_json", {}))


def _inflate_task(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, result=("result_json", None))


def _inflate_main_group_conversation_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def _derive_case_session_spec(conn, case_id: str) -> dict[str, str]:
    conversations = list_case_conversations(conn, case_id)
    if not conversations:
        raise ValueError("case conversations not found")
    main_group = next(
        (conversation for conversation in conversations if str(conversation.get("channel_key") or "") == "main_group"),
        conversations[0],
    )
    metadata = dict(main_group.get("metadata") or {})
    participant_a_id = str(metadata.get("participant_a_id") or "").strip()
    participant_b_id = str(metadata.get("participant_b_id") or "").strip()
    agent_id = str(metadata.get("agent_id") or "").strip()

    human_ids: list[str] = []
    agent_ids: list[str] = []
    for conversation in conversations:
        for member in conversation.get("members") or []:
            participant_id = str(member.get("participant_id") or "").strip()
            member_role = str(member.get("member_role") or "").strip()
            if not participant_id:
                continue
            if member_role == ROLE_AGENT and participant_id not in agent_ids:
                agent_ids.append(participant_id)
            if member_role == ROLE_HUMAN and participant_id not in human_ids:
                human_ids.append(participant_id)

    if not participant_a_id and human_ids:
        participant_a_id = human_ids[0]
    if not participant_b_id and len(human_ids) > 1:
        participant_b_id = human_ids[1]
    if not agent_id and agent_ids:
        agent_id = agent_ids[0]
    if not participant_a_id or not participant_b_id or not agent_id:
        raise ValueError("assistant case layout metadata is incomplete")

    return {
        "case_id": str(main_group["case_id"]),
        "relation_key": str(main_group["relation_key"]),
        "participant_a_id": participant_a_id,
        "participant_b_id": participant_b_id,
        "agent_participant_id": agent_id,
    }


def _derive_session_spec_from_main_group_row(row: dict[str, Any]) -> dict[str, str]:
    metadata = dict(row.get("metadata") or {})
    participant_a_id = str(metadata.get("participant_a_id") or "").strip()
    participant_b_id = str(metadata.get("participant_b_id") or "").strip()
    agent_id = str(metadata.get("agent_id") or "").strip()
    relation_key = str(row.get("relation_key") or "").strip()
    case_id = str(row.get("case_id") or "").strip()
    if not participant_a_id or not participant_b_id or not agent_id or not relation_key or not case_id:
        raise ValueError("assistant case layout metadata is incomplete")
    return {
        "case_id": case_id,
        "relation_key": relation_key,
        "participant_a_id": participant_a_id,
        "participant_b_id": participant_b_id,
        "agent_participant_id": agent_id,
    }


def _open_or_create_agent_session_from_spec(
    conn,
    *,
    session_id: str | None,
    case_id: str,
    session_spec: dict[str, str],
    triggered_by_message_id: int | None,
    now: datetime,
) -> str:
    trigger_message_id = int(triggered_by_message_id) if triggered_by_message_id is not None else None
    existing_session_id = str(session_id or "").strip()
    if existing_session_id:
        conn.execute(
            """
            UPDATE chat_agent_sessions
            SET relation_key = ?,
                status = ?,
                participant_a_id = ?,
                participant_b_id = ?,
                agent_participant_id = ?,
                triggered_by_message_id = COALESCE(triggered_by_message_id, ?),
                close_reason = NULL,
                ended_at = NULL,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                session_spec["relation_key"],
                SESSION_STATUS_OPEN,
                session_spec["participant_a_id"],
                session_spec["participant_b_id"],
                session_spec["agent_participant_id"],
                trigger_message_id,
                now,
                existing_session_id,
            ),
        )
        return existing_session_id

    created_session_id = _generate_session_id()
    try:
        conn.execute(
            """
            INSERT INTO chat_agent_sessions (
              session_id, case_id, relation_key, status,
              participant_a_id, participant_b_id, agent_participant_id,
              triggered_by_message_id, last_seen_message_id, last_user_message_at,
              last_agent_message_at, last_replied_at, cooldown_until, close_reason,
              state_json, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, NULL, ?, ?)
            """,
            (
                created_session_id,
                case_id,
                session_spec["relation_key"],
                SESSION_STATUS_OPEN,
                session_spec["participant_a_id"],
                session_spec["participant_b_id"],
                session_spec["agent_participant_id"],
                trigger_message_id,
                trigger_message_id,
                now if trigger_message_id is not None else None,
                json_dumps({}),
                now,
                now,
                now,
            ),
        )
    except IntegrityError:
        existing = get_agent_session_by_case(conn, case_id)
        if existing and str(existing.get("session_id") or "").strip():
            return str(existing["session_id"])
        raise
    return created_session_id


def is_public_followup_active(session: dict[str, Any] | None) -> bool:
    state = dict((session or {}).get("state") or {})
    return bool(state.get("public_followup_active"))


def get_agent_session(conn, session_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_agent_sessions WHERE session_id = ? LIMIT 1",
        (session_id,),
    )
    return _inflate_session(row_to_dict(cur.fetchone()))


def get_agent_session_by_case(conn, case_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_agent_sessions WHERE case_id = ? LIMIT 1",
        (case_id,),
    )
    return _inflate_session(row_to_dict(cur.fetchone()))


def list_agent_tasks(
    conn,
    *,
    case_id: str | None = None,
    session_id: str | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if case_id:
        clauses.append("case_id = ?")
        params.append(str(case_id))
    if session_id:
        clauses.append("session_id = ?")
        params.append(str(session_id))
    if statuses:
        normalized = [str(status) for status in statuses if str(status)]
        if normalized:
            clauses.append("status IN (" + ",".join("?" for _ in normalized) + ")")
            params.extend(normalized)
    params.append(lim)
    cur = conn.execute(
        f"""
        SELECT * FROM chat_agent_tasks
        WHERE {' AND '.join(clauses)}
        ORDER BY task_id ASC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = [_inflate_task(row_to_dict(row)) for row in cur.fetchall()]
    return [row for row in rows if row]


def get_agent_task(conn, task_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_agent_tasks WHERE task_id = ? LIMIT 1",
        (int(task_id),),
    )
    return _inflate_task(row_to_dict(cur.fetchone()))


def get_agent_tasks_by_ids(conn, task_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    normalized = [int(task_id) for task_id in task_ids]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    cur = conn.execute(
        f"""
        SELECT * FROM chat_agent_tasks
        WHERE task_id IN ({placeholders})
        """,
        tuple(normalized),
    )
    out: dict[int, dict[str, Any]] = {}
    for row in cur.fetchall():
        task = _inflate_task(row_to_dict(row))
        if task and task.get("task_id") is not None:
            out[int(task["task_id"])] = task
    return out


def _get_agent_task_by_dedupe_key(conn, dedupe_key: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_agent_tasks WHERE dedupe_key = ? LIMIT 1",
        (dedupe_key,),
    )
    return _inflate_task(row_to_dict(cur.fetchone()))


def _build_agent_task_dedupe_key(session_id: str, trigger_message_id: int | None, reason: str) -> str:
    return f"agent-session:{session_id}:reason:{reason}:message:{int(trigger_message_id or 0)}"


def _write_session_state(
    conn,
    session_id: str,
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    conn.execute(
        """
        UPDATE chat_agent_sessions
        SET state_json = ?,
            updated_at = ?
        WHERE session_id = ?
        """,
        (
            json_dumps(state),
            ts,
            session_id,
        ),
    )


def get_or_create_agent_session(
    conn,
    *,
    case_id: str,
    triggered_by_message_id: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    case_id = str(case_id or "").strip()
    if not case_id:
        raise ValueError("case_id is required")
    ts = current_time(now)
    trigger_message_id = int(triggered_by_message_id) if triggered_by_message_id is not None else None
    session_spec = _derive_case_session_spec(conn, case_id)
    existing = get_agent_session_by_case(conn, case_id)
    if existing:
        conn.execute(
            """
            UPDATE chat_agent_sessions
            SET relation_key = ?,
                status = ?,
                participant_a_id = ?,
                participant_b_id = ?,
                agent_participant_id = ?,
                triggered_by_message_id = COALESCE(triggered_by_message_id, ?),
                close_reason = NULL,
                ended_at = NULL,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                session_spec["relation_key"],
                SESSION_STATUS_OPEN,
                session_spec["participant_a_id"],
                session_spec["participant_b_id"],
                session_spec["agent_participant_id"],
                trigger_message_id,
                ts,
                existing["session_id"],
            ),
        )
        reopened = get_agent_session(conn, str(existing["session_id"]))
        assert reopened is not None
        return reopened

    session_id = _generate_session_id()
    try:
        conn.execute(
            """
            INSERT INTO chat_agent_sessions (
              session_id, case_id, relation_key, status,
              participant_a_id, participant_b_id, agent_participant_id,
              triggered_by_message_id, last_seen_message_id, last_user_message_at,
              last_agent_message_at, last_replied_at, cooldown_until, close_reason,
              state_json, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, NULL, ?, ?)
            """,
            (
                session_id,
                case_id,
                session_spec["relation_key"],
                SESSION_STATUS_OPEN,
                session_spec["participant_a_id"],
                session_spec["participant_b_id"],
                session_spec["agent_participant_id"],
                trigger_message_id,
                trigger_message_id,
                ts if trigger_message_id is not None else None,
                json_dumps({}),
                ts,
                ts,
                ts,
            ),
        )
    except IntegrityError:
        existing = get_agent_session_by_case(conn, case_id)
        if existing:
            return existing
        raise

    created = get_agent_session(conn, session_id)
    assert created is not None
    return created


def record_agent_session_user_activity(
    conn,
    session_id: str,
    *,
    trigger_message_id: int,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    conn.execute(
        """
        UPDATE chat_agent_sessions
        SET status = ?,
            close_reason = NULL,
            ended_at = NULL,
            last_seen_message_id = CASE
              WHEN last_seen_message_id IS NULL OR last_seen_message_id < ? THEN ?
              ELSE last_seen_message_id
            END,
            last_user_message_at = CASE
              WHEN last_user_message_at IS NULL OR last_user_message_at < ? THEN ?
              ELSE last_user_message_at
            END,
            updated_at = ?
        WHERE session_id = ?
        """,
        (
            SESSION_STATUS_OPEN,
            int(trigger_message_id),
            int(trigger_message_id),
            ts,
            ts,
            ts,
            str(session_id),
        ),
    )


def _session_has_pending_tasks(conn, session_id: str) -> bool:
    pending = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM chat_agent_tasks
        WHERE session_id = ? AND status IN (?, ?)
        """,
        (
            str(session_id),
            TASK_STATUS_PENDING,
            TASK_STATUS_RUNNING,
        ),
    ).fetchone()
    return bool(pending and int(pending["c"]) > 0)


def _session_ids_with_pending_tasks(conn, session_ids: Iterable[str]) -> set[str]:
    normalized_ids = [str(item).strip() for item in session_ids if str(item or "").strip()]
    if not normalized_ids:
        return set()
    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT DISTINCT session_id
        FROM chat_agent_tasks
        WHERE session_id IN ({placeholders}) AND status IN (?, ?)
        """,
        [*normalized_ids, TASK_STATUS_PENDING, TASK_STATUS_RUNNING],
    )
    return {str(row["session_id"]) for row in cur.fetchall() if str(row.get("session_id") or "").strip()}


def get_agent_sessions_by_ids(conn, session_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(item).strip() for item in session_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT * FROM chat_agent_sessions
        WHERE session_id IN ({placeholders})
        """,
        tuple(normalized_ids),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        session = _inflate_session(row_to_dict(row))
        if session and str(session.get("session_id") or "").strip():
            out[str(session["session_id"])] = session
    return out


def get_agent_sessions_by_case_ids(conn, case_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(item).strip() for item in case_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT * FROM chat_agent_sessions
        WHERE case_id IN ({placeholders})
        """,
        tuple(normalized_ids),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        session = _inflate_session(row_to_dict(row))
        case_id = str((session or {}).get("case_id") or "").strip()
        if session and case_id:
            out[case_id] = session
    return out


def get_agent_tasks_by_dedupe_keys(conn, dedupe_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item).strip() for item in dedupe_keys if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    cur = conn.execute(
        f"""
        SELECT * FROM chat_agent_tasks
        WHERE dedupe_key IN ({placeholders})
        """,
        tuple(normalized),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        task = _inflate_task(row_to_dict(row))
        dedupe_key = str((task or {}).get("dedupe_key") or "").strip()
        if task and dedupe_key:
            out[dedupe_key] = task
    return out


def _case_has_any_messages(conn, case_id: str) -> bool:
    cur = conn.execute(
        """
        SELECT m.message_id
        FROM chat_conversation_messages m
        JOIN chat_conversations c
          ON c.conversation_id = m.conversation_id
        WHERE c.case_id = ?
        ORDER BY m.message_id DESC
        LIMIT 1
        """,
        (case_id,),
    )
    return row_to_dict(cur.fetchone()) is not None


def _case_ids_with_any_messages(conn, case_ids: Iterable[str]) -> set[str]:
    normalized_ids = [str(item).strip() for item in case_ids if str(item or "").strip()]
    if not normalized_ids:
        return set()
    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT DISTINCT c.case_id
        FROM chat_conversation_messages m
        JOIN chat_conversations c
          ON c.conversation_id = m.conversation_id
        WHERE c.case_id IN ({placeholders})
        """,
        tuple(normalized_ids),
    )
    return {str(row["case_id"]) for row in cur.fetchall() if str(row.get("case_id") or "").strip()}


def enqueue_agent_task(
    conn,
    *,
    session_id: str,
    case_id: str,
    trigger_conversation_id: str,
    trigger_message_id: int,
    trigger_author_id: str,
    trigger_channel_key: str,
    reason: str = TASK_REASON_USER_MESSAGE,
    update_last_user_message_at: bool = True,
    touch_session: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    dedupe_key = _build_agent_task_dedupe_key(session_id, int(trigger_message_id), str(reason))
    res = conn.execute(
        """
        INSERT IGNORE INTO chat_agent_tasks (
          session_id, case_id, trigger_conversation_id, trigger_message_id,
          trigger_author_id, trigger_channel_key, reason, status, attempt_count,
          lease_until, dedupe_key, result_json, error_text, created_at, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL, ?, NULL, NULL)
        """,
        (
            session_id,
            case_id,
            trigger_conversation_id,
            int(trigger_message_id),
            trigger_author_id,
            trigger_channel_key,
            reason,
            TASK_STATUS_PENDING,
            dedupe_key,
            ts,
        ),
    )

    if touch_session:
        if update_last_user_message_at:
            record_agent_session_user_activity(
                conn,
                session_id,
                trigger_message_id=int(trigger_message_id),
                now=ts,
            )
        else:
            conn.execute(
                """
                UPDATE chat_agent_sessions
                SET status = ?,
                    close_reason = NULL,
                    ended_at = NULL,
                    last_seen_message_id = CASE
                      WHEN last_seen_message_id IS NULL OR last_seen_message_id < ? THEN ?
                      ELSE last_seen_message_id
                    END,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    SESSION_STATUS_OPEN,
                    int(trigger_message_id),
                    int(trigger_message_id),
                    ts,
                    session_id,
                ),
            )

    inserted = bool(int(res.rowcount or 0) > 0)
    if inserted and int(conn.lastrowid or 0) > 0:
        return {
            "task_id": int(conn.lastrowid),
            "session_id": session_id,
            "case_id": case_id,
            "trigger_conversation_id": trigger_conversation_id,
            "trigger_message_id": int(trigger_message_id),
            "trigger_author_id": trigger_author_id,
            "trigger_channel_key": trigger_channel_key,
            "reason": reason,
            "status": TASK_STATUS_PENDING,
            "attempt_count": 0,
            "lease_until": None,
            "result": None,
            "error_text": None,
            "dedupe_key": dedupe_key,
            "created_at": ts,
            "started_at": None,
            "finished_at": None,
            "_inserted": True,
        }

    task = _get_agent_task_by_dedupe_key(conn, dedupe_key)
    if not task:
        raise RuntimeError("failed to enqueue agent task")
    task["_inserted"] = False
    return task


def _latest_main_group_message(conn, case_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    return _latest_channel_message(conn, case_id, "main_group")


def _main_group_conversations_by_case(conn, case_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(item).strip() for item in case_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT *
        FROM chat_conversations
        WHERE channel_key = ? AND case_id IN ({placeholders})
        ORDER BY created_at ASC, conversation_id ASC
        """,
        ("main_group", *normalized_ids),
    )
    out: dict[str, dict[str, Any]] = {}
    for raw in cur.fetchall():
        conversation = inflate_json_columns(row_to_dict(raw), metadata=("metadata_json", {}))
        if not conversation:
            continue
        case_id = str(conversation.get("case_id") or "").strip()
        if case_id and case_id not in out:
            out[case_id] = conversation
    return out


def _latest_channel_message(conn, case_id: str, channel_key: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    conversation = get_conversation_by_case_and_key(conn, case_id, channel_key)
    if not conversation:
        return None
    cur = conn.execute(
        """
        SELECT message_id, author_id, source, created_at
        FROM chat_conversation_messages
        WHERE conversation_id = ?
        ORDER BY message_id DESC
        LIMIT 1
        """,
        (conversation["conversation_id"],),
    )
    message = row_to_dict(cur.fetchone())
    if not message:
        return None
    return conversation, message


def _latest_main_group_messages_by_case(
    conn,
    case_ids: Iterable[str],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    conversations_by_case = _main_group_conversations_by_case(conn, case_ids)
    if not conversations_by_case:
        return {}
    conversation_ids = [str(item["conversation_id"]) for item in conversations_by_case.values()]
    placeholders = ", ".join(["?"] * len(conversation_ids))
    try:
        cur = conn.execute(
            f"""
            SELECT message_id, author_id, source, created_at, conversation_id
            FROM (
              SELECT
                m.message_id,
                m.author_id,
                m.source,
                m.created_at,
                m.conversation_id,
                ROW_NUMBER() OVER (
                  PARTITION BY m.conversation_id
                  ORDER BY m.message_id DESC
                ) AS row_num
              FROM chat_conversation_messages m
              WHERE m.conversation_id IN ({placeholders})
            ) ranked_messages
            WHERE row_num = 1
            """,
            tuple(conversation_ids),
        )
        latest_by_conversation_id = {
            str(row["conversation_id"]): row_to_dict(row)
            for row in cur.fetchall()
            if str(row.get("conversation_id") or "").strip()
        }
    except Exception:
        cur = conn.execute(
            f"""
            SELECT message_id, author_id, source, created_at, conversation_id
            FROM chat_conversation_messages
            WHERE conversation_id IN ({placeholders})
            ORDER BY conversation_id ASC, message_id DESC
            """,
            tuple(conversation_ids),
        )
        latest_by_conversation_id = {}
        for row in cur.fetchall():
            row_dict = row_to_dict(row)
            conversation_id = str(row_dict.get("conversation_id") or "").strip()
            if not conversation_id or conversation_id in latest_by_conversation_id:
                continue
            latest_by_conversation_id[conversation_id] = row_dict
    out: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for case_id, conversation in conversations_by_case.items():
        message = latest_by_conversation_id.get(str(conversation["conversation_id"]))
        if message:
            out[case_id] = (conversation, message)
    return out


def _has_user_channel_message_since(
    conn,
    *,
    case_id: str,
    channel_key: str,
    participant_id: str,
    since: datetime | None,
) -> bool:
    conversation = get_conversation_by_case_and_key(conn, case_id, channel_key)
    if not conversation:
        return False
    clauses = [
        "conversation_id = ?",
        "author_id = ?",
        "source = ?",
    ]
    params: list[Any] = [
        str(conversation["conversation_id"]),
        str(participant_id),
        "user",
    ]
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    cur = conn.execute(
        f"""
        SELECT 1
        FROM chat_conversation_messages
        WHERE {' AND '.join(clauses)}
        ORDER BY message_id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return row_to_dict(cur.fetchone()) is not None


def _post_chat_followup_status_key(side: str) -> str:
    return "followup_a_status" if side == "a" else "followup_b_status"

def _post_chat_side_state(session: dict[str, Any], side: str) -> tuple[str, str, str, str]:
    if side == "a":
        return (
            str(session.get("participant_a_id") or ""),
            "assistant_dm_a",
            TASK_REASON_POST_CHAT_FOLLOWUP_A,
            _post_chat_followup_status_key("a"),
        )
    return (
        str(session.get("participant_b_id") or ""),
        "assistant_dm_b",
        TASK_REASON_POST_CHAT_FOLLOWUP_B,
        _post_chat_followup_status_key("b"),
    )


def _has_any_post_chat_user_dm_since(
    conn,
    *,
    session: dict[str, Any],
    since: datetime | None,
) -> bool:
    for side in ("a", "b"):
        participant_id, channel_key, _, _ = _post_chat_side_state(session, side)
        if not participant_id:
            continue
        if _has_user_channel_message_since(
            conn,
            case_id=str(session["case_id"]),
            channel_key=channel_key,
            participant_id=participant_id,
            since=since,
        ):
            return True
    return False


def enqueue_due_opening_probe_tasks(
    conn,
    *,
    limit: int = 10,
    opening_seconds: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    lim = max(1, min(int(limit), 100))
    cutoff = ts - timedelta(seconds=max(10, int(opening_seconds)))
    cur = conn.execute(
        """
        SELECT
          c.case_id,
          c.conversation_id,
          c.relation_key,
          c.metadata_json,
          c.created_at,
          s.session_id,
          s.status AS session_status,
          s.last_user_message_at
        FROM chat_conversations c
        LEFT JOIN chat_agent_sessions s
          ON s.case_id = c.case_id
        WHERE c.channel_key = ?
          AND c.status = ?
          AND c.created_at <= ?
        ORDER BY c.created_at ASC, c.case_id ASC
        LIMIT ?
        """,
        (
            "main_group",
            SESSION_STATUS_OPEN,
            cutoff,
            max(lim * 5, lim),
        ),
    )
    examined = 0
    enqueued_refs: list[dict[str, Any]] = []
    rows = [_inflate_main_group_conversation_row(row_to_dict(raw)) for raw in cur.fetchall()]
    case_ids = [str(row.get("case_id") or "").strip() for row in rows]
    session_pending = _session_ids_with_pending_tasks(
        conn,
        [str(row.get("session_id") or "").strip() for row in rows],
    )
    latest_main_by_case = _latest_main_group_messages_by_case(conn, case_ids)
    cases_with_any_messages = _case_ids_with_any_messages(conn, case_ids)
    eligible_rows: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        examined += 1
        session_status = str(row.get("session_status") or "").strip()
        if session_status and session_status != SESSION_STATUS_OPEN:
            continue
        if _coerce_dt(row.get("last_user_message_at")) is not None:
            continue
        session_id = str(row.get("session_id") or "").strip()
        if session_id and session_id in session_pending:
            continue
        case_id = str(row.get("case_id") or "").strip()
        latest_bundle = latest_main_by_case.get(case_id)
        if latest_bundle is not None:
            continue
        if case_id in cases_with_any_messages:
            continue
        eligible_rows.append(row)
        if len(eligible_rows) >= lim:
            break

    missing_session_payloads: list[tuple[str, str, str, str, str, str, str, datetime, datetime, datetime]] = []
    for row in eligible_rows:
        if str(row.get("session_id") or "").strip():
            continue
        session_id = _generate_session_id()
        session_spec = _derive_session_spec_from_main_group_row(row)
        row["_resolved_session_id"] = session_id
        missing_session_payloads.append(
            (
                session_id,
                str(row["case_id"]),
                session_spec["relation_key"],
                SESSION_STATUS_OPEN,
                session_spec["participant_a_id"],
                session_spec["participant_b_id"],
                session_spec["agent_participant_id"],
                json_dumps({}),
                ts,
                ts,
                ts,
            )
        )
    if missing_session_payloads:
        with conn.driver_connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT IGNORE INTO chat_agent_sessions (
                  session_id, case_id, relation_key, status,
                  participant_a_id, participant_b_id, agent_participant_id,
                  state_json, started_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                missing_session_payloads,
            )
        conn.driver_connection.commit()

    sessions_by_case = get_agent_sessions_by_case_ids(
        conn,
        [str(row.get("case_id") or "").strip() for row in eligible_rows],
    )
    task_plan: list[tuple[str, dict[str, Any], str]] = []
    for row in eligible_rows:
        case_id = str(row.get("case_id") or "").strip()
        session = sessions_by_case.get(case_id)
        if not session:
            continue
        session_id = str(session["session_id"])
        dedupe_key = _build_agent_task_dedupe_key(session_id, 0, TASK_REASON_OPENING_PROBE)
        task_plan.append((dedupe_key, row, session_id))

    existing_tasks = get_agent_tasks_by_dedupe_keys(conn, [item[0] for item in task_plan])
    task_payloads = [
        (
            session_id,
            str(row["case_id"]),
            str(row["conversation_id"]),
            0,
            "",
            "main_group",
            TASK_REASON_OPENING_PROBE,
            TASK_STATUS_PENDING,
            dedupe_key,
            ts,
        )
        for dedupe_key, row, session_id in task_plan
        if dedupe_key not in existing_tasks
    ]
    if task_payloads:
        with conn.driver_connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT IGNORE INTO chat_agent_tasks (
                  session_id, case_id, trigger_conversation_id, trigger_message_id,
                  trigger_author_id, trigger_channel_key, reason, status, attempt_count,
                  lease_until, dedupe_key, result_json, error_text, created_at, started_at, finished_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, NULL, %s, NULL, NULL, %s, NULL, NULL)
                """,
                task_payloads,
            )
        conn.driver_connection.commit()
        existing_tasks.update(get_agent_tasks_by_dedupe_keys(conn, [item[0] for item in task_plan]))

    for dedupe_key, row, session_id in task_plan:
        task = existing_tasks.get(dedupe_key)
        if not task or dedupe_key in get_agent_tasks_by_dedupe_keys(conn, []):
            pass
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in get_agent_tasks_by_dedupe_keys(conn, []):
            pass
        if task and dedupe_key not in [item[0] for item in task_plan if item[0] in existing_tasks]:
            continue
        if task and _build_agent_task_dedupe_key(session_id, 0, TASK_REASON_OPENING_PROBE) not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key in get_agent_tasks_by_dedupe_keys(conn, []):
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in [key for key in existing_tasks]:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key not in existing_tasks:
            continue
        if task and dedupe_key in existing_tasks and task.get("created_at") == ts:
            enqueued_refs.append(
                {
                    "session_id": session_id,
                    "task_id": int(task["task_id"]),
                    "trigger_message_id": int(task["trigger_message_id"]),
                }
            )
    return {
        "examined_sessions": examined,
        "enqueued": len(enqueued_refs),
        "task_refs": enqueued_refs,
    }


def enqueue_due_silence_probe_tasks(
    conn,
    *,
    limit: int = 10,
    silence_seconds: int = 45,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    lim = max(1, min(int(limit), 100))
    cutoff = ts - timedelta(seconds=max(15, int(silence_seconds)))
    cur = conn.execute(
        """
        SELECT *
        FROM chat_agent_sessions
        WHERE status = ?
          AND last_user_message_at IS NOT NULL
          AND last_user_message_at <= ?
        ORDER BY last_user_message_at ASC, session_id ASC
        LIMIT ?
        """,
        (
            SESSION_STATUS_OPEN,
            cutoff,
            max(lim * 5, lim),
        ),
    )
    examined = 0
    enqueued_refs: list[dict[str, Any]] = []
    raw_rows = [row_to_dict(raw) for raw in cur.fetchall()]
    sessions = [_inflate_session(row) for row in raw_rows]
    hydrated_sessions = [session for session in sessions if session]
    session_pending = _session_ids_with_pending_tasks(
        conn,
        [str(session["session_id"]) for session in hydrated_sessions],
    )
    latest_main_by_case = _latest_main_group_messages_by_case(
        conn,
        [str(session["case_id"]) for session in hydrated_sessions],
    )
    for session in hydrated_sessions:
        if len(enqueued_refs) >= lim:
            break
        state = dict(session.get("state") or {})
        if str(state.get("phase") or "") in POST_CHAT_PHASES:
            continue
        if is_public_followup_active(session):
            continue
        examined += 1
        if str(session["session_id"]) in session_pending:
            continue
        latest_bundle = latest_main_by_case.get(str(session["case_id"]))
        if not latest_bundle:
            continue
        conversation, message = latest_bundle
        message_created_at = _coerce_dt(message.get("created_at"))
        if not message_created_at or message_created_at > cutoff:
            continue
        if str(message.get("source") or "") != "user":
            continue
        task = enqueue_agent_task(
            conn,
            session_id=str(session["session_id"]),
            case_id=str(session["case_id"]),
            trigger_conversation_id=str(conversation["conversation_id"]),
            trigger_message_id=int(message["message_id"]),
            trigger_author_id=str(message["author_id"]),
            trigger_channel_key="main_group",
            reason=TASK_REASON_SILENCE_PROBE,
            update_last_user_message_at=False,
            now=ts,
        )
        if task.get("_inserted"):
            enqueued_refs.append(
                {
                    "session_id": str(session["session_id"]),
                    "task_id": int(task["task_id"]),
                    "trigger_message_id": int(message["message_id"]),
                }
            )
    return {
        "examined_sessions": examined,
        "enqueued": len(enqueued_refs),
        "task_refs": enqueued_refs,
    }


def enqueue_due_post_chat_followup_tasks(
    conn,
    *,
    limit: int = 10,
    followup_seconds: int = 720,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    lim = max(1, min(int(limit), 100))
    cutoff = ts - timedelta(seconds=max(60, int(followup_seconds)))
    cur = conn.execute(
        """
        SELECT *
        FROM chat_agent_sessions
        WHERE status = ?
        ORDER BY updated_at ASC, session_id ASC
        LIMIT ?
        """,
        (
            SESSION_STATUS_OPEN,
            max(lim * 10, lim),
        ),
    )

    examined = 0
    enqueued_refs: list[dict[str, Any]] = []
    raw_rows = [row_to_dict(raw) for raw in cur.fetchall()]
    sessions = [_inflate_session(row) for row in raw_rows]
    hydrated_sessions = [session for session in sessions if session]
    session_pending = _session_ids_with_pending_tasks(
        conn,
        [str(session["session_id"]) for session in hydrated_sessions],
    )
    latest_main_by_case = _latest_main_group_messages_by_case(
        conn,
        [str(session["case_id"]) for session in hydrated_sessions],
    )
    main_group_conversations = _main_group_conversations_by_case(
        conn,
        [str(session["case_id"]) for session in hydrated_sessions],
    )
    for session in hydrated_sessions:
        state = dict(session.get("state") or {})
        if str(state.get("phase") or "") not in {"post_chat_ready", "post_chat_followup"}:
            continue
        examined += 1
        if str(session["session_id"]) in session_pending:
            continue

        chat_end_at = _coerce_dt(state.get("chat_end_at"))
        chat_end_message_id = int(state.get("chat_end_message_id") or 0)
        if not chat_end_at or chat_end_at > cutoff or chat_end_message_id <= 0:
            continue

        latest_bundle = latest_main_by_case.get(str(session["case_id"]))
        if latest_bundle:
            _, latest_main_message = latest_bundle
            latest_main_created_at = _coerce_dt(latest_main_message.get("created_at"))
            latest_main_message_id = int(latest_main_message.get("message_id") or 0)
            if latest_main_message_id > chat_end_message_id and (
                latest_main_created_at is None or latest_main_created_at >= chat_end_at
            ):
                state["phase"] = "active"
                state["post_chat_cancelled_at"] = str(ts)
                _write_session_state(conn, str(session["session_id"]), state, now=ts)
                continue

        if str(state.get("post_chat_review_status") or "").strip():
            continue

        if _has_any_post_chat_user_dm_since(conn, session=session, since=chat_end_at):
            state["phase"] = "post_chat_followup"
            state["post_chat_review_status"] = "user_initiated"
            _write_session_state(conn, str(session["session_id"]), state, now=ts)
            continue

        conversation = main_group_conversations.get(str(session["case_id"]))
        if not conversation:
            continue
        task = enqueue_agent_task(
            conn,
            session_id=str(session["session_id"]),
            case_id=str(session["case_id"]),
            trigger_conversation_id=str(conversation["conversation_id"]),
            trigger_message_id=chat_end_message_id,
            trigger_author_id="",
            trigger_channel_key="main_group",
            reason=TASK_REASON_POST_CHAT_REVIEW,
            update_last_user_message_at=False,
            now=ts,
        )
        if task.get("_inserted"):
            enqueued_refs.append(
                {
                    "session_id": str(session["session_id"]),
                    "task_id": int(task["task_id"]),
                    "trigger_message_id": chat_end_message_id,
                    "target_channel_key": "main_group",
                }
            )
            state["phase"] = "post_chat_followup"
            state["post_chat_review_status"] = "queued"
            _write_session_state(conn, str(session["session_id"]), state, now=ts)
            if len(enqueued_refs) >= lim:
                break

    return {
        "examined_sessions": examined,
        "enqueued": len(enqueued_refs),
        "task_refs": enqueued_refs,
    }


def claim_pending_agent_tasks(
    conn,
    *,
    limit: int = 10,
    lease_seconds: int = 180,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    ts = current_time(now)
    lease_until = ts + timedelta(seconds=max(30, int(lease_seconds)))
    lim = max(1, min(int(limit), 100))
    cur = conn.execute(
        """
        SELECT task_id
        FROM chat_agent_tasks
        WHERE status = ?
           OR (status = ? AND lease_until IS NOT NULL AND lease_until < ?)
        ORDER BY created_at ASC, task_id ASC
        LIMIT ?
        """,
        (
            TASK_STATUS_PENDING,
            TASK_STATUS_RUNNING,
            ts,
            lim,
        ),
    )
    claimed_task_ids: list[int] = []
    for raw in cur.fetchall():
        task_id = int(raw["task_id"])
        res = conn.execute(
            """
            UPDATE chat_agent_tasks
            SET status = ?,
                attempt_count = attempt_count + 1,
                lease_until = ?,
                started_at = ?,
                finished_at = NULL
            WHERE task_id = ?
              AND (
                status = ?
                OR (status = ? AND lease_until IS NOT NULL AND lease_until < ?)
              )
            """,
            (
                TASK_STATUS_RUNNING,
                lease_until,
                ts,
                task_id,
                TASK_STATUS_PENDING,
                TASK_STATUS_RUNNING,
                ts,
            ),
        )
        if int(res.rowcount or 0) <= 0:
            continue
        claimed_task_ids.append(task_id)
    if not claimed_task_ids:
        return []
    tasks_by_id = get_agent_tasks_by_ids(conn, claimed_task_ids)
    return [tasks_by_id[task_id] for task_id in claimed_task_ids if task_id in tasks_by_id]


def complete_agent_task(
    conn,
    task_id: int,
    *,
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    conn.execute(
        """
        UPDATE chat_agent_tasks
        SET status = ?,
            lease_until = NULL,
            result_json = ?,
            error_text = NULL,
            finished_at = ?
        WHERE task_id = ?
        """,
        (
            TASK_STATUS_COMPLETED,
            json_dumps(result if result is not None else {}),
            ts,
            int(task_id),
        ),
    )


def fail_agent_task(
    conn,
    task_id: int,
    *,
    error_text: str,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    conn.execute(
        """
        UPDATE chat_agent_tasks
        SET status = ?,
            lease_until = NULL,
            error_text = ?,
            finished_at = ?
        WHERE task_id = ?
        """,
        (
            TASK_STATUS_FAILED,
            str(error_text or "")[:10000],
            ts,
            int(task_id),
        ),
    )


def apply_agent_session_outcome(
    conn,
    session_id: str,
    *,
    task_id: int,
    trigger_message_id: int,
    reply_message_id: int | None,
    reply_message_ids: list[int] | None = None,
    reason_codes: list[str] | None = None,
    state_patch: dict[str, Any] | None = None,
    public_followup: dict[str, Any] | None = None,
    cooldown_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    session = get_agent_session(conn, session_id)
    if not session:
        raise ValueError("agent session not found")
    ts = current_time(now)
    state = dict(session.get("state") or {})
    if isinstance(state_patch, dict):
        state.update(state_patch)
    if isinstance(public_followup, dict):
        active = bool(public_followup.get("active"))
        mode = str(public_followup.get("mode") or "").strip()
        state["public_followup_active"] = active
        if active and mode in PUBLIC_FOLLOWUP_MODES:
            state["public_followup_mode"] = mode
        elif not active:
            state.pop("public_followup_mode", None)
    if str(state.get("phase") or "").strip() in POST_CHAT_PHASES:
        state["public_followup_active"] = False
        state.pop("public_followup_mode", None)
    if reason_codes is not None:
        state["last_reason_codes"] = [str(code) for code in reason_codes]
    state["last_task_id"] = int(task_id)
    state["last_trigger_message_id"] = int(trigger_message_id)
    if reply_message_id is not None:
        state["last_reply_message_id"] = int(reply_message_id)
    if reply_message_ids:
        state["last_reply_message_ids"] = [int(message_id) for message_id in reply_message_ids]

    if cooldown_seconds is None:
        cooldown_until = session.get("cooldown_until")
    elif int(cooldown_seconds) <= 0:
        cooldown_until = None
    else:
        cooldown_until = ts + timedelta(seconds=int(cooldown_seconds))

    conn.execute(
        """
        UPDATE chat_agent_sessions
        SET status = ?,
            last_seen_message_id = CASE
              WHEN last_seen_message_id IS NULL OR last_seen_message_id < ? THEN ?
              ELSE last_seen_message_id
            END,
            last_agent_message_at = ?,
            last_replied_at = ?,
            cooldown_until = ?,
            state_json = ?,
            updated_at = ?
        WHERE session_id = ?
        """,
        (
            SESSION_STATUS_OPEN,
            int(trigger_message_id),
            int(trigger_message_id),
            ts if reply_message_id is not None else session.get("last_agent_message_at"),
            ts if reply_message_id is not None else session.get("last_replied_at"),
            cooldown_until,
            json_dumps(state),
            ts,
            session_id,
        ),
    )
    updated = get_agent_session(conn, session_id)
    assert updated is not None
    return updated


def close_idle_agent_sessions(
    conn,
    *,
    idle_seconds: int = 10800,
    now: datetime | None = None,
) -> int:
    ts = current_time(now)
    cutoff = ts - timedelta(seconds=max(60, int(idle_seconds)))
    cur = conn.execute(
        """
        SELECT session_id
        FROM chat_agent_sessions
        WHERE status = ?
          AND (
            (last_user_message_at IS NOT NULL AND last_user_message_at < ?)
            OR (last_user_message_at IS NULL AND updated_at < ?)
          )
        ORDER BY updated_at ASC, session_id ASC
        """,
        (
            SESSION_STATUS_OPEN,
            cutoff,
            cutoff,
        ),
    )
    closed = 0
    for raw in cur.fetchall():
        session_id = str(raw["session_id"])
        pending = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM chat_agent_tasks
            WHERE session_id = ? AND status IN (?, ?)
            """,
            (
                session_id,
                TASK_STATUS_PENDING,
                TASK_STATUS_RUNNING,
            ),
        ).fetchone()
        if pending and int(pending["c"]) > 0:
            continue
        res = conn.execute(
            """
            UPDATE chat_agent_sessions
            SET status = ?,
                close_reason = ?,
                ended_at = ?,
                updated_at = ?
            WHERE session_id = ? AND status = ?
            """,
            (
                SESSION_STATUS_CLOSED,
                "idle_timeout",
                ts,
                ts,
                session_id,
                SESSION_STATUS_OPEN,
            ),
        )
        closed += int(res.rowcount or 0)
    return closed


__all__ = [
    "PUBLIC_FOLLOWUP_MODE_OPENING",
    "PUBLIC_FOLLOWUP_MODE_SILENCE",
    "SESSION_STATUS_CLOSED",
    "SESSION_STATUS_OPEN",
    "TASK_REASON_OPENING_PROBE",
    "TASK_REASON_POST_CHAT_REVIEW",
    "TASK_REASON_POST_CHAT_FOLLOWUP_A",
    "TASK_REASON_POST_CHAT_FOLLOWUP_B",
    "TASK_REASON_SILENCE_PROBE",
    "TASK_REASON_USER_MESSAGE",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_FAILED",
    "TASK_STATUS_PENDING",
    "TASK_STATUS_RUNNING",
    "apply_agent_session_outcome",
    "claim_pending_agent_tasks",
    "close_idle_agent_sessions",
    "complete_agent_task",
    "current_time",
    "enqueue_due_opening_probe_tasks",
    "enqueue_due_post_chat_followup_tasks",
    "enqueue_due_silence_probe_tasks",
    "enqueue_agent_task",
    "fail_agent_task",
    "get_agent_session",
    "get_agent_session_by_case",
    "get_agent_task",
    "get_or_create_agent_session",
    "is_public_followup_active",
    "list_agent_tasks",
    "record_agent_session_user_activity",
]
