"""Profile facts vs collected statements (§13.1.2)."""

from __future__ import annotations

from typing import Any, Mapping

# P0 + P0-P1 columns on profiles that may appear on the资料页.
PROFILE_FACT_PROFILE_COLUMNS = frozenset(
    {
        "id",
        "name",
        "display_name",
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
        "children_count",
        "children_living_with_self",
        "smoking",
        "drinking",
        "relationship_goal",
        "avatar_url",
        "public_display_name",
        "public_education",
        "public_job",
        "public_personality",
        "public_values",
        "public_notes",
    }
)

# Persona fields that may be persisted when source_type is explicit / profile_form.
COLLECTED_PERSONA_FIELDS = frozenset(
    {
        "display_name",
        "self_smoking",
        "self_drinking",
        "self_relationship_goal",
        "self_life_rhythm",
        "self_work_pattern",
        "self_expression_style",
        "target_gender",
        "target_age_min",
        "target_age_max",
        "target_cities",
        "target_height_min",
        "target_height_max",
        "target_education_min",
        "target_income_min_wan",
        "target_income_max_wan",
        "target_marital_statuses",
        "target_marital_status_strength",
        "target_accept_partner_children",
        "target_accept_partner_children_strength",
        "target_accept_long_distance",
        "target_location_semantics",
        "target_requires_partner_accept_my_children",
        "target_want_children",
        "target_marriage_timeline",
        "must_have_tags",
        "must_not_have_tags",
        "preferred_traits",
        "disliked_traits",
    }
)

# Must never be persisted as long-term persona/profile facts (runtime inference only).
INFERENCE_ONLY_PERSONA_FIELDS = frozenset(
    {
        "persona_summary_internal",
        "preference_summary_internal",
        "public_profile_summary_draft",
        "public_preference_summary_draft",
    }
)

PERSISTABLE_SOURCE_TYPES = frozenset({"explicit", "profile_form", "explicit_confirmation"})
INFERENCE_SOURCE_TYPES = frozenset({"strong_inference", "weak_inference"})


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def extract_profile_facts(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    return {
        key: profile[key]
        for key in PROFILE_FACT_PROFILE_COLUMNS
        if key in profile and _has_value(profile[key])
    }


def extract_collected_statements(persona: Mapping[str, Any] | None) -> dict[str, Any]:
    if not persona:
        return {}
    return {
        key: persona[key]
        for key in COLLECTED_PERSONA_FIELDS
        if key in persona and _has_value(persona[key])
    }


def filter_explicit_patch(patch: Mapping[str, Any], source_type: str) -> dict[str, Any]:
    if source_type in INFERENCE_SOURCE_TYPES:
        return {}
    if source_type not in PERSISTABLE_SOURCE_TYPES:
        return dict(patch)
    filtered: dict[str, Any] = {}
    for key, value in patch.items():
        if key in INFERENCE_ONLY_PERSONA_FIELDS:
            continue
        if key in COLLECTED_PERSONA_FIELDS or key.startswith("target_") or key.startswith("self_"):
            filtered[key] = value
        elif key in {"display_name"}:
            filtered[key] = value
    return filtered
