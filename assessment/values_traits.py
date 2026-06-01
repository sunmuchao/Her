"""
价值观拍卖会特质定义

定义12个恋爱价值观特质，以及价值观类型分类算法。
"""

from __future__ import annotations

from typing import Any


# ============================================================
# 12个价值观特质定义
# ============================================================

VALUES_AUCTION_TRAITS: list[dict[str, Any]] = [
    {
        "trait_id": "loyalty",
        "trait_name": "专一忠诚",
        "trait_name_en": "Loyalty",
        "description": "对伴侣的忠诚度和专一性",
        "detail": "不出轨、不给异性暧昧机会、对感情认真负责",
    },
    {
        "trait_id": "wealth",
        "trait_name": "经济条件",
        "trait_name_en": "Wealth",
        "description": "对方的经济能力和财务状况",
        "detail": "有稳定收入、一定积蓄、能提供物质保障",
    },
    {
        "trait_id": "looks",
        "trait_name": "外貌颜值",
        "trait_name_en": "Looks",
        "description": "外貌吸引力、身材气质",
        "detail": "长相好看、身材好、穿衣有品味",
    },
    {
        "trait_id": "humor",
        "trait_name": "幽默风趣",
        "trait_name_en": "Humor",
        "description": "能否带来欢乐、调节气氛",
        "detail": "能逗自己开心、有趣的灵魂、会讲段子",
    },
    {
        "trait_id": "education",
        "trait_name": "学历背景",
        "trait_name_en": "Education",
        "description": "教育背景、知识广度",
        "detail": "有较高学历、有见识、能深度交流",
    },
    {
        "trait_id": "ambition",
        "trait_name": "上进心",
        "trait_name_en": "Ambition",
        "description": "事业心、自我提升意愿",
        "detail": "有目标、愿意努力、不断成长",
    },
    {
        "trait_id": "gentle",
        "trait_name": "温柔体贴",
        "trait_name_en": "Gentleness",
        "description": "情感关怀、细心程度",
        "detail": "善解人意、会照顾人、情绪稳定",
    },
    {
        "trait_id": "smart",
        "trait_name": "聪明智慧",
        "trait_name_en": "Intelligence",
        "description": "智力水平、解决问题的能力",
        "detail": "聪明、有智慧、能解决复杂问题",
    },
    {
        "trait_id": "family",
        "trait_name": "家庭背景",
        "trait_name_en": "FamilyBackground",
        "description": "家庭条件和父母相处",
        "detail": "家庭条件好、父母好相处、家庭氛围和谐",
    },
    {
        "trait_id": "height",
        "trait_name": "身高条件",
        "trait_name_en": "Height",
        "description": "对方的身高条件",
        "detail": "身高达到自己标准、身材比例好",
    },
    {
        "trait_id": "values_match",
        "trait_name": "三观一致",
        "trait_name_en": "ValuesAlignment",
        "description": "价值观、人生观的契合度",
        "detail": "世界观、人生观、价值观一致、思想契合",
    },
    {
        "trait_id": "companionship",
        "trait_name": "陪伴时间",
        "trait_name_en": "Companionship",
        "description": "愿意投入的陪伴时间",
        "detail": "愿意花时间陪伴、不总是忙碌、有时间相处",
    },
]


# 特质ID到名称的映射
TRAIT_ID_TO_NAME: dict[str, str] = {
    t["trait_id"]: t["trait_name"] for t in VALUES_AUCTION_TRAITS
}


# ============================================================
# 价值观类型分类
# ============================================================

