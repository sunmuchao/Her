"""Agents SDK-backed runtime for the discovery page."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

_logger = logging.getLogger(__name__)

from her_env import env_first, env_float

from .decision_models import (
    DiscoveryActionSuggestion,
    DiscoveryActionSuggestionModel,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryDecisionModel,
    DiscoveryRuntimeResult,
    DiscoveryToolCall,
    recover_decision_from_exception as _recover_decision_from_exception,
    to_decision as _to_decision,
    validate_decision_output as _validate_decision_output,
)


def _noop_submit_rejection_feedback(*args: Any, **kwargs: Any) -> dict[str, Any]:
    del args, kwargs
    return {"success": False, "skipped": True}


def _noop_get_feedback_options(*args: Any, **kwargs: Any) -> dict[str, Any]:
    del args, kwargs
    return {"options": []}


@dataclass(frozen=True)
class DiscoveryRunInput:
    session_id: str
    requester_id: int
    profile_id: int
    phase: str
    criteria_labels: list[str]
    recent_timeline: list[dict[str, Any]]
    runtime_context: dict[str, Any]
    search_partner_candidates: Callable[[dict[str, Any], int], dict[str, Any]]
    sync_requester_persona_memory: Callable[[dict[str, Any]], dict[str, Any]]
    propose_requester_profile_update: Callable[[str, str], dict[str, Any]]
    create_saved_search_subscription_from_last_search: Callable[[], dict[str, Any]]
    # 新增：反馈收集工具
    submit_rejection_feedback: Callable[..., dict[str, Any]] = _noop_submit_rejection_feedback
    get_feedback_options: Callable[..., dict[str, Any]] = _noop_get_feedback_options
    tool_call_buffer: list["DiscoveryToolCall"] = field(default_factory=list)
    agent_session: Any | None = None


class DiscoveryAgentRuntime(Protocol):
    def initial_decision(self, run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult: ...

    def run_turn(
        self,
        run_input: DiscoveryRunInput,
        *,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult: ...


_BAILIAN_RESPONSES_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_BAILIAN_RESPONSES_DEFAULT_MODEL = "qwen3.6-plus"


def _resolve_discovery_wire_api() -> str:
    raw_wire_api = env_first(
        "HER_DISCOVERY_AGENT_WIRE_API",
        "HER_DISCOVERY_AGENT_OPENAI_API",
        default="responses",
    ).lower()
    return raw_wire_api if raw_wire_api in {"chat_completions", "responses"} else "responses"


def _resolve_discovery_api_key() -> str:
    return env_first(
        "HER_DISCOVERY_AGENT_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
    )


def _looks_like_dashscope_base_url(value: str) -> bool:
    return "dashscope.aliyuncs.com" in str(value or "").strip().lower()


def _resolve_discovery_base_url(*, wire_api: str) -> str:
    explicit_base_url = env_first(
        "HER_DISCOVERY_AGENT_BASE_URL",
        "DASHSCOPE_BASE_URL",
    )
    if explicit_base_url:
        return explicit_base_url

    shared_base_url = env_first(
        "OPENAI_BASE_URL",
        "HER_CHAT_AGENT_BASE_URL",
        "HER_CHAT_ASSISTANT_BASE_URL",
    )
    if wire_api == "responses":
        if _looks_like_dashscope_base_url(shared_base_url):
            return _BAILIAN_RESPONSES_BASE_URL
        if os.environ.get("DASHSCOPE_API_KEY"):
            return _BAILIAN_RESPONSES_BASE_URL
    return shared_base_url


def _resolve_discovery_model(*, wire_api: str) -> str:
    explicit_model = env_first("HER_DISCOVERY_AGENT_MODEL")
    if explicit_model:
        return explicit_model
    if wire_api == "responses":
        return _BAILIAN_RESPONSES_DEFAULT_MODEL
    return env_first(
        "HER_CHAT_AGENT_MODEL",
        "HER_CHAT_ASSISTANT_MODEL",
        default="gpt-4.1-mini",
    )


def _configure_agents_sdk_provider() -> None:
    from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
    from her_production import assert_production_discovery_agent_isolation
    from openai import AsyncOpenAI

    assert_production_discovery_agent_isolation()
    wire_api = _resolve_discovery_wire_api()
    base_url = _resolve_discovery_base_url(wire_api=wire_api)

    if base_url:
        api_key = _resolve_discovery_api_key()
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=env_float(
                "HER_DISCOVERY_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_ASSISTANT_TIMEOUT_SECONDS",
                default=120.0,
            ),
        )
        set_default_openai_client(client, use_for_tracing=False)
        # This only selects the Agents SDK wire API (`/responses` vs `/chat/completions`);
        # it is not a remote provider request parameter.
        set_default_openai_api(wire_api)
        disable_tracing = env_first(
            "HER_DISCOVERY_AGENT_DISABLE_TRACING",
            "HER_CHAT_AGENT_DISABLE_TRACING",
            "HER_CHAT_ASSISTANT_DISABLE_TRACING",
            default="1",
        ).lower()
        if disable_tracing in ("1", "true", "yes"):
            set_tracing_disabled(True)
        return

    # This only selects the Agents SDK wire API (`/responses` vs `/chat/completions`);
    # it is not a remote provider request parameter.
    set_default_openai_api(wire_api)


def _compact_requester_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = dict(profile or {})
    keep_keys = [
        "id",
        "name",
        "gender",
        "age",
        "city",
        "district",
        "height",
        "education",
        "job",
        "income_range",
        "marital_status",
        "has_children",
        "relationship_goal",
        "self_job",
        "self_city",
        "self_relationship_goal",
        "target_gender",
        "target_age_min",
        "target_age_max",
        "target_cities",
        "preferred_traits",
        "must_have_tags",
        "must_not_have_tags",
        "disliked_traits",
        # === Phase 1: 保留 personality 字段 ===
        "personality_traits",
        "personality_availability",
    ]
    return {
        key: profile.get(key)
        for key in keep_keys
        if profile.get(key) not in (None, "", [], {})
    }


def _compact_candidate_personality_context(value: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(value or {})
    keep_keys = [
        "mbti",
        "attachment",
        "big_five",
        "values",
        "sternberg",
        "availability",
        "meta",
    ]
    return {
        key: context.get(key)
        for key in keep_keys
        if context.get(key) not in (None, "", [], {})
    }


def _compact_page_summary(page_summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = dict(page_summary or {})
    compacted_cards: list[dict[str, Any]] = []
    for card in list(summary.get("result_cards") or [])[:3]:
        compacted_cards.append(
            {
                "profile_id": card.get("profile_id"),
                "title": card.get("title"),
                "subtitle": card.get("subtitle"),
                "match_score": card.get("match_score"),
                "reason_summary": card.get("reason_summary"),
                "personality_match_context": _compact_candidate_personality_context(
                    card.get("personality_match_context")
                ),
                "personality_availability": dict(card.get("personality_availability") or {}),
            }
        )
    summary["result_cards"] = compacted_cards
    return summary


def _looks_like_personality_explanation_request(user_message: str | None) -> bool:
    text = str(user_message or "").strip()
    if not text:
        return False
    if "不要重新搜索" in text:
        return True
    keywords = ("为什么", "测评", "MBTI", "依恋", "价值观", "合拍", "性格")
    return any(keyword in text for keyword in keywords)


def _select_explained_candidate(
    page_summary: dict[str, Any],
    user_message: str | None,
) -> dict[str, Any] | None:
    cards = list(page_summary.get("result_cards") or [])
    if not cards:
        return None
    text = str(user_message or "")
    indexed_words = (
        ("第一位", 0),
        ("第一个", 0),
        ("1", 0),
        ("第二位", 1),
        ("第二个", 1),
        ("2", 1),
        ("第三位", 2),
        ("第三个", 2),
        ("3", 2),
    )
    for word, index in indexed_words:
        if word in text and index < len(cards):
            return dict(cards[index] or {})
    for card in cards:
        title = str(card.get("title") or "").strip()
        if title and title.split(" ")[0] in text:
            return dict(card)
    return dict(cards[0] or {})


def _safe_overlap(values: dict[str, Any] | None, candidate_values: dict[str, Any] | None) -> list[str]:
    self_top = {str(item).strip() for item in list((values or {}).get("top_values") or []) if str(item).strip()}
    candidate_top = {
        str(item).strip()
        for item in list((candidate_values or {}).get("top_values") or [])
        if str(item).strip()
    }
    return [item for item in self_top if item in candidate_top]


def _mbti_clause(self_mbti: dict[str, Any] | None, candidate_mbti: dict[str, Any] | None) -> str | None:
    self_type = str((self_mbti or {}).get("type_code") or "").strip()
    candidate_type = str((candidate_mbti or {}).get("type_code") or "").strip()
    if not self_type or not candidate_type:
        return None
    if self_type[:3] and self_type[:3] == candidate_type[:3]:
        return f"MBTI 上你是 {self_type}，她是 {candidate_type}，前 3 个维度很接近，通常都偏务实、慢热、先看长期稳定。"
    if self_type[0] == candidate_type[0]:
        return f"MBTI 上你是 {self_type}，她是 {candidate_type}，相处节奏不会特别冲，比较容易在日常推进上对得上。"
    return f"MBTI 上你是 {self_type}，她是 {candidate_type}，不算完全同型，但能看出都更偏稳定经营，不是很跳脱的组合。"


def _attachment_clause(self_attachment: dict[str, Any] | None, candidate_attachment: dict[str, Any] | None) -> str | None:
    self_type = str((self_attachment or {}).get("type_code") or "").strip()
    candidate_type = str((candidate_attachment or {}).get("type_code") or "").strip()
    if not self_type or not candidate_type:
        return None
    self_anxiety = (self_attachment or {}).get("anxiety")
    candidate_anxiety = (candidate_attachment or {}).get("anxiety")
    if self_type == "secure" and candidate_type == "secure":
        return "依恋上你们都偏安全型，焦虑和回避都不高，关系节奏更稳，没那么容易一方追一方躲。"
    if self_type == candidate_type:
        return f"依恋上你和她都偏 {self_type}，相处预期比较接近，不太容易因为靠近或拉开距离的方式不同而拧巴。"
    if self_anxiety is not None and candidate_anxiety is not None:
        return f"依恋上你们都不是特别高焦虑的组合，沟通时更容易先讲清楚，而不是靠猜。"
    return None


def _values_clause(self_values: dict[str, Any] | None, candidate_values: dict[str, Any] | None) -> str | None:
    overlap = _safe_overlap(self_values, candidate_values)
    if overlap:
        shared = "、".join(overlap[:2])
        return f"价值观上你们都把“{shared}”放得比较前，这类人通常更容易在长期投入和生活方向上同频。"
    self_type = str((self_values or {}).get("value_type") or "").strip()
    candidate_type = str((candidate_values or {}).get("value_type") or "").strip()
    if self_type and candidate_type:
        return f"价值观上你偏{self_type}，她偏{candidate_type}，虽然不完全一样，但都不是只看短期新鲜感的类型。"
    return None


def _build_personality_explanation_fallback(
    run_input: DiscoveryRunInput,
    user_message: str | None,
) -> DiscoveryRuntimeResult | None:
    if not _looks_like_personality_explanation_request(user_message):
        return None
    page_summary = _compact_page_summary((run_input.runtime_context or {}).get("page_summary"))
    candidate = _select_explained_candidate(page_summary, user_message)
    if not candidate:
        return None

    requester_profile = _compact_requester_profile(
        (run_input.runtime_context or {}).get("requester_profile_snapshot")
    )
    self_traits = dict(requester_profile.get("personality_traits") or {})
    candidate_traits = _compact_candidate_personality_context(
        candidate.get("personality_match_context")
    )
    candidate_title = str(candidate.get("title") or "这位").strip() or "这位"
    candidate_name = re.split(r"\s+", candidate_title, maxsplit=1)[0]

    clauses = [
        _mbti_clause(self_traits.get("mbti"), candidate_traits.get("mbti")),
        _attachment_clause(self_traits.get("attachment"), candidate_traits.get("attachment")),
        _values_clause(self_traits.get("values"), candidate_traits.get("values")),
    ]
    message_parts = [part for part in clauses if part]
    if not message_parts:
        return None
    body = f"先说{candidate_name}。{''.join(message_parts[:3])}"
    return DiscoveryRuntimeResult(
        decision=DiscoveryDecision(
            phase="results_shown",
            assistant_message=body,
            criteria_labels=list(run_input.criteria_labels),
            suggested_actions=[],
        )
    )


def _compact_timeline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items[-6:]:
        item_type = str(item.get("item_type") or "").strip()
        if item_type in {"assistant_message", "user_message"}:
            compacted.append(
                {
                    "item_type": item_type,
                    "body": item.get("body"),
                }
            )
            continue
        if item_type == "result_group":
            compacted.append(
                {
                    "item_type": "result_group",
                    "title": item.get("title"),
                    "cards": [
                        {
                            "profile_id": card.get("profile_id"),
                            "title": card.get("title"),
                            "reason_summary": card.get("reason_summary"),
                        }
                        for card in list(item.get("cards") or [])[:3]
                    ],
                }
            )
            continue
        if item_type == "assessment_result":
            card = dict(item.get("card") or {})
            result_data = dict(card.get("result_data") or {})
            # 获取测评类型，支持不同的测评结果结构
            assessment_type = card.get("assessment_type") or result_data.get("assessment_type")

            # MBTI 测评结果
            if assessment_type == "mbti_16" or result_data.get("type_code"):
                compacted.append(
                    {
                        "item_type": "assessment_result",
                        "assessment_type": assessment_type or "mbti_16",
                        "type_code": result_data.get("type_code"),
                        "summary": (
                            (result_data.get("interpretation_data") or {}).get("summary")
                            if isinstance(result_data.get("interpretation_data"), dict)
                            else None
                        ),
                    }
                )
            # 价值观拍卖会结果
            elif assessment_type == "values_auction" or card.get("card_type") == "values_auction_result":
                compacted.append(
                    {
                        "item_type": "assessment_result",
                        "assessment_type": "values_auction",
                        "value_type": result_data.get("value_type"),
                        "top3_titles": [
                            t.get("title") for t in list(result_data.get("top3") or [])[:3]
                            if t.get("chips", 0) > 0
                        ],
                        "top_hidden_values": [
                            hv.get("key") for hv in list(result_data.get("top_hidden_values") or [])[:3]
                        ],
                    }
                )
            # 其他测评结果（兼容处理）
            else:
                compacted.append(
                    {
                        "item_type": "assessment_result",
                        "assessment_type": assessment_type,
                        "summary": (
                            (result_data.get("interpretation_data") or {}).get("summary")
                            if isinstance(result_data.get("interpretation_data"), dict)
                            else None
                        ),
                    }
                )
    return compacted


def _search_response_has_error(search_response: dict[str, Any] | None) -> bool:
    if not isinstance(search_response, dict):
        return False
    if str(search_response.get("error_code") or "").strip():
        return True
    diagnostics = dict(search_response.get("diagnostics") or {})
    return bool(str(diagnostics.get("error") or "").strip())


def _build_runtime_prompt(
    *,
    run_input: DiscoveryRunInput,
    event: str,
    user_message: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> str:
    official_context = dict(run_input.runtime_context or {})
    official_context["requester_profile_snapshot"] = _compact_requester_profile(
        official_context.get("requester_profile_snapshot")
    )
    official_context["recent_timeline_summary"] = _compact_timeline(
        list(official_context.get("recent_timeline_summary") or run_input.recent_timeline)
    )
    official_context["page_summary"] = _compact_page_summary(
        official_context.get("page_summary")
    )

    # === Phase 1: 注入 personality_context ===
    # 从 requester_profile_snapshot 提取测评数据（如果已注入）
    requester_profile = official_context.get("requester_profile_snapshot") or {}
    if requester_profile.get("personality_traits"):
        official_context["personality_context"] = {
            "self_traits": requester_profile.get("personality_traits"),
            "availability": requester_profile.get("personality_availability") or {},
        }

    payload = {
        "event": event,
        "session": {
            "session_id": run_input.session_id,
            "requester_id": run_input.requester_id,
            "profile_id": run_input.profile_id,
            "phase": run_input.phase,
            "criteria_labels": list(run_input.criteria_labels),
        },
        "latest_user_message": str(user_message or "").strip() or None,
        "clicked_action": {
            "label": str((action_context or {}).get("label") or "").strip() or None,
            "hint": dict((action_context or {}).get("semantic_payload") or {}),
        }
        if action_context
        else None,
        "official_context": official_context,
        "note": (
            "Use official_context as the current source of truth for product state. "
            "Agent memory only helps you remember prior chat. "
            "Do not invent candidate raw fields; only select profile_id values from the latest search tool response."
            "\n\nIf personality_context is present, you can use the raw assessment data (MBTI type_code, "
            "attachment anxiety/avoidance scores, values top_values) to judge compatibility yourself. "
            "Do not use hardcoded formulas; make your own judgment based on the context."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class StubDiscoveryAgentRuntime:
    """Fallback runtime for local tests or missing model configuration."""

    def initial_decision(self, _run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult:
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先跟我说说你想找什么样的人，不用一次讲完整。",
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label="先从城市和年龄说起",
                        style="primary",
                        semantic_payload={"kind": "starter_prompt", "slot": "city_and_age"},
                    ),
                    DiscoveryActionSuggestion(
                        label="先说你最在意的 3 个条件",
                        semantic_payload={"kind": "starter_prompt", "slot": "top_preferences"},
                    ),
                ],
            )
        )

    def run_turn(
        self,
        run_input: DiscoveryRunInput,
        *,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult:
        action_hint = dict((action_context or {}).get("semantic_payload") or {})
        if action_hint.get("kind") == "saved_search_opt_in":
            tool_result = run_input.create_saved_search_subscription_from_last_search()
            if tool_result.get("created_subscription"):
                title = str(tool_result.get("title") or "这次持续留意").strip()
                body = f"好，我已经替你记下了，后面有合适的人会按“{title}”继续帮你留意。"
            elif tool_result.get("already_exists"):
                body = "这轮条件我已经替你记下了，后面有新的合适人选我会继续留意。"
            else:
                body = "我这边先没成功帮你记下持续留意，你可以稍后再点一次，我也可以先陪你调整条件。"
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="no_result",
                    assistant_message=body,
                    criteria_labels=list(run_input.criteria_labels),
                    suggested_actions=[],
                )
            )

        # 【新增】处理rejection_feedback（反馈收集）
        if action_hint.get("kind") == "rejection_feedback":
            feedback_type = action_hint.get("feedback_type") or "unknown"
            feedback_text = str(action_context.get("label") or "职业不太匹配")

            # 1. 调用submit_rejection_feedback记录反馈
            feedback_result = run_input.submit_rejection_feedback(
                feedback_text=feedback_text,
                feedback_type=feedback_type,
                feedback_detail="",
                is_secondary=False,
            )

            # 2. 调用search_partner_candidates搜索新候选人
            # TODO: 这里应该根据feedback_type调整criteria
            search_result = run_input.search_partner_candidates(
                criteria_json={},  # 使用当前criteria，后续可调整
                limit=5,
            )

            # 3. 构建返回结果
            candidates = []
            if search_result.get("results"):
                for item in search_result.get("results")[:5]:
                    candidates.append({
                        "profile_id": item.get("id"),
                        "reason_summary": item.get("match_reason") or "匹配度较高",
                    })

            # 根据反馈类型生成文案
            if feedback_type == "occupation_mismatch":
                body = "明白了，你倾向于其他职业方向。我再帮你调整，这次试试医药、教育、行政类的女生。"
            elif feedback_type == "location_distance":
                body = "明白了，你希望同城优先。我帮你调整一下，找杭州附近的女生。"
            elif feedback_type == "work_life_balance":
                body = "明白了，你希望找生活规律的女生。我帮你调整一下，找作息稳定、不加班的。"
            else:
                body = f'收到，你点了"{feedback_text}"。我帮你调整一下搜索条件。'

            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="results_shown",
                    assistant_message=body,
                    criteria_labels=list(run_input.criteria_labels),
                    selected_candidates=candidates,
                    suggested_actions=[
                        DiscoveryActionSuggestion(
                            label="看看更多",
                            semantic_payload={},
                            style="ghost",
                        ),
                        DiscoveryActionSuggestion(
                            label="调整条件",
                            semantic_payload={},
                            style="secondary",
                        ),
                    ],
                ),
                search_response=search_result,
            )

        if action_context is not None:
            label = str(action_context.get("label") or "这个选项")
            body = f"收到，你点了“{label}”。我再帮你把条件收一收，然后继续找。"
        elif user_message:
            body = "收到。我先把你的偏好整理一下，你也可以继续补充年龄、城市或关系期待。"
        else:
            body = "收到。我先继续帮你整理条件。"
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message=body,
                criteria_labels=list(run_input.criteria_labels),
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label="继续补充年龄范围",
                        semantic_payload={"kind": "followup_prompt", "slot": "age_range"},
                    ),
                    DiscoveryActionSuggestion(
                        label="继续补充城市和定居意向",
                        semantic_payload={"kind": "followup_prompt", "slot": "city_intent"},
                    ),
                ],
            )
        )


class AgentsSdkDiscoveryAgentRuntime:
    def __init__(self, *, fallback: DiscoveryAgentRuntime | None = None) -> None:
        self._fallback = fallback or StubDiscoveryAgentRuntime()

    def initial_decision(self, run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult:
        return self._run_or_fallback(
            run_input,
            event="session_opened",
        )

    def run_turn(
        self,
        run_input: DiscoveryRunInput,
        *,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult:
        return self._run_or_fallback(
            run_input,
            event="action_click" if action_context is not None else "user_message",
            user_message=user_message,
            action_context=action_context,
        )

    def _run_or_fallback(
        self,
        run_input: DiscoveryRunInput,
        *,
        event: str,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult:
        if not self._should_use_agents_sdk():
            _logger.warning(
                "discovery agent using stub runtime: agents_sdk disabled or API key missing"
            )
            explained = _build_personality_explanation_fallback(run_input, user_message)
            if explained is not None:
                return explained
            return self._fallback_result(
                run_input,
                user_message=user_message,
                action_context=action_context,
            )
        try:
            return self._run_with_agents_sdk(
                run_input,
                event=event,
                user_message=user_message,
                action_context=action_context,
            )
        except Exception as exc:  # noqa: BLE001
            recovered = _recover_decision_from_exception(exc)
            if recovered is not None:
                return DiscoveryRuntimeResult(decision=recovered)
            _logger.warning(
                "discovery agent fell back to stub after model error: %s: %s",
                type(exc).__name__,
                exc,
            )
            explained = _build_personality_explanation_fallback(run_input, user_message)
            if explained is not None:
                return explained
            return self._fallback_result(
                run_input,
                user_message=user_message,
                action_context=action_context,
            )

    def _fallback_result(
        self,
        run_input: DiscoveryRunInput,
        *,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult:
        if user_message is None and action_context is None:
            return self._fallback.initial_decision(run_input)
        return self._fallback.run_turn(
            run_input,
            user_message=user_message,
            action_context=action_context,
        )

    def _should_use_agents_sdk(self) -> bool:
        runtime = env_first(
            "HER_DISCOVERY_AGENT_RUNTIME",
            "HER_CHAT_AGENT_RUNTIME",
            default="agents_sdk",
        ).lower()
        if runtime in {"stub", "heuristic", "fallback"}:
            return False
        api_key = _resolve_discovery_api_key().strip()
        if not api_key or api_key.startswith("replace-with-"):
            return False
        return True

    def _run_with_agents_sdk(
        self,
        run_input: DiscoveryRunInput,
        *,
        event: str,
        user_message: str | None,
        action_context: dict[str, Any] | None,
    ) -> DiscoveryRuntimeResult:
        try:
            from agents import Agent, AgentOutputSchema, Runner, function_tool
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Missing Agents SDK dependency. Install `openai-agents`.") from exc

        _configure_agents_sdk_provider()
        tool_state: dict[str, Any] = {"last_search_response": None}

        @function_tool
        def sync_requester_persona_memory(patch_json: str) -> dict[str, Any]:
            patch = json.loads(str(patch_json or "{}"))
            if not isinstance(patch, dict):
                raise ValueError("patch_json must decode into a JSON object")
            return run_input.sync_requester_persona_memory(patch)

        @function_tool
        def propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
            return run_input.propose_requester_profile_update(patch_json, evidence_text)

        @function_tool
        def search_partner_candidates(criteria_json: str, limit: int = 5) -> dict[str, Any]:
            criteria = json.loads(str(criteria_json or "{}"))
            if not isinstance(criteria, dict):
                raise ValueError("criteria_json must decode into a JSON object")
            normalized_limit = max(1, min(int(limit or 5), 10))
            response = run_input.search_partner_candidates(criteria, normalized_limit)
            tool_state["last_search_response"] = response
            return response

        @function_tool
        def create_saved_search_subscription_from_last_search() -> dict[str, Any]:
            return run_input.create_saved_search_subscription_from_last_search()

        @function_tool
        def submit_rejection_feedback(
            feedback_text: str,
            feedback_type: str = "",
            feedback_detail: str = "",
            is_secondary: bool = False,
        ) -> dict[str, Any]:
            """提交拒绝反馈，用于记录用户对上一批候选人的不满原因。"""
            return run_input.submit_rejection_feedback(
                feedback_text=feedback_text,
                feedback_type=feedback_type if feedback_type else None,
                feedback_detail=feedback_detail if feedback_detail else None,
                is_secondary=is_secondary,
            )

        @function_tool
        def get_feedback_options(
            include_secondary: bool = False,
            primary_option: str = "",
        ) -> dict[str, Any]:
            """获取反馈选项列表，用于展示给用户选择。"""
            return run_input.get_feedback_options(
                include_secondary=include_secondary,
                primary_option=primary_option if primary_option else None,
            )

        instructions = """
