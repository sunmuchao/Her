"""Split persona/profile patches and gate profiles-table writes."""

from __future__ import annotations

from typing import Any, Mapping

from .collected_profile import COLLECTED_PERSONA_FIELDS, PROFILE_FACT_PROFILE_COLUMNS

# Persona keys that mirror formal profile facts (require user confirmation before profiles UPDATE).
_PERSONA_SELF_TO_PROFILE: dict[str, str] = {
    "self_gender": "gender",
    "self_age": "age",
    "self_city": "city",
    "self_district": "district",
    "self_height": "height",
    "self_education": "education",
    "self_job": "job",
    "self_marital_status": "marital_status",
    "self_has_children": "has_children",
    "self_children_count": "children_count",
    "self_children_living_with_self": "children_living_with_self",
    "self_smoking": "smoking",
    "self_drinking": "drinking",
    "self_relationship_goal": "relationship_goal",
    "display_name": "name",
}

_WRITABLE_PROFILE_COLUMNS = frozenset(
    PROFILE_FACT_PROFILE_COLUMNS
    - {
        "id",
        "avatar_url",
        "public_display_name",
        "public_education",
        "public_job",
        "public_personality",
        "public_values",
        "public_notes",
    }
)

_SEARCH_CRITERIA_KEYS = frozenset(
    {
        "gender",
        "age_min",
        "age_max",
        "cities",
        "city",
        "districts",
        "settlement_cities",
        "relationship_goals",
        "relationship_goal",
        "must_have",
        "must_not_have",
        "prefer",
        "height_min",
        "height_max",
        "smoking",
        "drinking",
        "long_distance",
        "housing_statuses",
        "car_statuses",
        "marital_statuses",
        "want_children",
        "accept_partner_children",
        "marriage_timelines",
        "photo_count_min",
        "active_within_days",
        "verified_level_min",
    }
)

_PROFILE_FIELD_LABELS: dict[str, str] = {
    "name": "姓名",
    "gender": "性别",
    "sexual_orientation": "性取向",
    "age": "年龄",
    "city": "所在城市",
    "district": "区县",
    "height": "身高",
    "education": "学历",
    "job": "职业",
    "income_range": "收入",
    "marital_status": "婚姻状况",
    "has_children": "是否有孩子",
    "children_count": "孩子数量",
    "children_living_with_self": "孩子是否同住",
    "smoking": "抽烟",
    "drinking": "喝酒",
    "relationship_goal": "恋爱目标",
}


def profile_field_label(field_name: str) -> str:
    return _PROFILE_FIELD_LABELS.get(str(field_name or "").strip(), str(field_name or "").strip())


def is_search_criteria_key(key: str) -> bool:
    return str(key or "").strip() in _SEARCH_CRITERIA_KEYS


def split_persona_patch(patch: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (profile_patch, persona_patch, search_criteria_patch)."""

    profile_part: dict[str, Any] = {}
    persona_part: dict[str, Any] = {}
    search_part: dict[str, Any] = {}

    for raw_key, value in dict(patch or {}).items():
        key = str(raw_key or "").strip()
        if not key or value in (None, "", [], {}):
            continue
        if key in {"profile_id", "user_key"}:
            persona_part[key] = value
            continue
        if key in _WRITABLE_PROFILE_COLUMNS:
            profile_part[key] = value
            continue
        if key in _PERSONA_SELF_TO_PROFILE:
            profile_part[_PERSONA_SELF_TO_PROFILE[key]] = value
            continue
        if is_search_criteria_key(key):
            search_part[key] = value
            continue
        if key in COLLECTED_PERSONA_FIELDS or key.startswith("target_") or key.startswith("self_"):
            persona_part[key] = value
            continue
        persona_part[key] = value

    return profile_part, persona_part, search_part


def build_profile_change_rows(
    *,
    current_profile: Mapping[str, Any] | None,
    proposed_patch: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = dict(current_profile or {})
    for field, new_value in dict(proposed_patch).items():
        old_value = current.get(field)
        if old_value == new_value:
            continue
        rows.append(
            {
                "field": field,
                "label": profile_field_label(field),
                "from": old_value,
                "to": new_value,
            }
        )
    return rows


def merge_working_criteria(
    session_state: Mapping[str, Any] | None,
    criteria: Mapping[str, Any] | None,
) -> dict[str, Any]:
    working = dict((session_state or {}).get("working_criteria") or {})
    incoming = dict(criteria or {})
    for key, value in incoming.items():
        if is_search_criteria_key(key) and value not in (None, "", [], {}):
            if key == "city" and "cities" not in incoming:
                working["cities"] = [value] if not isinstance(value, list) else value
            else:
                working[key] = value
    merged = dict(working)
    merged.update(incoming)
    if "city" in merged and "cities" not in merged:
        city = merged.pop("city", None)
        if city not in (None, "", [], {}):
            merged["cities"] = [city] if not isinstance(city, list) else city
    return merged


__all__ = [
    "build_profile_change_rows",
    "is_search_criteria_key",
    "merge_working_criteria",
    "profile_field_label",
    "split_persona_patch",
]
