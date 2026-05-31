"""大五人格测试精简版20题数据"""

from __future__ import annotations

from typing import Any


# 维度定义
DIMENSIONS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
DIMENSION_NAMES = ["开放性", "尽责性", "外向性", "宜人性", "神经质"]

# 每个维度包含的题目索引范围
DIMENSION_QUESTION_RANGES = {
    "openness": (0, 4),       # 第1-4题
    "conscientiousness": (4, 8),   # 第5-8题
    "extraversion": (8, 12),       # 第9-12题
    "agreeableness": (12, 16),     # 第13-16题
    "neuroticism": (16, 20),       # 第17-20题
}

# 维度反馈文本模板
DIMENSION_FEEDBACKS = {
    "openness": {
        "high": "你很有好奇心，喜欢探索新事物，对新想法感兴趣",
        "medium": "你愿意尝试新事物，但也会考虑实际情况，对新想法感兴趣但也尊重传统",
        "low": "你喜欢熟悉的事物，比较传统务实，更偏好稳定和已知的事物",
    },
    "conscientiousness": {
        "high": "你做事很有计划，很靠谱自律，注重细节，有明确的目标并为之努力",
        "medium": "你做事有一定计划，但偶尔会拖延，整体上比较可靠但不是特别严格",
        "low": "你比较随性，不太喜欢严格的计划，更偏好灵活自由的工作方式",
    },
    "extraversion": {
        "high": "你很外向，喜欢社交和热闹的活动，容易和陌生人交朋友，活泼健谈",
        "medium": "你有点外向，但不排斥独处，可以根据情况调整社交和独处的时间",
        "low": "你比较内向，喜欢安静独处，不太主动社交，更喜欢深入的一对一交流",
    },
    "agreeableness": {
        "high": "你很善良，好相处，乐于助人，相信大多数人值得信任，愿意妥协避免冲突",
        "medium": "你对人友善，但有自己的底线和原则，善良但有界限",
        "low": "你比较独立，不太在意他人看法，更关注自己的目标和利益",
    },
    "neuroticism": {
        "high": "你情绪较敏感，容易焦虑紧张，情绪波动较大，面对压力时容易不安",
        "medium": "你情绪基本稳定，偶尔会有波动，面对压力时一般能保持冷静",
        "low": "你情绪很稳定，很少焦虑紧张，面对压力时能保持冷静从容",
    },
}


