"""Profile-first discovery session open (scheme A) without initial LLM turn."""

from __future__ import annotations

import logging
import os
from typing import Any

from match_domain.onboarding_search import format_criteria_labels

LOGGER = logging.getLogger(__name__)

from .agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)

PROFILE_FIRST_OPEN_MESSAGE = (
    "我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。"
)
PROFILE_FIRST_LOW_QUALITY_HINT = (
    "按你现在的条件，库里匹配的人还不多；想多看几位可以直接说放宽城市或年龄。"
)
PROFILE_FIRST_EMPTY_MESSAGE = (
    "根据你刚填的资料，我先帮你筛了一轮，暂时没找到特别贴近的。你可以直接跟我说想怎么调整条件。"
)
PROFILE_FIRST_RESULT_TITLE = "根据你的资料，先给你看这些"
PROFILE_FIRST_SEARCH_LIMIT = 5
LOW_QUALITY_SCORE_THRESHOLD = 40


def discovery_opening_tts_enabled() -> bool:
    raw = (os.environ.get("HER_DISCOVERY_OPENING_TTS_ENABLED") or "").strip().lower()
    if not raw:
        return False
    return raw not in {"0", "false", "off", "no"}


def discovery_create_session_mode() -> str:
    raw = (os.environ.get("HER_DISCOVERY_CREATE_SESSION_MODE") or "profile_first").strip().lower()
    if raw in {"agent", "llm", "initial_decision"}:
        return "agent"
    return "profile_first"


def criteria_labels_from_search_criteria(criteria: dict[str, Any]) -> list[str]:
    return format_criteria_labels(criteria)


def default_profile_first_suggested_actions() -> list[DiscoveryActionSuggestion]:
    return [
        DiscoveryActionSuggestion(
            label="先从城市和年龄说起",
            style="primary",
            semantic_payload={"kind": "starter_prompt", "slot": "city_and_age"},
        ),
        DiscoveryActionSuggestion(
            label="先说你最在意的 3 个条件",
            semantic_payload={"kind": "starter_prompt", "slot": "top_preferences"},
        ),
    ]


def selected_candidates_from_search(
    search_response: dict[str, Any],
    *,
    limit: int = PROFILE_FIRST_SEARCH_LIMIT,
) -> list[DiscoveryCandidateSelection]:
    selections: list[DiscoveryCandidateSelection] = []
    for candidate in list(search_response.get("results") or [])[:limit]:
        profile_id = int(candidate.get("id") or 0)
        if profile_id <= 0:
            continue
        selections.append(DiscoveryCandidateSelection(profile_id=profile_id, reason_summary=""))
    return selections


def _should_append_low_quality_hint(
    search_response: dict[str, Any],
    *,
    selection_count: int,
) -> bool:
    if selection_count <= 0:
        return False
    results = list(search_response.get("results") or [])[:selection_count]
    top_score = max(int(item.get("score") or item.get("fit_score") or 0) for item in results)
    pool = dict(search_response.get("pool_summary") or {})
    scanned_count = int(pool.get("scanned_count") or 0)
    if top_score < LOW_QUALITY_SCORE_THRESHOLD:
        return True
    return selection_count <= 1 and scanned_count <= 3


def _profile_first_open_message(
    search_response: dict[str, Any],
    *,
    selection_count: int,
) -> str:
    message = PROFILE_FIRST_OPEN_MESSAGE
    if _should_append_low_quality_hint(search_response, selection_count=selection_count):
        return f"{message} {PROFILE_FIRST_LOW_QUALITY_HINT}"
    return message


def build_profile_first_open_result(
    search_response: dict[str, Any],
    *,
    criteria_labels: list[str],
) -> DiscoveryRuntimeResult:
    """构建开场白结果（profile_first模式）

    新增功能：为开场白消息生成语音（使用独立的TTS服务）

    Args:
        search_response: 搜索结果
        criteria_labels: 条件标签列表

    Returns:
        DiscoveryRuntimeResult，包含：
        - decision: 决策结果
        - assistant_message: 带metadata的开场白消息
        - search_response: 搜索结果
    """
    selections = selected_candidates_from_search(search_response)
    has_results = bool(search_response.get("has_match")) and bool(selections)

    # 确定开场白文本
    message_text = (
        _profile_first_open_message(search_response, selection_count=len(selections))
        if has_results
        else PROFILE_FIRST_EMPTY_MESSAGE
    )

    message_metadata = None
    if discovery_opening_tts_enabled():
        try:
            try:
                from chat_system.tts_service import synthesize_tts
            except ImportError:
                from partner_chat_system.tts_service import synthesize_tts

            LOGGER.info(f"[Discovery] 为开场白生成语音: text_length={len(message_text)}")
            tts_result = synthesize_tts(message_text, voice="xiaoxiao")
            if tts_result:
                message_metadata = tts_result
                LOGGER.info(f"[Discovery] 开场白语音生成成功: url={tts_result['media_url']}")
            else:
                LOGGER.warning("[Discovery] 开场白语音生成失败，仅返回文本")
        except ImportError as e:
            LOGGER.warning(f"[Discovery] TTS服务未安装，跳过语音生成: {e}")
        except Exception as e:
            LOGGER.error(f"[Discovery] 开场白语音生成异常: {e}")

    # 构建决策结果
    if has_results:
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message=message_text,
                assistant_message_metadata=message_metadata,  # 新增：传递metadata
                criteria_labels=list(criteria_labels),
                suggested_actions=[],
                result_group_title=PROFILE_FIRST_RESULT_TITLE,
                selected_candidates=selections,
            ),
            search_response=search_response,
        )

    return DiscoveryRuntimeResult(
        decision=DiscoveryDecision(
            phase="collecting_preferences",
            assistant_message=message_text,
            assistant_message_metadata=message_metadata,  # 新增：传递metadata
            criteria_labels=list(criteria_labels),
            suggested_actions=default_profile_first_suggested_actions(),
            result_group_title=None,
            selected_candidates=[],
        ),
        search_response=search_response,
    )


__all__ = [
    "PROFILE_FIRST_EMPTY_MESSAGE",
    "PROFILE_FIRST_LOW_QUALITY_HINT",
    "PROFILE_FIRST_OPEN_MESSAGE",
    "PROFILE_FIRST_RESULT_TITLE",
    "PROFILE_FIRST_SEARCH_LIMIT",
    "build_profile_first_open_result",
    "criteria_labels_from_search_criteria",
    "default_profile_first_suggested_actions",
    "discovery_create_session_mode",
    "selected_candidates_from_search",
]
