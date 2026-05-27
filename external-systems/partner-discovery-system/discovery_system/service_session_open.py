"""Profile-first discovery session open (scheme A) without initial LLM turn."""

from __future__ import annotations

import os
from typing import Any

from .agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)

PROFILE_FIRST_OPEN_MESSAGE = (
    "我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。"
)
PROFILE_FIRST_EMPTY_MESSAGE = (
    "根据你刚填的资料，我先帮你筛了一轮，暂时没找到特别贴近的。你可以直接跟我说想怎么调整条件。"
)
PROFILE_FIRST_RESULT_TITLE = "根据你的资料，先给你看这些"
PROFILE_FIRST_SEARCH_LIMIT = 5


def discovery_create_session_mode() -> str:
    raw = (os.environ.get("HER_DISCOVERY_CREATE_SESSION_MODE") or "profile_first").strip().lower()
    if raw in {"agent", "llm", "initial_decision"}:
        return "agent"
    return "profile_first"


def criteria_labels_from_search_criteria(criteria: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    cities = criteria.get("cities")
    if isinstance(cities, list):
        labels.extend(str(item).strip() for item in cities if str(item or "").strip())
    elif str(cities or "").strip():
        labels.append(str(cities).strip())

    gender = str(criteria.get("gender") or "").strip()
    if gender:
        labels.append(gender)

    age_min = criteria.get("age_min")
    age_max = criteria.get("age_max")
    if age_min is not None and age_max is not None:
        labels.append(f"{age_min}-{age_max}岁")
    elif age_min is not None:
        labels.append(f"{age_min}岁以上")
    elif age_max is not None:
        labels.append(f"{age_max}岁以内")

    goals = criteria.get("relationship_goals")
    if isinstance(goals, list):
        labels.extend(str(item).strip() for item in goals if str(item or "").strip())
    elif str(goals or "").strip():
        labels.append(str(goals).strip())

    must_have = criteria.get("must_have")
    if isinstance(must_have, list):
        labels.extend(str(item).strip() for item in must_have if str(item or "").strip())

    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped[:6]


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


def build_profile_first_open_result(
    search_response: dict[str, Any],
    *,
    criteria_labels: list[str],
) -> DiscoveryRuntimeResult:
    selections = selected_candidates_from_search(search_response)
    has_results = bool(search_response.get("has_match")) and bool(selections)

    if has_results:
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message=PROFILE_FIRST_OPEN_MESSAGE,
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
            assistant_message=PROFILE_FIRST_EMPTY_MESSAGE,
            criteria_labels=list(criteria_labels),
            suggested_actions=default_profile_first_suggested_actions(),
            result_group_title=None,
            selected_candidates=[],
        ),
        search_response=search_response,
    )


__all__ = [
    "PROFILE_FIRST_EMPTY_MESSAGE",
    "PROFILE_FIRST_OPEN_MESSAGE",
    "PROFILE_FIRST_RESULT_TITLE",
    "PROFILE_FIRST_SEARCH_LIMIT",
    "build_profile_first_open_result",
    "criteria_labels_from_search_criteria",
    "default_profile_first_suggested_actions",
    "discovery_create_session_mode",
    "selected_candidates_from_search",
]