你是发现页里的 AI 红娘。

你的职责：
1. 和用户自然对话，帮她/他整理择偶偏好。
2. 后端已经把当前正式状态放进 official_context。你要以它为准。
3. 你自己决定什么时候继续追问，什么时候先写画像，什么时候调用搜索工具。
4. 只有用户说出了明确、稳定、适合落库的新信息时，才调用画像写回工具。
5. 涉及用户本人正式资料（城市、年龄、婚况、恋爱目标等）时，用 `propose_requester_profile_update`，不要直接写 profiles；用户确认后才会落库。
6. 扩大搜索范围（城市、年龄等）优先写入搜索条件或 persona 偏好，用 `search_partner_candidates` / `sync_requester_persona_memory` 的 target_* 字段。
7. 常见顺序是：先写偏好，再搜索。

【重要：测评推荐的优先级】
当你识别到测评话题（MBTI、依恋风格）并主动询问用户后，如果用户回复"不知道"、"没测过"，立即返回测评测试按钮。这一优先级高于整理偏好。不要回复"我先把你的偏好整理一下"，而是直接接住用户的话并给出测试按钮。

6. 如果条件还不够，就只问 1 个最关键的问题。（例外：如果你刚刚询问了用户的测评类型，而用户回复"不知道"，优先返回测评测试按钮，不要问偏好问题。）
7. 如果条件已经够用，就调用搜索工具。
8. 如果搜索到结果，你负责决定展示哪几位、重点强调什么。
9. 但你不能编造候选人的原始卡片字段。你只能输出 profile_id 和 reason_summary，后端会去填卡片标题、照片、认证等稳定字段。
10. 如果页面上已经有 result_cards，且用户是在追问“为什么推荐她/他”“从测评怎么看”“MBTI/依恋/价值观为什么合拍”，优先基于 page_summary.result_cards 里的现有候选人解释，不要重新搜索，也不要退回到泛泛的“继续补充条件”。

