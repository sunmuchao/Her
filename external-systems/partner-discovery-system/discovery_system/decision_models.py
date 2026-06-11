"""Decision data models and schema helpers for discovery runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Annotated, Any, Literal, Union

from her_env import coerce_json_object
from pydantic import AliasChoices, BaseModel, Field, model_validator


VALID_PHASES = (
    "collecting_preferences",
    "searching",
    "results_shown",
    "no_result",
)
VALID_ACTION_STYLES = ("primary", "secondary", "ghost")
VALID_STARTER_PROMPT_SLOTS = ("city_and_age", "top_preferences")
VALID_FOLLOWUP_PROMPT_SLOTS = ("age_range", "city_intent")

DiscoveryPhase = Literal[
    "collecting_preferences",
    "searching",
    "results_shown",
    "no_result",
]
DiscoveryActionStyle = Literal["primary", "secondary", "ghost"]


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
class DiscoveryToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    status: str = "succeeded"


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


class DiscoveryStarterPromptPayloadModel(BaseModel):
    kind: Literal["starter_prompt"]
    slot: Literal["city_and_age", "top_preferences"]


class DiscoveryFollowupPromptPayloadModel(BaseModel):
    kind: Literal["followup_prompt"]
    slot: Literal["age_range", "city_intent"]


class DiscoverySavedSearchOptInPayloadModel(BaseModel):
    kind: Literal["saved_search_opt_in"]


class DiscoveryRefineCandidatesPayloadModel(BaseModel):
    """
    【已废弃】原设计用于调整特定候选人，但无实际使用场景。

    废弃原因：
    1. 业务规则要求"每次换一批都追问"，不存在"不追问的换一批"场景
    2. 与 show_more_candidates 语义重叠，职责边界模糊
    3. Agent指导已统一为 show_more_candidates

    替代方案：统一使用 show_more_candidates

    保留定义是为了向后兼容（可能有旧数据中使用），但新代码不应使用。
    """
    kind: Literal["refine_candidates"]
    candidates: list[int] | None = Field(default=None, min_length=1)
    hint: str | None = Field(default=None)


class DiscoveryAddCriteriaPayloadModel(BaseModel):
    kind: Literal["add_criteria"]


class DiscoveryRefinePreferencesPayloadModel(BaseModel):
    kind: Literal["refine_preferences"]


class DiscoveryShowMoreCandidatesPayloadModel(BaseModel):
    kind: Literal["show_more_candidates"]


class DiscoveryAgePreferencePayloadModel(BaseModel):
    kind: Literal["age_preference"]
    target_gender: str | None = Field(default=None)
    age_min: int | None = Field(default=None, ge=18)
    age_max: int | None = Field(default=None, ge=18)
    age_gap_max: int | None = Field(default=None, ge=0)
    flexible: bool | None = Field(default=None)


class DiscoveryStartAssessmentPayloadModel(BaseModel):
    """开始测评动作 - 用于AI推荐MBTI等测评"""
    kind: Literal["start_assessment"]
    assessment_type: Literal["mbti", "values", "attachment"] = Field(default="mbti")


class DiscoveryRejectionFeedbackPayloadModel(BaseModel):
    """拒绝反馈动作 - 用于收集用户对候选人的不满意原因"""
    kind: Literal["rejection_feedback"]
    feedback_type: str = Field(default="", description="反馈类型，如occupation_mismatch、lifestyle_mismatch等")


# ============================================================================
# 方案A：新增两个专用工具的 Payload Models
# ============================================================================


class ReplyPayloadModel(BaseModel):
    """
    reply_to_user 工具的参数模型。

    方案A：简化参数结构，无需 JSON 字符串。
    """
    kind: Literal["reply"]
    phase: DiscoveryPhase = Field(
        default="collecting_preferences",
        description="当前阶段: collecting_preferences/searching/no_result"
    )
    assistant_message: str = Field(
        description="回复内容，口语化、简短"
    )
    suggested_actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="建议按钮列表，每个包含 label/style/kind"
    )


class ShowCandidatesPayloadModel(BaseModel):
    """
    show_candidates 工具的参数模型。

    方案A：简化参数结构，candidate_ids 为简单列表而非 JSON 对象。
    """
    kind: Literal["show"]
    phase: DiscoveryPhase = Field(
        default="results_shown",
        description="当前阶段: results_shown/no_result"
    )
    assistant_message: str = Field(
        description="介绍候选人的消息，口语化"
    )
    result_group_title: str | None = Field(
        default=None,
        description="候选人分组标题"
    )
    criteria_labels: list[str] = Field(
        default_factory=list,
        description="筛选条件标签"
    )
    selected_candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="候选人列表，每个包含 profile_id 和 reason_summary"
    )


DiscoveryActionPayloadModel = Annotated[
    Union[
        DiscoveryStarterPromptPayloadModel,
        DiscoveryFollowupPromptPayloadModel,
        DiscoverySavedSearchOptInPayloadModel,
        DiscoveryRefineCandidatesPayloadModel,
        DiscoveryAddCriteriaPayloadModel,
        DiscoveryRefinePreferencesPayloadModel,
        DiscoveryShowMoreCandidatesPayloadModel,
        DiscoveryAgePreferencePayloadModel,
        DiscoveryStartAssessmentPayloadModel,
        DiscoveryRejectionFeedbackPayloadModel,
    ],
    Field(discriminator="kind"),
]


# 方案A：工具 Payload 联合类型（用于 decision 提取）
ToolPayloadModel = Union[ReplyPayloadModel, ShowCandidatesPayloadModel]


class DiscoveryActionSuggestionModel(BaseModel):
    label: str
    style: DiscoveryActionStyle = Field(default="secondary")
    semantic_payload: DiscoveryActionPayloadModel | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_action(self) -> "DiscoveryActionSuggestionModel":
        if not str(self.label or "").strip():
            raise ValueError("suggested action label is required")
        return self


class DiscoveryCandidateSelectionModel(BaseModel):
    profile_id: int = Field(ge=1)
    reason_summary: str = Field(default="")


class DiscoveryDecisionModel(BaseModel):
    phase: DiscoveryPhase
    assistant_message: str = Field(validation_alias=AliasChoices("assistant_message", "message"))
    criteria_labels: list[str] = Field(default_factory=list)
    suggested_actions: list[DiscoveryActionSuggestionModel] = Field(default_factory=list)
    result_group_title: str | None = Field(default=None)
    selected_candidates: list[DiscoveryCandidateSelectionModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_decision(self) -> "DiscoveryDecisionModel":
        if not str(self.assistant_message or "").strip():
            raise ValueError("assistant_message is required")
        return self


# ============================================================================
# 方案C：工具参数中的 Decision Schema
# ============================================================================

class DecisionPayloadModel(BaseModel):
    """
    用于工具参数的 Decision 结构。

    方案C核心：把 DiscoveryDecisionModel 的 schema 融进工具参数，
    让模型在调用 make_decision 工具时填写完整的决策 JSON。
    """
    phase: DiscoveryPhase = Field(
        description="当前阶段: collecting_preferences(收集条件)/searching(搜索中)/results_shown(展示结果)/no_result(无结果)"
    )
    assistant_message: str = Field(
        description="回复用户的消息，保持短，像真人红娘"
    )
    criteria_labels: list[str] = Field(
        default_factory=list,
        description="筛选条件标签，如 ['苏州', '26-30岁', '女生']"
    )
    suggested_actions: list[DiscoveryActionSuggestionModel] = Field(
        default_factory=list,
        description="建议操作按钮，最多3个"
    )
    result_group_title: str | None = Field(
        default=None,
        description="候选人分组标题，如 '这三位很适合你'"
    )
    selected_candidates: list[DiscoveryCandidateSelectionModel] = Field(
        default_factory=list,
        description="候选人列表，每个包含 profile_id 和 reason_summary"
    )

    @model_validator(mode="after")
    def _validate_decision(self) -> "DecisionPayloadModel":
        if not str(self.assistant_message or "").strip():
            raise ValueError("assistant_message is required")
        return self


def _coerce_json_output(raw_output: Any) -> dict[str, Any]:
    return coerce_json_object(raw_output)


def dump_action_payload(payload: DiscoveryActionPayloadModel | None) -> dict[str, Any]:
    if payload is None:
        return {}
    return payload.model_dump(mode="json", exclude_none=True)


def to_decision(model: DiscoveryDecisionModel) -> DiscoveryDecision:
    return DiscoveryDecision(
        phase=model.phase,
        assistant_message=model.assistant_message.strip(),
        criteria_labels=[str(label).strip() for label in model.criteria_labels if str(label or "").strip()],
        suggested_actions=[
            DiscoveryActionSuggestion(
                label=action.label.strip(),
                style=action.style,
                semantic_payload=dump_action_payload(action.semantic_payload),
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


def _repair_action_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """
    修复模型返回的不完整 semantic_payload。

    常见问题：
    - followup_prompt 缺少 slot
    - starter_prompt 缺少 slot
    - 包含无效字段（如 target_profile_id）

    修复策略：补默认值 + 移除无效字段
    """
    kind = str(raw_payload.get("kind") or "").strip()
    if not kind:
        return {"kind": "show_more_candidates"}  # fallback

    # followup_prompt 缺 slot → 补默认值
    if kind == "followup_prompt":
        slot = raw_payload.get("slot")
        if slot not in ("age_range", "city_intent"):
            # 尝试从上下文推断：如果提到年龄用 age_range，否则用 city_intent
            # 无法推断时默认 age_range
            return {"kind": "followup_prompt", "slot": "age_range"}
        return {"kind": "followup_prompt", "slot": slot}

    # starter_prompt 缺 slot → 补默认值
    if kind == "starter_prompt":
        slot = raw_payload.get("slot")
        if slot not in ("city_and_age", "top_preferences"):
            return {"kind": "starter_prompt", "slot": "city_and_age"}
        return {"kind": "starter_prompt", "slot": slot}

    # rejection_feedback 可选 feedback_type
    if kind == "rejection_feedback":
        feedback_type = str(raw_payload.get("feedback_type") or "").strip()
        return {"kind": "rejection_feedback", "feedback_type": feedback_type}

    # start_assessment 可选 assessment_type
    if kind == "start_assessment":
        assessment_type = raw_payload.get("assessment_type")
        if assessment_type not in ("mbti", "values", "attachment"):
            assessment_type = "mbti"
        return {"kind": "start_assessment", "assessment_type": assessment_type}

    # suggested: Agent 自主判断意图，保持原样返回
    if kind == "suggested":
        return {"kind": "suggested"}

    # 其他 kind 直接返回（只保留 kind 字段）
    return {"kind": kind}


def repair_suggested_actions(raw_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    修复模型返回的 suggested_actions 列表。

    对每个 action 的 semantic_payload 应用修复逻辑。
    """
    repaired: list[dict[str, Any]] = []
    for action in raw_actions[:3]:  # 最多3个
        label = str(action.get("label") or "").strip()
        if not label:
            continue
        style = str(action.get("style") or "secondary").strip()
        if style not in ("primary", "secondary", "ghost"):
            style = "secondary"
        raw_payload = dict(action.get("semantic_payload") or {})
        repaired_payload = _repair_action_payload(raw_payload)
        repaired.append({
            "label": label,
            "style": style,
            "semantic_payload": repaired_payload,
        })
    return repaired


