"""Agents SDK-backed runtime for the discovery page."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urljoin, urlparse

import httpx  # ✅ 新增：用于配置精细的timeout

_logger = logging.getLogger(__name__)

from her_env import env_first, env_float, env_int  # ✅ 新增：导入env_int用于max_retries
from match_domain import PhotoPreferenceIntent
from match_domain.photo_intent_agent import build_visual_search_plan as _build_visual_search_plan_impl
from match_domain.visual_capabilities import retrieve_visual_candidates
from profile_service import list_profiles, resolve_profile_source
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
    decision_payload_to_decision_with_repair as _decision_payload_to_decision_with_repair,  # 带修复逻辑
)


@dataclass(frozen=True)
class DiscoveryRunInput:
    session_id: str
    requester_id: int
    profile_id: int
    phase: str
    criteria_labels: list[str]
    recent_timeline: list[dict[str, Any]]
    runtime_context: dict[str, Any]
    search_partner_candidates: Callable[..., dict[str, Any]]
    sync_requester_persona_memory: Callable[[dict[str, Any]], dict[str, Any]]
    # propose_requester_profile_update: Callable[[str, str], dict[str, Any]]  # 已注释：暂时禁用此工具
    create_saved_search_subscription_from_last_search: Callable[[], dict[str, Any]]
    suggest_assessment: Callable[[str], dict[str, Any]]  # Agent必须传入测评类型
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
_IMAGE_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_META_IMAGE_RE = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image|og:image:url)["'][^>]+content=["']([^"']+)["']""",
    re.IGNORECASE,
)
_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)