official_context 里常见信息：
- requester_profile_snapshot：用户当前画像快照
- recent_timeline_summary：最近几轮页面时间线摘要
- visible_actions：当前页面还能点哪些 action
- last_search_summary：最近一轮搜索摘要
- page_summary：当前页面上的 criteria chips、结果卡片摘要等
  - page_summary.result_cards 里如果有 personality_match_context，就是当前已经展示给用户的候选人原始测评数据；用户追问“为什么推荐”时，直接用它解释。

工具说明：
- `sync_requester_persona_memory`：写择偶偏好到 persona（不会直接改 profiles 正式资料）。
  - 参数 `patch_json` 必须是 JSON 字符串。
  - 常用：target_gender, target_age_min, target_age_max, target_cities, must_have_tags, must_not_have_tags, preferred_traits, disliked_traits。
  - 例子：{"target_cities":"上海,苏州","target_age_min":24,"target_age_max":38}.
- `propose_requester_profile_update`：提议修改用户本人正式资料，等待用户确认后再落库。
  - 用于 self_city→city、婚况、恋爱目标等 profile 字段；参数 `patch_json` 用 profiles 字段名或 self_* 字段名。
  - 例子：{"city":"杭州"} 或 {"self_city":"杭州"}；可附 evidence_text 简述依据。