VALUE_TYPE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "忠诚至上型": {
        "condition": "loyalty >= 4",
        "description": "你最看重忠诚，背叛是你绝对不能接受的",
        "love_style": "你对感情非常认真，一旦认定就不会轻易放弃",
        "match_suggestion": "建议找同样看重'专一'的人",
        "caution": "避开给'好看'出高价的人（可能更看重外在）",
    },
    "务实型": {
        "condition": "wealth >= 3 or family >= 3",
        "description": "你看重物质基础和家庭匹配",
        "love_style": "你比较务实，认为经济基础决定上层建筑",
        "match_suggestion": "建议找同样务实的人",
        "caution": "可能与'陪伴型'产生冲突（赚钱vs陪人）",
    },
    "颜值优先型": {
        "condition": "looks >= 3 or height >= 3",
        "description": "你看重外在吸引力",
        "love_style": "你很在意对方的外在形象",
        "match_suggestion": "建议找外在条件好的人",
        "caution": "外在会变化，需要其他维度的支撑",
    },
    "情绪价值型": {
        "condition": "humor >= 3 or gentle >= 3",
        "description": "你看重情绪价值和情感关怀",
        "love_style": "你希望对方能让你开心、被照顾",
        "match_suggestion": "建议找有趣或温柔的人",
        "caution": "可能与'逻辑派'产生冲突",
    },
    "成长型": {
        "condition": "ambition >= 3 or education >= 3",
        "description": "你看重成长潜力和知识层次",
        "love_style": "你希望对方有上进心、能一起成长",
        "match_suggestion": "建议找有成长潜力的人",
        "caution": "可能与'安逸型'产生冲突",
    },
    "陪伴型": {
        "condition": "companionship >= 3 or values_match >= 3",
        "description": "你看重陪伴时间和三观契合",
        "love_style": "你希望对方愿意花时间陪你",
        "match_suggestion": "建议找愿意花时间的人",
        "caution": "可能与'事业型'产生冲突",
    },
    "均衡型": {
        "condition": "top_chips <= 3",
        "description": "你的价值观分布均匀，不极端",
        "love_style": "你比较灵活，能适应不同类型的人",
        "match_suggestion": "匹配范围广，不强制要求",
        "caution": "可能不够明确，需要多了解自己",
    },
    "综合型": {
        "condition": "其他情况",
        "description": "你的价值观有多个重点",
        "love_style": "你看重多个维度",
        "match_suggestion": "找在多个维度契合的人",
        "caution": "可能标准较高，需要适当取舍",
    },
}


def classify_value_type(bids: list[dict[str, Any]]) -> str:
    """
    根据竞拍结果分类价值观类型

    Args:
        bids: 排序后的竞拍结果列表，每个元素包含 trait_id, chips 等

    Returns:
        价值观类型名称，如 '忠诚至上型'、'务实型' 等
    """
    if not bids:
        return "综合型"

    # 获取筹码分配映射
    chips_map: dict[str, int] = {}
    for bid in bids:
        chips_map[bid["trait_id"]] = bid["chips"]

    # 获取最高出价的特质
    top_trait = bids[0]["trait_id"]
    top_chips = bids[0]["chips"]

    # 分类判断（按优先级）
    if top_trait == "loyalty" and top_chips >= 4:
        return "忠诚至上型"
    elif chips_map.get("wealth", 0) >= 3 or chips_map.get("family", 0) >= 3:
        return "务实型"
    elif chips_map.get("looks", 0) >= 3 or chips_map.get("height", 0) >= 3:
        return "颜值优先型"
    elif chips_map.get("humor", 0) >= 3 or chips_map.get("gentle", 0) >= 3:
        return "情绪价值型"
    elif chips_map.get("ambition", 0) >= 3 or chips_map.get("education", 0) >= 3:
        return "成长型"
    elif chips_map.get("companionship", 0) >= 3 or chips_map.get("values_match", 0) >= 3:
        return "陪伴型"
    elif top_chips <= 3:
        return "均衡型"
    else:
        return "综合型"


def get_value_type_info(value_type: str) -> dict[str, Any]:
    """
    获取价值观类型的详细信息

    Args:
        value_type: 价值观类型名称

    Returns:
        类型详细信息，包含 description, love_style, match_suggestion, caution
    """
    return VALUE_TYPE_DEFINITIONS.get(value_type, VALUE_TYPE_DEFINITIONS["综合型"])


