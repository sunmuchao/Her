"""Deprecated profiles table columns (§13.1.2 phase-4 cleanup)."""

from __future__ import annotations

# Persona field ← legacy profile column (migrate script mapping).
PROFILE_PREFERENCE_TO_PERSONA: dict[str, str] = {
    "preferred_age_min": "target_age_min",
    "preferred_age_max": "target_age_max",
    "preferred_cities": "target_cities",
    "preferred_height_min": "target_height_min",
    "preferred_height_max": "target_height_max",
    "preferred_education_min": "target_education_min",
    "preferred_income_min_wan": "target_income_min_wan",
    "preferred_income_max_wan": "target_income_max_wan",
    "accept_marital_status_strength": "target_marital_status_strength",
    "accept_partner_children_strength": "target_accept_partner_children_strength",
    "location_preference_semantics": "target_location_semantics",
    "requires_partner_accept_my_children": "target_requires_partner_accept_my_children",
}

DEPRECATED_PROFILE_COLUMNS: tuple[str, ...] = (
    *PROFILE_PREFERENCE_TO_PERSONA.keys(),
    "preferred_age_strictness",
    "preferred_height_strictness",
    "preferred_education_strictness",
    "preferred_income_strictness",
    "preferred_traits",
    "accept_marital_status",
    "accept_partner_children",
    "accept_partner_children_semantics",
    "accept_marital_status_semantics",
    "matcher_traits_json",
    "matcher_preferences_json",
    "matcher_risks_json",
    "matcher_summary_internal",
)

# Reciprocal checks read legacy profile keys; map from collected persona fields.
COLLECTED_TO_RECIPROCAL_PROFILE_ALIASES: dict[str, str] = {
    **{profile_col: persona_col for profile_col, persona_col in PROFILE_PREFERENCE_TO_PERSONA.items()},
    "accept_marital_status": "target_marital_statuses",
    "accept_partner_children": "target_accept_partner_children",
    "accept_long_distance": "target_accept_long_distance",
    "long_distance": "target_accept_long_distance",
}

__all__ = [
    "COLLECTED_TO_RECIPROCAL_PROFILE_ALIASES",
    "DEPRECATED_PROFILE_COLUMNS",
    "PROFILE_PREFERENCE_TO_PERSONA",
]
