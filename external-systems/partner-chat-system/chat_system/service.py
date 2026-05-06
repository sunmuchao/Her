"""Chat threads and messages (MVP: ``docs/chat-agent-architecture.md``)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from time import perf_counter
from typing import Any

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from match_domain.outbox import append_outbox_pending
from match_domain.trace_context import get_trace_id
from observability import (
    CHAT_FUNNEL_ASSISTANT_INVOKE,
    CHAT_FUNNEL_DRAFT_ADOPT,
    CHAT_FUNNEL_MESSAGE_SEND,
    CHAT_FUNNEL_THREAD_OPEN,
    funnel_stage,
)

from .assistant_llm import (
    build_dyadic_context_for_assistant,
    build_placeholder_assistant_guidance,
    generate_assistant_guidance,
    normalize_assistant_guidance,
    render_assistant_guidance,
)
from .events import chat_message_created_event, chat_thread_opened_event
from .mode_router import fast_mode_route
from .persona_jobs import maybe_enqueue_persona_sync_job
from .profile_loader import (
    DEFAULT_PROFILE_MYSQL_DSN,
    fetch_profile_for_participant,
    profile_row_to_assistant_summary,
    profile_row_to_hook_list,
)
from .risk import assert_message_allowed, maybe_capture_message_risk_signal
from .storage import json_dumps, json_loads, row_to_dict

ASSISTANT_AUTHOR_ID = "assistant"
VIS_DYADIC = "dyadic"
VIS_OWNER_ONLY = "owner_only"
VIS_SYSTEM = "system"
SRC_USER = "user"
SRC_AGENT_DRAFT = "agent_draft"
SRC_AGENT_SENT = "agent_sent_after_confirm"
SRC_SYSTEM = "system"
ASSISTANT_TRACE_SCHEMA_VERSION = 1


def current_time(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def _generate_thread_id() -> str:
    return f"cht-{uuid.uuid4().hex[:16]}"


def get_thread(conn, thread_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_threads WHERE thread_id = ? LIMIT 1",
        (thread_id,),
    )
    row = cur.fetchone()
    return _inflate_thread(row_to_dict(row))


def get_thread_by_case(conn, case_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_threads WHERE case_id = ? LIMIT 1",
        (case_id,),
    )
    row = cur.fetchone()
    return _inflate_thread(row_to_dict(row))


def _inflate_thread(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["metadata"] = json_loads(out.pop("metadata_json", None), {})
    return out


def _inflate_message(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["metadata"] = json_loads(out.pop("metadata_json", None), {})
    return out


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((perf_counter() - started_at) * 1000)))


def _profile_context_for_trace(profile_ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_profile_summary": str(profile_ctx.get("actor_profile_summary") or ""),
        "counterpart_profile_summary": str(profile_ctx.get("counterpart_profile_summary") or ""),
        "profile_hooks": list(profile_ctx.get("profile_hooks") or []),
    }


def _assistant_trace_payload(
    *,
    route_decision: dict[str, Any] | None,
    guidance: dict[str, Any],
    profile_ctx: dict[str, Any],
    route_latency_ms: int,
    guidance_latency_ms: int,
    total_latency_ms: int,
) -> dict[str, Any]:
    return {
        "schema_version": ASSISTANT_TRACE_SCHEMA_VERSION,
        "route_decision": dict(route_decision or {}),
        "guidance": normalize_assistant_guidance(guidance),
        "profile_context": _profile_context_for_trace(profile_ctx),
        "latency_ms": {
            "route": int(route_latency_ms),
            "guidance": int(guidance_latency_ms),
            "total": int(total_latency_ms),
        },
        "followed_assistant": None,
        "follow_level": None,
        "follow_evidence": None,
        "overpush_risk": None,
    }


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
    row = get_thread(conn, thread_id)
    assert row is not None
    return row


def _is_participant(thread: dict[str, Any], user_id: str) -> bool:
    return user_id in {thread["participant_a_id"], thread["participant_b_id"]}


def _message_visible_to(row: dict[str, Any], thread: dict[str, Any], requester_id: str) -> bool:
    vis = row["visibility"]
    if vis == VIS_DYADIC or vis == VIS_SYSTEM:
        return _is_participant(thread, requester_id)
    if vis == VIS_OWNER_ONLY:
        return row.get("message_recipient_id") == requester_id
    return False


def _other_participant_id(thread: dict[str, Any], user_id: str) -> str:
    if user_id == thread["participant_a_id"]:
        return str(thread["participant_b_id"])
    return str(thread["participant_a_id"])


def _assistant_profile_context(thread: dict[str, Any], user_id: str) -> dict[str, Any]:
    dsn = os.environ.get("HER_PROFILE_MYSQL_DSN") or DEFAULT_PROFILE_MYSQL_DSN
    try:
        actor_row = fetch_profile_for_participant(str(dsn), str(user_id))
    except Exception:
        actor_row = None
    try:
        counterpart_row = fetch_profile_for_participant(str(dsn), _other_participant_id(thread, user_id))
    except Exception:
        counterpart_row = None
    actor_summary = profile_row_to_assistant_summary(actor_row) if actor_row else ""
    counterpart_summary = profile_row_to_assistant_summary(counterpart_row) if counterpart_row else ""
    actor_hooks = profile_row_to_hook_list(actor_row) if actor_row else []
    counterpart_hooks = profile_row_to_hook_list(counterpart_row) if counterpart_row else []
    shared_hooks = [hook for hook in actor_hooks if hook in counterpart_hooks]
    ordered_hooks: list[str] = []
    for hook in shared_hooks + actor_hooks + counterpart_hooks:
        if hook and hook not in ordered_hooks:
            ordered_hooks.append(hook)
    return {
        "profile_dsn": str(dsn),
        "actor_profile_summary": actor_summary,
        "counterpart_profile_summary": counterpart_summary,
        "profile_hooks": ordered_hooks[:8],
    }


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

    lim = max(1, min(int(limit), 200))
    if before_message_id is not None:
        cur = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE thread_id = ? AND message_id < ?
            ORDER BY message_id DESC
            LIMIT ?
            """,
            (thread_id, int(before_message_id), lim),
        )
    else:
        cur = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE thread_id = ?
            ORDER BY message_id DESC
            LIMIT ?
            """,
            (thread_id, lim),
        )
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = _inflate_message(row_to_dict(raw))
        if row and _message_visible_to(row, thread, requester_id):
            out.append(row)
    out.reverse()
    return out


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

    if visibility not in (VIS_DYADIC, VIS_OWNER_ONLY, VIS_SYSTEM):
        raise ValueError("invalid visibility")
    if visibility == VIS_OWNER_ONLY and not message_recipient_id:
        raise ValueError("message_recipient_id is required for owner_only messages")

    if author_id == ASSISTANT_AUTHOR_ID:
        if visibility != VIS_OWNER_ONLY:
            raise ValueError("assistant messages must use owner_only visibility in MVP")
    elif not _is_participant(thread, author_id):
        raise ValueError("author is not a participant")
    else:
        assert_message_allowed(conn, thread_id, author_id)
        if visibility == VIS_DYADIC and source not in (SRC_USER, SRC_AGENT_SENT):
            raise ValueError("invalid source for user dyadic message")
        if visibility == VIS_OWNER_ONLY and source != SRC_USER:
            raise ValueError("participants may only post owner_only messages with source=user in MVP")

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
                author_id,
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
                author_id=author_id,
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
    mid = inserted_id
    cur = conn.execute("SELECT * FROM chat_messages WHERE message_id = ? LIMIT 1", (mid,))
    row = _inflate_message(row_to_dict(cur.fetchone()))
    assert row is not None
    if visibility == VIS_DYADIC and author_id != ASSISTANT_AUTHOR_ID:
        maybe_capture_message_risk_signal(
            conn,
            thread_id=thread_id,
            message_id=mid,
            author_id=author_id,
            body=body,
            now=ts,
        )
    try:
        maybe_enqueue_persona_sync_job(
            conn,
            thread,
            message_id=inserted_id,
            author_id=author_id,
            body=body,
            visibility=visibility,
            source=source,
            message_recipient_id=message_recipient_id,
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
        message_id=mid,
        visibility=visibility,
        source=source,
        author_id=author_id,
    )
    return dict(row)


def assistant_query(
    conn,
    thread_id: str,
    user_id: str,
    query_text: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, user_id):
        raise ValueError("user is not a participant")

    q = (query_text or "").strip()
    if not q:
        raise ValueError("query_text is required")

    post_message(
        conn,
        thread_id,
        user_id,
        q,
        visibility=VIS_OWNER_ONLY,
        source=SRC_USER,
        message_recipient_id=user_id,
        now=now,
    )
    total_started_at = perf_counter()
    context_limit = int(os.environ.get("HER_CHAT_ASSISTANT_CONTEXT_LIMIT") or "12")
    route_started_at = perf_counter()
    route_messages = list_messages(
        conn,
        thread_id,
        user_id,
        limit=max(6, min(context_limit, 20)),
    )
    route_decision = fast_mode_route(route_messages)
    route_latency_ms = _elapsed_ms(route_started_at)
    ctx = build_dyadic_context_for_assistant(
        conn,
        thread_id,
        limit=max(6, min(context_limit, 20)),
    )
    guidance_started_at = perf_counter()
    profile_ctx = _assistant_profile_context(thread, user_id)
    placeholder = build_placeholder_assistant_guidance(
        profile_hooks=list(profile_ctx.get("profile_hooks") or [])
    )
    guidance = generate_assistant_guidance(
        user_query=q,
        thread_context=ctx,
        actor_profile_summary=str(profile_ctx.get("actor_profile_summary") or ""),
        counterpart_profile_summary=str(profile_ctx.get("counterpart_profile_summary") or ""),
        profile_hooks=list(profile_ctx.get("profile_hooks") or []),
    ) or placeholder
    guidance = normalize_assistant_guidance(guidance)
    guidance_latency_ms = _elapsed_ms(guidance_started_at)
    body = render_assistant_guidance(guidance)
    total_latency_ms = _elapsed_ms(total_started_at)
    assistant_trace = _assistant_trace_payload(
        route_decision=route_decision,
        guidance=guidance,
        profile_ctx=profile_ctx,
        route_latency_ms=route_latency_ms,
        guidance_latency_ms=guidance_latency_ms,
        total_latency_ms=total_latency_ms,
    )
    out = post_message(
        conn,
        thread_id,
        ASSISTANT_AUTHOR_ID,
        body,
        visibility=VIS_OWNER_ONLY,
        source=SRC_AGENT_DRAFT,
        message_recipient_id=user_id,
        metadata={"assistant_trace": assistant_trace},
        now=now,
    )
    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_ASSISTANT_INVOKE,
        trace_id=get_trace_id(),
        case_id=str(thread["case_id"]),
        thread_id=thread_id,
        message_id=out["message_id"],
        user_id=user_id,
        route_latency_ms=route_latency_ms,
        guidance_latency_ms=guidance_latency_ms,
        assistant_latency_ms=total_latency_ms,
        route_interaction_mode=(route_decision or {}).get("interaction_mode"),
        guidance_interaction_mode=guidance.get("interaction_mode"),
    )
    out["assistant_guidance"] = guidance
    out["assistant_profile_context"] = profile_ctx
    out["assistant_route_decision"] = route_decision
    out["assistant_latency_ms"] = total_latency_ms
    out["assistant_latency_breakdown_ms"] = dict(assistant_trace["latency_ms"])
    out["assistant_trace"] = assistant_trace
    return out


def assistant_mode_route(
    conn,
    thread_id: str,
    requester_id: str,
    *,
    limit: int = 50,
) -> dict[str, Any] | None:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, requester_id):
        raise ValueError("requester is not a participant of this thread")
    started_at = perf_counter()
    messages = list_messages(conn, thread_id, requester_id, limit=limit)
    decision = fast_mode_route(messages)
    if decision is None:
        return None
    out = dict(decision)
    out["latency_ms"] = _elapsed_ms(started_at)
    return out


def adopt_draft(
    conn,
    thread_id: str,
    draft_message_id: int,
    adopter_user_id: str,
    *,
    body_override: str | None = None,
    client_msg_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, adopter_user_id):
        raise ValueError("adopter is not a participant")

    cur = conn.execute(
        "SELECT * FROM chat_messages WHERE message_id = ? AND thread_id = ? LIMIT 1",
        (int(draft_message_id), thread_id),
    )
    draft = _inflate_message(row_to_dict(cur.fetchone()))
    if not draft:
        raise ValueError("draft not found")
    if draft["source"] != SRC_AGENT_DRAFT or draft["visibility"] != VIS_OWNER_ONLY:
        raise ValueError("message is not an adoptable assistant draft")
    if draft.get("message_recipient_id") != adopter_user_id:
        raise ValueError("draft is not addressed to this user")
    if body_override is None:
        raise ValueError("body_override is required; assistant guidance cannot be sent directly")

    body = str(body_override or "").strip()
    if not body:
        raise ValueError("body is empty")
    if body == str(draft["body"] or "").strip():
        raise ValueError("body_override must be user-edited; assistant guidance cannot be forwarded verbatim")

    adoption_metadata = {
        "assistant_adoption": {
            "assistant_draft_message_id": int(draft_message_id),
            "followed_assistant": None,
            "follow_level": None,
            "follow_evidence": None,
            "overpush_risk": None,
        }
    }

    msg = post_message(
        conn,
        thread_id,
        adopter_user_id,
        body,
        visibility=VIS_DYADIC,
        source=SRC_AGENT_SENT,
        client_msg_id=client_msg_id,
        reply_to_message_id=int(draft_message_id),
        metadata=adoption_metadata,
        now=now,
    )
    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_DRAFT_ADOPT,
        trace_id=get_trace_id(),
        case_id=str(thread["case_id"]),
        thread_id=thread_id,
        message_id=msg["message_id"],
        adopter_user_id=adopter_user_id,
        draft_message_id=int(draft_message_id),
    )
    return msg


__all__ = [
    "ASSISTANT_AUTHOR_ID",
    "SRC_AGENT_DRAFT",
    "SRC_AGENT_SENT",
    "SRC_SYSTEM",
    "SRC_USER",
    "VIS_DYADIC",
    "VIS_OWNER_ONLY",
    "VIS_SYSTEM",
    "adopt_draft",
    "assistant_query",
    "current_time",
    "get_or_create_thread",
    "get_thread",
    "get_thread_by_case",
    "list_messages",
    "post_message",
]
