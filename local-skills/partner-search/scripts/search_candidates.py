#!/usr/bin/env python3

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse


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
    "accept_smoking": {"accept_smoking", "接受抽烟", "接受吸烟", "是否接受抽烟", "是否接受吸烟"},
    "accept_drinking": {"accept_drinking", "接受喝酒", "接受饮酒", "是否接受喝酒", "是否接受饮酒"},
    "accept_marital_status": {"accept_marital_status", "接受婚况", "可接受婚况", "可接受婚姻状态"},
    "accept_marital_status_strength": {
        "accept_marital_status_strength",
        "婚况接受强度",
        "婚史接受强度",
        "婚况接受态度",
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
    "marriage_timeline": {"marriage_timeline", "结婚时间", "结婚计划", "结婚节奏"},
    "family_background": {"family_background", "家庭情况", "家庭背景"},
    "profile_status": {"profile_status", "资料状态", "档案状态"},
    "last_active_at": {"last_active_at", "最近活跃时间", "最后活跃时间"},
    "verified_level": {"verified_level", "认证等级", "认证级别"},
    "source_channel": {"source_channel", "来源渠道", "来源"},
    "created_at": {"created_at", "创建时间"},
    "updated_at": {"updated_at", "更新时间"},
    "notes": {"notes", "备注", "说明"},
}

MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
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
    "accept_smoking",
    "accept_drinking",
    "accept_marital_status",
    "accept_marital_status_strength",
    "marital_status",
    "want_children",
    "accept_partner_children",
    "accept_partner_children_strength",
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

ACCEPTED_VALUES = {"接受", "是", "可以", "ok", "accept", "accepted"}
REJECTED_VALUES = {"不接受", "否", "不可以", "reject", "rejected"}
NEGOTIABLE_VALUES = {"可协商", "协商", "待定"}
UNKNOWN_VALUES = {"未知", "不确定", "未说明", "未填写", "unknown"}
POSITIVE_HABIT_VALUES = {"是", "偶尔", "有", "yes", "true", "1"}

FIELD_DISPLAY_NAMES = {
    "profile_status": "资料状态",
    "age": "年龄",
    "height": "身高",
    "gender": "性别",
    "city": "城市",
    "district": "区域",
    "settlement_city": "定居城市",
    "relationship_goal": "关系目标",
    "life_routine": "作息类型",
    "communication_style": "沟通风格",
    "dating_pace": "推进节奏",
    "expression_style": "表达风格",
    "relationship_capacity": "关系承接能力",
    "interaction_comfort": "相处状态",
    "patience_level": "耐心程度",
    "life_texture": "生活感层次",
    "career_intensity": "工作节奏类型",
    "exercise_habit": "运动习惯",
    "growth_signal": "事业势能",
    "warmth_style": "聊天温度",
    "aesthetic_expression": "审美表达",
    "conversation_resonance": "聊天共鸣",
    "personal_presence": "人物感",
    "lightness_humor": "轻松感",
    "consumption_attitude": "消费观锚点",
    "chat_texture": "聊天质感",
    "commitment_clarity": "长期意图明确度",
    "relationship_execution": "现实推进方式",
    "blended_family_readiness": "现实承接度",
    "smoking": "抽烟情况",
    "drinking": "喝酒情况",
    "long_distance": "异地态度",
    "housing_status": "住房情况",
    "car_status": "车辆情况",
    "marital_status": "婚况",
    "has_children": "子女情况",
    "want_children": "生育计划",
    "accept_partner_children": "是否接受对方有孩子",
    "marriage_timeline": "结婚节奏",
    "accept_marital_status": "是否接受对方婚况",
    "accept_marital_status_strength": "婚史接受真实度",
    "accept_smoking": "是否接受对方抽烟",
    "accept_drinking": "是否接受对方喝酒",
    "accept_long_distance": "是否接受异地",
    "accept_partner_children_strength": "对子女接受真实度",
    "preferred_age_strictness": "年龄要求硬度",
    "preferred_height_strictness": "身高要求硬度",
    "preferred_education_strictness": "学历要求硬度",
    "preferred_income_strictness": "收入要求硬度",
}

KEYWORD_EVIDENCE_FIELDS = [
    ("personality", "性格"),
    ("values", "价值观"),
    ("lifestyle", "生活方式"),
    ("hobbies", "爱好"),
    ("life_routine", "作息类型"),
    ("communication_style", "沟通风格"),
    ("dating_pace", "推进节奏"),
    ("expression_style", "表达风格"),
    ("relationship_capacity", "关系承接能力"),
    ("interaction_comfort", "相处状态"),
    ("patience_level", "耐心程度"),
    ("life_texture", "生活感层次"),
    ("career_intensity", "工作节奏类型"),
    ("exercise_habit", "运动习惯"),
    ("growth_signal", "事业势能"),
    ("warmth_style", "聊天温度"),
    ("aesthetic_expression", "审美表达"),
    ("conversation_resonance", "聊天共鸣"),
    ("personal_presence", "人物感"),
    ("lightness_humor", "轻松感"),
    ("consumption_attitude", "消费观锚点"),
    ("chat_texture", "聊天质感"),
    ("commitment_clarity", "长期意图明确度"),
    ("relationship_execution", "现实推进方式"),
    ("blended_family_readiness", "现实承接度"),
    ("notes", "备注"),
    ("family_background", "家庭情况"),
]

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

