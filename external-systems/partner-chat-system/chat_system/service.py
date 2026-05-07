"""Chat threads and messages (MVP: ``docs/chat-agent-architecture.md``)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
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
    align_guidance_to_route_decision,
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
    parse_profile_id_candidate,
    profile_row_to_assistant_summary,
    profile_row_to_hook_list,
)
from .risk import assert_message_allowed, maybe_capture_message_risk_signal
from .storage import json_dumps, json_loads, row_to_dict
from .trend_state import (
    advance_trend_state,
    apply_hint_event,
    decide_hint_trigger,
    normalize_trend_state,
)

ASSISTANT_AUTHOR_ID = "assistant"
VIS_DYADIC = "dyadic"
VIS_OWNER_ONLY = "owner_only"
VIS_SYSTEM = "system"
SRC_USER = "user"
SRC_AGENT_DRAFT = "agent_draft"
SRC_AGENT_HINT_ENTRY = "agent_hint_entry"
SRC_AGENT_SENT = "agent_sent_after_confirm"
SRC_SYSTEM = "system"
ASSISTANT_TRACE_SCHEMA_VERSION = 1
_ASSISTANT_TREND_STATE_METADATA_KEY = "assistant_trend_state_by_user"
_OWNER_ONLY_KIND_ASSISTANT_QUERY = "assistant_query"
_OWNER_ONLY_KIND_ASSISTANT_HINT_ENTRY = "assistant_hint_entry"


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
    thread = _inflate_thread(row_to_dict(row))
    if thread is not None:
        thread["_conn"] = conn
    return thread


def get_thread_by_case(conn, case_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_threads WHERE case_id = ? LIMIT 1",
        (case_id,),
    )
    row = cur.fetchone()
    thread = _inflate_thread(row_to_dict(row))
    if thread is not None:
        thread["_conn"] = conn
    return thread


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
    hint_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": ASSISTANT_TRACE_SCHEMA_VERSION,
        "route_decision": dict(route_decision or {}),
        "guidance": normalize_assistant_guidance(guidance),
        "profile_context": _profile_context_for_trace(profile_ctx),
        "hint_event": dict(hint_event or {}) if hint_event else None,
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


def _assistant_guidance_hidden_source(
    guidance: dict[str, Any] | None,
    *,
    hide_failed_guidance: bool = False,
) -> str | None:
    source = str(((guidance or {}).get("guidance_source")) or "").strip()
    if source == "timeout_hidden":
        return source
    if source == "error_hidden":
        return source
    if hide_failed_guidance and source.startswith("fallback"):
        return "error_hidden"
    return None


def _assistant_proactive_mode() -> str:
    raw = str(os.environ.get("HER_CHAT_ASSISTANT_PROACTIVE_MODE") or "entry").strip().lower()
    return raw if raw in {"entry", "detail"} else "entry"


def _assistant_entry_guidance(route_decision: dict[str, Any] | None) -> dict[str, Any]:
    decision = dict(route_decision or {})
    guidance = build_placeholder_assistant_guidance(
        profile_hooks=[],
        mutual_intent_assessment=str(decision.get("mutual_intent_assessment") or ""),
        interaction_mode=str(decision.get("interaction_mode") or ""),
        route_reason=str(decision.get("reason") or ""),
        guidance_source="entry_pending",
        online_scope_only=True,
    )
    aligned = align_guidance_to_route_decision(
        guidance,
        profile_hooks=[],
        preferred_mutual_intent_assessment=str(decision.get("mutual_intent_assessment") or ""),
        preferred_interaction_mode=str(decision.get("interaction_mode") or ""),
        route_reason=str(decision.get("reason") or ""),
        online_scope_only=True,
    )
    aligned["guidance_source"] = "entry_pending"
    return normalize_assistant_guidance(aligned)


def _assistant_entry_body(route_decision: dict[str, Any] | None) -> str:
    decision = dict(route_decision or {})
    situation = str(decision.get("situation") or "").strip().lower()
    trend = str(decision.get("state_trend") or "").strip().lower()
    if situation in {"stuck", "awkward"} or trend in {"cooling", "worsening"}:
        head = "这几轮有点聊干了。"
    else:
        head = "这轮有点没接顺。"
    return (
        f"{head}\n"
        "如果你还想继续，先别继续追原话题，换个更好接的小话题会更顺。\n"
        "可查看建议。"
    )


def _assistant_entry_out(
    conn,
    thread: dict[str, Any],
    user_id: str,
    *,
    route_decision: dict[str, Any],
    hint_event: dict[str, Any] | None,
    now: datetime | None,
) -> dict[str, Any]:
    started_at = perf_counter()
    guidance = _assistant_entry_guidance(route_decision)
    total_latency_ms = _elapsed_ms(started_at)
    assistant_trace = _assistant_trace_payload(
        route_decision=route_decision,
        guidance=guidance,
        profile_ctx={},
        route_latency_ms=0,
        guidance_latency_ms=0,
        total_latency_ms=total_latency_ms,
        hint_event=hint_event,
    )
    out = post_message(
        conn,
        str(thread["thread_id"]),
        ASSISTANT_AUTHOR_ID,
        _assistant_entry_body(route_decision),
        visibility=VIS_OWNER_ONLY,
        source=SRC_AGENT_HINT_ENTRY,
        message_recipient_id=user_id,
        metadata={
            "assistant_trace": assistant_trace,
            "owner_only_kind": _OWNER_ONLY_KIND_ASSISTANT_HINT_ENTRY,
            "assistant_entry": {
                "entry_kind": "proactive_coaching_entry",
                "detail_status": "pending",
            },
        },
        now=now,
    )
    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_ASSISTANT_INVOKE,
        trace_id=get_trace_id(),
        case_id=str(thread["case_id"]),
        thread_id=str(thread["thread_id"]),
        message_id=out["message_id"],
        user_id=user_id,
        route_latency_ms=0,
        guidance_latency_ms=0,
        assistant_latency_ms=total_latency_ms,
        route_interaction_mode=route_decision.get("interaction_mode"),
        guidance_interaction_mode=guidance.get("interaction_mode"),
    )
    out["assistant_guidance"] = guidance
    out["assistant_profile_context"] = {}
    out["assistant_route_decision"] = route_decision
    out["assistant_latency_ms"] = total_latency_ms
    out["assistant_latency_breakdown_ms"] = dict(assistant_trace["latency_ms"])
    out["assistant_trace"] = assistant_trace
    out["assistant_hint_shape"] = "entry"
    out["assistant_entry"] = {
        "entry_kind": "proactive_coaching_entry",
        "detail_status": "pending",
    }
    if hint_event is not None:
        out["assistant_hint_event"] = dict(hint_event)
    return out


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


def _coerce_profile_id_hint(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _participant_profile_hints(thread: dict[str, Any], participant_id: str) -> dict[str, Any]:
    metadata = dict(thread.get("metadata") or {})
    participant = str(participant_id or "")
    profile_id_hint = parse_profile_id_candidate(participant)
    user_key_hint: str | None = None

    refs = metadata.get("participant_profile_refs")
    if isinstance(refs, dict):
        ref = refs.get(participant)
        if isinstance(ref, dict):
            profile_id_hint = _coerce_profile_id_hint(ref.get("profile_id")) or profile_id_hint
            user_key_hint = str(ref.get("user_key") or "").strip() or user_key_hint

    profile_ids = metadata.get("participant_profile_ids")
    if isinstance(profile_ids, dict):
        profile_id_hint = _coerce_profile_id_hint(profile_ids.get(participant)) or profile_id_hint

    user_keys = metadata.get("participant_profile_user_keys")
    if isinstance(user_keys, dict):
        user_key_hint = str(user_keys.get(participant) or "").strip() or user_key_hint

    side = "a" if participant == str(thread.get("participant_a_id") or "") else "b"
    profile_id_hint = _coerce_profile_id_hint(metadata.get(f"participant_{side}_profile_id")) or profile_id_hint
    user_key_hint = str(metadata.get(f"participant_{side}_profile_user_key") or "").strip() or user_key_hint

    if user_key_hint is None and participant and not participant.startswith("profile-") and not participant.isdigit():
        user_key_hint = participant
    return {
        "profile_id": profile_id_hint,
        "user_key": user_key_hint,
    }

@lru_cache(maxsize=256)
def _assistant_profile_context_cached(
    dsn: str,
    actor_id: str,
    counterpart_id: str,
    actor_profile_id_hint: int | None,
    counterpart_profile_id_hint: int | None,
    actor_user_key_hint: str | None,
    counterpart_user_key_hint: str | None,
) -> tuple[str, str, tuple[str, ...]]:
    if not any(
        (
            actor_id,
            counterpart_id,
            actor_profile_id_hint is not None,
            counterpart_profile_id_hint is not None,
            actor_user_key_hint,
            counterpart_user_key_hint,
        )
    ):
        return "", "", ()

    def _safe_fetch(participant_id: str):
        try:
            hints = (
                actor_profile_id_hint,
                actor_user_key_hint,
            ) if participant_id == actor_id else (
                counterpart_profile_id_hint,
                counterpart_user_key_hint,
            )
            return fetch_profile_for_participant(
                str(dsn),
                str(participant_id),
                profile_id_hint=hints[0],
                user_key_hint=hints[1],
            )
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        actor_future = pool.submit(_safe_fetch, actor_id)
        counterpart_future = pool.submit(_safe_fetch, counterpart_id)
        actor_row = actor_future.result()
        counterpart_row = counterpart_future.result()

    actor_summary = profile_row_to_assistant_summary(actor_row) if actor_row else ""
    counterpart_summary = profile_row_to_assistant_summary(counterpart_row) if counterpart_row else ""
    actor_hooks = profile_row_to_hook_list(actor_row) if actor_row else []
    counterpart_hooks = profile_row_to_hook_list(counterpart_row) if counterpart_row else []
    shared_hooks = [hook for hook in actor_hooks if hook in counterpart_hooks]
    ordered_hooks: list[str] = []
    for hook in shared_hooks + actor_hooks + counterpart_hooks:
        if hook and hook not in ordered_hooks:
            ordered_hooks.append(hook)
    return actor_summary, counterpart_summary, tuple(ordered_hooks[:8])


def _assistant_profile_context(thread: dict[str, Any], user_id: str) -> dict[str, Any]:
    dsn = os.environ.get("HER_PROFILE_MYSQL_DSN") or DEFAULT_PROFILE_MYSQL_DSN
    actor_id = str(user_id)
    counterpart_id = _other_participant_id(thread, user_id)
    actor_hints = _participant_profile_hints(thread, actor_id)
    counterpart_hints = _participant_profile_hints(thread, counterpart_id)
    actor_summary, counterpart_summary, ordered_hooks = _assistant_profile_context_cached(
        str(dsn),
        actor_id,
        counterpart_id,
        actor_hints.get("profile_id"),
        counterpart_hints.get("profile_id"),
        actor_hints.get("user_key"),
        counterpart_hints.get("user_key"),
    )
    return {
        "profile_dsn": str(dsn),
        "actor_profile_summary": actor_summary,
        "counterpart_profile_summary": counterpart_summary,
        "profile_hooks": list(ordered_hooks[:8]),
    }


def _update_thread_metadata(
    conn,
    thread_id: str,
    metadata: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    conn.execute(
        "UPDATE chat_threads SET metadata_json = ?, updated_at = ? WHERE thread_id = ?",
        (json_dumps(metadata or {}), ts, thread_id),
    )
    conn.commit()


def _default_route_decision() -> dict[str, Any]:
    return {
        "need_rescue": False,
        "situation": "none",
        "problem_tags": [],
        "rescue_style": "none",
        "mutual_intent_assessment": "normal",
        "interaction_mode": "none",
        "reason": "当前没有明显需要主动提示的信号。",
        "decision_source": "none",
        "engagement_level": "medium",
        "warmth_level": "neutral",
        "irritation_level": "none",
        "state_trend": "stable",
    }


def _scope_online_assistant_route_decision(route_decision: dict[str, Any] | None) -> dict[str, Any]:
    decision = dict(route_decision or {})
    if not decision:
        return _default_route_decision()

    interaction_mode = str(decision.get("interaction_mode") or "").strip().lower()
    if interaction_mode == "repair":
        scoped = {
            **_default_route_decision(),
            **decision,
            "need_rescue": True,
            "mutual_intent_assessment": "communication_problem",
            "interaction_mode": "repair",
        }
        scoped.pop("risk_axis", None)
        scoped.pop("hold_subtype", None)
        if str(scoped.get("rescue_style") or "").strip().lower() == "none":
            scoped["rescue_style"] = "switch_topic"
        return scoped

    fallback = _default_route_decision()
    fallback["reason"] = (
        str(decision.get("reason") or "").strip()
        or "当前还不属于“双方都想继续聊但聊尬了”的回温场景，线上助手先不主动介入。"
    )
    fallback["decision_source"] = str(decision.get("decision_source") or "scope_filter")
    fallback["engagement_level"] = str(decision.get("engagement_level") or fallback["engagement_level"])
    fallback["warmth_level"] = str(decision.get("warmth_level") or fallback["warmth_level"])
    fallback["irritation_level"] = str(decision.get("irritation_level") or fallback["irritation_level"])
    fallback["state_trend"] = str(decision.get("state_trend") or fallback["state_trend"])
    return fallback


def _dyadic_message_count(conn, thread_id: str, *, author_id: str | None = None) -> int:
    if author_id is None:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM chat_messages WHERE thread_id = ? AND visibility = ?",
            (thread_id, VIS_DYADIC),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM chat_messages
            WHERE thread_id = ? AND visibility = ? AND author_id = ?
            """,
            (thread_id, VIS_DYADIC, author_id),
        ).fetchone()
    return int((row or {}).get("c") or 0)


