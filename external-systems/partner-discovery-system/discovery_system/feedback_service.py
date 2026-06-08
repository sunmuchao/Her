"""Feedback collection and working criteria adjustment for discovery system."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

_logger = logging.getLogger(__name__)

# 反馈类型到调整策略映射
FEEDBACK_TO_CRITERIA_ADJUSTMENT = {
    # === 动态生成选项（明确信号，直接调整）===

    "location_distance": {
        "affected_field": "target_cities",
        "adjustment_type": "tighten",
        "adjustment_logic": "set_to_user_city",
        "persona_write": {
            "preferred_traits": ["同城"],
            "disliked_traits": ["异地"]
        }
    },

    "age_gap": {
        "affected_field": "target_age_min",
        "adjustment_type": "tighten",
        "adjustment_logic": "narrow_range_by_feedback",
        "persona_write": {
            "preferred_traits": ["年龄接近", "年龄相仿"]
        }
    },

    "occupation_mismatch": {
        "affected_field": "occupation_weight",
        "adjustment_type": "shift",
        "adjustment_logic": "adjust_occupation_preference",
        "persona_write": {
            "preferred_traits": ["职业匹配"],
            "disliked_traits": ["特定职业类型"]
        }
    },

    "work_life_balance": {
        "affected_field": "life_rhythm_weight",
        "adjustment_type": "shift",
        "adjustment_logic": "increase_life_weight_decrease_work_weight",
        "persona_write": {
            "preferred_traits": ["生活感强", "工作生活平衡"],
            "disliked_traits": ["高强度工作", "加班多", "太卷"]
        }
    },

    "interest_mismatch": {
        "affected_field": "interest_weight",
        "adjustment_type": "shift",
        "adjustment_logic": "adjust_interest_preference",
        "persona_write": {
            "preferred_traits": ["兴趣相投", "玩得来"]
        }
    },

    # === 通用具体选项（部分触发二级追问）===

    "personality_mismatch": {
        "affected_field": "personality_match_weight",
        "adjustment_type": "shift",
        "adjustment_logic": "increase_personality_values_weight",
        "persona_write": {},
        "suggested_action": "start_assessment",
        "need_secondary": True,
        "secondary_type": "assessment_suggestion"
    },

    "criteria_generic": {
        "affected_field": "multiple",
        "adjustment_type": "clarify",
        "adjustment_logic": "trigger_secondary_follow_up",
        "need_secondary": True,
        "secondary_type": "criteria_detail"
    },

    # === 二级追问结果（明确具体条件）===

    "criteria_age": {
        "affected_field": "target_age_min",
        "adjustment_type": "tighten",
        "adjustment_logic": "adjust_age_by_secondary_feedback",
        "persona_write": {
            "preferred_traits": ["年龄合适"]
        }
    },

    "criteria_education": {
        "affected_field": "target_education_min",
        "adjustment_type": "adjust",
        "adjustment_logic": "adjust_education_by_secondary_feedback",
        "persona_write": {
            "preferred_traits": ["学历匹配"]
        }
    },

    "criteria_income": {
        "affected_field": "target_income_min_wan",
        "adjustment_type": "adjust",
        "adjustment_logic": "adjust_income_by_secondary_feedback",
        "persona_write": {
            "preferred_traits": ["收入合适"]
        }
    },

    "criteria_city": {
        "affected_field": "target_cities",
        "adjustment_type": "tighten",
        "adjustment_logic": "adjust_city_by_secondary_feedback",
        "persona_write": {
            "preferred_traits": ["同城", "距离近"]
        }
    },

    "criteria_multiple": {
        "affected_field": "multiple",
        "adjustment_type": "clarify",
        "adjustment_logic": "trigger_whole_criteria_clarification",
        "suggested_action": "criteria_clarification",
        "need_secondary": True,
        "secondary_type": "whole_criteria"
    }
}

# 二级追问选项映射
SECONDARY_OPTIONS_MAP = {
    "外在条件不合适（年龄/学历/收入）": {
        "追问文案": "具体是哪个条件不太对？",
        "选项": [
            "年龄差距有点大",
            "学历不太匹配",
            "收入差距有点大",
            "城市太远了",
            "都不太合适",
            "不想说，直接换"
        ]
    },

    "性格气质不对（相处感觉不搭）": {
        "追问文案": "性格匹配需要深度了解。要不要做个性格测评，帮你更精准地匹配？",
        "选项": [
            "好的，做测评（MBTI/依恋）",
            "先不做了，继续换一批",
            "直接换"
        ]
    },

    "兴趣爱好不一样（玩不到一起）": {
        "追问文案": "看来你们的兴趣不太搭。要不要重新说说你的兴趣偏好？",
        "选项": [
            "好的，重新说兴趣偏好",
            "先不调整，继续看",
            "直接换"
        ]
    }
}


@dataclass
class RejectionFeedbackResult:
    feedback_id: int
    feedback_type: str
    feedback_text: str
    persona_updated: bool
    criteria_adjusted: bool


@dataclass
class CriteriaAdjustmentResult:
    adjustment_id: int
    affected_field: str
    before_value: Any
    after_value: Any


def infer_feedback_type(feedback_text: str) -> str:
    """
    从反馈文案推断反馈类型。

    Args:
        feedback_text: 用户选择的反馈文案

    Returns:
        反馈类型字符串
    """
    # 优先检查一级通用选项（这些是触发二级追问的入口）
    if "外在条件不合适（年龄/学历/收入）" in feedback_text or "外在条件不合适" in feedback_text:
        return "criteria_generic"

    if "性格气质不对" in feedback_text or "相处感觉不搭" in feedback_text:
        return "personality_mismatch"

    if "兴趣爱好不一样" in feedback_text or "玩不到一起" in feedback_text:
        return "interest_mismatch"

    # 动态生成选项的推断规则
    if "太远了" in feedback_text or "异地" in feedback_text:
        return "location_distance"

    # 注意：单独的"年龄差距有点大"可能是二级追问结果
    # 但如果有括号补充信息，则是一级动态选项
    if "年龄差距有点大" in feedback_text or "年龄" in feedback_text:
        # 判断是一级还是二级：
        # 一级动态选项通常有括号补充信息，如"年龄差距有点大（候选人 28-35，你 26）"
        # 二级追问选项通常较短，没有括号，如"年龄差距有点大"
        if "（" in feedback_text or "(" in feedback_text:  # 有括号，是一级动态选项
            return "age_gap"
        if len(feedback_text) <= 15:  # 简短的文本，更可能是二级追问结果
            return "criteria_age"
        return "age_gap"
        return "age_gap"  # 一级选项

    if "职业不太匹配" in feedback_text or "职业" in feedback_text:
        return "occupation_mismatch"

    if "太忙太卷" in feedback_text or "工作压力" in feedback_text or "生活节奏不匹配" in feedback_text:
        return "work_life_balance"

    if "兴趣不太一样" in feedback_text or "兴趣爱好不一样" in feedback_text:
        if "兴趣爱好不一样" in feedback_text:
            return "interest_mismatch"  # 一级选项
        return "interest_mismatch"

    # 通用具体选项的推断规则
    if "性格气质不对" in feedback_text:
        return "personality_mismatch"

    if "外在条件不合适" in feedback_text:
        return "criteria_generic"

    # 二级追问结果的推断规则
    if "学历不太匹配" in feedback_text:
        return "criteria_education"

    if "收入差距有点大" in feedback_text:
        return "criteria_income"

    if "城市太远了" in feedback_text and "外在条件不合适" in feedback_text:
        return "criteria_city"

    if "都不太合适" in feedback_text:
        return "criteria_multiple"

    # 默认返回generic
    _logger.warning(f"无法推断反馈类型: {feedback_text}, 使用默认类型criteria_generic")
    return "criteria_generic"


def generate_feedback_options(
    last_batch_candidates: list[dict[str, Any]],
    user_profile: dict[str, Any],
    include_secondary: bool = False,
    primary_option: Optional[str] = None,
) -> dict[str, Any]:
    """
    根据上一批候选人特征，动态生成反馈选项。

    Args:
        last_batch_candidates: 上一批候选人列表
        user_profile: 用户资料
        include_secondary: 是否包含二级追问选项
        primary_option: 如果是二级追问，指定一级选项

    Returns:
        包含选项列表和追问文案的字典
    """
    if include_secondary and primary_option:
        # 返回二级追问选项
        secondary_config = SECONDARY_OPTIONS_MAP.get(primary_option, {})
        return {
            "options": secondary_config.get("选项", []),
            "追问文案": secondary_config.get("追问文案", "")
        }

    # 1. 优先生成动态选项（基于候选人特征，信号最明确）
    dynamic_options = []

    # 地理位置问题
    if has_long_distance_candidates(last_batch_candidates):
        dynamic_options.append("太远了（都是异地）")

    # 年龄差距问题
    age_gap = calculate_age_gap(last_batch_candidates, user_profile)
    if age_gap > 5:
        candidate_age_range = get_candidate_age_range(last_batch_candidates)
        user_age = user_profile.get("age", 0)
        dynamic_options.append(f"年龄差距有点大（候选人 {candidate_age_range}，你 {user_age}）")

    # 职业类型集中
    occupation_cluster = analyze_occupation_cluster(last_batch_candidates)
    if occupation_cluster.get("is_dominant"):
        dynamic_options.append(f"职业不太匹配（{occupation_cluster['type']}偏多）")

    # 生活节奏问题
    if has_high_intensity_candidates(last_batch_candidates):
        dynamic_options.append("太忙太卷（工作压力大的感觉）")

    # 兴趣爱好差距
    interest_gap = calculate_interest_gap(last_batch_candidates, user_profile)
    if interest_gap > 0.5:  # threshold
        candidate_interests = get_candidate_interests(last_batch_candidates)
        user_interests = user_profile.get("interests", "")
        dynamic_options.append(f"兴趣不太一样（{candidate_interests} vs 你的 {user_interests}）")

    # 2. 通用具体选项（可触发二级追问）
    generic_options = [
        "性格气质不对（相处感觉不搭）",
        "外在条件不合适（年龄/学历/收入）",
        "生活节奏不匹配（工作生活状态）",
        "兴趣爱好不一样（玩不到一起）"
    ]

    # 3. 合并选项（最多6个）
    if len(dynamic_options) >= 4:
        options = dynamic_options[:5]
    else:
        needed_generic = 5 - len(dynamic_options) - 1
        options = dynamic_options + generic_options[:needed_generic]

    options.append("跳过，直接换")

    return {
        "options": options[:6],
        "追问文案": "好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。"
    }


def has_long_distance_candidates(candidates: list[dict[str, Any]]) -> bool:
    """检查是否有异地候选人。"""
    if not candidates:
        return False
    # TODO: 实现具体的异地判断逻辑
    # 根据候选人城市和用户城市判断
    return False


def calculate_age_gap(candidates: list[dict[str, Any]], user_profile: dict[str, Any]) -> int:
    """计算年龄差距。"""
    if not candidates:
        return 0
    # TODO: 实现具体的年龄差距计算逻辑
    return 0


def get_candidate_age_range(candidates: list[dict[str, Any]]) -> str:
    """获取候选人年龄范围。"""
    if not candidates:
        return ""
    # TODO: 实现具体的年龄范围提取逻辑
    ages = [c.get("age", 0) for c in candidates if c.get("age")]
    if not ages:
        return ""
    return f"{min(ages)}-{max(ages)}"


def analyze_occupation_cluster(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """分析职业类型集中度。"""
    if not candidates:
        return {"is_dominant": False, "type": ""}
    # TODO: 实现具体的职业聚类分析逻辑
    return {"is_dominant": False, "type": ""}


def has_high_intensity_candidates(candidates: list[dict[str, Any]]) -> bool:
    """检查是否有高强度工作候选人。"""
    if not candidates:
        return False
    # TODO: 实现具体的高强度判断逻辑
    return False


def calculate_interest_gap(candidates: list[dict[str, Any]], user_profile: dict[str, Any]) -> float:
    """计算兴趣爱好差距。"""
    if not candidates:
        return 0.0
    # TODO: 实现具体的兴趣差距计算逻辑
    return 0.0


def get_candidate_interests(candidates: list[dict[str, Any]]) -> str:
    """获取候选人兴趣摘要。"""
    if not candidates:
        return ""
    # TODO: 实现具体的兴趣提取逻辑
    return ""