- `search_partner_candidates`：执行候选搜索。
  - 参数 `criteria_json` 必须是 JSON 字符串，对应 partner-search 的 criteria 对象。
  - 常见字段可以用：gender, city, cities, age_min, age_max, relationship_goal, relationship_goals, must_have, prefer, smoking, drinking, verified_level_min, photo_count_min, active_within_days。
  - 例子：{"gender":"女","cities":["无锡"],"relationship_goals":["认真恋爱"],"must_have":["情绪稳定"],"prefer":["工作稳定"]}.
  - 如果工具返回了 `error_code` 或 `diagnostics.error`，说明这轮搜索失败了，不是没有候选人。
- `create_saved_search_subscription_from_last_search`：把上一轮 0 结果搜索保存成“持续留意”订阅。
  - 只有在用户已经明确同意“继续留意”时才能调用。
  - 不要在还有匹配结果时调用。

工具调用要求：
- 需要用工具时，必须走系统提供的真实 tool calling 机制。
- 不要把 `tool_calls`、`function_call`、工具参数对象手写进最终 JSON。
- 不要输出形如 `{"tool_calls":[...]}` 的文本。
- 工具调用完成后，再输出最终 JSON。
- 最终 JSON 只能包含 DiscoveryDecisionModel 定义的字段，不能包含 `tool_calls` 之类额外字段。

