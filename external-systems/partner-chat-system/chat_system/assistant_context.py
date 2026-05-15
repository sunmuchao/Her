"""Context-loading helpers for the matchmaker agent."""

from __future__ import annotations

from typing import Any

from .persona_source import load_public_profile_from_persona_source
from .conversations import get_conversation_by_case_and_key, list_case_conversations
from .storage import inflate_json_columns, row_to_dict


def _inflate_case_message(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}))


def list_recent_case_messages(
    conn,
    case_id: str,
    *,
    limit: int = 30,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    params: list[Any] = [case_id]
    conversation_clause = ""
    if conversation_id:
        conversation_clause = "AND c.conversation_id = ?"
        params.append(str(conversation_id))
    params.append(lim)
    cur = conn.execute(
        f"""
        SELECT
          m.message_id,
          m.conversation_id,
          c.case_id,
          c.channel_key,
          c.conversation_kind,
          m.author_id,
          m.source,
          m.body,
          m.reply_to_message_id,
          m.metadata_json,
          m.created_at
        FROM chat_conversation_messages m
        JOIN chat_conversations c
          ON c.conversation_id = m.conversation_id
        WHERE c.case_id = ?
          {conversation_clause}
        ORDER BY m.message_id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = [_inflate_case_message(row_to_dict(row)) for row in cur.fetchall()]
    return list(reversed([row for row in rows if row]))


def search_case_history(
    conn,
    case_id: str,
    query: str,
    *,
    channel_key: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return []
    lim = max(1, min(int(limit), 100))
    params: list[Any] = [case_id]
    channel_clause = ""
    if channel_key:
        channel_clause = "AND c.channel_key = ?"
        params.append(str(channel_key))
    params.extend([f"%{text}%", lim])
    cur = conn.execute(
        f"""
        SELECT
          m.message_id,
          m.conversation_id,
          c.case_id,
          c.channel_key,
          c.conversation_kind,
          m.author_id,
          m.source,
          m.body,
          m.reply_to_message_id,
          m.metadata_json,
          m.created_at
        FROM chat_conversation_messages m
        JOIN chat_conversations c
          ON c.conversation_id = m.conversation_id
        WHERE c.case_id = ?
          {channel_clause}
          AND m.body LIKE ?
        ORDER BY m.message_id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = [_inflate_case_message(row_to_dict(row)) for row in cur.fetchall()]
    return [row for row in rows if row]


def get_message_window(
    conn,
    case_id: str,
    message_id: int,
    *,
    before: int = 3,
    after: int = 3,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT
          m.message_id,
          m.conversation_id,
          c.case_id,
          c.channel_key,
          c.conversation_kind,
          m.author_id,
          m.source,
          m.body,
          m.reply_to_message_id,
          m.metadata_json,
          m.created_at
        FROM chat_conversation_messages m
        JOIN chat_conversations c
          ON c.conversation_id = m.conversation_id
        WHERE c.case_id = ? AND m.message_id = ?
        LIMIT 1
        """,
        (case_id, int(message_id)),
    )
    pivot = _inflate_case_message(row_to_dict(cur.fetchone()))
    if not pivot:
        return []
    before_lim = max(0, min(int(before), 20))
    after_lim = max(0, min(int(after), 20))
    rows_before: list[dict[str, Any]] = []
    rows_after: list[dict[str, Any]] = []
    if before_lim > 0:
        cur = conn.execute(
            """
            SELECT
              m.message_id,
              m.conversation_id,
              c.case_id,
              c.channel_key,
              c.conversation_kind,
              m.author_id,
              m.source,
              m.body,
              m.reply_to_message_id,
              m.metadata_json,
              m.created_at
            FROM chat_conversation_messages m
            JOIN chat_conversations c
              ON c.conversation_id = m.conversation_id
            WHERE c.case_id = ?
              AND m.conversation_id = ?
              AND m.message_id < ?
            ORDER BY m.message_id DESC
            LIMIT ?
            """,
            (
                case_id,
                pivot["conversation_id"],
                int(message_id),
                before_lim,
            ),
        )
        rows_before = [_inflate_case_message(row_to_dict(row)) for row in cur.fetchall()]
    if after_lim > 0:
        cur = conn.execute(
            """
            SELECT
              m.message_id,
              m.conversation_id,
              c.case_id,
              c.channel_key,
              c.conversation_kind,
              m.author_id,
              m.source,
              m.body,
              m.reply_to_message_id,
              m.metadata_json,
              m.created_at
            FROM chat_conversation_messages m
            JOIN chat_conversations c
              ON c.conversation_id = m.conversation_id
            WHERE c.case_id = ?
              AND m.conversation_id = ?
              AND m.message_id > ?
            ORDER BY m.message_id ASC
            LIMIT ?
            """,
            (
                case_id,
                pivot["conversation_id"],
                int(message_id),
                after_lim,
            ),
        )
        rows_after = [_inflate_case_message(row_to_dict(row)) for row in cur.fetchall()]
    return list(reversed([row for row in rows_before if row])) + [pivot] + [row for row in rows_after if row]


def list_case_conversation_catalog(conn, case_id: str) -> list[dict[str, Any]]:
    conversations = list_case_conversations(conn, case_id)
    out: list[dict[str, Any]] = []
    for conversation in conversations:
        out.append(
            {
                "conversation_id": conversation["conversation_id"],
                "channel_key": conversation["channel_key"],
                "conversation_kind": conversation["conversation_kind"],
                "status": conversation["status"],
                "metadata": dict(conversation.get("metadata") or {}),
                "members": [
                    {
                        "participant_id": member["participant_id"],
                        "member_role": member["member_role"],
                        "can_read": bool(member["can_read"]),
                        "can_send": bool(member["can_send"]),
                        "metadata": dict(member.get("metadata") or {}),
                    }
                    for member in conversation.get("members") or []
                ],
            }
        )
    return out

def get_profile_snapshot(conn, case_id: str, participant_id: str) -> dict[str, Any]:
    participant_id = str(participant_id or "").strip()
    main_group = get_conversation_by_case_and_key(conn, case_id, "main_group")
    metadata = dict((main_group or {}).get("metadata") or {})
    role = "unknown"
    profile_id = None
    profile = None
    persona = None

    if participant_id and participant_id == str(metadata.get("participant_a_id") or ""):
        role = "participant_a"
        profile_id = metadata.get("participant_a_profile_id")
        profile = metadata.get("participant_a_profile")
        persona = metadata.get("participant_a_persona")
    elif participant_id and participant_id == str(metadata.get("participant_b_id") or ""):
        role = "participant_b"
        profile_id = metadata.get("participant_b_profile_id")
        profile = metadata.get("participant_b_profile")
        persona = metadata.get("participant_b_persona")
    elif participant_id and participant_id == str(metadata.get("agent_id") or ""):
        role = "agent"

    candidate_profile_id = profile_id or (profile or {}).get("id")
    if candidate_profile_id is not None:
        public_profile = load_public_profile_from_persona_source(candidate_profile_id)
        profile = dict(public_profile or {})
        if public_profile:
            profile_id = public_profile.get("id") or profile_id

    conversations = list_case_conversations(conn, case_id)
    conversation_roles: list[dict[str, Any]] = []
    for conversation in conversations:
        for member in conversation.get("members") or []:
            if str(member.get("participant_id") or "") != participant_id:
                continue
            conversation_roles.append(
                {
                    "conversation_id": conversation["conversation_id"],
                    "channel_key": conversation["channel_key"],
                    "conversation_kind": conversation["conversation_kind"],
                    "member_role": member["member_role"],
                }
            )

    return {
        "participant_id": participant_id,
        "case_id": case_id,
        "role": role,
        "profile_id": profile_id,
        "profile": profile,
        "persona": persona,
        "conversation_roles": conversation_roles,
    }


def build_case_agent_bootstrap(
    conn,
    case_id: str,
    *,
    recent_limit: int = 30,
) -> dict[str, Any]:
    conversations = list_case_conversation_catalog(conn, case_id)
    return {
        "case_id": case_id,
        "conversations": conversations,
        "recent_messages": list_recent_case_messages(conn, case_id, limit=recent_limit),
    }


__all__ = [
    "build_case_agent_bootstrap",
    "get_message_window",
    "get_profile_snapshot",
    "list_case_conversation_catalog",
    "list_recent_case_messages",
    "search_case_history",
]
