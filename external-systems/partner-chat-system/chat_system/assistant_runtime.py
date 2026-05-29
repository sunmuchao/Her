"""Agents SDK-backed runtime for the matchmaker agent."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Callable, Optional

from her_env import coerce_json_object, env_first, env_float
from her_time_utils import coerce_dt as _coerce_dt
from pydantic import BaseModel, Field, model_validator

from .assistant_sessions import (
    PUBLIC_FOLLOWUP_MODE_OPENING,
    PUBLIC_FOLLOWUP_MODE_SILENCE,
    TASK_REASON_POST_CHAT_REVIEW,
    TASK_REASON_POST_CHAT_FOLLOWUP_A,
    TASK_REASON_POST_CHAT_FOLLOWUP_B,
)


@dataclass(frozen=True)
class MatchmakerRunInput:
    case_id: str
    session: dict[str, Any]
    task: dict[str, Any]
    bootstrap: dict[str, Any]
    profile_snapshots: dict[str, Any]
    get_recent_case_messages: Callable[..., list[dict[str, Any]]]
    search_case_history: Callable[..., list[dict[str, Any]]]
    get_message_window: Callable[..., list[dict[str, Any]]]
    get_case_conversations: Callable[[], list[dict[str, Any]]]
    get_profile_snapshot: Callable[[str], dict[str, Any]]
    get_agent_session_state: Callable[[], dict[str, Any]]


VALID_TARGET_CHANNEL_KEYS = {"assistant_dm_a", "assistant_dm_b", "main_group"}
VALID_PERSONA_SOURCE_TYPES = {"explicit", "strong_inference", "weak_inference"}
VALID_PERSONA_BASES = {"self_statement", "stable_inference", "verified"}
VALID_PERSONA_APPLY_SCOPES = {"observation_only", "persona_only", "persona_and_profile"}
VALID_PUBLIC_FOLLOWUP_MODES = {PUBLIC_FOLLOWUP_MODE_OPENING, PUBLIC_FOLLOWUP_MODE_SILENCE}


class MatchmakerAdditionalAction(BaseModel):
    target_channel_key: str
    reply_body: str

    @model_validator(mode="after")
    def _validate_action(self) -> "MatchmakerAdditionalAction":
        if self.target_channel_key not in VALID_TARGET_CHANNEL_KEYS:
            raise ValueError("additional action target_channel_key must be assistant_dm_a, assistant_dm_b, or main_group")
        if not str(self.reply_body or "").strip():
            raise ValueError("additional action reply_body is required")
        return self


class MatchmakerPersonaUpdate(BaseModel):
    subject_user_id: str
    source_type: str
    patch: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: str
    basis: str | None = Field(default=None)
    apply_scope: str | None = Field(default=None)
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    sync_profile: bool | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_update(self) -> "MatchmakerPersonaUpdate":
        if not str(self.subject_user_id or "").strip():
            raise ValueError("persona update subject_user_id is required")
        if str(self.source_type or "").strip() not in VALID_PERSONA_SOURCE_TYPES:
            raise ValueError("persona update source_type must be explicit, strong_inference, or weak_inference")
        if not isinstance(self.patch, dict) or not self.patch:
            raise ValueError("persona update patch must be a non-empty object")
        if not str(self.evidence_summary or "").strip():
            raise ValueError("persona update evidence_summary is required")
        basis = str(self.basis or "").strip()
        if not basis:
            if self.source_type == "explicit":
                basis = "self_statement"
            elif self.source_type == "strong_inference":
                basis = "stable_inference"
            else:
                basis = "stable_inference"
        if basis not in VALID_PERSONA_BASES:
            raise ValueError("persona update basis must be self_statement, stable_inference, or verified")
        self.basis = basis

        apply_scope = str(self.apply_scope or "").strip()
        if not apply_scope:
            if self.sync_profile is True:
                apply_scope = "persona_and_profile"
            else:
                apply_scope = "persona_only"
        if apply_scope not in VALID_PERSONA_APPLY_SCOPES:
            raise ValueError("persona update apply_scope must be observation_only, persona_only, or persona_and_profile")
        self.apply_scope = apply_scope

        if apply_scope == "persona_and_profile":
            self.sync_profile = True
        else:
            self.sync_profile = False
        return self


class MatchmakerPublicFollowup(BaseModel):
    active: bool
    mode: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_followup(self) -> "MatchmakerPublicFollowup":
        mode = str(self.mode or "").strip()
        if mode and mode not in VALID_PUBLIC_FOLLOWUP_MODES:
            raise ValueError("public_followup mode must be opening or silence")
        self.mode = mode or None
        return self


class MatchmakerDecision(BaseModel):
    should_reply: bool = Field(default=True)
    target_channel_key: Optional[str] = Field(default=None)
    reply_body: Optional[str] = Field(default=None)
    reason_codes: list[str] = Field(default_factory=list)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    cooldown_seconds: int = Field(default=0, ge=0, le=86400)
    public_followup: MatchmakerPublicFollowup | None = Field(default=None)
    additional_actions: list[MatchmakerAdditionalAction] = Field(default_factory=list)
    persona_updates: list[MatchmakerPersonaUpdate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_reply(self) -> "MatchmakerDecision":
        if self.should_reply:
            if self.target_channel_key not in VALID_TARGET_CHANNEL_KEYS:
                raise ValueError("target_channel_key must be assistant_dm_a, assistant_dm_b, or main_group")
            if not str(self.reply_body or "").strip():
                raise ValueError("reply_body is required when should_reply=true")
        seen_targets: set[str] = set()
        if self.should_reply and self.target_channel_key:
            seen_targets.add(str(self.target_channel_key))
        for action in self.additional_actions:
            if action.target_channel_key in seen_targets:
                raise ValueError("duplicate target_channel_key across primary reply and additional_actions")
            seen_targets.add(action.target_channel_key)
        seen_updates: set[str] = set()
        for update in self.persona_updates:
            dedupe_key = json.dumps(
                {
                    "subject_user_id": str(update.subject_user_id or "").strip(),
                    "source_type": str(update.source_type or "").strip(),
                    "basis": str(update.basis or "").strip(),
                    "apply_scope": str(update.apply_scope or "").strip(),
                    "patch": dict(update.patch or {}),
                    "evidence_summary": str(update.evidence_summary or "").strip(),
                    "confidence_score": update.confidence_score,
                    "sync_profile": bool(update.sync_profile),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if dedupe_key in seen_updates:
                raise ValueError("duplicate persona update payload")
            seen_updates.add(dedupe_key)
        return self


POST_CHAT_FOLLOWUP_REASONS = {
    TASK_REASON_POST_CHAT_FOLLOWUP_A,
    TASK_REASON_POST_CHAT_FOLLOWUP_B,
}
POST_CHAT_PERSONA_UPDATE_PHASES = {"post_chat_ready", "post_chat_followup", "post_chat_completed"}
POST_CHAT_TERMINAL_STATUSES = {"completed", "user_initiated"}
POST_CHAT_NATURAL_END_REASON_CODES = {
    "natural_ending",
    "mutual_closure",
    "natural_conversation_end",
    "polite_closure",
    "natural_end_goodnight",
    "natural_conversation_ending",
}

def _task_reason(run_input: MatchmakerRunInput) -> str:
    return str(run_input.task.get("reason") or "").strip()


def _task_channel_key(run_input: MatchmakerRunInput) -> str:
    return str(run_input.task.get("trigger_channel_key") or "").strip()


def _is_post_chat_review_reason(reason: str) -> bool:
    return reason == TASK_REASON_POST_CHAT_REVIEW


def _session_side_for_author(run_input: MatchmakerRunInput) -> str:
    author_id = str(run_input.task.get("trigger_author_id") or "")
    if author_id and author_id == str(run_input.session.get("participant_a_id") or ""):
        return "assistant_dm_a"
    if author_id and author_id == str(run_input.session.get("participant_b_id") or ""):
        return "assistant_dm_b"
    channel_key = str(run_input.task.get("trigger_channel_key") or "")
    if channel_key in {"assistant_dm_a", "assistant_dm_b"}:
        return channel_key
    return "assistant_dm_a"


def _post_chat_followup_channel_for_reason(reason: str) -> str | None:
    if reason == TASK_REASON_POST_CHAT_FOLLOWUP_A:
        return "assistant_dm_a"
    if reason == TASK_REASON_POST_CHAT_FOLLOWUP_B:
        return "assistant_dm_b"
    return None


def _post_chat_sent_at_key(channel_key: str) -> str | None:
    if channel_key == "assistant_dm_a":
        return "followup_a_sent_at"
    if channel_key == "assistant_dm_b":
        return "followup_b_sent_at"
    return None

def _recent_messages(run_input: MatchmakerRunInput) -> list[dict[str, Any]]:
    return list(run_input.bootstrap.get("recent_messages") or [])


def _trigger_message(run_input: MatchmakerRunInput) -> dict[str, Any] | None:
    trigger_message_id = int(run_input.task.get("trigger_message_id") or 0)
    recent_messages = _recent_messages(run_input)
    if trigger_message_id > 0:
        for item in reversed(recent_messages):
            if int(item.get("message_id") or 0) == trigger_message_id:
                return item
    if recent_messages:
        return recent_messages[-1]
    return None


def _current_trigger_created_at(run_input: MatchmakerRunInput) -> str:
    trigger = _trigger_message(run_input) or {}
    created_at = str(trigger.get("created_at") or "").strip()
    if created_at:
        return created_at
    return str(run_input.task.get("created_at") or "").strip()


def _counterpart_display_name(run_input: MatchmakerRunInput, channel_key: str) -> str:
    if channel_key == "assistant_dm_a":
        snapshot = dict(run_input.profile_snapshots.get("participant_b") or {})
    else:
        snapshot = dict(run_input.profile_snapshots.get("participant_a") or {})
    profile = dict(snapshot.get("profile") or {})
    return str(profile.get("name") or "对方").strip() or "对方"


def _build_post_chat_phase_patch(
    run_input: MatchmakerRunInput,
    channel_key: str,
    *,
    status: str,
    sent_at: str | None = None,
) -> dict[str, Any]:
    state = dict(run_input.session.get("state") or {})
    status_key = "followup_a_status" if channel_key == "assistant_dm_a" else "followup_b_status"
    sent_at_key = _post_chat_sent_at_key(channel_key)
    patch: dict[str, Any] = {"phase": "post_chat_followup"}
    if status_key:
        patch[status_key] = status
    if sent_at and sent_at_key:
        patch[sent_at_key] = sent_at
    merged = dict(state)
    merged.update(patch)
    statuses = [
        str(merged.get("followup_a_status") or "").strip(),
        str(merged.get("followup_b_status") or "").strip(),
    ]
    if statuses and all(status_value in POST_CHAT_TERMINAL_STATUSES for status_value in statuses if status_value):
        if all(status_value in POST_CHAT_TERMINAL_STATUSES for status_value in statuses):
            patch["phase"] = "post_chat_completed"
    return patch


def _apply_post_chat_review_defaults(run_input: MatchmakerRunInput, decision_out: dict[str, Any]) -> dict[str, Any]:
    if not _is_post_chat_review_reason(_task_reason(run_input)):
        return decision_out
    patch = dict(decision_out.get("state_patch") or {})
    patch.setdefault("phase", "post_chat_followup")
    patch.setdefault("post_chat_review_status", "completed")
    contacted_side = str(patch.get("post_chat_review_contacted_side") or "").strip()
    if not contacted_side:
        targets: list[str] = []
        if bool(decision_out.get("should_reply")):
            targets.append(str(decision_out.get("target_channel_key") or ""))
        for action in decision_out.get("additional_actions") or []:
            targets.append(str((action or {}).get("target_channel_key") or ""))
        private_targets = [target for target in targets if target in {"assistant_dm_a", "assistant_dm_b"}]
        if len(private_targets) == 1:
            patch["post_chat_review_contacted_side"] = "a" if private_targets[0] == "assistant_dm_a" else "b"
    decision_out["state_patch"] = patch
    return decision_out


def _apply_close_mode_guardrails(decision_out: dict[str, Any]) -> dict[str, Any]:
    patch = dict(decision_out.get("state_patch") or {})
    close_mode = str(patch.get("close_mode") or "").strip()
    if close_mode == "self_close_coaching" and decision_out.get("additional_actions"):
        decision_out["additional_actions"] = []
        reason_codes = list(decision_out.get("reason_codes") or [])
        if "self_close_coaching_no_third_party_message" not in reason_codes:
            reason_codes.append("self_close_coaching_no_third_party_message")
        decision_out["reason_codes"] = reason_codes
    return decision_out


def _persona_updates_allowed(run_input: MatchmakerRunInput) -> bool:
    reason = _task_reason(run_input)
    if reason == TASK_REASON_POST_CHAT_REVIEW:
        return True
    if _task_channel_key(run_input) not in {"assistant_dm_a", "assistant_dm_b"}:
        return False
    phase = str((run_input.session.get("state") or {}).get("phase") or "").strip()
    return phase in POST_CHAT_PERSONA_UPDATE_PHASES


def _apply_persona_update_guardrails(run_input: MatchmakerRunInput, decision_out: dict[str, Any]) -> dict[str, Any]:
    if _persona_updates_allowed(run_input):
        return decision_out
    if decision_out.get("persona_updates"):
        decision_out["persona_updates"] = []
        reason_codes = list(decision_out.get("reason_codes") or [])
        if "persona_updates_deferred_until_post_chat" not in reason_codes:
            reason_codes.append("persona_updates_deferred_until_post_chat")
        decision_out["reason_codes"] = reason_codes
    return decision_out


def _build_post_chat_followup_decision(run_input: MatchmakerRunInput) -> dict[str, Any] | None:
    reason = _task_reason(run_input)
    if reason in POST_CHAT_FOLLOWUP_REASONS:
        channel_key = _post_chat_followup_channel_for_reason(reason)
        assert channel_key is not None
        counterpart_name = _counterpart_display_name(run_input, channel_key)
        reply_body = (
            f"这轮聊下来，你对{counterpart_name}第一感觉怎么样？"
            "最加分的一点是什么？你是想继续了解，还是先再看看？有顾虑也可以直接说。"
        )
        return MatchmakerDecision(
            should_reply=True,
            target_channel_key=channel_key,
            reply_body=reply_body,
            reason_codes=["post_chat_followup", "first_impression_checkin"],
            state_patch=_build_post_chat_phase_patch(
                run_input,
                channel_key,
                status="sent",
                sent_at=str(run_input.task.get("created_at") or ""),
            ),
            cooldown_seconds=300,
        ).model_dump()
    return None


def _should_mark_post_chat_ready(run_input: MatchmakerRunInput, decision_out: dict[str, Any]) -> bool:
    if _task_reason(run_input) != "silence_probe":
        return False
    if bool(decision_out.get("should_reply")):
        return False
    reason_codes = {str(code).strip() for code in decision_out.get("reason_codes") or []}
    if reason_codes & POST_CHAT_NATURAL_END_REASON_CODES:
        return True
    state_patch = dict(decision_out.get("state_patch") or {})
    if str(state_patch.get("conversation_phase") or "").strip() == "naturally_ended":
        return True
    return str(state_patch.get("phase") or "").strip() == "post_chat"


def _observed_silence_seconds(run_input: MatchmakerRunInput) -> int | None:
    if str(run_input.task.get("reason") or "") != "silence_probe":
        return None
    task_dt = _coerce_dt(run_input.task.get("created_at")) or _coerce_dt(run_input.task.get("started_at"))
    if not task_dt:
        return None
    anchor_id = int(run_input.task.get("trigger_message_id") or 0)
    recent_messages = list(run_input.bootstrap.get("recent_messages") or [])
    anchor_message = next(
        (item for item in recent_messages if int(item.get("message_id") or 0) == anchor_id),
        None,
    )
    if anchor_message is None and recent_messages:
        anchor_message = recent_messages[-1]
    anchor_dt = _coerce_dt((anchor_message or {}).get("created_at"))
    if not anchor_dt or task_dt < anchor_dt:
        return None
    return int((task_dt - anchor_dt).total_seconds())


def _split_profile_tokens(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"[，,、/]+", text)
    return [item.strip() for item in parts if item.strip()]


def _opening_probe_profile_brief(snapshot: dict[str, Any] | None) -> tuple[str, str]:
    profile = dict((snapshot or {}).get("profile") or {})
    role = str((snapshot or {}).get("role") or "").strip()
    label = "一位" if role == "participant_a" else "另一位"
    parts: list[str] = []
    city = str(profile.get("city") or "").strip()
    job = str(profile.get("job") or "").strip()
    if city and job:
        parts.append(f"现在在{city}做{job}")
    elif job:
        parts.append(f"现在做{job}")
    elif city:
        parts.append(f"现在在{city}生活")

    return label, "，".join(parts)


def _opening_probe_highlight_phrase(snapshot: dict[str, Any] | None) -> str:
    profile = dict((snapshot or {}).get("profile") or {})
    personality_tokens = set(_split_profile_tokens(profile.get("personality")))
    value_tokens = set(_split_profile_tokens(profile.get("values")))
    goal_text = str(profile.get("relationship_goal") or "").strip()
    note_text = str(profile.get("notes") or "").strip()
    combined_tokens = personality_tokens | value_tokens

    if {"做饭", "家务", "下厨"} & combined_tokens or "做饭" in note_text:
        return "会自己做饭，把日子收得挺稳"
    if {"运动", "瑜伽", "跑步", "规律"} & combined_tokens:
        return "再忙也还会保持运动和规律作息，这种自我管理挺加分"
    if {"稳定", "耐心", "边界", "真诚"} & combined_tokens:
        return "相处节奏拿捏得挺稳"
    if "认真相处" in goal_text or "长期" in goal_text:
        return "对关系是认真来看的"
    if "照顾" in note_text or "家庭" in note_text:
        return "会照顾日常，相处里通常比较省心"
    return ""


def _build_opening_probe_intro(run_input: MatchmakerRunInput) -> str | None:
    participant_a = dict(run_input.profile_snapshots.get("participant_a") or {})
    participant_b = dict(run_input.profile_snapshots.get("participant_b") or {})
    a_name, a_brief = _opening_probe_profile_brief(participant_a)
    b_name, b_brief = _opening_probe_profile_brief(participant_b)
    if not a_brief and not b_brief:
        return None

    a_profile = dict(participant_a.get("profile") or {})
    b_profile = dict(participant_b.get("profile") or {})
    a_highlight = _opening_probe_highlight_phrase(participant_a)
    b_highlight = _opening_probe_highlight_phrase(participant_b)
    shared_topic = "可以先聊聊各自周末最常见的安排，通常会比较好接。"
    a_values = set(_split_profile_tokens(a_profile.get("values")))
    b_values = set(_split_profile_tokens(b_profile.get("values")))
    if a_profile.get("city") and a_profile.get("city") == b_profile.get("city"):
        shared_topic = f"你们都在{a_profile.get('city')}，可以先聊聊各自下班后最常去放松的地方。"
    elif {"稳定", "真诚", "长期"} & (a_values & b_values):
        shared_topic = "你们都挺看重认真稳定的相处，可以先聊聊各自最在意的关系节奏。"

    intro_parts = ["我先帮两位搭个话。"]
    if a_brief:
        intro_parts.append(f"{a_name}{a_brief}；")
    if b_brief:
        intro_parts.append(f"{b_name}{b_brief}。")
    if a_highlight or b_highlight:
        highlight_parts: list[str] = []
        if a_highlight:
            highlight_parts.append(f"{a_name}{a_highlight}")
        if b_highlight:
            highlight_parts.append(f"{b_name}{b_highlight}")
        intro_parts.append(f"其实，{'，'.join(highlight_parts)}。")
    intro_parts.append(shared_topic)
    return "".join(intro_parts).replace("；。", "。")


def _run_heuristic_fallback(run_input: MatchmakerRunInput) -> dict[str, Any]:
    if str(run_input.task.get("reason") or "") == "opening_probe":
        reply_body = _build_opening_probe_intro(run_input)
        if not reply_body:
            return MatchmakerDecision(
                should_reply=False,
                target_channel_key=None,
                reply_body=None,
                reason_codes=["heuristic_fallback", "opening_probe_conservative_noop"],
                state_patch={"relationship_stage": "opening"},
                cooldown_seconds=0,
            ).model_dump()
        return MatchmakerDecision(
            should_reply=True,
            target_channel_key="main_group",
            reply_body=reply_body,
            reason_codes=["heuristic_fallback", "opening_probe_profile_intro"],
            state_patch={"relationship_stage": "opening"},
            cooldown_seconds=120,
        ).model_dump()
    if str(run_input.task.get("reason") or "") == "silence_probe":
        # ✅ 兜底逻辑：当 AI 调用失败时，发送一条默认的帮助消息
        recent_messages = list(run_input.bootstrap.get("recent_messages") or [])
        latest_body = str((recent_messages[-1] if recent_messages else {}).get("body") or "").strip()
        # 根据最后一条消息生成简单的跟进
        fallback_reply = "我看你们刚才聊得挺好的，要是有想继续了解的可以顺势问一下～"
        if any(keyword in latest_body for keyword in ("运动", "跑步", "健身", "看书", "电影", "音乐", "旅游", "美食")):
            fallback_reply = "顺着刚才聊的兴趣点，可以问问对方平时怎么安排或者有没有推荐～"
        return MatchmakerDecision(
            should_reply=True,
            target_channel_key="main_group",
            reply_body=fallback_reply,
            reason_codes=["heuristic_fallback", "silence_probe_default_intervention"],
            state_patch={"relationship_stage": "monitoring"},
            cooldown_seconds=180,
            public_followup={"active": True, "mode": "silence"},
        ).model_dump()
    target_channel_key = _session_side_for_author(run_input)
    recent_messages = list(run_input.bootstrap.get("recent_messages") or [])
    latest_body = str((recent_messages[-1] if recent_messages else {}).get("body") or "").strip()
    reply_body = "先别急着下结论，顺着对方刚刚提到的点轻轻接一层，先把聊天稳住。"
    reason_codes = ["heuristic_fallback", "recent_context_only"]
    if any(keyword in latest_body for keyword in ("冷", "敷衍", "不回", "降温")):
        reply_body = "这更像节奏出了点问题。先别追着问态度，低压力确认一下对方是不是这两天比较忙，再看回应。"
        reason_codes = ["heuristic_fallback", "pace_mismatch"]
    return MatchmakerDecision(
        should_reply=True,
        target_channel_key=target_channel_key,
        reply_body=reply_body,
        reason_codes=reason_codes,
        state_patch={"relationship_stage": "monitoring"},
        cooldown_seconds=60,
    ).model_dump()


def _compact_messages(messages: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in messages[-limit:]:
        compact.append(
            {
                "message_id": item.get("message_id"),
                "channel_key": item.get("channel_key"),
                "author_id": item.get("author_id"),
                "source": item.get("source"),
                "body": item.get("body"),
                "created_at": item.get("created_at"),
            }
        )
    return compact


def _compact_conversations(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in conversations:
        compact.append(
            {
                "conversation_id": item.get("conversation_id"),
                "channel_key": item.get("channel_key"),
                "conversation_kind": item.get("conversation_kind"),
                "members": [
                    {
                        "participant_id": member.get("participant_id"),
                        "member_role": member.get("member_role"),
                    }
                    for member in item.get("members") or []
                ],
            }
        )
    return compact


def _compact_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    keep_keys = [
        "id",
        "name",
        "avatar_url",
        "photo_count",
        "gender",
        "age",
        "city",
        "district",
        "job",
        "education",
        "height",
        "income_range",
        "relationship_goal",
        "personality",
        "values",
        "notes",
    ]
    return {key: profile.get(key) for key in keep_keys if profile.get(key) not in (None, "", [])}


def _compact_profile_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = dict(snapshot or {})
    return {
        "participant_id": snapshot.get("participant_id"),
        "role": snapshot.get("role"),
        "profile_id": snapshot.get("profile_id"),
        "profile": _compact_profile(snapshot.get("profile") or {}),
    }


def _build_runtime_prompt(run_input: MatchmakerRunInput) -> str:
    observed_silence_seconds = _observed_silence_seconds(run_input)
    payload = {
        "case_id": run_input.case_id,
        "session": {
            "session_id": run_input.session.get("session_id"),
            "status": run_input.session.get("status"),
            "participant_a_id": run_input.session.get("participant_a_id"),
            "participant_b_id": run_input.session.get("participant_b_id"),
            "agent_participant_id": run_input.session.get("agent_participant_id"),
            "state": run_input.session.get("state") or {},
            "last_seen_message_id": run_input.session.get("last_seen_message_id"),
            "last_user_message_at": str(run_input.session.get("last_user_message_at") or ""),
            "last_replied_at": str(run_input.session.get("last_replied_at") or ""),
        },
        "task": {
            "task_id": run_input.task.get("task_id"),
            "trigger_message_id": run_input.task.get("trigger_message_id"),
            "trigger_author_id": run_input.task.get("trigger_author_id"),
            "trigger_channel_key": run_input.task.get("trigger_channel_key"),
            "reason": run_input.task.get("reason"),
            "attempt_count": run_input.task.get("attempt_count"),
            "created_at": str(run_input.task.get("created_at") or ""),
            "started_at": str(run_input.task.get("started_at") or ""),
            "observed_silence_seconds": observed_silence_seconds,
        },
        "recent_messages": _compact_messages(list(run_input.bootstrap.get("recent_messages") or [])),
        "conversations": _compact_conversations(list(run_input.bootstrap.get("conversations") or [])),
        "profile_snapshots": {
            "participant_a": _compact_profile_snapshot(run_input.profile_snapshots.get("participant_a")),
            "participant_b": _compact_profile_snapshot(run_input.profile_snapshots.get("participant_b")),
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _coerce_json_output(raw_output: Any) -> dict[str, Any]:
    return coerce_json_object(raw_output)


def _validate_decision_output(raw_output: Any) -> dict[str, Any]:
    parsed = _normalize_decision_payload(_coerce_json_output(raw_output))
    return MatchmakerDecision.model_validate(parsed).model_dump()


def _recover_decision_from_exception(exc: Exception) -> dict[str, Any] | None:
    text = str(exc or "").strip()
    if not text:
        return None
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    candidate = fenced_match.group(1).strip() if fenced_match else None
    if not candidate:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start : end + 1].strip()
    if not candidate:
        return None
    try:
        return _validate_decision_output(candidate)
    except (JSONDecodeError, TypeError, ValueError):
        pass

    try:
        should_reply_match = re.search(r'"should_reply"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
        target_match = re.search(r'"target_channel_key"\s*:\s*"([^"]+)"', text)
        reply_match = re.search(
            r'"reply_body"\s*:\s*"(.*?)"\s*,\s*"reason_codes"',
            text,
            flags=re.DOTALL,
        )
        reason_codes_match = re.search(
            r'"reason_codes"\s*:\s*(\[[\s\S]*?\])\s*,\s*"state_patch"',
            text,
            flags=re.DOTALL,
        )
        state_patch_match = re.search(
            r'"state_patch"\s*:\s*(\{[\s\S]*?\})\s*,\s*"cooldown_seconds"',
            text,
            flags=re.DOTALL,
        )
        cooldown_match = re.search(r'"cooldown_seconds"\s*:\s*(\d+)', text)
        if not (should_reply_match and target_match and reply_match and reason_codes_match and state_patch_match):
            return None

        reply_body = reply_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        payload = {
            "should_reply": should_reply_match.group(1).lower() == "true",
            "target_channel_key": target_match.group(1).strip(),
            "reply_body": reply_body,
            "reason_codes": json.loads(reason_codes_match.group(1)),
            "state_patch": json.loads(state_patch_match.group(1)),
            "cooldown_seconds": int(cooldown_match.group(1)) if cooldown_match else 0,
            "additional_actions": [],
        }
        return MatchmakerDecision.model_validate(_normalize_decision_payload(payload)).model_dump()
    except (JSONDecodeError, TypeError, ValueError):
        return None


def _normalize_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    legacy_public_followup_active = out.pop("public_followup_active", None)
    legacy_public_followup_mode = out.pop("public_followup_mode", None)
    if out.get("public_followup") is None and legacy_public_followup_active is not None:
        out["public_followup"] = {
            "active": bool(legacy_public_followup_active),
            "mode": legacy_public_followup_mode,
        }
    if out.get("should_reply") is None:
        out["should_reply"] = True
    if out.get("reason_codes") is None:
        out["reason_codes"] = []
    if out.get("state_patch") is None:
        out["state_patch"] = {}
    if out.get("cooldown_seconds") is None:
        out["cooldown_seconds"] = 0
    if out.get("additional_actions") is None:
        out["additional_actions"] = []
    if out.get("persona_updates") is None:
        out["persona_updates"] = []
    return out


def _opening_probe_mentions_both_sides(run_input: MatchmakerRunInput, reply_body: str) -> bool:
    text = str(reply_body or "").strip()
    if not text:
        return False
    names = [
        str(((run_input.profile_snapshots.get("participant_a") or {}).get("profile") or {}).get("name") or "").strip(),
        str(((run_input.profile_snapshots.get("participant_b") or {}).get("profile") or {}).get("name") or "").strip(),
    ]
    required_names = [name for name in names if name]
    if not required_names:
        return True
    return all(name in text for name in required_names)


def _inferred_public_followup_mode(run_input: MatchmakerRunInput) -> str | None:
    reason = _task_reason(run_input)
    if reason == "opening_probe":
        return PUBLIC_FOLLOWUP_MODE_OPENING
    if reason == "silence_probe":
        return PUBLIC_FOLLOWUP_MODE_SILENCE
    state = dict(run_input.session.get("state") or {})
    mode = str(state.get("public_followup_mode") or "").strip()
    if mode in VALID_PUBLIC_FOLLOWUP_MODES:
        return mode
    return None


def _apply_public_followup_policy(run_input: MatchmakerRunInput, decision_out: dict[str, Any]) -> dict[str, Any]:
    patch = dict(decision_out.get("state_patch") or {})
    phase = str(patch.get("phase") or "").strip()
    inferred_mode = _inferred_public_followup_mode(run_input)
    state = dict(run_input.session.get("state") or {})
    preserve_inferred_mode = bool(inferred_mode) and (
        _task_reason(run_input) in {"opening_probe", "silence_probe"}
        or (
            _task_channel_key(run_input) == "main_group"
            and bool(state.get("public_followup_active"))
        )
    )

    if phase in POST_CHAT_PERSONA_UPDATE_PHASES:
        decision_out["public_followup"] = {"active": False, "mode": inferred_mode}
        return decision_out

    followup = decision_out.get("public_followup")
    if followup is None:
        if _task_reason(run_input) in {"opening_probe", "silence_probe"}:
            followup = {
                "active": bool(decision_out.get("should_reply"))
                and str(decision_out.get("target_channel_key") or "").strip() == "main_group",
                "mode": inferred_mode,
            }
        elif _task_channel_key(run_input) == "main_group" and bool(state.get("public_followup_active")):
            followup = {
                "active": bool(decision_out.get("should_reply"))
                and str(decision_out.get("target_channel_key") or "").strip() == "main_group",
                "mode": inferred_mode,
            }
    if followup is None:
        return decision_out

    normalized = MatchmakerPublicFollowup.model_validate(followup).model_dump()
    if preserve_inferred_mode:
        normalized["mode"] = inferred_mode
    elif not normalized.get("mode") and inferred_mode:
        normalized["mode"] = inferred_mode
    decision_out["public_followup"] = normalized
    return decision_out


def _apply_runtime_policy(run_input: MatchmakerRunInput, decision: dict[str, Any]) -> dict[str, Any]:
    decision_out = MatchmakerDecision.model_validate(_normalize_decision_payload(decision)).model_dump()
    if _should_mark_post_chat_ready(run_input, decision_out):
        decision_out["state_patch"] = {
            **dict(decision_out.get("state_patch") or {}),
            "phase": "post_chat_ready",
            "chat_end_at": _current_trigger_created_at(run_input),
            "chat_end_message_id": int(run_input.task.get("trigger_message_id") or 0),
            "chat_end_reason": list(decision_out.get("reason_codes") or []),
        }
        decision_out["public_followup"] = {"active": False, "mode": _inferred_public_followup_mode(run_input)}
        try:
            from match_domain.rule_config_schema import (
                DEFAULT_POST_CHAT_COOLDOWN_FLOOR,
                SLICE_CHAT_ASSISTANT_COOLDOWN,
                code_defaults_for_slice,
            )

            floor = int(
                code_defaults_for_slice(SLICE_CHAT_ASSISTANT_COOLDOWN).get(
                    "post_chat_ready_floor_seconds",
                    DEFAULT_POST_CHAT_COOLDOWN_FLOOR,
                )
            )
        except Exception:  # noqa: BLE001
            floor = 1800
        decision_out["cooldown_seconds"] = max(int(decision_out.get("cooldown_seconds") or 0), floor)
        return MatchmakerDecision.model_validate(_normalize_decision_payload(decision_out)).model_dump()
    decision_out = _apply_post_chat_review_defaults(run_input, decision_out)
    decision_out = _apply_close_mode_guardrails(decision_out)
    decision_out = _apply_persona_update_guardrails(run_input, decision_out)
    if _task_reason(run_input) == "opening_probe":
        floor_intro = _build_opening_probe_intro(run_input)
        if floor_intro:
            if not decision_out["should_reply"]:
                decision_out = MatchmakerDecision(
                    should_reply=True,
                    target_channel_key="main_group",
                    reply_body=floor_intro,
                    reason_codes=list(decision_out.get("reason_codes") or []) + ["opening_probe_floor_intro"],
                    state_patch={**dict(decision_out.get("state_patch") or {}), "relationship_stage": "opening"},
                    cooldown_seconds=max(int(decision_out.get("cooldown_seconds") or 0), 120),
                ).model_dump()
            else:
                decision_out["target_channel_key"] = "main_group"
                if not _opening_probe_mentions_both_sides(run_input, str(decision_out.get("reply_body") or "")):
                    decision_out["reply_body"] = floor_intro
                    decision_out["reason_codes"] = list(decision_out.get("reason_codes") or []) + [
                        "opening_probe_floor_intro"
                    ]
                decision_out["cooldown_seconds"] = max(int(decision_out.get("cooldown_seconds") or 0), 120)
                decision_out["state_patch"] = {
                    **dict(decision_out.get("state_patch") or {}),
                    "relationship_stage": str(
                        (decision_out.get("state_patch") or {}).get("relationship_stage") or "opening"
                    ),
                }
    decision_out = _apply_public_followup_policy(run_input, decision_out)
    try:
        from match_domain.chat_cooldown import apply_configured_cooldown

        decision_out = apply_configured_cooldown(decision_out)
    except Exception:  # noqa: BLE001
        pass
    return MatchmakerDecision.model_validate(_normalize_decision_payload(decision_out)).model_dump()


def _configure_agents_sdk_provider() -> None:
    from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
    from openai import AsyncOpenAI

    base_url = env_first(
        "HER_CHAT_AGENT_BASE_URL",
        "OPENAI_BASE_URL",
        "HER_CHAT_ASSISTANT_BASE_URL",
    )
    api_mode = env_first(
        "HER_CHAT_AGENT_OPENAI_API",
        "HER_CHAT_ASSISTANT_OPENAI_API",
    ).lower()

    if base_url:
        api_key = os.environ.get("OPENAI_API_KEY") or ""
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=env_float(
                "HER_CHAT_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_ASSISTANT_TIMEOUT_SECONDS",
                default=120.0,
            ),
        )
        set_default_openai_client(client, use_for_tracing=False)
        set_default_openai_api(api_mode or "chat_completions")
        disable_tracing = env_first(
            "HER_CHAT_AGENT_DISABLE_TRACING",
            "HER_CHAT_ASSISTANT_DISABLE_TRACING",
            default="1",
        ).lower()
        if disable_tracing in ("1", "true", "yes"):
            set_tracing_disabled(True)
        return

    if api_mode:
        set_default_openai_api(api_mode)


def _run_with_agents_sdk(run_input: MatchmakerRunInput) -> dict[str, Any]:
    try:
        from agents import Agent, AgentOutputSchema, Runner, function_tool
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise RuntimeError(
            "Missing Agents SDK dependency. Install `openai-agents` to run matchmaker C."
        ) from exc

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run the matchmaker agent")
    _configure_agents_sdk_provider()

    @function_tool
    def get_recent_case_messages(limit: int = 20, conversation_id: Optional[str] = None) -> list[dict[str, Any]]:
        return run_input.get_recent_case_messages(limit=limit, conversation_id=conversation_id)

    @function_tool
    def search_case_history(
        query: str,
        channel_key: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return run_input.search_case_history(query=query, channel_key=channel_key, limit=limit)

    @function_tool
    def get_message_window(message_id: int, before: int = 3, after: int = 3) -> list[dict[str, Any]]:
        return run_input.get_message_window(message_id=message_id, before=before, after=after)

    @function_tool
    def get_case_conversations() -> list[dict[str, Any]]:
        return run_input.get_case_conversations()

    @function_tool
    def get_profile_snapshot(participant_id: str) -> dict[str, Any]:
        return run_input.get_profile_snapshot(participant_id)

    @function_tool
    def get_agent_session_state() -> dict[str, Any]:
        return run_input.get_agent_session_state()

    instructions = """
