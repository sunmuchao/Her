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
    """将性取向映射到目标性别

    支持多种输入格式：
    - 英文标准值：like_male, like_female
    - 中文标准值：异性恋, 同性恋, 喜欢男性, 喜欢女性, 恋男, 恋女
    - 性别直接值：男, 女（表示喜欢该性别）

    返回值：
    - male：目标性别为男性
    - female：目标性别为女性
    - None：无法推导
    """
    raw = str(orientation or "").strip().lower()

    # 英文标准值
    if raw == "like_male":
        return "male"
    if raw == "like_female":
        return "female"

    # 中文标准值
    if raw in ["异性恋", "heterosexual"]:
        # 异性恋：需要根据用户自己的性别推导目标性别
        # 但这里只有orientation参数，无法推导，返回None
        return None
    if raw in ["同性恋", "homosexual", "gay", "lesbian"]:
        # 同性恋：喜欢和自己性别相同的人
        # 同样需要用户自己的性别，返回None
        return None

    # 中文直接表达（喜欢某性别）
    if raw in ["喜欢男性", "恋男", "喜欢男", "取向男"]:
        return "male"
    if raw in ["喜欢女性", "恋女", "喜欢女", "取向女"]:
        return "female"

    # 性别直接值（表示喜欢该性别）
    if raw in ["男", "male", "m"]:
        return "male"
    if raw in ["女", "female", "f"]:
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
    """格式化criteria对象为显示标签列表

    新增功能：扩展显示详细条件（身高、学历、婚况、孩子、异地等）
    标签数量限制：从6个增加到12个

    Args:
        criteria: 搜索条件对象，包含age_min、age_max、height_min、height_max等字段

    Returns:
        格式化后的标签列表，最多12个标签
    """
    labels: list[str] = []

    # 1. 城市（核心字段）
    cities = criteria.get("cities")
    if isinstance(cities, list):
        labels.extend(str(item).strip() for item in cities if str(item or "").strip())
    elif str(cities or "").strip():
        labels.append(str(cities).strip())

    # 2. 性别（核心字段）
    gender = str(criteria.get("gender") or "").strip()
    if gender:
        labels.append(gender_display_label(gender))

    # 3. 年龄范围（核心字段）
    age_min = criteria.get("age_min")
    age_max = criteria.get("age_max")
    if age_min is not None and age_max is not None:
        labels.append(f"{age_min}-{age_max}岁")
    elif age_min is not None:
        labels.append(f"{age_min}岁以上")
    elif age_max is not None:
        labels.append(f"{age_max}岁以内")

    # 4. 关系目标（核心字段）
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

    # ========== 新增详细字段提取 ==========

    # 5. 身高范围（新增）
    height_min = criteria.get("height_min")
    height_max = criteria.get("height_max")
    if height_min is not None and height_max is not None:
        labels.append(f"身高{height_min}-{height_max}cm")
    elif height_min is not None:
        labels.append(f"身高{height_min}cm以上")
    elif height_max is not None:
        labels.append(f"身高{height_max}cm以下")

    # 6. 学历要求（新增）
    education_min = criteria.get("education_min")
    if education_min:
        # 学历格式化：本科、硕士、博士等
        education_label = str(education_min).strip()
        labels.append(f"学历{education_label}")

    # 7. 婚况要求（新增）
    marital_statuses = criteria.get("marital_statuses")
    if isinstance(marital_statuses, list) and marital_statuses:
        # 婚况格式化：未婚、离异等
        marital_label = normalize_marital_status(marital_statuses[0]) or str(marital_statuses[0]).strip()
        labels.append(f"婚况{marital_label}")
    elif str(marital_statuses or "").strip():
        marital_label = normalize_marital_status(str(marital_statuses)) or str(marital_statuses).strip()
        labels.append(f"婚况{marital_label}")

    # 8. 孩子要求（新增）
    accept_children = criteria.get("accept_partner_children")
    if accept_children:
        # 孩子格式化：不接受、接受、可协商等
        children_label = str(accept_children).strip()
        labels.append(f"孩子{children_label}")

    # 9. 异地要求（新增）
    # 注意：criteria对象中字段名可能为long_distance或accept_long_distance
    accept_long_distance = criteria.get("long_distance") or criteria.get("accept_long_distance")
    if accept_long_distance:
        # 异地格式化：可协商、不接受、接受等
        distance_label = str(accept_long_distance).strip()
        labels.append(f"异地{distance_label}")

    # ========== 新增字段提取结束 ==========

    # 10. must_have（其他条件）
    must_have = criteria.get("must_have")
    if isinstance(must_have, list):
        labels.extend(str(item).strip() for item in must_have if str(item or "").strip())
    elif str(must_have or "").strip():
        labels.append(str(must_have).strip())

    # 去重逻辑
    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)

    # ⚠️ 调整标签数量限制：从6个增加到12个
    # 原因：新增了身高、学历、婚况、孩子、异地等5个字段，需要更多显示空间
    return deduped[:12]


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
