"""性格测评模块"""

from __future__ import annotations

from assessment.mbti_questions import (
    MBTI_QUESTIONS,
    DIMENSIONS,
    DIMENSION_NAMES,
    DIMENSION_QUESTION_RANGES,
    DIMENSION_FEEDBACKS,
    get_question,
    get_dimension_for_question,
    calculate_dimension_score,
    calculate_all_scores,
    get_dimension_feedback,
)

BIG_FIVE_QUESTIONS = MBTI_QUESTIONS
from assessment.service import (
    answer_assessment,
    begin_assessment,
    get_assessment_interpretation,
    get_or_create_assessment,  # 新增：断点续传
    get_personality_traits,
    start_assessment,
)

__all__ = [
    "MBTI_QUESTIONS",
    "BIG_FIVE_QUESTIONS",
    "DIMENSIONS",
    "DIMENSION_NAMES",
    "DIMENSION_QUESTION_RANGES",
    "DIMENSION_FEEDBACKS",
    "get_question",
    "get_dimension_for_question",
    "calculate_dimension_score",
    "calculate_all_scores",
    "get_dimension_feedback",
    "start_assessment",
    "begin_assessment",
    "answer_assessment",
    "get_assessment_interpretation",
    "get_or_create_assessment",  # 新增
    "get_personality_traits",
]
