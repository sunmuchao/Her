"""Agents SDK-backed runtime for the discovery page."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

_logger = logging.getLogger(__name__)

from her_env import env_first, env_float
from pydantic import BaseModel, Field

from .decision_models import (
    DiscoveryActionSuggestion,
    DiscoveryActionSuggestionModel,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryDecisionModel,
    DecisionPayloadModel,  # 方案C新增
    DiscoveryRuntimeResult,
    DiscoveryToolCall,
    recover_decision_from_exception as _recover_decision_from_exception,
    to_decision as _to_decision,
    validate_decision_output as _validate_decision_output,
    decision_payload_to_decision as _decision_payload_to_decision,  # 方案C新增
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
_DISCOVERY_CONTEXT_WARN_CHARS = 16000
_DISCOVERY_CONTEXT_ERROR_CHARS = 32000
_DISCOVERY_BATCH_REFRESH_PATTERNS = (
    "换一批",
    "重新找",
    "再看几位",
    "再给我看看",
    "看看更多",
    "看更多",
    "换一组",
)


class RejectionFeedbackParseModel(BaseModel):
    is_rejection_feedback: bool = True
    feedback_type: str = ""
    summary: str = ""
    search_criteria_patch: dict[str, Any] = Field(default_factory=dict)


def _safe_json_length(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _candidate_summary_for_model(candidate: dict[str, Any]) -> str:
    profile = dict(candidate.get("profile") or {})
    parts: list[str] = []
    age = candidate.get("age") or profile.get("age")
    city = candidate.get("city") or profile.get("city")
    job = candidate.get("job") or profile.get("job")
    education = candidate.get("education") or profile.get("education")
    relationship_goal = candidate.get("relationship_goal") or profile.get("relationship_goal")
    match_reason = candidate.get("match_reason") or candidate.get("reason_summary")
    if age:
        parts.append(f"{age}岁")
    if city:
        parts.append(str(city))
    if job:
        parts.append(str(job))
    if education:
        parts.append(str(education))
    if relationship_goal:
        parts.append(str(relationship_goal))
    if match_reason:
        parts.append(str(match_reason))
    return "，".join(part for part in parts if part)


def _summarize_search_response_for_model(search_response: dict[str, Any]) -> dict[str, Any]:
    response = dict(search_response or {})
    summary: dict[str, Any] = {
        "has_match": bool(response.get("has_match")),
        "result_count": int(response.get("result_count") or 0),
        "results": [],
    }
    error_code = str(response.get("error_code") or "").strip()
    diagnostics = dict(response.get("diagnostics") or {})
    error_message = str(diagnostics.get("error") or "").strip()
    if error_code:
        summary["error_code"] = error_code
    if error_message:
        summary["diagnostics"] = {"error": error_message}
    request_meta = dict(response.get("request_meta") or {})
    if request_meta:
        compact_meta: dict[str, Any] = {}
        criteria = request_meta.get("criteria")
        if isinstance(criteria, dict) and criteria:
            compact_meta["criteria"] = criteria
        for key in ("limit", "limit_count"):
            if request_meta.get(key) is not None:
                compact_meta[key] = request_meta.get(key)
        if compact_meta:
            summary["request_meta"] = compact_meta

    results_summary: list[dict[str, Any]] = []
    for candidate in list(response.get("results") or [])[:5]:
        if not isinstance(candidate, dict):
            continue
        profile_id = int(candidate.get("id") or candidate.get("profile_id") or 0)
        if profile_id <= 0:
            continue
        title = str(candidate.get("name") or candidate.get("title") or "").strip()
        item = {
            "profile_id": profile_id,
            "title": title or None,
            "summary": _candidate_summary_for_model(candidate),
        }
        score = candidate.get("score") or candidate.get("fit_score")
        if score is not None:
            item["score"] = score
        results_summary.append(item)
    summary["results"] = results_summary
    return summary


def _tool_schema_debug_payload(tools: list[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for tool in tools:
        entry = {"name": getattr(tool, "name", None) or getattr(tool, "__name__", "")}
        for attr in ("params_json_schema", "input_json_schema"):
            schema = getattr(tool, attr, None)
            if schema:
                entry["schema"] = schema
                break
        payload.append(entry)
    return payload


def _model_input_item_count(runtime_input: Any) -> int:
    if runtime_input is None:
        return 0
    if isinstance(runtime_input, str):
        return 1 if runtime_input.strip() else 0
    if isinstance(runtime_input, list):
        return len(runtime_input)
    return 1


def _log_discovery_context_size(
    *,
    event: str,
    instructions: str,
    runtime_input: str,
    output_schema: Any,
    tools: list[Any],
) -> None:
    messages_count = _model_input_item_count(runtime_input)
    instructions_chars = len(instructions)
    input_chars = len(runtime_input)
    schema_chars = _safe_json_length(output_schema.json_schema()) if output_schema else 0  # 方案C：处理 None
    tools_chars = _safe_json_length(_tool_schema_debug_payload(tools))
    total_chars = instructions_chars + input_chars + schema_chars + tools_chars
    level = logging.DEBUG
    if total_chars >= _DISCOVERY_CONTEXT_ERROR_CHARS:
        level = logging.ERROR
    elif total_chars >= _DISCOVERY_CONTEXT_WARN_CHARS:
        level = logging.WARNING
    _logger.log(
        level,
        "discovery agent context size event=%s messages_count=%s instructions_chars=%s input_chars=%s schema_chars=%s tools_chars=%s total_chars=%s rough_tokens=%s",
        event,
        messages_count,
        instructions_chars,
        input_chars,
        schema_chars,
        tools_chars,
        total_chars,
        round(total_chars / 4),
    )


def _stream_event_type(event: Any) -> str:
    return str(getattr(event, "type", "") or "").strip()


def _raw_stream_data_type(event: Any) -> str:
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        return str(data.get("type") or "").strip()
    return str(getattr(data, "type", "") or "").strip()


def _is_first_token_stream_event(event: Any) -> bool:
    if _stream_event_type(event) != "raw_response_event":
        return False
    data_type = _raw_stream_data_type(event)
    if not data_type:
        return False
    return any(marker in data_type for marker in ("delta", "text"))


def _usage_debug_payload(run_result: Any) -> dict[str, Any]:
    context_wrapper = getattr(run_result, "context_wrapper", None)
    usage = getattr(context_wrapper, "usage", None)
    if usage is None:
        return {
            "requests": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }
    return {
        "requests": getattr(usage, "requests", None),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


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


def _fallback_rejection_feedback_parse(user_message: str) -> dict[str, Any]:
    from .feedback_service import infer_feedback_type

    text = str(user_message or "").strip()
    feedback_type = str(infer_feedback_type(text) or "").strip()
    patch: dict[str, Any] = {}
    if feedback_type == "work_life_balance":
        patch = {
            "prefer": ["工作稳定", "生活规律"],
            "must_not_have": ["高强度工作"],
        }
    elif feedback_type == "location_distance":
        patch = {"prefer": ["同城优先"]}
    elif feedback_type in {"age_gap", "criteria_age"}:
        patch = {"prefer": ["年龄接近"]}
    elif feedback_type == "occupation_mismatch":
        patch = {"prefer": ["职业匹配"]}
    return {
        "is_rejection_feedback": bool(feedback_type),
        "feedback_type": feedback_type,
        "summary": text,
        "search_criteria_patch": patch,
    }


def parse_rejection_feedback_text(
    user_message: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = str(user_message or "").strip()
    if not text:
        return {
            "is_rejection_feedback": False,
            "feedback_type": "",
            "summary": "",
            "search_criteria_patch": {},
        }
    if not _resolve_discovery_api_key().strip():
        return _fallback_rejection_feedback_parse(text)

    try:
        from agents import Agent, AgentOutputSchema, Runner
    except ImportError:
        return _fallback_rejection_feedback_parse(text)

    try:
        _configure_agents_sdk_provider()
        agent = Agent(
            name="discovery_feedback_parser",
            instructions=(
                "你负责把用户对上一批候选人的自由文本反馈，解析成结构化搜索意图。"
                "当前前提是：系统已经明确问过用户“上一批哪里不合适”。"
                "你的任务不是陪聊，而是判断这句话是不是在回答这个问题。"
                "如果是，输出 is_rejection_feedback=true，并尽量给出 feedback_type 和 search_criteria_patch。"
                "feedback_type 优先使用这些类型：location_distance, age_gap, criteria_age, "
                "occupation_mismatch, work_life_balance, interest_mismatch, personality_mismatch, criteria_generic。"
                "search_criteria_patch 只放 discovery search 可用字段，例如 prefer, must_not_have, must_have, cities, age_min, age_max。"
                "不要输出解释性长文，summary 保留一句简短中文概括。"
            ),
            model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
            output_type=AgentOutputSchema(RejectionFeedbackParseModel, strict_json_schema=True),
            tools=[],
        )
        payload = json.dumps(
            {
                "user_message": text,
                "current_results": _normalize_current_results(runtime_context),
                "last_search": _normalize_last_search(runtime_context) or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result = Runner.run_sync(agent, input=payload)
        final_output = getattr(result, "final_output", result)
        if isinstance(final_output, RejectionFeedbackParseModel):
            return final_output.model_dump(mode="json")
        parsed = RejectionFeedbackParseModel.model_validate(final_output)
        return parsed.model_dump(mode="json")
    except Exception:
        return _fallback_rejection_feedback_parse(text)


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
        "gender",
        "age",
        "city",
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
    ]
    compact = {
        key: profile.get(key)
        for key in keep_keys
        if profile.get(key) not in (None, "", [], {})
    }
    personality_traits = dict(profile.get("personality_traits") or {})
    compact_traits: dict[str, Any] = {}
    mbti_type = str(dict(personality_traits.get("mbti") or {}).get("type_code") or "").strip()
    if mbti_type:
        compact_traits["mbti"] = {"type_code": mbti_type}
    attachment_type = str(dict(personality_traits.get("attachment") or {}).get("type_code") or "").strip()
    if attachment_type:
        compact_traits["attachment"] = {"type_code": attachment_type}
    values = dict(personality_traits.get("values") or {})
    value_type = str(values.get("value_type") or "").strip()
    top_values = [str(item).strip() for item in list(values.get("top_values") or []) if str(item).strip()][:2]
    compact_values: dict[str, Any] = {}
    if value_type:
        compact_values["value_type"] = value_type
    if top_values:
        compact_values["top_values"] = top_values
    if compact_values:
        compact_traits["values"] = compact_values
    if compact_traits:
        compact["personality_traits"] = compact_traits
    return compact


def _normalize_session_state(
    run_input: DiscoveryRunInput,
    runtime_context: dict[str, Any] | None,
) -> dict[str, Any]:
    session_context = dict((runtime_context or {}).get("session") or {})
    return {
        "session_id": str(session_context.get("session_id") or run_input.session_id),
        "phase": str(session_context.get("phase") or run_input.phase),
        "criteria_labels": list(session_context.get("criteria_labels") or run_input.criteria_labels or []),
        "status": session_context.get("status"),
    }


def _normalize_user_profile(runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    profile = (runtime_context or {}).get("user_profile")
    if profile is None:
        profile = (runtime_context or {}).get("requester_profile_snapshot")
    return _compact_requester_profile(profile)


def _compact_candidate_personality_context(value: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(value or {})
    compact: dict[str, Any] = {}
    mbti = dict(context.get("mbti") or {})
    mbti_type = str(mbti.get("type_code") or "").strip()
    if mbti_type:
        compact["mbti"] = {"type_code": mbti_type}
    attachment = dict(context.get("attachment") or {})
    attachment_type = str(attachment.get("type_code") or "").strip()
    if attachment_type:
        compact["attachment"] = {"type_code": attachment_type}
    values = dict(context.get("values") or {})
    value_type = str(values.get("value_type") or "").strip()
    top_values = [str(item).strip() for item in list(values.get("top_values") or []) if str(item).strip()][:2]
    compact_values: dict[str, Any] = {}
    if value_type:
        compact_values["value_type"] = value_type
    if top_values:
        compact_values["top_values"] = top_values
    if compact_values:
        compact["values"] = compact_values
    return compact


def _compact_current_results(
    results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    compacted_cards: list[dict[str, Any]] = []
    for card in list(results or [])[:3]:
        compacted_cards.append(
            {
                "profile_id": card.get("profile_id"),
                "title": card.get("title"),
                "reason_summary": card.get("reason_summary"),
                "compatibility_summary": card.get("compatibility_summary"),
                "personality_signals": _compact_candidate_personality_context(
                    card.get("personality_signals") or card.get("personality_match_context")
                ),
            }
        )
    return compacted_cards


def _normalize_current_results(runtime_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    current_results = (runtime_context or {}).get("current_results")
    if current_results is not None:
        return _compact_current_results(list(current_results or []))
    page_summary = dict((runtime_context or {}).get("page_summary") or {})
    return _compact_current_results(list(page_summary.get("result_cards") or []))


def _compact_visible_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for action in list(actions or [])[:3]:
        hint = dict(action.get("hint") or {})
        compact_hint: dict[str, Any] = {}
        kind = str(action.get("kind") or hint.get("kind") or "").strip() or None
        if kind:
            compact_hint["kind"] = kind
        for key in ("slot", "feedback_type", "assessment_type"):
            value = hint.get(key)
            if value not in (None, "", [], {}):
                compact_hint[key] = value
        compacted.append(
            {
                "label": str(action.get("label") or "").strip(),
                "kind": kind,
                "hint": compact_hint,
            }
        )
    return compacted


def _normalize_last_search(runtime_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if (runtime_context or {}).get("last_search") is not None:
        return dict((runtime_context or {}).get("last_search") or {})
    if (runtime_context or {}).get("last_search_summary") is not None:
        return dict((runtime_context or {}).get("last_search_summary") or {})
    return None


def _normalize_memory_summary(
    runtime_context: dict[str, Any] | None,
    recent_timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    memory_summary = dict((runtime_context or {}).get("memory_summary") or {})
    if memory_summary:
        return {
            "stable_preferences_summary": str(memory_summary.get("stable_preferences_summary") or "").strip() or None,
            "recent_feedback_summary": str(memory_summary.get("recent_feedback_summary") or "").strip() or None,
            "recent_conversation_summary": str(memory_summary.get("recent_conversation_summary") or "").strip() or None,
        }

    compacted_timeline = _compact_timeline(list((runtime_context or {}).get("recent_timeline_summary") or recent_timeline))
    recent_conversation_summary = ""
    latest_user = next(
        (item for item in reversed(compacted_timeline) if str(item.get("item_type") or "") == "user_message"),
        None,
    )
    if latest_user is not None:
        recent_conversation_summary = str(latest_user.get("body") or "").strip()
    return {
        "stable_preferences_summary": None,
        "recent_feedback_summary": None,
        "recent_conversation_summary": recent_conversation_summary or None,
    }


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
    candidate = _select_explained_candidate(
        {"result_cards": _normalize_current_results(run_input.runtime_context)},
        user_message,
    )
    if not candidate:
        return None

    requester_profile = _normalize_user_profile(run_input.runtime_context)
    self_traits = dict(requester_profile.get("personality_traits") or {})
    candidate_traits = _compact_candidate_personality_context(
        candidate.get("personality_signals") or candidate.get("personality_match_context")
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


def _prompt_needs_assessment_mode(user_message: str | None, action_context: dict[str, Any] | None) -> bool:
    if action_context is not None:
        hint = dict((action_context or {}).get("semantic_payload") or {})
        if str(hint.get("kind") or "").strip() == "start_assessment":
            return True
    text = str(user_message or "").strip()
    if not text:
        return False
    keywords = ("MBTI", "依恋", "价值观", "性格", "合拍", "测评", "不知道", "没测过", "不清楚")
    return any(keyword in text for keyword in keywords)


def _prompt_needs_rejection_feedback_mode(user_message: str | None, action_context: dict[str, Any] | None) -> bool:
    hint = dict((action_context or {}).get("semantic_payload") or {})
    action_kind = str(hint.get("kind") or "").strip()
    # 场景1: 用户点击反馈选项（处理反馈）
    if action_kind == "rejection_feedback":
        return True
    # 场景2: 用户点击"换一批"按钮（触发追问）
    if action_kind == "show_more_candidates":
        return True
    # 场景3: 用户主动说"换一批"
    text = str(user_message or "").strip()
    return any(marker in text for marker in _DISCOVERY_BATCH_REFRESH_PATTERNS)


def _build_discovery_agent_instructions(
    *,
    event: str,
    user_message: str | None,
    action_context: dict[str, Any] | None,
) -> str:
    del event
    sections = [
        """