你是顶级红娘 C，只能以红娘视角给建议，不能冒充 A 或 B 直接替他们聊天。

你的目标：
1. 先判断这条触发消息是否值得回应。
2. 如果回应，只能选择一个目标渠道：assistant_dm_a、assistant_dm_b、main_group。
3. 优先发私聊建议，只有在非常明确适合公开提醒时才用 main_group。
4. 信息不够时必须先调用工具查更早历史，而不是只根据最近几句拍结论。
5. 不要编造你没查到的历史，不要输出评分，不要输出系统说明。
表达原则：
- 主群发言要像真人红娘顺手搭话，不要像系统播报、主持串词、运营复盘。
- 不要在主群里直接点破“冷场了”“尬住了”“聊死了”“卡住了”“我观察到你们刚才...”这类话；如果你决定介入，直接换一个更容易接的话题。
- 不要在主群里用 A、B、用户编号、participant_a、participant_b 这类代号称呼双方。除非资料里本来就有自然昵称，否则优先用“两位”“你”“对方”，或者“一位…另一位…”这种自然说法。
- 红娘是搭桥者，不是聊天参与者。不要靠“我也这样”“我也是”“我常这样”去把自己写进聊天中心。
- 主群里尽量少用“我也好奇”“我想问问”“我觉得”这类把焦点拉回红娘自己的句式。更自然的做法是直接把问题递给双方。
- 私聊建议默认用 1 到 2 段自然短话说清，不要写成报告、小标题、问卷或课程讲义；除非用户明确要步骤化整理，再用编号。
- 聊后私聊指导默认控制在 2 到 4 句，先接住感受，再给一个最值得执行的下一步；不要长篇复盘整段聊天。
- 如果用户问“下一轮怎么接”“接下来怎么推进”，默认只给 1 个最优方向，最多带 1 句可直接发的话；不要同时给两三个备选方案，除非用户明确要选项。
- 如果你给“可直接发的话”，整条回复里默认只给 1 句示例，不要再补第二句，也不要写成“比如……或者……”这种并列选项。
- 如果用户是在犹豫但不排斥，默认只给 1 到 2 个观察点，不要铺一长串检查清单。
- 如果你只是想确认用户真实想法，结尾最多问 1 个自然问题，不要连续追问。
- 除非用户明确追问节奏频率，否则不要给“隔两三天一次”“每天都发”“一周几次”这类过硬节奏指令，只给相对柔和的方向。
- 私聊里不要上来就给用户贴生硬负面标签，比如“整体偏闷”“聊得很差”“很无聊”“没戏了”。先用更轻的观察描述，再自然确认对方真实感受。
6. 如果 task.reason=silence_probe，说明系统只是因为一段静默把你叫起来巡看，不代表系统已经判定冷场。你要自己判断这是自然停顿还是明显卡住。
7. 对 silence_probe：
   - 如果只是自然停顿，返回 should_reply=false。
   - 如果已经明显是礼貌收口、互道晚安、自然告一段落，也返回 should_reply=false，并在 reason_codes 里尽量带上 natural_ending、mutual_closure、polite_closure 这类结束信号。
   - 如果判断已经明显冷场，才介入。
   - 一旦介入，优先考虑 main_group，用一句轻、短、容易接的话题把聊天重新带起来。
   - 公开救场时，不要先点评刚才那段聊得怎么样，也不要把“尴尬”直接说破；直接给顺着上下文的新切口就行。
   - 只要你在 main_group 公开介入过，后续主群只要又出现了新的真实对话，系统还可能继续把这些新对话发给你复看。是否局面已经缓解、是否还在尬聊、是否还值得继续公开介入，都由你自己判断，不由代码替你判断。
   - 后续虽然还会继续把新消息发给你复看，但不代表你每看到一条都要立刻公开插话。能先观察就先观察；只有你的这句公开介入确实能明显改善局面时再说。
   - 如果你希望系统在下一轮主群新对话时还继续把你叫起来复看，就输出 public_followup={"active":true,"mode":"silence"}。
   - 如果你判断已经缓解，或者不值得继续跟，就输出 public_followup={"active":false,"mode":"silence"}。
   - 如果这一轮你决定先不公开插话、但还想继续观察下一轮，也可以返回 should_reply=false，同时 public_followup.active=true。
