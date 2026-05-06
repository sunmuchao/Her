"""Shared assistant field and mode definitions.

This module is the single source of truth for chat-assistant terminology.

Boundary:
- In the real product, ``interaction_mode`` shapes the assistant's own guidance
  output only; it does not control what a human user must send next.
- In roleplay/offline evaluation, a simulated agent may optionally read the
  same mode for experiments. That is an evaluation technique, not a product
  behavior contract.
"""

from __future__ import annotations

from typing import Any, Final

GUIDANCE_SCHEMA_VERSION: Final[int] = 2
TURN_EVALUATION_SCHEMA_VERSION: Final[int] = 1

DEFAULT_MUTUAL_INTENT_ASSESSMENT: Final[str] = "interest_unclear"

MUTUAL_INTENT_ASSESSMENTS: Final[tuple[str, ...]] = (
    "communication_problem",
    "interest_unclear",
    "interest_low",
    "boundary_risk",
    "normal",
)
MUTUAL_INTENT_ASSESSMENT_SET: Final[frozenset[str]] = frozenset(MUTUAL_INTENT_ASSESSMENTS)

INTERACTION_MODES: Final[tuple[str, ...]] = (
    "repair",
    "probe_lightly",
    "hold",
    "none",
)
INTERACTION_MODE_SET: Final[frozenset[str]] = frozenset(INTERACTION_MODES)

RESCUE_INTERACTION_MODES: Final[tuple[str, ...]] = (
    "repair",
    "probe_lightly",
)
RESCUE_INTERACTION_MODE_SET: Final[frozenset[str]] = frozenset(RESCUE_INTERACTION_MODES)

FOLLOW_LEVEL_NONE: Final[str] = "none"
FOLLOW_LEVEL_PARTIAL: Final[str] = "partial"
FOLLOW_LEVEL_STRONG: Final[str] = "strong"
FOLLOW_LEVEL_NOT_APPLICABLE: Final[str] = "not_applicable"
FOLLOW_LEVELS: Final[tuple[str, ...]] = (
    FOLLOW_LEVEL_NONE,
    FOLLOW_LEVEL_PARTIAL,
    FOLLOW_LEVEL_STRONG,
)
ASSISTANT_FOLLOW_LEVELS: Final[tuple[str, ...]] = (
    FOLLOW_LEVEL_NOT_APPLICABLE,
    *FOLLOW_LEVELS,
)

ASSISTANT_MODE_COMPLIANCE_LEVELS: Final[tuple[str, ...]] = (
    "not_applicable",
    "compliant",
    "drifted",
)

ASSISTANT_GUIDANCE_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "mutual_intent_assessment",
    "interaction_mode",
    "current_problem",
    "problem_tags",
    "why_not_to_push",
    "low_pressure_options",
    "avoid",
    "topic_directions",
    "easy_question_types",
    "rescue_flow",
    "graceful_exit_plan",
    "strategy_tags",
    "reply_suggestions",
    "profile_hooks_used",
)

RESCUE_DECISION_FIELDS: Final[tuple[str, ...]] = (
    "need_rescue",
    "situation",
    "problem_tags",
    "mutual_intent_assessment",
    "interaction_mode",
    "rescue_style",
    "reason",
)

TURN_EVALUATION_FIELDS: Final[tuple[str, ...]] = (
    "mutual_intent_assessment",
    "interaction_mode",
    "assistant_follow_assessment",
    "assistant_recovery_assessment",
    "assistant_mode_compliance",
)

SHARED_TURN_EVALUATION_FIELDS: Final[tuple[str, ...]] = (
    "turn_index",
    "speaker",
    "stress_beat_id",
    "stress_category",
    "mutual_intent_assessment_gold",
    "mutual_intent_assessment_pred",
    "interaction_mode_gold",
    "interaction_mode_pred",
    "assistant_mode_compliance",
    "need_rescue_gold",
    "need_rescue_pred",
    "problem_tags_gold",
    "problem_tags_pred",
    "strategy_tags_gold",
    "strategy_tags_pred",
    "used_assistant",
    "followed_assistant",
    "follow_level",
    "recovery_score_1to3_turns",
    "graceful_exit_score",
)