你是发现页里的 AI 红娘。

核心原则：
- 以 state 为当前产品状态真相，不要靠记忆猜页面状态。
- 当用户说"给我推荐"、"找对象"、"看看合适的"时，优先直接调用 search_partner_candidates，不要回复"我先把你的偏好整理一下"。
- 如果条件还不够，只问 1 个最关键的问题；如果条件已经够用，就直接搜索。
- 只有用户说出了明确、稳定、适合落库的新信息时，才调用画像写回工具。
- 改用户本人正式资料时，用 `propose_requester_profile_update`；择偶偏好用 `sync_requester_persona_memory`。
- 不能编造候选人的原始卡片字段。你只能输出 profile_id 和 reason_summary。
- 如果 state.current_results 已有候选人，且用户是在追问“为什么推荐她/他”“从测评怎么看”“MBTI/依恋/价值观为什么合拍”，优先基于 state.current_results 解释，不要重复搜索。

state 常见信息：
- session：当前会话 phase、criteria_labels 等权威状态
- user_profile：用户当前画像快照
- current_results：当前页面上的候选人摘要
- visible_actions：当前页面还能点哪些 action
- last_search：最近一轮搜索摘要

memory_summary 常见信息：
- stable_preferences_summary：长期稳定偏好摘要
- recent_feedback_summary：最近几轮“换一批/不合适”的摘要
- recent_conversation_summary：最近对话进展摘要