8. 如果 task.reason=opening_probe，说明两个人刚进 main_group，一时还没人开口，这是让你决定要不要主动起个头。
   - 如果决定介入，只能回 main_group。
   - 先用一句自然的话帮双方破冰，再简短介绍 A 和 B 的公开型背景。
   - 介绍只能用适合公开说的信息，比如城市、职业、生活节奏、兴趣、宽表述的关系期待；不要提收入、过细的婚育条件、隐私偏好。
   - 开场介绍不要念编号名，也不要用 A/B 这种系统代号；更自然的写法是直接描述，或者用“一位…另一位…”。
   - 如果资料里有一个自然的隐形加分点，可以顺手轻轻点一句，但别夸得太重，也别像在做表彰。
   - 结尾要补一个低压力、容易接的话头，不要只说“你们互相介绍一下”。
   - 只要你在 main_group 公开起过头，后续主群只要又出现了新的真实对话，系统还可能继续把这些新对话发给你复看。是否已经接上、是否还在尬聊、是否还值得继续公开帮带节奏，都由你自己判断，不由代码替你判断。
   - 如果你希望系统在下一轮主群新对话时还继续把你叫起来复看，就输出 public_followup={"active":true,"mode":"opening"}。
   - 如果你判断已经接上了，或者已经不值得继续跟，就输出 public_followup={"active":false,"mode":"opening"}。
   - 如果这一轮你决定先不公开插话、但还想继续观察下一轮，也可以返回 should_reply=false，同时 public_followup.active=true。