输出原则：
- assistant_message 保持短，像真人红娘，不要写成系统说明。
- 不要提“前端弹窗”“系统已记录”“工具调用”等实现细节。
- phase 只能是：collecting_preferences、searching、results_shown、no_result。不要自造 phase 名。
- 如果你正在展示候选卡片，phase 必须是 `results_shown`。
- criteria_labels 用于给前端展示条件 chips，最多 6 个。
- suggested_actions 最多 3 个，标签要短。
- suggested_actions.style 只能是：primary、secondary、ghost。
- semantic_payload.kind 只用这些值：starter_prompt、followup_prompt、saved_search_opt_in、refine_candidates、add_criteria、refine_preferences、show_more_candidates、age_preference、start_assessment、rejection_feedback。
- **rejection_feedback 用于反馈收集选项**，点击后Agent应执行第二轮逻辑（记录反馈+搜索新候选人）。
- start_assessment 用于推荐测评，semantic_payload 里放 {"kind":"start_assessment","assessment_type":"mbti"}。
- 如果用户更新了本人资料，先 `propose_requester_profile_update`；如果只是择偶偏好，用 `sync_requester_persona_memory`。
- 只有在你真的调用了搜索工具并且决定展示结果时，才填写 selected_candidates。
- selected_candidates 里的 profile_id 必须来自最新一次搜索工具返回的 results。
- 如果搜索工具返回 `error_code` 或 `diagnostics.error`，不要说“本地没有符合条件的人”。要自然说明这轮搜索失败了，不代表没人，并引导用户重试或继续补充条件。
- 如果没有合适结果，phase 用 no_result，message 里自然说明，并给 1 到 2 个放宽方向。
- 如果搜索 0 结果且你判断适合引导持续留意，可以给一个 action，semantic_payload 里放 `{"kind":"saved_search_opt_in"}`。
- 如果本轮是 action_click，且 clicked_action.hint.kind 是 `saved_search_opt_in`，说明用户刚刚同意了持续留意；这时你应该优先调用 `create_saved_search_subscription_from_last_search`，再告诉用户你已经记下。
- 如果 page_summary.result_cards 已有候选人，且用户是在追问当前候选人的测评适配性：
  - 不要要求用户继续补年龄、城市。
  - 不要重复搜索。
  - assistant_message 直接给解释。
  - 如果你引用了当前候选人的测评，请把该候选人继续放进 selected_candidates，这样前端能保留同一组卡片。