# 20题完整数据
BIG_FIVE_QUESTIONS: list[dict[str, Any]] = [
    # ========== 开放性（第1-4题）==========
    {
        "index": 0,
        "text": "你喜欢尝试新的餐厅、新的食物吗？",
        "options": [
            {"label": "A", "text": "非常喜欢", "score": 5},
            {"label": "B", "text": "比较喜欢", "score": 4},
            {"label": "C", "text": "无所谓", "score": 3},
            {"label": "D", "text": "不太喜欢", "score": 2},
            {"label": "E", "text": "非常不喜欢", "score": 1},
        ],
        "dimension": "openness",
        "reverse": False,
    },
    {
        "index": 1,
        "text": "你对艺术、音乐、文学感兴趣吗？",
        "options": [
            {"label": "A", "text": "非常感兴趣", "score": 5},
            {"label": "B", "text": "比较感兴趣", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太感兴趣", "score": 2},
            {"label": "E", "text": "完全不感兴趣", "score": 1},
        ],
        "dimension": "openness",
        "reverse": False,
    },
    {
        "index": 2,
        "text": "你喜欢思考抽象的问题、探索新的想法吗？",
        "options": [
            {"label": "A", "text": "非常喜欢", "score": 5},
            {"label": "B", "text": "比较喜欢", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太喜欢", "score": 2},
            {"label": "E", "text": "非常不喜欢", "score": 1},
        ],
        "dimension": "openness",
        "reverse": False,
    },
    {
        "index": 3,
        "text": "你更喜欢熟悉的事物，还是新奇的事物？",
        "options": [
            {"label": "A", "text": "更喜欢新奇", "score": 5},
            {"label": "B", "text": "都可以", "score": 4},
            {"label": "C", "text": "无所谓", "score": 3},
            {"label": "D", "text": "更喜欢熟悉", "score": 2},
            {"label": "E", "text": "只喜欢熟悉", "score": 1},
        ],
        "dimension": "openness",
        "reverse": False,
    },

    # ========== 尽责性（第5-8题）==========
    {
        "index": 4,
        "text": "你做事前会制定详细的计划吗？",
        "options": [
            {"label": "A", "text": "总是如此", "score": 5},
            {"label": "B", "text": "经常如此", "score": 4},
            {"label": "C", "text": "有时如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 2},
            {"label": "E", "text": "几乎从不", "score": 1},
        ],
        "dimension": "conscientiousness",
        "reverse": False,
    },
    {
        "index": 5,
        "text": "你能按时完成任务，不拖延吗？",
        "options": [
            {"label": "A", "text": "总是如此", "score": 5},
            {"label": "B", "text": "经常如此", "score": 4},
            {"label": "C", "text": "有时如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 2},
            {"label": "E", "text": "几乎从不", "score": 1},
        ],
        "dimension": "conscientiousness",
        "reverse": False,
    },
    {
        "index": 6,
        "text": "你注重细节，做事追求完美吗？",
        "options": [
            {"label": "A", "text": "总是如此", "score": 5},
            {"label": "B", "text": "经常如此", "score": 4},
            {"label": "C", "text": "有时如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 2},
            {"label": "E", "text": "几乎从不", "score": 1},
        ],
        "dimension": "conscientiousness",
        "reverse": False,
    },
    {
        "index": 7,
        "text": "你有明确的目标，并为之努力吗？",
        "options": [
            {"label": "A", "text": "总是如此", "score": 5},
            {"label": "B", "text": "经常如此", "score": 4},
            {"label": "C", "text": "有时如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 2},
            {"label": "E", "text": "几乎从不", "score": 1},
        ],
        "dimension": "conscientiousness",
        "reverse": False,
    },

    # ========== 外向性（第9-12题）==========
    {
        "index": 8,
        "text": "你喜欢参加热闹的聚会、社交活动吗？",
        "options": [
            {"label": "A", "text": "非常喜欢", "score": 5},
            {"label": "B", "text": "比较喜欢", "score": 4},
            {"label": "C", "text": "无所谓", "score": 3},
            {"label": "D", "text": "不太喜欢", "score": 2},
            {"label": "E", "text": "非常不喜欢", "score": 1},
        ],
        "dimension": "extraversion",
        "reverse": False,
    },
    {
        "index": 9,
        "text": "你容易和陌生人聊天、交朋友吗？",
        "options": [
            {"label": "A", "text": "非常容易", "score": 5},
            {"label": "B", "text": "比较容易", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太容易", "score": 2},
            {"label": "E", "text": "非常困难", "score": 1},
        ],
        "dimension": "extraversion",
        "reverse": False,
    },
    {
        "index": 10,
        "text": "你更喜欢独处，还是和一群人在一起？",
        "options": [
            {"label": "A", "text": "更喜欢一群人", "score": 5},
            {"label": "B", "text": "都可以", "score": 4},
            {"label": "C", "text": "无所谓", "score": 3},
            {"label": "D", "text": "更喜欢独处", "score": 2},
            {"label": "E", "text": "只喜欢独处", "score": 1},
        ],
        "dimension": "extraversion",
        "reverse": False,
    },
    {
        "index": 11,
        "text": "你是一个活泼、健谈的人吗？",
        "options": [
            {"label": "A", "text": "非常活泼", "score": 5},
            {"label": "B", "text": "比较活泼", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太活泼", "score": 2},
            {"label": "E", "text": "非常安静", "score": 1},
        ],
        "dimension": "extraversion",
        "reverse": False,
    },

    # ========== 宜人性（第13-16题）==========
    {
        "index": 12,
        "text": "你愿意帮助别人，即使对自己没好处吗？",
        "options": [
            {"label": "A", "text": "非常愿意", "score": 5},
            {"label": "B", "text": "比较愿意", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太愿意", "score": 2},
            {"label": "E", "text": "非常不愿意", "score": 1},
        ],
        "dimension": "agreeableness",
        "reverse": False,
    },
    {
        "index": 13,
        "text": "你相信大多数人都是善良的、值得信任的吗？",
        "options": [
            {"label": "A", "text": "非常相信", "score": 5},
            {"label": "B", "text": "比较相信", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太相信", "score": 2},
            {"label": "E", "text": "完全不相信", "score": 1},
        ],
        "dimension": "agreeableness",
        "reverse": False,
    },
    {
        "index": 14,
        "text": "你避免和别人发生冲突，愿意妥协吗？",
        "options": [
            {"label": "A", "text": "总是如此", "score": 5},
            {"label": "B", "text": "经常如此", "score": 4},
            {"label": "C", "text": "有时如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 2},
            {"label": "E", "text": "几乎从不", "score": 1},
        ],
        "dimension": "agreeableness",
        "reverse": False,
    },
    {
        "index": 15,
        "text": "你是一个善良、体贴的人吗？",
        "options": [
            {"label": "A", "text": "非常善良", "score": 5},
            {"label": "B", "text": "比较善良", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太善良", "score": 2},
            {"label": "E", "text": "非常冷漠", "score": 1},
        ],
        "dimension": "agreeableness",
        "reverse": False,
    },

    # ========== 神经质（第17-20题）==========
    # 注意：神经质题目反向计分（高分=情绪不稳定）
    {
        "index": 16,
        "text": "你容易感到焦虑、紧张吗？",
        "options": [
            {"label": "A", "text": "经常如此", "score": 1},  # 反向计分
            {"label": "B", "text": "有时如此", "score": 2},
            {"label": "C", "text": "偶尔如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 4},
            {"label": "E", "text": "几乎从不", "score": 5},
        ],
        "dimension": "neuroticism",
        "reverse": True,  # 标记为反向计分
    },
    {
        "index": 17,
        "text": "你情绪波动大吗？（容易生气、伤心、情绪化）",
        "options": [
            {"label": "A", "text": "经常如此", "score": 1},  # 反向计分
            {"label": "B", "text": "有时如此", "score": 2},
            {"label": "C", "text": "偶尔如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 4},
            {"label": "E", "text": "几乎从不", "score": 5},
        ],
        "dimension": "neuroticism",
        "reverse": True,
    },
    {
        "index": 18,
        "text": "你容易感到沮丧、失落吗？",
        "options": [
            {"label": "A", "text": "经常如此", "score": 1},  # 反向计分
            {"label": "B", "text": "有时如此", "score": 2},
            {"label": "C", "text": "偶尔如此", "score": 3},
            {"label": "D", "text": "很少如此", "score": 4},
            {"label": "E", "text": "几乎从不", "score": 5},
        ],
        "dimension": "neuroticism",
        "reverse": True,
    },
    {
        "index": 19,
        "text": "你面对压力时能保持冷静吗？",
        "options": [
            {"label": "A", "text": "非常冷静", "score": 5},
            {"label": "B", "text": "比较冷静", "score": 4},
            {"label": "C", "text": "一般", "score": 3},
            {"label": "D", "text": "不太冷静", "score": 2},
            {"label": "E", "text": "非常焦虑", "score": 1},
        ],
        "dimension": "neuroticism",
        "reverse": False,  # 这题正向计分
    },
]


def get_question(index: int) -> dict[str, Any] | None:
    """获取指定索引的题目"""
    if 0 <= index < len(BIG_FIVE_QUESTIONS):
        return BIG_FIVE_QUESTIONS[index]
    return None


def get_dimension_for_question(index: int) -> str | None:
    """获取题目所属维度"""
    question = get_question(index)
    if question:
        return question.get("dimension")
    return None


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    """计算指定维度的得分

    Args:
        answers: 答案分数列表（长度为20，每个值为1-5）
        dimension: 维度名称

    Returns:
        得分（0-100）
    """
    start, end = DIMENSION_QUESTION_RANGES.get(dimension, (0, 0))
    if start == end:
        return 0.0

    dimension_answers = answers[start:end]
    if not dimension_answers:
        return 0.0

    # 计算总分
    total = sum(dimension_answers)

    # 转换为0-100分
    # 4题总分范围：4~20分
    score = (total - 4) / 16 * 100

    return round(score, 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    """计算所有维度的得分

    Args:
        answers: 答案分数列表（长度为20）

    Returns:
        各维度得分字典
    """
    scores = {}
    for dimension in DIMENSIONS:
        scores[dimension] = calculate_dimension_score(answers, dimension)
    return scores


def get_dimension_feedback(dimension: str, score: float) -> str:
    """获取维度反馈文本

    Args:
        dimension: 维度名称
        score: 得分（0-100）

    Returns:
        反馈文本
    """
    feedbacks = DIMENSION_FEEDBACKS.get(dimension, {})

    if score >= 70:
        return feedbacks.get("high", "")
    elif score >= 40:
        return feedbacks.get("medium", "")
    else:
        return feedbacks.get("low", "")