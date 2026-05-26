"""Backward-compatible re-exports; canonical implementation is match_domain.criteria_compiler."""

from __future__ import annotations

from typing import Any, Mapping

from match_domain.criteria_compiler import (
    CompiledCriteria,
    SCENE_DISCOVERY_SEARCH,
    SCENE_RECOMMENDATION_REFRESH,
    SCENE_SAVED_SEARCH,
    build_discovery_search_request,
    build_effective_search_request,
    build_initial_request,
    build_subscription_overrides,
    compile_effective_criteria as _compile_effective_criteria,
)

__all__ = [
    "CompiledCriteria",
    "SCENE_DISCOVERY_SEARCH",
    "SCENE_RECOMMENDATION_REFRESH",
    "SCENE_SAVED_SEARCH",
    "build_discovery_search_request",
    "build_effective_search_request",
    "build_initial_request",
    "build_subscription_overrides",
    "compile_effective_criteria",
]


def compile_effective_criteria(
    subscription: Mapping[str, Any],
    persona_profile: Mapping[str, Any] | None = None,
    *,
    profile_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    compiled = _compile_effective_criteria(
        scene=SCENE_RECOMMENDATION_REFRESH,
        profile_row=profile_row,
        persona_row=persona_profile,
        subscription=subscription,
        fallback_self_profile=persona_profile,
    )
    return compiled.criteria