def decision_payload_to_decision(payload: DecisionPayloadModel) -> DiscoveryDecision:
    """从工具参数中的 DecisionPayloadModel 转换为 DiscoveryDecision"""
    return to_decision(DiscoveryDecisionModel(
        phase=payload.phase,
        assistant_message=payload.assistant_message,
        criteria_labels=payload.criteria_labels,
        suggested_actions=payload.suggested_actions,
        result_group_title=payload.result_group_title,
        selected_candidates=payload.selected_candidates,
    ))


def decision_payload_to_decision_with_repair(raw_payload: dict[str, Any]) -> DiscoveryDecision:
    """
    从原始 payload dict 转换为 DiscoveryDecision，带修复逻辑。

    方案A：支持 reply 和 show 两种 payload 类型。
    当模型返回的数据不符合 schema 时，尝试修复而非直接失败。
    """
    # 方案A：根据 kind 字段判断 payload 类型
    kind = str(raw_payload.get("kind") or "").strip()

    # 方案A新增：reply payload（纯回复，无候选人）
    if kind == "reply":
        raw_actions = list(raw_payload.get("suggested_actions") or [])
        repaired_actions = repair_suggested_actions(raw_actions)
        return DiscoveryDecision(
            phase=str(raw_payload.get("phase") or "collecting_preferences"),
            assistant_message=str(raw_payload.get("assistant_message") or ""),
            criteria_labels=[str(l).strip() for l in list(raw_payload.get("criteria_labels") or []) if str(l or "").strip()],
            suggested_actions=[
                DiscoveryActionSuggestion(
                    label=action["label"],
                    style=action["style"],
                    semantic_payload=action["semantic_payload"],
                )
                for action in repaired_actions
            ],
            result_group_title=None,
            selected_candidates=[],
        )

    # 方案A新增：show payload（展示候选人）
    if kind == "show":
        phase = str(raw_payload.get("phase") or "results_shown")
        # 如果有候选人，强制 phase 为 results_shown
        selected_candidates = list(raw_payload.get("selected_candidates") or [])
        if selected_candidates:
            phase = "results_shown"
        elif phase == "results_shown":
            phase = "no_result"

        return DiscoveryDecision(
            phase=phase,
            assistant_message=str(raw_payload.get("assistant_message") or ""),
            criteria_labels=[str(l).strip() for l in list(raw_payload.get("criteria_labels") or []) if str(l or "").strip()],
            suggested_actions=[],  # show_candidates 不需要 suggested_actions
            result_group_title=str(raw_payload.get("result_group_title") or "").strip() or None,
            selected_candidates=[
                DiscoveryCandidateSelection(
                    profile_id=int(c.get("profile_id") or 0),
                    reason_summary=str(c.get("reason_summary") or "").strip(),
                )
                for c in selected_candidates
                if int(c.get("profile_id") or 0) > 0
            ],
        )

    # 方案C兼容：无 kind 字段时，使用原有逻辑
    raw_actions = list(raw_payload.get("suggested_actions") or [])
    repaired_actions = repair_suggested_actions(raw_actions)

    # 构建 DecisionPayloadModel（允许验证失败时继续）
    try:
        payload = DecisionPayloadModel.model_validate({
            "phase": raw_payload.get("phase", "collecting_preferences"),
            "assistant_message": raw_payload.get("assistant_message", ""),
            "criteria_labels": raw_payload.get("criteria_labels", []),
            "suggested_actions": repaired_actions,
            "result_group_title": raw_payload.get("result_group_title"),
            "selected_candidates": raw_payload.get("selected_candidates", []),
        })
        return decision_payload_to_decision(payload)
    except Exception:
        # 验证仍然失败 → 手动构建 DiscoveryDecision
        return DiscoveryDecision(
            phase=str(raw_payload.get("phase") or "collecting_preferences"),
            assistant_message=str(raw_payload.get("assistant_message") or ""),
            criteria_labels=[str(l).strip() for l in list(raw_payload.get("criteria_labels") or []) if str(l or "").strip()],
            suggested_actions=[
                DiscoveryActionSuggestion(
                    label=action["label"],
                    style=action["style"],
                    semantic_payload=action["semantic_payload"],
                )
                for action in repaired_actions
            ],
            result_group_title=str(raw_payload.get("result_group_title") or "").strip() or None,
            selected_candidates=[
                DiscoveryCandidateSelection(
                    profile_id=int(c.get("profile_id") or 0),
                    reason_summary=str(c.get("reason_summary") or "").strip(),
                )
                for c in list(raw_payload.get("selected_candidates") or [])
                if int(c.get("profile_id") or 0) > 0
            ],
        )