说明：
- state.current_results 里的 personality_signals 是已经压缩过的测评信号；用户追问“为什么推荐”时，直接用它解释。

工具调用要求：
- 需要用工具时，必须走系统提供的真实 tool calling 机制。
- 不要把 `tool_calls`、`function_call`、工具参数对象手写进最终 JSON。
- 不要输出形如 `{“tool_calls”:[...]}` 的文本。

工具调用要求：
- 当用户说”找对象”、”推荐几个”、”给我看看”时，调用 search_partner_candidates 工具搜索。
- 每次回复用户后，必须调用 make_decision 工具输出你的决策。
- make_decision 工具参数说明：
  - phase: 当前阶段（collecting_preferences/searching/results_shown/no_result）
  - assistant_message: 回复用户的消息（必填，保持短）
  - criteria_labels_json: 筛选条件标签 JSON 数组字符串，如 [“苏州”, “26-30岁”]
  - suggested_actions_json: 建议操作按钮 JSON 数组字符串，格式：[{“label”:”换一批”,”style”:”secondary”,”semantic_payload”:{“kind”:”show_more_candidates”}}]
  - selected_candidates_json: 候选人 JSON 数组字符串，格式：[{“profile_id”:100,”reason_summary”:”价值观匹配”}]
- 所有 JSON 参数必须是有效的 JSON 字符串格式，不要直接写数组对象。

