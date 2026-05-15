"""Shared keyword and criteria-normalization helpers for partner search."""

from __future__ import annotations

import json
import re
from typing import Any

from her_time_utils import unique_ordered_texts


ACCEPTED_VALUES = {"接受", "是", "可以", "ok", "accept", "accepted"}
REJECTED_VALUES = {"不接受", "否", "不可以", "reject", "rejected"}
NEGOTIABLE_VALUES = {"可协商", "协商", "待定"}
GUARDED_NEGOTIABLE_VALUES = {"现阶段不太接受", "谨慎可协商", "低接受度可协商"}
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
    "accept_marital_status_semantics": "婚史接受细语义",
    "accept_smoking": "是否接受对方抽烟",
    "accept_drinking": "是否接受对方喝酒",
    "accept_long_distance": "是否接受异地",
    "accept_partner_children_strength": "对子女接受真实度",
    "accept_partner_children_semantics": "对子女接受细语义",
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

NEGATIVE_KEYWORD_EVIDENCE_FIELDS = KEYWORD_EVIDENCE_FIELDS + [
    ("relationship_goal", "关系目标"),
    ("city", "城市"),
    ("settlement_city", "定居城市"),
    ("housing_status", "住房情况"),
    ("car_status", "车辆情况"),
    ("education", "学历"),
    ("job", "工作"),
    ("income_range", "收入范围"),
    ("smoking", "抽烟情况"),
    ("drinking", "喝酒情况"),
    ("long_distance", "异地态度"),
    ("marital_status", "婚况"),
    ("want_children", "生育计划"),
]

STRUCTURED_KEYWORD_SIGNAL_RULES = {
    "情绪稳定": [
        ("interaction_comfort", "相处状态", {"相处轻松", "安静低压", "有边界不拧巴"}),
        ("patience_level", "耐心程度", {"高耐心", "耐心稳定"}),
        ("warmth_style", "聊天温度", {"有温度会接话", "理性但不冷"}),
        ("chat_texture", "聊天质感", {"稳重顺聊", "顺着聊不费劲"}),
        ("life_routine", "作息类型", {"生活规律", "生活稳定"}),
        ("relationship_execution", "现实推进方式", {"稳步推进不拖拉", "会把安排说清"}),
    ],
    "共同兴趣": [
        ("conversation_resonance", "聊天共鸣", {"能聊想法也能聊日常", "会接话也会接情绪"}),
        ("aesthetic_expression", "审美表达", {"有审美输出", "有生活审美"}),
    ],
    "有一点审美": [("aesthetic_expression", "审美表达", {"有审美输出", "有生活审美"})],
    "有情绪回应": [
        ("warmth_style", "聊天温度", {"有温度会接话", "理性但不冷"}),
        ("conversation_resonance", "聊天共鸣", {"会接话也会接情绪", "能聊想法也能聊日常"}),
    ],
    "现实推进能力": [
        ("relationship_execution", "推进方式", {"稳步推进不拖拉", "会把安排说清"}),
        ("blended_family_readiness", "现实承接", {"愿意一起商量", "安排比较成熟"}),
    ],
    "婚姻诚意": [
        ("commitment_clarity", "长期意图", {"明确奔着长期", "愿意稳定推进"}),
        ("relationship_execution", "推进方式", {"稳步推进不拖拉", "会把安排说清"}),
    ],
    "责任感": [
        ("relationship_execution", "推进方式", {"稳步推进不拖拉", "会把安排说清"}),
        ("blended_family_readiness", "现实承接", {"愿意一起商量", "安排比较成熟"}),
    ],
    "稳定踏实": [
        ("life_routine", "作息类型", {"生活规律", "生活稳定"}),
        ("consumption_attitude", "消费观", {"清醒务实", "踏实过日子"}),
    ],
}

TEXTUAL_KEYWORD_SIGNAL_RULES = {
    "情绪稳定": [
        ("personality", "性格", {"温和", "理性", "松弛", "稳重", "好相处", "有耐心", "不内耗"}),
        ("values", "价值观", {"边界清楚", "不拧巴", "不内耗", "稳定踏实"}),
    ],
    "责任感": [
        ("personality", "性格", {"有责任感", "靠谱", "有担当"}),
        ("values", "价值观", {"愿意共同经营生活", "责任感"}),
    ],
    "真诚": [
        ("personality", "性格", {"真诚", "坦诚", "不端着"}),
        ("values", "价值观", {"真诚", "不玩套路"}),
    ],
    "沟通自然": [
        ("personality", "性格", {"好相处", "不端着", "自然"}),
        ("values", "价值观", {"沟通顺畅", "不拧巴"}),
    ],
    "健康习惯": [
        ("personality", "性格", {"自律", "稳定"}),
        ("values", "价值观", {"规律运动", "作息规律"}),
    ],
}