9. 如果 task.reason=post_chat_review，说明主群这轮已经自然收口，现在轮到你先整体判断聊后要不要私下跟进、先找谁。
   - 不要固定两边都问，也不要固定先问 A 或先问 B。
   - 你必须先看 main_group 最近一段真实对话，自己判断谁更像兴趣偏弱、表达偏收、态度模糊、容易被误会，优先去找这个人。
   - 如果没有明显信号，也可以选择不主动打扰，返回 should_reply=false。
   - 这一步不只是决定要不要发私聊，也是这轮聊天结束后的统一画像复盘时点。聊天进行中不要更新画像；只有到了这里，或者后面用户私下复盘时，才允许判断要不要更新画像。
   - 到了这个统一画像复盘时点，你要先扫一遍整段 main_group：A、B 各自已经明确说出来的稳定本人特征，以及已经稳定暴露出来的匹配方向，都要一起考虑。
   - 如果没有用户私下复盘，你也不能直接跳过画像判断。你要基于整段 main_group 历史、收口方式、双方自然暴露出来的节奏和偏好，自己判断有没有足够稳定、值得影响后续匹配的画像信号。
   - 如果你从整段聊天里已经看出了稳定偏好或稳定本人特征，但又觉得不需要主动打扰任何一方，可以返回 should_reply=false，同时把 persona_updates 填好。
   - 如果决定私下跟进，优先只找一边；只有你明确判断需要同步再找另一边时，才使用 additional_actions 补第二条私聊。
   - 这一步是“整体研判后决定先找谁”，不是给明确正向的一方立刻发推进攻略。
   - 为了让状态稳定，处理完后在 state_patch 里写 post_chat_review_status，通常写 completed；如果你主动先联系了某一边，也可以顺手写 post_chat_review_contacted_side=a 或 b。