输出原则：
- assistant_message 保持短，像真人红娘，不要写成系统说明。
- phase 只能是：collecting_preferences、searching、results_shown、no_result。
- 如果你正在展示候选卡片，phase 必须是 `results_shown`。
- suggested_actions 最多 3 个，style 只能是 primary/secondary/ghost。
- semantic_payload.kind 只用这些值：
  - starter_prompt：首次对话引导
  - followup_prompt：追问补充信息
  - saved_search_opt_in：持续留意（无结果时推荐）
  - show_more_candidates：换一批（会触发追问反馈）
  - add_criteria：添加筛选条件
  - refine_preferences：调整偏好
  - age_preference：年龄偏好设置
  - start_assessment：推荐测评
  - rejection_feedback：拒绝反馈选项
- **"换一批"按钮必须使用 show_more_candidates**，这会触发系统追问上一批哪里不合适。
- **注意**：refine_candidates 已废弃，不要使用。如有旧数据中使用，可忽略但不应创建新的。
- 只有在你真的调用了搜索工具并且决定展示结果时，才填写 selected_candidates。
- selected_candidates 里的 profile_id 必须来自最新一次搜索工具返回的 results。
- 如果搜索工具返回 `error_code` 或 `diagnostics.error`，不要说”本地没有符合条件的人”。要自然说明这轮搜索失败了，不代表没人，并引导用户重试或继续补充条件。
- 如果 state.current_results 已有候选人，且你在解释当前候选人的测评适配性，assistant_message 直接解释；如果引用了当前候选人，请把该候选人继续放进 selected_candidates，这样前端能保留同一组卡片。
- reason_summary 应尽量写成用户能看懂的匹配理由，优先引用双方的 MBTI、依恋风格、价值观；如果候选人没测评，再用”从资料看””可能”等谨慎表达。
"""
    ]
    if _prompt_needs_assessment_mode(user_message, action_context):
        sections.append(
            """
