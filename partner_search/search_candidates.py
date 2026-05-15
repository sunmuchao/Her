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
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

from her_time_utils import coerce_int as as_int, unique_ordered_texts
from mysql_source_config import MYSQL_SCHEMES as MYSQL_SOURCE_SCHEMES
from mysql_source_config import parse_mysql_source_config
from outer_system_mysql_schema import quote_mysql_ident as mysql_quote_ident
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


def parse_mysql_source(source, table_name=None):
    try:
        return parse_mysql_source_config(
            source,
            source_label="MySQL source",
            table_name=table_name,
            default_photos_table_name=DEFAULT_MYSQL_PHOTOS_TABLE,
            default_host="localhost",
        )
    except ValueError as exc:
        if str(exc) == "MySQL source must include a database name.":
            raise ValueError(
                "MySQL source must include a database name, for example mysql://user:pass@host:3306/db"
            ) from exc
        raise


def quote_mysql_ident(identifier):
    return mysql_quote_ident(identifier)


def resolve_mysql_columns(conn, database, table):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name AS column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (database, table),
        )
        mapping = {}
        for row in cursor.fetchall():
            actual = row["column_name"]
            canonical = ALIAS_LOOKUP.get(normalize_key(actual), normalize_key(actual))
            mapping.setdefault(canonical, actual)
        return mapping


def build_mysql_prefilter(criteria, canonical_to_actual, include_ids=None, include_ids_mode="or"):
    include_ids = [item for item in (include_ids or []) if item is not None]
    include_ids_mode = as_lower(include_ids_mode) or "or"
    if include_ids_mode not in {"or", "only"}:
        raise ValueError("include_ids_mode must be either 'or' or 'only'.")
    if include_ids and "id" not in canonical_to_actual:
        return None

    base_clauses = []
    base_params = []

    def text_expr(actual):
        return f"COALESCE({quote_mysql_ident(actual)}, '')"

    def defaulted_text_expr(actual):
        return f"COALESCE(NULLIF({text_expr(actual)}, ''), %s)"

    def add_exact(canonical, value, allow_missing=False):
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        expr = text_expr(actual)
        if allow_missing:
            base_clauses.append(f"({expr} = %s OR {expr} = '')")
        else:
            base_clauses.append(f"{expr} = %s")
        base_params.append(as_text(value))

    def add_in(canonical, values, allow_missing=False, default_value=None):
        actual = canonical_to_actual.get(canonical)
        normalized = [as_text(item) for item in values or [] if as_text(item)]
        if actual is None or not normalized:
            return
        placeholders = ", ".join(["%s"] * len(normalized))
        if default_value is not None:
            expr = defaulted_text_expr(actual)
            base_clauses.append(f"{expr} IN ({placeholders})")
            base_params.append(as_text(default_value))
        else:
            expr = text_expr(actual)
            if allow_missing:
                base_clauses.append(f"({expr} IN ({placeholders}) OR {expr} = '')")
            else:
                base_clauses.append(f"{expr} IN ({placeholders})")
        base_params.extend(normalized)

    def add_not_in(canonical, values):
        actual = canonical_to_actual.get(canonical)
        normalized = [as_text(item) for item in values or [] if as_text(item)]
        if actual is None or not normalized:
            return
        placeholders = ", ".join(["%s"] * len(normalized))
        base_clauses.append(f"{text_expr(actual)} NOT IN ({placeholders})")
        base_params.extend(normalized)

    def add_numeric_bound(canonical, operator, value, allow_missing=False):
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        clause = f"{quote_mysql_ident(actual)} {operator} %s"
        if allow_missing:
            clause = f"({quote_mysql_ident(actual)} IS NULL OR {clause})"
        base_clauses.append(clause)
        base_params.append(value)

    add_exact("gender", criteria.get("gender"), allow_missing=True)
    add_numeric_bound("age", ">=", criteria.get("age_min"), allow_missing=True)
    add_numeric_bound("age", "<=", criteria.get("age_max"), allow_missing=True)
    add_numeric_bound("height", ">=", criteria.get("height_min"), allow_missing=True)
    add_numeric_bound("height", "<=", criteria.get("height_max"), allow_missing=True)
    add_in("city", criteria.get("cities"), allow_missing=True)
    add_in("district", criteria.get("districts"), allow_missing=True)
    add_in("settlement_city", criteria.get("settlement_cities"), allow_missing=True)
    add_in("relationship_goal", criteria.get("relationship_goals"), allow_missing=True)
    add_exact("smoking", criteria.get("smoking"), allow_missing=True)
    add_exact("drinking", criteria.get("drinking"), allow_missing=True)
    add_exact("long_distance", criteria.get("long_distance"), allow_missing=True)
    add_in("housing_status", criteria.get("housing_statuses"), allow_missing=True)
    add_in("car_status", criteria.get("car_statuses"), allow_missing=True)
    add_in("marital_status", criteria.get("marital_statuses"), allow_missing=True)
    add_exact("want_children", criteria.get("want_children"), allow_missing=True)
    add_exact("accept_partner_children", criteria.get("accept_partner_children"), allow_missing=True)
    add_in("marriage_timeline", criteria.get("marriage_timelines"), allow_missing=True)
    add_in("profile_status", criteria.get("profile_statuses") or ["active"], allow_missing=True)
    add_not_in("source_channel", criteria.get("exclude_source_channels"))
    add_in("verified_level", criteria.get("verified_levels"), default_value="none")
    add_in("photo_verification_level", criteria.get("photo_verification_levels"), default_value="none")
    add_numeric_bound("photo_count", ">=", criteria.get("photo_count_min"), allow_missing=True)

    if criteria.get("has_children") is not None:
        add_numeric_bound("has_children", "=", int(criteria["has_children"]), allow_missing=True)

    if criteria.get("verified_level_min"):
        actual = canonical_to_actual.get("verified_level")
        if actual is not None:
            required_rank = verified_rank(criteria["verified_level_min"])
            allowed_levels = [
                level
                for level, rank in VERIFIED_LEVEL_ORDER.items()
                if rank >= required_rank
            ]
            placeholders = ", ".join(["%s"] * len(allowed_levels))
            base_clauses.append(
                f"{defaulted_text_expr(actual)} IN ({placeholders})"
            )
            base_params.append("none")
            base_params.extend(allowed_levels)

    if criteria.get("photo_verification_level_min"):
        actual = canonical_to_actual.get("photo_verification_level")
        if actual is not None:
            required_rank = photo_verification_rank(criteria["photo_verification_level_min"])
            allowed_levels = [
                level
                for level, rank in PHOTO_VERIFICATION_LEVEL_ORDER.items()
                if rank >= required_rank
            ]
            placeholders = ", ".join(["%s"] * len(allowed_levels))
            base_clauses.append(
                f"{defaulted_text_expr(actual)} IN ({placeholders})"
            )
            base_params.append("none")
            base_params.extend(allowed_levels)

    if criteria.get("active_within_days") is not None:
        activity_fields = [
            canonical_to_actual.get(field)
            for field in ("last_active_at", "updated_at", "created_at")
            if canonical_to_actual.get(field)
        ]
        if activity_fields:
            cutoff = datetime.now() - timedelta(days=criteria["active_within_days"])
            coalesced_activity = ", ".join(quote_mysql_ident(field) for field in activity_fields)
            base_clauses.append(f"COALESCE({coalesced_activity}) >= %s")
            base_params.append(cutoff.strftime("%Y-%m-%d %H:%M:%S"))

    base_where = " AND ".join(f"({clause})" for clause in base_clauses)

    include_where = ""
    include_params = []
    if include_ids:
        actual_id = canonical_to_actual["id"]
        placeholders = ", ".join(["%s"] * len(include_ids))
        include_where = f"{quote_mysql_ident(actual_id)} IN ({placeholders})"
        include_params.extend(include_ids)

    if include_where and include_ids_mode == "only":
        return f" WHERE {include_where}", include_params
    if base_where and include_where:
        return f" WHERE ({base_where}) OR ({include_where})", base_params + include_params
    if base_where:
        return f" WHERE {base_where}", base_params
    if include_where:
        return f" WHERE {include_where}", include_params
    return "", []


