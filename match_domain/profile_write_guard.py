"""Split persona/profile patches and gate profiles-table writes."""

from __future__ import annotations

from typing import Any, Mapping

from .collected_profile import COLLECTED_PERSONA_FIELDS, PROFILE_FACT_PROFILE_COLUMNS

# Persona keys that mirror formal profile facts (require user confirmation before profiles UPDATE).
# 注意：已删除硬条件字段映射，这些字段应该只在 profiles 表中
_PERSONA_SELF_TO_PROFILE: dict[str, str] = {
    # 软偏好字段映射（如果需要）
    # 硬条件字段（gender, age, city, height, education, job, marital_status, has_children, smoking, drinking, relationship_goal）
    # 已删除，应该直接从 profiles 表读取
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

# Agent Native: 从"白名单准入"改为"黑名单排除"
# 明确排除的字段（内部状态、元数据、系统字段）
_EXCLUDED_SEARCH_KEYS = frozenset(
    {
        # 内部标识符（不参与搜索）
        "session_id",
        "requester_id",
        "profile_id",
        "user_key",
        "self_id",
        # 时间戳（不参与搜索）
        "created_at",
        "updated_at",
        "last_search_at",
        "last_sync_at",
        # 内部状态（不参与搜索）
        "internal_state",
        "working_criteria",
        "last_search_result_count",
        "last_search_has_match",
        "last_search_error_code",
        "last_search_error_message",
        "last_persona_sync_at",
        "last_persona_sync_fields",
        "profile_prompts_for_timeline",
        # 工具返回元数据（不参与搜索）
        "request_meta",
        "personality_trace",
        "user_personality_traits",
        # 分页/限制参数（单独处理，不属于筛选条件）
        "limit",
        "offset",
        "page",
    }
)

# 保留原有白名单用于类型推断（判断哪些字段是列表类型）
# 但不再作为"准入"判断，仅用于参数类型处理
_LIST_VALUE_CRITERIA_KEYS = frozenset(
    {
        "cities",
        "districts",
        "settlement_cities",
        "relationship_goals",
        "must_have",
        "must_not_have",
        "prefer",
        "housing_statuses",
        "car_statuses",
        "marital_statuses",
        "marriage_timelines",
        "personality_traits",  # 新增：性格偏好是列表类型
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


# 可量化字段白名单：只有这些字段才能写入 persona_part（结构化数据）
#
# 判断标准：
# 1. 数值范围：明确的数字范围（如年龄26-30、身高170-180）
# 2. 枚举类型：明确的有限选项（如MBTI 16种、婚姻状态3种）
# 3. 布尔值：明确的是/否（如是否接受异地）
# 4. 地理位置：明确的城市/区县（如北京、朝阳区）
# 5. 学历等级：明确的学历层次（如硕士、本科）
# 6. 标签：明确的标签体系（如必须有的标签、必须没有的标签）
#
# 注意：主观描述（性格温柔、重视家庭）不属于可量化字段
# 这些字段不在实时对话 patch 中，需要 LLM 会话结束后提炼
#
# 修正：区分可量化的"搜索条件"和"用户特质"
# 注意：smoking, drinking, relationship_goal, has_children 等硬条件在 profiles 表中
QUANTIFIABLE_FIELDS = frozenset({
    # 数值范围（明确的数字范围）
    "age", "age_min", "age_max",
    "height", "height_min", "height_max",
    "income", "income_min", "income_max",

    # 枚举类型（明确的有限选项 - 软偏好）
    "mbti_type", "personality_type",

    # 布尔值（明确的是/否 - 软偏好）
    "accept_partner_children", "accept_long_distance",

    # 地理位置（明确的城市/区县）
    "cities", "districts", "city", "district",

    # 学历等级（明确的学历层次）
    "education", "education_min",

    # 标签（明确的标签体系）
    "must_have_tags", "must_not_have_tags",
})

# 可量化的"搜索条件"字段（应该分流到 search_part）
# 这些字段用于搜索筛选，不是用户特质
QUANTIFIABLE_SEARCH_FIELDS = frozenset({
    # 数值范围（搜索条件）
    "age_min", "age_max",
    "height_min", "height_max",
    "income_min", "income_max",
    "education_min",

    # 地理位置（搜索条件）
    "cities", "districts", "city", "district",
})

# 可量化的"用户特质"字段（应该分流到 persona_part）
# 这些字段描述用户自身特征，不是搜索条件
# 注意：smoking, drinking, relationship_goal 是硬条件，应该在 profiles 表中
QUANTIFIABLE_USER_TRAIT_FIELDS = frozenset({
    # 枚举类型（用户特质 - 软偏好）
    "mbti_type", "personality_type",

    # 布尔值（用户特质 - 软偏好）
    "accept_partner_children", "accept_long_distance",

    # 标签（用户特质）
    "must_have_tags", "must_not_have_tags",
})


def profile_field_label(field_name: str) -> str:
    return _PROFILE_FIELD_LABELS.get(str(field_name or "").strip(), str(field_name or "").strip())


def is_search_criteria_key(key: str) -> bool:
    """Agent Native: 除明确排除的字段外，其他参数都允许透传到搜索

    原理：
    - 从"只认白名单"改为"只拒绝黑名单"
    - Agent 传入的任意参数（包括 personality_traits）都能透传到查询构建器
    - 软约束筛选逻辑在 Prompt 中表达，不在代码中硬编码
    """
    cleaned_key = str(key or "").strip()
    if not cleaned_key:
        return False
    # 拒绝黑名单中的字段
    if cleaned_key in _EXCLUDED_SEARCH_KEYS:
        return False
    # 拒绝内部字段（以 _ 开头）
    if cleaned_key.startswith("_"):
        return False
    # 其他字段都允许透传
    return True


def split_persona_patch(patch: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (profile_patch, persona_patch, search_criteria_patch).

    分流优先级（修正后）：
    1. 特殊标识符（profile_id, user_key） → persona_part
    2. profile 字段（_WRITABLE_PROFILE_COLUMNS） → profile_part
    3. self_ 字段映射（_PERSONA_SELF_TO_PROFILE） → profile_part
    4. 可量化的搜索条件（QUANTIFIABLE_SEARCH_FIELDS） → search_part ← 修正
    5. 可量化的用户特质（QUANTIFIABLE_USER_TRAIT_FIELDS） → persona_part ← 修正
    6. 其他搜索条件字段（黑名单排除） → search_part
    7. persona 字段（COLLECTED_PERSONA_FIELDS） → persona_part
    8. 兜底 → persona_part

    关键修正：
    - 区分"可量化的搜索条件"（cities, age_min）和"可量化的用户特质"（mbti_type, smoking）
    - 搜索条件 → search_part（用于筛选候选人）
    - 用户特质 → persona_part（描述用户自身特征）
    """

    profile_part: dict[str, Any] = {}
    persona_part: dict[str, Any] = {}
    search_part: dict[str, Any] = {}

    for raw_key, value in dict(patch or {}).items():
        key = str(raw_key or "").strip()
        if not key or value in (None, "", [], {}):
            continue

        # 第1层：特殊标识符
        if key in {"profile_id", "user_key"}:
            persona_part[key] = value
            continue

        # 第2层：profile 字段（硬约束）
        if key in _WRITABLE_PROFILE_COLUMNS:
            profile_part[key] = value
            continue

        # 第3层：self_ 字段映射（硬约束）
        if key in _PERSONA_SELF_TO_PROFILE:
            profile_part[_PERSONA_SELF_TO_PROFILE[key]] = value
            continue

        # 第4层：可量化的搜索条件（优先分流到 search_part）← 修正
        if key in QUANTIFIABLE_SEARCH_FIELDS:
            search_part[key] = value  # 搜索条件 → search_part
            continue

        # 第5层：可量化的用户特质（优先分流到 persona_part）← 修正
        if key in QUANTIFIABLE_USER_TRAIT_FIELDS:
            persona_part[key] = value  # 用户特质 → persona_part
            continue

        # 第6层：其他搜索条件字段（黑名单排除）
        if is_search_criteria_key(key):
            search_part[key] = value
            continue

        # 第7层：persona 字段
        if key in COLLECTED_PERSONA_FIELDS or key.startswith("target_") or key.startswith("self_"):
            persona_part[key] = value
            continue

        # 第8层：兜底
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

    # ✅ 修复：如果用户传了 cities，就清理旧的 city 字段
    if "cities" in incoming:
        working.pop("city", None)

    for key, value in incoming.items():
        if is_search_criteria_key(key) and value not in (None, "", [], {}):
            if key == "city" and "cities" not in incoming:
                working["cities"] = [value] if not isinstance(value, list) else value
            else:
                working[key] = value

    merged = dict(working)
    merged.update(incoming)

    # ✅ 修复：确保最终结果中 city 字段被清理
    if "cities" in merged:
        merged.pop("city", None)

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
    "QUANTIFIABLE_FIELDS",  # 新增导出：可量化字段白名单
]
