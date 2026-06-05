"""Triangular Love Scale (TLS-15) based assessment helpers."""

from __future__ import annotations

from typing import Any


STERNBERG_DIMENSIONS = ["intimacy", "passion", "commitment"]

STERNBERG_DIMENSION_NAMES = {
    "intimacy": "亲密",
    "passion": "激情",
    "commitment": "承诺",
}

STERNBERG_TYPE_NAMES = {
    "nonlove": "关系未成型",
    "liking": "喜欢型",
    "infatuation": "迷恋型",
    "empty_love": "空承诺型",
    "romantic_love": "浪漫爱型",
    "companionate_love": "伴侣爱型",
    "fatuous_love": "愚爱型",
    "consummate_love": "圆满爱型",
}

LIKERT_OPTIONS = [
    {"label": "1", "text": "完全不像这段关系里的我", "score": 1},
    {"label": "2", "text": "大多数时候都不是这样", "score": 2},
    {"label": "3", "text": "偶尔沾一点，但很弱", "score": 3},
    {"label": "4", "text": "有一点，但不太稳定", "score": 4},
    {"label": "5", "text": "一半一半，要看状态", "score": 5},
    {"label": "6", "text": "已经有点像我的真实感受", "score": 6},
    {"label": "7", "text": "这基本符合我现在的状态", "score": 7},
    {"label": "8", "text": "非常符合，而且持续存在", "score": 8},
    {"label": "9", "text": "几乎就是这段关系最真实的我", "score": 9},
]


def _question(index: int, dimension: str, text: str, *, source_item: str) -> dict[str, Any]:
    return {
        "index": index,
        "dimension": dimension,
        "text": text,
        "options": LIKERT_OPTIONS,
        "source_item": source_item,
    }


STERNBERG_QUESTIONS: list[dict[str, Any]] = [
    _question(0, "intimacy", "当我状态低的时候，和这个人待在一起会让我真切觉得被接住。", source_item="I have a warm relationship with my partner."),
    _question(1, "intimacy", "遇到委屈、压力或情绪低潮时，我会自然地想从 Ta 那里得到安慰和支持。", source_item="I receive considerable emotional support from my partner."),
    _question(2, "intimacy", "安排生活、设想未来或者做重要决定时，这个人在我心里都占着很重的位置。", source_item="I value my partner greatly in my life."),
    _question(3, "intimacy", "和这个人相处时，我通常能放松下来，不太需要刻意端着或伪装自己。", source_item="I have a comfortable relationship with my partner."),
    _question(4, "intimacy", "很多时候我会觉得，Ta 不是只是在听我说话，而是真的懂我在想什么。", source_item="I feel that my partner really understands me."),
    _question(5, "passion", "哪怕只是普通见面、散步或吃饭，这段关系里也会有很明显的浪漫氛围。", source_item="My relationship with my partner is very romantic."),
    _question(6, "passion", "每次看到 Ta、靠近 Ta，或者想到 Ta 时，我都能感到真实的吸引力。", source_item="I find my partner to be very personally attractive."),
    _question(7, "passion", "如果让我设想别的人来替代 Ta，我会很难想象还能得到同样的快乐和心动。", source_item="I cannot imagine another person making me as happy as my partner does."),
    _question(8, "passion", "这段关系有时会让我产生一种“就是很特别、很难解释”的心动感。", source_item="There is something almost “magical” about my relationship with my partner."),
    _question(9, "passion", "你们之间不只是相处顺，还带着明显的热烈、冲动或被点燃的感觉。", source_item="My relationship with my partner is passionate."),
    _question(10, "commitment", "即使遇到现实问题或阶段波动，我对这段关系能不能稳住这件事依然有信心。", source_item="I have confidence in the stability of my relationship with my partner."),
    _question(11, "commitment", "我会把自己对 Ta 的投入看成认真的承诺，而不只是当下上头。", source_item="I view my commitment to my partner as a solid one."),
    _question(12, "commitment", "如果有人问我“你到底爱不爱这个人”，我的答案其实是明确的。", source_item="I am certain of my love for my partner."),
    _question(13, "commitment", "在我的判断里，这段关系是有长期走下去可能性的，不只是短期相处看看。", source_item="I view my relationship with my partner as permanent."),
    _question(14, "commitment", "对这个人，我心里不只有喜欢，也会有一种想认真负责、认真对待的感觉。", source_item="I feel a sense of responsibility toward my partner."),
]

TOTAL_QUESTIONS = len(STERNBERG_QUESTIONS)
QUESTIONS_PER_DIMENSION = TOTAL_QUESTIONS // len(STERNBERG_DIMENSIONS)


def get_question(index: int) -> dict[str, Any] | None:
    if 0 <= index < TOTAL_QUESTIONS:
        return STERNBERG_QUESTIONS[index]
    return None


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    values = [
        answers[question["index"]]
        for question in STERNBERG_QUESTIONS
        if question["dimension"] == dimension and question["index"] < len(answers)
    ]
    if not values:
        return 0.0
    minimum = len(values)
    maximum = len(values) * 9
    total = sum(values)
    score = ((total - minimum) / (maximum - minimum)) * 100
    return round(max(0.0, min(100.0, score)), 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    return {dimension: calculate_dimension_score(answers, dimension) for dimension in STERNBERG_DIMENSIONS}


def get_dimension_feedback(dimension: str, score: float) -> str:
    if dimension == "intimacy":
        if score >= 70:
            return "你在“被理解、被支持、能交心”这条线上投入很高。对你来说，关系不只是心动，更是能不能真正靠近。"
        if score >= 40:
            return "你有亲密需求，但会看关系进展逐步打开。你既重视感觉，也会保留一点观察。"
        return "你在亲密层面还偏保留，或者这段关系里的“被懂、被接住”暂时还没很强。"
    if dimension == "passion":
        if score >= 70:
            return "你的心动和吸引感很鲜明。关系里如果没有明显火花，你很难把它定义成真正的喜欢。"
        if score >= 40:
            return "你有心动感，但并不是全靠高浓度激情驱动。热烈和现实你都会一起看。"
        return "你在激情维度更克制，或者这段关系的吸引力还没有强到把你卷进去。"
    if score >= 70:
        return "你对“把关系认真放进未来”这件事是有分量感的。承诺对你来说不是一句情绪话。"
    if score >= 40:
        return "你有投入和长期化的倾向，但会在现实、节奏和双方状态之间继续确认。"
    return "你在承诺这条线上目前还偏保留，可能是关系尚浅，也可能是你还没有准备好把未来绑定进去。"


def get_primary_love_type(scores: dict[str, float]) -> str:
    intimacy = float(scores.get("intimacy", 0))
    passion = float(scores.get("passion", 0))
    commitment = float(scores.get("commitment", 0))
    high_i = intimacy >= 60
    high_p = passion >= 60
    high_c = commitment >= 60
    if high_i and high_p and high_c:
        return "consummate_love"
    if high_i and high_p and not high_c:
        return "romantic_love"
    if high_i and not high_p and high_c:
        return "companionate_love"
    if not high_i and high_p and high_c:
        return "fatuous_love"
    if high_i and not high_p and not high_c:
        return "liking"
    if not high_i and high_p and not high_c:
        return "infatuation"
    if not high_i and not high_p and high_c:
        return "empty_love"
    return "nonlove"
