"""性格测评模块"""

from __future__ import annotations

# 改用 OEJTS 引擎（权威开源项目）
from assessment.oejts_engine import (
    OEJTS_QUESTIONS,
    DIMENSIONS,
    DIMENSION_NAMES,
    DIMENSION_QUESTION_COUNT,
    TOTAL_QUESTIONS,
    get_question,
    calculate_dimension_score,
    calculate_all_scores,
    get_dimension_feedback,
)

MBTI_QUESTIONS = OEJTS_QUESTIONS
BIG_FIVE_QUESTIONS = OEJTS_QUESTIONS

from assessment.service import (
    answer_assessment,
    begin_assessment,
    get_assessment_interpretation,
    get_or_create_assessment,
    get_personality_traits,
    start_assessment,
)

__all__ = [
    "MBTI_QUESTIONS",
    "OEJTS_QUESTIONS",
    "BIG_FIVE_QUESTIONS",
    "DIMENSIONS",
    "DIMENSION_NAMES",
    "DIMENSION_QUESTION_COUNT",
    "TOTAL_QUESTIONS",
    "get_question",
    "calculate_dimension_score",
    "calculate_all_scores",
    "get_dimension_feedback",
    "start_assessment",
    "begin_assessment",
    "answer_assessment",
    "get_assessment_interpretation",
    "get_or_create_assessment",
    "get_personality_traits",
]