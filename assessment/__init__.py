"""性格测评模块"""

from __future__ import annotations

from assessment.big_five_questions import (
    BIG_FIVE_QUESTIONS,
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

__all__ = [
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
]