RISK_FLAG_PENALTIES = {
    "对方对子女情况仅可协商": 10,
    "对方对子女接受度未知": 12,
    "对方对抽烟仅可协商": 7,
    "对方对抽烟接受度未知": 9,
    "对方对喝酒仅可协商": 6,
    "对方对喝酒接受度未知": 8,
    "对方异地仅可协商": 5,
    "对方异地接受度未知": 7,
    "对方年龄要求可能可放宽": 6,
    "对方身高要求可能可放宽": 5,
    "对方学历要求可能可放宽": 5,
    "对方收入要求可能可放宽": 6,
    "对方婚史接受度偏保守": 8,
    "对方对子女接受度偏保守": 9,
    "生活阶段可能有落差": 8,
    "资料偏稳但不够鲜活": 5,
    "相处可能偏冷": 6,
    "相处节奏可能偏赶": 5,
    "忙的时候可能更难推进": 5,
    "工作节奏偏忙，稳定投入要再看": 5,
    "主动沟通感偏弱": 4,
    "消费观还不够具体": 4,
    "聊天还像完成任务": 5,
    "长期意图有，但推进方式还不够落地": 4,
    "推进方式偏慢观察": 4,
    "成长势能偏弱": 6,
    "聊天温度偏冷": 5,
    "审美表达偏平": 4,
    "聊天可能像信息交换": 5,
    "人物感偏淡": 5,
    "聊天可能偏板正": 5,
    "进入关系信号偏弱": 6,
    "重组家庭现实承接仍需确认": 6,
    "未认证": 6,
    "活跃时间未知": 4,
    "90天前活跃": 6,
}

RELATIONSHIP_GOAL_STRENGTH_BONUS = {
    "先接触看看": 0,
    "认真恋爱": 2,
    "结婚导向": 4,
}

STRICTNESS_HARD_VALUES = {"硬性", "严格", "必须", "不能放宽"}
STRICTNESS_SOFT_VALUES = {"可放宽", "可商量", "弹性"}
STRICTNESS_REFERENCE_VALUES = {"仅参考", "参考", "偏好参考"}

ACCEPTANCE_STRENGTH_STRONG_VALUES = {"明确接受", "长期接受", "真接受"}
ACCEPTANCE_STRENGTH_CAUTION_VALUES = {"谨慎接受", "了解后定", "需要磨合"}
ACCEPTANCE_STRENGTH_SURFACE_VALUES = {"短期可聊", "表面接受", "先接触再说"}


def build_alias_lookup():
    lookup = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup[normalize_key(alias)] = canonical
    return lookup


ALIAS_LOOKUP = build_alias_lookup()


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
    source, separator, table_name = str(source_ref).rpartition("#")
    if not separator:
        return redact_mysql_source(source_ref)
    redacted = redact_mysql_source(source)
    return f"{redacted}#{table_name}" if table_name else redacted


def default_source_help_text():
    if DEFAULT_MYSQL_SOURCE:
        return f"Defaults to PARTNER_SEARCH_MYSQL_SOURCE={redact_mysql_source(DEFAULT_MYSQL_SOURCE)}."
    return "Required unless PARTNER_SEARCH_MYSQL_SOURCE is set."


