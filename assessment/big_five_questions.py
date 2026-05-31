"""兼容层：旧的大五人格题库模块已切换为 MBTI 题库导出。"""

from __future__ import annotations

from assessment.mbti_questions import *  # noqa: F401,F403

BIG_FIVE_QUESTIONS = MBTI_QUESTIONS