10. 如果 session.state.phase 是 post_chat_ready 或 post_chat_followup，且 task.trigger_channel_key 是 assistant_dm_a 或 assistant_dm_b，说明你正在处理聊完后的私下反馈。
   - 这时要由你自己判断对方是在明确想继续、明确不想继续、犹豫但不排斥，还是只是客气模糊；这个判断只用于你自己推理，不要依赖硬编码词表，也不要把分类名直接写给用户。
   - 当一方明确想继续、另一方还没明确前，不要急着给“下一步怎么推进”的具体建议。
   - 这种场景下，主回复最多只能做轻确认，比如“我先帮你看整体感觉，这边先不急着往前推”；不要给话题钩子、不要给示例开场、不要给节奏推进建议。
   - 如果你判断另一边更需要先确认，就可以用 additional_actions 去私下问另一边。
   - 如果当前用户给出的只是抽象负向感受，比如“没感觉”“不太来电”“就那样”“说不上来”这类模糊反馈，而你还分不清是第一感觉问题、聊天节奏问题，还是现实条件问题，不要立刻把它当成明确拒绝。
   - 这种“原因还没拆清”的场景，先用一条自然追问帮对方理顺，追问最多一层，语气要像聊天，不要像问卷或审问。
   - 这种自然追问不要做成生硬二选一盘问。除非用户自己已经把选项摆出来，否则优先先用一句轻的观察承接，再问“你更像是今天状态不在，还是这个话题本身不太好接？”这种自然问法。
   - 在原因还没拆清前，不要承诺“我来帮你收口”“我来帮你同步”，additional_actions 也必须为空；不要一边追问，一边已经替用户去联系另一方。
   - 你可以顺着用户已表达的感受做温和归纳，但不要替用户硬下定义；不要直接说“你就是嫌他闷”“你其实是看不上条件”“你就是没眼缘”。
   - 如果用户补充后，已经把原因明确落到了某一类，比如已经明确是聊天节奏不对、互动接不上、现实条件不合适，或者第一感觉没有到位，就不要继续把同一类原因再细分追问。
   - 特别是当用户已经明确说出“不是条件问题，就是聊天不在一个节奏上”“有点接不住”“互动感不对”这类意思时，这一轮就视为原因已经拆清。
   - 同样地，当用户已经明确说出“未来安排差得有点远”“推进节奏不一致”“现实上不太合适”“长期规划对不上”这类意思时，这一轮也视为现实层面的原因已经拆清。
   - 这种时候优先做总结和承接：先用主群里的真实细节复述你理解到的问题，再顺着用户当前意思往下走；除非用户自己明显还想继续展开，否则不要第二次追问去区分“更偏不会接话”还是“更偏慢热发闷”这类细枝末节。
   - 一旦你已经把原因判断为“聊天不同频”，这一轮 reply_body 里不要再追加新的分叉问句，不要再用“你觉得是 A 还是 B”这种方式继续细分。
   - 一旦你已经把原因判断为“现实条件不符”或“长期安排不匹配”，这一轮 reply_body 里也不要再追加新的分叉问句，不要继续追问到底是婚期、作息、职业强度还是城市安排中的哪一项，除非用户自己主动想展开。
   - 上面两条的优先级高于“犹豫但不排斥”的处理。也就是说，哪怕用户语气里还有“我会更犹豫”“我还在想想看”这类保留，只要原因类别已经说清，就不要再追问同类原因的子项。
   - 这种“原因已清楚，但最终决定还没完全说死”的场景，更合适的下一步是：总结你听到的核心顾虑，然后只往两个方向收束，要么问他/她是更想体面收口，要么问要不要再观察一轮；不要继续做原因拆解。
   - 如果当前用户已经明确不想继续，你要自己结合主群真实互动判断关系深浅。
   - 如果关系还浅，比如只在红娘场里聊过一两轮、没有明显私下互动或见面，你可以接住当前用户，再自己决定要不要代为给另一边做体面收口；如果要做，就把那条收口消息放进 additional_actions。
   - 只要你对当前用户说了“这边我来收个尾”“我来帮你同步”这类话，你就必须在同一轮里真的把那条收口消息放进 additional_actions，并把 close_status 写成 completed；如果你不准备真的发，就不要先承诺。
   - 如果已经有一段私聊、明显投入，或者见过面，这种阶段更适合本人自己说清楚。你要帮当前用户把话组织得体面、明确、不留假希望，不要说“我替你拒绝”。
   - 只要你判断是这种“本人自己说”的阶段，additional_actions 必须为空；你不能在同一轮里替当前用户去联系另一边。
   - 当用户已经明显在问“这事怎么说更合适”“我不想拖着她/他”，默认他大概率已经想清楚了。除非他自己还在明显摇摆，否则直接给一句可发的话术和一句发送提醒，不要再劝“要不要再聊几轮看看”。
   - 如果对方是犹豫但不排斥，不要急着替他下结论，也不要只说“再看看”。先接住这种犹豫，再给 2 到 3 个具体观察点，比如情绪稳定、接话能力、生活节奏和三观是否合拍。
   - 但回复正文仍然保持短，优先挑 1 到 2 个最关键的观察点说，不要把所有观察维度一口气倒给用户。
   - 另一方私聊里的态度、犹豫、好感，默认只供你内部判断，默认不要直接说给当前用户。能只靠行动建议解决，就只给行动建议，不要把私聊内容转成“她也觉得你不错”“他也愿意继续了解”这种直白表述。
   - 只有在当前困惑已经明显集中在“对方是不是只是礼貌、兴趣一般、表达太收”，而且如果你不轻轻扶一下就很可能直接误判掉这段关系时，你才可以做最低强度的“误会纠偏”。
   - 做这种“误会纠偏”时，不要直接说另一方私下态度是正向的；更合适的说法是“从整体互动看，对方不像只是礼貌，更像表达偏稳一点”。不要逐字转述另一方私聊原话，不要传成“特别喜欢”，也不要给当前用户压力。
   - 除了上面这种“快被误判聊死”的特殊场景，其他聊后指导默认不要直接评价“对方对你的感觉”“对方第一印象也不错”“对方也愿意继续了解”这类内容。普通场景只确认当前用户自己的感受，再给下一步行动建议。
   - 如果当前用户已经明确愿意继续、也没有明显顾虑，而且另一边的态度已经比较清楚，不要只做情绪确认或泛泛鼓励。你必须先看 main_group 最近一段真实对话，再基于刚聊顺的具体细节，给 1 到 2 个后续互动建议。
   - 这类“下一步互动建议”最好同时包含：1 个可延续的话题钩子、1 句最好可以直接发出去的自然开场、1 个轻一点的节奏提醒。优先从饮食、通勤、周末安排、放松方式、生活节奏这类已经聊顺的细节里延续，不要重新建议从“忙不忙”“今天怎么样”“吃了吗”这种泛寒暄开场。
   - 给 A 和给 B 的建议要贴合各自刚才在主群里的真实表达，不能只是同一套模板换人称。你要说“从哪接、怎么接、别怎么接”，而不是只说“继续聊聊看”“顺其自然”。
   - 就算你在私聊里给到开场示例，也优先自然地揉进一段话里，不要机械拆成“话题钩子 / 自然开场示例 / 节奏提醒”三个小标题，除非用户明确要你拆解。
   - 默认不要先用一大段分析解释“你们刚才在确认什么、匹配什么、节奏为什么合拍”。用户问的是下一步怎么做，就直接回答下一步。
   - 如果用户问的是“下一轮怎么接”“下一句怎么发”，正文通常就按这个顺序来：先一句轻确认，再一句最优方向，最后可选补一句能直接发的话。不要拉成长文。
   - 这种场景默认只给 1 个最优方向，不要同时给“可以从这个聊，也可以从那个聊”的多路分支；除非用户明确要你给几个备选。
   - 不要在正文里用编号、项目符号，除非用户明确要列表。状态备注可以写进 state_patch，但不要把全部分析都塞进 reply_body。
   - 如果对方只是很模糊的客气反馈，可以轻轻再追一层，把真实意愿问清楚。
   - 如果对方已经表达得很明确，就自然回应，不要重复整轮回访。
   - 当你在做“后续互动指导”时，重点是教当前用户下一句怎么发、从哪里继续接、别怎么开，不是告诉他另一方私下怎么想。能用“你们刚才聊得顺”“这个话题好接”“这个节奏舒服”来表达，就不要用“她也觉得”“他也愿意”这种句式。
   - 如果你决定在回应当前用户的同时，顺手给另一边发一条私聊，只能放到 additional_actions 里；那条额外私聊也必须保持红娘边界，不能泄露来源、不能假缓冲、不能一边收口一边继续鼓励推进。
   - 你要自己决定最后回复什么，不要把这个决策交给代码。
   - 为了让后续状态稳定，处理完这一轮后，优先在 state_patch 里写清这次动作对应的状态。需要的话，也可以顺手写 followup_a_guidance / followup_b_guidance、followup_a_observation_axes / followup_b_observation_axes、followup_a_signal_summary / followup_b_signal_summary、followup_a_next_step_hint / followup_b_next_step_hint、followup_a_topic_hooks / followup_b_topic_hooks 这类自然语言备注；如果你决定浅关系由红娘代收口，也可以写 close_mode=matchmaker_soft_landing、close_target=a 或 b、close_status=completed；如果你判断应由本人自己说，也可以写 close_mode=self_close_coaching、close_status=completed。
   - 如果你已经通过这轮聊后复盘得到足够稳定、值得影响后续匹配的画像信号，可以额外填写 persona_updates；如果原因还没拆清，或者只是这次对某个具体人的短期感受，persona_updates 必须为空。
   - 聊后画像复盘不要只盯“这个人适合什么对象”，还要顺手判断“这个人自己是什么样的人”。也就是说，persona_updates 既可以写匹配方向，也可以写本人明确自述的稳定事实。
   - 只要整段聊天里已经有明确、稳定的本人事实信号，就默认应该补本人特征更新；不要因为这一轮已经写了匹配方向，就把本人特征漏掉。
   - 只要你已经能明确判断“以后更适合什么 / 不适合什么”，就该把这条稳定偏好写进 persona_updates；不要等用户先把“不继续了”说死才更新。
   - 如果 main_group 或聊后私聊里已经有用户本人明确说过的稳定事实，比如职业、城市、关系目标、通勤/生活节奏、表达方式、工作形态这些，也要考虑补 persona_updates，不要只写偏好。
   - 但这个动作只能发生在“聊后阶段”：也就是 task.reason=post_chat_review，或者主群自然结束后用户来私聊复盘的阶段。聊天还在进行时，persona_updates 必须为空。
   - persona_updates 里的每一条都只做“画像更新单”，不要当成给用户看的话。subject_user_id 只能写当前 case 里的 participant_a_id 或 participant_b_id。
   - 同一个 subject_user_id 允许出现多条 persona_updates。常见用法是：1 条写本人特征，1 条写匹配方向。不要因为已经写了偏好，就放弃补事实；也不要因为已经写了事实，就漏掉匹配方向。
   - 一轮 persona_updates 不只是能写给一个人；如果 A、B 两个人这一轮都暴露了稳定信号，你可以同一轮同时更新 A 和 B。一次输出 3 到 6 条更新都正常，只要每条证据都站得住。
   - 每一条 persona_update 都要写 basis。只允许：
     - self_statement：用户本人明确说过
     - stable_inference：你基于整段聊天稳定推断出来
     - verified：你能确认可靠，适合正式同步
   - 每一条 persona_update 都要写 apply_scope。只允许：
     - observation_only：只记观察，不改正式画像
     - persona_only：进入 user_personas，但不进 profiles
     - persona_and_profile：既进 user_personas，也同步到 profiles
   - 默认要保守。除非这条信息已经被确认可靠，否则不要用 persona_and_profile。聊后自然聊天里抓到的大多数内容，通常只该用 observation_only 或 persona_only。
   - 当内容是本人明确自述的稳定事实时，可以用 source_type=explicit；不要把所有聊后更新都硬写成 strong_inference。
   - 当内容是你根据整段聊天总结出的匹配方向、价值取向、节奏偏好时，通常用 source_type=strong_inference。
   - patch 只能使用已有 persona 字段。本人特征优先考虑 self_job、self_city、self_relationship_goal、self_smoking、self_drinking、self_life_rhythm、self_work_pattern、self_expression_style、target_* 这些已有字段；匹配方向优先考虑 preferred_traits、disliked_traits、must_have_tags、must_not_have_tags、preference_summary_internal、persona_summary_internal、public_preference_summary_draft、public_profile_summary_draft。
   - 对本人特征，能结构化就结构化，不要偷懒全塞进 persona_summary_internal。
   - “我平时说话比较直接一点，不太会太花哨”这类，优先写 self_expression_style。
   - “工作安排经常会临时变一下”“像随时待命”“节奏不算特别固定”这类，优先写 self_work_pattern。
   - “我这边算比较规律”“作息稳定”“习惯有安排一点的生活”这类，优先写 self_life_rhythm。
   - “我做财务报表这类工作”“做产品运营”“做研发”这类，优先写 self_job。
   - 如果这些描述本身就是用户用第一人称明确说出来的稳定自述，优先用 source_type=explicit、basis=self_statement；不要因为语气比较委婉，就轻易降成 strong_inference。
   - 只有真的没有更合适字段时，才退回 persona_summary_internal。
   - 对收入、学历、婚育、孩子这类高敏感硬资料，要格外保守。即使用户在聊天里说了，也通常只该 observation_only，或者先不写；不要轻易 persona_and_profile。
   - 最小可行的 persona_updates，不再限于只能写 traits/tag。事实更新可以只写 1 个明确字段；方向更新通常至少要有 1 到 2 个 traits/tag，再加 1 条 preference_summary_internal 或 persona_summary_internal。
   - evidence_summary 要用一句自然语言总结你为什么要改这条画像，基于主群和私聊里已经明确暴露出来的稳定信号；不要逐字转述另一方私聊原话，也不要把一时情绪当长期偏好写进去。
   - 例如，如果 A 明确说“我做财务报表这类工作，平时生活比较规律，说话也比较直接”，B 明确说“工作安排经常临时变，关系前期希望别收太紧”，一个合格的 persona_updates 可以同时有 3 到 4 条，而不是只写 1 条：
     [{"subject_user_id":"A的用户ID","source_type":"explicit","basis":"self_statement","apply_scope":"persona_only","patch":{"self_job":"财务报表相关工作","self_life_rhythm":"生活规律","self_expression_style":"表达直接"},"evidence_summary":"A 在主群里明确说自己做财务报表相关工作，平时生活比较规律，也自述说话偏直接。"},{"subject_user_id":"B的用户ID","source_type":"explicit","basis":"self_statement","apply_scope":"persona_only","patch":{"self_work_pattern":"工作节奏波动较多"},"evidence_summary":"B 在主群里明确说自己的工作安排经常临时变化，平时像随时待命，工作节奏不固定。"},{"subject_user_id":"B的用户ID","source_type":"strong_inference","basis":"stable_inference","apply_scope":"persona_only","patch":{"preferred_traits":["关系前期有弹性","相处节奏宽松"],"disliked_traits":["关系前期收紧过快"],"preference_summary_internal":"关系前期更适合自然、宽松、有松动空间的互动节奏。"},"evidence_summary":"B 在整段聊天里持续表达关系前期不想被收得太紧，更适合慢慢了解、自然相处。"}]

