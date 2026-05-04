"""Bridge from the external recommendation system to the partner-search API."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping


def ensure_partner_search_skill_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    skill_root = repo_root / "local-skills" / "partner-search"
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    return skill_root


ensure_partner_search_skill_on_path()

from partner_search import load_self_profile, search_profiles  # noqa: E402


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _first_defined(*values: Any) -> Any:
    for value in values:
        if _has_value(value):
            return value
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return value


def normalize_requester_profile_for_subscription(
    profile: dict[str, Any] | None,
    *,
    fallback_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Convert a synced profile row back into the persona-style keys used by refresh."""

    if not profile and not fallback_profile:
        return None

    profile = dict(profile or {})
    normalized = dict(fallback_profile or {})
    normalized.update(profile)

    matcher_preferences = _as_mapping(profile.get("matcher_preferences"))
    matcher_risks = _as_mapping(profile.get("matcher_risks"))

    persona_fields = {
        "self_gender": profile.get("gender"),
        "self_age": profile.get("age"),
        "self_city": profile.get("city"),
        "self_district": profile.get("district"),
        "self_height": profile.get("height"),
        "self_education": profile.get("education"),
        "self_job": profile.get("job"),
        "self_marital_status": profile.get("marital_status"),
        "self_has_children": profile.get("has_children"),
        "self_children_count": profile.get("children_count"),
        "self_children_living_with_self": profile.get("children_living_with_self"),
        "self_smoking": profile.get("smoking"),
        "self_drinking": profile.get("drinking"),
        "self_relationship_goal": profile.get("relationship_goal"),
        "target_gender": _first_defined(
            matcher_preferences.get("target_gender"),
            profile.get("target_gender"),
        ),
        "target_age_min": _first_defined(
            profile.get("preferred_age_min"),
            matcher_preferences.get("target_age_min"),
            profile.get("target_age_min"),
        ),
        "target_age_max": _first_defined(
            profile.get("preferred_age_max"),
            matcher_preferences.get("target_age_max"),
            profile.get("target_age_max"),
        ),
        "target_cities": _first_defined(
            matcher_preferences.get("target_cities"),
            profile.get("preferred_cities"),
            profile.get("target_cities"),
        ),
        "target_height_min": _first_defined(
            profile.get("preferred_height_min"),
            matcher_preferences.get("target_height_min"),
            profile.get("target_height_min"),
        ),
        "target_height_max": _first_defined(
            profile.get("preferred_height_max"),
            matcher_preferences.get("target_height_max"),
            profile.get("target_height_max"),
        ),
        "target_education_min": _first_defined(
            profile.get("preferred_education_min"),
            matcher_preferences.get("target_education_min"),
            profile.get("target_education_min"),
        ),
        "target_income_min_wan": _first_defined(
            profile.get("preferred_income_min_wan"),
            matcher_preferences.get("target_income_min_wan"),
            profile.get("target_income_min_wan"),
        ),
        "target_income_max_wan": _first_defined(
            profile.get("preferred_income_max_wan"),
            matcher_preferences.get("target_income_max_wan"),
            profile.get("target_income_max_wan"),
        ),
        "target_marital_statuses": _first_defined(
            matcher_preferences.get("target_marital_statuses"),
            profile.get("accept_marital_status"),
            profile.get("target_marital_statuses"),
        ),
        "target_marital_status_strength": _first_defined(
            matcher_preferences.get("target_marital_status_strength"),
            profile.get("accept_marital_status_strength"),
            profile.get("target_marital_status_strength"),
        ),
        "target_accept_partner_children": _first_defined(
            matcher_preferences.get("target_accept_partner_children"),
            profile.get("accept_partner_children"),
            profile.get("target_accept_partner_children"),
        ),
        "target_accept_partner_children_strength": _first_defined(
            matcher_preferences.get("target_accept_partner_children_strength"),
            profile.get("accept_partner_children_strength"),
            profile.get("target_accept_partner_children_strength"),
        ),
        "target_accept_long_distance": _first_defined(
            matcher_preferences.get("target_accept_long_distance"),
            profile.get("accept_long_distance"),
            profile.get("long_distance"),
            profile.get("target_accept_long_distance"),
        ),
        "target_location_semantics": _first_defined(
            matcher_preferences.get("target_location_semantics"),
            profile.get("location_preference_semantics"),
            profile.get("target_location_semantics"),
        ),
        "target_requires_partner_accept_my_children": _first_defined(
            matcher_preferences.get("target_requires_partner_accept_my_children"),
            profile.get("requires_partner_accept_my_children"),
            profile.get("target_requires_partner_accept_my_children"),
        ),
        "target_want_children": _first_defined(
            matcher_preferences.get("target_want_children"),
            profile.get("target_want_children"),
        ),
        "target_marriage_timeline": _first_defined(
            matcher_preferences.get("target_marriage_timeline"),
            profile.get("target_marriage_timeline"),
        ),
        "must_have_tags": _first_defined(
            matcher_preferences.get("must_have_tags"),
            profile.get("must_have_tags"),
        ),
        "must_not_have_tags": _first_defined(
            matcher_risks.get("must_not_have_tags"),
            profile.get("must_not_have_tags"),
        ),
        "preferred_traits": _first_defined(
            matcher_preferences.get("preferred_traits"),
            profile.get("preferred_traits"),
        ),
        "disliked_traits": _first_defined(
            matcher_risks.get("disliked_traits"),
            profile.get("disliked_traits"),
        ),
    }
    for key, value in persona_fields.items():
        if _has_value(value):
            normalized[key] = value

    return _json_safe_value(normalized)


def run_partner_search(**kwargs: Any) -> dict[str, Any]:
    """Execute partner-search through its stable Python API."""

    return search_profiles(**kwargs)


def load_requester_profile(
    *,
    source: str,
    self_id: int | None,
    table_name: str | None = None,
    self_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the latest requester profile row for persona-driven refreshes."""

    if self_id is None:
        return self_profile

    try:
        profile = load_self_profile(
            source=source,
            self_id=self_id,
            table_name=table_name,
        )
        return normalize_requester_profile_for_subscription(
            profile,
            fallback_profile=self_profile,
        )
    except Exception:
        return normalize_requester_profile_for_subscription(
            self_profile,
            fallback_profile=self_profile,
        )
