"""MBTI 16 型人格测评题库（20题精简版）"""

from __future__ import annotations

from typing import Any

DIMENSIONS = ["ei", "sn", "tf", "jp"]
DIMENSION_NAMES = {
    "ei": "外向 / 内向",
    "sn": "实感 / 直觉",
    "tf": "思考 / 情感",
    "jp": "判断 / 知觉",
}

DIMENSION_QUESTION_RANGES = {
    "ei": (0, 5),
    "sn": (5, 10),
    "tf": (10, 15),
    "jp": (15, 20),
}

DIMENSION_FEEDBACKS = {
    "ei": {
        "high": "你更偏外向，倾向从互动和表达里获取能量。",
        "medium": "你能在独处和社交之间切换，比较灵活。",
        "low": "你更偏内向，通常喜欢安静和深入交流。",
    },
    "sn": {
        "high": "你更看重现实细节和可落地的信息。",
        "medium": "你会在具体事实和灵感想法之间平衡。",
        "low": "你更偏直觉，习惯先看趋势和可能性。",
    },
    "tf": {
        "high": "你更习惯用逻辑和标准来做判断。",
        "medium": "你会兼顾逻辑和感受，判断比较平衡。",
        "low": "你更看重关系感受和人的处境。",
    },
    "jp": {
        "high": "你更偏计划和确定性，喜欢把事情安排清楚。",
        "medium": "你能在计划和弹性之间保持平衡。",
        "low": "你更偏灵活开放，喜欢留有余地。",
    },
}

MBTI_QUESTIONS: list[dict[str, Any]] = [
    {
        "index": 0,
        "text": "你更喜欢和别人一起活动，而不是长时间独处吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "ei",
        "reverse": False,
    },
    {
        "index": 1,
        "text": "你通常会主动开口和陌生人聊天吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "ei",
        "reverse": False,
    },
    {
        "index": 2,
        "text": "社交结束后，你通常会觉得更有精神吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "ei",
        "reverse": False,
    },
    {
        "index": 3,
        "text": "你更愿意把想法说出来，而不是先自己想很久吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "ei",
        "reverse": False,
    },
    {
        "index": 4,
        "text": "你会自然带动聊天气氛吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "ei",
        "reverse": False,
    },
    {
        "index": 5,
        "text": "你更关注眼前的事实和细节，而不是抽象可能性吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "sn",
        "reverse": False,
    },
    {
        "index": 6,
        "text": "你更喜欢把事情落到具体步骤上吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "sn",
        "reverse": False,
    },
    {
        "index": 7,
        "text": "你更相信自己熟悉的经验，而不是新点子吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "sn",
        "reverse": False,
    },
    {
        "index": 8,
        "text": "你做决定时，更看重具体证据和事实吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "sn",
        "reverse": False,
    },
    {
        "index": 9,
        "text": "你更容易从细节里判断一个人的状态吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "sn",
        "reverse": False,
    },
    {
        "index": 10,
        "text": "你做决定时更依赖逻辑判断，而不是情绪感受吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "tf",
        "reverse": False,
    },
    {
        "index": 11,
        "text": "你会优先讲道理，而不是先照顾气氛吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "tf",
        "reverse": False,
    },
    {
        "index": 12,
        "text": "你更习惯直接指出问题，而不是顾及对方感受吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "tf",
        "reverse": False,
    },
    {
        "index": 13,
        "text": "别人求助时，你会先看事情是否合理，再决定是否帮忙吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "tf",
        "reverse": False,
    },
    {
        "index": 14,
        "text": "面对分歧时，你更在意谁的观点更合理，而不是谁更受伤吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "tf",
        "reverse": False,
    },
    {
        "index": 15,
        "text": "你喜欢提前规划好行程和安排吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "jp",
        "reverse": False,
    },
    {
        "index": 16,
        "text": "你更喜欢把事情尽快定下来吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "jp",
        "reverse": False,
    },
    {
        "index": 17,
        "text": "临时变化会让你明显不舒服吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "jp",
        "reverse": False,
    },
    {
        "index": 18,
        "text": "你通常会按计划完成事情，而不是边做边看吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 5},
            {"label": "B", "text": "比较符合", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 2},
            {"label": "E", "text": "完全不符合", "score": 1},
        ],
        "dimension": "jp",
        "reverse": False,
    },
    {
        "index": 19,
        "text": "你会因为不确定而反复拖延决定吗？",
        "options": [
            {"label": "A", "text": "非常符合", "score": 1},
            {"label": "B", "text": "比较符合", "score": 2},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太符合", "score": 4},
            {"label": "E", "text": "完全不符合", "score": 5},
        ],
        "dimension": "jp",
        "reverse": True,
    },
]


def get_question(index: int) -> dict[str, Any] | None:
    if 0 <= index < len(MBTI_QUESTIONS):
        return MBTI_QUESTIONS[index]
    return None


def get_dimension_for_question(index: int) -> str | None:
    question = get_question(index)
    if question:
        return str(question.get("dimension") or "")
    return None


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    start, end = DIMENSION_QUESTION_RANGES.get(dimension, (0, 0))
    if start == end:
        return 0.0
    dimension_answers = answers[start:end]
    if not dimension_answers:
        return 0.0
    total = sum(dimension_answers)
    score = (total - 5) / 20 * 100
    return round(score, 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    return {dimension: calculate_dimension_score(answers, dimension) for dimension in DIMENSIONS}


def get_dimension_feedback(dimension: str, score: float) -> str:
    feedbacks = DIMENSION_FEEDBACKS.get(dimension, {})
    if score >= 70:
        return str(feedbacks.get("high", ""))
    if score >= 40:
        return str(feedbacks.get("medium", ""))
    return str(feedbacks.get("low", ""))