def _assistant_trend_state(thread: dict[str, Any], user_id: str) -> dict[str, Any]:
    row = thread.get("_assistant_trend_state_row")
    if isinstance(row, dict) and str(row.get("user_id") or "") == str(user_id):
        return normalize_trend_state(json_loads(row.get("state_json"), {}))

    conn = thread.get("_conn")
    if conn is not None:
        cur = conn.execute(
            """
            SELECT user_id, state_json
            FROM chat_assistant_trend_states
            WHERE thread_id = ? AND user_id = ?
            LIMIT 1
            """,
            (str(thread["thread_id"]), str(user_id)),
        )
        trend_row = row_to_dict(cur.fetchone())
        if trend_row:
            thread["_assistant_trend_state_row"] = trend_row
            return normalize_trend_state(json_loads(trend_row.get("state_json"), {}))

    metadata = dict(thread.get("metadata") or {})
    by_user = metadata.get(_ASSISTANT_TREND_STATE_METADATA_KEY) or {}
    if not isinstance(by_user, dict):
        return normalize_trend_state(None)
    return normalize_trend_state(by_user.get(user_id))


def _persist_assistant_trend_state(
    conn,
    thread: dict[str, Any],
    user_id: str,
    trend_state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    ts = current_time(now)
    state_json = json_dumps(normalize_trend_state(trend_state))
    conn.execute(
        """
        INSERT INTO chat_assistant_trend_states (
          thread_id, user_id, state_json, updated_at
        ) VALUES (?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
          state_json = VALUES(state_json),
          updated_at = VALUES(updated_at)
        """,
        (str(thread["thread_id"]), str(user_id), state_json, ts),
    )
    conn.commit()
    thread["_assistant_trend_state_row"] = {
        "thread_id": str(thread["thread_id"]),
        "user_id": str(user_id),
        "state_json": state_json,
        "updated_at": ts,
    }


def _assistant_trend_state_with_entry(
    trend_state: dict[str, Any] | None,
    *,
    coaching_stage: str | None = None,
    active_entry_message_id: int | None = None,
    last_entry_turn: int | None = None,
    last_entry_opened_turn: int | None = None,
) -> dict[str, Any]:
    state = normalize_trend_state(trend_state)
    if coaching_stage is not None:
        state["coaching_stage"] = coaching_stage
    if active_entry_message_id is not None:
        state["active_entry_message_id"] = int(active_entry_message_id)
    if last_entry_turn is not None:
        state["last_entry_turn"] = int(last_entry_turn)
    if last_entry_opened_turn is not None:
        state["last_entry_opened_turn"] = int(last_entry_opened_turn)
    return normalize_trend_state(state)


def _proactive_assistant_query_text(route_decision: dict[str, Any] | None) -> str:
    decision = dict(route_decision or {})
    interaction_mode = str(decision.get("interaction_mode") or "none")
    mutual_intent = str(decision.get("mutual_intent_assessment") or "normal")
    reason = str(decision.get("reason") or "")
    situation = str(decision.get("situation") or "none")
    warmth_level = str(decision.get("warmth_level") or "").strip()
    irritation_level = str(decision.get("irritation_level") or "").strip()
    state_trend = str(decision.get("state_trend") or "").strip()
    state_line = (
        f"气氛走势：{state_trend or 'stable'}；语气热度：{warmth_level or 'neutral'}；"
        f"压力程度：{irritation_level or 'none'}。"
    )
    if interaction_mode == "repair":
        return (
            f"系统观察到这轮更像双方都还想继续聊，但沟通卡了一下。"
            f"当前情况：{situation}；意愿判断：{mutual_intent}；原因：{reason}。"
            f"{state_line}"
            "请先指出我这边最需要注意的问题，再给我下一步怎么接、怎么换到更容易继续的话题。"
            "不要直接代写成一条可发送消息。"
        )
    return (
        "请结合当前聊天记录，判断这轮是否需要回温助手主动介入；"
        "如果没有明显的冷场卡点，就直接告诉我这轮先顺着自然聊，不要额外制造紧张感。"
    )


def _assistant_draft_core(
    conn,
    thread: dict[str, Any],
    user_id: str,
    query_text: str,
    *,
    now: datetime | None,
    post_user_query: bool,
    hide_failed_guidance: bool = False,
    route_decision_override: dict[str, Any] | None = None,
    hint_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    q = (query_text or "").strip()
    if not q:
        raise ValueError("query_text is required")
    if post_user_query:
        post_message(
            conn,
            str(thread["thread_id"]),
            user_id,
            q,
            visibility=VIS_OWNER_ONLY,
            source=SRC_USER,
            message_recipient_id=user_id,
            metadata={
                "owner_only_kind": _OWNER_ONLY_KIND_ASSISTANT_QUERY,
                "skip_persona_sync": True,
            },
            now=now,
        )
    total_started_at = perf_counter()
    context_limit = int(os.environ.get("HER_CHAT_ASSISTANT_CONTEXT_LIMIT") or "12")
    message_limit = max(6, min(context_limit, 20))
    route_started_at = perf_counter()
    route_messages = _list_dyadic_messages(conn, thread, user_id, limit=message_limit)
    route_decision = _scope_online_assistant_route_decision(
        route_decision_override or fast_mode_route(route_messages) or _default_route_decision()
    )
    route_latency_ms = _elapsed_ms(route_started_at)
    ctx = build_dyadic_context_for_assistant(
        conn,
        str(thread["thread_id"]),
        limit=message_limit,
        visible_messages=route_messages,
    )
    guidance_started_at = perf_counter()
    profile_ctx = _assistant_profile_context(thread, user_id)
    placeholder = build_placeholder_assistant_guidance(
        profile_hooks=list(profile_ctx.get("profile_hooks") or []),
        mutual_intent_assessment=str(route_decision.get("mutual_intent_assessment") or ""),
        interaction_mode=str(route_decision.get("interaction_mode") or ""),
        online_scope_only=True,
    )
    guidance = generate_assistant_guidance(
        user_query=q,
        thread_context=ctx,
        actor_profile_summary=str(profile_ctx.get("actor_profile_summary") or ""),
        counterpart_profile_summary=str(profile_ctx.get("counterpart_profile_summary") or ""),
        profile_hooks=list(profile_ctx.get("profile_hooks") or []),
        preferred_mutual_intent_assessment=str(route_decision.get("mutual_intent_assessment") or ""),
        preferred_interaction_mode=str(route_decision.get("interaction_mode") or ""),
        route_reason=str(route_decision.get("reason") or ""),
        engagement_level=str(route_decision.get("engagement_level") or ""),
        warmth_level=str(route_decision.get("warmth_level") or ""),
        irritation_level=str(route_decision.get("irritation_level") or ""),
        state_trend=str(route_decision.get("state_trend") or ""),
        online_scope_only=True,
        hide_on_failure=hide_failed_guidance,
    ) or placeholder
    hidden_guidance_source = _assistant_guidance_hidden_source(
        guidance,
        hide_failed_guidance=hide_failed_guidance,
    )
    if hidden_guidance_source:
        guidance = normalize_assistant_guidance(
            {
                **placeholder,
                **dict(guidance or {}),
                "guidance_source": hidden_guidance_source,
            }
        )
    else:
        guidance = align_guidance_to_route_decision(
            guidance,
            profile_hooks=list(profile_ctx.get("profile_hooks") or []),
            preferred_mutual_intent_assessment=str(route_decision.get("mutual_intent_assessment") or ""),
            preferred_interaction_mode=str(route_decision.get("interaction_mode") or ""),
            route_reason=str(route_decision.get("reason") or ""),
            online_scope_only=True,
        )
        guidance = normalize_assistant_guidance(guidance)
    guidance_latency_ms = _elapsed_ms(guidance_started_at)
    total_latency_ms = _elapsed_ms(total_started_at)
    assistant_trace = _assistant_trace_payload(
        route_decision=route_decision,
        guidance=guidance,
        profile_ctx=profile_ctx,
        route_latency_ms=route_latency_ms,
        guidance_latency_ms=guidance_latency_ms,
        total_latency_ms=total_latency_ms,
        hint_event=hint_event,
    )
    if hidden_guidance_source:
        hidden_reason = (
            "guidance_timeout" if hidden_guidance_source == "timeout_hidden" else "guidance_error"
        )
        funnel_stage(
            system="chat",
            stage=CHAT_FUNNEL_ASSISTANT_INVOKE,
            trace_id=get_trace_id(),
            case_id=str(thread["case_id"]),
            thread_id=str(thread["thread_id"]),
            message_id=None,
            user_id=user_id,
            route_latency_ms=route_latency_ms,
            guidance_latency_ms=guidance_latency_ms,
            assistant_latency_ms=total_latency_ms,
            route_interaction_mode=route_decision.get("interaction_mode"),
            guidance_interaction_mode=guidance.get("interaction_mode"),
            assistant_hidden=True,
            assistant_hidden_reason=hidden_reason,
        )
        out = {
            "message_id": None,
            "thread_id": str(thread["thread_id"]),
            "author_id": ASSISTANT_AUTHOR_ID,
            "message_recipient_id": user_id,
            "visibility": VIS_OWNER_ONLY,
            "source": SRC_AGENT_DRAFT,
            "body": None,
            "metadata": {"assistant_trace": assistant_trace},
            "assistant_hidden": True,
            "assistant_hidden_reason": hidden_reason,
            "assistant_guidance": guidance,
            "assistant_profile_context": profile_ctx,
            "assistant_route_decision": route_decision,
            "assistant_latency_ms": total_latency_ms,
            "assistant_latency_breakdown_ms": dict(assistant_trace["latency_ms"]),
            "assistant_trace": assistant_trace,
            "assistant_hint_shape": "detail",
        }
        if hint_event is not None:
            out["assistant_hint_event"] = dict(hint_event)
        return out
    body = render_assistant_guidance(guidance)
    out = post_message(
        conn,
        str(thread["thread_id"]),
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
        thread_id=str(thread["thread_id"]),
        message_id=out["message_id"],
        user_id=user_id,
        route_latency_ms=route_latency_ms,
        guidance_latency_ms=guidance_latency_ms,
        assistant_latency_ms=total_latency_ms,
        route_interaction_mode=route_decision.get("interaction_mode"),
        guidance_interaction_mode=guidance.get("interaction_mode"),
    )
    out["assistant_guidance"] = guidance
    out["assistant_profile_context"] = profile_ctx
    out["assistant_route_decision"] = route_decision
    out["assistant_latency_ms"] = total_latency_ms
    out["assistant_latency_breakdown_ms"] = dict(assistant_trace["latency_ms"])
    out["assistant_trace"] = assistant_trace
    out["assistant_hint_shape"] = "detail"
    if hint_event is not None:
        out["assistant_hint_event"] = dict(hint_event)
    return out


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
    params: list[Any] = [str(thread["thread_id"])]
    before_clause = ""
    if before_message_id is not None:
        before_clause = "AND message_id < ?"
        params.append(int(before_message_id))

    if dyadic_only:
        cur = conn.execute(
            f"""
            SELECT * FROM chat_messages
            WHERE thread_id = ?
              {before_clause}
              AND visibility = ?
            ORDER BY message_id DESC
            LIMIT ?
            """,
            tuple(params + [VIS_DYADIC, lim]),
        )
    else:
        cur = conn.execute(
            f"""
            SELECT * FROM chat_messages
            WHERE thread_id = ?
              {before_clause}
              AND (
                visibility IN (?, ?)
                OR (visibility = ? AND message_recipient_id = ?)
              )
            ORDER BY message_id DESC
            LIMIT ?
            """,
            tuple(params + [VIS_DYADIC, VIS_SYSTEM, VIS_OWNER_ONLY, str(requester_id), lim]),
        )
    rows = cur.fetchall()
    out = [_inflate_message(row_to_dict(raw)) for raw in rows]
    return [row for row in reversed(out) if row]


def _list_dyadic_messages(
    conn,
    thread: dict[str, Any],
    requester_id: str,
    *,
    limit: int = 50,
    before_message_id: int | None = None,
) -> list[dict[str, Any]]:
    if not _is_participant(thread, requester_id):
        raise ValueError("requester is not a participant of this thread")
    return _list_messages_for_requester(
        conn,
        thread,
        requester_id,
        limit=limit,
        before_message_id=before_message_id,
        dyadic_only=True,
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
    return _assistant_draft_core(
        conn,
        thread,
        user_id,
        query_text,
        now=now,
        post_user_query=True,
        hide_failed_guidance=False,
    )


def assistant_open_coaching_entry(
    conn,
    thread_id: str,
    user_id: str,
    entry_message_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, user_id):
        raise ValueError("user is not a participant")
    cur = conn.execute(
        "SELECT * FROM chat_messages WHERE message_id = ? AND thread_id = ? LIMIT 1",
        (int(entry_message_id), thread_id),
    )
    entry = _inflate_message(row_to_dict(cur.fetchone()))
    if not entry:
        raise ValueError("entry not found")
    if str(entry.get("author_id") or "") != ASSISTANT_AUTHOR_ID:
        raise ValueError("entry is not an assistant message")
    if str(entry.get("visibility") or "") != VIS_OWNER_ONLY:
        raise ValueError("entry is not owner_only")
    if str(entry.get("message_recipient_id") or "") != str(user_id):
        raise ValueError("entry is not addressed to this user")
    meta = dict(entry.get("metadata") or {})
    if str(meta.get("owner_only_kind") or "") != _OWNER_ONLY_KIND_ASSISTANT_HINT_ENTRY:
        raise ValueError("message is not a coaching entry")
    trace = dict(meta.get("assistant_trace") or {})
    route_decision = _scope_online_assistant_route_decision(trace.get("route_decision") or {})
    out = _assistant_draft_core(
        conn,
        thread,
        user_id,
        _proactive_assistant_query_text(route_decision),
        now=now,
        post_user_query=False,
        hide_failed_guidance=False,
        route_decision_override=route_decision,
    )
    current_state = _assistant_trend_state(thread, user_id)
    viewed_state = _assistant_trend_state_with_entry(
        current_state,
        coaching_stage="viewed",
        active_entry_message_id=int(entry_message_id),
        last_entry_opened_turn=int(current_state.get("current_turn_index") or 0),
    )
    _persist_assistant_trend_state(conn, thread, user_id, viewed_state, now=now)
    out["assistant_entry_opened_from"] = int(entry_message_id)
    out["assistant_trend_state"] = normalize_trend_state(viewed_state)
    return out


def assistant_proactive_hint(
    conn,
    thread_id: str,
    user_id: str,
    *,
    route_decision: dict[str, Any] | None = None,
    follow_level: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    thread = get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if not _is_participant(thread, user_id):
        raise ValueError("user is not a participant")

    resolved_route = dict(route_decision or {})
    if not resolved_route:
        resolved_route = dict(
            fast_mode_route(_list_dyadic_messages(conn, thread, user_id, limit=200))
            or _default_route_decision()
        )
    else:
        resolved_route = dict(resolved_route)
    resolved_route = _scope_online_assistant_route_decision(resolved_route)

    current_state = _assistant_trend_state(thread, user_id)
    advanced_state = advance_trend_state(
        current_state,
        resolved_route,
        turn_index=_dyadic_message_count(conn, thread_id) + 1,
        actor_turn_count=_dyadic_message_count(conn, thread_id, author_id=user_id),
        follow_level=follow_level,
    )
    hint_event = decide_hint_trigger(
        advanced_state,
        speaker=user_id,
        reason=str(resolved_route.get("reason") or ""),
    )
    next_state = apply_hint_event(advanced_state, hint_event)

    if not bool(hint_event.get("hint_posted")):
        _persist_assistant_trend_state(conn, thread, user_id, next_state, now=now)
        return {
            "hint_posted": False,
            "assistant_hint_event": dict(hint_event),
            "assistant_route_decision": resolved_route,
            "assistant_trend_state": normalize_trend_state(next_state),
        }

    proactive_mode = _assistant_proactive_mode()
    if proactive_mode == "entry":
        out = _assistant_entry_out(
            conn,
            thread,
            user_id,
            route_decision=resolved_route,
            hint_event=hint_event,
            now=now,
        )
        next_state = _assistant_trend_state_with_entry(
            next_state,
            coaching_stage="suggested",
            active_entry_message_id=int(out["message_id"]),
            last_entry_turn=int(next_state.get("current_turn_index") or 0),
        )
        _persist_assistant_trend_state(conn, thread, user_id, next_state, now=now)
        out["hint_posted"] = True
        out["assistant_hint_event"] = dict(hint_event)
        out["assistant_trend_state"] = normalize_trend_state(next_state)
        return out

    out = _assistant_draft_core(
        conn,
        thread,
        user_id,
        _proactive_assistant_query_text(resolved_route),
        now=now,
        post_user_query=False,
        hide_failed_guidance=True,
        route_decision_override=resolved_route,
        hint_event=hint_event,
    )
    if bool(out.get("assistant_hidden")):
        hidden_reason = str(out.get("assistant_hidden_reason") or "").strip() or "guidance_error"
        hidden_event = dict(hint_event)
        hidden_event["hint_posted"] = False
        hidden_event["suppression_reason"] = (
            "assistant_timeout" if hidden_reason == "guidance_timeout" else "assistant_error"
        )
        _persist_assistant_trend_state(conn, thread, user_id, advanced_state, now=now)
        out["hint_posted"] = False
        out["assistant_hint_event"] = hidden_event
        out["assistant_trend_state"] = normalize_trend_state(advanced_state)
        return out
    _persist_assistant_trend_state(conn, thread, user_id, next_state, now=now)
    out["hint_posted"] = True
    out["assistant_hint_event"] = dict(hint_event)
    out["assistant_trend_state"] = normalize_trend_state(next_state)
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
    messages = _list_dyadic_messages(conn, thread, requester_id, limit=limit)
    decision = fast_mode_route(messages)
    if decision is None:
        return None
    out = _scope_online_assistant_route_decision(decision)
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
    "SRC_AGENT_HINT_ENTRY",
    "SRC_AGENT_SENT",
    "SRC_SYSTEM",
    "SRC_USER",
    "VIS_DYADIC",
    "VIS_OWNER_ONLY",
    "VIS_SYSTEM",
    "adopt_draft",
    "assistant_mode_route",
    "assistant_open_coaching_entry",
    "assistant_proactive_hint",
    "assistant_query",
    "current_time",
    "get_or_create_thread",
    "get_thread",
    "get_thread_by_case",
    "list_messages",
    "post_message",
]