def split_keywords(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[，,、;/\n]+", str(value))
    return [str(item).strip() for item in items if str(item).strip()]


def merge_keyword_args(values):
    merged = []
    for value in values or []:
        merged.extend(split_keywords(value))
    return merged


def as_lower(value):
    return str(value).strip().lower() if value is not None else ""


def as_text(value):
    return str(value).strip() if value is not None else ""


def normalize_whitespace(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def field_display_name(field):
    return FIELD_DISPLAY_NAMES.get(str(field), str(field))


def as_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def normalize_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    lowered = as_lower(value)
    if lowered in {"1", "true", "yes", "y", "是", "有"}:
        return True
    if lowered in {"0", "false", "no", "n", "否", "无"}:
        return False
    return None


def normalize_acceptance_state(value):
    if value is None or value == "":
        return "missing"
    lowered = as_lower(value)
    if lowered in ACCEPTED_VALUES:
        return "accepted"
    if lowered in REJECTED_VALUES:
        return "rejected"
    if lowered in NEGOTIABLE_VALUES:
        return "negotiable"
    if lowered in UNKNOWN_VALUES:
        return "unknown"
    normalized = normalize_bool(value)
    if normalized is True:
        return "accepted"
    if normalized is False:
        return "rejected"
    return "unknown"


def normalize_strictness_state(value):
    if value is None or value == "":
        return "hard"
    lowered = as_lower(value)
    if lowered in {as_lower(item) for item in STRICTNESS_HARD_VALUES}:
        return "hard"
    if lowered in {as_lower(item) for item in STRICTNESS_SOFT_VALUES}:
        return "soft"
    if lowered in {as_lower(item) for item in STRICTNESS_REFERENCE_VALUES}:
        return "reference"
    return "hard"


def normalize_acceptance_strength(value):
    if value is None or value == "":
        return "unknown"
    lowered = as_lower(value)
    if lowered in {as_lower(item) for item in ACCEPTANCE_STRENGTH_STRONG_VALUES}:
        return "strong"
    if lowered in {as_lower(item) for item in ACCEPTANCE_STRENGTH_CAUTION_VALUES}:
        return "cautious"
    if lowered in {as_lower(item) for item in ACCEPTANCE_STRENGTH_SURFACE_VALUES}:
        return "surface"
    return "unknown"


def contains_any_text(value, keywords):
    lowered = as_lower(value)
    return any(as_lower(keyword) in lowered for keyword in keywords)


def habit_requires_acceptance(value):
    return as_lower(value) in POSITIVE_HABIT_VALUES


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
    if marital_status in {"未婚", "离异未育"}:
        return False
    return None


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


def extract_keyword_evidence(record, keyword):
    lowered_keyword = as_lower(keyword)
    if not lowered_keyword:
        return None

    for field, label in KEYWORD_EVIDENCE_FIELDS:
        value = record.get(field)
        if not value:
            continue
        segments = [
            normalize_whitespace(part.strip(" ,，。;；|"))
            for part in re.split(r"[。；;\n|]+", str(value))
            if normalize_whitespace(part.strip(" ,，。;；|"))
        ]
        for segment in segments:
            if lowered_keyword in segment.lower():
                if contains_sensitive_note_detail(segment):
                    return f"{label}: 命中关键词，敏感细节已隐藏"
                return f"{label}: {shorten_text(redact_sensitive_text(segment))}"
    return None


def missing_field_penalty(field):
    if str(field).startswith("self_"):
        return 0
    return CRITICAL_MISSING_FIELD_PENALTIES.get(field, 0)


def risk_flag_penalty(risk_flag):
    return RISK_FLAG_PENALTIES.get(risk_flag, 0)


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


def keyword_requested(criteria, keywords):
    joined = " ".join(criteria.get("must_have", []) + criteria.get("prefer", []))
    return contains_any_text(joined, keywords)


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
    wants_proactive_communication = keyword_requested(criteria, {"主动沟通", "沟通"})
    cares_about_consumption = keyword_requested(
        criteria, {"消费观", "消费观正常", "不攀比", "过日子", "务实", "花钱观"}
    )

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
        if exercise_habit == "规律运动":
            reasons.append("运动习惯更匹配")
            score_bonus += 5
            match_evidence.append(f"运动习惯更匹配 <- 运动习惯: {exercise_habit}")
        elif exercise_habit == "轻运动":
            reasons.append("生活状态更合拍")
            score_bonus += 3
            match_evidence.append(f"生活状态更合拍 <- 运动习惯: {exercise_habit}")

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
            reasons.append("消费观更清醒")
            score_bonus += 5
            match_evidence.append(f"消费观更清醒 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "有取舍会生活":
            reasons.append("消费观有取舍，也会生活")
            score_bonus += 4
            match_evidence.append(f"消费观有取舍，也会生活 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "踏实过日子":
            reasons.append("消费观更适合过日子")
            score_bonus += 3
            match_evidence.append(f"消费观更适合过日子 <- 消费观锚点: {consumption_attitude}")
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
            reasons.append("更容易聊出感觉")
            score_bonus += 6
            match_evidence.append(f"更容易聊出感觉 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "会接话也会接情绪":
            reasons.append("聊天不只对条件，也有情绪接住感")
            score_bonus += 4
            match_evidence.append(f"聊天不只对条件，也有情绪接住感 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "偏信息交换":
            risk_flags.append("聊天可能像信息交换")
        if personal_presence == "有记忆点":
            reasons.append("人物感更强")
            score_bonus += 6
            match_evidence.append(f"人物感更强 <- 人物感: {personal_presence}")
        elif personal_presence == "温和耐看":
            reasons.append("人物感更舒服")
            score_bonus += 3
            match_evidence.append(f"人物感更舒服 <- 人物感: {personal_presence}")
        elif personal_presence == "偏平":
            risk_flags.append("人物感偏淡")
        if lightness_humor == "有点幽默不端着":
            reasons.append("聊天不木，也更有轻松感")
            score_bonus += 5
            match_evidence.append(f"聊天不木，也更有轻松感 <- 轻松感: {lightness_humor}")
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

    if requires_explicit_marital_acceptance(self_profile) or requires_explicit_children_acceptance(self_profile):
        if blended_family_readiness == "已想过现实安排":
            reasons.append("更能承接现实安排")
            score_bonus += 5
            match_evidence.append(f"更能承接现实安排 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness == "愿意一起商量":
            reasons.append("现实问题愿意一起商量")
            score_bonus += 2
            match_evidence.append(f"现实问题愿意一起商量 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness in {"仅口头接受", "未知", None, ""}:
            risk_flags.append("重组家庭现实承接仍需确认")
        if (
            requires_explicit_marital_acceptance(self_profile)
            and record.get("accept_marital_status_strength") == "明确接受"
            and contains_any_text(notes_and_values, {"婚史", "再婚", "现实安排", "家里相处", "边界", "为什么结束"})
        ):
            reasons.append("对婚史和现实问题想得更具体")
            score_bonus += 3
            match_evidence.append("对婚史和现实问题想得更具体 <- 备注/价值观提到了婚史或现实安排")

    relationship_goals = set(criteria.get("relationship_goals") or [])
    wants_clear_long_term = (
        "结婚导向" in relationship_goals
        or keyword_requested(criteria, {"稳定投入关系", "认真推进", "结婚", "长期"})
        or as_int(self_profile.get("age")) is not None
        and as_int(self_profile.get("age")) >= 29
    )
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
        reasons.append("不只合适，也更容易让人有感觉")
        score_bonus += 5
        match_evidence.append(
            "不只合适，也更容易让人有感觉 <- 聊天共鸣/人物感/审美表达组合更完整"
        )
    if (
        high_bar_profile
        and lightness_humor == "有点幽默不端着"
        and conversation_resonance == "能聊想法也能聊日常"
    ):
        reasons.append("理性之外，也更容易有火花")
        score_bonus += 4
        match_evidence.append("理性之外，也更容易有火花 <- 轻松感/聊天共鸣更完整")

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
        elif field == "accept_marital_status":
            questions.append("确认是否真的接受你的婚史，而不是表面上说可以。")
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
        elif risk == "对方对子女接受度偏保守":
            questions.append("确认对方能不能长期接受孩子和现实安排，不要只停留在口头上。")
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
        elif risk == "消费观还不够具体":
            questions.append("确认对方的消费观到底是清醒务实，还是只是资料里泛泛写正常。")
        elif risk == "聊天还像完成任务":
            questions.append("确认对方聊天是不是容易只讲条件和流程，还是能把话题真正聊活。")
        elif risk == "长期意图有，但推进方式还不够落地":
            questions.append("确认对方不是只会说想长期，而是真的会把推进节奏和安排说清。")
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

    record["combined_text"] = build_combined_text(record)
    return record


def build_combined_text(record):
    parts = []
    for key in TEXT_FIELDS:
        value = record.get(key)
        if value:
            parts.append(str(value))
    return " | ".join(parts).lower()


def parse_mysql_source(source, table_name=None):
    parsed = urlparse(str(source))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        raise ValueError(f"Unsupported MySQL source: {source}")

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError("MySQL source must include a database name, for example mysql://user:pass@host:3306/db")

    query = parse_qs(parsed.query)
    resolved_table = table_name or query.get("table", [None])[0]
    photos_table = query.get("photos_table", [DEFAULT_MYSQL_PHOTOS_TABLE])[0]
    charset = query.get("charset", ["utf8mb4"])[0]
    unix_socket = query.get("unix_socket", [None])[0]

    config = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": database,
        "table": resolved_table,
        "photos_table": photos_table,
        "charset": charset,
    }
    if unix_socket:
        config["unix_socket"] = unquote(unix_socket)
    return config


def quote_mysql_ident(identifier):
    return "`" + str(identifier).replace("`", "``") + "`"


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


def build_mysql_prefilter(criteria, canonical_to_actual, include_ids=None):
    include_ids = [item for item in (include_ids or []) if item is not None]
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
    add_in("verified_level", criteria.get("verified_levels"), default_value="none")
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

    if base_where and include_where:
        return f" WHERE ({base_where}) OR ({include_where})", base_params + include_params
    if base_where:
        return f" WHERE {base_where}", base_params
    if include_where:
        return f" WHERE {include_where}", include_params
    return "", []


def load_mysql(source, table_name=None, criteria=None, include_ids=None):
    try:
        import pymysql
    except ImportError as exc:
        raise ValueError("MySQL support requires PyMySQL. Install it with `pip install pymysql`.") from exc

    config = parse_mysql_source(source, table_name=table_name)
    connect_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config.get("user") is not None:
        connect_kwargs["user"] = config["user"]
    if config.get("password") is not None:
        connect_kwargs["password"] = config["password"]
    if config.get("unix_socket"):
        connect_kwargs["unix_socket"] = config["unix_socket"]

    conn = pymysql.connect(**connect_kwargs)
    try:
        table = config["table"] or detect_mysql_profile_table(conn, config["database"])
        if not table:
            raise ValueError(f"Could not detect a candidate table in MySQL database {config['database']}")
        canonical_to_actual = resolve_mysql_columns(conn, config["database"], table)
        prefilter = build_mysql_prefilter(criteria or {}, canonical_to_actual, include_ids=include_ids)
        if prefilter is None:
            where_clause, params = "", []
        else:
            where_clause, params = prefilter
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(table)}{where_clause}",
                params,
            )
            rows = cursor.fetchall()
        return [
            normalize_record(dict(row, source_file=f"{source}#{table}"))
            for row in rows
        ]
    finally:
        conn.close()


def load_mysql_photo_previews(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
    if preview_count <= 0 or not profile_ids:
        return {}

    try:
        import pymysql
    except ImportError as exc:
        raise ValueError("MySQL support requires PyMySQL. Install it with `pip install pymysql`.") from exc

    config = parse_mysql_source(source, table_name=table_name)
    photo_table = photos_table_name or config.get("photos_table") or DEFAULT_MYSQL_PHOTOS_TABLE
    connect_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config.get("user") is not None:
        connect_kwargs["user"] = config["user"]
    if config.get("password") is not None:
        connect_kwargs["password"] = config["password"]
    if config.get("unix_socket"):
        connect_kwargs["unix_socket"] = config["unix_socket"]

    conn = pymysql.connect(**connect_kwargs)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name AS column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (config["database"], photo_table),
            )
            photo_columns = {row["column_name"] for row in cursor.fetchall()}
            if "profile_id" not in photo_columns or "photo_url" not in photo_columns:
                raise ValueError(
                    f"MySQL photos table {config['database']}.{photo_table} must contain profile_id and photo_url columns."
                )

            placeholders = ", ".join(["%s"] * len(profile_ids))
            order_parts = ["`profile_id` ASC"]
            if "is_primary" in photo_columns:
                order_parts.append("CASE WHEN `is_primary` = 1 THEN 0 ELSE 1 END")
            elif "photo_type" in photo_columns:
                order_parts.append("CASE WHEN `photo_type` = 'avatar' THEN 0 ELSE 1 END")
            if "sort_order" in photo_columns:
                order_parts.append("`sort_order` ASC")
            if "id" in photo_columns:
                order_parts.append("`id` ASC")

            cursor.execute(
                f"""
                SELECT `profile_id`, `photo_url`
                FROM {quote_mysql_ident(photo_table)}
                WHERE `profile_id` IN ({placeholders})
                ORDER BY {", ".join(order_parts)}
                """,
                profile_ids,
            )

            previews = {}
            for row in cursor.fetchall():
                profile_id = as_int(row.get("profile_id"))
                photo_url = row.get("photo_url")
                if profile_id is None or not photo_url:
                    continue
                previews.setdefault(profile_id, [])
                if len(previews[profile_id]) < preview_count:
                    previews[profile_id].append(photo_url)
            return previews
    finally:
        conn.close()


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


def load_source(source, table_name=None, criteria=None, include_ids=None):
    if not is_mysql_source(source):
        raise ValueError(
            "Unsupported source type. Use a MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles"
        )
    return load_mysql(
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
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

    must_have = merge_keyword_args(args.must_have)
    if must_have:
        criteria["must_have"] = must_have

    must_not_have = merge_keyword_args(args.must_not_have)
    if must_not_have:
        criteria["must_not_have"] = must_not_have

    prefer = merge_keyword_args(args.prefer)
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
    if args.photo_count_min is not None:
        criteria["photo_count_min"] = args.photo_count_min
    required_known_fields = [
        ALIAS_LOOKUP.get(normalize_key(field), normalize_key(field))
        for field in merge_keyword_args(getattr(args, "require_known", None))
    ]
    if required_known_fields:
        criteria["required_known_fields"] = required_known_fields
    criteria["exclude_ids"] = {item for item in args.exclude_id or []}

    return criteria


def build_self_profile_from_args(args, records):
    profile = {}

    if args.self_id is not None:
        matched_records = [record for record in records if as_int(record.get("id")) == args.self_id]
        if not matched_records:
            raise ValueError(f"Could not find self profile id {args.self_id} in the selected source.")
        distinct_sources = unique_ordered(record.get("source_file") or "" for record in matched_records)
        if len(distinct_sources) > 1:
            readable_sources = [redact_source_ref(source) or "<unknown source>" for source in distinct_sources]
            raise ValueError(
                f"Self profile id {args.self_id} is ambiguous across multiple sources: "
                + ", ".join(readable_sources)
                + ". Narrow --source or use a unique id."
            )
        matched = matched_records[0]
        profile.update(strip_internal_fields(matched))
        profile["source_file"] = matched.get("source_file") or ""
        income_min, income_max = parse_income_range_to_wan(matched.get("income_range"))
        profile["income_min_wan"] = income_min
        profile["income_max_wan"] = income_max

    overlays = {
        "age": args.self_age,
        "city": args.self_city,
        "height": args.self_height,
        "education": args.self_education,
        "job": getattr(args, "self_job", None),
        "marital_status": args.self_marital_status,
        "smoking": args.self_smoking,
        "drinking": args.self_drinking,
    }
    for key, value in overlays.items():
        if value is not None:
            profile[key] = value

    if args.self_income_wan is not None:
        profile["income_min_wan"] = args.self_income_wan
        profile["income_max_wan"] = args.self_income_wan
    if args.self_has_children is not None:
        profile["has_children"] = bool(args.self_has_children)

    if not profile:
        return None

    if args.self_id is not None:
        profile["id"] = args.self_id
    profile["has_children"] = normalize_bool(profile.get("has_children"))
    return profile


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
    labels = {
        0: "未认证",
        1: "基础认证",
        2: "照片认证",
        3: "实名认证",
        4: "线下核验",
    }
    return (rank * 2, labels.get(rank, "未认证"), rank)


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
    if code in {"active_too_old", "active_time_missing"}:
        return "放宽活跃时间要求，先确认对方现在还找不找。"
    if code == "relationship_goal_mismatch":
        return "关系目标别卡太死，结婚导向和认真恋爱可以先一起放进池子。"
    if code in {"smoking_mismatch", "drinking_mismatch", "long_distance_mismatch"}:
        return "把生活习惯类条件分成硬雷点和可追问项，别一刀切。"
    if code in {
        "marital_status_mismatch",
        "has_children_mismatch",
        "want_children_mismatch",
        "accept_partner_children_mismatch",
        "accept_marital_status_strength_mismatch",
        "accept_partner_children_strength_mismatch",
        "reciprocal_marital_status_preference",
        "reciprocal_children_acceptance",
        "reciprocal_marital_status_acceptance_not_strong",
        "reciprocal_children_acceptance_not_strong",
        "reciprocal_marital_status_acceptance_unknown",
        "reciprocal_children_acceptance_unknown",
    }:
        return "婚况和孩子会明显压缩池子，建议先保留边界内可聊对象再二次确认。"
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
            "top_reasons": [],
            "relax_suggestions": [
                "数据源预筛后已经没候选了，先检查城市、年龄、资料状态、最近活跃、认证等级这些硬条件。"
            ],
        }

    rejection_counts = Counter()
    passed_count = 0
    for record in records:
        diagnostic = evaluate_candidate(record, criteria, diagnostics=True)
        if diagnostic and diagnostic.get("matched"):
            passed_count += 1
            continue
        reason = "unknown"
        if diagnostic:
            reason = diagnostic.get("reject_reason") or "unknown"
        rejection_counts[reason] += 1

    top_reasons = [
        {
            "reason": reason,
            "label": format_rejection_reason(reason),
            "count": count,
        }
        for reason, count in rejection_counts.most_common(4)
    ]
    relax_suggestions = unique_ordered(
        suggestion_for_rejection(item["reason"])
        for item in top_reasons
    )

    return {
        "scanned_count": len(records),
        "passed_count": passed_count,
        "top_reasons": top_reasons,
        "relax_suggestions": relax_suggestions[:3],
    }


def format_no_match_text(diagnostics):
    lines = ["No matches found."]
    if not diagnostics:
        return "\n".join(lines)

    lines.append(
        f"pool_summary: scanned={diagnostics.get('scanned_count', 0)} | passed={diagnostics.get('passed_count', 0)}"
    )
    top_reasons = diagnostics.get("top_reasons") or []
    if top_reasons:
        lines.append(
            "why_no_match: "
            + " | ".join(f"{item['label']} x{item['count']}" for item in top_reasons)
        )
    suggestions = diagnostics.get("relax_suggestions") or []
    if suggestions:
        lines.append("relax_suggestions: " + " | ".join(suggestions))
    return "\n".join(lines)


def evaluate_reciprocal_compatibility(record, self_profile, diagnostics=False):
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
    if accepted_statuses:
        self_status = self_profile.get("marital_status")
        if not self_status:
            missing_fields.append("self_marital_status")
        elif not match_any_exact(self_status, accepted_statuses):
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
                elif requires_explicit_marital_acceptance(self_profile):
                    return fail("reciprocal_marital_status_acceptance_not_strong")
                elif marital_strength in {"cautious", "surface"}:
                    risk_flags.append("对方婚史接受度偏保守")
                elif marital_strength == "unknown":
                    if requires_explicit_marital_acceptance(self_profile):
                        return fail("reciprocal_marital_status_acceptance_unknown")
                    missing_fields.append("accept_marital_status_strength")
    else:
        self_status = self_profile.get("marital_status")
        if self_status and as_lower(self_status) not in {"", "未婚"}:
            missing_fields.append("accept_marital_status")

    self_has_children = normalize_bool(self_profile.get("has_children"))
    accept_partner_children = normalize_acceptance_state(record.get("accept_partner_children"))
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
            elif requires_explicit_children_acceptance(self_profile):
                return fail("reciprocal_children_acceptance_not_strong")
            elif children_strength in {"cautious", "surface"}:
                risk_flags.append("对方对子女接受度偏保守")
            elif children_strength == "unknown":
                if requires_explicit_children_acceptance(self_profile):
                    return fail("reciprocal_children_acceptance_unknown")
                missing_fields.append("accept_partner_children_strength")
        elif accept_partner_children == "negotiable":
            if requires_explicit_children_acceptance(self_profile):
                return fail("reciprocal_children_acceptance_not_strong")
            risk_flags.append("对方对子女情况仅可协商")
        elif accept_partner_children == "unknown":
            if requires_explicit_children_acceptance(self_profile):
                return fail("reciprocal_children_acceptance_unknown")
            risk_flags.append("对方对子女接受度未知")
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
        elif accept_long_distance == "negotiable":
            risk_flags.append("对方异地仅可协商")
        elif accept_long_distance == "unknown":
            risk_flags.append("对方异地接受度未知")
        else:
            missing_fields.append("accept_long_distance")

    return {
        "matched": True,
        "matched_on": reasons,
        "missing_fields": missing_fields,
        "risk_flags": risk_flags,
        "score_bonus": score_bonus,
        "reject_reason": None,
    }


def evaluate_candidate(record, criteria, diagnostics=False):
    def fail(reason, detail=None):
        if not diagnostics:
            return None
        return {
            "matched": False,
            "reject_reason": build_rejection_reason(reason, detail),
            "id": record.get("id"),
            "name": record.get("name") or "未命名",
        }

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
    if criteria.get("height_min") is not None:
        if height is None:
            missing_fields.append("height")
        elif height < criteria["height_min"]:
            return fail("height_below_min")
        else:
            fit_score += 5
    if criteria.get("height_max") is not None:
        if height is None:
            if "height" not in missing_fields:
                missing_fields.append("height")
        elif height > criteria["height_max"]:
            return fail("height_above_max")

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
    if self_city and candidate_city and as_lower(self_city) == as_lower(candidate_city):
        reasons.append("同城")
        fit_score += 8

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

    combined_text = record.get("combined_text", "")

    if criteria.get("must_have"):
        for keyword in criteria["must_have"]:
            if keyword.lower() not in combined_text:
                return fail("must_have_missing", keyword)
            reasons.append(f"包含 {keyword}")
            fit_score += 8
            evidence = extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if criteria.get("must_not_have"):
        for keyword in criteria["must_not_have"]:
            if keyword.lower() in combined_text:
                return fail("must_not_have_hit", keyword)

    for keyword in criteria.get("prefer", []):
        if keyword.lower() in combined_text:
            reasons.append(f"偏好命中 {keyword}")
            fit_score += 6
            evidence = extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if criteria.get("smoking"):
        smoking = as_lower(record.get("smoking"))
        desired = as_lower(criteria["smoking"])
        if not smoking:
            missing_fields.append("smoking")
        elif smoking != desired:
            return fail("smoking_mismatch")
        else:
            fit_score += 8

    if criteria.get("drinking"):
        drinking = as_lower(record.get("drinking"))
        desired = as_lower(criteria["drinking"])
        if not drinking:
            missing_fields.append("drinking")
        elif drinking != desired:
            return fail("drinking_mismatch")
        else:
            fit_score += 5

    if criteria.get("long_distance"):
        long_distance = as_lower(record.get("long_distance"))
        desired = as_lower(criteria["long_distance"])
        if not long_distance:
            missing_fields.append("long_distance")
        elif long_distance != desired:
            return fail("long_distance_mismatch")
        else:
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
        elif not match_any_exact(marital_status, criteria["marital_statuses"]):
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

    missing_penalty = sum(missing_field_penalty(field) for field in unique_ordered(missing_fields))
    risk_score = missing_penalty + sum(
        risk_flag_penalty(flag) for flag in unique_ordered(risk_flags)
    )
    score = fit_score + confidence_score - risk_score

    follow_up_questions = build_follow_up_questions(
        record,
        missing_fields,
        risk_flags,
        self_profile=criteria.get("self_profile"),
    )

    result = {
        "matched": True,
        "id": record.get("id"),
        "name": record.get("name") or "未命名",
        "score": score,
        "fit_score": fit_score,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "matched_on": unique_ordered(reasons),
        "reciprocal_on": unique_ordered(reciprocal_reasons),
        "missing_fields": unique_ordered(missing_fields),
        "risk_flags": unique_ordered(risk_flags),
        "match_evidence": unique_ordered(match_evidence),
        "follow_up_questions": follow_up_questions,
        "profile": strip_internal_fields(record),
        "source_file": record.get("source_file"),
        "verified_rank": verified_sort_rank,
        "activity_sort_ts": int(activity_dt.timestamp()) if activity_dt else 0,
        "profile_status_rank": profile_status_rank(profile_status),
        "reject_reason": None,
    }
    if not diagnostics:
        result.pop("matched", None)
        result.pop("reject_reason", None)
    return result


def unique_ordered(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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


def attach_photo_previews(results, preview_count, photos_table_name=None):
    if preview_count <= 0 or not results:
        return

    grouped_profile_ids = {}
    for result in results:
        profile_id = as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, _, table_name = source_file.rpartition("#")
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
        source, _, table_name = source_file.rpartition("#")
        previews = preview_lookup.get((source, table_name or None), {}).get(profile_id, [])
        if previews:
            result["photo_preview"] = previews


def format_text(results, include_source=False):
    lines = []
    for index, result in enumerate(results, start=1):
        profile = result["profile"]
        headline = (
            f"{index}. {result['name']} | score={result['score']} | "
            f"{profile.get('age', '未知')}岁 | {profile.get('city', '城市未知')} | "
            f"{profile.get('job', '工作未知')}"
        )
        lines.append(headline)
        lines.append(
            "   scoring: "
            f"fit={result.get('fit_score', result['score'])} | "
            f"confidence={result.get('confidence_score', 0)} | "
            f"risk={result.get('risk_score', 0)}"
        )
        meta_parts = []
        if profile.get("profile_status"):
            meta_parts.append(f"status={profile.get('profile_status')}")
        if profile.get("verified_level"):
            meta_parts.append(f"verified={profile.get('verified_level')}")
        if profile.get("photo_count") is not None:
            meta_parts.append(f"photos={profile.get('photo_count')}")
        activity_field, activity_dt = effective_activity_info(profile)
        active_at = format_datetime(activity_dt)
        if activity_field and active_at:
            meta_parts.append(f"{activity_field}={active_at}")
        if meta_parts:
            lines.append(f"   meta: {' | '.join(meta_parts)}")
        vibe_parts = []
        if profile.get("life_routine"):
            vibe_parts.append(f"作息={profile.get('life_routine')}")
        if profile.get("communication_style"):
            vibe_parts.append(f"沟通={profile.get('communication_style')}")
        if profile.get("dating_pace"):
            vibe_parts.append(f"节奏={profile.get('dating_pace')}")
        if profile.get("expression_style"):
            vibe_parts.append(f"表达={profile.get('expression_style')}")
        if profile.get("relationship_capacity"):
            vibe_parts.append(f"关系投入={profile.get('relationship_capacity')}")
        if profile.get("interaction_comfort"):
            vibe_parts.append(f"相处={profile.get('interaction_comfort')}")
        if profile.get("patience_level"):
            vibe_parts.append(f"耐心={profile.get('patience_level')}")
        if profile.get("life_texture"):
            vibe_parts.append(f"生活感={profile.get('life_texture')}")
        if profile.get("career_intensity"):
            vibe_parts.append(f"工作={profile.get('career_intensity')}")
        if profile.get("exercise_habit"):
            vibe_parts.append(f"运动={profile.get('exercise_habit')}")
        if profile.get("growth_signal"):
            vibe_parts.append(f"成长={profile.get('growth_signal')}")
        if profile.get("warmth_style"):
            vibe_parts.append(f"温度={profile.get('warmth_style')}")
        if profile.get("aesthetic_expression"):
            vibe_parts.append(f"审美={profile.get('aesthetic_expression')}")
        if profile.get("conversation_resonance"):
            vibe_parts.append(f"共鸣={profile.get('conversation_resonance')}")
        if profile.get("personal_presence"):
            vibe_parts.append(f"人物感={profile.get('personal_presence')}")
        if profile.get("lightness_humor"):
            vibe_parts.append(f"轻松感={profile.get('lightness_humor')}")
        if profile.get("consumption_attitude"):
            vibe_parts.append(f"消费观={profile.get('consumption_attitude')}")
        if profile.get("chat_texture"):
            vibe_parts.append(f"聊天质感={profile.get('chat_texture')}")
        if profile.get("commitment_clarity"):
            vibe_parts.append(f"长期意图={profile.get('commitment_clarity')}")
        if profile.get("relationship_execution"):
            vibe_parts.append(f"推进方式={profile.get('relationship_execution')}")
        if profile.get("blended_family_readiness"):
            vibe_parts.append(f"现实承接={profile.get('blended_family_readiness')}")
        if vibe_parts:
            lines.append(f"   vibe: {' | '.join(vibe_parts)}")
        if result.get("photo_preview"):
            lines.append(f"   photo_preview: {', '.join(result['photo_preview'])}")
        if result["matched_on"]:
            lines.append(f"   matched_on: {', '.join(result['matched_on'])}")
        if result["reciprocal_on"]:
            lines.append(f"   reciprocal_on: {', '.join(result['reciprocal_on'])}")
        if result["missing_fields"]:
            lines.append(f"   missing_fields: {', '.join(result['missing_fields'])}")
        if result["risk_flags"]:
            lines.append(f"   risk_flags: {', '.join(result['risk_flags'])}")
        if result.get("match_evidence"):
            lines.append(f"   match_evidence: {' | '.join(result['match_evidence'])}")
        if result.get("follow_up_questions"):
            lines.append(f"   follow_up_questions: {' | '.join(result['follow_up_questions'])}")
        notes_summary = summarize_notes(profile.get("notes"))
        if notes_summary:
            lines.append(f"   notes: {notes_summary}")
        if include_source and result.get("source_file"):
            lines.append(f"   source: {redact_source_ref(result['source_file'])}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Search profile sources for partner candidates.")
    parser.add_argument(
        "--source",
        action="append",
        help=(
            "MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles. "
            f"Repeatable. {default_source_help_text()}"
        ),
    )
    parser.add_argument("--table", help="MySQL table name when the table is not included in the DSN.")
    parser.add_argument("--gender", help="Filter by gender.")
    parser.add_argument("--age-min", type=int, help="Minimum age.")
    parser.add_argument("--age-max", type=int, help="Maximum age.")
    parser.add_argument("--height-min", type=int, help="Minimum height in cm.")
    parser.add_argument("--height-max", type=int, help="Maximum height in cm.")
    parser.add_argument("--city", action="append", help="Allowed city. Repeat or use comma-separated values.")
    parser.add_argument("--district", action="append", help="Allowed district. Repeat or use comma-separated values.")
    parser.add_argument(
        "--settlement-city",
        action="append",
        help="Allowed long-term settlement city. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--relationship-goal",
        action="append",
        help="Allowed relationship goal. Repeat or use comma-separated values.",
    )
    parser.add_argument("--must-have", action="append", help="Required keyword. Repeat or use comma-separated values.")
    parser.add_argument(
        "--must-not-have",
        action="append",
        help="Excluded keyword. Repeat or use comma-separated values.",
    )
    parser.add_argument("--prefer", action="append", help="Preferred keyword. Repeat or use comma-separated values.")
    parser.add_argument(
        "--require-known",
        action="append",
        help=(
            "Require these fields to be explicitly filled instead of missing. "
            "Repeat or use comma-separated canonical field names such as smoking,want_children,accept_partner_children."
        ),
    )
    parser.add_argument("--smoking", help="Exact smoking preference, for example 否.")
    parser.add_argument("--drinking", help="Exact drinking preference, for example 否.")
    parser.add_argument("--long-distance", help="Exact long-distance preference, for example 不接受.")
    parser.add_argument(
        "--housing-status",
        action="append",
        help="Allowed housing status. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--car-status",
        action="append",
        help="Allowed car status. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--marital-status",
        action="append",
        help="Allowed candidate marital status. Repeat or use comma-separated values.",
    )
    parser.add_argument("--has-children", type=int, choices=[0, 1], help="Filter whether the candidate has children.")
    parser.add_argument("--want-children", help="Candidate child plan, for example 想要 or 可协商.")
    parser.add_argument(
        "--accept-partner-children",
        help="Candidate acceptance of a partner who already has children.",
    )
    parser.add_argument(
        "--accept-marital-status-strength",
        help="Required candidate marital-history acceptance strength, for example 明确接受.",
    )
    parser.add_argument(
        "--accept-partner-children-strength",
        help="Required candidate child-acceptance strength, for example 明确接受.",
    )
    parser.add_argument(
        "--marriage-timeline",
        action="append",
        help="Allowed marriage timeline. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--profile-status",
        action="append",
        help="Allowed profile status. Defaults to active. Repeat or use comma-separated values.",
    )
    parser.add_argument("--active-within-days", type=int, help="Require recent activity within N days.")
    parser.add_argument(
        "--verified-level-min",
        choices=["none", "basic", "photo", "id", "offline"],
        help="Minimum verification level.",
    )
    parser.add_argument(
        "--verified-level",
        action="append",
        help="Exact allowed verification level. Repeat or use comma-separated values.",
    )
    parser.add_argument("--photo-count-min", type=int, help="Minimum required photo count.")
    parser.add_argument(
        "--photo-preview-count",
        type=int,
        default=0,
        help="Return the top N photo URLs from the MySQL photos table for each result.",
    )
    parser.add_argument(
        "--photos-table",
        help="MySQL photos table name when not using the default profile_photos or DSN photos_table query param.",
    )
    parser.add_argument("--self-id", type=int, help="Use an existing profile id as your own profile for reciprocal matching.")
    parser.add_argument("--self-age", type=int, help="Your age for reciprocal matching.")
    parser.add_argument("--self-city", help="Your city for reciprocal matching.")
    parser.add_argument("--self-height", type=int, help="Your height in cm for reciprocal matching.")
    parser.add_argument("--self-education", help="Your education for reciprocal matching.")
    parser.add_argument("--self-job", help="Your job for contextual matching, for example 医生 or 金融.")
    parser.add_argument("--self-income-wan", type=int, help="Your annual income in 万 for reciprocal matching.")
    parser.add_argument("--self-marital-status", help="Your marital status for reciprocal matching.")
    parser.add_argument("--self-has-children", type=int, choices=[0, 1], help="Whether you have children for reciprocal matching.")
    parser.add_argument("--self-smoking", help="Your smoking habit for reciprocal matching.")
    parser.add_argument("--self-drinking", help="Your drinking habit for reciprocal matching.")
    parser.add_argument("--exclude-id", action="append", type=int, help="Profile id to exclude from results. Repeatable.")
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Include the redacted source DSN and table in the text output for debugging.",
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to return.")
    args = parser.parse_args()

    try:
        criteria = build_criteria_from_args(args)
        records = []
        sources = args.source or ([DEFAULT_MYSQL_SOURCE] if DEFAULT_MYSQL_SOURCE else [])
        if not sources:
            raise ValueError(
                "No profile source configured. Pass --source mysql://user:pass@host:3306/db?table=profiles "
                "or set PARTNER_SEARCH_MYSQL_SOURCE."
            )
        include_ids = [args.self_id] if args.self_id is not None else []
        for source in sources:
            records.extend(
                load_source(
                    source,
                    table_name=args.table,
                    criteria=criteria,
                    include_ids=include_ids,
                )
            )
        self_profile = build_self_profile_from_args(args, records)
        if self_profile:
            criteria["self_profile"] = self_profile
        if args.self_id is not None:
            criteria.setdefault("exclude_record_refs", set()).add(record_ref(self_profile))
        results = []
        for record in records:
            evaluated = evaluate_candidate(record, criteria)
            if evaluated:
                results.append(evaluated)
        results.sort(key=result_sort_key, reverse=True)
        results = results[: args.limit]
        attach_photo_previews(results, args.photo_preview_count, photos_table_name=args.photos_table)

        if results:
            print(format_text(results, include_source=args.show_source))
        else:
            print(format_no_match_text(build_no_match_diagnostics(records, criteria)))
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