# 保留原函数名作为别名（向后兼容）
_decision_payload_to_decision_with_repair = decision_payload_to_decision_with_repair


def validate_decision_output(raw_output: Any) -> DiscoveryDecision:
    parsed = DiscoveryDecisionModel.model_validate(_coerce_json_output(raw_output))
    return to_decision(parsed)


def recover_decision_from_exception(exc: Exception) -> DiscoveryDecision | None:
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
        return validate_decision_output(candidate)
    except (JSONDecodeError, TypeError, ValueError):
        return None


__all__ = [
    "DiscoveryActionPayloadModel",
    "DiscoveryActionStyle",
    "DiscoveryActionSuggestion",
    "DiscoveryActionSuggestionModel",
    "DiscoveryAgePreferencePayloadModel",
    "DiscoveryCandidateSelection",
    "DiscoveryCandidateSelectionModel",
    "DiscoveryDecision",
    "DiscoveryDecisionModel",
    "DecisionPayloadModel",  # 方案C新增
    "DiscoveryFollowupPromptPayloadModel",
    "DiscoveryPhase",
    "DiscoveryRefineCandidatesPayloadModel",
    "DiscoveryRuntimeResult",
    "DiscoverySavedSearchOptInPayloadModel",
    "DiscoveryShowMoreCandidatesPayloadModel",
    "DiscoveryStartAssessmentPayloadModel",
    "DiscoveryStarterPromptPayloadModel",
    "DiscoveryRejectionFeedbackPayloadModel",
    "DiscoveryToolCall",
    "VALID_ACTION_STYLES",
    "VALID_FOLLOWUP_PROMPT_SLOTS",
    "VALID_PHASES",
    "VALID_STARTER_PROMPT_SLOTS",
    "dump_action_payload",
    "decision_payload_to_decision",  # 方案C新增
    "decision_payload_to_decision_with_repair",  # 带修复逻辑
    "repair_suggested_actions",  # 新增
    "recover_decision_from_exception",
    "to_decision",
    "validate_decision_output",
]