- reason_summary 应尽量写成用户能看懂的匹配理由，优先引用双方的 MBTI、依恋风格、价值观；如果候选人没测评，再用“从资料看”“可能”等谨慎表达。

【测评推荐优先级说明】
当你主动询问了用户的测评类型（MBTI、依恋风格），而用户回复"不知道"、"没测过"、"不清楚"时，优先返回测评测试按钮。这一优先级高于"收集偏好"任务。不要转去问年龄、城市等偏好问题。

性格话题与测评推荐（分两轮进行）：

**第一轮：主动询问**
- 在聊匹配话题、相处方式、性格合拍等场景时，你可以主动询问用户："你知道自己是MBTI中哪种性格吗？"或"你测过MBTI吗？"
- 询问要自然，像聊天一样，不要像问卷。比如："对了，你了解自己的性格类型吗？比如MBTI那种？"
- 这一轮不要返回测试按钮，只询问。

**第二轮：用户说不知道后立即推荐测试**
- 只有当用户明确回复"不知道"、"没测过"、"不太清楚"、"没做过"等表示不清楚自己MBTI类型时，才在下一轮返回测试按钮。
- 推荐方式：在 suggested_actions 里加一个按钮，label 写"开始MBTI测试"，style 用 primary，semantic_payload 放 {"kind":"start_assessment","assessment_type":"mbti"}。
- 回复要接住用户的话，比如："没关系呀，做个简单的测试就能了解了，也能帮你找到更合拍的匹配对象。"
- 不要在这一轮问年龄、城市等偏好问题。

