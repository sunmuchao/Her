#!/usr/bin/env python3

"""Search profile sources for partner candidates.

This module intentionally keeps product workflow concerns out of the matching
engine. The CLI remains available, but the search flow is split into small
helpers so callers can reuse loading, evaluation, and rendering separately.
"""

import argparse as _argparse
import os
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

from her_time_utils import coerce_int as as_int, unique_ordered_texts
from mysql_source_config import MYSQL_SCHEMES as MYSQL_SOURCE_SCHEMES
from partner_moderation import overlay_records_with_moderation
from partner_search.search_inputs import (
    KEYWORD_EVIDENCE_FIELDS,
    STRUCTURED_KEYWORD_SIGNAL_RULES,
    TEXTUAL_KEYWORD_SIGNAL_RULES,
    UNKNOWN_VALUES,
    as_lower,
    as_text,
    contains_any_text,
    evaluate_exclusion_keyword,
    field_display_name,
    first_defined,
    habit_requires_acceptance,
    merge_keyword_args,
    merge_keyword_values,
    normalize_acceptance_state,
    normalize_acceptance_strength,
    normalize_bool,
    normalize_strictness_state,
    normalize_whitespace,
    parse_json_object,
    split_evidence_segments,
    split_keywords,
    split_must_have_keywords,
)
from partner_search.search_sources import (
    SearchSourceRuntime,
    attach_photo_previews as _attach_photo_previews,
    build_mysql_prefilter as _build_mysql_prefilter,
    detect_mysql_profile_table as _detect_mysql_profile_table,
    load_mysql as _load_mysql,
    load_mysql_photo_previews as _load_mysql_photo_previews,
    load_source as _load_source,
    parse_mysql_source as _parse_mysql_source,
    quote_mysql_ident as _quote_mysql_ident,
    resolve_mysql_columns as _resolve_mysql_columns,
)
from partner_search.search_no_match import (
    SearchNoMatchRuntime,
    build_fallback_candidates as _build_fallback_candidates,
    build_no_match_diagnostics as _build_no_match_diagnostics,
    build_no_match_diagnostics_payload as _build_no_match_diagnostics_payload,
    build_rejection_reason as _build_rejection_reason,
    format_no_match_text as _format_no_match_text,
    format_rejection_reason as _format_rejection_reason,
    parse_rejection_reason as _parse_rejection_reason,
    suggestion_for_rejection as _suggestion_for_rejection,
)
from partner_search.search_ranking import (
    SearchRankingRuntime,
    build_match_result as _build_match_result,
    diversity_job_cluster as _diversity_job_cluster,
    diversity_penalty as _diversity_penalty,
    diversity_signature as _diversity_signature,
    record_ref as _record_ref,
    result_sort_key as _result_sort_key,
    select_diverse_results as _select_diverse_results,
    trim_low_quality_tail as _trim_low_quality_tail,
)
from partner_search.search_reciprocal import (
    SearchReciprocalRuntime,
    evaluate_reciprocal_compatibility as _evaluate_reciprocal_compatibility,
    exact_match as _exact_match,
    income_range_overlaps as _income_range_overlaps,
    match_any_exact as _match_any_exact,
    matcher_preference_tags as _matcher_preference_tags,
)
from partner_search.search_trust import (
    SearchTrustRuntime,
    activity_score_info as _activity_score_info,
    build_profile_consistency_flags as _build_profile_consistency_flags,
    build_trust_actions as _build_trust_actions,
    build_trust_caution_items as _build_trust_caution_items,
    build_trust_summary as _build_trust_summary,
    build_verification_items as _build_verification_items,
    format_income_range_text as _format_income_range_text,
    normalize_field_verification_status as _normalize_field_verification_status,
    photo_verification_level as _photo_verification_level,
    photo_verification_level_label as _photo_verification_level_label,
    profile_field_verification_raw_status as _profile_field_verification_raw_status,
    profile_field_verification_status as _profile_field_verification_status,
    verified_level_label as _verified_level_label,
    verified_score_info as _verified_score_info,
)
from partner_search.search_runtime_helpers import SearchRuntime, SearchRuntimeHelpers
from profile_source_refs import build_source_file_ref as _build_source_file_ref
from profile_source_refs import split_source_file_ref as _split_source_file_ref
from profile_service import (
    detect_profile_table,
    list_profile_columns,
    list_profile_photo_previews,
    list_profiles,
    resolve_profile_source,
)

argparse = _argparse


FIELD_ALIASES = {
    "id": {"id", "编号"},
    "name": {"name", "姓名", "昵称"},
    "avatar_url": {"avatar_url", "头像", "头像地址"},
    "photo_count": {"photo_count", "照片数", "照片数量"},
    "gender": {"gender", "性别"},
    "age": {"age", "年龄"},
    "city": {"city", "城市", "所在地", "现居地"},
    "district": {"district", "区县", "区域"},
    "hometown": {"hometown", "老家", "籍贯"},
    "settlement_city": {"settlement_city", "定居城市", "长期定居城市"},
    "housing_status": {"housing_status", "住房情况"},
    "car_status": {"car_status", "车辆情况"},
    "height": {"height", "身高"},
    "education": {"education", "学历"},
    "job": {"job", "工作", "职业"},
    "income_range": {"income_range", "收入", "收入范围"},
    "relationship_goal": {"relationship_goal", "目标", "恋爱目标", "婚恋目标", "关系目标"},
    "preferred_age_min": {"preferred_age_min", "择偶年龄下限", "年龄要求下限", "偏好年龄下限", "年龄最小"},
    "preferred_age_max": {"preferred_age_max", "择偶年龄上限", "年龄要求上限", "偏好年龄上限", "年龄最大"},
    "preferred_cities": {"preferred_cities", "择偶城市", "意向城市", "期望城市", "偏好城市"},
    "preferred_height_min": {"preferred_height_min", "择偶身高下限", "身高要求下限", "偏好身高下限", "最低身高"},
    "preferred_height_max": {"preferred_height_max", "择偶身高上限", "身高要求上限", "偏好身高上限", "最高身高"},
    "preferred_age_strictness": {"preferred_age_strictness", "年龄要求严格度", "择偶年龄严格度"},
    "preferred_height_strictness": {"preferred_height_strictness", "身高要求严格度", "择偶身高严格度"},
    "preferred_education_min": {"preferred_education_min", "择偶学历下限", "最低学历", "学历要求"},
    "preferred_education_strictness": {"preferred_education_strictness", "学历要求严格度", "择偶学历严格度"},
    "preferred_income_min_wan": {"preferred_income_min_wan", "择偶收入下限", "收入要求下限", "最低收入"},
    "preferred_income_max_wan": {"preferred_income_max_wan", "择偶收入上限", "收入要求上限", "最高收入"},
    "preferred_income_strictness": {"preferred_income_strictness", "收入要求严格度", "择偶收入严格度"},
    "personality": {"personality", "性格"},
    "values": {"values", "价值观", "消费观"},
    "lifestyle": {"lifestyle", "生活方式", "作息"},
    "hobbies": {"hobbies", "兴趣", "爱好"},
    "life_routine": {"life_routine", "作息类型", "生活节奏"},
    "communication_style": {"communication_style", "沟通风格", "沟通方式"},
    "dating_pace": {"dating_pace", "推进节奏", "相处节奏"},
    "expression_style": {"expression_style", "表达风格", "表达感", "生活感"},
    "relationship_capacity": {"relationship_capacity", "关系投入能力", "关系承接能力"},
    "interaction_comfort": {"interaction_comfort", "相处轻松度", "相处压力", "相处状态"},
    "patience_level": {"patience_level", "耐心程度", "耐心水平"},
    "life_texture": {"life_texture", "生活立体感", "生活层次", "生活感层次"},
    "career_intensity": {"career_intensity", "工作节奏类型", "职业强度", "工作强度"},
    "exercise_habit": {"exercise_habit", "运动习惯", "运动频率"},
    "growth_signal": {"growth_signal", "事业势能", "成长性", "发展势能"},
    "warmth_style": {"warmth_style", "聊天温度", "互动温度", "温度感"},
    "aesthetic_expression": {"aesthetic_expression", "审美表达", "审美感", "内容输出"},
    "conversation_resonance": {
        "conversation_resonance",
        "聊天共鸣",
        "聊天同频感",
        "聊天感觉",
    },
    "personal_presence": {
        "personal_presence",
        "人物感",
        "记忆点",
        "个人辨识度",
    },
    "lightness_humor": {
        "lightness_humor",
        "轻松感",
        "幽默感",
        "聊天轻盈度",
    },
    "consumption_attitude": {
        "consumption_attitude",
        "消费观锚点",
        "消费观类型",
        "花钱观",
    },
    "chat_texture": {
        "chat_texture",
        "聊天质感",
        "聊天趣味",
        "聊天顺滑度",
    },
    "commitment_clarity": {
        "commitment_clarity",
        "进入关系明确度",
        "结婚意愿明确度",
        "长期意图明确度",
    },
    "relationship_execution": {
        "relationship_execution",
        "现实推进方式",
        "关系推进方式",
        "推进执行感",
    },
    "blended_family_readiness": {
        "blended_family_readiness",
        "重组家庭承接度",
        "现实承接度",
        "带娃现实承接度",
    },
    "smoking": {"smoking", "抽烟", "吸烟"},
    "drinking": {"drinking", "喝酒", "饮酒"},
    "long_distance": {"long_distance", "异地", "接受异地"},
    "accept_long_distance": {"accept_long_distance", "是否接受异地", "可否异地"},
    "location_preference_semantics": {
        "location_preference_semantics",
        "位置偏好补充",
        "异地补充说明",
        "位置偏好语义",
    },
    "accept_smoking": {"accept_smoking", "接受抽烟", "接受吸烟", "是否接受抽烟", "是否接受吸烟"},
    "accept_drinking": {"accept_drinking", "接受喝酒", "接受饮酒", "是否接受喝酒", "是否接受饮酒"},
    "accept_marital_status": {"accept_marital_status", "接受婚况", "可接受婚况", "可接受婚姻状态"},
    "accept_marital_status_strength": {
        "accept_marital_status_strength",
        "婚况接受强度",
        "婚史接受强度",
        "婚况接受态度",
    },
    "accept_marital_status_semantics": {
        "accept_marital_status_semantics",
        "婚况接受细语义",
        "婚史接受细语义",
        "婚况接受真实表达",
    },
    "marital_status": {"marital_status", "婚姻状态"},
    "has_children": {"has_children", "有无孩子", "是否有孩子", "是否已育"},
    "children_count": {"children_count", "孩子数量", "子女数量"},
    "children_living_with_self": {"children_living_with_self", "孩子是否同住", "子女是否同住"},
    "want_children": {"want_children", "是否想要孩子", "想要孩子", "生育计划", "孩子计划"},
    "accept_partner_children": {
        "accept_partner_children",
        "接受对方孩子",
        "是否接受对方有孩子",
        "是否接受伴侣有孩子",
    },
    "accept_partner_children_strength": {
        "accept_partner_children_strength",
        "接受孩子强度",
        "对子女接受强度",
        "对子女接受态度",
    },
    "accept_partner_children_semantics": {
        "accept_partner_children_semantics",
        "对子女接受细语义",
        "对子女接受真实表达",
        "对子女接受补充语义",
    },
    "requires_partner_accept_my_children": {
        "requires_partner_accept_my_children",
        "是否要求对方接受其孩子现实",
        "对方是否需要接受其孩子现实",
    },
    "marriage_timeline": {"marriage_timeline", "结婚时间", "结婚计划", "结婚节奏"},
    "family_background": {"family_background", "家庭情况", "家庭背景"},
    "profile_status": {"profile_status", "资料状态", "档案状态"},
    "last_active_at": {"last_active_at", "最近活跃时间", "最后活跃时间"},
    "verified_level": {"verified_level", "认证等级", "认证级别"},
    "photo_verification_level": {"photo_verification_level", "照片核验等级", "照片认证层级", "photo_verified_level"},
    "education_verification_status": {"education_verification_status", "学历认证状态", "education_verified_status"},
    "job_verification_status": {"job_verification_status", "职业认证状态", "job_verified_status"},
    "income_verification_status": {"income_verification_status", "收入认证状态", "income_verified_status"},
    "city_verification_status": {"city_verification_status", "城市认证状态", "city_verified_status"},
    "marital_status_verification_status": {"marital_status_verification_status", "婚况认证状态", "marital_verified_status"},
    "children_verification_status": {"children_verification_status", "子女情况认证状态", "children_verified_status"},
    "relationship_goal_verification_status": {"relationship_goal_verification_status", "结婚意向认证状态", "goal_verified_status"},
    "profile_review_status": {"profile_review_status", "资料复核状态", "profile_consistency_status"},
    "job_change_count_30d": {"job_change_count_30d", "近30天职业修改次数"},
    "city_change_count_30d": {"city_change_count_30d", "近30天城市修改次数"},
    "income_change_count_30d": {"income_change_count_30d", "近30天收入修改次数"},
    "source_channel": {"source_channel", "来源渠道", "来源"},
    "created_at": {"created_at", "创建时间"},
    "updated_at": {"updated_at", "更新时间"},
    "notes": {"notes", "备注", "说明"},
}

MYSQL_SCHEMES = MYSQL_SOURCE_SCHEMES
DEFAULT_MYSQL_SOURCE = os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
DEFAULT_MYSQL_PHOTOS_TABLE = os.environ.get(
    "PARTNER_SEARCH_MYSQL_PHOTOS_TABLE",
    "profile_photos",
)
PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
EMAIL_PATTERN = re.compile(r"(?P<local>[A-Za-z0-9._%+-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
NATIONAL_ID_PATTERN = re.compile(r"(?<![\dXx])(\d{6})\d{8}(\d{3}[\dXx])(?![\dXx])")
CONTACT_HANDLE_PATTERN = re.compile(
    r"(?P<label>(?:微信(?:号)?|wechat|wx|vx|qq)\s*[:：]?\s*)(?P<handle>[A-Za-z][-_A-Za-z0-9]{5,19}|\d{5,12})",
    re.IGNORECASE,
)
ADDRESS_DETAIL_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:路|街|道|巷|弄|村|苑|城|湾|里|花园|小区|大厦|公寓|广场)\s*\d{1,4}(?:号|栋|幢|单元|室)?"
)
ORG_DETAIL_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:小学|中学|幼儿园|大学|学院|医院|公司)"
)
CHILD_DETAIL_PATTERN = re.compile(r"(?:儿子|女儿|孩子)\s*\d{1,2}\s*岁")
SENSITIVE_NOTE_PATTERNS = (
    PHONE_PATTERN,
    EMAIL_PATTERN,
    NATIONAL_ID_PATTERN,
    CONTACT_HANDLE_PATTERN,
    ADDRESS_DETAIL_PATTERN,
    ORG_DETAIL_PATTERN,
    CHILD_DETAIL_PATTERN,
)