ROLEPLAY_TURN_EVALUATION_FIELDS: Final[tuple[str, ...]] = (
    "schema_scope",
    "gold_rescue",
    "stress_beat",
    "rescue_decision",
    "rescue_decision_source",
    "assistant_guidance",
    "assistant_profile_context",
    "assistant_mode_compliance_details",
    "assistant_follow_assessment",
    "assistant_recovery_assessment",
    "generated_message",
    "generated_message_id",
    "generated_message_created_at",
    "message_generation_source",
    "message_generation_error",
    "assistant_latency_ms",
    "naturalness",
)


def format_choice_values(values: tuple[str, ...]) -> str:
    return "|".join(values)


def normalize_mutual_intent_assessment(
    value: Any,
    *,
    default: str = DEFAULT_MUTUAL_INTENT_ASSESSMENT,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in MUTUAL_INTENT_ASSESSMENT_SET:
        return raw
    text = str(value or "").strip()
    if "双方" in text and any(token in text for token in ("还想聊", "想继续聊", "继续聊")):
        return "communication_problem"
    if any(token in text for token in ("边界", "敏感", "压力")):
        return "boundary_risk"
    if any(token in text for token in ("兴趣低", "意愿低", "不想聊", "敷衍", "别硬推", "别讨好")):
        return "interest_low"
    if any(token in text for token in ("不明确", "不确定", "试探", "先探")):
        return "interest_unclear"
    if any(token in text for token in ("正常", "自然聊", "顺着聊")):
        return "normal"
    return default


def default_interaction_mode(
    mutual_intent_assessment: str,
    *,
    need_rescue: bool | None = None,
) -> str:
    if mutual_intent_assessment == "communication_problem":
        if need_rescue is False:
            return "none"
        return "repair"
    if mutual_intent_assessment == "interest_unclear":
        if need_rescue is False:
            return "none"
        return "probe_lightly"
    if mutual_intent_assessment in {"interest_low", "boundary_risk"}:
        return "hold"
    return "none"


def normalize_interaction_mode(
    value: Any,
    *,
    mutual_intent_assessment: str,
    need_rescue: bool | None = None,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in INTERACTION_MODE_SET:
        return raw
    text = str(value or "").strip()
    if "低压试探" in text or "轻试" in text:
        return "probe_lightly"
    if any(token in text for token in ("先收住", "别硬推", "别推进", "别讨好")):
        return "hold"
    if any(token in text for token in ("正常修复", "接住", "往下聊", "继续往下聊")):
        return "repair"
    if any(token in text for token in ("不用介入", "顺着聊", "自然往下聊")):
        return "none"
    return default_interaction_mode(mutual_intent_assessment, need_rescue=need_rescue)


def is_rescue_interaction_mode(interaction_mode: str) -> bool:
    return str(interaction_mode or "").strip().lower() in RESCUE_INTERACTION_MODE_SET


__all__ = [
    "ASSISTANT_FOLLOW_LEVELS",
    "ASSISTANT_GUIDANCE_FIELDS",
    "ASSISTANT_MODE_COMPLIANCE_LEVELS",
    "DEFAULT_MUTUAL_INTENT_ASSESSMENT",
    "FOLLOW_LEVEL_NONE",
    "FOLLOW_LEVEL_NOT_APPLICABLE",
    "FOLLOW_LEVEL_PARTIAL",
    "FOLLOW_LEVEL_STRONG",
    "FOLLOW_LEVELS",
    "GUIDANCE_SCHEMA_VERSION",
    "ROLEPLAY_TURN_EVALUATION_FIELDS",
    "SHARED_TURN_EVALUATION_FIELDS",
    "TURN_EVALUATION_SCHEMA_VERSION",
    "INTERACTION_MODES",
    "INTERACTION_MODE_SET",
    "MUTUAL_INTENT_ASSESSMENTS",
    "MUTUAL_INTENT_ASSESSMENT_SET",
    "RESCUE_DECISION_FIELDS",
    "RESCUE_INTERACTION_MODES",
    "TURN_EVALUATION_FIELDS",
    "default_interaction_mode",
    "format_choice_values",
    "is_rescue_interaction_mode",
    "normalize_interaction_mode",
    "normalize_mutual_intent_assessment",
]
