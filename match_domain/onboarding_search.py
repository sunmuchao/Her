"""Onboarding → profile / persona / search defaults for profile-first discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

DEFAULT_AGE_SPAN = 5
MIN_SEARCH_AGE = 18

_GENDER_ALIASES = {
    "male": "male",
    "m": "male",
    "男": "male",
    "female": "female",
    "f": "female",
    "女": "female",
}

_GENDER_DISPLAY = {
    "male": "男",
    "female": "女",
}

_RELATIONSHIP_GOAL_SEARCH_EXPANSION: dict[str, list[str]] = {
    "dating": ["dating", "认真恋爱"],
    "marriage": ["marriage", "结婚导向"],
    "friends": ["friends"],
    "认真恋爱": ["认真恋爱", "dating"],
    "结婚导向": ["结婚导向", "marriage"],
}

_RELATIONSHIP_GOAL_DISPLAY: dict[str, str] = {
    "dating": "先谈恋爱",
    "marriage": "奔着结婚",
    "friends": "找搭子",
    "认真恋爱": "认真恋爱",
    "结婚导向": "结婚导向",
    "认真相处": "认真相处",
    "long_term": "长期关系",
}


def normalize_search_gender(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return _GENDER_ALIASES.get(text)


def expand_search_gender_values(value: Any) -> list[str]:
    """All stored/searchable gender tokens that match the canonical filter value."""
    canonical = normalize_search_gender(value)
    if not canonical:
        text = str(value or "").strip()
        return [text] if text else []
    expanded: list[str] = []
    for alias, mapped in _GENDER_ALIASES.items():
        if mapped != canonical:
            continue
        for candidate in (alias, mapped):
            if candidate not in expanded:
                expanded.append(candidate)
    return expanded


def genders_match_for_search(record_gender: Any, criteria_gender: Any) -> bool:
    record_canonical = normalize_search_gender(record_gender)
    criteria_canonical = normalize_search_gender(criteria_gender)
    if not criteria_canonical:
        expected = str(criteria_gender or "").strip().lower()
        if not expected:
            return True
        return str(record_gender or "").strip().lower() == expected
    if not record_canonical:
        return False
    return record_canonical == criteria_canonical


def gender_display_label(value: Any) -> str:
    normalized = normalize_search_gender(value)
    if normalized:
        return _GENDER_DISPLAY[normalized]
    text = str(value or "").strip()
    return text


def age_from_birthday(birthday: str | None) -> int | None:
    text = str(birthday or "").strip()
    if not text:
        return None
    try:
        if len(text) >= 4 and text[:4].isdigit():
            birth_year = int(text[:4])
            return max(MIN_SEARCH_AGE, datetime.now(timezone.utc).year - birth_year)
    except ValueError:
        return None
    return None


def default_target_age_range(self_age: int | None, *, span: int = DEFAULT_AGE_SPAN) -> tuple[int | None, int | None]:
    if self_age is None:
        return None, None
    age_min = max(MIN_SEARCH_AGE, int(self_age) - span)
    age_max = max(age_min, int(self_age) + span)
    return age_min, age_max


def map_sexual_orientation_to_target_gender(orientation: Any) -> str | None:
    raw = str(orientation or "").strip().lower()
    if raw == "like_male":
        return "male"
    if raw == "like_female":
        return "female"
    return None


def normalize_marital_status(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    mapping = {
        "never_married": "未婚",
        "divorced": "离异",
        "widowed": "丧偶",
        "married": "已婚",
    }
    return mapping.get(raw, raw)


def normalize_has_children(value: Any) -> int | None:
    raw = str(value or "").strip().lower()
    if raw in {"yes", "true", "1", "有", "有孩子"}:
        return 1
    if raw in {"no", "false", "0", "无", "没有", "没有孩子"}:
        return 0
    return None


def build_onboarding_profile_fields(
    basic_info: Mapping[str, Any] | None,
    preference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    basic = dict(basic_info or {})
    pref = dict(preference or {})
    fields: dict[str, Any] = {
        "name": basic.get("name"),
        "gender": basic.get("gender"),
        "city": basic.get("location") or basic.get("city"),
        "relationship_goal": pref.get("relationship_goal") or basic.get("relationship_goal"),
        "sexual_orientation": basic.get("sexual_orientation"),
    }
    age = age_from_birthday(basic.get("birthday"))
    if age is not None:
        fields["age"] = age
    marital_status = normalize_marital_status(basic.get("marriage_status") or basic.get("marital_status"))
    if marital_status:
        fields["marital_status"] = marital_status
    has_children = normalize_has_children(basic.get("has_children"))
    if has_children is not None:
        fields["has_children"] = has_children
    return {key: value for key, value in fields.items() if value not in (None, "")}


def expand_relationship_goals_for_search(goals: list[Any]) -> list[str]:
    expanded: list[str] = []
    for goal in goals:
        text = str(goal or "").strip()
        if not text:
            continue
        if text not in expanded:
            expanded.append(text)
        aliases = _RELATIONSHIP_GOAL_SEARCH_EXPANSION.get(text.lower(), [])
        aliases = aliases or _RELATIONSHIP_GOAL_SEARCH_EXPANSION.get(text, [])
        for alias in aliases:
            if alias not in expanded:
                expanded.append(alias)
    return expanded


def build_profile_search_defaults(profile_row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Derive baseline search criteria from explicit profile facts."""
    if not profile_row:
        return {}
    patch: dict[str, Any] = {}

    target_gender = map_sexual_orientation_to_target_gender(profile_row.get("sexual_orientation"))
    if target_gender:
        patch["gender"] = target_gender

    self_age = profile_row.get("age")
    try:
        self_age = int(self_age) if self_age not in (None, "") else None
    except (TypeError, ValueError):
        self_age = None
    age_min, age_max = default_target_age_range(self_age)
    if age_min is not None:
        patch["age_min"] = age_min
    if age_max is not None:
        patch["age_max"] = age_max

    city = str(profile_row.get("city") or "").strip()
    if city:
        patch["cities"] = [city]

    rel_goal = str(profile_row.get("relationship_goal") or "").strip()
    if rel_goal:
        patch["relationship_goals"] = expand_relationship_goals_for_search([rel_goal])

    return patch