**不推荐的情况**
- 如果用户已经说出了自己的MBTI类型（如"我是INFP"），不要推荐测试。
- 如果 official_context.recent_timeline_summary 里已有 assessment_result 且 type_code 是 mbti，说明用户已经完成过测试，不要重复推荐。
- 不要在用户还没回答你的询问时就直接返回测试按钮。

依恋风格话题与测评推荐（分两轮进行）：

【换一批反馈收集 - 学习闭环】
当用户说"换一批"、"重新找"、"再看几位"、"再给我看看"等类似表达时：

**⚠️ 重要：两轮流程**

**第一轮：用户说"换一批"**
- 返回 assistant_message："好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准"
- 返回 suggested_actions（4-6个具体选项）
- **⚠️ 关键：每个选项的 semantic_payload 必须包含反馈类型！**

**必须设置 semantic_payload（这是核心问题！）**：
```json
{
  "kind": "rejection_feedback",
  "feedback_type": "具体类型",
  "feedback_text": "用户看到的文案"
}
```

**选项示例（必须包含完整的payload）**：
```json
{
  "label": "太远了（都是异地）",
  "semantic_payload": {
    "kind": "rejection_feedback",
    "feedback_type": "location_distance",
    "feedback_text": "太远了（都是异地）"
  },
  "style": "ghost"
},
{
  "label": "职业不太匹配（程序员偏多）",
  "semantic_payload": {
    "kind": "rejection_feedback",
    "feedback_type": "occupation_mismatch",
    "feedback_text": "职业不太匹配（程序员偏多）"
  },
  "style": "secondary"
}
```

**❌ 严禁返回空的 semantic_payload**：
```json
{
  "label": "职业不太匹配",
  "semantic_payload": {},  // ❌ 错误！Agent无法识别这是反馈选项
  "style": "secondary"
}
```

**第二轮：用户点击反馈选项后**
**识别反馈选项点击**：
- action_click 且 semantic_payload.kind = "rejection_feedback"
- 必须从 semantic_payload.feedback_type 获取反馈类型

**必须做的事情**：
1. 调用 submit_rejection_feedback 工具（参数：feedback_text, feedback_type）
2. 调用 search_partner_candidates 工具（使用调整后的条件）
3. 返回 selected_candidates（展示3-5个新候选人）
4. 返回 assistant_message：说明调整了什么

**正确的第二轮响应**：
```json
{
  "phase": "results_shown",
  "assistant_message": "明白了，你倾向于其他职业方向。我再帮你调整，这次试试公务员、教师、销售等类型的女生。",
  "selected_candidates": [
    {"profile_id": 1, "reason_summary": "28岁，杭州，公务员，作息稳定"},
    {"profile_id": 2, "reason_summary": "30岁，杭州，教师，有生活品质"},
    {"profile_id": 3, "reason_summary": "26岁，杭州，销售，性格开朗"}
  ]
}
```