def load_mysql(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    config = parse_mysql_source(source, table_name=table_name)
    normalized_source, normalized_table = resolve_profile_source(source, config.get("table"))
    effective_source = normalized_source or str(source)
    table = normalized_table or detect_profile_table(source_dsn=effective_source)
    if not table:
        raise ValueError(f"Could not detect a candidate table in MySQL database {config['database']}")

    canonical_to_actual = {}
    for actual in list_profile_columns(source_dsn=effective_source, source_table_name=table):
        canonical = ALIAS_LOOKUP.get(normalize_key(actual), normalize_key(actual))
        canonical_to_actual.setdefault(canonical, actual)

    prefilter = build_mysql_prefilter(
        criteria or {},
        canonical_to_actual,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )
    if prefilter is None:
        where_clause, params = "", []
    else:
        where_clause, params = prefilter
    rows = list_profiles(
        source_dsn=effective_source,
        source_table_name=table,
        where_clause=where_clause.replace("%s", "?"),
        params=params,
    )
    return [
        normalize_record(dict(row, source_file=build_source_file_ref(effective_source, table)))
        for row in rows
    ]


def load_mysql_photo_previews(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
    if preview_count <= 0 or not profile_ids:
        return {}

    config = parse_mysql_source(source, table_name=table_name)
    return list_profile_photo_previews(
        source_dsn=source,
        source_table_name=config.get("table"),
        photos_table_name=photos_table_name or config.get("photos_table") or DEFAULT_MYSQL_PHOTOS_TABLE,
        profile_ids=[item for item in profile_ids if item is not None],
        preview_count=preview_count,
    )


def detect_mysql_profile_table(conn, database):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            (database,),
        )
        tables = [row["table_name"] for row in cursor.fetchall()]

        scored_tables = []
        for table in tables:
            cursor.execute(
                """
                SELECT column_name AS column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (database, table),
            )
            columns = {normalize_key(row["column_name"]) for row in cursor.fetchall()}
            canonical_columns = {ALIAS_LOOKUP.get(column, column) for column in columns}
            score = 0
            for required, weight in {
                "id": 2,
                "name": 2,
                "gender": 2,
                "age": 2,
                "city": 2,
                "profile_status": 1,
                "verified_level": 1,
            }.items():
                if required in canonical_columns:
                    score += weight
            scored_tables.append((table, score))

        if not scored_tables:
            return None

        best_score = max(score for _, score in scored_tables)
        if best_score <= 0:
            return None

        best_tables = [table for table, score in scored_tables if score == best_score]
        if len(best_tables) > 1:
            raise ValueError(
                "Ambiguous MySQL candidate tables: "
                + ", ".join(best_tables)
                + ". Specify ?table=... in the DSN or pass --table."
            )
        return best_tables[0]


def load_source(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    if not is_mysql_source(source):
        raise ValueError(
            "Unsupported source type. Use a MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles"
        )
    return load_mysql(
        source,
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
    return as_lower(value) == as_lower(expected)


def match_any_exact(value, candidates):
    lowered = as_lower(value)
    return lowered in {as_lower(item) for item in candidates}


def income_range_overlaps(min_value, max_value, required_min, required_max):
    if min_value is None and max_value is None:
        return None
    candidate_min = min_value if min_value is not None else max_value
    candidate_max = max_value if max_value is not None else min_value
    if required_min is not None and candidate_max is not None and candidate_max < required_min:
        return False
    if required_max is not None and candidate_min is not None and candidate_min > required_max:
        return False
    return True


def activity_score_info(record):
    active_at = effective_activity_datetime(record)
    if active_at is None:
        return (0, None, None)

    now = datetime.now()
    age = now - active_at
    if age <= timedelta(days=7):
        return (12, "7天内活跃", active_at)
    if age <= timedelta(days=30):
        return (8, "30天内活跃", active_at)
    if age <= timedelta(days=90):
        return (4, "90天内活跃", active_at)
    return (0, "90天前活跃", active_at)


def verified_score_info(record):
    level = record.get("verified_level") or "none"
    rank = verified_rank(level)
    return (rank * 2, verified_level_label(level), rank)


def verified_level_label(value):
    labels = {
        0: "未认证",
        1: "基础认证",
        2: "照片认证",
        3: "实名认证",
        4: "线下核验",
    }
    return labels.get(verified_rank(value), "未认证")


def photo_verification_level(profile):
    profile = profile or {}
    explicit = as_lower(profile.get("photo_verification_level") or profile.get("photo_verified_level"))
    if explicit in {"none", "uploaded", "human_verified", "live_video_verified", "offline_verified"}:
        return explicit
    if normalize_bool(profile.get("live_video_verified")) is True:
        return "live_video_verified"
    verified_rank_value = verified_rank(profile.get("verified_level"))
    photo_count = as_int(profile.get("photo_count"))
    has_photo = bool(profile.get("avatar_url")) or (photo_count is not None and photo_count > 0)
    if verified_rank_value >= 4:
        return "offline_verified"
    if verified_rank_value >= 2:
        return "human_verified"
    if has_photo:
        return "uploaded"
    return "none"


def photo_verification_level_label(value):
    labels = {
        "none": "未上传照片",
        "uploaded": "普通上传照片",
        "human_verified": "真人照片认证",
        "live_video_verified": "活体自拍视频认证",
        "offline_verified": "线下核验照片",
    }
    return labels.get(as_lower(value), "普通上传照片")


def normalize_field_verification_status(value, fallback="self_reported"):
    lowered = as_lower(value)
    if lowered in {"verified", "approved", "passed", "platform_verified", "human_verified", "live_video_verified", "offline_verified"}:
        return "verified"
    if lowered in {"needs_review", "inconsistent", "mismatch", "suspicious", "rejected", "expired", "disputed"}:
        return "needs_review"
    if lowered in {"pending", "submitted", "under_review", "resubmission_required"}:
        return "pending"
    if lowered in {"missing", "not_provided", "none"}:
        return "missing"
    if lowered in {"self_reported", "declared", "user_filled"}:
        return "self_reported"
    return fallback


def profile_field_verification_raw_status(profile, field_key):
    return as_lower(
        profile.get(f"{field_key}_verification_status")
        or profile.get(f"{field_key}_verified_status")
        or profile.get(f"{field_key}_auth_status")
    )


def profile_field_verification_status(profile, field_key, fallback="self_reported"):
    return normalize_field_verification_status(
        profile_field_verification_raw_status(profile, field_key),
        fallback=fallback,
    )


def format_income_range_text(record):
    income_range = as_text(record.get("income_range"))
    if income_range:
        return income_range

    income_min = as_int(record.get("income_min_wan"))
    income_max = as_int(record.get("income_max_wan"))
    if income_min is None and income_max is None:
        return None
    if income_min is None:
        return f"{income_max}万/年"
    if income_max is None:
        return f"{income_min}万/年"
    if income_min == income_max:
        return f"{income_min}万/年"
    return f"{income_min}-{income_max}万/年"


def build_profile_consistency_flags(profile):
    profile = profile or {}
    flags = []
    review_status = as_lower(profile.get("profile_review_status"))
    if review_status in {"needs_review", "inconsistent", "limited_exposure"}:
        flags.append("资料存在待复核或不一致信号")

    income_max = as_int(profile.get("income_max_wan"))
    if income_max is None:
        _, income_max = parse_income_range_to_wan(profile.get("income_range"))
    job_text = as_text(profile.get("job"))
    if income_max is not None and income_max >= 80 and job_text:
        if any(keyword in job_text for keyword in ("助理", "文员", "行政", "客服", "店员", "实习")):
            flags.append("收入声明与职业类型存在明显落差")

    for field_key, label in (
        ("job_change_count_30d", "职业"),
        ("city_change_count_30d", "城市"),
        ("income_change_count_30d", "收入"),
    ):
        change_count = as_int(profile.get(field_key))
        if change_count is not None and change_count >= 2:
            flags.append(f"{label}近30天修改较频繁")
    return unique_ordered(flags)


def build_verification_items(profile):
    profile = profile or {}
    items = []
    verified_level = profile.get("verified_level") or "none"
    verified_rank_value = verified_rank(verified_level)
    photo_count = as_int(profile.get("photo_count"))
    has_photo = bool(profile.get("avatar_url")) or (photo_count is not None and photo_count > 0)
    photo_level = photo_verification_level(profile)

    photo_suffix = f"（{photo_count}张）" if photo_count is not None and photo_count > 0 else ""
    if photo_level == "offline_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已线下核验照片{photo_suffix}",
            }
        )
    elif photo_level == "live_video_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已活体自拍视频认证{photo_suffix}",
            }
        )
    elif photo_level == "human_verified":
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "verified",
                "source": "platform_verification",
                "summary": f"已真人照片认证{photo_suffix}",
            }
        )
    elif has_photo or photo_level == "uploaded":
        uploaded_summary = f"已上传{photo_count}张照片" if photo_count is not None and photo_count > 0 else "已上传照片"
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "self_reported",
                "source": "profile_self_reported",
                "summary": uploaded_summary + "（未真人认证）",
            }
        )
    else:
        items.append(
            {
                "key": "photo",
                "label": "照片",
                "status": "missing",
                "source": "not_provided",
                "summary": "未上传照片",
            }
        )

    if verified_rank_value >= 4:
        identity_summary = "已线下核验"
        identity_status = "verified"
    elif verified_rank_value >= 3:
        identity_summary = "已实名认证"
        identity_status = "verified"
    elif verified_rank_value >= 1:
        identity_summary = "已基础认证"
        identity_status = "verified"
    else:
        identity_summary = "未实名"
        identity_status = "missing"
    items.append(
        {
            "key": "identity",
            "label": "身份",
            "status": identity_status,
            "source": "platform_verification" if verified_rank_value >= 1 else "not_provided",
            "summary": identity_summary,
        }
    )

    if verified_rank_value >= 4:
        items.append(
            {
                "key": "offline_check",
                "label": "线下核验",
                "status": "verified",
                "source": "platform_verification",
                "summary": "已完成线下核验",
            }
        )
    elif photo_level == "live_video_verified":
        items.append(
            {
                "key": "offline_check",
                "label": "真人视频核验",
                "status": "verified",
                "source": "platform_verification",
                "summary": "已完成活体自拍视频核验",
            }
        )

    age = as_int(profile.get("age"))
    age_status = "verified" if verified_rank_value >= 3 else profile_field_verification_status(profile, "age", fallback="self_reported")
    if age is not None:
        items.append(
            {
                "key": "age",
                "label": "年龄",
                "status": age_status,
                "source": "platform_verification" if age_status == "verified" else "profile_self_reported",
                "summary": f"{age}岁（{'实名层级' if age_status == 'verified' else '资料填写'}）",
            }
        )
    else:
        items.append(
            {
                "key": "age",
                "label": "年龄",
                "status": "missing",
                "source": "not_provided",
                "summary": "年龄未填写",
            }
        )

    def append_profile_item(key, label, value, *, missing_summary, verified_template, self_reported_template):
        if value is None or value == "":
            items.append(
                {
                    "key": key,
                    "label": label,
                    "status": "missing",
                    "source": "not_provided",
                    "summary": missing_summary,
                }
            )
            return

        status = profile_field_verification_status(profile, key, fallback="self_reported")
        raw_status = profile_field_verification_raw_status(profile, key)
        source = "profile_self_reported"
        if status == "verified":
            source = "platform_verification"
            summary = verified_template.format(value=value)
        elif raw_status == "resubmission_required":
            source = "review_pending"
            summary = f"{value}（材料需补充后重新提交）"
        elif raw_status == "expired":
            source = "review_pending"
            summary = f"{value}（认证已过期，需重新提交）"
        elif raw_status == "disputed":
            source = "risk_review"
            summary = f"{value}（认证结果存在争议，复核中）"
        elif raw_status == "rejected":
            source = "risk_review"
            summary = f"{value}（材料未通过，建议重新提交）"
        elif status == "pending":
            source = "review_pending"
            summary = f"{value}（认证审核中）"
        elif status == "needs_review":
            source = "risk_review"
            summary = f"{value}（存在不一致信号，建议复核）"
        else:
            summary = self_reported_template.format(value=value)
        items.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "raw_status": raw_status or status,
                "source": source,
                "summary": summary,
            }
        )

    append_profile_item(
        "city",
        "城市",
        as_text(profile.get("city")),
        missing_summary="城市未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )
    append_profile_item(
        "education",
        "学历",
        as_text(profile.get("education")),
        missing_summary="学历未填写",
        verified_template="{value}（已认证）",
        self_reported_template="{value}（未单独认证）",
    )
    append_profile_item(
        "job",
        "职业",
        as_text(profile.get("job")),
        missing_summary="职业未填写",
        verified_template="{value}（已认证）",
        self_reported_template="{value}（未单独认证）",
    )
    append_profile_item(
        "income",
        "收入",
        format_income_range_text(profile),
        missing_summary="收入未填写",
        verified_template="{value}（已认证区间）",
        self_reported_template="{value}（未单独认证）",
    )
    append_profile_item(
        "marital_status",
        "婚况",
        as_text(profile.get("marital_status")),
        missing_summary="婚况未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )

    has_children = effective_has_children(profile)
    if has_children is None:
        items.append(
            {
                "key": "children",
                "label": "子女情况",
                "status": "missing",
                "source": "not_provided",
                "summary": "子女情况未填写",
            }
        )
    else:
        child_label = "有孩子" if has_children else "无孩子"
        child_count = as_int(profile.get("children_count"))
        if has_children and child_count:
            child_label = f"有{child_count}个孩子"
        children_status = profile_field_verification_status(profile, "children", fallback="self_reported")
        items.append(
            {
                "key": "children",
                "label": "子女情况",
                "status": children_status,
                "source": "platform_verification" if children_status == "verified" else "profile_self_reported",
                "summary": f"{child_label}（{'已核验' if children_status == 'verified' else '资料填写'}）",
            }
        )

    append_profile_item(
        "relationship_goal",
        "结婚意向",
        as_text(profile.get("relationship_goal")),
        missing_summary="结婚意向未填写",
        verified_template="{value}（已核验）",
        self_reported_template="{value}（资料填写）",
    )
    return items


def build_trust_caution_items(profile, verification_items=None):
    profile = profile or {}
    verification_items = verification_items or build_verification_items(profile)
    caution_items = []
    photo_item = next((item for item in verification_items if item.get("key") == "photo"), None)
    if photo_item and photo_item.get("status") == "self_reported":
        caution_items.append("照片仅为普通上传，建议先视频核验再深入沟通")
    if any(item.get("status") == "needs_review" for item in verification_items if item.get("key") in {"education", "job", "income", "marital_status", "children"}):
        caution_items.append("部分高决策字段存在不一致信号，建议补充核验")
    if any(item.get("raw_status") == "expired" for item in verification_items if item.get("key") in {"education", "job", "income"}):
        caution_items.append("部分高决策字段认证已过期，建议重新提交最新材料")
    if any(item.get("raw_status") == "disputed" for item in verification_items if item.get("key") in {"education", "job", "income"}):
        caution_items.append("部分高决策字段正在争议复核中，建议暂不把其视为已核验信息")
    if profile_field_verification_status(profile, "income", fallback="self_reported") == "self_reported" and format_income_range_text(profile):
        caution_items.append("收入仍为自填信息，建议仅将其视为参考")
    caution_items.extend(profile.get("moderation_caution_items") or [])
    caution_items.extend(build_profile_consistency_flags(profile))
    return unique_ordered(caution_items)


def build_trust_actions(profile, verification_items=None, caution_items=None):
    verification_items = verification_items or build_verification_items(profile)
    caution_items = caution_items or build_trust_caution_items(profile, verification_items=verification_items)
    actions = []
    photo_item = next((item for item in verification_items if item.get("key") == "photo"), None)
    if photo_item and photo_item.get("status") != "verified":
        actions.append("建议先视频核验真人状态")
    if any(item.get("key") in {"income", "job", "education"} and item.get("status") in {"self_reported", "needs_review"} for item in verification_items):
        actions.append("建议先确认职业、学历和收入区间是否真实")
    if any(item.get("raw_status") in {"expired", "resubmission_required", "rejected", "disputed"} for item in verification_items if item.get("key") in {"education", "job", "income"}):
        actions.append("若继续沟通前要做高决策判断，建议等待对方补件或复核完成")
    if caution_items:
        actions.append("在转到站外或涉及金钱前，先完成平台内核验")
    return unique_ordered(actions)


def build_trust_summary(profile, verification_items=None):
    profile = profile or {}
    verification_items = verification_items or build_verification_items(profile)
    verified_labels = [item["label"] for item in verification_items if item["status"] == "verified"]
    self_reported_labels = [
        item["label"]
        for item in verification_items
        if item["status"] in {"self_reported", "pending"}
        and item["key"] in {"education", "job", "income", "marital_status", "children", "relationship_goal"}
    ]
    missing_labels = [
        item["label"]
        for item in verification_items
        if item["status"] == "missing"
        and item["key"] in {"marital_status", "children", "income", "education", "job", "relationship_goal"}
    ]
    caution_labels = [
        item["label"]
        for item in verification_items
        if item["status"] == "needs_review"
        and item["key"] in {"education", "job", "income", "marital_status", "children", "relationship_goal"}
    ]

    badges = []
    verified_rank_value = verified_rank(profile.get("verified_level"))
    photo_level = photo_verification_level(profile)
    if photo_level == "offline_verified":
        badges.append("照片已线下核验")
    elif photo_level == "live_video_verified":
        badges.append("照片已活体视频核验")
    elif photo_level == "human_verified":
        badges.append("照片已真人认证")
    if verified_rank_value >= 3:
        badges.append("已实名认证")
    elif verified_rank_value >= 1:
        badges.append("已基础认证")
    if verified_rank_value >= 4 and photo_level != "offline_verified":
        badges.append("已线下核验")
    activity_label = activity_score_info(profile)[1]
    if activity_label:
        badges.append(activity_label)

    headline_parts = []
    if badges:
        headline_parts.append("；".join(unique_ordered(badges[:3])))
    else:
        headline_parts.append("认证信息有限")

    if caution_labels:
        headline_parts.append("以下字段存在待复核信号：" + "、".join(unique_ordered(caution_labels)[:3]))
    if self_reported_labels:
        headline_parts.append("其余关键信息以资料填写为主：" + "、".join(unique_ordered(self_reported_labels)[:4]))
    elif not caution_labels and missing_labels:
        headline_parts.append("仍有资料待补充：" + "、".join(unique_ordered(missing_labels)[:3]))

    caution_items = build_trust_caution_items(profile, verification_items=verification_items)
    return {
        "headline": "；".join(headline_parts),
        "verified_level": profile.get("verified_level") or "none",
        "verified_label": verified_level_label(profile.get("verified_level")),
        "photo_verification_level": photo_level,
        "photo_verification_label": photo_verification_level_label(photo_level),
        "badges": unique_ordered(badges),
        "verified_items": unique_ordered(verified_labels),
        "self_reported_items": unique_ordered(self_reported_labels),
        "missing_items": unique_ordered(missing_labels),
        "caution_items": caution_items,
        "trust_actions": build_trust_actions(profile, verification_items=verification_items, caution_items=caution_items),
    }


def build_rejection_reason(code, detail=None):
    if detail is None or detail == "":
        return str(code)
    return f"{code}:{detail}"


def parse_rejection_reason(reason):
    code, _, detail = str(reason or "").partition(":")
    return code, detail


def format_rejection_reason(reason):
    code, detail = parse_rejection_reason(reason)
    labels = {
        "profile_status_mismatch": "资料状态不在要求范围",
        "active_time_missing": "缺少最近活跃时间",
        "active_too_old": "最近活跃时间太久",
        "verified_below_min": "认证等级低于最低要求",
        "verified_level_mismatch": "认证等级不在允许范围",
        "photo_verification_below_min": "照片核验等级低于最低要求",
        "photo_verification_level_mismatch": "照片核验等级不在允许范围",
        "age_below_min": "年龄低于下限",
        "age_above_max": "年龄高于上限",
        "height_below_min": "身高低于下限",
        "height_above_max": "身高高于上限",
        "gender_mismatch": "性别不匹配",
        "city_mismatch": "城市不在要求范围",
        "district_mismatch": "区域不在要求范围",
        "settlement_city_mismatch": "定居城市不在要求范围",
        "relationship_goal_mismatch": "关系目标不一致",
        "smoking_mismatch": "抽烟条件不匹配",
        "drinking_mismatch": "喝酒条件不匹配",
        "long_distance_mismatch": "异地态度不匹配",
        "housing_status_mismatch": "住房条件不匹配",
        "car_status_mismatch": "车辆条件不匹配",
        "marital_status_mismatch": "婚况不匹配",
        "has_children_mismatch": "子女情况不匹配",
        "want_children_mismatch": "生育计划不匹配",
        "accept_partner_children_mismatch": "对子女接受度不匹配",
        "accept_marital_status_strength_mismatch": "婚史接受真实度不匹配",
        "accept_partner_children_strength_mismatch": "对子女接受真实度不匹配",
        "marriage_timeline_mismatch": "结婚节奏不匹配",
        "photo_count_too_low": "照片数量低于要求",
        "education_below_self_preference": "低于你的学历底线",
        "reciprocal_age_preference": "不符合对方年龄偏好",
        "reciprocal_city_preference": "不符合对方城市偏好",
        "reciprocal_height_preference": "不符合对方身高偏好",
        "reciprocal_education_preference": "不符合对方学历偏好",
        "reciprocal_income_preference": "不符合对方收入偏好",
        "reciprocal_marital_status_preference": "不符合对方婚况接受范围",
        "reciprocal_children_acceptance": "对方不能接受你的子女情况",
        "reciprocal_marital_status_acceptance_not_strong": "对方对你的婚史不是明确接受",
        "reciprocal_children_acceptance_not_strong": "对方对你的孩子不是明确接受",
        "reciprocal_marital_status_acceptance_unknown": "对方没明确写是否真接受你的婚史",
        "reciprocal_children_acceptance_unknown": "对方没明确写是否真接受你的孩子",
        "reciprocal_smoking_acceptance": "对方不能接受你的抽烟情况",
        "reciprocal_drinking_acceptance": "对方不能接受你的喝酒情况",
        "reciprocal_long_distance_acceptance": "对方不能接受异地",
        "candidate_pool_empty_after_exclusions": "筛选后没有其他可用候选",
        "exclude_source_channel": "来自排除的来源渠道",
    }
    if code == "must_have_missing":
        return f"缺少必需关键词「{detail}」"
    if code == "must_not_have_hit":
        return f"命中排除关键词「{detail}」"
    if code == "required_known_missing":
        return f"资料里没明确写{field_display_name(detail)}"
    return labels.get(code, code or "未知淘汰原因")


def suggestion_for_rejection(reason):
    code, detail = parse_rejection_reason(reason)
    if code in {"city_mismatch", "district_mismatch", "settlement_city_mismatch"}:
        return "放宽地域条件，先别把同区/同定居地卡得太死。"
    if code == "must_have_missing":
        return f"把“{detail}”从硬条件改成加分项，先保留可聊对象。"
    if code == "must_not_have_hit":
        return f"确认“{detail}”是不是真硬雷点，不然先改成追问题。"
    if code in {"verified_below_min", "verified_level_mismatch"}:
        return "先放宽认证要求，再靠追问确认真实性。"
    if code == "photo_count_too_low":
        return "先放宽照片门槛，用资料内容和风险提示做二筛。"
    if code == "education_below_self_preference":
        return "先确认学历底线是不是硬条件，不然别把明显低于预期的人往前放。"
    if code in {"active_too_old", "active_time_missing"}:
        return "放宽活跃时间要求，先确认对方现在还找不找。"
    if code == "relationship_goal_mismatch":
        return "关系目标别卡太死，结婚导向和认真恋爱可以先一起放进池子。"
    if code in {"smoking_mismatch", "drinking_mismatch", "long_distance_mismatch"}:
        return "把生活习惯类条件分成硬雷点和可追问项，别一刀切。"
    if code in {
        "marital_status_mismatch",
        "accept_marital_status_strength_mismatch",
        "reciprocal_marital_status_preference",
        "reciprocal_marital_status_acceptance_not_strong",
        "reciprocal_marital_status_acceptance_unknown",
    }:
        return "婚况会明显压缩池子，先看对方是否明确接受再婚/复杂婚史。"
    if code in {
        "has_children_mismatch",
        "want_children_mismatch",
        "accept_partner_children_mismatch",
        "accept_partner_children_strength_mismatch",
        "reciprocal_children_acceptance",
        "reciprocal_children_acceptance_not_strong",
        "reciprocal_children_acceptance_unknown",
    }:
        return "孩子相关条件会明显压缩池子，先确认对方是明确接受、谨慎接受还是完全不接受。"
    if code in {
        "candidate_pool_empty_after_exclusions",
    }:
        return "这轮不是排序问题，是当前城市/年龄段没有其他可用候选，先补数据池。"
    if code == "required_known_missing":
        return f"先别强制要求写明{field_display_name(detail)}，保留结果后再追问。"
    if code.startswith("reciprocal_"):
        return "这次是卡在对方反向要求上，优先检查城市、年龄、婚况、孩子、异地。"
    return None


def build_no_match_diagnostics(records, criteria):
    if not records:
        return {
            "scanned_count": 0,
            "passed_count": 0,
            "usable_count": 0,
            "top_reasons": [],
            "relax_suggestions": [
                "数据源预筛后已经没候选了，先检查城市、年龄、资料状态、最近活跃、认证等级这些硬条件。"
            ],
        }

    rejection_counts = Counter()
    passed_count = 0
    excluded_count = 0
    for record in records:
        diagnostic = evaluate_candidate(record, criteria, diagnostics=True)
        if diagnostic and diagnostic.get("matched"):
            passed_count += 1
            continue
        reason = "unknown"
        if diagnostic:
            reason = diagnostic.get("reject_reason") or "unknown"
        if reason == "exclude_record_ref":
            excluded_count += 1
            continue
        rejection_counts[reason] += 1

    usable_count = max(len(records) - excluded_count, 0)

    if rejection_counts:
        top_reasons = [
            {
                "reason": reason,
                "label": format_rejection_reason(reason),
                "count": count,
            }
            for reason, count in rejection_counts.most_common(4)
        ]
    elif excluded_count:
        top_reasons = [
            {
                "reason": "candidate_pool_empty_after_exclusions",
                "label": "筛选后没有其他可用候选",
                "count": excluded_count,
            }
        ]
    else:
        top_reasons = []
    relax_suggestions = unique_ordered(
        suggestion_for_rejection(item["reason"])
        for item in top_reasons
    )

    return build_no_match_diagnostics_payload(
        scanned_count=len(records),
        passed_count=passed_count,
        usable_count=usable_count,
        top_reasons=top_reasons,
        relax_suggestions=relax_suggestions[:3],
    )


def build_no_match_diagnostics_payload(
    scanned_count,
    passed_count,
    usable_count,
    top_reasons,
    relax_suggestions,
):
    return {
        "scanned_count": scanned_count,
        "passed_count": passed_count,
        "usable_count": usable_count,
        "top_reasons": top_reasons,
        "relax_suggestions": relax_suggestions,
    }


def build_fallback_candidates(records, criteria, limit=3):
    candidates = []
    for record in records:
        strict_diagnostic = evaluate_candidate(record, criteria, diagnostics=True)
        if strict_diagnostic and strict_diagnostic.get("matched"):
            continue

        fallback_result = evaluate_candidate(
            record,
            criteria,
            reciprocal_mode="fallback",
        )
        if not fallback_result:
            continue

        if strict_diagnostic and strict_diagnostic.get("reject_reason"):
            fallback_result["fallback_reason"] = format_rejection_reason(
                strict_diagnostic["reject_reason"]
            )
        candidates.append(fallback_result)

    candidates.sort(key=result_sort_key, reverse=True)
    return select_diverse_results(candidates, limit)


def format_no_match_text(diagnostics, fallback_results=None):
    lines = ["No matches found."]
    if not diagnostics:
        return "\n".join(lines)

    pool_parts = [
        f"scanned={diagnostics.get('scanned_count', 0)}",
        f"passed={diagnostics.get('passed_count', 0)}",
    ]
    if diagnostics.get("usable_count") is not None and diagnostics.get("usable_count") != diagnostics.get("scanned_count"):
        pool_parts.append(f"usable_after_exclusions={diagnostics.get('usable_count', 0)}")
    lines.append("pool_summary: " + " | ".join(pool_parts))
    top_reasons = diagnostics.get("top_reasons") or []
    if top_reasons:
        lines.append(
            "why_no_match: "
            + " | ".join(f"{item['label']} x{item['count']}" for item in top_reasons)
        )
    suggestions = diagnostics.get("relax_suggestions") or []
    if suggestions:
        lines.append("relax_suggestions: " + " | ".join(suggestions))
    if fallback_results:
        lines.append("fallback_matches: strict 条件下没人过，但下面这些属于放宽后可聊对象。")
        lines.append(format_text(fallback_results))
    return "\n".join(lines)


def matcher_preference_tags(record):
    preferences = record.get("matcher_preferences")
    if not isinstance(preferences, dict):
        preferences = parse_json_object(record.get("matcher_preferences_json"))
    tags = []
    for key in ("must_have_tags", "preferred_traits"):
        value = preferences.get(key)
        if isinstance(value, list):
            tags.extend(value)
        else:
            tags.extend(split_keywords(value))
    return unique_ordered(tags)


def evaluate_reciprocal_compatibility(record, self_profile, diagnostics=False, reciprocal_mode="strict"):
    def fail(reason, detail=None):
        if not diagnostics:
            return None
        return {
            "matched": False,
            "matched_on": [],
            "missing_fields": [],
            "risk_flags": [],
            "score_bonus": 0,
            "reject_reason": build_rejection_reason(reason, detail),
        }

    if not self_profile:
        return {
            "matched": True,
            "matched_on": [],
            "missing_fields": [],
            "risk_flags": [],
            "score_bonus": 0,
            "reject_reason": None,
        }

    reasons = []
    missing_fields = []
    risk_flags = []
    score_bonus = 0

    self_age = as_int(self_profile.get("age"))
    pref_age_min = as_int(record.get("preferred_age_min"))
    pref_age_max = as_int(record.get("preferred_age_max"))
    age_strictness = normalize_strictness_state(record.get("preferred_age_strictness"))
    if pref_age_min is not None or pref_age_max is not None:
        if self_age is None:
            missing_fields.append("self_age")
        elif pref_age_min is not None and self_age < pref_age_min:
            if age_strictness == "hard":
                return fail("reciprocal_age_preference")
            risk_flag = soft_preference_risk_flag("age", age_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        elif pref_age_max is not None and self_age > pref_age_max:
            if age_strictness == "hard":
                return fail("reciprocal_age_preference")
            risk_flag = soft_preference_risk_flag("age", age_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方年龄偏好命中")
            score_bonus += 10

    pref_cities = split_keywords(record.get("preferred_cities"))
    self_city = self_profile.get("city")
    if pref_cities:
        if not self_city:
            missing_fields.append("self_city")
        elif not match_any_exact(self_city, pref_cities):
            city_preference_risk = reciprocal_city_preference_risk_flag(
                normalize_acceptance_state(record.get("accept_long_distance")),
                reciprocal_mode,
            )
            if city_preference_risk:
                risk_flags.append(city_preference_risk)
                risk_flags.extend(location_semantics_risk_flags(record))
            else:
                return fail("reciprocal_city_preference")
        else:
            reasons.append("对方城市偏好命中")
            score_bonus += 10

    self_height = as_int(self_profile.get("height"))
    pref_height_min = as_int(record.get("preferred_height_min"))
    pref_height_max = as_int(record.get("preferred_height_max"))
    height_strictness = normalize_strictness_state(record.get("preferred_height_strictness"))
    if pref_height_min is not None or pref_height_max is not None:
        if self_height is None:
            missing_fields.append("self_height")
        elif pref_height_min is not None and self_height < pref_height_min:
            if height_strictness == "hard":
                return fail("reciprocal_height_preference")
            risk_flag = soft_preference_risk_flag("height", height_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        elif pref_height_max is not None and self_height > pref_height_max:
            if height_strictness == "hard":
                return fail("reciprocal_height_preference")
            risk_flag = soft_preference_risk_flag("height", height_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方身高偏好命中")
            score_bonus += 6

    pref_education_min = record.get("preferred_education_min")
    education_strictness = normalize_strictness_state(record.get("preferred_education_strictness"))
    if pref_education_min:
        self_education = self_profile.get("education")
        self_rank = education_rank(self_education)
        required_rank = education_rank(pref_education_min)
        if not self_education:
            missing_fields.append("self_education")
        elif self_rank is None or required_rank is None:
            if not exact_match(self_education, pref_education_min):
                if education_strictness == "hard":
                    return fail("reciprocal_education_preference")
                risk_flag = soft_preference_risk_flag("education", education_strictness)
                if risk_flag:
                    risk_flags.append(risk_flag)
        elif self_rank < required_rank:
            if education_strictness == "hard":
                return fail("reciprocal_education_preference")
            risk_flag = soft_preference_risk_flag("education", education_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方学历偏好命中")
            score_bonus += 6

    pref_income_min = as_int(record.get("preferred_income_min_wan"))
    pref_income_max = as_int(record.get("preferred_income_max_wan"))
    income_strictness = normalize_strictness_state(record.get("preferred_income_strictness"))
    if pref_income_min is not None or pref_income_max is not None:
        self_income_min = as_int(self_profile.get("income_min_wan"))
        self_income_max = as_int(self_profile.get("income_max_wan"))
        overlap = income_range_overlaps(self_income_min, self_income_max, pref_income_min, pref_income_max)
        if overlap is None:
            missing_fields.append("self_income_wan")
        elif overlap is False:
            if income_strictness == "hard":
                return fail("reciprocal_income_preference")
            risk_flag = soft_preference_risk_flag("income", income_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方收入偏好命中")
            score_bonus += 6

    accepted_statuses = split_keywords(record.get("accept_marital_status"))
    accept_marital_status_semantics = as_text(record.get("accept_marital_status_semantics"))
    if accepted_statuses:
        self_status = self_profile.get("marital_status")
        if not self_status:
            missing_fields.append("self_marital_status")
        elif not any(match_any_exact(option, accepted_statuses) for option in marital_status_match_options(self_profile)):
            return fail("reciprocal_marital_status_preference")
        else:
            reasons.append("对方可接受婚况命中")
            score_bonus += 8
            if as_lower(self_status) not in {"", "未婚"}:
                marital_strength = normalize_acceptance_strength(
                    record.get("accept_marital_status_strength")
                )
                if marital_strength == "strong":
                    score_bonus += 2
                else:
                    marital_risk = marital_acceptance_risk_flag(
                        marital_strength,
                        accept_marital_status_semantics,
                    )
                    if marital_risk:
                        risk_flags.append(marital_risk)
    else:
        self_status = self_profile.get("marital_status")
        if self_status and as_lower(self_status) not in {"", "未婚"}:
            missing_fields.append("accept_marital_status")

    self_has_children = normalize_bool(self_profile.get("has_children"))
    accept_partner_children = normalize_acceptance_state(record.get("accept_partner_children"))
    accept_partner_children_semantics = as_text(record.get("accept_partner_children_semantics"))
    if self_has_children is None:
        if accept_partner_children != "missing":
            missing_fields.append("self_has_children")
    elif self_has_children:
        if accept_partner_children == "rejected":
            return fail("reciprocal_children_acceptance")
        if accept_partner_children == "accepted":
            reasons.append("对方接受你有孩子")
            score_bonus += 8
            children_strength = normalize_acceptance_strength(
                record.get("accept_partner_children_strength")
            )
            if children_strength == "strong":
                score_bonus += 2
            else:
                children_risk = children_acceptance_risk_flag(
                    "accepted",
                    children_strength,
                    accept_partner_children_semantics,
                )
                if children_risk:
                    risk_flags.append(children_risk)
        elif accept_partner_children in {"negotiable", "guarded"}:
            risk_flags.append(
                children_acceptance_risk_flag(
                    accept_partner_children,
                    normalize_acceptance_strength(
                        record.get("accept_partner_children_strength")
                    ),
                    accept_partner_children_semantics,
                )
            )
        elif accept_partner_children == "unknown":
            if reciprocal_mode == "fallback":
                risk_flags.append("对方对子女接受度未知")
            else:
                return fail("reciprocal_children_acceptance_unknown")
        else:
            missing_fields.append("accept_partner_children")

    self_smoking = self_profile.get("smoking")
    accept_smoking = normalize_acceptance_state(record.get("accept_smoking"))
    if not self_smoking:
        if accept_smoking != "missing":
            missing_fields.append("self_smoking")
    elif habit_requires_acceptance(self_smoking):
        if accept_smoking == "rejected":
            return fail("reciprocal_smoking_acceptance")
        if accept_smoking == "accepted":
            reasons.append("对方接受你的抽烟习惯")
            score_bonus += 4
        elif accept_smoking == "negotiable":
            risk_flags.append("对方对抽烟仅可协商")
        elif accept_smoking == "unknown":
            risk_flags.append("对方对抽烟接受度未知")
        else:
            missing_fields.append("accept_smoking")

    self_drinking = self_profile.get("drinking")
    accept_drinking = normalize_acceptance_state(record.get("accept_drinking"))
    if not self_drinking:
        if accept_drinking != "missing":
            missing_fields.append("self_drinking")
    elif habit_requires_acceptance(self_drinking):
        if accept_drinking == "rejected":
            return fail("reciprocal_drinking_acceptance")
        if accept_drinking == "accepted":
            reasons.append("对方接受你的喝酒习惯")
            score_bonus += 4
        elif accept_drinking == "negotiable":
            risk_flags.append("对方对喝酒仅可协商")
        elif accept_drinking == "unknown":
            risk_flags.append("对方对喝酒接受度未知")
        else:
            missing_fields.append("accept_drinking")

    candidate_city = record.get("city")
    accept_long_distance = normalize_acceptance_state(record.get("accept_long_distance"))
    if self_city and candidate_city and as_lower(self_city) != as_lower(candidate_city):
        if accept_long_distance == "rejected":
            return fail("reciprocal_long_distance_acceptance")
        if accept_long_distance == "accepted":
            reasons.append("对方接受异地")
            score_bonus += 4
            risk_flags.extend(location_semantics_risk_flags(record))
        elif accept_long_distance == "negotiable":
            risk_flags.append("对方异地仅可协商")
            risk_flags.extend(location_semantics_risk_flags(record))
        elif accept_long_distance == "unknown":
            risk_flags.append("对方异地接受度未知")
            risk_flags.extend(location_semantics_risk_flags(record))
        else:
            missing_fields.append("accept_long_distance")

    soft_preference_tags = matcher_preference_tags(record)
    if soft_preference_tags:
        self_text = as_lower(self_profile.get("combined_text"))
        matched_soft_tags = [tag for tag in soft_preference_tags if as_lower(tag) in self_text]
        if matched_soft_tags:
            reasons.append("对方软性偏好有重合")
            score_bonus += min(4, len(matched_soft_tags) * 2)

    return {
        "matched": True,
        "matched_on": reasons,
        "missing_fields": missing_fields,
        "risk_flags": risk_flags,
        "score_bonus": score_bonus,
        "reject_reason": None,
    }


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
    return {
        "matched": matched,
        "id": record.get("id"),
        "name": record.get("name") or "未命名",
        "score": score,
        "fit_score": fit_score,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "matched_on": matched_on,
        "reciprocal_on": reciprocal_on,
        "missing_fields": missing_fields,
        "self_profile_gaps": self_profile_gaps,
        "risk_flags": risk_flags,
        "match_evidence": match_evidence,
        "follow_up_questions": follow_up_questions,
        "profile": strip_internal_fields(record),
        "source_file": record.get("source_file"),
        "verified_rank": verified_rank,
        "activity_sort_ts": activity_sort_ts,
        "profile_status_rank": profile_status_rank,
        "reject_reason": reject_reason,
    }


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
    return (as_int(record.get("id")), record.get("source_file") or "")


def result_sort_key(result):
    return (
        result["score"],
        result["verified_rank"],
        result["activity_sort_ts"],
        result["profile_status_rank"],
    )


def diversity_job_cluster(job):
    text = as_text(job)
    if not text:
        return ""
    for pattern, label in DIVERSITY_JOB_PATTERNS:
        if pattern.search(text):
            return label
    return text[:12]


def diversity_signature(result):
    profile = result.get("profile") or {}
    return (
        diversity_job_cluster(profile.get("job")),
        as_text(profile.get("career_intensity")),
        as_text(profile.get("communication_style")),
        as_text(profile.get("life_routine")),
        as_text(profile.get("commitment_clarity")),
    )


def diversity_penalty(candidate, selected):
    candidate_signature = diversity_signature(candidate)
    max_penalty = 0
    for existing in selected:
        overlap = sum(
            1
            for left, right in zip(candidate_signature, diversity_signature(existing))
            if left and right and left == right
        )
        if overlap >= 4:
            max_penalty = max(max_penalty, 6)
        elif overlap >= 3:
            max_penalty = max(max_penalty, 4)
        elif overlap >= 2:
            max_penalty = max(max_penalty, 2)
    return max_penalty


def trim_low_quality_tail(results):
    if len(results) <= 1:
        return results

    leader = results[0]
    trimmed = [leader]
    for item in results[1:]:
        score_gap = leader.get("score", 0) - item.get("score", 0)
        severe_concession = "多项条件需要放宽后才成立" in (item.get("risk_flags") or [])
        high_risk_tail = item.get("risk_score", 0) >= 35
        if severe_concession and score_gap >= 20:
            continue
        if high_risk_tail and score_gap >= 25:
            continue
        trimmed.append(item)
    return trimmed


def select_diverse_results(results, limit):
    results = trim_low_quality_tail(results)
    if len(results) <= limit:
        return results[:limit]

    remaining = list(results)
    selected = []
    while remaining and len(selected) < limit:
        best = None
        best_key = None
        for item in remaining:
            penalty = diversity_penalty(item, selected)
            key = (
                item["score"] - penalty,
                item["score"],
                item["verified_rank"],
                item["activity_sort_ts"],
                item["profile_status_rank"],
            )
            if best is None or key > best_key:
                best = item
                best_key = key
        selected.append(best)
        remaining.remove(best)
    return selected


def attach_photo_previews(results, preview_count, photos_table_name=None):
    if preview_count <= 0 or not results:
        return

    grouped_profile_ids = {}
    for result in results:
        profile_id = as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, table_name = split_source_file_ref(source_file)
        if profile_id is None or not source:
            continue
        group_key = (source, table_name or None)
        grouped_profile_ids.setdefault(group_key, [])
        if profile_id not in grouped_profile_ids[group_key]:
            grouped_profile_ids[group_key].append(profile_id)

    preview_lookup = {}
    for group_key, profile_ids in grouped_profile_ids.items():
        source, table_name = group_key
        try:
            preview_lookup[group_key] = load_mysql_photo_previews(
                source,
                profile_ids,
                table_name=table_name,
                photos_table_name=photos_table_name,
                preview_count=preview_count,
            )
        except Exception as exc:
            print(
                f"WARN: skipping photo previews for {redact_mysql_source(source)}#{table_name or ''}: {exc}",
                file=sys.stderr,
            )
            preview_lookup[group_key] = {}

    for result in results:
        profile_id = as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, table_name = split_source_file_ref(source_file)
        previews = preview_lookup.get((source, table_name or None), {}).get(profile_id, [])
        if previews:
            result["photo_preview"] = previews


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
