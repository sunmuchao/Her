"""OEJTS 适配器服务

将 OEJTS 引擎结果转换为前端期望的格式，并集成恋爱风格内容生成器。
"""

from __future__ import annotations

from typing import Any

from assessment.oejts_engine import (
    DIMENSIONS,
    DIMENSION_NAMES,
    TOTAL_QUESTIONS,
    OEJTS_QUESTIONS,
    calculate_all_scores,
    get_type_code,
    get_dimension_feedback,
)
from assessment.love_style_generator import (
    get_type_info,
    get_labels,
    get_interpretation,
    get_extreme_tags,
    get_xiaoya_message,
    calculate_love_match,
)


def get_question_payload(question_index: int, assessment_id: str) -> dict[str, Any]:
    """获取题目数据（转换为前端期望的格式）

    Args:
        question_index: 题目索引（0-47）
        assessment_id: 测评ID

    Returns:
        前端期望的问题数据格式
    """
    if question_index < 0 or question_index >= TOTAL_QUESTIONS:
        raise ValueError(f"题目索引必须在 0-{TOTAL_QUESTIONS-1} 范围内")

    question = OEJTS_QUESTIONS[question_index]

    return {
        "current_question": question_index + 1,  # 前端显示从 1 开始
        "total_questions": TOTAL_QUESTIONS,
        "question_text": question["text"],
        "options": question["options"],
        "progress": int(round(((question_index + 1) / TOTAL_QUESTIONS) * 100)),
        "assessment_id": assessment_id,
    }


def build_dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    """构建维度行数据（用于雷达图展示）

    Args:
        scores: 四个维度得分

    Returns:
        维度行数据列表
    """
    dimension_labels = {
        "ei": "社交能量",
        "sn": "关注焦点",
        "tf": "决策方式",
        "jp": "生活节奏",
    }

    dimension_traits = {
        "ei": {"high": "社交达人", "medium": "灵活切换", "low": "独处爱好者"},
        "sn": {"high": "务实派", "medium": "事实与氛围并重", "low": "氛围感派"},
        "tf": {"high": "逻辑派", "medium": "道理与感受平衡", "low": "感受派"},
        "jp": {"high": "计划派", "medium": "计划弹性兼顾", "low": "随性派"},
    }

    rows = []
    for dimension in DIMENSIONS:
        score = scores.get(dimension, 50)
        level = "high" if score >= 70 else "low" if score < 40 else "medium"

        rows.append({
            "key": dimension,
            "name": dimension_labels.get(dimension, dimension),
            "score": score,
            "level": level,
            "trait": dimension_traits.get(dimension, {}).get(level, ""),
            "feedback": get_dimension_feedback(dimension, score),
        })

    return rows


def build_result_data(answers: list[int], assessment_id: str) -> dict[str, Any]:
    """构建结果数据（转换为前端期望的格式）

    Args:
        answers: 答案列表（48个答案，每个答案为选项分数 1-5）
        assessment_id: 测评ID

    Returns:
        前端期望的结果数据格式
    """
    # 1. 使用 OEJTS 引擎计算分数和类型
    scores = calculate_all_scores(answers)
    type_code = get_type_code(scores)

    # 2. 使用恋爱风格生成器获取内容
    type_info = get_type_info(type_code)
    labels = get_labels(scores)
    interpretation = get_interpretation(scores)
    extreme_tags = get_extreme_tags(scores)
    xiaoya_message = get_xiaoya_message(type_code, scores)

    # 3. 构建维度行数据
    dimension_rows = build_dimension_rows(scores)

    # 4. 构建完整结果数据
    return {
        "type_code": type_code,
        "scores": scores,
        "dimension_rows": dimension_rows,
        "labels": labels,
        "interpretation_data": interpretation,
        "extreme_tags": extreme_tags,
        "xiaoya_message": xiaoya_message,
        "reward": "测完了解你的恋爱优势与雷区",
        "assessment_id": assessment_id,
        "engine_version": "oejts_1.2",  # 标记使用 OEJTS 1.2 引擎
    }


def build_intro_card(assessment_id: str) -> dict[str, Any]:
    """构建测评介绍卡片

    Args:
        assessment_id: 测评ID

    Returns:
        测评介绍卡片数据
    """
    return {
        "card_type": "assessment_intro",
        "assessment_type": "mbti_16",
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "MBTI 16型人格测评",
            "description": "基于 OEJTS 1.2 心理测量学规范开发\n信度 Cronbach's α = 0.84，效度复测一致性 = 0.89",
            "duration": "约 10-15 分钟",
            "reward": "测完了解你的恋爱优势与雷区",
            "total_questions": TOTAL_QUESTIONS,
        },
    }


def build_question_card(question_index: int, assessment_id: str) -> dict[str, Any]:
    """构建问题卡片

    Args:
        question_index: 题目索引
        assessment_id: 测评ID

    Returns:
        问题卡片数据
    """
    question_data = get_question_payload(question_index, assessment_id)

    return {
        "card_type": "assessment_question",
        "assessment_type": "mbti_16",
        "assessment_id": assessment_id,
        "question_data": question_data,
    }


def build_feedback_card(
    question_index: int,
    dimension: str,
    score: float,
    assessment_id: str
) -> dict[str, Any]:
    """构建维度反馈卡片（每完成一个维度后展示）

    Args:
        question_index: 当前题目索引
        dimension: 刚完成的维度
        score: 该维度的实时得分
        assessment_id: 测评ID

    Returns:
        反馈卡片数据
    """
    dimension_labels = {
        "ei": "社交能量",
        "sn": "关注焦点",
        "tf": "决策方式",
        "jp": "生活节奏",
    }

    return {
        "card_type": "assessment_feedback",
        "assessment_type": "mbti_16",
        "assessment_id": assessment_id,
        "feedback_data": {
            "dimension": dimension,
            "dimension_name": dimension_labels.get(dimension, dimension),
            "score": score,
            "feedback_text": get_dimension_feedback(dimension, score),
            "current_question": question_index + 1,
            "total_questions": TOTAL_QUESTIONS,
        },
    }


def build_result_card(answers: list[int], assessment_id: str) -> dict[str, Any]:
    """构建结果卡片

    Args:
        answers: 所有答案
        assessment_id: 测评ID

    Returns:
        结果卡片数据
    """
    result_data = build_result_data(answers, assessment_id)

    return {
        "card_type": "assessment_result",
        "assessment_type": "mbti_16",
        "assessment_id": assessment_id,
        "result_data": result_data,
    }


# 导出
__all__ = [
    "get_question_payload",
    "build_dimension_rows",
    "build_result_data",
    "build_intro_card",
    "build_question_card",
    "build_feedback_card",
    "build_result_card",
]
