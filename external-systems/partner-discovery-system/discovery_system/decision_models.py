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
    kind: Literal["refine_candidates"]
    candidates: list[int] = Field(min_length=1)


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
    ],
    Field(discriminator="kind"),
]


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
    "DiscoveryFollowupPromptPayloadModel",
    "DiscoveryPhase",
    "DiscoveryRefineCandidatesPayloadModel",
    "DiscoveryRuntimeResult",
    "DiscoverySavedSearchOptInPayloadModel",
    "DiscoveryShowMoreCandidatesPayloadModel",
    "DiscoveryStarterPromptPayloadModel",
    "DiscoveryToolCall",
    "VALID_ACTION_STYLES",
    "VALID_FOLLOWUP_PROMPT_SLOTS",
    "VALID_PHASES",
    "VALID_STARTER_PROMPT_SLOTS",
    "dump_action_payload",
    "recover_decision_from_exception",
    "to_decision",
    "validate_decision_output",
]
