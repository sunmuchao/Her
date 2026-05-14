"""Agents SDK-backed runtime for the discovery page."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field, model_validator


VALID_PHASES = {
    "collecting_preferences",
    "searching",
    "results_shown",
    "no_result",
}
VALID_ACTION_STYLES = {"primary", "secondary", "ghost"}


@dataclass(frozen=True)
class DiscoveryRunInput:
    session_id: str
    requester_id: int
    profile_id: int
    phase: str
    criteria_labels: list[str]
    recent_timeline: list[dict[str, Any]]
    get_discovery_session_state: Callable[[], dict[str, Any]]
    get_requester_profile: Callable[[], dict[str, Any] | None]
    search_partner_candidates: Callable[[dict[str, Any], int], dict[str, Any]]
    create_saved_search_subscription_from_last_search: Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class DiscoveryActionSuggestion:
    label: str
    style: str = "secondary"
    semantic_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryCandidateSelection:
    profile_id: int
    reason_summary: str = ""


@dataclass(frozen=True)
class DiscoveryDecision:
    phase: str
    assistant_message: str
    criteria_labels: list[str] = field(default_factory=list)
    suggested_actions: list[DiscoveryActionSuggestion] = field(default_factory=list)
    result_group_title: str | None = None
    selected_candidates: list[DiscoveryCandidateSelection] = field(default_factory=list)


@dataclass(frozen=True)
class DiscoveryRuntimeResult:
    decision: DiscoveryDecision
    search_response: dict[str, Any] | None = None


class DiscoveryAgentRuntime(Protocol):
    def initial_decision(self, run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult: ...

    def run_turn(
        self,
        run_input: DiscoveryRunInput,
        *,
        user_message: str | None = None,
        action_context: dict[str, Any] | None = None,
    ) -> DiscoveryRuntimeResult: ...


class DiscoveryActionSuggestionModel(BaseModel):
    label: str
    style: str = Field(default="secondary")
    semantic_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_action(self) -> "DiscoveryActionSuggestionModel":
        if not str(self.label or "").strip():
            raise ValueError("suggested action label is required")
        if self.style not in VALID_ACTION_STYLES:
            raise ValueError("suggested action style must be primary, secondary, or ghost")
        return self


class DiscoveryCandidateSelectionModel(BaseModel):
    profile_id: int = Field(ge=1)
    reason_summary: str = Field(default="")


class DiscoveryDecisionModel(BaseModel):
    phase: str
    assistant_message: str
    criteria_labels: list[str] = Field(default_factory=list)
    suggested_actions: list[DiscoveryActionSuggestionModel] = Field(default_factory=list)
    result_group_title: str | None = Field(default=None)
    selected_candidates: list[DiscoveryCandidateSelectionModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_decision(self) -> "DiscoveryDecisionModel":
        if self.phase not in VALID_PHASES:
            raise ValueError("phase must be collecting_preferences, searching, results_shown, or no_result")
        if not str(self.assistant_message or "").strip():
            raise ValueError("assistant_message is required")
        return self


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return default


def _env_float(*names: str, default: float) -> float:
    raw = _env_first(*names, default=str(default))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _configure_agents_sdk_provider() -> None:
    from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled
    from openai import AsyncOpenAI

    base_url = _env_first(
        "HER_DISCOVERY_AGENT_BASE_URL",
        "HER_CHAT_AGENT_BASE_URL",
        "OPENAI_BASE_URL",
        "HER_CHAT_ASSISTANT_BASE_URL",
    )
    api_mode = _env_first(
        "HER_DISCOVERY_AGENT_OPENAI_API",
        "HER_CHAT_AGENT_OPENAI_API",
        "HER_CHAT_ASSISTANT_OPENAI_API",
    ).lower()

    if base_url:
        api_key = os.environ.get("OPENAI_API_KEY") or ""
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=_env_float(
                "HER_DISCOVERY_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_AGENT_TIMEOUT_SECONDS",
                "HER_CHAT_ASSISTANT_TIMEOUT_SECONDS",
                default=120.0,
            ),
        )
        set_default_openai_client(client, use_for_tracing=False)
        set_default_openai_api(api_mode or "chat_completions")
        disable_tracing = _env_first(
            "HER_DISCOVERY_AGENT_DISABLE_TRACING",
            "HER_CHAT_AGENT_DISABLE_TRACING",
            "HER_CHAT_ASSISTANT_DISABLE_TRACING",
            default="1",
        ).lower()
        if disable_tracing in ("1", "true", "yes"):
            set_tracing_disabled(True)
        return

    if api_mode:
        set_default_openai_api(api_mode)


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


def _build_runtime_prompt(
    *,
    run_input: DiscoveryRunInput,
    event: str,
    user_message: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> str:
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
        "recent_timeline": _compact_timeline(run_input.recent_timeline),
        "requester_profile_hint": _compact_requester_profile(run_input.get_requester_profile()),
        "note": (
            "If you need more context, call tools. "
            "Do not invent candidate raw fields; only select profile_id values from the latest search tool response."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _coerce_json_output(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    text = str(raw_output or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    if text and not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _validate_decision_output(raw_output: Any) -> DiscoveryDecision:
    parsed = DiscoveryDecisionModel.model_validate(_coerce_json_output(raw_output))
    return _to_decision(parsed)


def _recover_decision_from_exception(exc: Exception) -> DiscoveryDecision | None:
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
        return None


def _to_decision(model: DiscoveryDecisionModel) -> DiscoveryDecision:
    return DiscoveryDecision(
        phase=model.phase,
        assistant_message=model.assistant_message.strip(),
        criteria_labels=[str(label).strip() for label in model.criteria_labels if str(label or "").strip()],
        suggested_actions=[
            DiscoveryActionSuggestion(
                label=action.label.strip(),
                style=action.style,
                semantic_payload=dict(action.semantic_payload or {}),
            )
            for action in model.suggested_actions
        ],
        result_group_title=(str(model.result_group_title or "").strip() or None),
        selected_candidates=[
            DiscoveryCandidateSelection(
                profile_id=selection.profile_id,
                reason_summary=str(selection.reason_summary or "").strip(),
            )
            for selection in model.selected_candidates
        ],
    )


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
        runtime = _env_first(
            "HER_DISCOVERY_AGENT_RUNTIME",
            "HER_CHAT_AGENT_RUNTIME",
            default="agents_sdk",
        ).lower()
        if runtime in {"stub", "heuristic", "fallback"}:
            return False
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
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
        def get_discovery_session_state() -> dict[str, Any]:
            return run_input.get_discovery_session_state()

        @function_tool
        def get_requester_profile() -> dict[str, Any]:
            return dict(run_input.get_requester_profile() or {})

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
2. 你自己决定什么时候继续追问，什么时候调用搜索工具。
3. 如果条件还不够，就只问 1 个最关键的问题。
4. 如果条件已经够用，就调用搜索工具。
5. 如果搜索到结果，你负责决定展示哪几位、重点强调什么。
6. 但你不能编造候选人的原始卡片字段。你只能输出 profile_id 和 reason_summary，后端会去填卡片标题、照片、认证等稳定字段。

工具说明：
- `get_discovery_session_state`：看当前 session 的状态、当前条件和最近内容。
- `get_requester_profile`：看用户自己的资料，帮助你理解 TA 的背景。
- `search_partner_candidates`：执行候选搜索。
  - 参数 `criteria_json` 必须是 JSON 字符串，对应 partner-search 的 criteria 对象。
  - 常见字段可以用：gender, city, cities, age_min, age_max, relationship_goal, relationship_goals, must_have, prefer, smoking, drinking, verified_level_min, photo_count_min, active_within_days。
  - 例子：{"gender":"女","cities":["无锡"],"relationship_goals":["认真恋爱"],"must_have":["情绪稳定"],"prefer":["工作稳定"]}.
- `create_saved_search_subscription_from_last_search`：把上一轮 0 结果搜索保存成“持续留意”订阅。
  - 只有在用户已经明确同意“继续留意”时才能调用。
  - 不要在还有匹配结果时调用。

输出原则：
- assistant_message 保持短，像真人红娘，不要写成系统说明。
- criteria_labels 用于给前端展示条件 chips，最多 6 个。
- suggested_actions 最多 3 个，标签要短。
- 只有在你真的调用了搜索工具并且决定展示结果时，才填写 selected_candidates。
- selected_candidates 里的 profile_id 必须来自最新一次搜索工具返回的 results。
- 如果没有合适结果，phase 用 no_result，message 里自然说明，并给 1 到 2 个放宽方向。
- 如果搜索 0 结果且你判断适合引导持续留意，可以给一个 action，semantic_payload 里放 `{"kind":"saved_search_opt_in"}`。
- 如果本轮是 action_click，且 clicked_action.hint.kind 是 `saved_search_opt_in`，说明用户刚刚同意了持续留意；这时你应该优先调用 `create_saved_search_subscription_from_last_search`，再告诉用户你已经记下。

输出必须是合法 JSON，只输出结构化结果，不要加代码块。
"""

        agent = Agent(
            name="discovery_matchmaker",
            instructions=instructions.strip(),
            model=_env_first(
                "HER_DISCOVERY_AGENT_MODEL",
                "HER_CHAT_AGENT_MODEL",
                "HER_CHAT_ASSISTANT_MODEL",
                default="gpt-4.1-mini",
            ),
            output_type=AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=False),
            tools=[
                get_discovery_session_state,
                get_requester_profile,
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
                phase="results_shown" if search_response.get("has_match") else "no_result",
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
    "DiscoveryAgentRuntime",
    "DiscoveryCandidateSelection",
    "DiscoveryDecision",
    "DiscoveryRunInput",
    "DiscoveryRuntimeResult",
    "StubDiscoveryAgentRuntime",
    "create_default_discovery_agent_runtime",
]