def normalize_key(key):
    return re.sub(r"[\s\-]+", "_", str(key).strip().lower())


TEXT_FIELDS = [
    "name",
    "city",
    "district",
    "hometown",
    "settlement_city",
    "housing_status",
    "car_status",
    "education",
    "job",
    "income_range",
    "relationship_goal",
    "preferred_cities",
    "preferred_age_strictness",
    "preferred_height_strictness",
    "preferred_education_strictness",
    "preferred_income_strictness",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "life_routine",
    "communication_style",
    "dating_pace",
    "expression_style",
    "relationship_capacity",
    "interaction_comfort",
    "patience_level",
    "life_texture",
    "career_intensity",
    "exercise_habit",
    "growth_signal",
    "warmth_style",
    "aesthetic_expression",
    "conversation_resonance",
    "personal_presence",
    "lightness_humor",
    "consumption_attitude",
    "chat_texture",
    "commitment_clarity",
    "relationship_execution",
    "blended_family_readiness",
    "smoking",
    "drinking",
    "long_distance",
    "accept_long_distance",
    "location_preference_semantics",
    "accept_smoking",
    "accept_drinking",
    "accept_marital_status",
    "accept_marital_status_strength",
    "accept_marital_status_semantics",
    "marital_status",
    "want_children",
    "accept_partner_children",
    "accept_partner_children_strength",
    "accept_partner_children_semantics",
    "marriage_timeline",
    "family_background",
    "notes",
    "source_channel",
]

VERIFIED_LEVEL_ORDER = {
    "none": 0,
    "basic": 1,
    "photo": 2,
    "id": 3,
    "offline": 4,
}

PHOTO_VERIFICATION_LEVEL_ORDER = {
    "none": 0,
    "uploaded": 1,
    "human_verified": 2,
    "live_video_verified": 3,
    "offline_verified": 4,
}

PROFILE_STATUS_ORDER = {
    "archived": 0,
    "matched": 1,
    "paused": 2,
    "active": 3,
}

EDUCATION_ORDER = {
    "初中": 1,
    "高中": 2,
    "中专": 3,
    "大专": 4,
    "专升本": 5,
    "本科": 6,
    "硕士": 7,
    "博士": 8,
}

BUSY_JOB_KEYWORDS = {"医生", "护士", "审计", "金融", "投行", "新媒体", "课程顾问", "外贸"}

CRITICAL_MISSING_FIELD_PENALTIES = {
    "smoking": 8,
    "drinking": 4,
    "long_distance": 6,
    "marital_status": 7,
    "want_children": 8,
    "accept_partner_children": 10,
    "accept_marital_status": 8,
    "accept_smoking": 5,
    "accept_drinking": 5,
    "accept_long_distance": 7,
    "marriage_timeline": 5,
    "settlement_city": 4,
}

SELF_PROFILE_GAP_PENALTIES = {
    "self_age": 3,
    "self_city": 4,
    "self_height": 4,
    "self_education": 3,
    "self_income_wan": 3,
    "self_marital_status": 4,
    "self_has_children": 5,
    "self_smoking": 2,
    "self_drinking": 2,
}

RISK_FLAG_PENALTIES = {
    "对方对子女情况仅可协商": 10,
    "对方对子女接受度偏低": 11,
    "对方对子女接受需要先接触再判断": 10,
    "对方对子女接受度未知": 12,
    "对方城市偏好未命中，但资料写了接受异地": 6,
    "对方城市偏好未命中，异地仅可协商": 10,
    "对方城市偏好未命中，异地接受度未知": 10,
    "对方对抽烟仅可协商": 7,
    "对方对抽烟接受度未知": 9,
    "对方对喝酒仅可协商": 4,
    "对方对喝酒接受度未知": 8,
    "对方异地仅可协商": 7,
    "对方异地接受度未知": 8,
    "对方年龄要求可能可放宽": 7,
    "对方身高要求可能可放宽": 5,
    "对方学历要求可能可放宽": 5,
    "对方收入要求可能可放宽": 6,
    "对方婚史接受度偏保守": 9,
    "对方婚史接受需要先聊再判断": 9,
    "对方婚史接受度未知": 10,
    "对方对子女接受度偏保守": 9,
    "学历没有完全卡进你的底线": 12,
    "对方不接受长期异地，需要确认落地计划": 9,
    "异地需要明确落地计划": 6,
    "非同城，见面推进成本更高": 4,
    "多项条件需要放宽后才成立": 6,
    "生活阶段可能有落差": 8,
    "资料偏稳但不够鲜活": 5,
    "相处可能偏冷": 6,
    "相处节奏可能偏赶": 5,
    "忙的时候可能更难推进": 5,
    "工作节奏偏忙，稳定投入要再看": 5,
    "主动沟通感偏弱": 4,
    "乐观外放感偏弱": 3,
    "消费观还不够具体": 4,
    "聊天还像完成任务": 7,
    "认真相处信号还不够落地": 6,
    "认真相处推进偏慢": 5,
    "长期意图有，但推进方式还不够落地": 9,
    "推进方式偏慢观察": 6,
    "成长势能偏弱": 6,
    "聊天温度偏冷": 5,
    "审美表达偏平": 4,
    "聊天可能像信息交换": 5,
    "人物感偏淡": 4,
    "聊天可能偏板正": 5,
    "进入关系信号偏弱": 9,
    "重组家庭现实承接仍需确认": 6,
    "资料存在待复核或不一致信号": 8,
    "收入声明与职业类型存在明显落差": 12,
    "职业近30天修改较频繁": 8,
    "城市近30天修改较频繁": 6,
    "收入近30天修改较频繁": 8,
    "未认证": 6,
    "活跃时间未知": 4,
    "90天前活跃": 6,
}

CREATIVE_JOB_PATTERNS = (
    re.compile(r"(设计|ui|ux|交互|视觉|插画|动画|品牌|创意|内容|游戏|摄影|导演|编剧)", re.I),
)

SENSITIVE_RELATION_NOTE_PATTERNS = (
    re.compile(r"(孩子|带娃|生育|备孕|不要孩子|丁克)"),
    re.compile(r"(离异|再婚|婚史|前任|前夫|前妻)"),
)

DIVERSITY_JOB_PATTERNS = (
    (re.compile(r"(医生|护士|药师|医疗|医院|临床)"), "medical"),
    (re.compile(r"(教师|老师|学校|教育|培训)"), "education"),
    (re.compile(r"(产品|运营|研发|工程师|程序|算法|设计)"), "tech"),
    (re.compile(r"(金融|银行|证券|基金|投行|保险)"), "finance"),
    (re.compile(r"(体制|公务员|事业单位|国企)"), "public-sector"),
)

SIGNAL_FIELD_SPECS = (
    ("life_routine", "作息"),
    ("communication_style", "沟通"),
    ("dating_pace", "节奏"),
    ("career_intensity", "工作节奏"),
    ("consumption_attitude", "消费观"),
    ("commitment_clarity", "长期意图"),
    ("relationship_execution", "推进方式"),
    ("blended_family_readiness", "现实承接"),
    ("growth_signal", "成长"),
    ("interaction_comfort", "相处"),
)

RELATIONSHIP_GOAL_STRENGTH_BONUS = {
    "先接触看看": 0,
    "认真恋爱": 2,
    "结婚导向": 4,
}

NEAR_DISTANCE_PRIORITY_MARKERS = (
    "同城",
    "近距离",
    "通勤",
    "稳定留",
    "落地计划",
    "见面成本不能太高",
    "长期异地不接受",
)

SOFT_CONCESSION_RISK_FLAGS = {
    "对方年龄要求可能可放宽",
    "对方身高要求可能可放宽",
    "对方学历要求可能可放宽",
    "对方收入要求可能可放宽",
    "对方城市偏好未命中，异地仅可协商",
    "对方城市偏好未命中，异地接受度未知",
    "对方异地仅可协商",
    "对方异地接受度未知",
    "对方婚史接受度偏保守",
    "对方婚史接受需要先聊再判断",
    "对方对子女情况仅可协商",
    "对方对子女接受度偏保守",
    "对方对子女接受需要先接触再判断",
    "认真相处信号还不够落地",
    "认真相处推进偏慢",
    "长期意图有，但推进方式还不够落地",
    "推进方式偏慢观察",
}


def build_alias_lookup():
    lookup = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup[normalize_key(alias)] = canonical
    return lookup


ALIAS_LOOKUP = build_alias_lookup()

REQUEST_SEQUENCE_CRITERIA_ALIASES = {
    "cities": ("cities", "city"),
    "districts": ("districts", "district"),
    "settlement_cities": ("settlement_cities", "settlement_city"),
    "relationship_goals": ("relationship_goals", "relationship_goal"),
    "must_have": ("must_have",),
    "must_not_have": ("must_not_have", "must_not_have"),
    "prefer": ("prefer",),
    "housing_statuses": ("housing_statuses", "housing_status"),
    "car_statuses": ("car_statuses", "car_status"),
    "marital_statuses": ("marital_statuses", "marital_status"),
    "marriage_timelines": ("marriage_timelines", "marriage_timeline"),
    "profile_statuses": ("profile_statuses", "profile_status"),
    "verified_levels": ("verified_levels", "verified_level"),
    "photo_verification_levels": ("photo_verification_levels", "photo_verification_level"),
    "required_known_fields": ("required_known_fields", "require_known"),
}

REQUEST_SCALAR_CRITERIA_ALIASES = {
    "gender": ("gender",),
    "age_min": ("age_min",),
    "age_max": ("age_max",),
    "height_min": ("height_min",),
    "height_max": ("height_max",),
    "smoking": ("smoking",),
    "drinking": ("drinking",),
    "long_distance": ("long_distance",),
    "want_children": ("want_children",),
    "accept_partner_children": ("accept_partner_children",),
    "accept_marital_status_strength": ("accept_marital_status_strength",),
    "accept_partner_children_strength": ("accept_partner_children_strength",),
    "active_within_days": ("active_within_days",),
    "verified_level_min": ("verified_level_min",),
    "photo_verification_level_min": ("photo_verification_level_min",),
    "photo_count_min": ("photo_count_min",),
    "has_children": ("has_children",),
}

STRUCTURED_RESULT_LIST_FIELDS = (
    "matched_on",
    "reciprocal_on",
    "missing_fields",
    "self_profile_gaps",
    "risk_flags",
    "match_evidence",
    "follow_up_questions",
    "photo_preview",
)


def is_mysql_source(source):
    try:
        return urlparse(str(source)).scheme.lower() in MYSQL_SCHEMES
    except Exception:
        return False


def redact_mysql_source(source):
    text = str(source)
    try:
        parsed = urlparse(text)
    except Exception:
        return text
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        return text

    userinfo = ""
    if parsed.username:
        username = unquote(parsed.username)
        if parsed.password:
            userinfo = f"{username}:***@"
        else:
            userinfo = f"{username}@"

    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    query = parse_qs(parsed.query)
    safe_query_parts = []
    for key in ("table", "photos_table", "charset"):
        value = query.get(key, [None])[0]
        if value:
            safe_query_parts.append(f"{key}={value}")
    query_text = f"?{'&'.join(safe_query_parts)}" if safe_query_parts else ""
    return f"{parsed.scheme}://{userinfo}{host}{port}{parsed.path}{query_text}"


def redact_source_ref(source_ref):
    if not source_ref:
        return ""
    source, table_name = split_source_file_ref(source_ref)
    if not table_name:
        return redact_mysql_source(source_ref)
    redacted = redact_mysql_source(source)
    return f"{redacted}#{table_name}" if table_name else redacted


def default_source_help_text():
    if DEFAULT_MYSQL_SOURCE:
        return f"Defaults to PARTNER_SEARCH_MYSQL_SOURCE={redact_mysql_source(DEFAULT_MYSQL_SOURCE)}."
    return "Required unless PARTNER_SEARCH_MYSQL_SOURCE is set."


def as_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def education_rank(value):
    return EDUCATION_ORDER.get(str(value).strip()) if value else None


def verified_rank(value):
    return VERIFIED_LEVEL_ORDER.get(as_lower(value), 0)


def photo_verification_rank(value):
    return PHOTO_VERIFICATION_LEVEL_ORDER.get(as_lower(value), 0)


def profile_status_rank(value):
    return PROFILE_STATUS_ORDER.get(as_lower(value), 0)


