"""Heuristic personality-summary builder for seeded virtual personas."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_csv(value: Any) -> list[str]:
    return [item.strip() for item in _clean(value).split(",") if item.strip()]


def _first_nonempty(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _clamp(value: float, low: int = 5, high: int = 95) -> float:
    return float(max(low, min(high, round(value))))


def _jitter(identity: str, dimension: str, spread: int = 6) -> int:
    """
    使用 SHA-256 生成确定性抖动值（替代不安全的 MD5）。

    安全修复：MD5 存在碰撞风险，升级为 SHA-256 用于确定性生成。
    虽然 MD5 在此场景不涉及安全认证，但为符合最佳实践，升级为更安全的算法。
    """
    digest = hashlib.sha256(f"{identity}:{dimension}".encode("utf-8")).digest()
    return int(digest[0] % (spread * 2 + 1)) - spread


def _score(base: float, identity: str, dimension: str, deltas: list[float]) -> float:
    return _clamp(base + sum(deltas) + _jitter(identity, dimension))


def _mbti_type(scores: Mapping[str, float]) -> str:
    return "".join(
        [
            "E" if float(scores.get("ei", 50)) >= 50 else "I",
            "S" if float(scores.get("sn", 50)) >= 50 else "N",
            "T" if float(scores.get("tf", 50)) >= 50 else "F",
            "J" if float(scores.get("jp", 50)) >= 50 else "P",
        ]
    )


def _attachment_type(anxiety: float, avoidance: float) -> str:
    anxious = anxiety >= 50
    avoidant = avoidance >= 50
    if anxious and avoidant:
        return "fearful"
    if anxious:
        return "anxious"
    if avoidant:
        return "avoidant"
    return "secure"


def _sternberg_type(intimacy: float, passion: float, commitment: float) -> str:
    dimensions = {
        "intimacy": intimacy,
        "passion": passion,
        "commitment": commitment,
    }
    ordered = sorted(dimensions.items(), key=lambda item: item[1], reverse=True)
    top_keys = [item[0] for item in ordered if item[1] >= 60]
    if set(top_keys) == {"intimacy", "commitment", "passion"}:
        return "consummate"
    if set(top_keys) == {"intimacy", "commitment"}:
        return "companionate"
    if set(top_keys) == {"passion", "commitment"}:
        return "fatuous"
    if set(top_keys) == {"intimacy", "passion"}:
        return "romantic"
    if ordered[0][0] == "commitment":
        return "empty"
    if ordered[0][0] == "passion":
        return "infatuation"
    return "liking"


def _count_hits(items: set[str], mapping: Mapping[str, tuple[str, ...]]) -> dict[str, int]:
    counts = {key: 0 for key in mapping}
    for key, tags in mapping.items():
        counts[key] = sum(1 for tag in tags if tag in items)
    return counts


def build_synthetic_personality_traits(record: Mapping[str, Any], *, identity: str | None = None) -> dict[str, Any]:
    user_identity = identity or _clean(_first_nonempty(record, "user_key", "profile_id", "id")) or "synthetic"
    completed_at = _clean(_first_nonempty(record, "updated_at", "created_at")) or "2026-06-05 00:00:00"

    personality_tags = set(
        _split_csv(_first_nonempty(record, "personality", "preferred_traits"))
        + _split_csv(record.get("public_personality"))
        + _split_csv(record.get("self_expression_style"))
    )
    values_tags = set(_split_csv(_first_nonempty(record, "values", "public_values")))
    lifestyle_tags = set(
        _split_csv(_first_nonempty(record, "lifestyle", "life_routine"))
        + _split_csv(record.get("self_life_rhythm"))
        + _split_csv(record.get("self_work_pattern"))
    )
    hobby_tags = set(_split_csv(record.get("hobbies")))
    all_tags = personality_tags | values_tags | lifestyle_tags | hobby_tags

    relationship_goal = _clean(_first_nonempty(record, "self_relationship_goal", "relationship_goal"))
    marital_status = _clean(_first_nonempty(record, "self_marital_status", "marital_status"))
    want_children = _clean(_first_nonempty(record, "target_want_children", "want_children"))
    age = int(_first_nonempty(record, "self_age", "age") or 28)
    job = _clean(_first_nonempty(record, "self_job", "job"))

    extroversion_hits = _count_hits(
        all_tags,
        {
            "plus": ("开朗", "爱笑", "善沟通", "看展", "旅行", "桌游"),
            "minus": ("慢热", "安静", "独立", "偏宅", "阅读"),
        },
    )
    sensing_hits = _count_hits(
        all_tags,
        {
            "plus": ("务实", "生活规律", "规律作息", "干净整洁", "养生", "喜欢做饭", "爱逛菜场"),
            "minus": ("摄影", "画画", "看展", "旅行", "咖啡", "新媒体运营", "品牌策划"),
        },
    )
    thinking_hits = _count_hits(
        all_tags,
        {
            "plus": ("理性", "有主见", "务实", "边界感强", "后端工程师", "法务", "审计", "财务"),
            "minus": ("温和", "细腻", "真诚", "顾家", "有耐心"),
        },
    )
    judging_hits = _count_hits(
        all_tags,
        {
            "plus": ("生活规律", "规律作息", "不熬夜", "干净整洁", "养生", "有责任感", "结婚导向", "认真恋爱"),
            "minus": ("松弛", "先接触看看", "偶尔短途旅行", "偏宅"),
        },
    )

    mbti_scores = {
        "ei": _score(50, user_identity, "mbti_ei", [18 * extroversion_hits["plus"], -14 * extroversion_hits["minus"]]),
        "sn": _score(52, user_identity, "mbti_sn", [14 * sensing_hits["plus"], -12 * sensing_hits["minus"]]),
        "tf": _score(50, user_identity, "mbti_tf", [15 * thinking_hits["plus"], -12 * thinking_hits["minus"]]),
        "jp": _score(
            50,
            user_identity,
            "mbti_jp",
            [
                12 * judging_hits["plus"],
                -12 * judging_hits["minus"],
                8 if relationship_goal == "结婚导向" else 0,
                -8 if relationship_goal == "先接触看看" else 0,
            ],
        ),
    }
    mbti = {
        "assessment_id": f"synthetic_mbti_{user_identity}",
        "type_code": _mbti_type(mbti_scores),
        "scores": mbti_scores,
        "completed_at": completed_at,
    }

    attachment_anxiety = _score(
        42,
        user_identity,
        "attachment_anxiety",
        [
            -16 if "情绪稳定" in all_tags else 0,
            -10 if "松弛" in all_tags else 0,
            -8 if "独立" in all_tags else 0,
            8 if "细腻" in all_tags else 0,
            5 if relationship_goal == "结婚导向" else 0,
            6 if marital_status.startswith("离异") else 0,
        ],
    )
    attachment_avoidance = _score(
        44,
        user_identity,
        "attachment_avoidance",
        [
            16 if "边界感强" in all_tags else 0,
            10 if "独立" in all_tags else 0,
            10 if "慢热" in all_tags else 0,
            8 if "安静" in all_tags else 0,
            10 if relationship_goal == "先接触看看" else 0,
            -10 if "善沟通" in all_tags else 0,
            -8 if "顾家" in all_tags else 0,
            -8 if relationship_goal == "结婚导向" else 0,
        ],
    )
    attachment = {
        "assessment_id": f"synthetic_attachment_{user_identity}",
        "type_code": _attachment_type(attachment_anxiety, attachment_avoidance),
        "anxiety": attachment_anxiety,
        "avoidance": attachment_avoidance,
        "completed_at": completed_at,
    }

    openness = _score(
        48,
        user_identity,
        "big_five_openness",
        [
            10 if hobby_tags & {"摄影", "旅行", "看展", "画画", "电影"} else 0,
            8 if all_tags & {"咖啡", "偶尔短途旅行", "新媒体运营", "品牌策划", "设计师", "UI设计"} else 0,
            -6 if all_tags & {"务实", "爱逛菜场"} else 0,
        ],
    )
    conscientiousness = _score(
        54,
        user_identity,
        "big_five_conscientiousness",
        [
            12 if all_tags & {"生活规律", "规律作息", "干净整洁", "养生"} else 0,
            10 if all_tags & {"有责任感", "务实", "顾家"} else 0,
            8 if job in {"公务员", "事业单位职员", "教师", "财务", "会计", "审计"} else 0,
        ],
    )
    extraversion = _score(
        46,
        user_identity,
        "big_five_extraversion",
        [
            14 if all_tags & {"开朗", "爱笑", "善沟通"} else 0,
            8 if hobby_tags & {"桌游", "羽毛球", "游泳"} else 0,
            -10 if all_tags & {"安静", "慢热", "偏宅"} else 0,
        ],
    )
    agreeableness = _score(
        55,
        user_identity,
        "big_five_agreeableness",
        [
            14 if all_tags & {"温和", "真诚", "有耐心", "好相处"} else 0,
            10 if all_tags & {"顾家", "重视家庭", "愿意共同经营生活"} else 0,
            -8 if all_tags & {"边界感强", "有主见"} else 0,
        ],
    )
    neuroticism = _score(
        42,
        user_identity,
        "big_five_neuroticism",
        [
            -20 if "情绪稳定" in all_tags else 0,
            -10 if "松弛" in all_tags else 0,
            8 if "细腻" in all_tags else 0,
            6 if marital_status.startswith("离异") else 0,
        ],
    )
    big_five = {
        "assessment_id": f"synthetic_big_five_{user_identity}",
        "scores": {
            "openness": openness,
            "conscientiousness": conscientiousness,
            "extraversion": extraversion,
            "agreeableness": agreeableness,
            "neuroticism": neuroticism,
        },
        "completed_at": completed_at,
    }

    intimacy = _score(
        50,
        user_identity,
        "sternberg_intimacy",
        [
            10 if all_tags & {"真诚", "善沟通", "温和", "有耐心"} else 0,
            8 if all_tags & {"好相处", "顾家"} else 0,
            -6 if "边界感强" in all_tags else 0,
        ],
    )
    passion = _score(
        48,
        user_identity,
        "sternberg_passion",
        [
            8 if all_tags & {"开朗", "爱笑", "爱运动", "旅行"} else 0,
            6 if age <= 27 else 0,
            -6 if "慢热" in all_tags else 0,
        ],
    )
    commitment = _score(
        52,
        user_identity,
        "sternberg_commitment",
        [
            16 if relationship_goal == "结婚导向" else 0,
            10 if relationship_goal == "认真恋爱" else 0,
            10 if want_children == "想要" else 0,
            10 if all_tags & {"有责任感", "顾家", "重视家庭", "对感情认真"} else 0,
            -10 if relationship_goal == "先接触看看" else 0,
        ],
    )
    sternberg = {
        "assessment_id": f"synthetic_sternberg_{user_identity}",
        "type_code": _sternberg_type(intimacy, passion, commitment),
        "scores": {
            "intimacy": intimacy,
            "passion": passion,
            "commitment": commitment,
        },
        "completed_at": completed_at,
    }

    value_groups = {
        "稳定经营": ("消费观正常", "务实", "稳定踏实", "生活规律", "规律作息", "结婚导向", "认真恋爱"),
        "家庭责任": ("重视家庭", "愿意共同经营生活", "顾家", "想要"),
        "真诚沟通": ("真诚", "善沟通", "能沟通", "有耐心", "温和"),
        "独立空间": ("边界感强", "尊重彼此空间", "独立", "慢热", "安静"),
        "成长探索": ("乐观", "有主见", "旅行", "看展", "摄影", "画画"),
        "生活质感": ("喜欢做饭", "咖啡", "干净整洁", "养生", "周末会出门走走"),
    }
    group_scores = {key: 0 for key in value_groups}
    for key, tags in value_groups.items():
        group_scores[key] = sum(1 for tag in tags if tag in all_tags)
    if want_children == "想要":
        group_scores["家庭责任"] += 1
    if relationship_goal == "结婚导向":
        group_scores["稳定经营"] += 1
    if relationship_goal == "先接触看看":
        group_scores["独立空间"] += 1

    ordered_groups = [key for key, score in sorted(group_scores.items(), key=lambda item: (-item[1], item[0])) if score > 0]
    top_values = ordered_groups[:3] or ["稳定经营", "真诚沟通", "生活质感"]
    value_type_map = {
        "稳定经营": "稳定经营型",
        "家庭责任": "家庭投入型",
        "真诚沟通": "真诚靠近型",
        "独立空间": "独立清醒型",
        "成长探索": "成长探索型",
        "生活质感": "生活质感型",
    }
    value_type = value_type_map.get(top_values[0], "稳定经营型")

    tensions: list[str] = []
    if "稳定经营" in top_values and "成长探索" in top_values:
        tensions.append("稳定 vs 新鲜感")
    if "真诚沟通" in top_values and "独立空间" in top_values:
        tensions.append("亲密投入 vs 个人空间")
    if "家庭责任" in top_values and "独立空间" in top_values:
        tensions.append("家庭投入 vs 自主边界")

    values_summary = {
        "assessment_id": f"synthetic_values_{user_identity}",
        "value_type": value_type,
        "top_values": top_values,
        "tensions": tensions,
        "completed_at": completed_at,
    }

    return {
        "mbti": mbti,
        "attachment": attachment,
        "big_five": big_five,
        "sternberg": sternberg,
        "values": values_summary,
    }


__all__ = ["build_synthetic_personality_traits"]