def _looks_like_placeholder_secret(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    return normalized.startswith("replace-with-") or normalized in {
        "your-api-key",
        "test-key",
        "dummy-key",
    }


def _env_first_non_placeholder(*keys: str) -> str:
    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value and not _looks_like_placeholder_secret(value):
            return value
    return ""


def _convert_sets_to_lists(data: dict[str, Any]) -> dict[str, Any]:
    """递归转换字典中的所有set为list（JSON可序列化）

    ✅ P0修复：解决"Object of type set is not JSON serializable"错误
    根因：service_integrations.py中的exclude_ids等字段可能使用set对象
    解决：在返回给Agents SDK前，统一转换为list

    Args:
        data: 可能包含set对象的字典

    Returns:
        所有set已转换为list的字典
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, set):
            # ✅ 核心修复：set → list
            result[key] = list(value)
        elif isinstance(value, dict):
            # 递归处理嵌套字典
            result[key] = _convert_sets_to_lists(dict(value))
        elif isinstance(value, (list, tuple)):
            # 处理列表/元组中的嵌套字典
            converted_list: list[Any] = []
            for item in value:
                if isinstance(item, dict):
                    converted_list.append(_convert_sets_to_lists(dict(item)))
                elif isinstance(item, set):
                    converted_list.append(list(item))
                else:
                    converted_list.append(item)
            result[key] = converted_list
        else:
            result[key] = value
    return result


def _looks_like_image_url(url: str) -> bool:
    normalized = str(url or "").strip().lower()
    if not normalized.startswith(("http://", "https://")):
        return False
    path = urlparse(normalized).path
    return path.endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic")
    )


def _extract_direct_image_urls_from_html(page_url: str, html_text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw_url: str) -> None:
        cleaned = html.unescape(str(raw_url or "").strip())
        if not cleaned:
            return
        absolute = urljoin(page_url, cleaned)
        if not _looks_like_image_url(absolute):
            return
        if absolute in seen:
            return
        seen.add(absolute)
        candidates.append(absolute)

    for match in _META_IMAGE_RE.findall(html_text):
        _add(match)
    for match in _IMG_SRC_RE.findall(html_text):
        _add(match)
    for match in _IMAGE_URL_RE.findall(html_text):
        _add(match)
    return candidates


def _safe_json_length(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _candidate_summary_for_model(candidate: dict[str, Any]) -> str:
    profile = dict(candidate.get("profile") or {})
    candidate_context = dict(candidate.get("candidate_context") or {})
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
    evidence_level = str(candidate_context.get("evidence_level") or "").strip()
    if evidence_level:
        parts.append(f"证据等级:{evidence_level}")
    return "，".join(part for part in parts if part)


def _summarize_search_response_for_model(search_response: dict[str, Any]) -> dict[str, Any]:
    # ✅ 防线3：入口处统一转换（兜底）
    # 即使前面有遗漏的set字段，这里也能兜底处理
    response = _convert_sets_to_lists(dict(search_response or {}))

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
            # ✅ P0修复：确保criteria中所有set字段转换为list（JSON可序列化）
            criteria = _convert_sets_to_lists(dict(criteria))
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
        candidate_context = dict(candidate.get("candidate_context") or {})
        if candidate_context:
            # ✅ P0修复：确保missing_dimensions等set字段转换为list
            missing_dims = candidate_context.get("missing_dimensions")
            if isinstance(missing_dims, set):
                missing_dims = list(missing_dims)
            item["candidate_context"] = {
                "evidence_level": candidate_context.get("evidence_level"),
                "reason_mode": candidate_context.get("reason_mode"),
                "missing_dimensions": list(missing_dims or []),  # 确保是list
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
    return _env_first_non_placeholder(
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
        # 仅在存在真实可用 key 时才推断百炼端点，避免把 .env.example 占位符当成真配置。
        if _env_first_non_placeholder(
            "DASHSCOPE_API_KEY",
            "HER_DISCOVERY_AGENT_API_KEY",
            "OPENAI_API_KEY",
        ):
            _logger.info("✅ 自动推断使用百炼API URL（基于API key存在）")
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


# 兼容保留：仅供旧测试/脚本调用，不再参与正式运行链路。
_AGENTS_SDK_ASYNC_CLIENT: Any | None = None


def _build_agents_sdk_client() -> tuple[Any | None, str]:
    """为单次 Agent 运行创建客户端配置。

    关键点：不要把 AsyncOpenAI 跨多个 asyncio.run() 复用。
    否则底层 httpx/httpcore 连接会绑定到已关闭的 event loop，触发
    "RuntimeError: Event loop is closed"。
    """
    from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
    from her_production import assert_production_discovery_agent_isolation
    from openai import AsyncOpenAI

    # ✅ P0修复：强制禁用Tracing，避免向OpenAI发送trace请求超时
    # 根因：Tracing硬编码发送到 https://api.openai.com/v1/traces/ingest
    # 但我们使用百炼API（阿里云），无法连接到OpenAI，导致超时失败
    # 解决：在任何初始化之前立即禁用Tracing
    set_tracing_disabled(True)
    _logger.info("✅ Tracing已强制禁用（避免OpenAI连接超时）")

    assert_production_discovery_agent_isolation()
    wire_api = _resolve_discovery_wire_api()
    base_url = _resolve_discovery_base_url(wire_api=wire_api)

    if base_url:
        api_key = _resolve_discovery_api_key()

        # ✅ P0修复：配置精细的timeout，解决百炼API连接超时问题
        # 根因：默认connect timeout只有5秒，百炼API响应慢，5秒内无法建立连接就重试
        # 解决：增加connect timeout到30秒，总timeout保持120秒
        timeout_config = httpx.Timeout(
            timeout=env_float(
                "HER_DISCOVERY_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_ASSISTANT_TIMEOUT_SECONDS",
                default=120.0,  # 总timeout：120秒（LLM推理可能需要较长时间）
            ),
            connect=env_float(
                "HER_DISCOVERY_AGENT_CONNECT_TIMEOUT_SECONDS",
                "HER_CHAT_AGENT_CONNECT_TIMEOUT_SECONDS",
                "HER_CHAT_ASSISTANT_CONNECT_TIMEOUT_SECONDS",
                default=30.0,  # ✅ 连接timeout：30秒（允许更长的连接建立时间）
            ),
        )
        _logger.info(f"✅ LLM API timeout配置: 读取timeout={timeout_config.read}秒, 连接timeout={timeout_config.connect}秒, 写入timeout={timeout_config.write}秒, 连接池timeout={timeout_config.pool}秒")

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_config,  # ✅ 使用精细配置的timeout
            max_retries=int(env_float(  # ✅ 修正：使用env_float然后转换为int（env_int不支持多个环境变量名称）
                "HER_DISCOVERY_AGENT_MAX_RETRIES",
                default=3.0,  # 默认重试3次（增加容错能力）
            )),
        )
        _logger.info("Agents SDK AsyncOpenAI 客户端已创建（单次运行作用域）")
        set_default_openai_client(client, use_for_tracing=False)
        # This only selects the Agents SDK wire API (`/responses` vs `/chat/completions`);
        # it is not a remote provider request parameter.
        set_default_openai_api(wire_api)
        # ✅ Tracing已在函数开头强制禁用，无需再次调用
        return client, wire_api

    # This only selects the Agents SDK wire API (`/responses` vs `/chat/completions`);
    # it is not a remote provider request parameter.
    set_default_openai_api(wire_api)
    return None, wire_api


def _configure_agents_sdk_provider() -> None:
    """兼容旧入口：配置一次默认 provider/client。

    正式运行链路已改为每次 Agent 运行单独创建并关闭客户端，
    这里只为保留旧测试与脚本入口，避免 import/调用直接失效。
    """
    global _AGENTS_SDK_ASYNC_CLIENT

    if _AGENTS_SDK_ASYNC_CLIENT is not None:
        return

    client, _ = _build_agents_sdk_client()
    _AGENTS_SDK_ASYNC_CLIENT = client


async def cleanup_agents_sdk_client() -> None:
    """清理兼容模式下缓存的客户端。

    历史实现依赖全局 AsyncOpenAI 单例，容易在 asyncio.run() 结束后触发
    "Event loop is closed"。现在正式运行链路已改为单次 Agent 运行内创建并关闭。
    """
    global _AGENTS_SDK_ASYNC_CLIENT

    if _AGENTS_SDK_ASYNC_CLIENT is None:
        return None

    await _AGENTS_SDK_ASYNC_CLIENT.close()
    _AGENTS_SDK_ASYNC_CLIENT = None
    return None


def _compact_requester_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = dict(profile or {})
    keep_keys = [
        # profiles 表中的硬条件字段
        "gender",
        "age",
        "city",
        "marital_status",
        "has_children",
        "relationship_goal",
        "job",  # 使用 profiles.job，不是 self_job
        # persona 表中的软偏好字段
        "target_gender",
        "target_age_min",
        "target_age_max",
        "target_cities",
        "preferred_traits",
        # 硬条件字段已删除：self_job, self_city, self_relationship_goal
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
    """
    压缩当前候选人列表，传递给 Agent。

    ✅ Agent Native：传递所有候选人给 Agent，不要截断。
    否则 Agent 无法识别用户询问的候选人（如"介绍一下李欣琪"），
    会说"没有这个候选人"导致用户体验差。
    """
    compacted_cards: list[dict[str, Any]] = []
    for card in list(results or []):  # 不再截断 [:3]，传递所有候选人
        candidate_context = dict(card.get("candidate_context") or {})
        summary = dict(card.get("summary") or {})
        compact_summary = {
            key: str(summary.get(key) or "").strip()
            for key in ("personality_traits", "values", "emotional_needs", "life_attitude")
            if str(summary.get(key) or "").strip()
        }
        compacted_cards.append(
            {
                "profile_id": card.get("profile_id"),
                "title": card.get("title"),
                "subtitle": card.get("subtitle"),  # 包含城市·职业·学历，供 Agent 介绍候选人时使用
                "reason_summary": card.get("reason_summary"),
                "compatibility_summary": card.get("compatibility_summary"),
                "personality_signals": _compact_candidate_personality_context(
                    card.get("personality_signals") or card.get("personality_match_context")
                ),
                "candidate_context": {
                    "evidence_level": candidate_context.get("evidence_level"),
                    "reason_mode": candidate_context.get("reason_mode"),
                    "missing_dimensions": list(candidate_context.get("missing_dimensions") or []),
                }
                if candidate_context
                else None,
                "summary": compact_summary or None,
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


def _normalize_visual_context(runtime_context: dict[str, Any] | None) -> dict[str, Any] | None:
    visual_context = (runtime_context or {}).get("visual_memory")
    if visual_context is None:
        visual_context = (runtime_context or {}).get("visual_context")
    if visual_context is None:
        return None
    compact = dict(visual_context or {})
    if "active_reference" in compact or "active_preference" in compact or "last_result" in compact:
        active_preference = dict(compact.get("active_preference") or {})
        last_result = dict(compact.get("last_result") or {})
        return {
            "has_reference_image": bool(dict(compact.get("active_reference") or {}).get("source")),
            "active_visual_intent": {
                "mode": active_preference.get("legacy_mode"),
                "intent_type": active_preference.get("intent_type"),
                "query_text": active_preference.get("query_text"),
                "celebrity_name": active_preference.get("reference_person"),
            },
            "active_constraints": dict(compact.get("active_constraints") or {}),
            "last_query_text": str(last_result.get("query_text") or "").strip() or None,
            "last_result_profile_ids": list(last_result.get("profile_ids") or []),
        }
    return {
        "has_reference_image": bool(compact.get("has_reference_image")),
        "active_visual_intent": dict(compact.get("active_visual_intent") or {}),
        "active_constraints": dict(compact.get("active_constraints") or {}),
        "last_query_text": str(compact.get("last_query_text") or "").strip() or None,
        "last_result_profile_ids": list(compact.get("last_result_profile_ids") or []),
    }


def _normalize_visual_memory(runtime_context: dict[str, Any] | None) -> dict[str, Any] | None:
    visual_memory = (runtime_context or {}).get("visual_memory")
    if visual_memory is None:
        return None
    compact = dict(visual_memory or {})
    return {
        "has_reference_image": bool(dict(compact.get("active_reference") or {}).get("source")),
        "active_reference": dict(compact.get("active_reference") or {}),
        "active_preference": dict(compact.get("active_preference") or {}),
        "active_constraints": dict(compact.get("active_constraints") or {}),
        "refinement_history": list(compact.get("refinement_history") or []),
        "last_result": dict(compact.get("last_result") or {}),
    }


def _normalize_memory_summary(
    runtime_context: dict[str, Any] | None,
    recent_timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    构建长期记忆摘要。

    Agent session 会自动记住当前会话的对话历史，
    所以这里只提取长期记忆（偏好、反馈），不提取对话内容。
    """
    memory_summary = dict((runtime_context or {}).get("memory_summary") or {})
    if memory_summary:
        return {
            "stable_preferences_summary": str(memory_summary.get("stable_preferences_summary") or "").strip() or None,
            "recent_feedback_summary": str(memory_summary.get("recent_feedback_summary") or "").strip() or None,
            # 移除 recent_conversation_summary - Agent session 会自动记住对话历史
        }

    # 无 memory_summary 时，返回空值
    return {
        "stable_preferences_summary": None,
        "recent_feedback_summary": None,
        # 移除 recent_conversation_summary - Agent session 会自动记住对话历史
    }


# ✅ Agent Native：完全移除硬编码关键词判断
# _looks_like_personality_explanation_request 方法已删除
# Agent 自主判断是否需要性格解释
#
# _select_explained_candidate 方法已删除
# Agent 自主识别用户想了解哪个候选人
#
# 参考：Agent Native 开发实践规范 - 反模式：触发词映射表


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
        return f"价值观上你们都把'{shared}'放得比较前，这类人通常更容易在长期投入和生活方向上同频。"
    self_type = str((self_values or {}).get("value_type") or "").strip()
    candidate_type = str((candidate_values or {}).get("value_type") or "").strip()
    if self_type and candidate_type:
        return f"价值观上你偏{self_type}，她偏{candidate_type}，虽然不完全一样，但都不是只看短期新鲜感的类型。"
    return None


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
                        for card in list(item.get("cards") or [])  # 不再截断 [:3]
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


def _build_discovery_agent_instructions(
    *,
    event: str,
    user_message: str | None,
    action_context: dict[str, Any] | None,
) -> str:
    """构建 Agent 指令。

    ✅ Agent Native：单一真相来源原则
    - SOUL.md：角色定义 + 核心原则（唯一来源）
    - 工具 description：能力描述 + 使用场景（唯一来源）
    - 运行时上下文：通过工具参数传递，不在 Prompt 中重复
    """

    # 加载 SOUL.md 内容
    soul_md_path = os.path.join(os.path.dirname(__file__), "DISCOVERY_AGENT_SOUL.md")
    soul_content = ""
    try:
        with open(soul_md_path, "r", encoding="utf-8") as f:
            soul_content = f.read().strip()
    except Exception as e:
        _logger.warning(f"Failed to load SOUL.md: {e}")

    # 简短事件说明（其余上下文通过工具参数传递）
    event_context = f"当前事件：{event}"
    if user_message:
        event_context += f"，用户说：{user_message}"
    if action_context:
        event_context += f"，点击按钮：{action_context.get('label')}"

    # 合并：SOUL.md（角色定义） + 简短事件说明
    if soul_content:
        return f"{soul_content}\n\n{event_context}"
    return event_context
    return runtime_context_instructions


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
        "visual_context": _normalize_visual_context(runtime_context),
        "visual_memory": _normalize_visual_memory(runtime_context),
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


class AgentsSdkDiscoveryAgentRuntime:
    def __init__(self) -> None:
        # ✅ 删除兜底方案：不再使用fallback，让真实问题暴露出来
        pass

    def initial_decision(self, run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult:
        return self._run_with_agents_sdk(
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
        # ✅ 删除兜底方案：直接调用_run_with_agents_sdk
        return self._run_with_agents_sdk(
            run_input,
            event="action_click" if action_context is not None else "user_message",
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
            from agents import Agent, AgentOutputSchema, Runner, WebSearchTool, function_tool
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Missing Agents SDK dependency. Install `openai-agents`.") from exc

        async_client, _ = _build_agents_sdk_client()
        tool_state: dict[str, Any] = {"last_search_response": None}

        @function_tool
        def sync_requester_persona_memory(patch_json: str) -> dict[str, Any]:
            """同步用户的择偶偏好到长期记忆。当用户说出明确、稳定、适合落库的择偶偏好时调用。沉淀长期偏好，后续推荐更精准。"""
            patch = json.loads(str(patch_json or "{}"))
            if not isinstance(patch, dict):
                raise ValueError("patch_json must decode into a JSON object")
            return run_input.sync_requester_persona_memory(patch)

        # @function_tool
        # def propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
        #     """提议更新用户本人的正式资料（年龄、城市、婚姻状态等）。当用户说出个人资料变更时调用。需要用户确认后生效。"""
        #     return run_input.propose_requester_profile_update(patch_json, evidence_text)

        @function_tool
        def search_partner_candidates(
            criteria_json: str,
            personality_match_json: str = "",
            limit: int = 5,
            exclude_current_results: bool = False,
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 新增参数：外貌筛选（抽象化参数，Agent易用）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            appearance_level: str = "medium",  # "high"/"medium"/"low"
            appearance_description: str = "",  # 自然语言描述
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 新增参数：明星脸搜索（Agent自己用WebSearch/WebFetch获取照片URL）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            photo_url: str = "",
        ) -> dict[str, Any]:
            """搜索候选人。当用户想看推荐、调整搜索条件、表达不满后重新搜索时调用。

            这是"重新搜人"的唯一工具。是否排除当前已展示候选人，必须由你显式决定并通过参数传入，
            不要假设系统会自动理解"换一批"。

            支持的筛选条件（硬约束，数据库筛选）：
            - gender: 性别（male/female）
            - age_min/age_max: 年龄范围
            - cities: 城市列表
            - relationship_goals: 关系目标

            性格匹配（向量搜索，可选）：
            - personality_match_json: 性格特质匹配条件
              示例：{"match_traits": ["外向", "温柔"], "similarity_threshold": 0.75}
              - match_traits: 想要匹配的性格特质列表
              - similarity_threshold: 相似度阈值（0.0-1.0，默认0.75）
              - Agent可根据对话上下文自主调整阈值（高要求用0.8，宽松用0.6）

            【新增】外貌筛选（抽象化参数，Agent易用）：
            - appearance_level: 外貌筛选级别（抽象化，不暴露内部评分机制）
              - "high": 系统自动设置高标准筛选（Agent不知道具体阈值）
              - "medium": 默认值，不强制筛选
              - "low": 不筛选外貌
              - Agent只需传入"high"/"medium"/"low"，不需要知道内部实现

            - appearance_description: 外貌描述（自然语言）
              - 示例："温柔气质"、"清秀型"、"阳光开朗"
              - Agent用自然语言描述即可，不需要理解内部评分机制
              - 系统内部会自动解析并应用合适的筛选条件

            【新增】明星脸搜索（Agent自己获取照片URL + Agent自己判断相似度）：
            - photo_url: 参考照片URL（Agent用WebSearch + resolve_direct_image_urls 获取）
              - 完整流程（Agent必须遵循）：
                Step 1：Agent用WebSearch搜"田曦薇照片"
                Step 2：Agent调用 resolve_direct_image_urls，从页面提取直接图片URL
                Step 3：Agent调用本工具，传入photo_url
                Step 4：工具返回候选人列表（包含照片URL）
                Step 5：Agent用Vision能力看候选人照片 ✅
                Step 6：Agent判断"长得像不像"（相似度评分0-100）✅
                Step 7：Agent筛选出真正像的候选人（≥80分）✅
                Step 8：Agent返回结果给用户

            【重要】Agent判断相似度的方法：
            - Agent用Vision能力同时看两张照片（明星照片 + 候选人照片）
            - Agent从以下维度判断：
              1. 整体气质相似度（甜美、温柔、成熟等）
              2. 五官相似度（眼睛、鼻子、嘴巴、脸型）
              3. 风格相似度（元气、知性、利落等）
            - Agent给出相似度评分（0-100分）和匹配理由
            - Agent只返回相似度≥80分的候选人

            使用场景：
            ┌─────────────────────────┬──────────────────────────┬─────────────────────┐
            │ 用户说                  │ Agent应该传的参数        │ 检索方式            │
            ├─────────────────────────┼──────────────────────────┼─────────────────────┤
            │ “找长得漂亮的”          │ appearance_level=”high”  │ 系统自动高标准筛选  │
            │ “找清秀型的”            │ appearance_description   │ 向量搜索（标签）    │
            │                         │ =”清秀型”                │                     │
            │ “找纯欲风的”            │ appearance_description   │ 向量搜索（口语化）  │
            │                         │ =”纯欲风”                │                     │
            │ “找清秀又漂亮的”        │ appearance_level=”high”  │ 组合筛选            │
            │                         │ + appearance_description │                     │
            │ “找像田曦薇的女生”      │ photo_url=”https://...”  │ 照片向量搜索        │
            │                         │ （Agent自己搜照片）      │ + Agent自己判断相似度│
            │                         │ + Agent看照片筛选        │                     │
            └─────────────────────────┴──────────────────────────┴─────────────────────┘

            返回数据：
            - 基础信息：姓名、年龄、城市、职业等
            - 性格数据：personality_signals包含MBTI、依恋风格、价值观等原始数据
            - 外貌数据：appearance_keywords、style_scores等原始数据
            - candidate_context：数据完整度指示器，帮助Agent判断推荐理由的详细程度
              - evidence_level：数据丰富程度（high/medium/low）
              - reason_mode：可用的推理深度（rich_reasoning/limited_reasoning/profile_only）
              - missing_dimensions：缺失的数据维度（如summary、personality_traits等）
              - Agent应根据这些字段自主决定推荐理由的详细程度和措辞
            - Agent自主判断性格匹配度和外貌匹配度，生成推荐理由

            参数：
            - criteria_json: 筛选条件的JSON字符串（硬约束）
            - personality_match_json: 性格匹配条件的JSON字符串（可选）
            - limit: 最终返回数量（默认5，最大10）
            - exclude_current_results: 是否排除当前已展示候选人（用于”换一批”）
            - appearance_level: 外貌筛选级别（”high”/”medium”/”low”，默认”medium”）
            - appearance_description: 外貌描述的自然语言字符串（可选）
            - photo_url: 参考照片URL（可选，用于明星脸搜索）

            【重要：对用户的表达约束】
            - 你可以内部使用 appearance_level / appearance_description 来完成检索
            - 但回复用户时，应使用自然语言描述：
              - “我按你更在意的外形感觉重新筛了一批”
              - “这批整体更符合你的审美方向”
              - “先给你看几位更有眼缘的”
            - 候选人分组标题应写成”更符合你审美的这几位”或”这批更有眼缘”
            - 不要说”高颜值推荐”、”评分筛选”等技术术语

            `exclude_current_results` 使用规则：
            - 用户想"换一批 / 看别的 / 再看看别人 / 不要刚才那批"：
              必须传 `true`
            - 用户只是追问当前候选人、解释推荐理由、比较现有候选人：
              必须传 `false`
            - 你已经决定要展示"新的候选人列表"而不是继续聊当前候选人时：
              应优先传 `true`，避免把刚展示过的人重复返回

            【重要】搜索策略（两阶段）：
            第一阶段：数据库搜索（获取所有符合硬约束的候选人）
            - 不限制数量（搜索所有符合 criteria 的候选人）
            - 避免因数量限制过小导致向量筛选后结果为空

            第二阶段：向量筛选 + 截断
            - 对第一阶段的候选人做性格向量筛选 + 外貌向量筛选
            - 向量筛选后截断为 limit 数量返回
            - 确保"无性格数据"的候选人不会被错误过滤

            返回：
            - has_match: 是否找到候选人（True/False）
            - result_count: 候选人数量
            - results: 候选人列表（包含性格原始数据 + 外貌数据）

            【重要】Agent下一步动作（必须遵循）：
            - 用户想"换一批/看其他/再看看别人"：
              → 调用本工具时传 `exclude_current_results=true`
              → 如果不传 true，你可能会再次拿到当前这批候选人
            - has_match=True, result_count>0（找到候选人）：
              → 调用 show_candidates 展示候选人列表
              → 或调用 reply_to_user 解释推荐理由
              → 不能直接输出文本消息结束
            - has_match=False, result_count=0（未找到候选人）：
              → **必须调用 reply_to_user** 向用户解释情况并提供替代方案
              → 替代方案：放宽条件、扩大搜索范围、创建订阅等
              → 不能直接输出文本消息结束
            """
            # 🔍 可观测性埋点：记录Agent传递的参数
            _logger.info(
                "【工具调用参数】search_partner_candidates criteria_json=%s personality_match_json=%s limit=%s exclude_current_results=%s appearance_level=%s appearance_description=%s photo_url=%s",
                repr(criteria_json)[:200],
                repr(personality_match_json)[:200],
                limit,
                exclude_current_results,
                appearance_level,
                repr(appearance_description)[:200],
                repr(photo_url)[:200],
            )

            criteria = json.loads(str(criteria_json or "{}"))
            if not isinstance(criteria, dict):
                raise ValueError("criteria_json must decode into a JSON object")

            # 🔍 可观测性埋点：记录解析后的criteria字典
            _logger.info(
                "【解析后的criteria】%s",
                json.dumps(criteria, ensure_ascii=False)[:200]
            )

            # 解析性格匹配参数
            personality_match = {}
            if personality_match_json and personality_match_json.strip():
                try:
                    personality_match = json.loads(personality_match_json)
                    if not isinstance(personality_match, dict):
                        _logger.warning("personality_match_json must decode into a JSON object, got %s", type(personality_match))
                        personality_match = {}
                except json.JSONDecodeError as exc:
                    _logger.warning("personality_match_json decode failed: %s", str(exc)[:100])
                    personality_match = {}

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 新增：外貌参数处理（抽象化参数）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 系统内部会将抽象参数转换为具体的筛选条件
            # Agent不需要知道内部实现细节
            appearance_match = {}

            # 1. appearance_level 处理（系统内部转换）
            # Agent只传入"high"/"medium"/"low"，系统自动设置筛选标准
            if appearance_level and appearance_level.strip():
                normalized_level = appearance_level.strip().lower()
                if normalized_level in ("high", "medium", "low"):
                    appearance_match["level"] = normalized_level
                    _logger.info(
                        "【外貌筛选-级别】appearance_level=%s",
                        normalized_level
                    )

            # 2. appearance_description 处理（自然语言描述）
            # Agent传入自然语言描述，系统自动解析
            if appearance_description and appearance_description.strip():
                appearance_match["description"] = appearance_description.strip()
                _logger.info(
                    "【外貌筛选-描述】appearance_description=%s",
                    appearance_description[:100]
                )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 新增：明星脸搜索参数处理
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 3. 明星脸搜索（照片向量搜索）
            photo_match = {}
            if photo_url and photo_url.strip():
                photo_match = {
                    "photo_url": photo_url.strip(),
                }
                _logger.info(
                    "【明星脸搜索】photo_url=%s",
                    photo_url[:200]
                )

            # ✅ 方案C：放宽limit上限，支持两阶段搜索
            # 第一阶段搜索至少50个，第二阶段截断为用户要求的limit
            # 所以上限放宽到50（而不是10）
            normalized_limit = max(1, min(int(limit or 5), 50))
            response = run_input.search_partner_candidates(
                criteria,
                personality_match,
                normalized_limit,
                exclude_current_results=bool(exclude_current_results),
                appearance_match=appearance_match,  # ← 传递外貌向量搜索参数
                photo_match=photo_match,  # ← 传递明星脸搜索参数
            )
            tool_state["last_search_response"] = response
            return _summarize_search_response_for_model(response)

        @function_tool
        def build_visual_search_plan(
            turn_text: str = "",
            current_image_url: str = "",
        ) -> dict[str, Any]:
            """构建视觉搜索计划，判断这轮是直接搜、继续沿用上一张图，还是先追问。

            适用场景：
            - 用户上传了图片，但没有明确说按脸找还是按感觉找
            - 用户说“按刚才那张继续找”“还是这种感觉”
            - 用户补充 refinement，如“换成上海”“温柔一点”
            """
            plan = _build_visual_search_plan_impl(
                text=turn_text or None,
                image_source=current_image_url or None,
                visual_context=_normalize_visual_context(run_input.runtime_context) or {},
                client_context={},
            )
            return plan

        @function_tool
        def load_recent_visual_context() -> dict[str, Any]:
            """读取当前 discovery session 最近一次视觉搜索上下文。"""
            return _normalize_visual_context(run_input.runtime_context) or {
                "has_reference_image": False,
                "active_visual_intent": {},
                "active_constraints": {},
                "last_query_text": None,
                "last_result_profile_ids": [],
            }

        def _visual_search_candidates(
            *,
            mode: str,
            reference_image_url: str,
            query_text: str = "",
            celebrity_name: str = "",
            hard_filters_json: str = "",
            limit: int = 12,
        ) -> dict[str, Any]:
            source_dsn, source_table = resolve_profile_source(
                os.environ.get("HER_DISCOVERY_PROFILE_SOURCE") or os.environ.get("HER_PROFILE_SOURCE_DSN"),
                None,
            )
            hard_filters: dict[str, Any] = {}
            if hard_filters_json.strip():
                decoded = json.loads(hard_filters_json)
                if isinstance(decoded, dict):
                    hard_filters = decoded
            intent = PhotoPreferenceIntent(
                intent_type={
                    "face": "face_similarity_search",
                    "style": "style_similarity_search",
                    "celebrity": "celebrity_face_search",
                }.get(mode, "hybrid_photo_search"),
                mode=mode,
                query_text=query_text.strip() or celebrity_name.strip() or "视觉搜索",
                attribute_filters={},
                hard_filters=hard_filters,
                celebrity_name=celebrity_name.strip() or None,
                raw_text=query_text.strip() or celebrity_name.strip() or "视觉搜索",
            )
            response = retrieve_visual_candidates(
                source_dsn=source_dsn,
                requester_user_key=str(run_input.requester_id),
                intent=intent,
                image_source=reference_image_url.strip() or None,
                requester_profile_id=run_input.profile_id,
                top_k=max(1, min(int(limit or 12), 30)),
            )
            ranked_results = [
                dict(item)
                for item in list(response.get("results") or [])
                if int(item.get("profile_id") or 0) > 0
            ]
            profile_ids = [int(item["profile_id"]) for item in ranked_results]
            rows_by_id: dict[int, dict[str, Any]] = {}
            if profile_ids:
                placeholders = ", ".join("?" for _ in profile_ids)
                rows = list_profiles(
                    source_dsn=source_dsn,
                    source_table_name=source_table,
                    where_clause=f"`id` IN ({placeholders})",
                    params=tuple(profile_ids),
                )
                rows_by_id = {
                    int(row.get("id")): dict(row)
                    for row in rows
                    if int(row.get("id") or 0) > 0
                }
            return {
                "search_type": response.get("search_type") or intent.intent_type,
                "intent_mode": mode,
                "query_text": intent.query_text,
                "result_count": len(ranked_results),
                "results": [
                    {
                        "profile_id": int(item.get("profile_id") or 0),
                        "title": str((rows_by_id.get(int(item.get("profile_id") or 0)) or {}).get("display_name") or (rows_by_id.get(int(item.get("profile_id") or 0)) or {}).get("name") or "候选人"),
                        "city": str((rows_by_id.get(int(item.get("profile_id") or 0)) or {}).get("city") or "").strip() or None,
                        "final_score": item.get("final_score") or item.get("base_score"),
                        "appearance_summary": item.get("appearance_summary"),
                    }
                    for item in ranked_results
                ],
            }

        @function_tool
        def parse_visual_user_intent(
            turn_text: str = "",
            current_image_url: str = "",
        ) -> dict[str, Any]:
            """解析用户这句视觉搜索诉求，输出能力化 visual plan。"""
            return _build_visual_search_plan_impl(
                text=turn_text or None,
                image_source=current_image_url or None,
                visual_context=_normalize_visual_context(run_input.runtime_context) or {},
                client_context={},
            )

        @function_tool
        def search_face_similarity_candidates(
            reference_image_url: str,
            query_text: str = "",
            hard_filters_json: str = "",
            limit: int = 12,
        ) -> dict[str, Any]:
            """按脸相似搜索候选人。底层仍复用内部 face search 能力。"""
            return _visual_search_candidates(
                mode="face",
                reference_image_url=reference_image_url,
                query_text=query_text,
                hard_filters_json=hard_filters_json,
                limit=limit,
            )

        @function_tool
        def search_style_similarity_candidates(
            reference_image_url: str,
            query_text: str = "",
            hard_filters_json: str = "",
            limit: int = 12,
        ) -> dict[str, Any]:
            """按整体感觉/风格搜索候选人。底层仍复用内部 style search 能力。"""
            return _visual_search_candidates(
                mode="style",
                reference_image_url=reference_image_url,
                query_text=query_text,
                hard_filters_json=hard_filters_json,
                limit=limit,
            )

        @function_tool
        def search_reference_person_candidates(
            reference_person_name: str = "",
            reference_image_url: str = "",
            hard_filters_json: str = "",
            limit: int = 12,
        ) -> dict[str, Any]:
            """按参考人物/参考图搜索候选人。底层仍复用内部 reference/face search 能力。"""
            if reference_image_url.strip():
                return _visual_search_candidates(
                    mode="face",
                    reference_image_url=reference_image_url,
                    query_text=reference_person_name,
                    celebrity_name=reference_person_name,
                    hard_filters_json=hard_filters_json,
                    limit=limit,
                )
            return {
                "ok": False,
                "error": "reference_image_url is required",
                "hint": "先用 WebSearch + resolve_direct_image_urls 拿到参考人物图片，再调用本工具。",
            }

        @function_tool
        def apply_candidate_hard_filters(
            candidate_ids: list[int],
            hard_filters_json: str = "",
        ) -> dict[str, Any]:
            """对已有候选人结果应用硬条件过滤。"""
            hard_filters = json.loads(hard_filters_json) if hard_filters_json.strip() else {}
            allowed_ids = [int(candidate_id) for candidate_id in list(candidate_ids or []) if int(candidate_id) > 0]
            return {
                "input_candidate_ids": allowed_ids,
                "hard_filters": hard_filters if isinstance(hard_filters, dict) else {},
                "filtered_candidate_ids": allowed_ids,
            }

        @function_tool
        def rerank_visual_candidates(
            candidate_ids: list[int],
            rerank_reason: str = "",
        ) -> dict[str, Any]:
            """在已有视觉候选人上做二次排序说明。"""
            ranked_ids = [int(candidate_id) for candidate_id in list(candidate_ids or []) if int(candidate_id) > 0]
            return {
                "candidate_ids": ranked_ids,
                "rerank_reason": rerank_reason.strip() or None,
                "reranked_candidate_ids": ranked_ids,
            }

        @function_tool
        def persist_visual_search_memory(
            visual_memory_json: str,
        ) -> dict[str, Any]:
            """把本轮视觉搜索结论整理成可落库的记忆快照。"""
            payload = json.loads(visual_memory_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError("visual_memory_json must decode into an object")
            return {"ok": True, "memory_snapshot": payload}

        @function_tool
        def resolve_direct_image_urls(
            page_url: str,
            max_results: int = 5,
        ) -> dict[str, Any]:
            """从网页中提取可直接访问的图片URL，帮助明星脸搜索拿到 photo_url。

            用法：
            - 先用 web_search 找到可能包含明星照片的页面
            - 再调用本工具，把页面 URL 转成 1~5 个直接图片 URL
            - 选一个最像官方/写真/清晰头像的 URL 传给 search_partner_candidates(photo_url=...)
            """
            normalized_url = str(page_url or "").strip()
            if not normalized_url:
                raise ValueError("page_url is required")

            limit = max(1, min(int(max_results or 5), 10))
            _logger.info("【工具调用】resolve_direct_image_urls page_url=%s max_results=%s", normalized_url[:300], limit)

            try:
                response = httpx.get(
                    normalized_url,
                    timeout=15.0,
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                        )
                    },
                )
                response.raise_for_status()
            except Exception as exc:
                _logger.warning("resolve_direct_image_urls fetch failed url=%s error=%s", normalized_url[:200], str(exc)[:200])
                return {
                    "ok": False,
                    "page_url": normalized_url,
                    "image_urls": [],
                    "error": str(exc)[:300],
                }

            content_type = str(response.headers.get("content-type") or "").lower()
            final_url = str(response.url)
            if content_type.startswith("image/") and _looks_like_image_url(final_url):
                return {
                    "ok": True,
                    "page_url": normalized_url,
                    "resolved_url": final_url,
                    "image_urls": [final_url],
                    "content_type": content_type,
                }

            html_text = response.text or ""
            image_urls = _extract_direct_image_urls_from_html(final_url, html_text)[:limit]
            _logger.info("【工具结果】resolve_direct_image_urls resolved_url=%s image_count=%s", final_url[:300], len(image_urls))
            return {
                "ok": bool(image_urls),
                "page_url": normalized_url,
                "resolved_url": final_url,
                "image_urls": image_urls,
                "content_type": content_type,
            }

        @function_tool
        def create_saved_search_subscription_from_last_search() -> dict[str, Any]:
            """创建订阅，按当前搜索条件持续留意新候选人。当用户想长期关注符合条件的候选人、或者当前搜索无结果时推荐使用。"""
            return run_input.create_saved_search_subscription_from_last_search()

        @function_tool
        def suggest_assessment(assessment_type: str) -> dict[str, Any]:
            """检查用户测评状态，如未完成则返回引导卡片。

            适用场景：
            - 当用户关心性格匹配、提到性格相关话题时
            - 当Agent判断需要了解用户性格类型时

            参数：
            - assessment_type: 测评类型（必须传入）
              - "mbti_16": MBTI性格测试（了解性格类型，快速简单）
              - "attachment_style": 依恋风格测试（了解亲密关系模式、相处节奏）
              - "big_five": 大五人格测试（了解性格结构，科学全面）

            Agent自主选择测评类型的建议：
            - 用户提到"性格类型"、"内向/外向"、"MBTI" → 可优先推荐MBTI（快速了解性格类型）
            - 用户提到"相处节奏"、"忽冷忽热"、"关系模式"、"依恋" → 可考虑依恋风格测试
            - 用户想深入了解性格结构、需要科学分析 → 可推荐大五人格测试

            返回：
            - 已完成：返回性格类型原始数据，Agent可自主决定是否向用户解释
            - 未完成：返回测评状态原始数据，Agent必须调用reply_to_user向用户展示测评引导

            【重要】Agent下一步动作（必须遵循）：
            - completed=False（用户未完成测评）：
              → 立即调用 reply_to_user，message中用口语化方式介绍测评（如："做个MBTI测试，5分钟就能了解你的性格类型..."）
              → button_texts提供测评入口（如：["开始测评", "暂不测试"]）
              → 不能直接输出文本消息结束
            - completed=True（用户已完成测评）：
              → 可自主决定是否调用 reply_to_user 解释性格类型
            """
            _logger.info("【工具调用】suggest_assessment")
            _logger.info("  - assessment_type：%s", assessment_type)
            result = run_input.suggest_assessment(assessment_type)
            tool_state["assessment_payload"] = result
            return result

        # ====================================================================
        # 方案A：拆分为两个专用工具（reply_to_user + show_candidates）
        # ====================================================================
        tool_state["reply_payload"] = None  # 存储 reply_to_user 工具参数
        tool_state["show_payload"] = None   # 存储 show_candidates 工具参数

        @function_tool
        def reply_to_user(
            message: str,
            phase: str = "collecting_preferences",
            button_texts: list[str] = [],
        ) -> dict[str, Any]:
            """回复用户对话消息，不展示候选人卡片。

            适用场景：
            - 回答用户问题
            - 解释推荐理由
            - 收集用户反馈
            """
            # 【证据优先】记录工具调用参数
            _logger.info("【工具调用】reply_to_user")
            _logger.info("  - message：%s", message)
            _logger.info("  - phase：%s", phase)
            _logger.info("  - button_texts：%s", button_texts)

            payload = {
                "kind": "reply",
                "phase": phase,
                "assistant_message": message,
                "suggested_actions": [
                    {"label": btn, "style": "secondary", "semantic_payload": {"kind": "suggested"}}
                    for btn in button_texts[:3]
                ],
            }
            tool_state["reply_payload"] = payload
            return {"success": True, "kind": "reply", "phase": phase}

        @function_tool
        def show_candidates(
            message: str,
            candidate_ids: list[int],
            title: str = "",
            criteria: list[str] = [],
        ) -> dict[str, Any]:
            """展示候选人列表（适用于搜索结果和推荐候选人）

            适用场景：
            - 搜索后有新的候选人结果
            - 推荐候选人推送（message包含推荐介绍）
            """
            # 【证据优先】记录工具调用参数
            _logger.info("【工具调用】show_candidates")
            _logger.info("  - message：%s", message)
            _logger.info("  - candidate_ids：%s", candidate_ids)
            _logger.info("  - title：%s", title)
            _logger.info("  - criteria：%s", criteria)

            payload = {
                "kind": "show",
                "phase": "results_shown" if candidate_ids else "no_result",
                "assistant_message": message,
                "result_group_title": title if title else None,
                "criteria_labels": criteria,
                "selected_candidates": [
                    {"profile_id": cid, "reason_summary": ""}
                    for cid in candidate_ids
                ],
            }
            tool_state["show_payload"] = payload
            return {"success": True, "kind": "show", "candidate_count": len(candidate_ids)}

        instructions = _build_discovery_agent_instructions(
            event=event,
            user_message=user_message,
            action_context=action_context,
        )

        web_search_tool = WebSearchTool(
            search_context_size="medium",
            external_web_access=True,
        )
        _logger.info("Discovery agent 已挂载 WebSearchTool（实验性接入）")

        # 方案A：拆分为两个专用工具（reply_to_user + show_candidates）
        tools = [
            sync_requester_persona_memory,
            # propose_requester_profile_update,  # 已注释：暂时禁用此工具
            load_recent_visual_context,
            build_visual_search_plan,
            parse_visual_user_intent,
            search_face_similarity_candidates,
            search_style_similarity_candidates,
            search_reference_person_candidates,
            apply_candidate_hard_filters,
            rerank_visual_candidates,
            persist_visual_search_memory,
            search_partner_candidates,
            resolve_direct_image_urls,
            create_saved_search_subscription_from_last_search,
            reply_to_user,   # 方案A：回复专用工具
            show_candidates, # 方案A：展示候选人专用工具
            suggest_assessment,  # 心理测评引导工具
            web_search_tool,  # 实验性：允许 Agent 直接联网搜索明星参考图
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
        # 启用会话记忆：agent_session 将在 _run_streamed_agent 中传入 Runner
        if run_input.agent_session is not None:
            _logger.debug(
                "discovery agent session memory enabled session_id=%s",
                run_input.session_id,
            )

        # 方案A：不设置 output_type，因为使用专用工具（reply_to_user/show_candidates）
        # Agent 通过工具参数返回决策，不需要直接输出 DiscoveryDecisionModel
        # 遗留问题：方案 C 的 output_type=DiscoveryDecisionModel 会导致 Agents SDK
        # 错误地把工具参数当作决策模型解析（如 search_partner_candidates 的参数）
        agent = Agent(
            name="discovery_matchmaker",
            instructions=instructions.strip(),
            model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
            tools=tools,
        )
        started = time.perf_counter()
        result, first_token_latency_ms = asyncio.run(
            self._run_streamed_agent(
                Runner=Runner,
                agent=agent,
                runtime_input=runtime_input,
                started=started,
                tool_state=tool_state,
                agent_session=run_input.agent_session,  # 启用会话记忆
                async_client=async_client,
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
        # 方案C：支持 reply_to_user + show_candidates 同时调用
        # ====================================================================
        reply_payload = tool_state.get("reply_payload")
        show_payload = tool_state.get("show_payload")

        # 方案C：提取所有 payload，供 Service 层处理
        payloads = []
        if reply_payload:
            payloads.append(reply_payload)
        if show_payload:
            payloads.append(show_payload)

        # 提取主要 decision（用于 phase 等核心字段）
        # 优先使用 show_candidates（展示候选人优先级高于纯回复）
        decision_payload = show_payload or reply_payload

        if decision_payload is not None:
            _logger.debug(
                "discovery agent extracted decision from %s tool payload=%s, total_payloads=%s",
                "show_candidates" if show_payload else "reply_to_user",
                str(decision_payload)[:200],
                len(payloads)
            )
            # 方案C：构建 decision，传入 _all_payloads
            decision = DiscoveryDecision(
                phase=decision_payload.get("phase") or "collecting_preferences",
                assistant_message=decision_payload.get("assistant_message") or "",
                criteria_labels=decision_payload.get("criteria_labels") or [],
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label=action.get("label"),
                        style=action.get("style"),
                        semantic_payload=action.get("semantic_payload"),
                    )
                    for action in (decision_payload.get("suggested_actions") or [])
                ],
                result_group_title=decision_payload.get("result_group_title"),
                selected_candidates=[
                    DiscoveryCandidateSelection(
                        profile_id=c.get("profile_id"),
                        reason_summary=c.get("reason_summary") or "",
                    )
                    for c in (decision_payload.get("selected_candidates") or [])
                ],
                _all_payloads=payloads,  # 方案C：传入所有 payloads
            )
        else:
            # Fallback：尝试从 final_output 恢复
            final_output = getattr(result, "final_output", result)
            _logger.warning(
                "discovery agent no reply/show tool called, falling back to final_output type=%s",
                type(final_output).__name__,
            )
            # 尝试多种恢复方式
            recovered = None
            if isinstance(final_output, Exception):
                recovered = _recover_decision_from_exception(final_output)
            elif isinstance(final_output, dict):
                # dict 类型的 final_output 可能包含决策结构
                try:
                    recovered = _decision_payload_to_decision_with_repair(final_output)
                except Exception:
                    recovered = None
            else:
                try:
                    recovered = _validate_decision_output(final_output)
                except Exception:
                    recovered = None
            if recovered is not None:
                decision = recovered
            else:
                # ✅ 删除兜底方案：Agent没有调用工具时，抛出异常暴露真实问题
                raise RuntimeError(
                    f"Agent没有调用reply_to_user或show_candidates工具。"
                    f"用户输入：{user_message or action_context or 'initial'}"
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

        # ====================================================================
        # 【证据优先】关键日志埋点：记录 Agent 实际行为
        # 用于测试实验边界验证，收集证据后再决定改进方案
        # ====================================================================
        _logger.info("=" * 80)
        _logger.info("【Agent 实际行为记录】")
        _logger.info("用户输入：%s", user_message or action_context or "initial")
        _logger.info("Agent 输出：%s", decision.assistant_message)
        _logger.info("决策阶段：%s", decision.phase)
        _logger.info("建议按钮：%s", [action.label for action in (decision.suggested_actions or [])])
        _logger.info("工具调用：%s", list(tool_state.keys()))
        _logger.info("=" * 80)

        # 提取测评卡片数据
        assessment_payload = tool_state.get("assessment_payload")

        return DiscoveryRuntimeResult(
            decision=decision,
            search_response=search_response,
            assessment_payload=assessment_payload,  # 传递测评卡片数据给前端
        )

    async def _run_streamed_agent(
        self,
        *,
        Runner: Any,
        agent: Any,
        runtime_input: str,
        started: float,
        tool_state: dict[str, Any],
        agent_session: Any | None = None,  # 新增：会话记忆
        async_client: Any | None = None,
    ) -> tuple[Any, float | None]:
        try:
            # 启用会话记忆：传入 session 参数
            streamed_result = Runner.run_streamed(
                agent,
                input=runtime_input,
                session=agent_session,  # 启用会话记忆
            )
            first_token_latency_ms: float | None = None
            async for stream_event in streamed_result.stream_events():
                if first_token_latency_ms is None and _is_first_token_stream_event(stream_event):
                    first_token_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
                if tool_state.get("show_payload") is not None or tool_state.get("reply_payload") is not None:
                    _logger.debug(
                        "discovery agent stopping stream after terminal tool payload: has_show=%s has_reply=%s",
                        tool_state.get("show_payload") is not None,
                        tool_state.get("reply_payload") is not None,
                    )
                    break
            run_loop_task = getattr(streamed_result, "run_loop_task", None)
            if (
                run_loop_task is not None
                and tool_state.get("show_payload") is None
                and tool_state.get("reply_payload") is None
            ):
                await run_loop_task
            return streamed_result, first_token_latency_ms
        finally:
            if async_client is not None:
                await async_client.close()
                _logger.debug("Agents SDK AsyncOpenAI 客户端已在当前事件循环内关闭")


def create_default_discovery_agent_runtime() -> DiscoveryAgentRuntime:
    # ✅ 删除兜底方案：不再使用fallback，直接返回AgentsSdkDiscoveryAgentRuntime
    return AgentsSdkDiscoveryAgentRuntime()


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
    "create_default_discovery_agent_runtime",
]
