#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from her_time_utils import clean_text, coerce_int as as_int, unique_ordered_texts
from mysql_source_config import parse_mysql_source_config
from outer_system_mysql_schema import quote_mysql_ident as mysql_quote_ident
from persona_memory_sync.public_profile_helpers import (
    PublicProfileHelpers,
    PublicProfileRuntime,
)


DEFAULT_SOURCE_ENV = "PERSONA_MEMORY_MYSQL_SOURCE"
DEFAULT_PROFILE_TABLE = "profiles"
DEFAULT_PERSONA_TABLE = "user_personas"
DEFAULT_OBSERVATION_TABLE = "user_persona_observations"
DEFAULT_PUBLIC_VIEW = "public_profile_view"
VALID_APPLY_SCOPES = {"observation_only", "persona_only", "persona_and_profile"}

USER_PERSONA_FIELDS = {
    "profile_id",
    "display_name",
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
    "self_marital_status",
    "self_has_children",
    "self_children_count",
    "self_children_living_with_self",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
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
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

LIST_FIELDS = {
    "target_cities",
    "target_marital_statuses",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
}

INT_FIELDS = {
    "profile_id",
    "self_age",
    "self_height",
    "self_income_wan",
    "self_children_count",
    "target_age_min",
    "target_age_max",
    "target_height_min",
    "target_height_max",
    "target_income_min_wan",
    "target_income_max_wan",
}

BOOL_FIELDS = {
    "self_has_children",
    "self_children_living_with_self",
    "target_requires_partner_accept_my_children",
}

EXPLICIT_ONLY_FIELDS = {
    "profile_id",
    "display_name",
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
    "self_marital_status",
    "self_has_children",
    "self_children_count",
    "self_children_living_with_self",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
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
}

INFERENCE_MUTABLE_LIST_FIELDS = {
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
}

STRONG_INFERENCE_MUTABLE_SCALARS = {
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

SOFT_SELF_DESCRIPTION_FIELDS = {
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
}

PERSONA_TO_PROFILE_FIELD_MAP = {
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
    "target_age_min": "preferred_age_min",
    "target_age_max": "preferred_age_max",
    "target_cities": "preferred_cities",
    "target_height_min": "preferred_height_min",
    "target_height_max": "preferred_height_max",
    "target_education_min": "preferred_education_min",
    "target_income_min_wan": "preferred_income_min_wan",
    "target_income_max_wan": "preferred_income_max_wan",
    "target_marital_status_strength": "accept_marital_status_strength",
    "target_accept_partner_children_strength": "accept_partner_children_strength",
    "target_location_semantics": "location_preference_semantics",
    "target_requires_partner_accept_my_children": "requires_partner_accept_my_children",
}

PROFILE_EXTENSION_COLUMNS = {
    "matcher_traits_json": "JSON NULL",
    "matcher_preferences_json": "JSON NULL",
    "matcher_risks_json": "JSON NULL",
    "matcher_summary_internal": "TEXT NULL",
    "accept_marital_status_semantics": "VARCHAR(128) NULL",
    "accept_partner_children_semantics": "VARCHAR(128) NULL",
    "location_preference_semantics": "VARCHAR(128) NULL",
    "requires_partner_accept_my_children": "TINYINT(1) NULL",
    "public_display_name": "VARCHAR(64) NULL",
    "public_education": "VARCHAR(32) NULL",
    "public_job": "VARCHAR(64) NULL",
    "public_personality": "TEXT NULL",
    "public_values": "TEXT NULL",
    "public_notes": "TEXT NULL",
}

PROFILE_SYNC_PERSONA_FIELDS = set(PERSONA_TO_PROFILE_FIELD_MAP) | {
    "display_name",
    "self_income_wan",
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
    "target_accept_long_distance",
    "target_accept_partner_children",
    "target_accept_partner_children_strength",
    "target_location_semantics",
    "target_requires_partner_accept_my_children",
    "target_marital_statuses",
    "target_marital_status_strength",
    "target_gender",
    "target_want_children",
    "target_marriage_timeline",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

PATCH_DERIVED_PROFILE_COLUMNS = {
    "self_income_wan": {"income_range"},
    "self_education": {"public_education"},
    "self_job": {"public_job"},
    "self_life_rhythm": {"matcher_traits_json", "matcher_summary_internal", "public_personality", "personality"},
    "self_work_pattern": {"matcher_traits_json", "matcher_summary_internal", "public_personality", "personality"},
    "self_expression_style": {"matcher_traits_json", "matcher_summary_internal", "public_personality", "personality"},
    "target_accept_long_distance": {"long_distance", "accept_long_distance"},
    "target_accept_partner_children": {"accept_partner_children", "accept_partner_children_semantics"},
    "target_location_semantics": {"location_preference_semantics"},
    "target_requires_partner_accept_my_children": {"requires_partner_accept_my_children"},
    "target_marital_statuses": {"accept_marital_status", "accept_marital_status_semantics"},
    "target_marital_status_strength": {"accept_marital_status_strength", "accept_marital_status_semantics"},
    "target_accept_partner_children_strength": {"accept_partner_children_strength", "accept_partner_children_semantics"},
}

RAW_NEGATIVE_TO_MATCHER = {
    "绿茶": {
        "boundary_clarity_risk": "high",
        "multi_thread_ambiguity_risk": "high",
        "attention_seeking_tendency": "high",
    },
    "拜金": {
        "material_expectation_level": "high",
        "spending_values_mismatch_risk": "high",
    },
    "冷暴力": {
        "communication_shutdown_risk": "high",
        "conflict_repair_capacity": "low",
    },
    "暧昧不清": {
        "commitment_clarity": "low",
        "ambiguity_risk": "high",
    },
    "抽烟": {
        "partner_smoking_tolerance": "low",
    },
}

POSITIVE_TAG_TO_MATCHER = {
    "情绪稳定": {
        "emotional_stability_priority": "high",
    },
    "愿意沟通": {
        "communication_directness_preference": "high",
        "repair_orientation_priority": "high",
    },
    "沟通": {
        "communication_directness_preference": "high",
    },
    "消费观正常": {
        "spending_values_alignment_priority": "high",
    },
    "同城": {
        "same_city_priority": "high",
    },
}

PUBLIC_SAFE_NEGATIVE_NOTES = {
    "暧昧不清": "不喜欢关系里反复拉扯",
    "长期暧昧": "不喜欢长期暧昧拉扯",
    "反复拉扯": "不喜欢关系里反复拉扯",
    "冷暴力": "希望沟通方式更稳定直接",
    "情绪攻击": "希望沟通方式稳定、彼此尊重",
    "绿茶": "关系边界希望更清晰",
    "拜金": "消费观需要更加一致",
    "抽烟": "更偏好生活习惯相近的人",
    "控制欲强": "不喜欢控制感太强的相处",
    "不尊重人": "希望关系里有基本尊重",
    "沟通不清": "希望沟通更直接清晰",
    "态度暧昧": "不喜欢态度暧昧",
}

PUBLIC_SAFE_TAG_MAP = {
    "愿意沟通": "愿意沟通",
    "沟通": "愿意沟通",
    "消费观正常": "消费观相近",
    "接受孩子现实": "能承接现实关系",
    "能接受孩子现实": "能承接现实关系",
    "婚姻诚意": "婚姻诚意",
    "现实推进能力": "现实推进能力",
    "共同兴趣": "共同兴趣",
    "有共同兴趣更好": "共同兴趣",
    "有一点审美": "审美契合",
    "健康习惯": "健康习惯",
    "真诚": "真诚",
    "责任感": "责任感",
    "责任心": "责任感",
    "行动力": "行动力",
    "生活规律": "生活规律",
    "家庭观念": "家庭观念",
    "稳定踏实": "稳定踏实",
}

PUBLIC_VALUE_PRIORITY_TAGS = (
    "情绪稳定",
    "边界清楚",
    "责任感",
    "沟通顺畅",
    "愿意沟通",
    "真诚",
    "稳定踏实",
    "婚姻诚意",
    "现实推进能力",
    "能承接现实关系",
    "真正接受孩子现实",
    "行动力",
    "健康习惯",
    "生活规律",
    "家庭观念",
)

PUBLIC_JOB_PATTERNS = (
    (re.compile(r"(高校教师|大学教师|高校讲师)"), "高校教师"),
    (re.compile(r"(医院|诊所|药师|医生|医师|护士|临床|医疗)"), "医疗相关工作"),
    (re.compile(r"(学校|教师|老师|教研|辅导员|教育|培训)"), "教育相关工作"),
    (re.compile(r"(银行|证券|基金|保险|金融)"), "金融相关工作"),
    (re.compile(r"(研究院|实验室|科研)"), "科研相关工作"),
)

NON_SMOKING_VALUES = {"否", "不抽烟", "不吸烟"}

OBSERVATION_FIELD_LABELS = {
    "display_name": "昵称",
    "self_age": "年龄",
    "self_city": "现居城市",
    "self_education": "学历",
    "self_job": "职业",
    "self_life_rhythm": "生活节奏",
    "self_work_pattern": "工作形态",
    "self_expression_style": "表达风格",
    "self_income_wan": "收入",
    "self_marital_status": "婚况",
    "self_has_children": "是否有孩子",
    "self_children_count": "孩子数量",
    "self_children_living_with_self": "孩子是否随自己生活",
    "self_smoking": "抽烟情况",
    "self_drinking": "喝酒情况",
    "self_relationship_goal": "关系目标",
    "target_gender": "目标性别",
    "target_age_min": "目标年龄下限",
    "target_age_max": "目标年龄上限",
    "target_cities": "目标城市",
    "target_height_min": "目标身高下限",
    "target_height_max": "目标身高上限",
    "target_education_min": "目标学历下限",
    "target_marital_statuses": "可接受婚况",
    "target_marital_status_strength": "婚史接受强度",
    "target_accept_partner_children": "对子女情况接受度",
    "target_accept_partner_children_strength": "对子女情况接受强度",
    "target_accept_long_distance": "异地接受度",
    "target_location_semantics": "位置偏好补充",
    "target_requires_partner_accept_my_children": "对方是否需要接受自己的孩子现实",
    "must_have_tags": "硬偏好标签",
    "must_not_have_tags": "明确排斥标签",
    "preferred_traits": "更偏好特质",
    "disliked_traits": "不太接受特质",
}

ACCEPTANCE_STRENGTH_STRONG_VALUES = {"明确接受", "长期接受", "真接受"}
ACCEPTANCE_STRENGTH_CAUTION_VALUES = {"谨慎接受", "了解后定", "需要磨合"}
ACCEPTANCE_STRENGTH_SURFACE_VALUES = {"短期可聊", "表面接受", "先接触再说"}
CHILD_ACCEPTANCE_GUARDED_CANONICAL = "现阶段不太接受"
CHILD_ACCEPTANCE_GUARDED_ALIASES = {"谨慎可协商", "低接受度可协商", CHILD_ACCEPTANCE_GUARDED_CANONICAL}
CHILD_ACCEPTANCE_GUARDED_MARKERS = (
    "不太接受",
    "优先不考虑",
    "先不考虑",
    "偏谨慎",
    "偏保留",
    "现阶段不考虑",
)
MARITAL_ACCEPTANCE_CAUTIOUS_MARKERS = (
    "更看具体",
    "看具体人",
    "看具体情况",
    "相处质量",
    "人稳定",
    "情况清楚",
)
MARITAL_ACCEPTANCE_SURFACE_MARKERS = (
    "先聊再判断",
    "先接触再判断",
    "先聊再说",
)

SOFT_REQUIREMENT_TAGS = {
    "聊得来",
    "有感觉",
    "共同兴趣",
    "有共同兴趣更好",
    "眼缘",
    "生活状态正常",
    "有共同话题",
    "相处舒服",
    "情绪稳定",
    "愿意沟通",
    "沟通顺畅",
    "责任感",
    "真诚",
    "消费观正常",
    "边界清楚",
    "边界感正常",
    "尊重彼此",
    "尊重他人",
    "家庭观念",
    "有行动力",
    "有计划",
    "有担当",
    "有同理心",
    "收入稳定",
    "真实",
    "有分寸",
    "婚姻诚意",
    "长期投入能力",
    "生活规律",
    "生活稳定",
    "稳定工作",
    "接受孩子现实",
    "能接受孩子现实",
}

SOFT_REQUIREMENT_MARKERS = (
    "聊得来",
    "有感觉",
    "共同兴趣",
    "共同话题",
    "眼缘",
    "相处舒服",
    "情绪稳定",
    "沟通",
    "责任感",
    "真诚",
    "消费观",
    "边界",
    "尊重",
    "家庭观念",
    "行动力",
    "有计划",
    "有担当",
    "同理心",
    "收入稳定",
    "真实",
    "有分寸",
    "婚姻诚意",
    "长期投入",
    "生活规律",
    "生活稳定",
    "稳定工作",
)

PARENT_REALITY_REQUIRED_MARKERS = (
    "接受孩子现实",
    "能接受孩子现实",
    "接受我有孩子",
    "接受我这边有孩子",
    "接受我的孩子",
    "接受我带孩子",
    "能承接孩子现实",
)

PARTNER_HAS_CHILDREN_MARKERS = (
    "接受对方有孩子",
    "接受对方已有孩子",
    "对方有孩子也可以",
    "能接受对方有孩子",
    "能接受对方带孩子",
)

LOCATION_NUANCE_MARKERS = (
    "稳定留沪",
    "双城过渡",
    "异地",
    "长期异地",
    "短期异地",
    "近距离",
    "落地计划",
    "落地异地",
    "同城",
    "周边",
    "通勤",
    "落地",
)

SAFE_PUBLIC_PERSONALITY_PATTERNS = (
    (re.compile(r"慢热[^，。；]{0,12}(?:有反馈|有回应)"), "慢热但有反馈"),
    (re.compile(r"慢热但认真"), "慢热但认真"),
    (re.compile(r"表达克制"), "表达克制"),
    (re.compile(r"(?:做事|相处|生活)[^，。；]{0,6}有计划"), "做事有计划"),
    (re.compile(r"(?:相处舒服|相处自然|不拉扯|不拧巴)"), "相处不拧巴"),
    (re.compile(r"生活安静稳定"), "生活安静稳定"),
    (re.compile(r"生活有规划"), "生活有规划"),
    (re.compile(r"生活规律"), "生活规律"),
    (re.compile(r"作息规律"), "作息规律"),
    (re.compile(r"作息不算特别规律"), "作息不算特别规律"),
    (re.compile(r"务实"), "务实"),
    (re.compile(r"工作有创意"), "工作有创意"),
    (re.compile(r"(?:有自己的生活趣味|生活有趣味)"), "有自己的生活趣味"),
    (re.compile(r"生活节奏总体正常"), "生活节奏总体正常"),
)

LIFE_RHYTHM_CANONICAL_PATTERNS = (
    (re.compile(r"(生活|作息|节奏).{0,8}(规律|稳定|固定)"), "生活规律"),
    (re.compile(r"(生活|作息|节奏).{0,8}(灵活|松动|弹性)"), "生活节奏灵活"),
    (re.compile(r"(作息|节奏).{0,8}(不固定|不算特别规律|经常变)"), "作息不固定"),
)

WORK_PATTERN_CANONICAL_PATTERNS = (
    (re.compile(r"(工作|安排|节奏).{0,10}(临时变动|经常变|波动|随时待命|排班)"), "工作节奏波动较多"),
    (re.compile(r"(工作|安排|节奏).{0,10}(规律|稳定|固定)"), "工作节奏稳定"),
    (re.compile(r"(工作|时间|安排).{0,10}(灵活|自由|弹性)"), "工作时间灵活"),
)

EXPRESSION_STYLE_CANONICAL_PATTERNS = (
    (re.compile(r"(说话|表达).{0,10}(直接|不拐弯|不花哨)"), "表达直接"),
    (re.compile(r"(说话|表达).{0,10}(克制|收着|偏稳|含蓄)"), "表达克制"),
    (re.compile(r"慢热.{0,8}(有反馈|有回应)?"), "慢热但有反馈"),
)

SAFE_STRUCTURED_PERSONALITY_LABELS = {
    "生活规律",
    "生活节奏灵活",
    "作息不固定",
    "工作节奏波动较多",
    "工作节奏稳定",
    "工作时间灵活",
    "表达直接",
    "表达克制",
    "慢热但有反馈",
}

LONG_DISTANCE_BLOCK_PATTERNS = (
    re.compile(r"(?:不接受|不考虑|不能接受|不想)[^，。；]{0,8}长期异地"),
    re.compile(r"长期[^，。；]{0,8}异地[^，。；]{0,8}(?:不接受|不考虑|不行|免谈)"),
    re.compile(r"长期不落地异地"),
)

REGIONAL_CITY_EXPANSIONS = {
    "江浙沪": ("上海", "苏州", "无锡", "南京", "杭州", "常州", "宁波"),
}

CITY_PREFERENCE_PATTERNS = (
    re.compile(
        r"(?P<phrase>(?P<cities>[\u4e00-\u9fff]{2,4}(?:或|/|、|和|及)[\u4e00-\u9fff]{2,4})(?:都可以|都可|均可|优先))"
    ),
    re.compile(r"(?P<phrase>(?P<city>[\u4e00-\u9fff]{2,4})优先)"),
    re.compile(r"(?P<phrase>(?P<city>[\u4e00-\u9fff]{2,4})(?:都可以|都可|均可))"),
)

CITY_TOKEN_BLOCKLIST = {
    "江浙沪",
    "异地",
    "长期",
    "短期",
    "原则",
    "关系",
    "现实",
    "正常",
    "推进",
    "沟通",
    "计划",
    "见面",
    "稳定",
    "留沪",
    "同城",
    "周边",
    "通勤",
    "落地",
}

CITY_TOKEN_BLOCK_SUBSTRINGS = {
    "范围",
    "地区",
    "城市",
    "周边",
}


def resolve_mysql_source(source: Optional[str] = None) -> str:
    resolved = source or os.environ.get(DEFAULT_SOURCE_ENV)
    if resolved:
        return resolved
    raise ValueError(
        "No MySQL source configured. Pass --source mysql://user:pass@host:3306/db?table=profiles "
        f"or set {DEFAULT_SOURCE_ENV}."
    )


def parse_mysql_source(source: Optional[str] = None) -> Dict[str, Any]:
    source = resolve_mysql_source(source)
    return parse_mysql_source_config(
        source,
        source_label="MySQL source",
        default_table_name=DEFAULT_PROFILE_TABLE,
        include_source=True,
    )


def mysql_connect(source: Optional[str] = None):
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ValueError("PyMySQL is required. Install it with `python3 -m pip install pymysql`.") from exc

    config = parse_mysql_source(source)
    kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config["user"] is not None:
        kwargs["user"] = config["user"]
    if config["password"] is not None:
        kwargs["password"] = config["password"]
    return pymysql.connect(**kwargs)


def quote_mysql_ident(identifier: str) -> str:
    return mysql_quote_ident(identifier)


def persona_field_affects_profile(field_name: str) -> bool:
    return field_name in PROFILE_SYNC_PERSONA_FIELDS


def profile_columns_for_persona_patch(patch: Dict[str, Any]) -> List[str]:
    columns = set()
    for field_name in patch:
        profile_field = PERSONA_TO_PROFILE_FIELD_MAP.get(field_name)
        if profile_field:
            columns.add(profile_field)
        columns.update(PATCH_DERIVED_PROFILE_COLUMNS.get(field_name, set()))
    return sorted(columns)


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _canonicalize_by_patterns(value: Any, patterns: Iterable[Tuple[re.Pattern[str], str]]) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    for pattern, label in patterns:
        if pattern.search(text):
            return label
    return text


def canonicalize_life_rhythm(value: Any) -> Optional[str]:
    return _canonicalize_by_patterns(value, LIFE_RHYTHM_CANONICAL_PATTERNS)


def canonicalize_work_pattern(value: Any) -> Optional[str]:
    return _canonicalize_by_patterns(value, WORK_PATTERN_CANONICAL_PATTERNS)


def canonicalize_expression_style(value: Any) -> Optional[str]:
    return _canonicalize_by_patterns(value, EXPRESSION_STYLE_CANONICAL_PATTERNS)


def canonicalize_child_acceptance_state(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if text in CHILD_ACCEPTANCE_GUARDED_ALIASES:
        return CHILD_ACCEPTANCE_GUARDED_CANONICAL
    if text not in {"不接受", "明确不接受", "完全不接受"} and any(
        marker in text for marker in CHILD_ACCEPTANCE_GUARDED_MARKERS
    ):
        return CHILD_ACCEPTANCE_GUARDED_CANONICAL
    return text


def acceptance_strength_bucket(value: Any) -> str:
    lowered = clean_text(value)
    if not lowered:
        return "unknown"
    if lowered in ACCEPTANCE_STRENGTH_STRONG_VALUES:
        return "strong"
    if lowered in ACCEPTANCE_STRENGTH_CAUTION_VALUES:
        return "cautious"
    if lowered in ACCEPTANCE_STRENGTH_SURFACE_VALUES:
        return "surface"
    return "unknown"


def format_acceptance_note(value: Any, strength: Any) -> Optional[str]:
    note_value = canonicalize_child_acceptance_state(value) or clean_text(value)
    note_strength = clean_text(strength)
    if not note_value:
        return None
    if not note_strength:
        if note_value == CHILD_ACCEPTANCE_GUARDED_CANONICAL:
            return CHILD_ACCEPTANCE_GUARDED_CANONICAL
        return note_value
    bucket = acceptance_strength_bucket(note_strength)
    if note_value == CHILD_ACCEPTANCE_GUARDED_CANONICAL:
        return CHILD_ACCEPTANCE_GUARDED_CANONICAL
    if note_value == "可协商" and bucket == "cautious":
        return "现阶段接受度偏低，需结合具体情况判断"
    if note_value == "可协商" and bucket == "surface":
        return "可协商，先接触再判断"
    if note_value == "接受" and bucket == "cautious":
        return "接受，但会更看具体相处"
    return f"{note_value}（{note_strength}）"


def acceptance_semantics_label(value: Any, strength: Any) -> Optional[str]:
    state = canonicalize_child_acceptance_state(value) or clean_text(value)
    if not state:
        return None
    bucket = acceptance_strength_bucket(strength)
    if state == "不接受":
        return "明确不接受"
    if state == "未知":
        return "态度未知"
    if state == CHILD_ACCEPTANCE_GUARDED_CANONICAL:
        return CHILD_ACCEPTANCE_GUARDED_CANONICAL
    if state == "接受":
        if bucket == "strong":
            return "明确接受"
        if bucket == "cautious":
            return "接受，但会更看具体情况"
        if bucket == "surface":
            return "先接受接触，再看后续现实情况"
        return "接受"
    if state == "可协商":
        if bucket == "strong":
            return "愿意结合具体情况认真评估"
        if bucket == "cautious":
            return "现阶段接受度偏低，需结合具体情况判断"
        if bucket == "surface":
            return "可以先接触再判断"
        return "可协商"
    return state


def marital_acceptance_semantics_label(statuses: Any, strength: Any) -> Optional[str]:
    status_text = clean_text(statuses)
    if not status_text:
        return None
    bucket = acceptance_strength_bucket(strength)
    if bucket == "strong":
        return "在可接受范围内，态度明确"
    if bucket == "cautious":
        return "能接受，但更看具体人和相处质量"
    if bucket == "surface":
        return "能先聊，但还要再判断"
    if status_text == "未婚":
        return "仅接受未婚"
    return "可接受婚况范围已设置"


def infer_target_marital_status_strength(
    explicit_strength: Any,
    statuses: Any,
    *texts: Any,
) -> Optional[str]:
    explicit = clean_text(explicit_strength)
    if explicit and explicit not in {"可协商", "接受"}:
        return explicit

    status_text = clean_text(statuses)
    if not status_text:
        return explicit

    combined = " ".join(clean_text(text) or "" for text in texts)
    if any(marker in combined for marker in MARITAL_ACCEPTANCE_SURFACE_MARKERS):
        return "先接触再说"
    if any(marker in combined for marker in MARITAL_ACCEPTANCE_CAUTIOUS_MARKERS):
        return "谨慎接受"
    return explicit


def normalize_boolish(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "是", "有"}:
        return 1
    if lowered in {"0", "false", "no", "n", "否", "无"}:
        return 0
    return None


def split_multi_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[，,、;/\n|]+", str(value))
    result: List[str] = []
    seen = set()
    for item in items:
        text = clean_text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def unique_ordered(items: Iterable[str]) -> List[str]:
    return unique_ordered_texts(items)


def bool_is_true(value: Any) -> bool:
    return normalize_boolish(value) == 1


def extract_children_count_from_text(*texts: Any) -> Optional[int]:
    for raw_text in texts:
        text = clean_text(raw_text) or ""
        if not text:
            continue
        if any(marker in text for marker in ("有一女", "有一子", "一个孩子", "1个孩子")):
            return 1
        if any(marker in text for marker in ("有两孩", "两个孩子", "2个孩子", "一子一女")):
            return 2
        match = re.search(r"有([一二两三四五六七八九十0-9])个孩子", text)
        if match:
            mapping = {
                "一": 1,
                "二": 2,
                "两": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
                "九": 9,
                "十": 10,
            }
            token = match.group(1)
            return mapping.get(token, as_int(token))
    return None


def extract_children_living_with_self_from_text(*texts: Any) -> Optional[int]:
    for raw_text in texts:
        text = clean_text(raw_text) or ""
        if not text:
            continue
        if any(marker in text for marker in ("不随身", "不跟自己住", "不在身边", "不跟我住")):
            return 0
        if any(marker in text for marker in ("随身", "跟自己住", "跟我住", "自己带")):
            return 1
    return None


def normalize_self_marital_status_label(status: Any) -> Optional[str]:
    text = clean_text(status)
    if not text:
        return None
    if text.startswith("离异"):
        return "离异"
    if text.startswith("丧偶"):
        return "丧偶"
    return text


def infer_children_state_from_marital_status(status: Any) -> Optional[int]:
    text = clean_text(status) or ""
    if not text:
        return None
    if any(marker in text for marker in ("无孩", "未育")):
        return 0
    if any(marker in text for marker in ("已育", "有孩", "带娃", "带孩子")):
        return 1
    return None


def expand_regional_target_cities(target_cities: Any, *texts: Any) -> List[str]:
    cities = split_multi_value(target_cities)
    combined_text = " ".join(clean_text(text) or "" for text in texts)
    expanded = list(cities) + extract_city_candidates_from_semantics(*texts)
    for region, region_cities in REGIONAL_CITY_EXPANSIONS.items():
        if region in combined_text:
            expanded.extend(region_cities)
    return unique_ordered(expanded)


def infer_target_long_distance_value(explicit_value: Any, semantics_text: Any) -> Optional[str]:
    explicit = clean_text(explicit_value)
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return explicit

    allows_short_term = any(
        marker in semantics for marker in ("短期异地可了解", "短期通勤型距离", "短期通勤", "稳定留沪")
    )
    dual_city_transition = any(
        marker in semantics for marker in ("双城过渡", "近距离", "通勤", "见面成本不能太高")
    )
    long_term_cautious = "长期异地比较谨慎" in semantics
    blocks_long_term = any(pattern.search(semantics) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)

    if explicit == "可协商":
        if long_term_cautious:
            return "短期通勤可了解，长期异地谨慎"
        if allows_short_term or dual_city_transition or blocks_long_term:
            return "近距离可推进，长期异地不接受"
    if explicit == "不接受":
        if allows_short_term and blocks_long_term:
            return "短期可了解，长期异地不接受"
        if (
            any(marker in semantics for marker in ("近距离", "见面成本不能太高", "稳定留沪"))
            or (
                "落地计划" in semantics
                and any(marker in semantics for marker in ("可以沟通", "可沟通", "可了解", "能看"))
            )
        ) and "明确不接受长期异地" not in semantics:
            return "近距离可推进，长期异地不接受"
        if dual_city_transition and blocks_long_term and "短期过渡" not in semantics:
            return "近距离可推进，长期异地不接受"
    return explicit


def canonicalize_long_distance_state(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if text in {"接受", "不接受", "可协商", "未知"}:
        return text

    if "短期通勤" in text or ("通勤" in text and "谨慎" in text):
        return "短期通勤可了解，长期异地谨慎"
    if "短期可了解" in text and any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS):
        return "短期可了解，长期异地不接受"
    if any(
        marker in text
        for marker in ("近距离", "双城过渡", "稳定留沪", "见面成本不能太高")
    ) and (
        any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)
        or "不接受远距离异地" in text
        or "长期异地不接受" in text
    ):
        return "近距离可推进，长期异地不接受"
    if "长期异地比较谨慎" in text:
        return "短期通勤可了解，长期异地谨慎"

    has_transition_allowance = any(
        marker in text
        for marker in (
            "短期异地",
            "短期通勤",
            "短期可了解",
            "短期过渡",
            "通勤型距离",
            "近距离",
            "落地计划",
            "双城过渡",
            "稳定留沪",
        )
    )
    if has_transition_allowance or "谨慎" in text:
        return "可协商"
    if "不接受异地" in text or any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS):
        return "不接受"
    if "接受" in text:
        return "接受"
    return text


def normalize_city_token(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if text.endswith("市") and len(text) >= 3:
        text = text[:-1]
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
        return None
    if text in CITY_TOKEN_BLOCKLIST:
        return None
    if any(marker in text for marker in CITY_TOKEN_BLOCK_SUBSTRINGS):
        return None
    return text


def extract_city_preference_phrase_from_semantics(semantics_text: Any) -> Optional[str]:
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return None
    for segment in split_text_segments(semantics):
        for pattern in CITY_PREFERENCE_PATTERNS:
            match = pattern.search(segment)
            if not match:
                continue
            phrase = clean_text(match.group("phrase"))
            city_tokens = [
                normalize_city_token(token)
                for token in re.split(r"(?:或|/|、|和|及)", match.groupdict().get("cities") or match.groupdict().get("city") or "")
            ]
            city_tokens = [token for token in city_tokens if token]
            if city_tokens:
                return phrase
    return None


def extract_region_preference_phrase_from_semantics(semantics_text: Any) -> Optional[str]:
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return None
    for segment in split_text_segments(semantics):
        for region in REGIONAL_CITY_EXPANSIONS:
            match = re.search(rf"({re.escape(region)}(?:范围内)?优先)", segment)
            if match:
                return clean_text(match.group(1))
    return None


def extract_city_candidates_from_semantics(*texts: Any) -> List[str]:
    candidates: List[str] = []
    for text in texts:
        phrase = extract_city_preference_phrase_from_semantics(text)
        if not phrase:
            continue
        city_part = re.sub(r"(?:都可以|都可|均可|优先)$", "", phrase)
        for token in re.split(r"(?:或|/|、|和|及)", city_part):
            normalized = normalize_city_token(token)
            if normalized:
                candidates.append(normalized)
    return unique_ordered(candidates)


def build_public_city_preference_phrase(known_cities: Iterable[str], semantics_text: Any) -> Optional[str]:
    semantic_phrase = extract_city_preference_phrase_from_semantics(semantics_text)
    region_phrase = extract_region_preference_phrase_from_semantics(semantics_text)
    cities = [city for city in known_cities if clean_text(city)]
    semantics = clean_text(semantics_text) or ""

    base_phrase: Optional[str] = None
    if semantic_phrase:
        base_phrase = semantic_phrase
    elif region_phrase:
        base_phrase = region_phrase
    elif cities:
        if len(cities) == 1:
            base_phrase = f"{cities[0]}优先"
        elif len(cities) == 2:
            suffix = "都可以" if "都可以" in semantics else "优先"
            base_phrase = f"{cities[0]}或{cities[1]}{suffix}"
        else:
            base_phrase = "、".join(cities[:3]) + "优先"

    suffixes: List[str] = []
    if "稳定留沪" in semantics:
        suffixes.append("也接受明确留沪")
    if "双城过渡" in semantics:
        if "见面成本" in semantics:
            suffixes.append("也接受低成本双城过渡")
        else:
            suffixes.append("也接受双城过渡")

    if not base_phrase:
        if suffixes:
            return "，".join(unique_ordered(suffixes))
        return None

    for suffix in unique_ordered(suffixes):
        if suffix not in base_phrase:
            base_phrase += f"，{suffix}"
    return base_phrase


def contains_any_marker(texts: Iterable[Any], markers: Iterable[str]) -> bool:
    normalized_texts = [clean_text(text) or "" for text in texts]
    return any(marker in text for text in normalized_texts for marker in markers)


def split_text_segments(value: Any) -> List[str]:
    text = clean_text(value)
    if not text:
        return []
    segments: List[str] = []
    for block in re.split(r"[。；;\n]+", text):
        for part in re.split(r"[，,]+", block):
            normalized = clean_text(part.strip("，,。；; "))
            if normalized:
                segments.append(normalized)
    return unique_ordered(segments)


def has_location_signal(segment: Any, known_cities: Optional[Iterable[str]] = None) -> bool:
    text = clean_text(segment) or ""
    if not text:
        return False
    if extract_city_preference_phrase_from_semantics(text):
        return True
    if extract_region_preference_phrase_from_semantics(text):
        return True
    cities = [city for city in (known_cities or []) if clean_text(city)]
    if any(city in text for city in cities):
        return True
    return any(marker in text for marker in LOCATION_NUANCE_MARKERS)


def extract_location_semantics(
    *texts: Any,
    known_cities: Optional[Iterable[str]] = None,
) -> Optional[str]:
    segments: List[str] = []
    for text in texts:
        for segment in split_text_segments(text):
            if has_location_signal(segment, known_cities=known_cities):
                segments.append(segment)
    unique_segments = unique_ordered(segments)
    return "；".join(unique_segments) if unique_segments else None


def build_public_location_note(persona: Dict[str, Any]) -> Optional[str]:
    known_cities = split_multi_value(persona.get("target_cities"))
    explicit_distance_value = clean_text(persona.get("target_accept_long_distance"))
    semantics = "；".join(
        unique_ordered(
            [
                item
                for item in (
                    clean_text(persona.get("target_location_semantics")),
                    extract_location_semantics(
                        persona.get("public_preference_summary_draft"),
                        persona.get("preference_summary_internal"),
                        known_cities=known_cities,
                    ),
                )
                if item
            ]
        )
    )
    explicit_distance_boundary = clean_text(persona.get("target_accept_long_distance")) == "不接受"
    has_landing_plan = any(marker in semantics for marker in ("落地计划", "稳定留沪", "双城过渡", "落地"))
    allows_short_term = "短期异地" in semantics
    blocks_long_term = any(pattern.search(semantics) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)
    explicit_boundary_from_text = "不接受异地" in semantics or blocks_long_term
    needs_real_world_meetup = any(
        marker in semantics for marker in ("正常见面", "推进关系", "见面成本不能太高", "见面成本")
    )

    if explicit_distance_value in {
        "短期通勤可了解，长期异地谨慎",
        "短期可了解，长期异地不接受",
        "近距离可推进，长期异地不接受",
    }:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in explicit_distance_value:
            return f"{city_note}；{explicit_distance_value}"
        return explicit_distance_value
    if blocks_long_term and (allows_short_term or has_landing_plan):
        note = (
            "明确不接受长期异地；如有短期过渡，需明确落地计划"
            if explicit_distance_boundary
            else "短期异地可了解，但需要明确落地计划；不接受长期异地"
        )
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_boundary_from_text and needs_real_world_meetup:
        note = "原则上不接受异地；需能正常见面并推进关系"
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if blocks_long_term:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "不接受长期异地"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if has_landing_plan and "异地" in semantics:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "异地需有明确落地计划"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_boundary_from_text:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "原则上不接受异地"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_distance_boundary:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "更适合同城或近距离认真相处"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if any(marker in semantics for marker in ("同城", "近距离", "周边", "通勤")):
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "更适合同城或近距离认真相处"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    return None


def enrich_patch_from_explicit_semantics(patch: Dict[str, Any]) -> Dict[str, Any]:
    enriched = deepcopy(patch)
    marital_status = clean_text(enriched.get("self_marital_status"))
    inferred_children_from_status = infer_children_state_from_marital_status(marital_status)
    normalized_marital_status = normalize_self_marital_status_label(marital_status)
    if normalized_marital_status and normalized_marital_status != marital_status:
        enriched["self_marital_status"] = normalized_marital_status
    if (
        inferred_children_from_status is not None
        and enriched.get("self_has_children") in {None, ""}
    ):
        enriched["self_has_children"] = inferred_children_from_status

    text_candidates = [
        enriched.get("persona_summary_internal"),
        enriched.get("preference_summary_internal"),
        enriched.get("public_preference_summary_draft"),
        enriched.get("public_profile_summary_draft"),
    ]
    list_candidates = (
        split_multi_value(enriched.get("must_have_tags"))
        + split_multi_value(enriched.get("preferred_traits"))
        + split_multi_value(enriched.get("disliked_traits"))
    )
    has_children = bool_is_true(enriched.get("self_has_children")) or bool_is_true(
        enriched.get("self_children_count")
    )

    if enriched.get("self_children_count") in {None, ""}:
        inferred_count = extract_children_count_from_text(*text_candidates)
        if inferred_count is not None:
            enriched["self_children_count"] = inferred_count

    if enriched.get("self_children_living_with_self") in {None, ""}:
        inferred_living = extract_children_living_with_self_from_text(*text_candidates)
        if inferred_living is not None:
            enriched["self_children_living_with_self"] = inferred_living

    partner_must_accept_my_children = contains_any_marker(
        text_candidates + list_candidates,
        PARENT_REALITY_REQUIRED_MARKERS,
    )
    accepts_partner_with_children = contains_any_marker(
        text_candidates + list_candidates,
        PARTNER_HAS_CHILDREN_MARKERS,
    )

    if has_children and partner_must_accept_my_children:
        enriched["target_requires_partner_accept_my_children"] = 1
        if clean_text(enriched.get("target_accept_partner_children")) and not accepts_partner_with_children:
            enriched["target_accept_partner_children"] = None
            if "target_accept_partner_children_strength" in enriched:
                enriched["target_accept_partner_children_strength"] = None

    if (
        clean_text(enriched.get("target_location_semantics")) is None
        and clean_text(enriched.get("preference_summary_internal"))
        and contains_any_marker(text_candidates, LOCATION_NUANCE_MARKERS)
    ):
        enriched["target_location_semantics"] = extract_location_semantics(
            enriched.get("preference_summary_internal"),
            enriched.get("public_preference_summary_draft"),
            known_cities=split_multi_value(enriched.get("target_cities")),
        )

    expanded_target_cities = expand_regional_target_cities(
        enriched.get("target_cities"),
        enriched.get("target_location_semantics"),
        enriched.get("preference_summary_internal"),
    )
    if expanded_target_cities:
        enriched["target_cities"] = expanded_target_cities

    inferred_target_long_distance = infer_target_long_distance_value(
        enriched.get("target_accept_long_distance"),
        enriched.get("target_location_semantics"),
    )
    if inferred_target_long_distance:
        enriched["target_accept_long_distance"] = inferred_target_long_distance

    inferred_marital_strength = infer_target_marital_status_strength(
        enriched.get("target_marital_status_strength"),
        enriched.get("target_marital_statuses"),
        enriched.get("preference_summary_internal"),
        enriched.get("public_preference_summary_draft"),
        enriched.get("persona_summary_internal"),
    )
    if inferred_marital_strength:
        enriched["target_marital_status_strength"] = inferred_marital_strength

    return enriched


def is_soft_requirement_tag(tag: Any) -> bool:
    text = clean_text(tag)
    if not text:
        return False
    if text in SOFT_REQUIREMENT_TAGS:
        return True
    return any(marker in text for marker in SOFT_REQUIREMENT_MARKERS)


def rebalance_soft_requirement_tags(patch: Dict[str, Any]) -> Dict[str, Any]:
    normalized_patch = deepcopy(patch)
    if "must_have_tags" not in normalized_patch:
        return normalized_patch

    must_have_items = split_multi_value(normalized_patch.get("must_have_tags"))
    preferred_items = split_multi_value(normalized_patch.get("preferred_traits"))
    requires_accepting_my_children = normalize_boolish(
        normalized_patch.get("target_requires_partner_accept_my_children")
    ) == 1
    hard_must_have: List[str] = []
    soft_must_have: List[str] = []
    for item in must_have_items:
        if requires_accepting_my_children and contains_any_marker(
            [item], PARENT_REALITY_REQUIRED_MARKERS
        ):
            soft_must_have.append(item)
        elif is_soft_requirement_tag(item):
            soft_must_have.append(item)
        else:
            hard_must_have.append(item)

    if soft_must_have:
        normalized_patch["must_have_tags"] = hard_must_have
        normalized_patch["preferred_traits"] = preferred_items + soft_must_have
    return normalized_patch


def csv_from_items(items: Iterable[str]) -> Optional[str]:
    normalized = split_multi_value(list(items))
    return ",".join(normalized) if normalized else None


def items_from_csv(value: Any) -> List[str]:
    return split_multi_value(value)


def parse_patch_json(raw_json: Optional[str] = None, patch_file: Optional[str] = None) -> Dict[str, Any]:
    if bool(raw_json) == bool(patch_file):
        raise ValueError("Provide exactly one of --patch-json or --patch-file.")
    if patch_file:
        with open(patch_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(raw_json or "{}")


def normalize_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    patch = enrich_patch_from_explicit_semantics(patch)
    patch = rebalance_soft_requirement_tags(patch)
    normalized: Dict[str, Any] = {}
    for key, value in patch.items():
        if key not in USER_PERSONA_FIELDS:
            raise ValueError(f"Unsupported persona field: {key}")
        if key in LIST_FIELDS:
            normalized[key] = csv_from_items(split_multi_value(value))
        elif key in BOOL_FIELDS:
            normalized[key] = normalize_boolish(value)
        elif key in INT_FIELDS:
            normalized[key] = as_int(value)
        else:
            normalized[key] = clean_text(value)
            if key == "self_life_rhythm":
                normalized[key] = canonicalize_life_rhythm(normalized[key])
            elif key == "self_work_pattern":
                normalized[key] = canonicalize_work_pattern(normalized[key])
            elif key == "self_expression_style":
                normalized[key] = canonicalize_expression_style(normalized[key])
            if key == "target_accept_partner_children":
                normalized[key] = canonicalize_child_acceptance_state(normalized[key])
    return normalized


def merge_persona(existing: Optional[Dict[str, Any]], patch: Dict[str, Any], source_type: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    existing = deepcopy(existing or {})
    merged = deepcopy(existing)
    field_results: List[Dict[str, Any]] = []

    if source_type not in {"explicit", "strong_inference", "weak_inference"}:
        raise ValueError(f"Unsupported source_type: {source_type}")

    for field_name, new_value in patch.items():
        old_value = merged.get(field_name)
        action_type = "skip"
        applied = False
        note = ""

        if source_type == "weak_inference":
            note = "weak_inference_only"
        elif field_name in LIST_FIELDS:
            old_items = items_from_csv(old_value)
            new_items = items_from_csv(new_value)
            if source_type == "explicit":
                candidate_value = csv_from_items(new_items)
            elif field_name in INFERENCE_MUTABLE_LIST_FIELDS:
                candidate_value = csv_from_items(old_items + new_items)
            else:
                candidate_value = old_value
                note = "explicit_only_list"
            if candidate_value != old_value and note == "":
                merged[field_name] = candidate_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
            elif note == "":
                note = "no_change"
        else:
            if source_type == "explicit":
                candidate_value = new_value
            elif field_name in STRONG_INFERENCE_MUTABLE_SCALARS or field_name in SOFT_SELF_DESCRIPTION_FIELDS:
                candidate_value = new_value
            elif field_name in EXPLICIT_ONLY_FIELDS:
                candidate_value = old_value
                note = "explicit_only_scalar"
            else:
                candidate_value = old_value
                note = "not_mutable"
            if note == "" and candidate_value != old_value:
                merged[field_name] = candidate_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
            elif note == "":
                note = "no_change"

        field_results.append(
            {
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "stored_value": merged.get(field_name),
                "action_type": action_type,
                "applied_to_persona": applied,
                "note": note,
            }
        )

    merged = sanitize_persona_summary_fields(merged)
    for item in field_results:
        item["stored_value"] = merged.get(item["field_name"])

    merged["updated_at"] = now_string()
    if source_type == "explicit":
        merged["last_confirmed_at"] = merged["updated_at"]
    elif source_type == "strong_inference":
        merged["last_inferred_at"] = merged["updated_at"]
    return merged, field_results


def income_wan_to_range(value: Any) -> Optional[str]:
    amount = as_int(value)
    if amount is None:
        return None
    if amount <= 10:
        return "0-10万/年"
    floor = max(0, (amount // 5) * 5 - 4)
    ceiling = floor + 9
    if amount % 5 == 0:
        floor = amount - 4
        ceiling = amount + 5
    return f"{floor}-{ceiling}万/年"


def append_matcher_features(target: Dict[str, Any], feature_map: Dict[str, Any]) -> None:
    for key, value in feature_map.items():
        target[key] = value


def build_matcher_payload(persona: Dict[str, Any]) -> Dict[str, Optional[str]]:
    must_have = items_from_csv(persona.get("must_have_tags"))
    must_not_have = items_from_csv(persona.get("must_not_have_tags"))
    preferred_traits = items_from_csv(persona.get("preferred_traits"))
    disliked_traits = items_from_csv(persona.get("disliked_traits"))
    target_cities = items_from_csv(persona.get("target_cities"))
    target_statuses = items_from_csv(persona.get("target_marital_statuses"))

    matcher_traits = {
        "self_city": persona.get("self_city"),
        "self_relationship_goal": persona.get("self_relationship_goal"),
        "self_smoking": persona.get("self_smoking"),
        "self_drinking": persona.get("self_drinking"),
        "self_life_rhythm": persona.get("self_life_rhythm"),
        "self_work_pattern": persona.get("self_work_pattern"),
        "self_expression_style": persona.get("self_expression_style"),
        "same_city_priority": "high" if len(target_cities) == 1 else "normal",
    }
    matcher_preferences = {
        "target_gender": persona.get("target_gender"),
        "target_cities": target_cities,
        "target_age_min": persona.get("target_age_min"),
        "target_age_max": persona.get("target_age_max"),
        "target_height_min": persona.get("target_height_min"),
        "target_height_max": persona.get("target_height_max"),
        "target_education_min": persona.get("target_education_min"),
        "target_income_min_wan": persona.get("target_income_min_wan"),
        "target_income_max_wan": persona.get("target_income_max_wan"),
        "target_marital_statuses": target_statuses,
        "target_marital_status_strength": persona.get("target_marital_status_strength"),
        "target_marital_status_semantics": marital_acceptance_semantics_label(
            persona.get("target_marital_statuses"),
            persona.get("target_marital_status_strength"),
        ),
        "target_accept_partner_children": canonicalize_child_acceptance_state(
            persona.get("target_accept_partner_children")
        ),
        "target_accept_partner_children_strength": persona.get("target_accept_partner_children_strength"),
        "target_accept_partner_children_semantics": acceptance_semantics_label(
            persona.get("target_accept_partner_children"),
            persona.get("target_accept_partner_children_strength"),
        ),
        "target_accept_long_distance": persona.get("target_accept_long_distance"),
        "target_location_semantics": clean_text(persona.get("target_location_semantics")),
        "target_requires_partner_accept_my_children": normalize_boolish(
            persona.get("target_requires_partner_accept_my_children")
        ),
        "must_have_tags": must_have,
        "preferred_traits": preferred_traits,
    }
    matcher_risks = {
        "must_not_have_tags": must_not_have,
        "disliked_traits": disliked_traits,
    }

    for tag in must_have + preferred_traits:
        append_matcher_features(matcher_preferences, POSITIVE_TAG_TO_MATCHER.get(tag, {}))
    for tag in must_not_have + disliked_traits:
        append_matcher_features(matcher_risks, RAW_NEGATIVE_TO_MATCHER.get(tag, {}))

    summary_parts = []
    if clean_text(persona.get("persona_summary_internal")):
        summary_parts.append(clean_text(persona.get("persona_summary_internal")))
    for field_name in ("self_life_rhythm", "self_work_pattern", "self_expression_style"):
        if clean_text(persona.get(field_name)):
            summary_parts.append(f"{field_name}: {clean_text(persona.get(field_name))}")
    if clean_text(persona.get("preference_summary_internal")):
        summary_parts.append(clean_text(persona.get("preference_summary_internal")))
    if must_have:
        summary_parts.append("must_have: " + ", ".join(must_have))
    if must_not_have:
        summary_parts.append("must_not_have: " + ", ".join(must_not_have))

    return {
        "matcher_traits_json": json.dumps(matcher_traits, ensure_ascii=False, sort_keys=True),
        "matcher_preferences_json": json.dumps(matcher_preferences, ensure_ascii=False, sort_keys=True),
        "matcher_risks_json": json.dumps(matcher_risks, ensure_ascii=False, sort_keys=True),
        "matcher_summary_internal": " | ".join(part for part in summary_parts if part) or None,
    }


_public_profile_helpers = PublicProfileHelpers(
    PublicProfileRuntime(
        as_int=as_int,
        clean_text=clean_text,
        normalize_boolish=normalize_boolish,
        split_multi_value=split_multi_value,
        unique_ordered=unique_ordered,
        items_from_csv=items_from_csv,
        build_public_location_note=build_public_location_note,
        split_text_segments=split_text_segments,
        has_location_signal=has_location_signal,
        public_safe_tag_map=PUBLIC_SAFE_TAG_MAP,
        public_job_patterns=PUBLIC_JOB_PATTERNS,
        public_value_priority_tags=PUBLIC_VALUE_PRIORITY_TAGS,
        public_safe_negative_notes=PUBLIC_SAFE_NEGATIVE_NOTES,
        safe_public_personality_patterns=SAFE_PUBLIC_PERSONALITY_PATTERNS,
        safe_structured_personality_labels=SAFE_STRUCTURED_PERSONALITY_LABELS,
        observation_field_labels=OBSERVATION_FIELD_LABELS,
    )
)

public_safe_tag = _public_profile_helpers.public_safe_tag
build_public_job_title = _public_profile_helpers.build_public_job_title
build_public_education = _public_profile_helpers.build_public_education
build_public_display_name = _public_profile_helpers.build_public_display_name
sanitize_internal_profile_summary = _public_profile_helpers.sanitize_internal_profile_summary
build_legacy_public_personality = _public_profile_helpers.build_legacy_public_personality
build_public_city_phrase = _public_profile_helpers.build_public_city_phrase
build_public_relationship_goal = _public_profile_helpers.build_public_relationship_goal
sanitize_public_profile_summary = _public_profile_helpers.sanitize_public_profile_summary
sanitize_public_preference_summary = _public_profile_helpers.sanitize_public_preference_summary
observation_field_label = _public_profile_helpers.observation_field_label
summarize_observation_evidence = _public_profile_helpers.summarize_observation_evidence
sanitize_persona_summary_fields = _public_profile_helpers.sanitize_persona_summary_fields
extract_safe_public_personality_traits = _public_profile_helpers.extract_safe_public_personality_traits
build_public_profile = _public_profile_helpers.build_public_profile


def build_profile_payload(
    persona: Dict[str, Any],
    existing_profile: Optional[Dict[str, Any]] = None,
    include_null_persona_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    existing_profile = existing_profile or {}
    include_null_persona_fields = set(include_null_persona_fields or [])
    payload: Dict[str, Any] = {}
    for persona_field, profile_field in PERSONA_TO_PROFILE_FIELD_MAP.items():
        value = persona.get(persona_field)
        if value is not None or persona_field in include_null_persona_fields:
            payload[profile_field] = value

    if persona.get("self_income_wan") is not None:
        payload["income_range"] = income_wan_to_range(persona.get("self_income_wan"))
    if persona.get("target_accept_long_distance") is not None:
        canonical_long_distance = canonicalize_long_distance_state(
            persona.get("target_accept_long_distance")
        )
        payload["long_distance"] = canonical_long_distance
        payload["accept_long_distance"] = canonical_long_distance
    if persona.get("target_accept_partner_children") is not None:
        payload["accept_partner_children"] = canonicalize_child_acceptance_state(
            persona.get("target_accept_partner_children")
        )
    if (
        persona.get("target_accept_partner_children") is not None
        or "target_accept_partner_children" in include_null_persona_fields
        or "target_accept_partner_children_strength" in include_null_persona_fields
    ):
        payload["accept_partner_children_semantics"] = acceptance_semantics_label(
            persona.get("target_accept_partner_children"),
            persona.get("target_accept_partner_children_strength"),
        )
    if persona.get("target_marital_statuses") is not None:
        payload["accept_marital_status"] = persona.get("target_marital_statuses")
    if (
        persona.get("target_marital_statuses") is not None
        or "target_marital_statuses" in include_null_persona_fields
        or "target_marital_status_strength" in include_null_persona_fields
    ):
        payload["accept_marital_status_semantics"] = marital_acceptance_semantics_label(
            persona.get("target_marital_statuses"),
            persona.get("target_marital_status_strength"),
        )

    public_payload = build_public_profile(persona)
    matcher_payload = build_matcher_payload(persona)
    payload.update(public_payload)
    payload.update(matcher_payload)
    must_have = items_from_csv(persona.get("must_have_tags"))
    must_not_have = items_from_csv(persona.get("must_not_have_tags"))
    preferred_traits = items_from_csv(persona.get("preferred_traits"))
    disliked_traits = items_from_csv(persona.get("disliked_traits"))

    existing_personality = clean_text(existing_profile.get("personality"))
    legacy_personality = build_legacy_public_personality(persona)
    sanitized_persona_summary = sanitize_internal_profile_summary(
        persona.get("persona_summary_internal"),
        persona,
    )
    if sanitized_persona_summary:
        internal_personality = sanitized_persona_summary
    elif existing_personality and existing_personality != legacy_personality:
        internal_personality = (
            sanitize_internal_profile_summary(existing_personality, persona)
            or existing_personality
        )
    else:
        internal_personality = public_payload["public_personality"]

    if clean_text(persona.get("preference_summary_internal")):
        internal_values = clean_text(persona.get("preference_summary_internal"))
    else:
        value_fragments = []
        if must_have:
            value_fragments.append("看重" + "、".join(must_have[:3]))
        if preferred_traits:
            value_fragments.append("偏好" + "、".join(preferred_traits[:3]))
        if persona.get("target_accept_long_distance") == "不接受":
            value_fragments.append("异地推进需要同城前提")
        internal_values = (
            "；".join(value_fragments)
            or clean_text(existing_profile.get("values"))
            or public_payload["public_values"]
        )

    internal_note_parts = []
    if must_not_have:
        internal_note_parts.append("明确避开" + "、".join(must_not_have[:5]))
    note_disliked_traits = [item for item in disliked_traits if item not in set(must_not_have)]
    if note_disliked_traits:
        internal_note_parts.append("不太接受" + "、".join(note_disliked_traits[:5]))
    if persona.get("target_marital_statuses"):
        marital_note = f"可接受婚况={persona.get('target_marital_statuses')}"
        if clean_text(persona.get("target_marital_status_strength")):
            marital_note += f"（{persona.get('target_marital_status_strength')}）"
        internal_note_parts.append(marital_note)
    if persona.get("target_accept_partner_children"):
        child_note = format_acceptance_note(
            persona.get("target_accept_partner_children"),
            persona.get("target_accept_partner_children_strength"),
        )
        internal_note_parts.append(f"你对对方孩子情况={child_note}")
    if (
        normalize_boolish(persona.get("target_requires_partner_accept_my_children")) == 1
        and (
            normalize_boolish(persona.get("self_has_children")) == 1
            or (as_int(persona.get("self_children_count")) or 0) > 0
        )
    ):
        internal_note_parts.append("对方需能接受你的孩子现实")
    internal_notes = (
        "；".join(internal_note_parts)
        or clean_text(existing_profile.get("notes"))
        or matcher_payload["matcher_summary_internal"]
        or public_payload["public_notes"]
    )

    payload["personality"] = internal_personality
    payload["values"] = internal_values
    payload["notes"] = internal_notes
    payload["name"] = clean_text(persona.get("display_name")) or clean_text(existing_profile.get("name")) or clean_text(persona.get("user_key")) or "未命名"
    payload["public_display_name"] = (
        clean_text(existing_profile.get("public_display_name"))
        or build_public_display_name(persona.get("profile_id") or existing_profile.get("id"))
    )
    payload["source_channel"] = clean_text(existing_profile.get("source_channel")) or "persona-memory-sync"
    payload["profile_status"] = clean_text(existing_profile.get("profile_status")) or "active"
    payload["verified_level"] = clean_text(existing_profile.get("verified_level")) or "none"
    payload["last_active_at"] = now_string()
    return payload


def mark_profile_sync_results(
    field_results: List[Dict[str, Any]],
    *,
    synced_profile: bool,
) -> List[Dict[str, Any]]:
    for item in field_results:
        item["applied_to_profile"] = bool(
            synced_profile
            and item.get("applied_to_persona")
            and persona_field_affects_profile(item.get("field_name", ""))
        )
    return field_results


def insert_profile_stub(cursor, profile_table: str, payload: Dict[str, Any]) -> int:
    insert_params = (
        payload["name"],
        payload["profile_status"],
        payload["verified_level"],
        payload["source_channel"],
        payload["last_active_at"],
    )
    insert_sql = f"""
        INSERT INTO {quote_mysql_ident(profile_table)}
          (name, profile_status, verified_level, source_channel, last_active_at)
        VALUES (%s, %s, %s, %s, %s)
        """
    try:
        cursor.execute(insert_sql, insert_params)
    except Exception as exc:
        error_text = str(exc)
        if "doesn't have a default value" not in error_text or "'id'" not in error_text:
            raise
        cursor.execute(
            f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {quote_mysql_ident(profile_table)}"
        )
        row = cursor.fetchone() or {}
        next_id = as_int(row.get("next_id") if isinstance(row, dict) else None)
        if next_id is None:
            raise ValueError(f"Could not allocate a fallback profile id from {profile_table}.") from exc
        cursor.execute(
            f"""
            INSERT INTO {quote_mysql_ident(profile_table)}
              (id, name, profile_status, verified_level, source_channel, last_active_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (next_id,) + insert_params,
        )
        return int(next_id)
    profile_id = getattr(cursor, "lastrowid", None)
    if not profile_id:
        raise ValueError(
            f"Could not allocate a profile id from {profile_table}. Ensure profiles.id is AUTO_INCREMENT."
        )
    return int(profile_id)


def fetch_persona(
    cursor,
    persona_table: str,
    *,
    user_key: Optional[str] = None,
    profile_id: Optional[int] = None,
):
    if user_key:
        cursor.execute(
            f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
            (user_key,),
        )
        return cursor.fetchone()
    if profile_id is not None:
        cursor.execute(
            f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE profile_id = %s",
            (profile_id,),
        )
        return cursor.fetchone()
    raise ValueError("Provide user_key or profile_id to fetch a persona.")


def fetch_profile(cursor, profile_table: str, profile_id: int):
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
        (profile_id,),
    )
    return cursor.fetchone()


def fetch_public_profile(cursor, public_view_name: str, profile_id: int):
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(public_view_name)} WHERE id = %s LIMIT 1",
        (profile_id,),
    )
    return cursor.fetchone()


def upsert_persona(cursor, persona_table: str, merged_persona: Dict[str, Any]):
    payload = {key: value for key, value in merged_persona.items() if key not in {"id", "created_at"}}
    columns = list(payload.keys())
    values = [payload[column] for column in columns]
    update_clause = ", ".join(
        f"{quote_mysql_ident(column)} = VALUES({quote_mysql_ident(column)})" for column in columns
    )
    cursor.execute(
        f"""
        INSERT INTO {quote_mysql_ident(persona_table)} ({", ".join(quote_mysql_ident(column) for column in columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        ON DUPLICATE KEY UPDATE {update_clause}
        """,
        values,
    )
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
        (merged_persona["user_key"],),
    )
    return cursor.fetchone()


def insert_observations(
    cursor,
    observation_table: str,
    *,
    user_key: str,
    persona_id,
    source_type: str,
    confidence_score,
    evidence_text,
    conversation_ref,
    field_results: List[Dict[str, Any]],
):
    for item in field_results:
        sanitized_evidence = summarize_observation_evidence(
            item["field_name"],
            item["new_value"],
            evidence_text,
        )
        cursor.execute(
            f"""
            INSERT INTO {quote_mysql_ident(observation_table)}
              (user_key, persona_id, field_name, field_value, source_type, confidence_score,
               evidence_text, conversation_ref, action_type, applied_to_persona, applied_to_profile, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_key,
                persona_id,
                item["field_name"],
                item["new_value"],
                source_type,
                confidence_score,
                sanitized_evidence,
                conversation_ref,
                item["action_type"],
                1 if item["applied_to_persona"] else 0,
                1 if item.get("applied_to_profile") else 0,
                now_string(),
            ),
        )


def apply_observation_only_scope(
    existing_persona: Optional[Dict[str, Any]],
    field_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    existing_persona = dict(existing_persona or {})
    for item in field_results:
        if item.get("applied_to_persona"):
            item["applied_to_persona"] = False
            note = str(item.get("note") or "").strip()
            item["note"] = f"{note};observation_only_scope" if note else "observation_only_scope"
        item["stored_value"] = existing_persona.get(item["field_name"])
    return field_results


def ensure_persona_profile_binding(cursor, persona_table: str, profile_table: str, persona: Dict[str, Any]) -> int:
    profile_id = as_int(persona.get("profile_id"))
    if profile_id is not None:
        return profile_id

    initial_payload = build_profile_payload(persona, existing_profile={})
    profile_id = insert_profile_stub(cursor, profile_table, initial_payload)
    cursor.execute(
        f"UPDATE {quote_mysql_ident(persona_table)} SET profile_id = %s WHERE id = %s",
        (profile_id, persona["id"]),
    )
    persona["profile_id"] = profile_id
    return profile_id


def upsert_profile(cursor, profile_table: str, payload: Dict[str, Any], profile_id: int, force_columns=None) -> List[str]:
    existing = fetch_profile(cursor, profile_table, profile_id)
    if existing is None:
        cursor.execute(
            f"""
            INSERT INTO {quote_mysql_ident(profile_table)}
              (id, name, profile_status, verified_level, source_channel, last_active_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                profile_id,
                payload["name"],
                payload["profile_status"],
                payload["verified_level"],
                payload["source_channel"],
                payload["last_active_at"],
            ),
        )
        existing = {}

    force_columns = set(force_columns or [])
    update_columns = [column for column, value in payload.items() if value is not None or column in force_columns]
    cursor.execute(
        f"""
        UPDATE {quote_mysql_ident(profile_table)}
        SET {", ".join(f"{quote_mysql_ident(column)} = %s" for column in update_columns)}
        WHERE id = %s
        """,
        [payload[column] for column in update_columns] + [profile_id],
    )
    return update_columns


def write_public_profile_fields(cursor, profile_table: str, profile_id: int, profile_payload: Dict[str, Any]) -> List[str]:
    update_columns = [
        "public_display_name",
        "public_education",
        "public_job",
        "public_personality",
        "public_values",
        "public_notes",
        "personality",
        "values",
        "notes",
    ]
    cursor.execute(
        f"""
        UPDATE {quote_mysql_ident(profile_table)}
        SET {", ".join(f"{quote_mysql_ident(column)} = %s" for column in update_columns)}
        WHERE id = %s
        """,
        [profile_payload[column] for column in update_columns] + [profile_id],
    )
    return update_columns


def apply_persona_patch(
    *,
    source: Optional[str],
    user_key: str,
    source_type: str,
    normalized_patch: Dict[str, Any],
    persona_table: str = DEFAULT_PERSONA_TABLE,
    observation_table: str = DEFAULT_OBSERVATION_TABLE,
    profile_table: Optional[str] = None,
    confidence_score=None,
    evidence_text=None,
    conversation_ref=None,
    apply_scope: str = "persona_only",
    sync_profile: bool = False,
) -> Dict[str, Any]:
    if apply_scope not in VALID_APPLY_SCOPES:
        raise ValueError(f"Unsupported apply_scope: {apply_scope}")
    profile_table = profile_table or parse_mysql_source(source)["table"]
    conn = mysql_connect(source)
    profile_synced = False
    field_results: List[Dict[str, Any]] = []
    try:
        with conn.cursor() as cursor:
            existing = fetch_persona(cursor, persona_table, user_key=user_key)
            base = dict(existing or {})
            base["user_key"] = user_key
            merged, field_results = merge_persona(base, normalized_patch, source_type)
            saved_persona = None
            persona_id = existing["id"] if existing else None

            if apply_scope == "observation_only":
                apply_observation_only_scope(existing, field_results)
            else:
                merged["user_key"] = user_key
                saved_persona = upsert_persona(cursor, persona_table, merged)
                persona_id = saved_persona["id"]

                if apply_scope == "persona_and_profile" and sync_profile and source_type != "weak_inference":
                    persona_for_profile = dict(saved_persona)
                    persona_for_profile["user_key"] = user_key
                    profile_id = ensure_persona_profile_binding(
                        cursor,
                        persona_table,
                        profile_table,
                        persona_for_profile,
                    )
                    existing_profile = fetch_profile(cursor, profile_table, profile_id) or {}
                    payload = build_profile_payload(
                        persona_for_profile,
                        existing_profile=existing_profile,
                        include_null_persona_fields=normalized_patch.keys(),
                    )
                    upsert_profile(
                        cursor,
                        profile_table,
                        payload,
                        profile_id,
                        force_columns=profile_columns_for_persona_patch(normalized_patch),
                    )
                    profile_synced = True

            mark_profile_sync_results(field_results, synced_profile=profile_synced)
            insert_observations(
                cursor,
                observation_table,
                user_key=user_key,
                persona_id=persona_id,
                source_type=source_type,
                confidence_score=confidence_score,
                evidence_text=evidence_text,
                conversation_ref=conversation_ref,
                field_results=field_results,
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "user_key": user_key,
        "source_type": source_type,
        "apply_scope": apply_scope,
        "applied_fields": [item for item in field_results if item["applied_to_persona"]],
        "skipped_fields": [item for item in field_results if not item["applied_to_persona"]],
        "synced_profile": profile_synced,
    }


def sync_persona_profile(
    *,
    source: Optional[str],
    persona_table: str = DEFAULT_PERSONA_TABLE,
    profile_table: Optional[str] = None,
    user_key: Optional[str] = None,
    profile_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not user_key and profile_id is None:
        raise ValueError("Provide user_key or profile_id.")

    profile_table = profile_table or parse_mysql_source(source)["table"]
    conn = mysql_connect(source)
    summary: Dict[str, Any] = {}
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key, profile_id=profile_id)
            if not persona:
                raise ValueError("Persona not found.")

            bound_profile_id = as_int(persona.get("profile_id")) or profile_id
            if bound_profile_id is None:
                bound_profile_id = ensure_persona_profile_binding(
                    cursor,
                    persona_table,
                    profile_table,
                    persona,
                )
            else:
                persona["profile_id"] = bound_profile_id

            existing_profile = fetch_profile(cursor, profile_table, bound_profile_id) or {}
            payload = build_profile_payload(persona, existing_profile=existing_profile)
            update_columns = upsert_profile(
                cursor,
                profile_table,
                payload,
                bound_profile_id,
            )

            summary = {
                "user_key": persona["user_key"],
                "profile_id": bound_profile_id,
                "updated_columns": update_columns,
                "public_personality": payload.get("public_personality"),
                "public_values": payload.get("public_values"),
                "public_notes": payload.get("public_notes"),
            }

        conn.commit()
    finally:
        conn.close()

    return summary


def render_public_profile_result(
    *,
    source: Optional[str],
    persona_table: str = DEFAULT_PERSONA_TABLE,
    profile_table: Optional[str] = None,
    user_key: Optional[str] = None,
    profile_id: Optional[int] = None,
    write_profile: bool = False,
) -> Dict[str, Any]:
    if not user_key and profile_id is None:
        raise ValueError("Provide user_key or profile_id.")

    profile_table = profile_table or parse_mysql_source(source)["table"]
    conn = mysql_connect(source)
    output: Dict[str, Any] = {}
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key, profile_id=profile_id)
            if not persona:
                raise ValueError("Persona not found.")

            target_profile_id = as_int(persona.get("profile_id")) or as_int(profile_id)

            if write_profile:
                if target_profile_id is None:
                    target_profile_id = ensure_persona_profile_binding(
                        cursor,
                        persona_table,
                        profile_table,
                        persona,
                    )
                elif as_int(persona.get("profile_id")) is None and persona.get("id") is not None:
                    cursor.execute(
                        f"UPDATE {quote_mysql_ident(persona_table)} SET profile_id = %s WHERE id = %s",
                        (target_profile_id, persona["id"]),
                    )
                    persona["profile_id"] = target_profile_id
                else:
                    persona["profile_id"] = target_profile_id
                existing_profile = fetch_profile(cursor, profile_table, target_profile_id) or {}
                profile_payload = build_profile_payload(persona, existing_profile=existing_profile)
                write_public_profile_fields(
                    cursor,
                    profile_table,
                    target_profile_id,
                    profile_payload,
                )

            if target_profile_id is None:
                raise ValueError("Persona is not bound to a profile.")
            public_profile = fetch_public_profile(cursor, DEFAULT_PUBLIC_VIEW, target_profile_id)
            if not public_profile:
                raise ValueError(f"Public profile {target_profile_id} was not found in view {DEFAULT_PUBLIC_VIEW}.")
            output = {
                "user_key": persona["user_key"],
                "profile_id": target_profile_id,
                **public_profile,
            }

        conn.commit()
    finally:
        conn.close()

    return output


def build_public_profile_view_sql(profile_table: str = DEFAULT_PROFILE_TABLE, view_name: str = DEFAULT_PUBLIC_VIEW) -> str:
    profile_table_q = quote_mysql_ident(profile_table)
    view_name_q = quote_mysql_ident(view_name)
    return f"""
CREATE OR REPLACE VIEW {view_name_q} AS
SELECT
  id,
  COALESCE(
    NULLIF(TRIM(public_display_name), ''),
    CONCAT('用户', LPAD(MOD(id, 10000), 4, '0'))
  ) AS name,
  avatar_url,
  photo_count,
  gender,
  age,
  city,
  district,
  height,
  NULLIF(TRIM(public_education), '') AS education,
  COALESCE(
    public_job,
    CASE
      WHEN job REGEXP '医院|诊所|药师|医生|医师|护士|临床|医疗' THEN '医疗相关工作'
      WHEN job REGEXP '学校|教师|老师|教研|辅导员|教育|培训' THEN '教育相关工作'
      WHEN job REGEXP '银行|证券|基金|保险|金融' THEN '金融相关工作'
      WHEN job REGEXP '研究院|实验室|科研' THEN '科研相关工作'
      ELSE job
    END
  ) AS job,
  CAST(NULL AS CHAR(32)) AS income_range,
  CASE
    WHEN relationship_goal IS NULL OR TRIM(relationship_goal) = '' THEN NULL
    WHEN relationship_goal REGEXP '不着急|不仓促|不想仓促|先看相处|先看相处质量|慢慢来'
      AND relationship_goal REGEXP '再婚'
      THEN '认真相处，先看关系质量，合适再往婚姻走'
    WHEN relationship_goal REGEXP '不着急|不仓促|不想仓促|先看相处|先看相处质量|慢慢来'
      AND relationship_goal REGEXP '长期关系|长期'
      AND relationship_goal REGEXP '结婚|婚姻'
      THEN '认真相处，先看长期关系，合适再考虑婚姻'
    WHEN relationship_goal REGEXP '不着急|不仓促|不想仓促|先看相处|先看相处质量|慢慢来'
      AND relationship_goal REGEXP '长期关系|长期'
      THEN '认真相处，长期关系方向明确，不仓促推进'
    WHEN relationship_goal REGEXP '不着急|不仓促|不想仓促|先看相处|先看相处质量|慢慢来'
      AND relationship_goal REGEXP '结婚|婚姻'
      THEN '认真相处，方向明确，不仓促推进'
    WHEN relationship_goal REGEXP '现实关系'
      THEN '认真相处，长期现实关系方向明确'
    WHEN relationship_goal REGEXP '认真找长期关系' AND relationship_goal REGEXP '会考虑结婚'
      THEN '认真相处，先看长期关系，合适再考虑婚姻'
    WHEN relationship_goal REGEXP '[一二两三四五六七八九十]+年内' AND relationship_goal REGEXP '再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '[0-9]+[[:space:]]*(-|到|至|~)[[:space:]]*[0-9]+年内' AND relationship_goal REGEXP '再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '[0-9]+年内' AND relationship_goal REGEXP '再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '[一二两三四五六七八九十]+年内' AND relationship_goal REGEXP '结婚|再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '[0-9]+[[:space:]]*(-|到|至|~)[[:space:]]*[0-9]+年内' AND relationship_goal REGEXP '结婚|再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '[0-9]+年内' AND relationship_goal REGEXP '结婚|再婚'
      THEN '认真相处，合适就认真往后走'
    WHEN relationship_goal REGEXP '再婚' THEN '认真相处，合适再往婚姻走'
    WHEN relationship_goal REGEXP '长期关系' AND relationship_goal REGEXP '结婚|婚姻'
      THEN '认真相处，长期关系稳定了再往婚姻走'
    WHEN relationship_goal REGEXP '认真恋爱' AND relationship_goal REGEXP '结婚'
      THEN '认真相处，合适再往婚姻走'
    WHEN relationship_goal REGEXP '稳定结婚'
      THEN '认真相处，长期关系稳定了再往婚姻走'
    WHEN relationship_goal REGEXP '认真找长期关系'
      THEN '认真相处，重视长期稳定关系'
    WHEN relationship_goal = '结婚导向' THEN '认真相处，合适再往婚姻走'
    WHEN relationship_goal REGEXP '结婚' THEN '认真相处，合适再往婚姻走'
    WHEN relationship_goal REGEXP '认真恋爱|长期|稳定' THEN '认真相处，重视长期稳定关系'
    ELSE relationship_goal
  END AS relationship_goal,
  public_personality AS personality,
  public_values AS `values`,
  public_notes AS notes
FROM {profile_table_q}
""".strip()
