"""Agents SDK-backed runtime for the discovery page."""

from __future__ import annotations

import json
import logging
import os
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
    ]
    return {
        key: profile.get(key)
        for key in keep_keys
        if profile.get(key) not in (None, "", [], {})
    }


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
6. 如果条件还不够，就只问 1 个最关键的问题。
7. 如果条件已经够用，就调用搜索工具。
8. 如果搜索到结果，你负责决定展示哪几位、重点强调什么。
9. 但你不能编造候选人的原始卡片字段。你只能输出 profile_id 和 reason_summary，后端会去填卡片标题、照片、认证等稳定字段。

official_context 里常见信息：
- requester_profile_snapshot：用户当前画像快照
- recent_timeline_summary：最近几轮页面时间线摘要
- visible_actions：当前页面还能点哪些 action
- last_search_summary：最近一轮搜索摘要
- page_summary：当前页面上的 criteria chips、结果卡片摘要等

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
- semantic_payload.kind 只用这些值：starter_prompt、followup_prompt、saved_search_opt_in、refine_candidates、add_criteria、refine_preferences、show_more_candidates、age_preference。
- 如果用户更新了本人资料，先 `propose_requester_profile_update`；如果只是择偶偏好，用 `sync_requester_persona_memory`。
- 只有在你真的调用了搜索工具并且决定展示结果时，才填写 selected_candidates。
- selected_candidates 里的 profile_id 必须来自最新一次搜索工具返回的 results。
- 如果搜索工具返回 `error_code` 或 `diagnostics.error`，不要说“本地没有符合条件的人”。要自然说明这轮搜索失败了，不代表没人，并引导用户重试或继续补充条件。
- 如果没有合适结果，phase 用 no_result，message 里自然说明，并给 1 到 2 个放宽方向。
- 如果搜索 0 结果且你判断适合引导持续留意，可以给一个 action，semantic_payload 里放 `{"kind":"saved_search_opt_in"}`。
- 如果本轮是 action_click，且 clicked_action.hint.kind 是 `saved_search_opt_in`，说明用户刚刚同意了持续留意；这时你应该优先调用 `create_saved_search_subscription_from_last_search`，再告诉用户你已经记下。

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
