"""Multi-conversation case chat model for A-C / B-C / A-B-C assistant layouts."""

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

from .events import (
    chat_conversation_message_created_event,
    chat_conversation_opened_event,
)
from .storage import inflate_json_columns, json_dumps, row_to_dict

CONV_KIND_DM = "dm"
CONV_KIND_GROUP = "group"

ROLE_HUMAN = "human"
ROLE_AGENT = "agent"
ROLE_SYSTEM = "system"

SOURCE_USER = "user"
SOURCE_AGENT = "agent"
SOURCE_SYSTEM = "system"

LAYOUT_ROLE_MAIN_GROUP = "main_group"
LAYOUT_ROLE_ASSISTANT_DM_A = "assistant_dm_a"
LAYOUT_ROLE_ASSISTANT_DM_B = "assistant_dm_b"


def _generate_conversation_id() -> str:
    return f"cvt-{uuid.uuid4().hex[:16]}"


def _inflate_conversation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def _inflate_member(row: dict[str, Any] | None) -> dict[str, Any] | None:
    out = inflate_json_columns(row, metadata=("metadata_json", {}))
    if not out:
        return None
    out["can_read"] = bool(out.get("can_read"))
    out["can_send"] = bool(out.get("can_send"))
    return out


def _inflate_message(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def _normalize_member_specs(member_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(member_specs, list) or not member_specs:
        raise ValueError("member_specs must be a non-empty list")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in member_specs:
        participant_id = str((raw or {}).get("participant_id") or "").strip()
        if not participant_id:
            raise ValueError("participant_id is required for every member")
        if participant_id in seen:
            raise ValueError("duplicate participant_id in member_specs")
        seen.add(participant_id)
        member_role = str((raw or {}).get("member_role") or ROLE_HUMAN).strip() or ROLE_HUMAN
        if member_role not in {ROLE_HUMAN, ROLE_AGENT, ROLE_SYSTEM}:
            raise ValueError("invalid member_role")
        out.append(
            {
                "participant_id": participant_id,
                "member_role": member_role,
                "can_read": 1 if bool((raw or {}).get("can_read", True)) else 0,
                "can_send": 1 if bool((raw or {}).get("can_send", True)) else 0,
                "metadata": dict((raw or {}).get("metadata") or {}),
            }
        )
    return out


def _layout_sort_rank(conversation: dict[str, Any]) -> tuple[int, str]:
    layout_role = str((conversation.get("metadata") or {}).get("layout_role") or "")
    rank = {
        LAYOUT_ROLE_MAIN_GROUP: 0,
        LAYOUT_ROLE_ASSISTANT_DM_A: 1,
        LAYOUT_ROLE_ASSISTANT_DM_B: 2,
    }.get(layout_role, 99)
    return rank, str(conversation.get("conversation_id") or "")


def get_conversation(conn, conversation_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_conversations WHERE conversation_id = ? LIMIT 1",
        (conversation_id,),
    )
    return _inflate_conversation(row_to_dict(cur.fetchone()))


def get_conversation_by_case_and_key(conn, case_id: str, channel_key: str) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT * FROM chat_conversations
        WHERE case_id = ? AND channel_key = ?
        LIMIT 1
        """,
        (case_id, channel_key),
    )
    return _inflate_conversation(row_to_dict(cur.fetchone()))


def list_conversation_members(conn, conversation_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM chat_conversation_members
        WHERE conversation_id = ?
        ORDER BY joined_at ASC, participant_id ASC
        """,
        (conversation_id,),
    )
    rows = [_inflate_member(row_to_dict(row)) for row in cur.fetchall()]
    return [row for row in rows if row]


def get_conversation_member(
    conn,
    conversation_id: str,
    participant_id: str,
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT * FROM chat_conversation_members
        WHERE conversation_id = ? AND participant_id = ?
        LIMIT 1
        """,
        (conversation_id, participant_id),
    )
    return _inflate_member(row_to_dict(cur.fetchone()))


def _conversation_bundle(conn, conversation_id: str) -> dict[str, Any]:
    conversation = get_conversation(conn, conversation_id)
    if not conversation:
        raise ValueError("conversation not found")
    members = list_conversation_members(conn, conversation_id)
    return {**conversation, "members": members}


def _upsert_conversation_member(
    conn,
    conversation_id: str,
    *,
    participant_id: str,
    member_role: str,
    can_read: int,
    can_send: int,
    metadata: dict[str, Any] | None,
    joined_at: datetime,
) -> None:
    existing = get_conversation_member(conn, conversation_id, participant_id)
    payload = json_dumps(dict(metadata or {}))
    if not existing:
        conn.execute(
            """
            INSERT INTO chat_conversation_members (
              conversation_id, participant_id, member_role, can_read, can_send,
              metadata_json, joined_at, left_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                conversation_id,
                participant_id,
                member_role,
                int(can_read),
                int(can_send),
                payload,
                joined_at,
            ),
        )
        return
    conn.execute(
        """
        UPDATE chat_conversation_members
        SET member_role = ?,
            can_read = ?,
            can_send = ?,
            metadata_json = ?,
            left_at = NULL
        WHERE conversation_id = ? AND participant_id = ?
        """,
        (
            member_role,
            int(can_read),
            int(can_send),
            payload,
            conversation_id,
            participant_id,
        ),
    )


def get_or_create_conversation(
    conn,
    *,
    case_id: str,
    relation_key: str,
    channel_key: str,
    conversation_kind: str,
    member_specs: list[dict[str, Any]],
    conversation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    case_id = str(case_id or "").strip()
    relation_key = str(relation_key or "").strip()
    channel_key = str(channel_key or "").strip()
    if not case_id:
        raise ValueError("case_id is required")
    if not relation_key:
        raise ValueError("relation_key is required")
    if not channel_key:
        raise ValueError("channel_key is required")
    if conversation_kind not in {CONV_KIND_DM, CONV_KIND_GROUP}:
        raise ValueError("invalid conversation_kind")

    members = _normalize_member_specs(member_specs)
    existing = get_conversation_by_case_and_key(conn, case_id, channel_key)
    ts = current_time(now)
    if existing:
        for member in members:
            _upsert_conversation_member(
                conn,
                existing["conversation_id"],
                participant_id=str(member["participant_id"]),
                member_role=str(member["member_role"]),
                can_read=int(member["can_read"]),
                can_send=int(member["can_send"]),
                metadata=dict(member["metadata"]),
                joined_at=ts,
            )
        conn.commit()
        return _conversation_bundle(conn, str(existing["conversation_id"]))

    explicit_conversation_id = str(conversation_id or "").strip() or None
    if explicit_conversation_id and len(explicit_conversation_id) > 64:
        raise ValueError("conversation_id must be 64 characters or fewer")
    conversation_id = explicit_conversation_id or _generate_conversation_id()
    try:
        conn.execute(
            """
            INSERT INTO chat_conversations (
              conversation_id, case_id, relation_key, channel_key, conversation_kind,
              status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                case_id,
                relation_key,
                channel_key,
                conversation_kind,
                "open",
                json_dumps(dict(metadata or {})),
                ts,
                ts,
            ),
        )
        for member in members:
            _upsert_conversation_member(
                conn,
                conversation_id,
                participant_id=str(member["participant_id"]),
                member_role=str(member["member_role"]),
                can_read=int(member["can_read"]),
                can_send=int(member["can_send"]),
                metadata=dict(member["metadata"]),
                joined_at=ts,
            )
        append_outbox_pending(
            conn,
            event=chat_conversation_opened_event(
                conversation_id=conversation_id,
                case_id=case_id,
                relation_key=relation_key,
                channel_key=channel_key,
                conversation_kind=conversation_kind,
                participant_ids=[str(member["participant_id"]) for member in members],
                occurred_at=ts,
            ),
            source_row_table="chat_conversations",
            source_row_id=None,
            created_at_str=ts.isoformat(sep=" "),
        )
        conn.commit()
        funnel_stage(
            system="chat",
            stage=CHAT_FUNNEL_THREAD_OPEN,
            trace_id=get_trace_id(),
            case_id=case_id,
            thread_id=conversation_id,
            relation_key=relation_key,
            channel_key=channel_key,
            conversation_kind=conversation_kind,
        )
    except IntegrityError:
        conn.rollback()
        existing2 = get_conversation_by_case_and_key(conn, case_id, channel_key)
        if existing2:
            return _conversation_bundle(conn, str(existing2["conversation_id"]))
        raise

    return _conversation_bundle(conn, conversation_id)


def create_assistant_case_layout(
    conn,
    *,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    agent_id: str,
    conversation_ids: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    participant_a_id = str(participant_a_id or "").strip()
    participant_b_id = str(participant_b_id or "").strip()
    agent_id = str(agent_id or "").strip()
    if not participant_a_id or not participant_b_id or not agent_id:
        raise ValueError("participant_a_id, participant_b_id, and agent_id are required")
    if len({participant_a_id, participant_b_id, agent_id}) != 3:
        raise ValueError("participant_a_id, participant_b_id, and agent_id must be distinct")

    base_metadata = dict(metadata or {})
    conv_ids = dict(conversation_ids or {})
    main = get_or_create_conversation(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="main_group",
        conversation_kind=CONV_KIND_GROUP,
        conversation_id=conv_ids.get("main_group"),
        member_specs=[
            {"participant_id": participant_a_id, "member_role": ROLE_HUMAN},
            {"participant_id": participant_b_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        metadata={
            **base_metadata,
            "layout_role": LAYOUT_ROLE_MAIN_GROUP,
            "participant_a_id": participant_a_id,
            "participant_b_id": participant_b_id,
            "agent_id": agent_id,
        },
        now=now,
    )
    dm_a = get_or_create_conversation(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="assistant_dm_a",
        conversation_kind=CONV_KIND_DM,
        conversation_id=conv_ids.get("assistant_dm_a"),
        member_specs=[
            {"participant_id": participant_a_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        metadata={
            **base_metadata,
            "layout_role": LAYOUT_ROLE_ASSISTANT_DM_A,
            "owner_user_id": participant_a_id,
            "agent_id": agent_id,
        },
        now=now,
    )
    dm_b = get_or_create_conversation(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="assistant_dm_b",
        conversation_kind=CONV_KIND_DM,
        conversation_id=conv_ids.get("assistant_dm_b"),
        member_specs=[
            {"participant_id": participant_b_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        metadata={
            **base_metadata,
            "layout_role": LAYOUT_ROLE_ASSISTANT_DM_B,
            "owner_user_id": participant_b_id,
            "agent_id": agent_id,
        },
        now=now,
    )
    conversations = sorted([main, dm_a, dm_b], key=_layout_sort_rank)
    return {
        "case_id": case_id,
        "relation_key": relation_key,
        "participant_a_id": participant_a_id,
        "participant_b_id": participant_b_id,
        "agent_id": agent_id,
        "conversation_count": len(conversations),
        "conversations": conversations,
    }


def list_case_conversations(
    conn,
    case_id: str,
    requester_id: str | None = None,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM chat_conversations
        WHERE case_id = ?
        ORDER BY created_at ASC, conversation_id ASC
        """,
        (case_id,),
    )
    conversations = [_inflate_conversation(row_to_dict(row)) for row in cur.fetchall()]
    out: list[dict[str, Any]] = []
    requester = str(requester_id or "").strip()
    for conversation in conversations:
        if not conversation:
            continue
        members = list_conversation_members(conn, str(conversation["conversation_id"]))
        if requester:
            member_map = {str(member["participant_id"]): member for member in members}
            requester_member = member_map.get(requester)
            if not requester_member or not requester_member.get("can_read"):
                continue
        out.append({**conversation, "members": members})
    return sorted(out, key=_layout_sort_rank)


def _require_read_member(conn, conversation_id: str, requester_id: str) -> dict[str, Any]:
    conversation = get_conversation(conn, conversation_id)
    if not conversation:
        raise ValueError("conversation not found")
    member = get_conversation_member(conn, conversation_id, requester_id)
    if not member or not member.get("can_read"):
        raise ValueError("requester is not allowed to read this conversation")
    return conversation


def list_conversation_messages(
    conn,
    conversation_id: str,
    requester_id: str,
    *,
    limit: int = 50,
    before_message_id: int | None = None,
) -> list[dict[str, Any]]:
    _require_read_member(conn, conversation_id, requester_id)
    lim = max(1, min(int(limit), 500))
    params: list[Any] = [conversation_id]
    before_clause = ""
    if before_message_id is not None:
        before_clause = "AND message_id < ?"
        params.append(int(before_message_id))
    params.append(lim)
    cur = conn.execute(
        f"""
        SELECT * FROM chat_conversation_messages
        WHERE conversation_id = ?
          {before_clause}
        ORDER BY message_id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = [_inflate_message(row_to_dict(row)) for row in cur.fetchall()]
    rows = [row for row in rows if row]
    return list(reversed(rows))


def _maybe_enqueue_persona_sync_job_for_conversation(
    conn,
    conversation: dict[str, Any],
    *,
    author_member: dict[str, Any],
    message_id: int,
    author_id: str,
    body: str,
    source: str,
    metadata: dict[str, Any] | None,
    ts: datetime,
) -> None:
    # Persona updates are intentionally deferred until post-chat review.
    # Live conversation messages should not enqueue sync jobs directly.
    return


def post_conversation_message(
    conn,
    conversation_id: str,
    author_id: str,
    body: str,
    *,
    source: str | None = None,
    client_msg_id: str | None = None,
    reply_to_message_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    conversation = get_conversation(conn, conversation_id)
    if not conversation:
        raise ValueError("conversation not found")
    author_id = str(author_id or "").strip()
    if not author_id:
        raise ValueError("author_id is required")
    body_text = str(body or "")
    if not body_text:
        raise ValueError("body is required")

    author_member = get_conversation_member(conn, conversation_id, author_id)
    resolved_source = str(source or "").strip() or None
    if resolved_source == SOURCE_SYSTEM:
        author_member = None
    else:
        if not author_member or not author_member.get("can_send"):
            raise ValueError("author is not allowed to send in this conversation")
        inferred_source = SOURCE_AGENT if author_member.get("member_role") == ROLE_AGENT else SOURCE_USER
        resolved_source = resolved_source or inferred_source
        if resolved_source not in {SOURCE_USER, SOURCE_AGENT}:
            raise ValueError("invalid source")
        if resolved_source == SOURCE_AGENT and author_member.get("member_role") != ROLE_AGENT:
            raise ValueError("only agent members may use source=agent")
        if resolved_source == SOURCE_USER and author_member.get("member_role") == ROLE_AGENT:
            raise ValueError("agent members must use source=agent")

    ts = current_time(now)
    cmid = str(client_msg_id or "").strip() or None
    if cmid:
        cmid = cmid[:191]
        cur = conn.execute(
            """
            SELECT * FROM chat_conversation_messages
            WHERE conversation_id = ? AND client_msg_id = ?
            LIMIT 1
            """,
            (conversation_id, cmid),
        )
        existing = _inflate_message(row_to_dict(cur.fetchone()))
        if existing:
            return dict(existing)

    try:
        conn.execute(
            """
            INSERT INTO chat_conversation_messages (
              conversation_id, author_id, source, body, client_msg_id,
              reply_to_message_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                author_id,
                resolved_source,
                body_text,
                cmid,
                reply_to_message_id,
                json_dumps(dict(metadata or {})),
                ts,
            ),
        )
        inserted_id = int(conn.lastrowid)
        conn.execute(
            "UPDATE chat_conversations SET updated_at = ? WHERE conversation_id = ?",
            (ts, conversation_id),
        )
        append_outbox_pending(
            conn,
            event=chat_conversation_message_created_event(
                conversation_id=conversation_id,
                case_id=str(conversation["case_id"]),
                message_id=inserted_id,
                channel_key=str(conversation["channel_key"]),
                author_id=author_id,
                body=body_text,
                source=str(resolved_source),
                occurred_at=ts,
            ),
            source_row_table="chat_conversation_messages",
            source_row_id=inserted_id,
            created_at_str=ts.isoformat(sep=" "),
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()
        if cmid:
            cur = conn.execute(
                """
                SELECT * FROM chat_conversation_messages
                WHERE conversation_id = ? AND client_msg_id = ?
                LIMIT 1
                """,
                (conversation_id, cmid),
            )
            existing = _inflate_message(row_to_dict(cur.fetchone()))
            if existing:
                return dict(existing)
        raise

    cur = conn.execute(
        "SELECT * FROM chat_conversation_messages WHERE message_id = ? LIMIT 1",
        (inserted_id,),
    )
    row = _inflate_message(row_to_dict(cur.fetchone()))
    assert row is not None

    if author_member is not None:
        _maybe_enqueue_persona_sync_job_for_conversation(
            conn,
            conversation,
            author_member=author_member,
            message_id=inserted_id,
            author_id=author_id,
            body=body_text,
            source=str(resolved_source),
            metadata=metadata,
            ts=ts,
        )
        conn.commit()

    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_MESSAGE_SEND,
        trace_id=get_trace_id(),
        case_id=str(conversation["case_id"]),
        thread_id=conversation_id,
        channel_key=str(conversation["channel_key"]),
        conversation_kind=str(conversation["conversation_kind"]),
        message_id=inserted_id,
        author_id=author_id,
        source=str(resolved_source),
    )
    return dict(row)


def build_case_conversation_timeline(
    conn,
    case_id: str,
    requester_id: str,
    *,
    message_limit: int = 50,
) -> dict[str, Any]:
    conversations = list_case_conversations(conn, case_id, requester_id=requester_id)
    out: list[dict[str, Any]] = []
    for conversation in conversations:
        out.append(
            {
                "conversation": conversation,
                "messages": list_conversation_messages(
                    conn,
                    str(conversation["conversation_id"]),
                    requester_id,
                    limit=message_limit,
                ),
            }
        )
    return {
        "case_id": case_id,
        "requester_id": requester_id,
        "conversation_count": len(out),
        "conversations": out,
    }


__all__ = [
    "CONV_KIND_DM",
    "CONV_KIND_GROUP",
    "LAYOUT_ROLE_ASSISTANT_DM_A",
    "LAYOUT_ROLE_ASSISTANT_DM_B",
    "LAYOUT_ROLE_MAIN_GROUP",
    "ROLE_AGENT",
    "ROLE_HUMAN",
    "ROLE_SYSTEM",
    "SOURCE_AGENT",
    "SOURCE_SYSTEM",
    "SOURCE_USER",
    "build_case_conversation_timeline",
    "create_assistant_case_layout",
    "current_time",
    "get_conversation",
    "get_conversation_by_case_and_key",
    "get_conversation_member",
    "get_or_create_conversation",
    "list_case_conversations",
    "list_conversation_members",
    "list_conversation_messages",
    "post_conversation_message",
]