SOFT_MUST_HAVE_KEYWORDS = {
    "情绪稳定",
    "性格稳定",
    "愿意沟通",
    "能沟通",
    "好沟通",
    "沟通顺畅",
    "边界清楚",
    "边界感",
    "不暧昧",
    "稳定工作",
    "稳定生活",
    "责任感",
    "真诚",
    "消费观正常",
    "同城稳定发展",
    "同城见面方便",
    "同城更方便",
    "长期推进明确",
    "认真长期关系",
    "愿意经营生活",
    "作息相对正常",
    "作息稳定",
    "成长背景相近",
    "少酒",
}

SOFT_MUST_HAVE_MARKERS = (
    "沟通",
    "情绪稳定",
    "性格稳定",
    "边界",
    "暧昧",
    "责任感",
    "真诚",
    "稳定工作",
    "稳定生活",
    "同城",
    "长期推进",
    "经营生活",
    "消费观",
    "作息",
    "成长背景",
    "少酒",
)

SOFT_EXCLUSION_KEYWORDS = {"拉扯", "暧昧", "内耗", "冷暴力", "控制欲", "情绪失控"}
SOFT_EXCLUSION_MARKERS = ("拉扯", "暧昧", "内耗", "冷暴力", "控制欲")

NEGATIVE_KEYWORD_STRUCTURED_FIELDS = {
    "抽烟": "smoking",
    "吸烟": "smoking",
    "喝酒": "drinking",
    "饮酒": "drinking",
}

STRICTNESS_HARD_VALUES = {"硬性", "严格", "必须", "不能放宽"}
STRICTNESS_SOFT_VALUES = {"可放宽", "可商量", "弹性"}
STRICTNESS_REFERENCE_VALUES = {"仅参考", "参考", "偏好参考"}

ACCEPTANCE_STRENGTH_STRONG_VALUES = {"明确接受", "长期接受", "真接受"}
ACCEPTANCE_STRENGTH_CAUTION_VALUES = {"谨慎接受", "了解后定", "需要磨合"}
ACCEPTANCE_STRENGTH_SURFACE_VALUES = {"短期可聊", "表面接受", "先接触再说"}


def split_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[，,、;/\n]+", str(value))
    return [str(item).strip() for item in items if str(item).strip()]


def merge_keyword_args(values: Any) -> list[str]:
    merged: list[str] = []
    for value in values or []:
        merged.extend(split_keywords(value))
    return merged


def merge_keyword_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return unique_ordered_texts(
            keyword
            for item in value
            for keyword in split_keywords(item)
        )
    return unique_ordered_texts(split_keywords(value))


def first_defined(mapping: dict[str, Any], aliases: tuple[str, ...] | list[str]) -> Any:
    for alias in aliases:
        if alias in mapping and mapping[alias] is not None:
            return mapping[alias]
    return None