测评推荐规则：
- 当你主动询问了用户的测评类型（MBTI、依恋风格），而用户回复"不知道"、"没测过"、"不清楚"时，优先返回测评测试按钮，不要转去问年龄、城市等偏好问题。
- 询问要自然，像聊天一样，不要像问卷。
- 推荐 MBTI 时，按钮用 {"kind":"start_assessment","assessment_type":"mbti"}。
- 推荐依恋风格时，按钮用 {"kind":"start_assessment","assessment_type":"attachment"}。
- 如果 memory_summary.recent_conversation_summary 已明确提到 MBTI 结果，或者 state.current_results 已经足够解释当前问题，不要重复推荐测评。
"""
        )
    if _prompt_needs_rejection_feedback_mode(user_message, action_context):
        sections.append(
            """
换一批反馈闭环：
- 当用户说"换一批"、"重新找"、"再看几位"、"再给我看看"时，系统会自动追问上一批哪里不合适。
- **展示候选人后，"换一批"按钮必须使用 semantic_payload.kind = "show_more_candidates"**。
- 反馈选项必须使用 semantic_payload.kind = "rejection_feedback"，并带 feedback_type。
- 用户点击 rejection_feedback 后，必须：
  1. 调用 submit_rejection_feedback
  2. 调用 search_partner_candidates
  3. 返回 selected_candidates
  4. assistant_message 说明你调整了什么