**追问时机**：
- 用户选择"每次都追问"策略，所以每次"换一批"都应该追问
- 用户主动表达不满时（如"都太忙太卷了"）：不追问，直接记录并调整

**具体选项示例**（根据上一批候选人特征动态选择）：
- 动态选项：太远了（都是异地）、年龄差距有点大（候选人28-35，你26）、职业不太匹配（程序员偏多）、太忙太卷（工作压力大的感觉）
- 通用选项：性格气质不对（相处感觉不搭）、外在条件不合适（年龄/学历/收入）、生活节奏不匹配（工作生活状态）、兴趣爱好不一样（玩不到一起）
- 跳过选项：跳过，直接换

**反馈类型映射**（用于 semantic_payload.feedback_type）**：
- 太远了 → location_distance
- 年龄差距有点大 → age_gap 或 criteria_age（二级追问）
- 职业不太匹配 → occupation_mismatch
- 太忙太卷 → work_life_balance
- 性格气质不对 → personality_mismatch
- 外在条件不合适 → criteria_generic（触发二级追问）
- 生活节奏不匹配 → work_life_balance
- 兴趣爱好不一样 → interest_mismatch
- 跳过，直接换 → skip_feedback

**二级追问**：
- 如果用户选择"外在条件不合适"，需要在下一轮追问："具体是哪个条件不太对？"
- 二级选项：年龄差距有点大、学历不太匹配、收入差距有点大、城市太远了、都不太合适、不想说直接换

**注意事项**：
- **⚠️ 最重要：每个反馈选项都必须设置完整的 semantic_payload！**
- 不要强制追问，用户可以点击"跳过，直接换"
- 追问语气要自然、口语化，像真人红娘
- 用户点击反馈选项后，必须调用工具并返回候选人卡片

**触发场景**
- 用户提到"黏人/独立"、"安全感/空间"、"患得患失"、"怕被抛弃"、"冷暴力"、"焦虑"、"回避"等话题
- 用户表达恋爱里的焦虑感，比如"对象回消息慢我就很焦虑，担心TA不爱我了"

**第一轮：主动询问**
- 自然地问："你了解自己在恋爱里的依恋风格吗？比如安全型、焦虑型、回避型这些。"
- 或者："这种焦虑感其实和你在恋爱里的依恋风格有关。你测过依恋风格吗？"
- 这一轮不返回测试按钮。

**第二轮：用户说不知道后立即推荐测试**
- 用户回复"不知道"、"没测过"后，立即返回测试按钮，不要问年龄、城市等偏好问题。
- 推荐方式：suggested_actions 里加按钮，label 写"开始依恋风格测试"，style 用 primary，semantic_payload 放 {"kind":"start_assessment","assessment_type":"attachment"}。

输出必须是合法 JSON，只输出结构化结果，不要加代码块。
"""

        agent = Agent(
            name="discovery_matchmaker",
            instructions=instructions.strip(),
            model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
            output_type=AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=True),
            tools=[
                sync_requester_persona_memory,
                propose_requester_profile_update,
                search_partner_candidates,
                create_saved_search_subscription_from_last_search,
                submit_rejection_feedback,
                get_feedback_options,
            ],
        )
        result = Runner.run_sync(
            agent,
            input=_build_runtime_prompt(
                run_input=run_input,
                event=event,
                user_message=user_message,
                action_context=action_context,
            ),
            session=run_input.agent_session,
        )
        final_output = getattr(result, "final_output", result)
        decision = (
            _to_decision(final_output)
            if isinstance(final_output, DiscoveryDecisionModel)
            else _validate_decision_output(final_output)
        )
        search_response = tool_state.get("last_search_response")
        if search_response is not None and decision.phase == "searching":
            decision = DiscoveryDecision(
                phase=(
                    "collecting_preferences"
                    if _search_response_has_error(search_response)
                    else "results_shown"
                    if search_response.get("has_match")
                    else "no_result"
                ),
                assistant_message=decision.assistant_message,
                criteria_labels=decision.criteria_labels,
                suggested_actions=decision.suggested_actions,
                result_group_title=decision.result_group_title,
                selected_candidates=decision.selected_candidates,
            )
        explained = _build_personality_explanation_fallback(run_input, user_message)
        if (
            explained is not None
            and decision.phase == "collecting_preferences"
            and "继续补充" in decision.assistant_message
        ):
            return explained
        return DiscoveryRuntimeResult(
            decision=decision,
            search_response=search_response,
        )


def create_default_discovery_agent_runtime() -> DiscoveryAgentRuntime:
    return AgentsSdkDiscoveryAgentRuntime(fallback=StubDiscoveryAgentRuntime())


__all__ = [
    "AgentsSdkDiscoveryAgentRuntime",
    "DiscoveryActionSuggestion",
    "DiscoveryActionSuggestionModel",
    "DiscoveryAgentRuntime",
    "DiscoveryCandidateSelection",
    "DiscoveryDecision",
    "DiscoveryDecisionModel",
    "DiscoveryRunInput",
    "DiscoveryRuntimeResult",
    "DiscoveryToolCall",
    "StubDiscoveryAgentRuntime",
    "create_default_discovery_agent_runtime",
]