def parse_income_range_to_wan(value):
    if value is None:
        return (None, None)
    numbers = [int(item) for item in re.findall(r"\d+", str(value))]
    if not numbers:
        return (None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (min(numbers[0], numbers[1]), max(numbers[0], numbers[1]))


def effective_has_children(record):
    direct = normalize_bool(record.get("has_children"))
    if direct is not None:
        return direct
    marital_status = as_lower(record.get("marital_status"))
    if "已育" in marital_status:
        return True
    if marital_status in {"未婚", "离异未育", "离异无孩"} or "无孩" in marital_status:
        return False
    return None


def marital_status_match_options(record):
    status = as_text(record.get("marital_status"))
    if not status:
        return []
    options = [status]
    lowered = as_lower(status)
    has_children = normalize_bool(record.get("has_children"))
    if lowered in {"离异", "离异无孩", "离异未育", "离异已育"}:
        options.append("离异")
    if lowered == "离异":
        if has_children is True:
            options.append("离异已育")
        elif has_children is False:
            options.append("离异未育")
            options.append("离异无孩")
    elif lowered == "离异已育":
        options.append("离异")
    elif lowered in {"离异未育", "离异无孩"}:
        options.append("离异")
        options.append("离异未育")
        options.append("离异无孩")
    return unique_ordered(options)


def effective_activity_datetime(record):
    return effective_activity_info(record)[1]


def effective_activity_info(record):
    for field in ("last_active_at", "updated_at", "created_at"):
        parsed = as_datetime(record.get(field))
        if parsed is not None:
            return (field, parsed)
    return (None, None)


def format_datetime(value):
    parsed = as_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else None


def mask_value(value, left=2, right=2, mask="***"):
    text = str(value)
    if not text:
        return text
    if len(text) <= left + right:
        if len(text) <= 2:
            return "*" * len(text)
        return text[:1] + mask
    suffix = text[-right:] if right > 0 else ""
    return text[:left] + mask + suffix


def redact_sensitive_text(value):
    if value is None or value == "":
        return value

    text = str(value)
    text = PHONE_PATTERN.sub(lambda match: f"{match.group(1)}****{match.group(2)}", text)
    text = NATIONAL_ID_PATTERN.sub(
        lambda match: f"{match.group(1)}********{match.group(2)}",
        text,
    )
    text = EMAIL_PATTERN.sub(
        lambda match: f"{mask_value(match.group('local'), left=1, right=0)}@{match.group('domain')}",
        text,
    )
    text = CONTACT_HANDLE_PATTERN.sub(
        lambda match: f"{match.group('label')}{mask_value(match.group('handle'), left=2, right=2)}",
        text,
    )
    return text


def contains_sensitive_note_detail(value):
    if value is None or value == "":
        return False
    text = str(value)
    return any(pattern.search(text) for pattern in SENSITIVE_NOTE_PATTERNS)


def summarize_notes(value, max_segments=2, max_length=80):
    if value is None or value == "":
        return None

    text = normalize_whitespace(value)
    if not text:
        return None

    if contains_sensitive_note_detail(text):
        return "有补充备注，已隐藏敏感细节"

    redacted = normalize_whitespace(redact_sensitive_text(text))
    parts = [
        part.strip(" ,，。;；|")
        for part in re.split(r"[。；;\n|]+", redacted)
        if part.strip(" ,，。;；|")
    ]
    if not parts:
        return None

    summary = "；".join(parts[:max_segments])
    if len(summary) > max_length:
        summary = summary[: max_length - 3].rstrip() + "..."
    return summary or None


def shorten_text(value, max_length=60):
    text = normalize_whitespace(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def extract_literal_keyword_evidence(record, keyword):
    lowered_keyword = as_lower(keyword)
    if not lowered_keyword:
        return None

    for field, label in KEYWORD_EVIDENCE_FIELDS:
        value = record.get(field)
        if not value:
            continue
        segments = split_evidence_segments(value)
        for segment in segments:
            if lowered_keyword in segment.lower():
                if contains_sensitive_note_detail(segment):
                    return f"{label}: 命中关键词，敏感细节已隐藏"
                return f"{label}: {shorten_text(redact_sensitive_text(segment))}"
    return None


def collect_keyword_signal_evidence(record, keyword):
    lowered_keyword = as_lower(keyword)
    signal_parts = []

    for field, label, expected_values in STRUCTURED_KEYWORD_SIGNAL_RULES.get(lowered_keyword, []):
        value = as_text(record.get(field))
        if value and value in expected_values:
            signal_parts.append(f"{label}={value}")

    for field, label, cues in TEXTUAL_KEYWORD_SIGNAL_RULES.get(lowered_keyword, []):
        value = record.get(field)
        if not value or not contains_any_text(value, cues):
            continue
        signal_parts.append(f"{label}={shorten_text(redact_sensitive_text(value), max_length=20)}")

    if len(signal_parts) < 3:
        return []
    return signal_parts[:3]


def keyword_matches_record(record, keyword):
    lowered_keyword = as_lower(keyword)
    if not lowered_keyword:
        return False
    if lowered_keyword in as_lower(record.get("combined_text", "")):
        return True
    return bool(collect_keyword_signal_evidence(record, keyword))


def extract_keyword_evidence(record, keyword):
    literal_evidence = extract_literal_keyword_evidence(record, keyword)
    if literal_evidence:
        return literal_evidence

    signal_evidence = collect_keyword_signal_evidence(record, keyword)
    if signal_evidence:
        return f"结构化信号: {'；'.join(signal_evidence)}"
    return None


def missing_field_penalty(field):
    return CRITICAL_MISSING_FIELD_PENALTIES.get(field, 0)


def self_profile_gap_penalty(field):
    return SELF_PROFILE_GAP_PENALTIES.get(field, 0)


def risk_flag_penalty(risk_flag):
    if str(risk_flag).startswith("资料里提到“"):
        return 4
    return RISK_FLAG_PENALTIES.get(risk_flag, 0)


def location_semantics_risk_flags(record):
    semantics = as_text(record.get("location_preference_semantics"))
    if not semantics:
        return []
    if re.search(r"(?:不接受|不考虑|不能接受|不想)[^，。；]{0,8}长期异地", semantics) or re.search(
        r"长期[^，。；]{0,8}异地[^，。；]{0,8}(?:不接受|不考虑|不行|免谈)",
        semantics,
    ):
        return ["对方不接受长期异地，需要确认落地计划"]
    if any(marker in semantics for marker in ("落地计划", "稳定留沪", "双城过渡", "短期异地")):
        return ["异地需要明确落地计划"]
    return []


def soft_preference_risk_flag(kind, strictness_state):
    if strictness_state == "reference":
        return None
    mapping = {
        "age": "对方年龄要求可能可放宽",
        "height": "对方身高要求可能可放宽",
        "education": "对方学历要求可能可放宽",
        "income": "对方收入要求可能可放宽",
    }
    return mapping.get(kind)


def self_preference_strictness(value):
    if value is None or value == "":
        return "soft"
    return normalize_strictness_state(value)


def self_education_floor_risk_flag(self_profile, record):
    preferred_min = self_profile.get("preferred_education_min")
    if not preferred_min:
        return None

    required_rank = education_rank(preferred_min)
    candidate_rank = education_rank(record.get("education"))
    if required_rank is None or candidate_rank is None:
        return None
    if candidate_rank >= required_rank:
        return None

    strictness = self_preference_strictness(self_profile.get("preferred_education_strictness"))
    if strictness == "hard":
        return "education_below_self_preference"
    return "学历没有完全卡进你的底线"


def keyword_requested(criteria, keywords):
    joined = " ".join(criteria.get("must_have", []) + criteria.get("prefer", []))
    return contains_any_text(joined, keywords)


def creative_job_match(value):
    text = as_text(value)
    if not text:
        return False
    return any(pattern.search(text) for pattern in CREATIVE_JOB_PATTERNS)


def child_or_marital_topic_requested(criteria, self_profile):
    if requires_explicit_children_acceptance(self_profile):
        return True
    joined = " ".join(
        criteria.get("must_have", [])
        + criteria.get("prefer", [])
        + criteria.get("must_not_have", [])
        + criteria.get("relationship_goals", [])
    )
    return contains_any_text(joined, {"孩子", "带娃", "婚史", "再婚", "生育", "接受孩子现实"})


def summarize_notes_for_result(record, criteria, self_profile, max_segments=2, max_length=80):
    notes = record.get("notes")
    summary = summarize_notes(notes, max_segments=max_segments, max_length=max_length)
    if not summary:
        return None
    if child_or_marital_topic_requested(criteria, self_profile):
        return summary

    parts = [
        part.strip(" ,，。;；|")
        for part in re.split(r"[。；;\n|]+", summary)
        if part.strip(" ,，。;；|")
    ]
    filtered = [
        part
        for part in parts
        if not any(pattern.search(part) for pattern in SENSITIVE_RELATION_NOTE_PATTERNS)
    ]
    if not filtered:
        return None
    compact = "；".join(filtered[:max_segments])
    if len(compact) > max_length:
        compact = compact[: max_length - 3].rstrip() + "..."
    return compact or None


def candidate_income_bounds(record):
    income_min = as_int(record.get("income_min_wan"))
    income_max = as_int(record.get("income_max_wan"))
    if income_min is not None or income_max is not None:
        return income_min, income_max
    return parse_income_range_to_wan(record.get("income_range"))


def requires_explicit_marital_acceptance(self_profile):
    status = as_lower(self_profile.get("marital_status"))
    return bool(status and status != "未婚")


def requires_explicit_children_acceptance(self_profile):
    return normalize_bool(self_profile.get("has_children")) is True


def marital_acceptance_risk_flag(strength, semantics):
    semantics_text = as_text(semantics)
    if contains_any_text(semantics_text, {"先聊再判断", "先接触再判断"}):
        return "对方婚史接受需要先聊再判断"
    if contains_any_text(semantics_text, {"更看具体", "相处质量"}):
        return "对方婚史接受度偏保守"
    if contains_any_text(semantics_text, {"态度未知"}):
        return "对方婚史接受度未知"
    if strength == "surface":
        return "对方婚史接受需要先聊再判断"
    if strength == "cautious":
        return "对方婚史接受度偏保守"
    if strength == "unknown":
        return "对方婚史接受度未知"
    return None


def children_acceptance_risk_flag(state, strength, semantics):
    semantics_text = as_text(semantics)
    if contains_any_text(semantics_text, {"偏低", "偏保留"}):
        return "对方对子女接受度偏低"
    if contains_any_text(semantics_text, {"不太接受", "非常看具体"}):
        return "对方对子女接受度偏低"
    if contains_any_text(semantics_text, {"先接触再判断", "先聊再判断", "后续现实情况"}):
        return "对方对子女接受需要先接触再判断"
    if contains_any_text(semantics_text, {"更看具体"}):
        return "对方对子女接受度偏保守"
    if contains_any_text(semantics_text, {"态度未知"}):
        return "对方对子女接受度未知"

    if state == "accepted":
        if strength == "cautious":
            return "对方对子女接受度偏保守"
        if strength == "surface":
            return "对方对子女接受需要先接触再判断"
        if strength == "unknown":
            return "对方对子女接受度未知"
        return None

    if state == "negotiable":
        if strength == "cautious":
            return "对方对子女接受度偏低"
        if strength == "surface":
            return "对方对子女接受需要先接触再判断"
        return "对方对子女情况仅可协商"

    if state == "guarded":
        return "对方对子女接受度偏低"

    if state == "unknown":
        return "对方对子女接受度未知"
    return None


def reciprocal_city_preference_risk_flag(accept_long_distance_state, reciprocal_mode):
    if accept_long_distance_state == "accepted":
        return "对方城市偏好未命中，但资料写了接受异地"
    if accept_long_distance_state in {"negotiable", "guarded"}:
        return "对方城市偏好未命中，异地仅可协商"
    if reciprocal_mode == "fallback" and accept_long_distance_state in {"unknown", "missing"}:
        return "对方城市偏好未命中，异地接受度未知"
    return None


def self_prefers_near_distance(self_profile):
    if not self_profile:
        return False
    self_city = as_text(self_profile.get("city"))
    if not self_city:
        return False

    own_long_distance = normalize_acceptance_state(
        self_profile.get("accept_long_distance") or self_profile.get("long_distance")
    )
    if own_long_distance in {"rejected", "guarded"}:
        return True

    preferred_cities = split_keywords(self_profile.get("preferred_cities"))
    if preferred_cities and match_any_exact(self_city, preferred_cities):
        return True

    location_semantics = as_text(self_profile.get("location_preference_semantics"))
    return any(marker in location_semantics for marker in NEAR_DISTANCE_PRIORITY_MARKERS)


def concession_stack_risk_flag(risk_flags):
    concession_count = sum(1 for flag in unique_ordered(risk_flags) if flag in SOFT_CONCESSION_RISK_FLAGS)
    if concession_count >= 3:
        return "多项条件需要放宽后才成立"
    return None


def evaluate_contextual_fit(record, criteria, self_profile=None):
    self_profile = self_profile or {}
    reasons = []
    risk_flags = []
    match_evidence = []
    score_bonus = 0

    interaction_comfort = record.get("interaction_comfort")
    patience_level = record.get("patience_level")
    life_texture = record.get("life_texture")
    career_intensity = record.get("career_intensity")
    exercise_habit = record.get("exercise_habit")
    growth_signal = record.get("growth_signal")
    warmth_style = record.get("warmth_style")
    aesthetic_expression = record.get("aesthetic_expression")
    conversation_resonance = record.get("conversation_resonance")
    personal_presence = record.get("personal_presence")
    lightness_humor = record.get("lightness_humor")
    consumption_attitude = record.get("consumption_attitude")
    chat_texture = record.get("chat_texture")
    commitment_clarity = record.get("commitment_clarity")
    relationship_execution = record.get("relationship_execution")
    blended_family_readiness = record.get("blended_family_readiness")
    communication_style = record.get("communication_style")
    dating_pace = record.get("dating_pace")
    expression_style = record.get("expression_style")
    notes_and_values = " ".join(
        str(record.get(field) or "") for field in ("notes", "values", "family_background")
    )
    steady_life_profile = (
        requires_explicit_marital_acceptance(self_profile)
        or requires_explicit_children_acceptance(self_profile)
        or keyword_requested(criteria, {"稳定踏实", "生活规律", "省心", "过日子", "相处舒服", "相处轻松", "简单舒服", "不累"})
    )
    cares_about_regular_life = keyword_requested(criteria, {"生活规律", "生活稳定"})
    wants_proactive_communication = keyword_requested(criteria, {"主动沟通", "沟通"})
    cares_about_consumption = keyword_requested(
        criteria, {"消费观", "消费观正常", "不攀比", "过日子", "务实", "花钱观"}
    )
    cares_about_positive_energy = keyword_requested(criteria, {"乐观", "爱笑", "松弛"})

    if keyword_requested(criteria, {"有耐心", "慢热", "沟通", "会接话", "相处", "舒服", "不累"}):
        if interaction_comfort in {"相处轻松", "安静低压", "有边界不拧巴"}:
            reasons.append("相处压力更小")
            score_bonus += 4
            match_evidence.append(f"相处压力更小 <- 相处状态: {interaction_comfort}")
        if patience_level in {"高耐心", "耐心稳定"}:
            reasons.append("耐心更匹配")
            score_bonus += 4
            match_evidence.append(f"耐心更匹配 <- 耐心程度: {patience_level}")
        elif patience_level == "节奏偏快":
            risk_flags.append("相处节奏可能偏赶")
        if expression_style == "理性克制" and communication_style == "理性直接":
            risk_flags.append("相处可能偏冷")
        if warmth_style == "有温度会接话":
            reasons.append("聊天温度更舒服")
            score_bonus += 4
            match_evidence.append(f"聊天温度更舒服 <- 聊天温度: {warmth_style}")
        elif warmth_style == "理性但不冷":
            reasons.append("理性但不冷")
            score_bonus += 3
            match_evidence.append(f"理性但不冷 <- 聊天温度: {warmth_style}")
        elif warmth_style == "偏克制":
            risk_flags.append("聊天温度偏冷")
        if conversation_resonance == "会接话也会接情绪":
            reasons.append("聊天更容易有来有回")
            score_bonus += 4
            match_evidence.append(f"聊天更容易有来有回 <- 聊天共鸣: {conversation_resonance}")

    if keyword_requested(criteria, {"边界", "边界感", "理性直接"}):
        if interaction_comfort == "有边界不拧巴":
            reasons.append("边界清楚不拧巴")
            score_bonus += 4
            match_evidence.append(f"边界清楚不拧巴 <- 相处状态: {interaction_comfort}")

    if keyword_requested(criteria, {"生活规律", "爱运动", "健身", "乐观"}):
        if cares_about_regular_life and record.get("life_routine") in {"生活规律", "生活稳定"}:
            reasons.append("生活节奏更稳")
            score_bonus += 3
            match_evidence.append(f"生活节奏更稳 <- 作息类型: {record.get('life_routine')}")
        if exercise_habit == "规律运动":
            reasons.append("运动习惯更匹配")
            score_bonus += 5
            match_evidence.append(f"运动习惯更匹配 <- 运动习惯: {exercise_habit}")
        elif exercise_habit == "轻运动":
            reasons.append("生活状态更合拍")
            score_bonus += 3
            match_evidence.append(f"生活状态更合拍 <- 运动习惯: {exercise_habit}")
        if cares_about_positive_energy:
            if warmth_style == "有温度会接话":
                reasons.append("相处更有正反馈")
                score_bonus += 3
                match_evidence.append(f"相处更有正反馈 <- 聊天温度: {warmth_style}")
            elif warmth_style == "理性但不冷":
                reasons.append("情绪反馈更稳定")
                score_bonus += 2
                match_evidence.append(f"情绪反馈更稳定 <- 聊天温度: {warmth_style}")
            if lightness_humor == "有点幽默不端着":
                reasons.append("相处更有松弛感")
                score_bonus += 4
                match_evidence.append(f"相处更有松弛感 <- 轻松感: {lightness_humor}")
            elif lightness_humor == "稳重有分寸":
                reasons.append("相处更稳定不内耗")
                score_bonus += 2
                match_evidence.append(f"相处更稳定不内耗 <- 轻松感: {lightness_humor}")
            elif lightness_humor == "偏克制":
                risk_flags.append("乐观外放感偏弱")

    self_education_rank = education_rank(self_profile.get("education"))
    self_income_max = as_int(self_profile.get("income_max_wan"))
    candidate_education_rank = education_rank(record.get("education"))
    _, candidate_income_max = candidate_income_bounds(record)
    high_bar_profile = (
        (self_education_rank is not None and self_education_rank >= EDUCATION_ORDER["硕士"])
        or (self_income_max is not None and self_income_max >= 50)
    )
    wants_expressive_resonance = high_bar_profile or keyword_requested(
        criteria,
        {
            "见识",
            "表达",
            "审美",
            "共同兴趣",
            "情绪回应",
            "生活感",
            "会聊天",
            "会接话",
            "接话",
            "人物感",
            "上头",
            "火花",
            "不板正",
            "不端着",
            "聊天趣味",
            "聊天不累",
        },
    )

    if self_education_rank is not None and self_education_rank >= EDUCATION_ORDER["硕士"]:
        if candidate_education_rank is not None:
            if candidate_education_rank >= max(EDUCATION_ORDER["硕士"], self_education_rank - 1):
                reasons.append("学历层次更接近")
                score_bonus += 5
                match_evidence.append(f"学历层次更接近 <- 学历: {record.get('education')}")
                if (
                    self_education_rank >= EDUCATION_ORDER["博士"]
                    and candidate_education_rank >= EDUCATION_ORDER["博士"]
                ):
                    reasons.append("认知层次更对位")
                    score_bonus += 4
                    match_evidence.append(f"认知层次更对位 <- 学历: {record.get('education')}")
            elif self_education_rank >= EDUCATION_ORDER["博士"] and candidate_education_rank <= EDUCATION_ORDER["本科"]:
                risk_flags.append("生活阶段可能有落差")

    if self_income_max is not None and self_income_max >= 60 and candidate_income_max is not None:
        if candidate_income_max >= max(32, int(self_income_max * 0.45)):
            reasons.append("生活阶段更接近")
            score_bonus += 6
            match_evidence.append(f"生活阶段更接近 <- 收入范围: {record.get('income_range')}")
        elif candidate_income_max < max(26, int(self_income_max * 0.4)):
            risk_flags.append("生活阶段可能有落差")

    if cares_about_consumption or high_bar_profile:
        if consumption_attitude == "清醒务实":
            reasons.append("过日子观念更稳")
            score_bonus += 5
            match_evidence.append(f"过日子观念更稳 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "有取舍会生活":
            reasons.append("生活方式更有分寸")
            score_bonus += 4
            match_evidence.append(f"生活方式更有分寸 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "踏实过日子":
            reasons.append("过日子状态更踏实")
            score_bonus += 3
            match_evidence.append(f"过日子状态更踏实 <- 消费观锚点: {consumption_attitude}")
        elif cares_about_consumption and consumption_attitude == "表达不明显":
            risk_flags.append("消费观还不够具体")

    if wants_expressive_resonance:
        if wants_proactive_communication:
            if communication_style == "主动沟通":
                reasons.append("沟通更主动")
                score_bonus += 4
                match_evidence.append(f"沟通更主动 <- 沟通风格: {communication_style}")
            elif communication_style == "稳定沟通":
                reasons.append("沟通节奏更稳")
                score_bonus += 2
                match_evidence.append(f"沟通节奏更稳 <- 沟通风格: {communication_style}")
            elif communication_style == "慢热少话":
                risk_flags.append("主动沟通感偏弱")
        if warmth_style == "有温度会接话":
            reasons.append("理性之外也有温度")
            score_bonus += 4
            match_evidence.append(f"理性之外也有温度 <- 聊天温度: {warmth_style}")
        elif warmth_style == "理性但不冷":
            reasons.append("理性但不端着")
            score_bonus += 3
            match_evidence.append(f"理性但不端着 <- 聊天温度: {warmth_style}")
        elif warmth_style == "偏克制":
            risk_flags.append("聊天温度偏冷")
        if chat_texture == "有梗也有内容":
            reasons.append("聊天更有趣也更有内容")
            score_bonus += 5
            match_evidence.append(f"聊天更有趣也更有内容 <- 聊天质感: {chat_texture}")
        elif chat_texture == "顺着聊不费劲":
            reasons.append("聊天更顺，不容易累")
            score_bonus += 4
            match_evidence.append(f"聊天更顺，不容易累 <- 聊天质感: {chat_texture}")
        elif chat_texture == "稳重顺聊":
            reasons.append("聊天顺畅不拧巴")
            score_bonus += 3
            match_evidence.append(f"聊天顺畅不拧巴 <- 聊天质感: {chat_texture}")
        elif chat_texture == "偏功能聊天":
            risk_flags.append("聊天还像完成任务")
        if life_texture == "有见识也有生活感":
            reasons.append("资料不只稳，也更有生活感")
            score_bonus += 7
            match_evidence.append(f"资料不只稳，也更有生活感 <- 生活感层次: {life_texture}")
        elif life_texture == "有生活感":
            reasons.append("有生活感")
            score_bonus += 4
            match_evidence.append(f"有生活感 <- 生活感层次: {life_texture}")
        elif life_texture == "简单稳定":
            risk_flags.append("资料偏稳但不够鲜活")
        if aesthetic_expression == "有审美输出":
            reasons.append("更有审美和表达感")
            score_bonus += 6
            match_evidence.append(f"更有审美和表达感 <- 审美表达: {aesthetic_expression}")
        elif aesthetic_expression == "有生活审美":
            reasons.append("审美表达更顺眼")
            score_bonus += 3
            match_evidence.append(f"审美表达更顺眼 <- 审美表达: {aesthetic_expression}")
        elif aesthetic_expression == "普通":
            risk_flags.append("审美表达偏平")
        if conversation_resonance == "能聊想法也能聊日常":
            reasons.append("聊天层次更完整")
            score_bonus += 5
            match_evidence.append(f"聊天层次更完整 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "会接话也会接情绪":
            reasons.append("聊天不只对条件，也有情绪接住感")
            score_bonus += 4
            match_evidence.append(f"聊天不只对条件，也有情绪接住感 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "偏信息交换":
            risk_flags.append("聊天可能像信息交换")
        if personal_presence == "有记忆点":
            reasons.append("资料辨识度更高")
            score_bonus += 4
            match_evidence.append(f"资料辨识度更高 <- 人物感: {personal_presence}")
        elif personal_presence == "温和耐看":
            reasons.append("人物感更舒服")
            score_bonus += 3
            match_evidence.append(f"人物感更舒服 <- 人物感: {personal_presence}")
        elif personal_presence == "偏平":
            risk_flags.append("人物感偏淡")
        if lightness_humor == "有点幽默不端着":
            reasons.append("互动更轻松")
            score_bonus += 4
            match_evidence.append(f"互动更轻松 <- 轻松感: {lightness_humor}")
        elif lightness_humor == "稳重有分寸":
            reasons.append("稳重但不板正")
            score_bonus += 3
            match_evidence.append(f"稳重但不板正 <- 轻松感: {lightness_humor}")
        elif lightness_humor == "偏克制":
            risk_flags.append("聊天可能偏板正")

    if high_bar_profile or keyword_requested(criteria, {"成长", "势能", "事业", "大局观", "上进"}):
        if growth_signal == "上升明确":
            reasons.append("成长势能更强")
            score_bonus += 6
            match_evidence.append(f"成长势能更强 <- 事业势能: {growth_signal}")
        elif growth_signal == "平台成熟":
            reasons.append("发展阶段更成熟")
            score_bonus += 4
            match_evidence.append(f"发展阶段更成熟 <- 事业势能: {growth_signal}")
        elif high_bar_profile and growth_signal in {"稳定型", "未知"}:
            risk_flags.append("成长势能偏弱")

    if steady_life_profile:
        if career_intensity == "规律稳定":
            reasons.append("工作节奏更稳")
            score_bonus += 5
            match_evidence.append(f"工作节奏更稳 <- 工作节奏类型: {career_intensity}")
        elif career_intensity == "常规稳定":
            reasons.append("关系投入更省心")
            score_bonus += 3
            match_evidence.append(f"关系投入更省心 <- 工作节奏类型: {career_intensity}")
        elif career_intensity == "高强度但可协调":
            risk_flags.append("工作节奏偏忙，稳定投入要再看")

    self_job = self_profile.get("job")
    if self_job and contains_any_text(self_job, BUSY_JOB_KEYWORDS):
        if communication_style in {"主动沟通", "稳定沟通"} and dating_pace != "慢热推进":
            reasons.append("能配合忙碌节奏")
            score_bonus += 5
            match_evidence.append(
                f"能配合忙碌节奏 <- 沟通风格: {communication_style} | 推进节奏: {dating_pace}"
            )
        if career_intensity == "高强度但可协调":
            reasons.append("也能理解高强度工作")
            score_bonus += 3
            match_evidence.append(f"也能理解高强度工作 <- 工作节奏类型: {career_intensity}")
        elif communication_style == "慢热少话":
            risk_flags.append("忙的时候可能更难推进")

    if wants_expressive_resonance and creative_job_match(self_job) and creative_job_match(record.get("job")):
        reasons.append("审美和内容语境更接近")
        score_bonus += 6
        match_evidence.append(f"审美和内容语境更接近 <- 职业: {record.get('job')}")

    needs_explicit_family_reality = requires_explicit_children_acceptance(self_profile) or keyword_requested(
        criteria, {"接受孩子现实", "孩子现实", "现实承接", "再婚现实"}
    )
    if needs_explicit_family_reality:
        if blended_family_readiness == "已想过现实安排":
            reasons.append("现实安排想得更具体")
            score_bonus += 5
            match_evidence.append(f"现实安排想得更具体 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness == "愿意一起商量":
            reasons.append("现实问题愿意一起商量")
            score_bonus += 2
            match_evidence.append(f"现实问题愿意一起商量 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness in {"仅口头接受", "未知", None, ""}:
            risk_flags.append("重组家庭现实承接仍需确认")
        if (
            requires_explicit_children_acceptance(self_profile)
            and contains_any_text(notes_and_values, {"婚史", "再婚", "现实安排", "家里相处", "边界", "为什么结束"})
        ):
            reasons.append("复杂现实问题愿意提前讲清")
            score_bonus += 3
            match_evidence.append("复杂现实问题愿意提前讲清 <- 备注/价值观提到了现实安排")

    relationship_goals = set(criteria.get("relationship_goals") or [])
    wants_steady_relationship = (
        "认真恋爱" in relationship_goals
        or "结婚导向" in relationship_goals
        or keyword_requested(criteria, {"认真相处", "稳定投入关系", "认真推进"})
    )
    wants_clear_long_term = (
        "结婚导向" in relationship_goals
        or keyword_requested(criteria, {"稳定投入关系", "认真推进", "结婚", "长期"})
        or as_int(self_profile.get("age")) is not None
        and as_int(self_profile.get("age")) >= 29
    )
    if wants_steady_relationship and not wants_clear_long_term:
        if commitment_clarity == "明确奔着长期":
            reasons.append("认真相处意愿更明确")
            score_bonus += 4
            match_evidence.append(f"认真相处意愿更明确 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "愿意稳定推进":
            reasons.append("认真相处预期更清楚")
            score_bonus += 2
            match_evidence.append(f"认真相处预期更清楚 <- 长期意图明确度: {commitment_clarity}")
        if relationship_execution == "会把安排说清":
            reasons.append("认真相处不拖泥带水")
            score_bonus += 4
            match_evidence.append(f"认真相处不拖泥带水 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "稳步推进不拖拉":
            reasons.append("认真相处节奏更稳")
            score_bonus += 2
            match_evidence.append(f"认真相处节奏更稳 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "口头长期待验证":
            risk_flags.append("认真相处信号还不够落地")
        elif relationship_execution == "先聊熟再定":
            risk_flags.append("认真相处推进偏慢")
    if wants_clear_long_term:
        if commitment_clarity == "明确奔着长期":
            reasons.append("进入关系意愿更明确")
            score_bonus += 5
            match_evidence.append(f"进入关系意愿更明确 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "愿意稳定推进":
            reasons.append("长期推进预期更清楚")
            score_bonus += 3
            match_evidence.append(f"长期推进预期更清楚 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "先聊熟再说":
            risk_flags.append("进入关系信号偏弱")
        if relationship_execution == "会把安排说清":
            reasons.append("推进方式更落地")
            score_bonus += 5
            match_evidence.append(f"推进方式更落地 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "稳步推进不拖拉":
            reasons.append("推进节奏更踏实")
            score_bonus += 3
            match_evidence.append(f"推进节奏更踏实 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "口头长期待验证":
            risk_flags.append("长期意图有，但推进方式还不够落地")
        elif relationship_execution == "先聊熟再定":
            risk_flags.append("推进方式偏慢观察")

    if (
        high_bar_profile
        and conversation_resonance == "能聊想法也能聊日常"
        and personal_presence == "有记忆点"
        and aesthetic_expression in {"有审美输出", "有生活审美"}
    ):
        reasons.append("条件之外，表达层次也更完整")
        score_bonus += 4
        match_evidence.append(
            "条件之外，表达层次也更完整 <- 聊天共鸣/人物感/审美表达组合更完整"
        )
    if (
        high_bar_profile
        and lightness_humor == "有点幽默不端着"
        and conversation_resonance == "能聊想法也能聊日常"
    ):
        reasons.append("互动不容易太板正")
        score_bonus += 3
        match_evidence.append("互动不容易太板正 <- 轻松感/聊天共鸣更完整")

    return {
        "matched_on": reasons,
        "risk_flags": risk_flags,
        "match_evidence": match_evidence,
        "score_bonus": score_bonus,
        "missing_fields": [],
    }


def has_explicit_field_value(record, field):
    if field == "has_children":
        return effective_has_children(record) is not None

    value = record.get(field)
    if value is None or value == "":
        return False

    lowered = as_lower(value)
    if lowered in UNKNOWN_VALUES:
        return False
    return True


def build_follow_up_questions(record, missing_fields, risk_flags, self_profile=None):
    questions = []
    self_profile = self_profile or {}
    candidate_city = record.get("city")
    self_city = self_profile.get("city")

    for field in unique_ordered(missing_fields):
        if field == "smoking":
            questions.append("确认是否抽烟，以及频率如何。")
        elif field == "drinking":
            questions.append("确认是否喝酒，以及频率和场景。")
        elif field == "long_distance":
            questions.append("确认是否接受异地，以及多远算异地。")
        elif field == "settlement_city":
            questions.append("确认长期打算定居在哪个城市。")
        elif field == "marital_status":
            questions.append("确认当前婚况是否与你预期一致。")
        elif field == "want_children":
            questions.append("确认未来是否想要孩子，以及时间安排。")
        elif field == "marriage_timeline":
            questions.append("确认结婚节奏，是1年内推进还是合适再定。")
        elif field == "accept_partner_children":
            questions.append("确认是否能长期接受伴侣已有孩子，以及现实安排怎么想。")
        elif field == "accept_partner_children_semantics":
            questions.append("确认对方对子女情况到底是能接受，还是只是态度偏保留。")
        elif field == "accept_marital_status":
            questions.append("确认是否真的接受你的婚史，而不是表面上说可以。")
        elif field == "accept_marital_status_semantics":
            questions.append("确认对方对婚史是明确接受，还是要看具体人和相处质量。")
        elif field == "accept_smoking":
            questions.append("确认是否真的接受伴侣抽烟，而不是先聊着再说。")
        elif field == "accept_drinking":
            questions.append("确认是否真的接受伴侣偶尔喝酒。")
        elif field == "accept_long_distance":
            if self_city and candidate_city and as_lower(self_city) != as_lower(candidate_city):
                questions.append("确认异地是否能长期接受，以及见面频率怎么安排。")
        elif field == "life_routine":
            questions.append("确认平时作息到底稳不稳，工作日和周末差别大不大。")
        elif field == "communication_style":
            questions.append("确认沟通频率和方式，遇到问题是当下聊还是闷着。")
        elif field == "dating_pace":
            questions.append("确认推进节奏，是慢热观察型还是想尽快认真推进。")
        elif field == "expression_style":
            questions.append("确认对方是不是会表达、有生活感，聊天会不会太干。")
        elif field == "relationship_capacity":
            questions.append("确认对方现在有没有稳定投入关系的时间和精力。")
        elif field == "interaction_comfort":
            questions.append("确认相处会不会累，遇到分歧时是能聊开还是会绷着。")
        elif field == "patience_level":
            questions.append("确认对方耐心够不够，推进时会不会容易着急。")
        elif field == "life_texture":
            questions.append("确认对方是不是只有稳定条件，还是生活里也有表达和趣味。")
        elif field == "career_intensity":
            questions.append("确认工作节奏到底有多忙，关系里能不能稳定投入。")
        elif field == "exercise_habit":
            questions.append("确认有没有稳定运动或身体管理习惯。")
        elif field == "growth_signal":
            questions.append("确认对方现在是稳定型，还是还在明显上升期。")
        elif field == "warmth_style":
            questions.append("确认聊天有没有温度，还是只是礼貌理性地回复。")
        elif field == "aesthetic_expression":
            questions.append("确认对方是不是有自己的审美和表达，不只是资料写得漂亮。")
        elif field == "blended_family_readiness":
            questions.append("确认对方有没有认真想过离异带娃后的现实安排，而不是只说可以。")
        elif field == "consumption_attitude":
            questions.append("确认对方花钱更看重什么，是清醒务实，还是容易被外在包装带着走。")
        elif field == "chat_texture":
            questions.append("确认对方聊天是顺着聊不费劲，还是容易只剩条件交换。")
        elif field == "relationship_execution":
            questions.append("确认对方认真推进时，会不会把见面节奏、关系预期和现实安排说清。")

    for risk in unique_ordered(risk_flags):
        if risk == "对方对子女情况仅可协商":
            questions.append("确认对方是能真正接受你有孩子，还是只是暂时不想说死。")
        elif risk == "对方对子女接受度偏低":
            questions.append("确认对方对子女情况是不是现实里会比较难接受，不要只看口头上没拒绝。")
        elif risk == "对方对子女接受需要先接触再判断":
            questions.append("确认对方对子女情况是不是只有接触意愿，真到关系推进时会不会犹豫。")
        elif risk == "对方城市偏好未命中，但资料写了接受异地":
            questions.append("确认城市不是对方的硬门槛，异地或跨城推进在现实里怎么落地。")
        elif risk == "对方城市偏好未命中，异地仅可协商":
            questions.append("确认城市偏好没命中时，对方是不是只是嘴上可协商，现实里会不会很快卡住。")
        elif risk == "对方城市偏好未命中，异地接受度未知":
            questions.append("确认城市偏好没命中的情况下，对方到底能不能接受跨城推进。")
        elif risk == "对方不接受长期异地，需要确认落地计划":
            questions.append("确认对方能接受的是短期过渡，还是只要长期异地就会卡住，以及落地计划怎么定。")
        elif risk == "异地需要明确落地计划":
            questions.append("确认跨城推进有没有明确落地计划，不要只停留在原则上可以。")
        elif risk == "非同城，见面推进成本更高":
            questions.append("确认见面频率、通勤成本和落地安排，不要默认跨城也能自然推进。")
        elif risk == "对方对喝酒仅可协商":
            questions.append("确认偶尔喝酒在对方那里是能接受，还是只是勉强可协商。")
        elif risk == "对方对抽烟仅可协商":
            questions.append("确认抽烟问题是不是对方的硬雷点。")
        elif risk == "对方异地仅可协商":
            questions.append("确认异地推进的底线和可执行方式，不要只停留在口头可协商。")
        elif risk == "90天前活跃":
            questions.append("确认对方现在是否还在认真相亲，以及回复节奏是否稳定。")
        elif risk == "对方年龄要求可能可放宽":
            questions.append("确认年龄差在对方那里到底是不是硬门槛，别一上来就自我淘汰。")
        elif risk == "对方身高要求可能可放宽":
            questions.append("确认身高条件是硬卡，还是聊得来可以放宽。")
        elif risk == "对方学历要求可能可放宽":
            questions.append("确认学历要求是不是死卡，还是更看实际认知和相处。")
        elif risk == "对方收入要求可能可放宽":
            questions.append("确认对方在意的是收入数字，还是更在意生活方式和相处压力。")
        elif risk == "对方婚史接受度偏保守":
            questions.append("确认对方对婚史是长期能接受，还是只是暂时不想说死。")
        elif risk == "对方婚史接受需要先聊再判断":
            questions.append("确认对方对婚史是不是先聊了再说，后面会不会卡在现实接受度上。")
        elif risk == "对方婚史接受度未知":
            questions.append("确认对方对婚史的接受到底有多明确，别只看到可接受范围。")
        elif risk == "对方对子女接受度偏保守":
            questions.append("确认对方能不能长期接受孩子和现实安排，不要只停留在口头上。")
        elif risk == "学历没有完全卡进你的底线":
            questions.append("确认学历底线是不是只作参考，不然明显低于预期的人不该排到前面。")
        elif risk == "生活阶段可能有落差":
            questions.append("确认你们的收入压力、消费方式和长期生活节奏是不是一个频道。")
        elif risk == "资料偏稳但不够鲜活":
            questions.append("确认对方是不是只有条件合适，还是聊天和生活里也真的有感觉。")
        elif risk == "相处可能偏冷":
            questions.append("确认对方理性之外有没有温度，聊天会不会太端着。")
        elif risk == "相处节奏可能偏赶":
            questions.append("确认推进会不会太快，会不会让你有压力。")
        elif risk == "忙的时候可能更难推进":
            questions.append("确认工作忙时的沟通和见面安排能不能稳定下来。")
        elif risk == "工作节奏偏忙，稳定投入要再看":
            questions.append("确认对方工作到底有多忙，周中回复和见面能不能稳定。")
        elif risk == "主动沟通感偏弱":
            questions.append("确认对方是慢热还是低反馈，别聊着聊着只剩你一个人在推进。")
        elif risk == "乐观外放感偏弱":
            questions.append("确认对方是稳定安静型，还是实际相处里会偏闷、偏没劲。")
        elif risk == "消费观还不够具体":
            questions.append("确认对方的消费观到底是清醒务实，还是只是资料里泛泛写正常。")
        elif risk == "聊天还像完成任务":
            questions.append("确认对方聊天是不是容易只讲条件和流程，还是能把话题真正聊活。")
        elif risk == "认真相处信号还不够落地":
            questions.append("确认对方是不是只说想认真相处，还是会真的把见面和节奏往前推。")
        elif risk == "认真相处推进偏慢":
            questions.append("确认对方是稳一点，还是会把认真相处一直拖在观察阶段。")
        elif risk == "长期意图有，但推进方式还不够落地":
            questions.append("确认对方不是只会说想长期，而是真的会把推进节奏和安排说清。")
        elif risk == "多项条件需要放宽后才成立":
            questions.append("确认这段匹配到底是少数几个点不完美，还是很多关键条件都要靠放宽才行。")
        elif risk == "推进方式偏慢观察":
            questions.append("确认对方是慢热但会往前走，还是会一直停在观察阶段。")
        elif risk == "成长势能偏弱":
            questions.append("确认对方接下来几年是继续往上走，还是更偏稳定守成。")
        elif risk == "聊天温度偏冷":
            questions.append("确认对方是不是只在资料里理性，实际聊天会不会太冷。")
        elif risk == "审美表达偏平":
            questions.append("确认对方有没有自己的生活审美和表达，而不是只有基础条件。")
        elif risk == "聊天可能像信息交换":
            questions.append("确认对方聊天是不是只在交换条件和流程，还是能真正聊出共鸣。")
        elif risk == "人物感偏淡":
            questions.append("确认对方除了条件在线，有没有让你记住和想继续了解的点。")
        elif risk == "聊天可能偏板正":
            questions.append("确认对方是不是太稳太克制，实际聊天会不会少一点轻松感和火花。")
        elif risk == "进入关系信号偏弱":
            questions.append("确认对方到底是明确奔着长期来，还是只是先聊着看感觉。")
        elif risk == "重组家庭现实承接仍需确认":
            questions.append("确认对方有没有具体想过孩子、时间和家庭安排，不要只停留在口头接受。")
        elif risk.startswith("资料里提到“"):
            keyword = str(risk).removeprefix("资料里提到“").split("”", 1)[0]
            questions.append(f"确认对方提到“{keyword}”是在表达边界，还是现实里真的会出现这类问题。")

    return unique_ordered(questions)[:5]


def normalize_record(raw):
    record = {}
    for key, value in raw.items():
        canonical = ALIAS_LOOKUP.get(normalize_key(key), normalize_key(key))
        record[canonical] = value

    if "source_file" not in record:
        record["source_file"] = ""

    for key, value in list(record.items()):
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        record[key] = value

    if record.get("age") is not None:
        match = re.search(r"\d+", str(record["age"]))
        record["age"] = int(match.group()) if match else None

    if record.get("height") is not None:
        match = re.search(r"\d+", str(record["height"]))
        record["height"] = int(match.group()) if match else None

    if record.get("income_min_wan") is None and record.get("income_max_wan") is None:
        income_min, income_max = parse_income_range_to_wan(record.get("income_range"))
        if income_min is not None:
            record["income_min_wan"] = income_min
        if income_max is not None:
            record["income_max_wan"] = income_max

    record["matcher_traits"] = parse_json_object(record.get("matcher_traits_json"))
    record["matcher_preferences"] = parse_json_object(record.get("matcher_preferences_json"))
    record["matcher_risks"] = parse_json_object(record.get("matcher_risks_json"))

    record["combined_text"] = build_combined_text(record)
    return record


def build_source_file_ref(source, table_name=None):
    return _build_source_file_ref(source, table_name)


def split_source_file_ref(source_ref):
    return _split_source_file_ref(source_ref)


def build_combined_text(record):
    parts = []
    for key in TEXT_FIELDS:
        value = record.get(key)
        if value:
            parts.append(str(value))
    return " | ".join(parts).lower()


def _build_search_source_runtime() -> SearchSourceRuntime:
    return SearchSourceRuntime(
        alias_lookup=ALIAS_LOOKUP,
        verified_level_order=VERIFIED_LEVEL_ORDER,
        photo_verification_level_order=PHOTO_VERIFICATION_LEVEL_ORDER,
        default_mysql_photos_table=DEFAULT_MYSQL_PHOTOS_TABLE,
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_key=normalize_key,
        verified_rank=verified_rank,
        photo_verification_rank=photo_verification_rank,
        normalize_record=normalize_record,
        build_source_file_ref=build_source_file_ref,
        split_source_file_ref=split_source_file_ref,
        redact_mysql_source=redact_mysql_source,
        resolve_profile_source=resolve_profile_source,
        detect_profile_table=detect_profile_table,
        list_profile_columns=list_profile_columns,
        list_profile_previews=list_profile_photo_previews,
        list_profiles=list_profiles,
        load_mysql_photo_previews_fn=load_mysql_photo_previews,
    )


def _build_search_trust_runtime() -> SearchTrustRuntime:
    return SearchTrustRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        verified_rank=verified_rank,
        effective_activity_datetime=effective_activity_datetime,
        effective_has_children=effective_has_children,
        parse_income_range_to_wan=parse_income_range_to_wan,
        unique_ordered=unique_ordered,
    )


def _build_search_no_match_runtime() -> SearchNoMatchRuntime:
    return SearchNoMatchRuntime(
        field_display_name=field_display_name,
        unique_ordered=unique_ordered,
        evaluate_candidate=evaluate_candidate,
        result_sort_key=result_sort_key,
        select_diverse_results=select_diverse_results,
        format_text=format_text,
    )


def _build_search_reciprocal_runtime() -> SearchReciprocalRuntime:
    return SearchReciprocalRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        split_keywords=split_keywords,
        parse_json_object=parse_json_object,
        unique_ordered=unique_ordered,
        build_rejection_reason=build_rejection_reason,
        normalize_strictness_state=normalize_strictness_state,
        soft_preference_risk_flag=soft_preference_risk_flag,
        reciprocal_city_preference_risk_flag=reciprocal_city_preference_risk_flag,
        normalize_acceptance_state=normalize_acceptance_state,
        location_semantics_risk_flags=location_semantics_risk_flags,
        education_rank=education_rank,
        marital_status_match_options=marital_status_match_options,
        normalize_acceptance_strength=normalize_acceptance_strength,
        marital_acceptance_risk_flag=marital_acceptance_risk_flag,
        children_acceptance_risk_flag=children_acceptance_risk_flag,
        habit_requires_acceptance=habit_requires_acceptance,
    )


def _build_search_ranking_runtime() -> SearchRankingRuntime:
    return SearchRankingRuntime(
        as_int=as_int,
        as_text=as_text,
        strip_internal_fields=strip_internal_fields,
        diversity_job_patterns=DIVERSITY_JOB_PATTERNS,
    )


def parse_mysql_source(source, table_name=None):
    return _parse_mysql_source(_build_search_source_runtime(), source, table_name=table_name)


def quote_mysql_ident(identifier):
    return _quote_mysql_ident(identifier)


def resolve_mysql_columns(conn, database, table):
    return _resolve_mysql_columns(_build_search_source_runtime(), conn, database, table)


def build_mysql_prefilter(criteria, canonical_to_actual, include_ids=None, include_ids_mode="or"):
    return _build_mysql_prefilter(
        _build_search_source_runtime(),
        criteria,
        canonical_to_actual,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def load_mysql(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    return _load_mysql(
        _build_search_source_runtime(),
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def load_mysql_photo_previews(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
    return _load_mysql_photo_previews(
        _build_search_source_runtime(),
        source,
        profile_ids,
        table_name=table_name,
        photos_table_name=photos_table_name,
        preview_count=preview_count,
    )


def detect_mysql_profile_table(conn, database):
    return _detect_mysql_profile_table(_build_search_source_runtime(), conn, database)


def load_source(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    return _load_source(
        _build_search_source_runtime(),
        source,
        is_mysql_source=is_mysql_source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def build_criteria_from_args(args):
    criteria = {}

    if args.gender:
        criteria["gender"] = str(args.gender).strip().lower()

    for key in ("age_min", "age_max", "height_min", "height_max"):
        value = getattr(args, key)
        if value is not None:
            criteria[key] = value

    cities = merge_keyword_args(args.city)
    if cities:
        criteria["cities"] = cities
    districts = merge_keyword_args(args.district)
    if districts:
        criteria["districts"] = districts
    settlement_cities = merge_keyword_args(args.settlement_city)
    if settlement_cities:
        criteria["settlement_cities"] = settlement_cities

    relationship_goals = merge_keyword_args(args.relationship_goal)
    if relationship_goals:
        criteria["relationship_goals"] = relationship_goals

    must_not_have = merge_keyword_args(args.must_not_have)
    if must_not_have:
        criteria["must_not_have"] = must_not_have

    must_have = merge_keyword_args(args.must_have)
    hard_must_have, soft_must_have = split_must_have_keywords(must_have)
    if hard_must_have:
        criteria["must_have"] = hard_must_have

    prefer = merge_keyword_args(args.prefer)
    if soft_must_have:
        prefer = unique_ordered(prefer + soft_must_have)
    if prefer:
        criteria["prefer"] = prefer

    if args.smoking:
        criteria["smoking"] = args.smoking
    if args.drinking:
        criteria["drinking"] = args.drinking
    if args.long_distance:
        criteria["long_distance"] = args.long_distance
    if args.housing_status:
        criteria["housing_statuses"] = merge_keyword_args(args.housing_status)
    if args.car_status:
        criteria["car_statuses"] = merge_keyword_args(args.car_status)
    if args.marital_status:
        criteria["marital_statuses"] = merge_keyword_args(args.marital_status)
    if args.has_children is not None:
        criteria["has_children"] = bool(args.has_children)
    if args.want_children:
        criteria["want_children"] = args.want_children
    if args.accept_partner_children:
        criteria["accept_partner_children"] = args.accept_partner_children
    accept_marital_status_strength = getattr(args, "accept_marital_status_strength", None)
    if accept_marital_status_strength:
        criteria["accept_marital_status_strength"] = accept_marital_status_strength
    accept_partner_children_strength = getattr(args, "accept_partner_children_strength", None)
    if accept_partner_children_strength:
        criteria["accept_partner_children_strength"] = accept_partner_children_strength
    if args.marriage_timeline:
        criteria["marriage_timelines"] = merge_keyword_args(args.marriage_timeline)
    criteria["profile_statuses"] = merge_keyword_args(args.profile_status) or ["active"]
    if args.active_within_days is not None:
        criteria["active_within_days"] = args.active_within_days
    if args.verified_level_min:
        criteria["verified_level_min"] = args.verified_level_min
    if args.verified_level:
        criteria["verified_levels"] = merge_keyword_args(args.verified_level)
    photo_verification_level_min = getattr(args, "photo_verification_level_min", None)
    if photo_verification_level_min:
        criteria["photo_verification_level_min"] = photo_verification_level_min
    photo_verification_level = getattr(args, "photo_verification_level", None)
    if photo_verification_level:
        criteria["photo_verification_levels"] = merge_keyword_args(photo_verification_level)
    if args.photo_count_min is not None:
        criteria["photo_count_min"] = args.photo_count_min
    required_known_fields = [
        ALIAS_LOOKUP.get(normalize_key(field), normalize_key(field))
        for field in merge_keyword_args(getattr(args, "require_known", None))
    ]
    if required_known_fields:
        criteria["required_known_fields"] = required_known_fields
    criteria["exclude_ids"] = {item for item in args.exclude_id or []}
    exclude_source_channels = merge_keyword_args(getattr(args, "exclude_source_channel", None))
    if exclude_source_channels:
        criteria["exclude_source_channels"] = {
            as_lower(item) for item in exclude_source_channels if as_lower(item)
        }

    return criteria


def normalize_request_criteria(criteria):
    criteria = dict(criteria or {})
    normalized = {}

    scalar_values = {}
    for target_key, aliases in REQUEST_SCALAR_CRITERIA_ALIASES.items():
        scalar_values[target_key] = first_defined(criteria, aliases)

    if scalar_values["gender"]:
        normalized["gender"] = as_text(scalar_values["gender"]).lower()

    for key in ("age_min", "age_max", "height_min", "height_max", "active_within_days", "photo_count_min"):
        value = as_int(scalar_values.get(key))
        if value is not None:
            normalized[key] = value

    for key in (
        "smoking",
        "drinking",
        "long_distance",
        "want_children",
        "accept_partner_children",
        "accept_marital_status_strength",
        "accept_partner_children_strength",
        "verified_level_min",
        "photo_verification_level_min",
    ):
        value = scalar_values.get(key)
        if value is not None and value != "":
            normalized[key] = value

    has_children = normalize_bool(scalar_values.get("has_children"))
    if has_children is not None:
        normalized["has_children"] = has_children

    for target_key, aliases in REQUEST_SEQUENCE_CRITERIA_ALIASES.items():
        values = merge_keyword_values(first_defined(criteria, aliases))
        if not values:
            continue
        if target_key == "required_known_fields":
            normalized[target_key] = [
                ALIAS_LOOKUP.get(normalize_key(field), normalize_key(field))
                for field in values
            ]
        else:
            normalized[target_key] = values

    must_have = normalized.pop("must_have", [])
    hard_must_have, soft_must_have = split_must_have_keywords(must_have)
    if hard_must_have:
        normalized["must_have"] = hard_must_have
    prefer = normalized.get("prefer", [])
    if soft_must_have:
        prefer = unique_ordered(prefer + soft_must_have)
    if prefer:
        normalized["prefer"] = prefer

    exclude_ids = first_defined(criteria, ("exclude_ids", "exclude_id"))
    if exclude_ids is None:
        normalized["exclude_ids"] = set()
    elif isinstance(exclude_ids, (list, tuple, set)):
        normalized["exclude_ids"] = {item for item in (as_int(value) for value in exclude_ids) if item is not None}
    else:
        exclude_id = as_int(exclude_ids)
        normalized["exclude_ids"] = {exclude_id} if exclude_id is not None else set()

    exclude_source_channels = first_defined(criteria, ("exclude_source_channels", "exclude_source_channel"))
    if exclude_source_channels is None:
        normalized["exclude_source_channels"] = set()
    elif isinstance(exclude_source_channels, (list, tuple, set)):
        normalized["exclude_source_channels"] = {
            item for item in (as_lower(value) for value in exclude_source_channels) if item
        }
    else:
        exclude_source_channel = as_lower(exclude_source_channels)
        normalized["exclude_source_channels"] = (
            {exclude_source_channel} if exclude_source_channel else set()
        )

    profile_statuses = normalized.get("profile_statuses")
    if not profile_statuses:
        normalized["profile_statuses"] = ["active"]

    if "exclude_record_refs" in criteria and criteria["exclude_record_refs"] is not None:
        normalized["exclude_record_refs"] = set(criteria["exclude_record_refs"])

    if "self_profile" in criteria and criteria["self_profile"]:
        normalized["self_profile"] = normalize_self_profile_input(criteria["self_profile"])

    return normalized


def resolve_self_profile_record(self_id, records):
    matched_records = [record for record in records if as_int(record.get("id")) == self_id]
    if not matched_records:
        raise ValueError(f"Could not find self profile id {self_id} in the selected source.")
    distinct_sources = unique_ordered(record.get("source_file") or "" for record in matched_records)
    if len(distinct_sources) > 1:
        readable_sources = [redact_source_ref(source) or "<unknown source>" for source in distinct_sources]
        raise ValueError(
            f"Self profile id {self_id} is ambiguous across multiple sources: "
            + ", ".join(readable_sources)
            + ". Narrow --source or use a unique id."
        )
    return matched_records[0]


def normalize_self_profile_input(profile):
    if not profile:
        return None
    if not any(value is not None and value != "" for value in profile.values()):
        return None

    normalized = normalize_record(dict(profile))
    income_wan = as_int(normalized.get("income_wan"))
    if income_wan is not None:
        normalized["income_min_wan"] = income_wan
        normalized["income_max_wan"] = income_wan

    if normalized.get("income_min_wan") is None and normalized.get("income_max_wan") is None:
        income_min, income_max = parse_income_range_to_wan(normalized.get("income_range"))
        if income_min is not None:
            normalized["income_min_wan"] = income_min
        if income_max is not None:
            normalized["income_max_wan"] = income_max

    normalized["has_children"] = normalize_bool(normalized.get("has_children"))
    normalized["combined_text"] = build_combined_text(normalized)
    return normalized


def build_self_profile(records, self_id=None, profile_input=None):
    profile = {}

    if self_id is not None:
        matched = resolve_self_profile_record(self_id, records)
        profile.update(strip_internal_fields(matched))
        profile["source_file"] = matched.get("source_file") or ""
        income_min, income_max = parse_income_range_to_wan(matched.get("income_range"))
        profile["income_min_wan"] = income_min
        profile["income_max_wan"] = income_max

    normalized_input = normalize_self_profile_input(profile_input)
    if normalized_input:
        existing_source = profile.get("source_file") or ""
        profile.update(strip_internal_fields(normalized_input))
        if existing_source and not profile.get("source_file"):
            profile["source_file"] = existing_source

    if not profile:
        return None

    if self_id is not None:
        profile["id"] = self_id
    profile["has_children"] = normalize_bool(profile.get("has_children"))
    profile["combined_text"] = build_combined_text(profile)
    return profile


def build_self_profile_from_args(args, records):
    profile_input = {
        "age": args.self_age,
        "city": args.self_city,
        "height": args.self_height,
        "education": args.self_education,
        "job": getattr(args, "self_job", None),
        "marital_status": args.self_marital_status,
        "smoking": args.self_smoking,
        "drinking": args.self_drinking,
    }
    if args.self_income_wan is not None:
        profile_input["income_wan"] = args.self_income_wan
    if args.self_has_children is not None:
        profile_input["has_children"] = bool(args.self_has_children)

    return build_self_profile(
        records,
        self_id=args.self_id,
        profile_input=profile_input,
    )


def exact_match(value, expected):
    return _exact_match(_build_search_reciprocal_runtime(), value, expected)


def match_any_exact(value, candidates):
    return _match_any_exact(_build_search_reciprocal_runtime(), value, candidates)


def income_range_overlaps(min_value, max_value, required_min, required_max):
    return _income_range_overlaps(min_value, max_value, required_min, required_max)


def activity_score_info(record):
    return _activity_score_info(_build_search_trust_runtime(), record)


def verified_score_info(record):
    return _verified_score_info(_build_search_trust_runtime(), record)


def verified_level_label(value):
    return _verified_level_label(_build_search_trust_runtime(), value)


def photo_verification_level(profile):
    return _photo_verification_level(_build_search_trust_runtime(), profile)


def photo_verification_level_label(value):
    return _photo_verification_level_label(_build_search_trust_runtime(), value)


def normalize_field_verification_status(value, fallback="self_reported"):
    return _normalize_field_verification_status(
        _build_search_trust_runtime(),
        value,
        fallback=fallback,
    )


def profile_field_verification_raw_status(profile, field_key):
    return _profile_field_verification_raw_status(
        _build_search_trust_runtime(),
        profile,
        field_key,
    )


def profile_field_verification_status(profile, field_key, fallback="self_reported"):
    return _profile_field_verification_status(
        _build_search_trust_runtime(),
        profile,
        field_key,
        fallback=fallback,
    )


def format_income_range_text(record):
    return _format_income_range_text(_build_search_trust_runtime(), record)


def build_profile_consistency_flags(profile):
    return _build_profile_consistency_flags(_build_search_trust_runtime(), profile)


def build_verification_items(profile):
    return _build_verification_items(_build_search_trust_runtime(), profile)


def build_trust_caution_items(profile, verification_items=None):
    return _build_trust_caution_items(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
    )


def build_trust_actions(profile, verification_items=None, caution_items=None):
    return _build_trust_actions(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
        caution_items=caution_items,
    )


def build_trust_summary(profile, verification_items=None):
    return _build_trust_summary(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
    )


def build_rejection_reason(code, detail=None):
    return _build_rejection_reason(code, detail=detail)


def parse_rejection_reason(reason):
    return _parse_rejection_reason(reason)


def format_rejection_reason(reason):
    return _format_rejection_reason(_build_search_no_match_runtime(), reason)


def suggestion_for_rejection(reason):
    return _suggestion_for_rejection(_build_search_no_match_runtime(), reason)


def build_no_match_diagnostics(records, criteria):
    return _build_no_match_diagnostics(
        _build_search_no_match_runtime(),
        records,
        criteria,
    )


def build_no_match_diagnostics_payload(
    scanned_count,
    passed_count,
    usable_count,
    top_reasons,
    relax_suggestions,
):
    return _build_no_match_diagnostics_payload(
        scanned_count=scanned_count,
        passed_count=passed_count,
        usable_count=usable_count,
        top_reasons=top_reasons,
        relax_suggestions=relax_suggestions,
    )


def build_fallback_candidates(records, criteria, limit=3):
    return _build_fallback_candidates(
        _build_search_no_match_runtime(),
        records,
        criteria,
        limit=limit,
    )


def format_no_match_text(diagnostics, fallback_results=None):
    return _format_no_match_text(
        _build_search_no_match_runtime(),
        diagnostics,
        fallback_results=fallback_results,
    )


def matcher_preference_tags(record):
    return _matcher_preference_tags(_build_search_reciprocal_runtime(), record)


def evaluate_reciprocal_compatibility(record, self_profile, diagnostics=False, reciprocal_mode="strict"):
    return _evaluate_reciprocal_compatibility(
        _build_search_reciprocal_runtime(),
        record,
        self_profile,
        diagnostics=diagnostics,
        reciprocal_mode=reciprocal_mode,
    )


def evaluate_candidate(record, criteria, diagnostics=False, reciprocal_mode="strict"):
    def fail(reason, detail=None):
        if not diagnostics:
            return None
        activity_dt = effective_activity_datetime(record)
        return build_match_result(
            record=record,
            score=0,
            fit_score=0,
            confidence_score=0,
            risk_score=0,
            matched_on=[],
            reciprocal_on=[],
            missing_fields=[],
            self_profile_gaps=[],
            risk_flags=[],
            match_evidence=[],
            follow_up_questions=[],
            verified_rank=verified_rank(record.get("verified_level")),
            activity_sort_ts=int(activity_dt.timestamp()) if activity_dt else 0,
            profile_status_rank=profile_status_rank(record.get("profile_status")),
            matched=False,
            reject_reason=build_rejection_reason(reason, detail),
        )

    reasons = []
    reciprocal_reasons = []
    missing_fields = []
    risk_flags = []
    match_evidence = []
    fit_score = 0
    confidence_score = 0

    if record_ref(record) in criteria.get("exclude_record_refs", set()):
        return fail("exclude_record_ref")
    if as_int(record.get("id")) in criteria.get("exclude_ids", set()):
        return fail("exclude_id")
    source_channel = as_lower(record.get("source_channel"))
    if source_channel and source_channel in criteria.get("exclude_source_channels", set()):
        return fail("exclude_source_channel")

    profile_status = record.get("profile_status")
    allowed_statuses = criteria.get("profile_statuses") or ["active"]
    if not profile_status:
        missing_fields.append("profile_status")
    else:
        if not match_any_exact(profile_status, allowed_statuses):
            return fail("profile_status_mismatch")
        reasons.append(f"状态 {profile_status}")
        confidence_score += 4

    active_at = effective_activity_datetime(record)
    if criteria.get("active_within_days") is not None:
        if active_at is None:
            missing_fields.append("last_active_at")
            return fail("active_time_missing")
        if active_at < datetime.now() - timedelta(days=criteria["active_within_days"]):
            return fail("active_too_old")

    if criteria.get("verified_level_min"):
        if verified_rank(record.get("verified_level")) < verified_rank(criteria["verified_level_min"]):
            return fail("verified_below_min")

    if criteria.get("photo_verification_level_min"):
        if photo_verification_rank(photo_verification_level(record)) < photo_verification_rank(criteria["photo_verification_level_min"]):
            return fail("photo_verification_below_min")

    age = record.get("age")
    if criteria.get("age_min") is not None:
        if age is None:
            missing_fields.append("age")
        elif age < criteria["age_min"]:
            return fail("age_below_min")
        else:
            reasons.append(f"年龄 {age}")
            fit_score += 15
    if criteria.get("age_max") is not None:
        if age is None:
            if "age" not in missing_fields:
                missing_fields.append("age")
        elif age > criteria["age_max"]:
            return fail("age_above_max")

    height = record.get("height")
    height_reason_added = False
    if criteria.get("height_min") is not None:
        if height is None:
            missing_fields.append("height")
        elif height < criteria["height_min"]:
            return fail("height_below_min")
        else:
            reasons.append(f"身高 {height}cm")
            height_reason_added = True
            fit_score += 5
    if criteria.get("height_max") is not None:
        if height is None:
            if "height" not in missing_fields:
                missing_fields.append("height")
        elif height > criteria["height_max"]:
            return fail("height_above_max")
        elif not height_reason_added:
            reasons.append(f"身高 {height}cm")
            height_reason_added = True

    if criteria.get("gender"):
        gender = as_lower(record.get("gender"))
        if not gender:
            missing_fields.append("gender")
        elif gender != criteria["gender"]:
            return fail("gender_mismatch")
        else:
            reasons.append(f"性别 {record.get('gender')}")
            fit_score += 10

    if criteria.get("cities"):
        city = as_lower(record.get("city"))
        if not city:
            missing_fields.append("city")
        elif city not in [as_lower(item) for item in criteria["cities"]]:
            return fail("city_mismatch")
        else:
            reasons.append(f"城市 {record.get('city')}")
            fit_score += 20

    self_profile = criteria.get("self_profile") or {}
    self_city = self_profile.get("city")
    candidate_city = record.get("city")
    near_distance_priority = self_prefers_near_distance(self_profile)
    if self_city and candidate_city and as_lower(self_city) == as_lower(candidate_city):
        reasons.append("同城")
        fit_score += 8
        if near_distance_priority:
            reasons.append("近距离更省心")
            fit_score += 4
    elif self_city and candidate_city and near_distance_priority:
        risk_flags.append("非同城，见面推进成本更高")

    if criteria.get("districts"):
        district = as_lower(record.get("district"))
        if not district:
            missing_fields.append("district")
        elif district not in [as_lower(item) for item in criteria["districts"]]:
            return fail("district_mismatch")
        else:
            reasons.append(f"区域 {record.get('district')}")
            fit_score += 8

    if criteria.get("settlement_cities"):
        settlement_city = as_lower(record.get("settlement_city"))
        if not settlement_city:
            missing_fields.append("settlement_city")
        elif settlement_city not in [as_lower(item) for item in criteria["settlement_cities"]]:
            return fail("settlement_city_mismatch")
        else:
            reasons.append(f"定居 {record.get('settlement_city')}")
            fit_score += 8
    elif self_city and record.get("settlement_city") and as_lower(record.get("settlement_city")) == as_lower(self_city):
        reasons.append("定居与你同城")
        fit_score += 4

    if criteria.get("relationship_goals"):
        goal = as_lower(record.get("relationship_goal"))
        if not goal:
            missing_fields.append("relationship_goal")
        elif goal not in [as_lower(item) for item in criteria["relationship_goals"]]:
            return fail("relationship_goal_mismatch")
        else:
            reasons.append(f"目标 {record.get('relationship_goal')}")
            fit_score += 15
            fit_score += RELATIONSHIP_GOAL_STRENGTH_BONUS.get(record.get("relationship_goal"), 0)

    if criteria.get("must_have"):
        for keyword in criteria["must_have"]:
            if not keyword_matches_record(record, keyword):
                return fail("must_have_missing", keyword)
            reasons.append(f"包含 {keyword}")
            fit_score += 8
            evidence = extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if criteria.get("must_not_have"):
        for keyword in criteria["must_not_have"]:
            exclusion = evaluate_exclusion_keyword(record, keyword)
            if exclusion["blocked"]:
                return fail("must_not_have_hit", keyword)
            if exclusion.get("risk_flag"):
                risk_flags.append(exclusion["risk_flag"])

    matched_prefer_count = 0
    for keyword in criteria.get("prefer", []):
        if keyword_matches_record(record, keyword):
            reasons.append(f"偏好命中 {keyword}")
            fit_score += 6
            matched_prefer_count += 1
            evidence = extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if matched_prefer_count >= 3:
        fit_score += 4
    elif matched_prefer_count >= 2:
        fit_score += 2

    self_education_floor_risk = self_education_floor_risk_flag(criteria.get("self_profile") or {}, record)
    if self_education_floor_risk == "education_below_self_preference":
        return fail("education_below_self_preference")
    if self_education_floor_risk:
        risk_flags.append(self_education_floor_risk)

    if criteria.get("smoking"):
        smoking = as_lower(record.get("smoking"))
        desired = as_lower(criteria["smoking"])
        if not smoking:
            missing_fields.append("smoking")
        elif smoking != desired:
            return fail("smoking_mismatch")
        else:
            if desired in {"否", "不抽烟", "不吸烟"}:
                reasons.append("不抽烟")
            else:
                reasons.append(f"抽烟习惯 {record.get('smoking')}")
            fit_score += 8

    if criteria.get("drinking"):
        drinking = as_lower(record.get("drinking"))
        desired = as_lower(criteria["drinking"])
        if not drinking:
            missing_fields.append("drinking")
        elif drinking != desired:
            return fail("drinking_mismatch")
        else:
            if desired in {"否", "不喝酒", "不饮酒"}:
                reasons.append("少酒/不喝酒")
            else:
                reasons.append(f"饮酒习惯 {record.get('drinking')}")
            fit_score += 5

    if criteria.get("long_distance"):
        long_distance = as_lower(record.get("long_distance"))
        desired = as_lower(criteria["long_distance"])
        if not long_distance:
            missing_fields.append("long_distance")
        elif long_distance != desired:
            return fail("long_distance_mismatch")
        else:
            reasons.append(f"异地态度 {record.get('long_distance')}")
            fit_score += 8

    if criteria.get("housing_statuses"):
        housing_status = record.get("housing_status")
        if not housing_status:
            missing_fields.append("housing_status")
        elif not match_any_exact(housing_status, criteria["housing_statuses"]):
            return fail("housing_status_mismatch")
        else:
            reasons.append(f"住房 {housing_status}")
            fit_score += 6

    if criteria.get("car_statuses"):
        car_status = record.get("car_status")
        if not car_status:
            missing_fields.append("car_status")
        elif not match_any_exact(car_status, criteria["car_statuses"]):
            return fail("car_status_mismatch")
        else:
            reasons.append(f"车辆 {car_status}")
            fit_score += 4

    if criteria.get("marital_statuses"):
        marital_status = record.get("marital_status")
        if not marital_status:
            missing_fields.append("marital_status")
        elif not any(
            match_any_exact(option, criteria["marital_statuses"])
            for option in marital_status_match_options({"marital_status": marital_status, "has_children": record.get("has_children")})
        ):
            return fail("marital_status_mismatch")
        else:
            reasons.append(f"婚况 {marital_status}")
            fit_score += 10

    if criteria.get("has_children") is not None:
        has_children = effective_has_children(record)
        if has_children is None:
            missing_fields.append("has_children")
        elif has_children != criteria["has_children"]:
            return fail("has_children_mismatch")
        else:
            reasons.append("子女情况命中")
            fit_score += 10

    if criteria.get("want_children"):
        want_children = record.get("want_children")
        if not want_children:
            missing_fields.append("want_children")
        elif not exact_match(want_children, criteria["want_children"]):
            return fail("want_children_mismatch")
        else:
            reasons.append(f"生育计划 {want_children}")
            fit_score += 8

    if criteria.get("accept_partner_children"):
        accept_partner_children = record.get("accept_partner_children")
        if not accept_partner_children:
            missing_fields.append("accept_partner_children")
        elif not exact_match(accept_partner_children, criteria["accept_partner_children"]):
            return fail("accept_partner_children_mismatch")
        else:
            reasons.append(f"接受对方孩子 {accept_partner_children}")
            fit_score += 6

    if criteria.get("accept_marital_status_strength"):
        marital_strength = record.get("accept_marital_status_strength")
        if not marital_strength:
            missing_fields.append("accept_marital_status_strength")
        elif not exact_match(marital_strength, criteria["accept_marital_status_strength"]):
            return fail("accept_marital_status_strength_mismatch")
        else:
            reasons.append(f"婚史接受真实度 {marital_strength}")
            fit_score += 5

    if criteria.get("accept_partner_children_strength"):
        children_strength = record.get("accept_partner_children_strength")
        if not children_strength:
            missing_fields.append("accept_partner_children_strength")
        elif not exact_match(children_strength, criteria["accept_partner_children_strength"]):
            return fail("accept_partner_children_strength_mismatch")
        else:
            reasons.append(f"对子女接受真实度 {children_strength}")
            fit_score += 5

    if criteria.get("marriage_timelines"):
        marriage_timeline = record.get("marriage_timeline")
        if not marriage_timeline:
            missing_fields.append("marriage_timeline")
        elif not match_any_exact(marriage_timeline, criteria["marriage_timelines"]):
            return fail("marriage_timeline_mismatch")
        else:
            reasons.append(f"结婚节奏 {marriage_timeline}")
            fit_score += 8

    if criteria.get("verified_levels"):
        verified_level = record.get("verified_level") or "none"
        if not match_any_exact(verified_level, criteria["verified_levels"]):
            return fail("verified_level_mismatch")
        reasons.append(f"认证 {verified_level}")
        confidence_score += 4

    if criteria.get("photo_verification_levels"):
        candidate_photo_level = photo_verification_level(record)
        if not match_any_exact(candidate_photo_level, criteria["photo_verification_levels"]):
            return fail("photo_verification_level_mismatch")
        reasons.append(f"照片核验 {photo_verification_level_label(candidate_photo_level)}")
        confidence_score += 3

    if criteria.get("photo_count_min") is not None:
        photo_count = as_int(record.get("photo_count"))
        if photo_count is None:
            missing_fields.append("photo_count")
        elif photo_count < criteria["photo_count_min"]:
            return fail("photo_count_too_low")
        else:
            reasons.append(f"照片 {photo_count}张")
            confidence_score += min(photo_count, 6)

    if not reasons:
        reasons.append("基础条件未提供，按资料完整度保留")

    reciprocal = evaluate_reciprocal_compatibility(
        record,
        criteria.get("self_profile"),
        diagnostics=diagnostics,
        reciprocal_mode=reciprocal_mode,
    )
    if reciprocal is None:
        return fail("reciprocal_mismatch")
    if not reciprocal.get("matched", True):
        return fail(parse_rejection_reason(reciprocal.get("reject_reason"))[0], parse_rejection_reason(reciprocal.get("reject_reason"))[1])
    reciprocal_reasons.extend(reciprocal["matched_on"])
    missing_fields.extend(reciprocal["missing_fields"])
    risk_flags.extend(reciprocal["risk_flags"])
    fit_score += reciprocal["score_bonus"]

    contextual_fit = evaluate_contextual_fit(
        record,
        criteria,
        self_profile=criteria.get("self_profile"),
    )
    reasons.extend(contextual_fit["matched_on"])
    missing_fields.extend(contextual_fit["missing_fields"])
    risk_flags.extend(contextual_fit["risk_flags"])
    match_evidence.extend(contextual_fit["match_evidence"])
    fit_score += contextual_fit["score_bonus"]

    stacked_concession_risk = concession_stack_risk_flag(risk_flags)
    if stacked_concession_risk:
        risk_flags.append(stacked_concession_risk)

    verified_score, verified_label, verified_sort_rank = verified_score_info(record)
    confidence_score += verified_score
    if verified_sort_rank > 0:
        reasons.append(verified_label)
    else:
        risk_flags.append("未认证")

    activity_bonus, activity_label, activity_dt = activity_score_info(record)
    confidence_score += activity_bonus
    if activity_label and activity_bonus > 0:
        reasons.append(activity_label)
    elif activity_dt is None:
        risk_flags.append("活跃时间未知")
    elif activity_label:
        risk_flags.append(activity_label)

    completeness = sum(1 for field in TEXT_FIELDS if record.get(field))
    confidence_score += min(completeness, 10)
    matcher_enrichment_count = sum(
        1 for field in ("matcher_traits", "matcher_preferences", "matcher_risks") if record.get(field)
    )
    if matcher_enrichment_count:
        confidence_score += min(matcher_enrichment_count, 2)

    risk_flags.extend(build_profile_consistency_flags(record))

    required_known_fields = {
        field
        for field in criteria.get("required_known_fields", [])
        if not str(field).startswith("self_")
    }
    for field in required_known_fields:
        if not has_explicit_field_value(record, field) and field not in missing_fields:
            missing_fields.append(field)
    failed_required_known = [
        field for field in unique_ordered(missing_fields) if field in required_known_fields
    ]
    if failed_required_known:
        return fail("required_known_missing", failed_required_known[0])

    all_missing_fields = unique_ordered(missing_fields)
    self_profile_gaps = [
        field for field in all_missing_fields if str(field).startswith("self_")
    ]
    candidate_missing_fields = [
        field for field in all_missing_fields if not str(field).startswith("self_")
    ]
    missing_penalty = sum(missing_field_penalty(field) for field in candidate_missing_fields)
    self_gap_penalty = sum(self_profile_gap_penalty(field) for field in self_profile_gaps)
    risk_score = missing_penalty + sum(
        risk_flag_penalty(flag) for flag in unique_ordered(risk_flags)
    ) + self_gap_penalty
    score = fit_score + confidence_score - risk_score

    follow_up_questions = build_follow_up_questions(
        record,
        candidate_missing_fields,
        risk_flags,
        self_profile=criteria.get("self_profile"),
    )

    result = build_match_result(
        record=record,
        score=score,
        fit_score=fit_score,
        confidence_score=confidence_score,
        risk_score=risk_score,
        matched_on=unique_ordered(reasons),
        reciprocal_on=unique_ordered(reciprocal_reasons),
        missing_fields=candidate_missing_fields,
        self_profile_gaps=self_profile_gaps,
        risk_flags=unique_ordered(risk_flags),
        match_evidence=unique_ordered(match_evidence),
        follow_up_questions=follow_up_questions,
        verified_rank=verified_sort_rank,
        activity_sort_ts=int(activity_dt.timestamp()) if activity_dt else 0,
        profile_status_rank=profile_status_rank(profile_status),
        matched=True,
        reject_reason=None,
    )
    result["display_notes"] = summarize_notes_for_result(
        record,
        criteria,
        criteria.get("self_profile") or {},
    )
    if not diagnostics:
        result.pop("matched", None)
        result.pop("reject_reason", None)
    return result


def build_match_result(
    record,
    score,
    fit_score,
    confidence_score,
    risk_score,
    matched_on,
    reciprocal_on,
    missing_fields,
    self_profile_gaps,
    risk_flags,
    match_evidence,
    follow_up_questions,
    verified_rank,
    activity_sort_ts,
    profile_status_rank,
    matched=True,
    reject_reason=None,
):
    return _build_match_result(
        _build_search_ranking_runtime(),
        record=record,
        score=score,
        fit_score=fit_score,
        confidence_score=confidence_score,
        risk_score=risk_score,
        matched_on=matched_on,
        reciprocal_on=reciprocal_on,
        missing_fields=missing_fields,
        self_profile_gaps=self_profile_gaps,
        risk_flags=risk_flags,
        match_evidence=match_evidence,
        follow_up_questions=follow_up_questions,
        verified_rank=verified_rank,
        activity_sort_ts=activity_sort_ts,
        profile_status_rank=profile_status_rank,
        matched=matched,
        reject_reason=reject_reason,
    )


def unique_ordered(items):
    return unique_ordered_texts(items)


def strip_internal_fields(record):
    cleaned = {}
    for key, value in record.items():
        if key in {"combined_text", "source_file"}:
            continue
        cleaned[key] = value
    return cleaned


def record_ref(record):
    return _record_ref(_build_search_ranking_runtime(), record)


def result_sort_key(result):
    return _result_sort_key(result)


def diversity_job_cluster(job):
    return _diversity_job_cluster(_build_search_ranking_runtime(), job)


def diversity_signature(result):
    return _diversity_signature(_build_search_ranking_runtime(), result)


def diversity_penalty(candidate, selected):
    return _diversity_penalty(_build_search_ranking_runtime(), candidate, selected)


def trim_low_quality_tail(results):
    return _trim_low_quality_tail(results)


def select_diverse_results(results, limit):
    return _select_diverse_results(_build_search_ranking_runtime(), results, limit)


def attach_photo_previews(results, preview_count, photos_table_name=None):
    return _attach_photo_previews(
        _build_search_source_runtime(),
        results,
        preview_count,
        photos_table_name=photos_table_name,
    )


_search_runtime_helpers = SearchRuntimeHelpers(
    SearchRuntime(
        signal_field_specs=SIGNAL_FIELD_SPECS,
        default_mysql_source=DEFAULT_MYSQL_SOURCE,
        as_int=as_int,
        default_source_help_text=default_source_help_text,
        normalize_request_criteria=normalize_request_criteria,
        normalize_self_profile_input=normalize_self_profile_input,
        build_criteria_from_args=build_criteria_from_args,
        load_source=lambda *args, **kwargs: load_source(*args, **kwargs),
        overlay_records_with_moderation=overlay_records_with_moderation,
        evaluate_candidate=evaluate_candidate,
        result_sort_key=result_sort_key,
        select_diverse_results=select_diverse_results,
        build_self_profile=build_self_profile,
        record_ref=record_ref,
        build_fallback_candidates=build_fallback_candidates,
        build_no_match_diagnostics=build_no_match_diagnostics,
        attach_photo_previews=lambda *args, **kwargs: attach_photo_previews(*args, **kwargs),
        effective_activity_info=effective_activity_info,
        effective_activity_datetime=effective_activity_datetime,
        format_datetime=format_datetime,
        build_trust_summary=build_trust_summary,
        summarize_notes=summarize_notes,
        build_verification_items=build_verification_items,
        activity_score_info=activity_score_info,
        redact_source_ref=redact_source_ref,
        format_no_match_text=format_no_match_text,
    )
)

summarize_signal_parts = _search_runtime_helpers.summarize_signal_parts
format_result_headline = _search_runtime_helpers.format_result_headline
format_result_scoring_line = _search_runtime_helpers.format_result_scoring_line
build_result_meta_parts = _search_runtime_helpers.build_result_meta_parts
append_labeled_line = _search_runtime_helpers.append_labeled_line
append_joined_line = _search_runtime_helpers.append_joined_line
append_result_detail_lines = _search_runtime_helpers.append_result_detail_lines
format_result_block = _search_runtime_helpers.format_result_block
format_text = _search_runtime_helpers.format_text
register_argument_specs = _search_runtime_helpers.register_argument_specs
build_source_argument_specs = _search_runtime_helpers.build_source_argument_specs
add_source_arguments = _search_runtime_helpers.add_source_arguments
add_profile_filter_arguments = _search_runtime_helpers.add_profile_filter_arguments
add_quality_arguments = _search_runtime_helpers.add_quality_arguments
add_self_profile_arguments = _search_runtime_helpers.add_self_profile_arguments
add_output_arguments = _search_runtime_helpers.add_output_arguments
build_parser = _search_runtime_helpers.build_parser
build_search_request = _search_runtime_helpers.build_search_request
build_cli_self_profile_input = _search_runtime_helpers.build_cli_self_profile_input
build_search_request_from_args = _search_runtime_helpers.build_search_request_from_args
resolve_request_sources = _search_runtime_helpers.resolve_request_sources
resolve_sources = _search_runtime_helpers.resolve_sources
collect_source_records_for_request = _search_runtime_helpers.collect_source_records_for_request
collect_source_records = _search_runtime_helpers.collect_source_records
evaluate_records = _search_runtime_helpers.evaluate_records
apply_request_self_profile_context = _search_runtime_helpers.apply_request_self_profile_context
apply_self_profile_context = _search_runtime_helpers.apply_self_profile_context
build_search_run = _search_runtime_helpers.build_search_run
populate_no_match_details = _search_runtime_helpers.populate_no_match_details
prepare_search_request_context = _search_runtime_helpers.prepare_search_request_context
prepare_search_context = _search_runtime_helpers.prepare_search_context
execute_search_request = _search_runtime_helpers.execute_search_request
execute_search = _search_runtime_helpers.execute_search
json_safe = _search_runtime_helpers.json_safe
build_structured_result_payload = _search_runtime_helpers.build_structured_result_payload
build_pool_summary = _search_runtime_helpers.build_pool_summary
build_structured_search_response = _search_runtime_helpers.build_structured_search_response
render_search_json = _search_runtime_helpers.render_search_json
render_search_output = _search_runtime_helpers.render_search_output


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        search_run = execute_search(args)
        if args.output_format == "json":
            print(
                render_search_json(
                    search_run,
                    include_source=args.show_source,
                )
            )
        else:
            print(render_search_output(search_run, include_source=args.show_source))
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