# ============================================================
# 简短解读生成
# ============================================================

TRAIT_INTERPRETATIONS: dict[str, dict[str, str]] = {
    "loyalty": {
        "high": "你最看重忠诚，背叛是你绝对不能接受的",
        "medium": "你比较看重忠诚，希望对方对感情认真",
        "low": "你对忠诚的要求不高，可能更看重其他",
    },
    "wealth": {
        "high": "你看重经济基础，希望对方有物质保障",
        "medium": "你有一定的物质要求，但不是第一位",
        "low": "你对经济条件不太在意",
    },
    "looks": {
        "high": "你看重外貌，希望对方长相好看",
        "medium": "你对外貌有一定要求",
        "low": "你对外貌不太在意",
    },
    "humor": {
        "high": "你看重情绪价值，希望对方有趣",
        "medium": "你希望对方能带来一些快乐",
        "low": "你对幽默不太在意",
    },
    "education": {
        "high": "你看重学历和见识，希望深度交流",
        "medium": "你对学历有一定要求",
        "low": "你对学历不太在意",
    },
    "ambition": {
        "high": "你看重上进心，希望对方有目标",
        "medium": "你希望对方有一定上进心",
        "low": "你对上进心不太在意",
    },
    "gentle": {
        "high": "你看重温柔体贴，希望被照顾",
        "medium": "你希望对方能体贴一些",
        "low": "你对温柔不太在意",
    },
    "smart": {
        "high": "你看重聪明智慧，希望智力匹配",
        "medium": "你希望对方有一定聪明度",
        "low": "你对聪明不太在意",
    },
    "family": {
        "high": "你看重家庭背景，希望家庭匹配",
        "medium": "你对家庭有一定要求",
        "low": "你对家庭背景不太在意",
    },
    "height": {
        "high": "你看重身高，有明确标准",
        "medium": "你对身高有一定要求",
        "low": "你对身高不太在意",
    },
    "values_match": {
        "high": "你看重三观一致，希望思想契合",
        "medium": "你希望三观有一定契合",
        "low": "你对三观不太在意",
    },
    "companionship": {
        "high": "你看重陪伴时间，希望对方花时间陪你",
        "medium": "你希望对方有一定陪伴",
        "low": "你对陪伴时间不太在意",
    },
}


def get_trait_interpretation(trait_id: str, chips: int) -> str:
    """
    根据特质和筹码数生成简短解读

    Args:
        trait_id: 特质ID
        chips: 筹码数

    Returns:
        简短解读文本
    """
    trait_interp = TRAIT_INTERPRETATIONS.get(trait_id, {})

    if chips >= 4:
        return trait_interp.get("high", f"你看重{TRAIT_ID_TO_NAME.get(trait_id, trait_id)}")
    elif chips >= 2:
        return trait_interp.get("medium", f"你对{TRAIT_ID_TO_NAME.get(trait_id, trait_id)}有一定要求")
    else:
        return trait_interp.get("low", f"你对{TRAIT_ID_TO_NAME.get(trait_id, trait_id)}不太在意")


# ============================================================
# 配置常量
# ============================================================

TOTAL_CHIPS = 10  # 总筹码数
MIN_BID = 0       # 最小出价
MAX_BID = 10      # 最大出价（单特质）
TRAIT_COUNT = 12  # 特质数量

ASSESSMENT_TYPE_VALUES_AUCTION = "values_auction"
VALUES_AUCTION_SESSION_FIELD = "values_auction.session"
VALUES_AUCTION_RESULT_FIELD = "values_auction.result"
VALUES_AUCTION_INTERPRETATION_FIELD = "values_auction.interpretation"
VALUES_AUCTION_DUAL_SESSION_FIELD = "values_auction.dual_session"