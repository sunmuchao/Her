"""Sanitize mixed client self_profile payloads for partner_search (§13.1.2)."""

from __future__ import annotations

from typing import Any, Mapping

from profile_service import get_profile

from .criteria_compiler import SCENE_SAVED_SEARCH, compile_effective_criteria
from .persona_loader import load_persona_by_profile_id

# Legacy profile columns that must not be supplied by clients on self_profile.
DEPRECATED_SELF_PROFILE_KEYS = frozenset(
    {
        "preferred_age_min",
        "preferred_age_max",
        "preferred_cities",
        "preferred_height_min",
        "preferred_height_max",
        "preferred_education_min",
        "preferred_education_strictness",
        "preferred_income_min_wan",
        "preferred_income_max_wan",
        "preferred_income_strictness",
        "preferred_age_strictness",
        "preferred_height_strictness",
        "preferred_traits",
        "accept_marital_status",
        "accept_marital_status_strength",
        "accept_marital_status_semantics",
        "accept_partner_children",
        "accept_partner_children_strength",
        "accept_partner_children_semantics",
        "location_preference_semantics",
        "requires_partner_accept_my_children",
        "long_distance",
        "accept_long_distance",
        "matcher_traits_json",
        "matcher_preferences_json",
        "matcher_risks_json",
        "matcher_summary_internal",
        "matcher_preferences",
        "matcher_risks",
        "matcher_traits",
    }
)

# Collected persona keys belong in compile criteria, not raw self_profile from clients.
MIXED_PERSONA_KEYS_ON_SELF_PROFILE = frozenset(
    {
        key
        for key in (
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
        )
    }
)


def strip_mixed_self_profile_fields(
    self_profile: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    if not self_profile:
        return {}, []
    cleaned = dict(self_profile)
    stripped: list[str] = []
    for key in list(cleaned.keys()):
        if key in DEPRECATED_SELF_PROFILE_KEYS or key in MIXED_PERSONA_KEYS_ON_SELF_PROFILE:
            stripped.append(key)
            cleaned.pop(key, None)
    return cleaned, stripped


def prepare_gateway_search_body(
    body: Mapping[str, Any],
    *,
    profile_source_dsn: str,
    profile_table_name: str,
) -> dict[str, Any]:
    """Return partner_search kwargs plus optional deprecation metadata."""
    raw_self_profile = body.get("self_profile")
    self_id = body.get("self_id")
    compile_self = bool(body.get("compile_self", True))
    stripped_keys: list[str] = []

    cleaned_self_profile, stripped = strip_mixed_self_profile_fields(
        raw_self_profile if isinstance(raw_self_profile, Mapping) else None
    )
    stripped_keys.extend(stripped)

    criteria = dict(body.get("criteria") or {})
    compiled_self_profile = cleaned_self_profile

    if compile_self and self_id not in (None, ""):
        profile_row: dict[str, Any] | None = None
        try:
            profile_row = get_profile(
                source_dsn=profile_source_dsn,
                source_table_name=profile_table_name,
                profile_id=int(self_id),
            )
        except ValueError:
            profile_row = None
        persona_row = load_persona_by_profile_id(
            source=profile_source_dsn,
            profile_id=int(self_id),
        )
        if profile_row or persona_row:
            compiled = compile_effective_criteria(
                scene=SCENE_SAVED_SEARCH,
                profile_row=profile_row,
                persona_row=persona_row,
                base_criteria=criteria,
                fallback_self_profile=cleaned_self_profile or None,
            )
            criteria = compiled.criteria
            compiled_self_profile = compiled.self_profile
            if stripped:
                stripped_keys = sorted(set(stripped_keys))

    search_kwargs = {
        "source": body.get("source") or body.get("sources"),
        "criteria": criteria,
        "self_profile": compiled_self_profile or None,
        "self_id": self_id,
        "table_name": body.get("table_name"),
        "photos_table_name": body.get("photos_table_name"),
        "limit": int(body.get("limit", 10)),
        "photo_preview_count": int(body.get("photo_preview_count", 0)),
        "include_source": body.get("include_source"),
        "include_text": body.get("include_text"),
        "include_moderation_blocked": body.get("include_moderation_blocked"),
    }

    deprecation: dict[str, Any] | None = None
    if stripped_keys:
        deprecation = {
            "self_profile_fields_removed": stripped_keys,
            "message": (
                "Mixed profile/persona keys on self_profile are deprecated. "
                "Use compile_self=true with self_id, or pass criteria compiled from collected statements."
            ),
            "read_apis": {
                "profile_facts": "/v1/profile/me",
                "collected_statements": "/v1/persona/collected",
            },
        }

    return {"search_kwargs": search_kwargs, "deprecation": deprecation}


__all__ = [
    "DEPRECATED_SELF_PROFILE_KEYS",
    "MIXED_PERSONA_KEYS_ON_SELF_PROFILE",
    "prepare_gateway_search_body",
    "strip_mixed_self_profile_fields",
]
