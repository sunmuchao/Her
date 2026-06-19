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
        "sexual_orientation",
        "age",
        "city",
        "district",
        "hometown_city",  # 新增：籍贯/家乡城市
        "height",
        "weight",  # 新增：体重（kg）
        "education",
        "job",
        "income_range",
        "has_house",  # 新增：房产情况
        "has_car",  # 新增：车产情况
        "marital_status",
        "has_children",
        "children_count",
        "children_living_with_self",
        "religion",  # 新增：宗教信仰
        "is_only_child",  # 新增：是否独生子女
        "smoking",
        "drinking",
        "relationship_goal",
        "target_gender",  # 新增：期望对象性别
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
# 注意：只保留可量化字段（数值范围、枚举类型、布尔值、地理位置编码、学历编码）
COLLECTED_PERSONA_FIELDS = frozenset(
    {
        "display_name",
        # 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style
        # target_gender 已移动到 profiles 表（硬条件）
        "target_age_min",
        "target_age_max",
        "target_cities",
        "target_cities_adcodes",  # 新增：目标城市编码列表（快速范围搜索）
        "target_districts_adcodes",  # 新增：目标区县编码列表（精准商圈匹配）
        "target_height_min",
        "target_height_max",
        "target_weight_min",  # 新增：目标体重下限
        "target_weight_max",  # 新增：目标体重上限
        "target_education_min",  # 保留：学历字符串（兼容）
        "target_education_min_code",  # 新增：学历编码（1-专科，2-本科，3-硕士，4-博士）
        "target_income_min_wan",
        "target_income_max_wan",
        "target_hometown_cities",  # 新增：期望对方家乡列表
        "target_hometown_cities_adcodes",  # 新增：期望对方家乡编码列表（精准匹配）
        "target_house_requirement",  # 新增：对方房产要求
        "target_car_requirement",  # 新增：对方车产要求
        "target_marital_statuses",
        "target_marital_status_strength",
        "target_accept_partner_children",
        "target_accept_partner_children_strength",
        "target_accept_long_distance",
        "target_location_semantics",
        "target_smoke_acceptance",  # 新增：对方抽烟接受度
        "target_drink_acceptance",  # 新增：对方喝酒接受度
        "target_requires_partner_accept_my_children",
        "target_want_children",
        "target_marriage_timeline",
        # must_have_tags 和 must_not_have_tags 已删除
        # 不可量化字段已删除：preferred_traits, disliked_traits（性格特质偏好）
    }
)

# Must never be persisted as long-term persona/profile facts (runtime inference only).
# 注意：persona_summary_internal 等不可量化字段已完全删除，不再需要这个列表
INFERENCE_ONLY_PERSONA_FIELDS = frozenset(
    {
        # 不可量化字段已删除：persona_summary_internal, preference_summary_internal
        # 不可量化字段已删除：public_profile_summary_draft, public_preference_summary_draft
        # 这些字段应该存储在向量库或对话摘要表中，不在 persona 表
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


def _flatten_matcher_nested(record: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for nested_key in ("matcher_preferences", "matcher_risks"):
        nested = record.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key, value in nested.items():
            if _has_value(value):
                flat[key] = value
    return flat


def merge_collected_for_compile(
    *,
    profile_row: Mapping[str, Any] | None = None,
    persona_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge persona collected fields with synced profile preferences (profile wins on conflict)."""

    from match_domain.reciprocal_preferences import enrich_record_for_reciprocal

    persona_collected = extract_collected_statements(persona_row or {})
    profile_collected: dict[str, Any] = {}
    if profile_row:
        enriched = enrich_record_for_reciprocal(profile_row)
        profile_collected = dict(extract_collected_statements(enriched))
        for key, value in _flatten_matcher_nested(enriched).items():
            if key in COLLECTED_PERSONA_FIELDS and _has_value(value):
                profile_collected[key] = value

    merged = dict(persona_collected)
    merged.update(profile_collected)
    return merged


def filter_explicit_patch(patch: Mapping[str, Any], source_type: str) -> dict[str, Any]:
    if source_type in INFERENCE_SOURCE_TYPES:
        return {}
    if source_type not in PERSISTABLE_SOURCE_TYPES:
        return dict(patch)
    filtered: dict[str, Any] = {}
    for key, value in patch.items():
        if key in INFERENCE_ONLY_PERSONA_FIELDS:
            continue
        if key == "self_personality_traits_json":
            filtered[key] = value
            continue
        if key in COLLECTED_PERSONA_FIELDS or key.startswith("target_") or key.startswith("self_"):
            filtered[key] = value
        elif key in {"display_name"}:
            filtered[key] = value
    return filtered
