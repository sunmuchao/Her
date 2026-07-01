"""Queue consumer for the triggered matchmaker agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from her_time_utils import coerce_dt as _coerce_dt, current_time

from .assistant_feature_flags import is_match_chat_ai_assistant_enabled
from .assistant_context import (
    build_case_agent_bootstrap,
    get_message_window,
    get_profile_snapshot,
    list_case_conversation_catalog,
    list_recent_case_messages,
    search_case_history,
)
from .assistant_runtime import MatchmakerDecision, MatchmakerRunInput, run_matchmaker_agent
from .assistant_sessions import (
    TASK_REASON_USER_MESSAGE,
    apply_agent_session_outcome,
    claim_pending_agent_tasks,
    complete_agent_task,
    fail_agent_task,
    get_agent_session,
    get_agent_sessions_by_ids,
    is_public_followup_active,
)
from .conversations import get_conversation_by_case_and_key, list_case_conversations, post_conversation_message
from .media_storage import upload_audio
import asyncio
import tempfile
import os


from .tts_service import synthesize_tts


def _synthesize_tts_for_text(text: str, voice: str = "xiaoxiao") -> dict[str, Any] | None:
    """为文本生成语音（复用独立的TTS服务）

    已废弃：直接使用 tts_service.synthesize_tts
    保留此函数作为向后兼容的wrapper
    """
    return synthesize_tts(text, voice)


def _should_generate_tts(
    channel_key: str,
    reason_codes: list[str],
    text: str,
) -> bool:
    """判断是否需要为回复生成语音

    触发场景：
    1. 开场白（opening_probe）
    2. 私信小雅（assistant_dm_a/b）
    3. AI红娘提示（main_group + agent消息）

    Args:
        channel_key: 目标频道（main_group/assistant_dm_a/assistant_dm_b）
        reason_codes: 决策原因码
        text: 回复文本

    Returns:
        True if should generate TTS
    """
    # 场景1：开场白（主动提示）
    if "opening_probe" in reason_codes:
        return True

    # 场景2：私信小雅（assistant_dm频道）
    if channel_key.startswith("assistant_dm_"):
        return True

    # 场景3：AI红娘提示（main_group + 特定reason）
    if channel_key == "main_group" and any(
        code in reason_codes
        for code in ["silence_probe", "post_chat_review", "post_chat_followup"]
    ):
        return True

    # 文本长度限制（太长的文本不生成语音，避免等待时间过长）
    if len(text) > 500:  # 超过500字符不生成语音
        LOGGER.info(f"[TTS] 文本过长({len(text)}字符)，跳过语音生成")
        return False

    return False
from .persona_jobs import enqueue_persona_sync_job

def _normalize_now(now: datetime | None = None) -> datetime:
    return current_time(now)


def _ensure_connection(conn) -> None:
    raw = getattr(conn, "_conn", None)
    if raw is not None:
        raw.ping(reconnect=True)


def _build_run_input(
    conn,
    *,
    session: dict[str, Any],
    task: dict[str, Any],
    recent_limit: int,
) -> MatchmakerRunInput:
    case_id = str(task["case_id"])
    conversations = list_case_conversations(conn, case_id)
    main_group = next(
        (
            conversation
            for conversation in conversations
            if str(conversation.get("channel_key") or "").strip() == "main_group"
        ),
        None,
    )
    bootstrap = build_case_agent_bootstrap(
        conn,
        case_id,
        recent_limit=recent_limit,
        conversations=conversations,
    )
    profile_snapshot_cache: dict[str, dict[str, Any]] = {}

    def _cached_profile_snapshot(participant_id: str) -> dict[str, Any]:
        participant_id = str(participant_id or "").strip()
        snapshot = profile_snapshot_cache.get(participant_id)
        if snapshot is None:
            snapshot = get_profile_snapshot(
                conn,
                case_id,
                participant_id,
                main_group=main_group,
                conversations=conversations,
            )
            profile_snapshot_cache[participant_id] = snapshot
        return snapshot

    profile_snapshots = {
        "participant_a": _cached_profile_snapshot(str(session["participant_a_id"])),
        "participant_b": _cached_profile_snapshot(str(session["participant_b_id"])),
    }
    return MatchmakerRunInput(
        case_id=case_id,
        session=session,
        task=task,
        bootstrap=bootstrap,
        profile_snapshots=profile_snapshots,
        get_recent_case_messages=lambda **kwargs: list_recent_case_messages(conn, case_id, **kwargs),
        search_case_history=lambda **kwargs: search_case_history(conn, case_id, **kwargs),
        get_message_window=lambda **kwargs: get_message_window(conn, case_id, **kwargs),
        get_case_conversations=lambda: list_case_conversation_catalog(conn, case_id),
        get_profile_snapshot=lambda participant_id: _cached_profile_snapshot(participant_id),
        get_agent_session_state=lambda: dict((get_agent_session(conn, str(session["session_id"])) or {}).get("state") or {}),
    )


def _resolve_target_conversation_id(conn, case_id: str, channel_key: str) -> str:
    conversation = get_conversation_by_case_and_key(conn, case_id, channel_key)
    if not conversation:
        raise ValueError(f"conversation not found for channel_key={channel_key}")
    return str(conversation["conversation_id"])


def _post_decision_messages(
    conn,
    *,
    session: dict[str, Any],
    case_id: str,
    task_id: int,
    decision: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []

    def _post_one(channel_key: str, body: str, action_suffix: str, action_reason_codes: list[str]) -> dict[str, Any]:
        target_conversation_id = _resolve_target_conversation_id(conn, case_id, channel_key)

        # ✅ 判断是否需要生成语音
        audio_metadata = None
        if _should_generate_tts(channel_key, action_reason_codes, body):
            LOGGER.info(f"[Agent] 为回复生成语音: channel={channel_key}, text_preview={body[:50]}")
            audio_metadata = _synthesize_tts_for_text(body, voice="xiaoxiao")

        # 构建消息metadata
        message_metadata = {
            "agent_session_id": session["session_id"],
            "agent_task_id": task_id,
            "reason_codes": list(action_reason_codes),
        }

        # ✅ 如果生成了语音，附加到metadata
        if audio_metadata:
            message_metadata["media_type"] = audio_metadata["media_type"]
            message_metadata["media_url"] = audio_metadata["media_url"]
            message_metadata["media_metadata"] = audio_metadata["media_metadata"]
            LOGGER.info(f"[Agent] 消息包含语音: url={audio_metadata['media_url']}")

        return post_conversation_message(
            conn,
            target_conversation_id,
            str(session["agent_participant_id"]),
            str(body),
            source="agent",
            client_msg_id=f"matchmaker-task-{task_id}{action_suffix}",
            metadata=message_metadata,
            now=now,
        )

    if decision["should_reply"]:
        posted.append(
            _post_one(
                str(decision["target_channel_key"]),
                str(decision["reply_body"]),
                "",
                list(decision.get("reason_codes") or []),
            )
        )

    for index, action in enumerate(decision.get("additional_actions") or [], start=1):
        payload = dict(action or {})
        posted.append(
            _post_one(
                str(payload.get("target_channel_key") or ""),
                str(payload.get("reply_body") or ""),
                f"-extra-{index}",
                list(decision.get("reason_codes") or []) + ["additional_action"],
            )
        )
    return posted


def _soft_landing_channel_for_target(close_target: str) -> str | None:
    if close_target == "a":
        return "assistant_dm_a"
    if close_target == "b":
        return "assistant_dm_b"
    return None


def _ensure_soft_landing_delivery(decision: dict[str, Any]) -> dict[str, Any]:
    out = dict(decision or {})
    patch = dict(out.get("state_patch") or {})
    if str(patch.get("close_mode") or "").strip() != "matchmaker_soft_landing":
        return out
    target_channel_key = _soft_landing_channel_for_target(str(patch.get("close_target") or "").strip())
    if not target_channel_key:
        return out
    safe_soft_landing_body = (
        "这轮我先跟你同步一下，这边先不继续往下推进了。"
        "更多还是整体感觉和节奏没有完全对上，不是你哪里做得不好，也谢谢你这次认真聊。"
    )
    existing_targets: set[str] = set()
    if bool(out.get("should_reply")) and str(out.get("target_channel_key") or "").strip():
        existing_targets.add(str(out.get("target_channel_key") or "").strip())
        if str(out.get("target_channel_key") or "").strip() == target_channel_key:
            out["reply_body"] = safe_soft_landing_body
    for action in out.get("additional_actions") or []:
        action_target = str((action or {}).get("target_channel_key") or "").strip()
        existing_targets.add(action_target)
        if action_target == target_channel_key:
            action["reply_body"] = safe_soft_landing_body
    if target_channel_key in existing_targets:
        return out
    additional_actions = list(out.get("additional_actions") or [])
    additional_actions.append(
        {
            "target_channel_key": target_channel_key,
            "reply_body": safe_soft_landing_body,
        }
    )
    out["additional_actions"] = additional_actions
    reason_codes = list(out.get("reason_codes") or [])
    if "soft_landing_delivery_fallback" not in reason_codes:
        reason_codes.append("soft_landing_delivery_fallback")
    out["reason_codes"] = reason_codes
    return out


def _skip_task_result(reason_codes: list[str]) -> dict[str, Any]:
    return {
        "should_reply": False,
        "target_channel_key": None,
        "reply_body": None,
        "reason_codes": list(reason_codes),
        "state_patch": {},
        "cooldown_seconds": 0,
        "additional_actions": [],
        "persona_updates": [],
        "reply_message_id": None,
        "reply_message_ids": [],
    }


def _enqueue_decision_persona_updates(
    conn,
    *,
    session: dict[str, Any],
    task: dict[str, Any],
    decision: dict[str, Any],
    reply_messages: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    updates = list(decision.get("persona_updates") or [])
    if not updates:
        return []
    valid_subjects = {
        str(session.get("participant_a_id") or "").strip(),
        str(session.get("participant_b_id") or "").strip(),
    }
    valid_subjects.discard("")
    anchor_message_id = int(reply_messages[-1]["message_id"]) if reply_messages else int(task["trigger_message_id"])
    thread_id = str(task.get("trigger_conversation_id") or "")
    conversation_ref = f"{thread_id}/{int(task['trigger_message_id'])}"
    enqueued: list[dict[str, Any]] = []
    for raw_update in updates:
        update = dict(raw_update or {})
        subject_user_id = str(update.get("subject_user_id") or "").strip()
        if subject_user_id not in valid_subjects:
            raise ValueError(f"persona update subject_user_id is outside this session: {subject_user_id}")
        patch = dict(update.get("patch") or {})
        evidence_summary = str(update.get("evidence_summary") or "").strip()
        evidence = {
            "conversation_ref": conversation_ref,
            "evidence_text": evidence_summary,
            "reason": "assistant_post_chat_review",
            "source_type": str(update.get("source_type") or "").strip(),
            "basis": str(update.get("basis") or "").strip(),
            "apply_scope": str(update.get("apply_scope") or "").strip(),
            "confidence_score": update.get("confidence_score"),
            "sync_profile": bool(update.get("sync_profile", False)),
            "assistant_session_id": str(session.get("session_id") or ""),
            "agent_task_id": int(task["task_id"]),
            "task_reason": str(task.get("reason") or ""),
            "reason_codes": list(decision.get("reason_codes") or []),
        }
        if enqueue_persona_sync_job(
            conn,
            thread_id=thread_id,
            message_id=anchor_message_id,
            subject_user_id=subject_user_id,
            patch=patch,
            evidence=evidence,
            now=now,
        ):
            enqueued.append(
                {
                    "subject_user_id": subject_user_id,
                    "patch": patch,
                    "source_type": evidence["source_type"],
                    "basis": evidence["basis"],
                    "apply_scope": evidence["apply_scope"],
                }
            )
    return enqueued


def _complete_skipped_task(
    conn,
    *,
    task_id: int,
    reason_codes: list[str],
    now: datetime,
) -> None:
    complete_agent_task(
        conn,
        task_id,
        result=_skip_task_result(reason_codes),
        now=now,
    )


def _coalesce_claimed_tasks(
    conn,
    claimed: list[dict[str, Any]],
    *,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[int]]:
    kept: list[dict[str, Any]] = []
    skipped_task_ids: list[int] = []
    by_session: dict[str, list[dict[str, Any]]] = {}
    for task in claimed:
        by_session.setdefault(str(task["session_id"]), []).append(task)

    for session_tasks in by_session.values():
        latest_dm_a = max(
            (task for task in session_tasks if str(task.get("trigger_channel_key")) == "assistant_dm_a"),
            key=lambda item: int(item["trigger_message_id"]),
            default=None,
        )
        latest_dm_b = max(
            (task for task in session_tasks if str(task.get("trigger_channel_key")) == "assistant_dm_b"),
            key=lambda item: int(item["trigger_message_id"]),
            default=None,
        )
        keep_ids: set[int] = set()
        if latest_dm_a:
            keep_ids.add(int(latest_dm_a["task_id"]))
        if latest_dm_b:
            keep_ids.add(int(latest_dm_b["task_id"]))
        if not keep_ids and session_tasks:
            latest_task = max(session_tasks, key=lambda item: int(item["trigger_message_id"]))
            keep_ids.add(int(latest_task["task_id"]))

        dm_supersedes_public = bool(latest_dm_a or latest_dm_b)
        for task in session_tasks:
            task_id = int(task["task_id"])
            if task_id in keep_ids:
                kept.append(task)
                continue
            reason_code = "superseded_by_newer_trigger"
            if dm_supersedes_public and str(task.get("trigger_channel_key")) == "main_group":
                reason_code = "superseded_by_explicit_dm_trigger"
            _complete_skipped_task(conn, task_id=task_id, reason_codes=[reason_code], now=now)
            skipped_task_ids.append(task_id)

    kept.sort(key=lambda item: (int(item["trigger_message_id"]), int(item["task_id"])))
    return kept, skipped_task_ids


def _is_public_trigger_in_cooldown(
    session: dict[str, Any],
    task: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    if str(task.get("trigger_channel_key") or "") != "main_group":
        return False
    if str(task.get("reason") or "") != TASK_REASON_USER_MESSAGE:
        return False
    if is_public_followup_active(session):
        return False
    cooldown_until = _coerce_dt(session.get("cooldown_until"))
    return bool(cooldown_until and now < cooldown_until)


def process_pending_agent_tasks(
    conn,
    *,
    limit: int = 10,
    lease_seconds: int = 180,
    recent_limit: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _normalize_now(now)
    if not is_match_chat_ai_assistant_enabled():
        claimed = claim_pending_agent_tasks(conn, limit=limit, lease_seconds=lease_seconds, now=ts)
        conn.commit()
        skipped_task_ids: list[int] = []
        for task in claimed:
            task_id = int(task["task_id"])
            _complete_skipped_task(
                conn,
                task_id=task_id,
                reason_codes=["assistant_disabled"],
                now=ts,
            )
            skipped_task_ids.append(task_id)
        conn.commit()
        return {
            "claimed": len(claimed),
            "completed": len(skipped_task_ids),
            "failed": 0,
            "replies_posted": 0,
            "task_ids": skipped_task_ids,
            "skipped_task_ids": skipped_task_ids,
            "errors": [],
            "disabled": True,
        }
    claimed = claim_pending_agent_tasks(conn, limit=limit, lease_seconds=lease_seconds, now=ts)
    conn.commit()

    out: dict[str, Any] = {
        "claimed": len(claimed),
        "completed": 0,
        "failed": 0,
        "replies_posted": 0,
        "task_ids": [],
        "skipped_task_ids": [],
        "errors": [],
    }
    claimed, skipped_task_ids = _coalesce_claimed_tasks(conn, claimed, now=ts)
    if skipped_task_ids:
        conn.commit()
        out["completed"] += len(skipped_task_ids)
        out["skipped_task_ids"] = skipped_task_ids

    sessions_by_id = get_agent_sessions_by_ids(conn, [str(task["session_id"]) for task in claimed])

    for task in claimed:
        task_id = int(task["task_id"])
        out["task_ids"].append(task_id)
        try:
            session = sessions_by_id.get(str(task["session_id"]))
            if not session:
                raise ValueError("agent session not found")
            if _is_public_trigger_in_cooldown(session, task, now=ts):
                _complete_skipped_task(
                    conn,
                    task_id=task_id,
                    reason_codes=["cooldown_active_public_trigger"],
                    now=ts,
                )
                conn.commit()
                out["completed"] += 1
                out["skipped_task_ids"].append(task_id)
                continue

            run_input = _build_run_input(conn, session=session, task=task, recent_limit=recent_limit)
            decision = MatchmakerDecision.model_validate(run_matchmaker_agent(run_input)).model_dump()
            decision = MatchmakerDecision.model_validate(_ensure_soft_landing_delivery(decision)).model_dump()
            _ensure_connection(conn)
            reply_messages = _post_decision_messages(
                conn,
                session=session,
                case_id=str(task["case_id"]),
                task_id=task_id,
                decision=decision,
                now=ts,
            )
            out["replies_posted"] += len(reply_messages)
            persona_updates = _enqueue_decision_persona_updates(
                conn,
                session=session,
                task=task,
                decision=decision,
                reply_messages=reply_messages,
                now=ts,
            )

            apply_agent_session_outcome(
                conn,
                str(session["session_id"]),
                task_id=task_id,
                trigger_message_id=int(task["trigger_message_id"]),
                reply_message_id=int(reply_messages[-1]["message_id"]) if reply_messages else None,
                reply_message_ids=[int(item["message_id"]) for item in reply_messages],
                reason_codes=list(decision.get("reason_codes") or []),
                state_patch=dict(decision.get("state_patch") or {}),
                public_followup=dict(decision.get("public_followup") or {}) if decision.get("public_followup") else None,
                cooldown_seconds=int(decision.get("cooldown_seconds") or 0),
                now=ts,
            )
            complete_agent_task(
                conn,
                task_id,
                result={
                    **decision,
                    "persona_updates_enqueued": persona_updates,
                    "reply_message_id": int(reply_messages[-1]["message_id"]) if reply_messages else None,
                    "reply_message_ids": [int(item["message_id"]) for item in reply_messages],
                },
                now=ts,
            )
            conn.commit()
            out["completed"] += 1
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                _ensure_connection(conn)
                fail_agent_task(conn, task_id, error_text=str(exc), now=ts)
                conn.commit()
            except Exception:
                pass
            out["failed"] += 1
            out["errors"].append({"task_id": task_id, "error": str(exc)})
    return out


__all__ = ["process_pending_agent_tasks"]