- 常见 feedback_type：location_distance、age_gap、criteria_age、occupation_mismatch、work_life_balance、interest_mismatch、personality_mismatch、criteria_generic、skip_feedback。
- 如果用户选择 saved_search_opt_in，则优先调用 create_saved_search_subscription_from_last_search。
- **重要**：不要使用已废弃的 refine_candidates，统一使用 show_more_candidates 以符合业务规则"每次换一批都追问"。
"""
        )
    return "\n\n".join(section.strip() for section in sections if section.strip())


def _build_runtime_prompt(
    *,
    run_input: DiscoveryRunInput,
    event: str,
    user_message: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> str:
    runtime_context = dict(run_input.runtime_context or {})
    user_profile = _normalize_user_profile(runtime_context)
    state = {
        "session": _normalize_session_state(run_input, runtime_context),
        "user_profile": user_profile,
        "current_results": _normalize_current_results(runtime_context),
        "visible_actions": _compact_visible_actions(list(runtime_context.get("visible_actions") or [])),
        "last_search": _normalize_last_search(runtime_context),
    }
    memory_summary = _normalize_memory_summary(runtime_context, run_input.recent_timeline)

    payload = {
        "event": {
            "type": event,
            "user_message": str(user_message or "").strip() or None,
            "clicked_action": {
                "label": str((action_context or {}).get("label") or "").strip() or None,
                "kind": str(dict((action_context or {}).get("semantic_payload") or {}).get("kind") or "").strip() or None,
                "hint": dict((action_context or {}).get("semantic_payload") or {}),
            }
            if action_context
            else None,
        },
        "state": state,
        "memory_summary": memory_summary,
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
                            semantic_payload={"kind": "show_more_candidates"},
                            style="ghost",
                        ),
                        DiscoveryActionSuggestion(
                            label="调整条件",
                            semantic_payload={"kind": "add_criteria"},
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
            """同步用户的择偶偏好到长期记忆。当用户说出明确的择偶偏好时调用此工具。"""
            patch = json.loads(str(patch_json or "{}"))
            if not isinstance(patch, dict):
                raise ValueError("patch_json must decode into a JSON object")
            return run_input.sync_requester_persona_memory(patch)

        @function_tool
        def propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
            """提议更新用户本人的正式资料（年龄、城市、婚姻状态等）。当用户说出个人资料变更时调用此工具。"""
            return run_input.propose_requester_profile_update(patch_json, evidence_text)

        @function_tool
        def search_partner_candidates(criteria_json: str, limit: int = 5) -> dict[str, Any]:
            """搜索候选人。当用户说"找对象"、"推荐几个"、"给我看看"时调用此工具。返回匹配的候选人列表。"""
            criteria = json.loads(str(criteria_json or "{}"))
            if not isinstance(criteria, dict):
                raise ValueError("criteria_json must decode into a JSON object")
            normalized_limit = max(1, min(int(limit or 5), 10))
            response = run_input.search_partner_candidates(criteria, normalized_limit)
            tool_state["last_search_response"] = response
            return _summarize_search_response_for_model(response)

        @function_tool
        def create_saved_search_subscription_from_last_search() -> dict[str, Any]:
            """创建订阅，按当前搜索条件持续留意新候选人。当用户想"持续留意"或"订阅"时调用此工具。"""
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

        # ====================================================================
        # 方案C：make_decision 工具 - 把 Decision Schema 融进工具参数
        # ====================================================================
        tool_state["decision_payload"] = None  # 存储 make_decision 工具参数

        @function_tool
        def make_decision(
            phase: str,
            assistant_message: str,
            criteria_labels_json: str = "[]",
            suggested_actions_json: str = "[]",
            result_group_title: str = "",
            selected_candidates_json: str = "[]",
        ) -> dict[str, Any]:
            """
            输出决策结果。每次回复用户后，必须调用此工具来输出你的决策。

            参数说明：
            - phase: 当前阶段（collecting_preferences/searching/results_shown/no_result）
            - assistant_message: 回复用户的消息（必填）
            - criteria_labels_json: 筛选条件标签 JSON 数组，如 ["苏州", "26-30岁"]
            - suggested_actions_json: 建议操作按钮 JSON 数组，每个包含 label/style/semantic_payload
            - result_group_title: 候选人分组标题（可选）
            - selected_candidates_json: 候选人 JSON 数组，每个包含 profile_id 和 reason_summary

            JSON 格式示例：
            suggested_actions_json: [{"label":"换一批","style":"secondary","semantic_payload":{"kind":"show_more_candidates"}}]
            selected_candidates_json: [{"profile_id":100,"reason_summary":"价值观匹配"}]

            重要：
            - 只有在搜索成功后才填写 selected_candidates
            - suggested_actions 最多3个，style 只能是 primary/secondary/ghost
            """
            payload = {
                "phase": phase,
                "assistant_message": assistant_message,
                "criteria_labels": json.loads(criteria_labels_json) if criteria_labels_json else [],
                "suggested_actions": json.loads(suggested_actions_json) if suggested_actions_json else [],
                "result_group_title": result_group_title if result_group_title else None,
                "selected_candidates": json.loads(selected_candidates_json) if selected_candidates_json else [],
            }
            tool_state["decision_payload"] = payload  # 存储供后续提取
            return {"success": True, "phase": phase}

        instructions = _build_discovery_agent_instructions(
            event=event,
            user_message=user_message,
            action_context=action_context,
        )

        # 方案C：移除 output_schema，只用 tools
        tools = [
            sync_requester_persona_memory,
            propose_requester_profile_update,
            search_partner_candidates,
            create_saved_search_subscription_from_last_search,
            submit_rejection_feedback,
            get_feedback_options,
            make_decision,  # 方案C新增
        ]
        runtime_input = _build_runtime_prompt(
            run_input=run_input,
            event=event,
            user_message=user_message,
            action_context=action_context,
        )
        _log_discovery_context_size(
            event=event,
            instructions=instructions.strip(),
            runtime_input=runtime_input,
            output_schema=None,  # 方案C：无 output_schema
            tools=tools,
        )
        if run_input.agent_session is not None:
            _logger.debug(
                "discovery agent session memory bypassed for prompt-size control session_id=%s",
                run_input.session_id,
            )

        agent = Agent(
            name="discovery_matchmaker",
            instructions=instructions.strip(),
            model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
            output_type=None,  # 方案C：移除 output_schema
            tools=tools,
        )
        started = time.perf_counter()
        result, first_token_latency_ms = asyncio.run(
            self._run_streamed_agent(
                Runner=Runner,
                agent=agent,
                runtime_input=runtime_input,
                started=started,
            )
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        usage_payload = _usage_debug_payload(result)
        _logger.debug(
            "discovery agent run metrics event=%s elapsed_ms=%s response_id=%s input_tokens=%s output_tokens=%s total_tokens=%s requests=%s first_token_latency_ms=%s",
            event,
            elapsed_ms,
            getattr(result, "last_response_id", None),
            usage_payload["input_tokens"],
            usage_payload["output_tokens"],
            usage_payload["total_tokens"],
            usage_payload["requests"],
            first_token_latency_ms,
        )

        # ====================================================================
        # 方案C：从 make_decision 工具参数中提取 decision
        # ====================================================================
        decision_payload = tool_state.get("decision_payload")
        if decision_payload is not None:
            _logger.debug(
                "discovery agent extracted decision from make_decision tool payload=%s",
                str(decision_payload)[:200]
            )
            decision = _decision_payload_to_decision(DecisionPayloadModel.model_validate(decision_payload))
        else:
            # Fallback：尝试从 final_output 恢复
            final_output = getattr(result, "final_output", result)
            _logger.warning(
                "discovery agent make_decision tool not called, falling back to final_output type=%s",
                type(final_output).__name__,
            )
            recovered = _recover_decision_from_exception(final_output) if isinstance(final_output, Exception) else None
            if recovered is not None:
                decision = recovered
            else:
                # 最终 fallback：使用 stub
                _logger.warning("discovery agent fell back to stub after no decision payload")
                return self._fallback_result(
                    run_input,
                    user_message=user_message,
                    action_context=action_context,
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

    async def _run_streamed_agent(
        self,
        *,
        Runner: Any,
        agent: Any,
        runtime_input: str,
        started: float,
    ) -> tuple[Any, float | None]:
        streamed_result = Runner.run_streamed(
            agent,
            input=runtime_input,
        )
        first_token_latency_ms: float | None = None
        async for stream_event in streamed_result.stream_events():
            if first_token_latency_ms is None and _is_first_token_stream_event(stream_event):
                first_token_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        run_loop_task = getattr(streamed_result, "run_loop_task", None)
        if run_loop_task is not None:
            await run_loop_task
        return streamed_result, first_token_latency_ms


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