def build_onboarding_persona_patch(
    basic_info: Mapping[str, Any] | None,
    _preference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Preference-table defaults only (not duplicated profile facts)."""
    basic = dict(basic_info or {})
    patch: dict[str, Any] = {}

    city = str(basic.get("location") or basic.get("city") or "").strip()
    if city:
        patch["target_cities"] = city

    self_age = age_from_birthday(basic.get("birthday"))
    if basic.get("age") not in (None, ""):
        try:
            self_age = int(basic["age"])
        except (TypeError, ValueError):
            pass
    age_min, age_max = default_target_age_range(self_age)
    if age_min is not None:
        patch["target_age_min"] = age_min
    if age_max is not None:
        patch["target_age_max"] = age_max

    profile_id = basic.get("profile_id")
    try:
        if profile_id is not None and int(profile_id) > 0:
            patch["profile_id"] = int(profile_id)
    except (TypeError, ValueError):
        pass

    return {key: value for key, value in patch.items() if value not in (None, "", [], {})}


def relationship_goal_display_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _RELATIONSHIP_GOAL_DISPLAY.get(text, _RELATIONSHIP_GOAL_DISPLAY.get(text.lower(), text))


def format_criteria_labels(criteria: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []

    cities = criteria.get("cities")
    if isinstance(cities, list):
        labels.extend(str(item).strip() for item in cities if str(item or "").strip())
    elif str(cities or "").strip():
        labels.append(str(cities).strip())

    gender = str(criteria.get("gender") or "").strip()
    if gender:
        labels.append(gender_display_label(gender))

    age_min = criteria.get("age_min")
    age_max = criteria.get("age_max")
    if age_min is not None and age_max is not None:
        labels.append(f"{age_min}-{age_max}岁")
    elif age_min is not None:
        labels.append(f"{age_min}岁以上")
    elif age_max is not None:
        labels.append(f"{age_max}岁以内")

    goals = criteria.get("relationship_goals")
    goal_items: list[Any]
    if isinstance(goals, list):
        goal_items = goals
    elif str(goals or "").strip():
        goal_items = [goals]
    else:
        goal_items = []
    if goal_items:
        primary_label = relationship_goal_display_label(goal_items[0])
        if primary_label:
            labels.append(primary_label)

    must_have = criteria.get("must_have")
    if isinstance(must_have, list):
        labels.extend(str(item).strip() for item in must_have if str(item or "").strip())
    elif str(must_have or "").strip():
        labels.append(str(must_have).strip())

    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped[:6]


def normalize_compiled_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(criteria)
    gender = normalize_search_gender(normalized.get("gender"))
    if gender:
        normalized["gender"] = gender
    elif "gender" in normalized:
        normalized.pop("gender", None)

    goals = normalized.get("relationship_goals")
    if isinstance(goals, list) and goals:
        normalized["relationship_goals"] = expand_relationship_goals_for_search(goals)
    return normalized


__all__ = [
    "DEFAULT_AGE_SPAN",
    "MIN_SEARCH_AGE",
    "age_from_birthday",
    "build_onboarding_persona_patch",
    "build_onboarding_profile_fields",
    "build_profile_search_defaults",
    "default_target_age_range",
    "expand_relationship_goals_for_search",
    "expand_search_gender_values",
    "format_criteria_labels",
    "gender_display_label",
    "genders_match_for_search",
    "map_sexual_orientation_to_target_gender",
    "normalize_compiled_criteria",
    "normalize_has_children",
    "normalize_marital_status",
    "normalize_search_gender",
    "relationship_goal_display_label",
]