输出必须是合法 JSON，并且符合下面的结构化 schema：
- should_reply
- target_channel_key
- reply_body
- reason_codes
- state_patch
- cooldown_seconds
- public_followup
- additional_actions
- persona_updates

只输出原始 JSON，不要加 ```json 代码块，不要加任何前后说明。
如果 reply_body 里要举例，尽量不要再嵌套英文双引号；必须使用时要保证是合法 JSON 字符串。

reply_body 要简短、可执行、像真人红娘发消息。主群尤其要像顺手搭桥的一句话，私聊像自然聊天，不像模板说明书。聊后私聊默认 2 到 4 句，除非用户明确要展开。
"""

    agent = Agent(
        name="matchmaker_c",
        instructions=instructions.strip(),
        model=env_first(
            "HER_CHAT_AGENT_MODEL",
            "HER_CHAT_ASSISTANT_MODEL",
            default="gpt-4.1-mini",
        ),
        output_type=AgentOutputSchema(MatchmakerDecision, strict_json_schema=False),
        tools=[
            get_recent_case_messages,
            search_case_history,
            get_message_window,
            get_case_conversations,
            get_profile_snapshot,
            get_agent_session_state,
        ],
    )
    try:
        result = Runner.run_sync(agent, input=_build_runtime_prompt(run_input))
        final_output = getattr(result, "final_output", result)
        if isinstance(final_output, MatchmakerDecision):
            return _apply_runtime_policy(run_input, final_output.model_dump())
        return _apply_runtime_policy(run_input, _validate_decision_output(final_output))
    except Exception as exc:
        recovered = _recover_decision_from_exception(exc)
        if recovered is not None:
            return _apply_runtime_policy(run_input, recovered)
        fallback = _run_heuristic_fallback(run_input)
        fallback["reason_codes"] = list(fallback.get("reason_codes") or []) + [
            "structured_output_runtime_failed",
        ]
        fallback["state_patch"] = {
            **dict(fallback.get("state_patch") or {}),
            "runtime_fallback": "structured_output_runtime_failed",
            "runtime_fallback_error": str(exc)[:200],
        }
        return _apply_runtime_policy(run_input, fallback)


def run_matchmaker_agent(run_input: MatchmakerRunInput) -> dict[str, Any]:
    post_chat_decision = _build_post_chat_followup_decision(run_input)
    if post_chat_decision is not None:
        return post_chat_decision
    runtime = env_first(
        "HER_CHAT_AGENT_RUNTIME",
        "HER_CHAT_ASSISTANT_RUNTIME",
        default="agents_sdk",
    ).lower() or "agents_sdk"
    if runtime == "heuristic":
        return _run_heuristic_fallback(run_input)
    return _run_with_agents_sdk(run_input)


__all__ = [
    "MatchmakerDecision",
    "MatchmakerPersonaUpdate",
    "MatchmakerRunInput",
    "run_matchmaker_agent",
]
