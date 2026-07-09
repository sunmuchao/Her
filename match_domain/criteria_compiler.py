"""Unified effective-criteria compiler (§13.1.2) — collected inputs only."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from her_time_utils import clean_text as _clean_text

from .collected_profile import extract_profile_facts, merge_collected_for_compile
from .onboarding_search import build_profile_search_defaults, normalize_compiled_criteria

LIST_FIELD_KEYS = frozenset(
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
        "profile_statuses",
        "verified_levels",
        "required_known_fields",
        "exclude_source_channels",
    }
)

SCENE_DISCOVERY_SEARCH = "discovery_search"
SCENE_RECOMMENDATION_REFRESH = "recommendation_refresh"
SCENE_SAVED_SEARCH = "saved_search"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, tuple):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, set):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, str):
        parts = re.split(r"[，,、/|]+", value)
        return [part.strip() for part in parts if part.strip()]
    return [value]


def _unique_ordered(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    ordered: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _coerce_criteria_value(value: Any, *, as_list_value: bool = False) -> Any:
    if as_list_value:
        return _unique_ordered([item for item in _as_list(value) if item not in {None, ""}])
    if value is None or value == "":
        return None
    return value


def _apply_patch(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    updated = dict(base)
    for key, value in patch.items():
        if value is None or value == "" or value == [] or value == {}:
            updated.pop(key, None)
            continue
        if key in LIST_FIELD_KEYS:
            updated[key] = _coerce_criteria_value(value, as_list_value=True)
        else:
            updated[key] = value
    return updated


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def _build_relationship_goals(profile_facts: Mapping[str, Any] | None, fallback: Any) -> list[Any]:
    """Build relationship goals from profile facts.

    注意：relationship_goal 现在在 profiles 表中（硬条件），不在 persona 表的 self_relationship_goal

    修复：确保返回的是数据库标准值（英文）
    """
    if not profile_facts:
        return _unique_ordered(_as_list(fallback))

    # 导入字段值映射器
    from match_domain.field_value_mapper import FieldValueMapper

    self_goal = _clean_text(profile_facts.get("relationship_goal"))
    if not self_goal:
        return _unique_ordered(_as_list(fallback))

    # 使用FieldValueMapper规范化为数据库标准值
    normalized_goal = FieldValueMapper.to_db_value("relationship_goal", self_goal)

    if normalized_goal == "marriage":  # 结婚导向
        # 只匹配同样想结婚的人
        return ["marriage"]
    elif normalized_goal == "dating":  # 认真恋爱
        # 认真恋爱可以接受结婚导向的人
        return ["dating", "marriage"]
    elif normalized_goal:
        # 其他情况，返回规范化后的值
        return [normalized_goal]

    return _unique_ordered(_as_list(fallback))


def _build_collected_criteria_patch(
    collected: Mapping[str, Any] | None,
    profile_facts: Mapping[str, Any] | None = None,  # ← 新增参数：profile_facts
) -> dict[str, Any]:
    if not collected:
        return {}

    patch: dict[str, Any] = {}
    field_map = {
        "gender": "target_gender",
        "age_min": "target_age_min",
        "age_max": "target_age_max",
        "cities": "target_cities",
        "height_min": "target_height_min",
        "height_max": "target_height_max",
        "marital_statuses": "target_marital_statuses",
        "accept_marital_status_strength": "target_marital_status_strength",
        "accept_partner_children": "target_accept_partner_children",
        "accept_partner_children_strength": "target_accept_partner_children_strength",
        "long_distance": "target_accept_long_distance",
        "want_children": "target_want_children",
        "marriage_timelines": "target_marriage_timeline",
        "must_have": "must_have_tags",
        "must_not_have": "must_not_have_tags",
        # prefer 映射已删除：preferred_traits（不可量化：性格特质偏好）
    }

    for target_key, source_key in field_map.items():
        if source_key not in collected:
            continue
        value = collected.get(source_key)
        if target_key in LIST_FIELD_KEYS:
            patch[target_key] = _coerce_criteria_value(value, as_list_value=True)
        else:
            patch[target_key] = _coerce_criteria_value(value)

    relationship_goals = _build_relationship_goals(profile_facts, patch.get("relationship_goals"))
    if relationship_goals:
        patch["relationship_goals"] = relationship_goals
    return patch


def _build_source_map(
    *,
    profile_facts: Mapping[str, Any],
    collected: Mapping[str, Any],
    criteria: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    source_map: dict[str, dict[str, Any]] = {}
    reverse_map = {
        "gender": "target_gender",
        "age_min": "target_age_min",
        "age_max": "target_age_max",
        "cities": "target_cities",
        "height_min": "target_height_min",
        "height_max": "target_height_max",
        "marital_statuses": "target_marital_statuses",
        "accept_partner_children": "target_accept_partner_children",
        "long_distance": "target_accept_long_distance",
        "must_have": "must_have_tags",
        "must_not_have": "must_not_have_tags",
        # prefer 映射已删除：preferred_traits（不可量化：性格特质偏好）
        # relationship_goals 映射已删除，relationship_goal 现在在 profiles 表中（硬条件）
    }
    for criteria_key in criteria:
        persona_key = reverse_map.get(criteria_key)
        if persona_key and persona_key in collected:
            source_map[criteria_key] = {
                "source": "explicit_statement",
                "field": persona_key,
            }
        # relationship_goals 特殊处理已删除，relationship_goal 现在在 profiles 表中（硬条件）
        elif overrides and criteria_key in overrides:
            source_map[criteria_key] = {"source": "explicit_override", "field": criteria_key}
        elif criteria_key == "gender" and profile_facts.get("sexual_orientation"):
            source_map[criteria_key] = {"source": "profile_form", "field": "sexual_orientation"}
        elif criteria_key in build_profile_search_defaults(profile_facts):
            source_map[criteria_key] = {"source": "profile_form", "field": criteria_key}
    return source_map


def _criteria_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _split_criteria(criteria: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """改进：明确区分硬约束和软约束参数

    Agent Native架构原则：
    - 硬约束参数：在数据库层执行筛选（性别、年龄、城市等）
    - 软约束参数：在Agent层自主判断（性格特质、价值观等）

    新逻辑：
    1. 硬约束参数进入 hard_filters（传递到搜索层）
    2. 软约束参数被忽略（不传递到搜索层，Agent根据返回的原始数据自主判断）
    3. soft_preferences 保留为空（兼容性）

    这样 search_sources.py 只处理硬约束，性格筛选等软约束由Agent自主决策
    """
    import logging
    _logger = logging.getLogger(__name__)

    # 软约束参数列表（不在数据库层筛选，由Agent自主判断）
    SOFT_CONSTRAINT_KEYS = {
        "personality_traits",      # 性格特质（如内向/外向）
        "personality_match",       # 性格匹配条件
        "values_match",            # 价值观匹配
        "attachment_match",        # 依恋风格匹配
        "compatibility_threshold", # 兼容度阈值
    }

    hard_filters: dict[str, Any] = {}
    soft_preferences: dict[str, Any] = {}  # 保留为空，用于兼容性

    for key, value in criteria.items():
        # 过滤空值
        if value is None or value == "" or value == []:
            continue

        # 检查是否是软约束参数
        if key in SOFT_CONSTRAINT_KEYS:
            _logger.debug(
                "【软约束参数忽略】key=%s value=%s reason='不在数据库层筛选，Agent根据返回数据自主判断'",
                key,
                str(value)[:100]
            )
            continue  # ← 软约束参数不传递到搜索层

        # 硬约束参数进入 hard_filters
        hard_filters[key] = value

    return hard_filters, soft_preferences


def _build_self_profile(
    profile_facts: Mapping[str, Any],
    collected: Mapping[str, Any],
    *,
    fallback_self_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    self_profile = dict(fallback_self_profile or {})
    if profile_facts:
        self_profile.update(profile_facts)
    persona_self = {
        f"self_{key[len('self_'):]}": value
        for key, value in collected.items()
        if key.startswith("self_")
    }
    self_profile.update({k: v for k, v in persona_self.items() if v not in (None, "", [], {})})
    return self_profile


@dataclass
class CompiledCriteria:
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    criteria: dict[str, Any] = field(default_factory=dict)
    self_profile: dict[str, Any] = field(default_factory=dict)
    source_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    criteria_hash: str = ""
    scene: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_initial_request(subscription: Mapping[str, Any]) -> dict[str, Any]:
    initial_request = _json_loads(subscription.get("initial_request_json"), {})
    if initial_request:
        return dict(initial_request)
    return {
        "source": subscription.get("source"),
        "criteria": _json_loads(subscription.get("search_criteria_json"), {}),
        "self_profile": _json_loads(subscription.get("self_profile_json"), None),
        "self_id": subscription.get("self_id"),
        "table_name": subscription.get("table_name"),
        "photos_table_name": subscription.get("photos_table_name"),
        "limit": int(subscription.get("limit_count") or 10),
        "photo_preview_count": 0,
        "include_source": True,
        "include_text": False,
    }


def build_subscription_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = _json_loads(subscription.get("subscription_overrides_json"), {})
    if not isinstance(overrides, Mapping):
        return {}
    filtered = dict(overrides or {})
    filtered.pop("review_policy", None)
    return filtered


def compile_effective_criteria(
    *,
    scene: str,
    profile_row: Mapping[str, Any] | None = None,
    persona_row: Mapping[str, Any] | None = None,
    base_criteria: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
    subscription: Mapping[str, Any] | None = None,
    fallback_self_profile: Mapping[str, Any] | None = None,
) -> CompiledCriteria:
    profile_facts = extract_profile_facts(profile_row or {})
    collected = merge_collected_for_compile(profile_row=profile_row, persona_row=persona_row)

    if subscription is not None:
        initial = build_initial_request(subscription)
        criteria_base = dict(initial.get("criteria") or {})
        subscription_overrides = build_subscription_overrides(subscription)
        fallback_self_profile = fallback_self_profile or initial.get("self_profile")
    else:
        criteria_base = dict(base_criteria or {})
        subscription_overrides = {}

    criteria = _apply_patch(criteria_base, build_profile_search_defaults(profile_row or {}))
    criteria = _apply_patch(criteria, _build_collected_criteria_patch(collected, profile_facts=profile_facts))
    explicit_overrides = dict(overrides or {})
    explicit_overrides.update(subscription_overrides)
    criteria = _apply_patch(criteria, explicit_overrides)
    criteria = normalize_compiled_criteria(criteria)

    # ====================================================================
    # Bug修复2：性别筛选兜底逻辑
    # ====================================================================
    # 问题：如果 sexual_orientation 字段缺失，系统无法推导目标性别
    # 解决：添加两层兜底机制
    #   1. 优先从 sexual_orientation 推导（标准逻辑）
    #   2. 如果缺失，默认异性恋逻辑（女生→目标男性，男生→目标女性）
    # 原理：确保即使数据不完美，也能有合理的筛选条件
    # ====================================================================
    import logging
    _logger = logging.getLogger(__name__)

    if "gender" not in criteria or not criteria.get("gender"):
        from match_domain.onboarding_search import (
            map_sexual_orientation_to_target_gender,
            normalize_search_gender,
        )

        # 第一层：尝试从 sexual_orientation 推导
        sexual_orientation = profile_facts.get("sexual_orientation") if profile_facts else None
        target_gender = map_sexual_orientation_to_target_gender(sexual_orientation)

        if target_gender:
            criteria["gender"] = target_gender
            _logger.info(
                f"【性别筛选推导】scene={scene} sexual_orientation={sexual_orientation} → target_gender={target_gender}"
            )
        else:
            # 第二层：兜底默认异性恋逻辑
            self_gender = profile_facts.get("gender") if profile_facts else None
            if self_gender:
                normalized_self = normalize_search_gender(self_gender)
                if normalized_self == "female":
                    default_target = "male"
                elif normalized_self == "male":
                    default_target = "female"
                else:
                    default_target = None

                if default_target:
                    criteria["gender"] = default_target
                    _logger.warning(
                        f"【性别筛选兜底】scene={scene} user_gender={self_gender} "
                        f"default_target={default_target} reason='sexual_orientation缺失，使用默认异性恋逻辑'"
                    )
            else:
                _logger.error(
                    f"【性别筛选缺失】scene={scene} reason='既没有sexual_orientation也没有gender，无法推导目标性别'"
                )

    hard_filters, soft_preferences = _split_criteria(criteria)
    source_map = _build_source_map(
        profile_facts=profile_facts,
        collected=collected,
        criteria=criteria,
        overrides=explicit_overrides,
    )

    # ====================================================================
    # 日志追踪：记录性别筛选条件的生成过程
    # ====================================================================
    # 目的：追踪性别筛选条件的来源和推导过程，便于诊断问题
    # 输出：target_gender、source（explicit_statement/profile_form/explicit_override）、原始字段值
    # ====================================================================
    if criteria.get("gender"):
        gender_source = source_map.get("gender", {})
        _logger.info(
            f"【性别筛选条件】scene={scene} "
            f"target_gender={criteria.get('gender')} "
            f"source={gender_source.get('source', 'unknown')} "
            f"field={gender_source.get('field', 'unknown')} "
            f"sexual_orientation={profile_facts.get('sexual_orientation') if profile_facts else None}"
        )
    else:
        _logger.warning(
            f"【性别筛选缺失警告】scene={scene} "
            f"profile_facts={dict(profile_facts or {})} "
            f"reason='最终criteria中没有gender字段'"
        )

    self_profile = _build_self_profile(
        profile_facts,
        collected,
        fallback_self_profile=fallback_self_profile,
    )
    criteria_hash = _criteria_hash(
        {
            "scene": scene,
            "criteria": criteria,
            "self_profile_keys": sorted(self_profile.keys()),
        }
    )
    return CompiledCriteria(
        hard_filters=hard_filters,
        soft_preferences=soft_preferences,
        criteria=criteria,
        self_profile=self_profile,
        source_map=source_map,
        criteria_hash=criteria_hash,
        scene=scene,
    )


def build_effective_search_request(
    subscription: Mapping[str, Any],
    *,
    persona_profile: Mapping[str, Any] | None = None,
    profile_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    initial_request = build_initial_request(subscription)
    compiled = compile_effective_criteria(
        scene=SCENE_RECOMMENDATION_REFRESH,
        profile_row=profile_row,
        persona_row=persona_profile,
        subscription=subscription,
        fallback_self_profile=persona_profile or initial_request.get("self_profile"),
    )
    return {
        "source": initial_request.get("source") or subscription.get("source"),
        "table_name": initial_request.get("table_name") or subscription.get("table_name"),
        "photos_table_name": initial_request.get("photos_table_name") or subscription.get("photos_table_name"),
        "criteria": compiled.criteria,
        "self_profile": compiled.self_profile,
        "compiled": compiled.to_dict(),
        "self_id": initial_request.get("self_id", subscription.get("self_id")),
        "limit": int(initial_request.get("limit") or subscription.get("limit_count") or 10),
        "photo_preview_count": int(initial_request.get("photo_preview_count") or 0),
        "include_source": bool(initial_request.get("include_source", True)),
        "include_text": bool(initial_request.get("include_text", False)),
    }


def build_discovery_search_request(
    *,
    source: str,
    profile_row: Mapping[str, Any] | None,
    persona_row: Mapping[str, Any] | None,
    criteria_overrides: Mapping[str, Any] | None,
    self_id: int | None,
    limit: int,
    table_name: str | None = None,
    photos_table_name: str | None = None,
) -> dict[str, Any]:
    compiled = compile_effective_criteria(
        scene=SCENE_DISCOVERY_SEARCH,
        profile_row=profile_row,
        persona_row=persona_row,
        base_criteria={},
        overrides=criteria_overrides,
        fallback_self_profile=profile_row,
    )
    return {
        "source": source,
        "table_name": table_name,
        "photos_table_name": photos_table_name,
        "criteria": compiled.criteria,
        "self_profile": compiled.self_profile,
        "compiled": compiled.to_dict(),
        "self_id": self_id,
        "limit": limit,
        "photo_preview_count": 3,
        "include_source": False,
    }