def as_lower(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_whitespace(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def canonicalize_keyword(keyword: Any) -> str:
    return normalize_whitespace(keyword).replace("，", ",")


def is_soft_must_have_keyword(keyword: Any) -> bool:
    normalized = canonicalize_keyword(keyword)
    if not normalized:
        return False
    if normalized in SOFT_MUST_HAVE_KEYWORDS:
        return True
    return any(marker in normalized for marker in SOFT_MUST_HAVE_MARKERS)


def split_must_have_keywords(keywords: Any) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    for keyword in keywords or []:
        if is_soft_must_have_keyword(keyword):
            soft.append(keyword)
        else:
            hard.append(keyword)
    return unique_ordered_texts(hard), unique_ordered_texts(soft)


def is_soft_exclusion_keyword(keyword: Any) -> bool:
    normalized = canonicalize_keyword(keyword)
    if not normalized:
        return False
    if normalized in SOFT_EXCLUSION_KEYWORDS:
        return True
    return any(marker in normalized for marker in SOFT_EXCLUSION_MARKERS)


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def field_display_name(field: Any) -> str:
    return FIELD_DISPLAY_NAMES.get(str(field), str(field))


def split_evidence_segments(value: Any) -> list[str]:
    return [
        normalize_whitespace(part.strip(" ,，。;；|"))
        for part in re.split(r"[。；;\n|]+", str(value))
        if normalize_whitespace(part.strip(" ,，。;；|"))
    ]


def normalize_bool(value: Any) -> bool | None:
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


def normalize_acceptance_state(value: Any) -> str:
    if value is None or value == "":
        return "missing"
    lowered = as_lower(value)
    if lowered in ACCEPTED_VALUES:
        return "accepted"
    if lowered in REJECTED_VALUES:
        return "rejected"
    if lowered in GUARDED_NEGOTIABLE_VALUES:
        return "guarded"
    if lowered in NEGOTIABLE_VALUES:
        return "negotiable"
    if any(marker in lowered for marker in ("短期异地", "双城过渡", "落地计划", "稳定留沪", "通勤型距离")):
        return "negotiable"
    if "长期异地比较谨慎" in lowered:
        return "guarded"
    if lowered in UNKNOWN_VALUES:
        return "unknown"
    normalized = normalize_bool(value)
    if normalized is True:
        return "accepted"
    if normalized is False:
        return "rejected"
    return "unknown"


def normalize_strictness_state(value: Any) -> str:
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


def normalize_acceptance_strength(value: Any) -> str:
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


def contains_any_text(value: Any, keywords: set[str] | list[str] | tuple[str, ...]) -> bool:
    lowered = as_lower(value)
    return any(as_lower(keyword) in lowered for keyword in keywords)


def habit_requires_acceptance(value: Any) -> bool:
    return as_lower(value) in POSITIVE_HABIT_VALUES


def keyword_segment_pairs(record: dict[str, Any], keyword: Any) -> list[tuple[str, str]]:
    lowered_keyword = as_lower(keyword)
    if not lowered_keyword:
        return []

    pairs: list[tuple[str, str]] = []
    for field, label in NEGATIVE_KEYWORD_EVIDENCE_FIELDS:
        value = record.get(field)
        if not value:
            continue
        for segment in split_evidence_segments(value):
            if lowered_keyword in segment.lower():
                pairs.append((label, segment))
    if (
        not pairs
        and lowered_keyword in as_lower(record.get("combined_text", ""))
        and (
            canonicalize_keyword(keyword) in NEGATIVE_KEYWORD_STRUCTURED_FIELDS
            or is_soft_exclusion_keyword(keyword)
        )
    ):
        pairs.append(("资料文本", as_text(keyword)))
    return pairs


def segment_negates_keyword(segment: Any, keyword: Any) -> bool:
    text = normalize_whitespace(segment)
    escaped_keyword = re.escape(as_text(keyword))
    patterns = (
        rf"(?:不|别|没|无|拒绝|反感|讨厌|最怕|远离|受不了)[^，。；;,.]{{0,12}}{escaped_keyword}",
        rf"(?:不想|不要|不爱|不接受|不喜欢|不搞|不玩)[^，。；;,.]{{0,12}}{escaped_keyword}",
        rf"{escaped_keyword}[^，。；;,.]{{0,8}}(?:不行|免谈|劝退|pass)",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def negative_keyword_structured_conflict(record: dict[str, Any], keyword: Any) -> bool | None:
    field = NEGATIVE_KEYWORD_STRUCTURED_FIELDS.get(canonicalize_keyword(keyword))
    if not field:
        return None

    value = record.get(field)
    if not value:
        return None

    if field in {"smoking", "drinking"}:
        return habit_requires_acceptance(value)
    return None


def soft_exclusion_risk_flag(keyword: Any) -> str:
    return f"资料里提到“{keyword}”，需要确认具体语境"


def evaluate_exclusion_keyword(record: dict[str, Any], keyword: Any) -> dict[str, Any]:
    structured_conflict = negative_keyword_structured_conflict(record, keyword)
    if structured_conflict is True:
        return {"blocked": True, "risk_flag": None}
    if structured_conflict is False:
        return {"blocked": False, "risk_flag": None}

    matched_segments: list[tuple[str, str]] = []
    for label, segment in keyword_segment_pairs(record, keyword):
        if segment_negates_keyword(segment, keyword):
            continue
        matched_segments.append((label, segment))

    if not matched_segments:
        return {"blocked": False, "risk_flag": None}

    if is_soft_exclusion_keyword(keyword):
        return {"blocked": False, "risk_flag": soft_exclusion_risk_flag(keyword)}

    return {"blocked": True, "risk_flag": None}


__all__ = [
    "FIELD_DISPLAY_NAMES",
    "KEYWORD_EVIDENCE_FIELDS",
    "NEGATIVE_KEYWORD_EVIDENCE_FIELDS",
    "STRUCTURED_KEYWORD_SIGNAL_RULES",
    "TEXTUAL_KEYWORD_SIGNAL_RULES",
    "as_lower",
    "as_text",
    "canonicalize_keyword",
    "contains_any_text",
    "evaluate_exclusion_keyword",
    "field_display_name",
    "first_defined",
    "habit_requires_acceptance",
    "is_soft_exclusion_keyword",
    "merge_keyword_args",
    "merge_keyword_values",
    "normalize_acceptance_state",
    "normalize_acceptance_strength",
    "normalize_bool",
    "normalize_strictness_state",
    "normalize_whitespace",
    "parse_json_object",
    "split_evidence_segments",
    "split_keywords",
    "split_must_have_keywords",
]
