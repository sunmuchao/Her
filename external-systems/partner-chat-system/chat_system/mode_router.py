"""Fast rule-based mode routing for chat assistant intervention."""

from __future__ import annotations

import re
from typing import Any

from .assistant_contract import (
    default_interaction_mode,
    is_rescue_interaction_mode,
    normalize_interaction_mode,
    normalize_mutual_intent_assessment,
)

VIS_DYADIC = "dyadic"

BOUNDARY_HINTS: tuple[str, ...] = (
    "收入",
    "工资",
    "年薪",
    "房",
    "车",
    "彩礼",
    "前任",
    "照片",
    "身材",
    "住哪",
    "见面",
)
_QUESTION_TOKENS = (
    "吗",
    "呢",
    "哪种",
    "什么",
    "怎么",
    "干嘛",
    "是不是",
    "有空",
    "要不要",
    "行不行",
    "可不可以",
    "方不方便",
)
_APPEARANCE_PRESSURE_HINTS = (
    "本人吧",
    "本人吗",
    "照片看着",
    "照片是本人",
    "发张照片",
    "见光死",
    "差距太大",
)
_PRESSURE_HINTS = (
    "不想浪费时间",
    "别浪费时间",
    "直接见面",
    "出来见见",
    "周末有空出来见见",
    "这周末有空出来见见",
)
_DISMISSIVE_HINTS = (
    "那挺省事",
    "省事",
    "挺别致",
    "理解能力挺别致",
    "别抱太大希望",
    "不用费劲",
)
_DEFENSIVE_HINTS = (
    "怎么怕见光死",
    "怕见光死",
    "你理解能力",
)
_APPEARANCE_AXIS_HINTS = (
    "照片",
    "本人",
    "见光死",
    "身材",
    "瘦",
    "胖",
    "外貌",
    "差距太大",
)
_INCOME_AXIS_HINTS = (
    "收入",
    "工资",
    "年薪",
    "房",
    "车",
    "彩礼",
    "条件",
)
_PRIVACY_AXIS_HINTS = (
    "前任",
    "婚史",
    "离异",
    "孩子",
    "隐私",
    "住哪",
)
_MEETUP_AXIS_HINTS = (
    "见面",
    "出来见",
    "这周末有空出来见见",
    "直接见面",
    "约出来",
)
_PRESSURE_COMPARE_AXIS_HINTS = (
    "别浪费时间",
    "不想浪费时间",
    "省事",
    "理解能力挺别致",
    "不用费劲",
    "别抱太大希望",
    "差距太大",
)
_WARM_HINTS = (
    "哈哈",
    "那不错",
    "挺巧",
    "我也",
    "还挺",
    "蛮",
    "有点意思",
)

_COLD_REPLIES = (
    "嗯",
    "哦",
    "哦哦",
    "这样啊",
    "哦，这样啊。",
    "挺好的",
    "还好",
    "一般",
    "行吧",
)
_LOW_ENERGY_PATTERNS = (
    "在的",
    "挺简单",
    "简单的",
    "就那样",
    "一般般",
    "还行吧",
    "都行",
    "随便",
    "看情况",
    "再说吧",
)
_ALLOWED_SITUATIONS = {"cold", "awkward", "stuck", "rude", "boundary", "off_topic", "none"}
_ALLOWED_RESCUE_STYLES = {"reengage", "switch_topic", "none"}
_ALLOWED_ENGAGEMENT_LEVELS = {"high", "medium", "low", "closed"}
_ALLOWED_WARMTH_LEVELS = {"warm", "neutral", "cold", "sharp"}
_ALLOWED_IRRITATION_LEVELS = {"none", "mild", "medium", "high"}
_ALLOWED_STATE_TRENDS = {"warming", "stable", "cooling", "worsening", "recovering"}
_DEFAULT_PROBLEM_TAGS_BY_SITUATION: dict[str, tuple[str, ...]] = {
    "cold": ("closed_reply", "low_energy"),
    "awkward": ("awkward_transition",),
    "stuck": ("topic_dead_end", "conversation_stall"),
    "rude": ("micro_rude", "defensive_tone"),
    "boundary": ("boundary_risk", "sensitive_topic"),
    "off_topic": ("topic_drift",),
    "none": (),
}


def _dedupe_strs(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _compact_match_text(text: str) -> str:
    return re.sub(r"[\s，,。.!！?？~～、:：;；“”\"'（）()]+", "", str(text or ""))


def _to_clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None or value == "":
        items = []
    else:
        items = [value]
    return _dedupe_strs([str(item or "").strip() for item in items])


def is_question_like(text: str) -> bool:
    t = str(text or "")
    return "？" in t or "?" in t or any(token in t for token in _QUESTION_TOKENS)


def is_cold_like(text: str) -> bool:
    t = " ".join(str(text or "").split()).strip()
    if not t:
        return True
    if t in _COLD_REPLIES:
        return True
    if len(t) <= 4 and not is_question_like(t):
        return True
    return False


def is_low_energy_like(text: str) -> bool:
    t = " ".join(str(text or "").split()).strip()
    if is_cold_like(t):
        return True
    if not t or is_question_like(t):
        return False
    compact = _compact_text(t)
    if any(token in compact for token in _LOW_ENERGY_PATTERNS):
        return True
    clauses = [part for part in re.split(r"[，,。.!！?？~～]+", compact) if part]
    if len(compact) <= 10 and clauses and all(len(part) <= 4 for part in clauses):
        return True
    if len(compact) <= 8 and any(token in compact for token in ("你好", "在的", "收到", "好的")):
        return True
    return False


def _engagement_score(text: str) -> int:
    compact = _compact_text(text)
    if not compact or is_low_energy_like(text):
        return 0
    score = 0
    if len(compact) >= 8:
        score += 1
    if is_question_like(text):
        score += 1
    if any(token in compact for token in ("我", "最近", "平时", "周末", "一般", "会", "喜欢")) and len(compact) >= 6:
        score += 1
    return score


def _recent_mutual_engagement(messages: list[dict[str, Any]], *, window: int = 4) -> bool:
    recent = messages[-window:]
    best_by_author: dict[str, int] = {}
    for message in recent:
        author = str(message.get("author_id") or "")
        if not author:
            continue
        best_by_author[author] = max(
            best_by_author.get(author, 0),
            _engagement_score(str(message.get("body") or "")),
        )
    return len(best_by_author) >= 2 and sum(1 for value in best_by_author.values() if value >= 1) >= 2


def _speaker_recent_engagement(messages: list[dict[str, Any]], speaker_id: str, *, max_messages: int = 2) -> int:
    scores: list[int] = []
    for message in reversed(messages):
        if str(message.get("author_id") or "") != speaker_id:
            continue
        scores.append(_engagement_score(str(message.get("body") or "")))
        if len(scores) >= max_messages:
            break
    return max(scores, default=0)


def _speaker_low_energy_streak(messages: list[dict[str, Any]], speaker_id: str) -> int:
    streak = 0
    for message in reversed(messages):
        if str(message.get("author_id") or "") != speaker_id:
            continue
        body = str(message.get("body") or "")
        if is_low_energy_like(body):
            streak += 1
            continue
        break
    return streak


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    compact = _compact_match_text(text)
    return bool(compact) and any(token in compact for token in tokens)


def _is_boundary_like(text: str) -> bool:
    return _contains_any_token(text, BOUNDARY_HINTS + _APPEARANCE_PRESSURE_HINTS)


def _is_pressure_like(text: str) -> bool:
    return _contains_any_token(text, _PRESSURE_HINTS)


def _is_dismissive_like(text: str) -> bool:
    return _contains_any_token(text, _DISMISSIVE_HINTS)


def _is_defensive_like(text: str) -> bool:
    return _contains_any_token(text, _DEFENSIVE_HINTS)


def _recent_risk_flags(messages: list[dict[str, Any]], *, window: int = 3) -> list[str]:
    flags: list[str] = []
    for message in messages[-window:]:
        body = str(message.get("body") or "")
        if _is_boundary_like(body):
            flags.append("boundary_risk")
        if _is_pressure_like(body):
            flags.append("pressure")
        if _is_dismissive_like(body):
            flags.append("dismissive")
        if _is_defensive_like(body):
            flags.append("defensive")
    return _dedupe_strs(flags)


def _normalize_engagement_level(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _ALLOWED_ENGAGEMENT_LEVELS else "medium"


def _normalize_warmth_level(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _ALLOWED_WARMTH_LEVELS else "neutral"


def _normalize_irritation_level(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _ALLOWED_IRRITATION_LEVELS else "none"


def _normalize_state_trend(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _ALLOWED_STATE_TRENDS else "stable"


def _infer_engagement_level(
    messages: list[dict[str, Any]],
    *,
    last_body: str,
    last_author: str,
) -> str:
    streak = _speaker_low_energy_streak(messages, last_author)
    if streak >= 2:
        return "closed"
    if is_low_energy_like(last_body):
        return "low"
    score = _engagement_score(last_body)
    if score >= 2 and _recent_mutual_engagement(messages):
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _infer_warmth_level(last_body: str, recent_risk_flags: list[str]) -> str:
    compact = _compact_text(last_body)
    if _is_dismissive_like(last_body) or _is_defensive_like(last_body):
        return "sharp"
    if any(flag in recent_risk_flags for flag in ("dismissive", "defensive")):
        return "sharp"
    if is_low_energy_like(last_body):
        return "cold"
    if compact and any(token in compact for token in _WARM_HINTS):
        return "warm"
    return "neutral"


def _infer_irritation_level(
    messages: list[dict[str, Any]],
    *,
    last_body: str,
    last_author: str,
    recent_risk_flags: list[str],
) -> str:
    if _is_dismissive_like(last_body) or _is_defensive_like(last_body):
        return "high"
    if any(flag in recent_risk_flags for flag in ("dismissive", "defensive")):
        return "high"
    if _is_boundary_like(last_body) or _is_pressure_like(last_body):
        return "medium"
    if any(flag in recent_risk_flags for flag in ("boundary_risk", "pressure")):
        return "medium"
    if _speaker_low_energy_streak(messages, last_author) >= 2 or is_low_energy_like(last_body):
        return "mild"
    return "none"


def _infer_state_trend(
    messages: list[dict[str, Any]],
    *,
    engagement_level: str,
    warmth_level: str,
    irritation_level: str,
) -> str:
    recent = [str(message.get("body") or "").strip() for message in messages[-3:]]
    if not recent:
        return "stable"
    if irritation_level in {"medium", "high"} or warmth_level == "sharp":
        return "worsening"
    if engagement_level in {"low", "closed"} and any(
        not is_low_energy_like(body) for body in recent[:-1]
    ):
        return "cooling"
    if engagement_level in {"medium", "high"} and any(
        is_low_energy_like(body) for body in recent[:-1]
    ) and not is_low_energy_like(recent[-1]):
        return "recovering"
    if engagement_level == "high" and len(recent) >= 2 and _engagement_score(recent[-1]) >= _engagement_score(recent[-2]):
        return "warming"
    return "stable"


def _state_snapshot(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {
            "engagement_level": "medium",
            "warmth_level": "neutral",
            "irritation_level": "none",
            "state_trend": "stable",
        }
    last_body = str(messages[-1].get("body") or "").strip()
    last_author = str(messages[-1].get("author_id") or "")
    recent_risk_flags = _recent_risk_flags(messages)
    engagement_level = _infer_engagement_level(messages, last_body=last_body, last_author=last_author)
    warmth_level = _infer_warmth_level(last_body, recent_risk_flags)
    irritation_level = _infer_irritation_level(
        messages,
        last_body=last_body,
        last_author=last_author,
        recent_risk_flags=recent_risk_flags,
    )
    state_trend = _infer_state_trend(
        messages,
        engagement_level=engagement_level,
        warmth_level=warmth_level,
        irritation_level=irritation_level,
    )
    return {
        "engagement_level": engagement_level,
        "warmth_level": warmth_level,
        "irritation_level": irritation_level,
        "state_trend": state_trend,
    }


def _has_cold_prefix_question(text: str) -> bool:
    if not is_question_like(text):
        return False
    parts = [part.strip() for part in re.split(r"[，,。.!！?？~～]+", str(text or "")) if part.strip()]
    return len(parts) == 2 and is_cold_like(parts[0]) and not is_question_like(parts[0])


def _should_repair_cold_prefix_question(messages: list[dict[str, Any]], *, window: int = 4) -> bool:
    recent = messages[-window:]
    if len(recent) < 2 or _recent_risk_flags(recent):
        return False
    bodies = [str(message.get("body") or "").strip() for message in recent]
    if not _has_cold_prefix_question(bodies[-1]):
        return False
    return any(is_low_energy_like(body) for body in bodies[:-1])


def _should_repair_after_awkward_reply(messages: list[dict[str, Any]], *, window: int = 4) -> bool:
    recent = messages[-window:]
    if len(recent) < 3 or _recent_risk_flags(recent):
        return False
    bodies = [str(message.get("body") or "").strip() for message in recent]
    last_body = bodies[-1]
    prev_body = bodies[-2]
    if not is_low_energy_like(last_body):
        return False
    return _has_cold_prefix_question(prev_body)


def _normalize_situation(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in _ALLOWED_SITUATIONS:
        return raw
    text = str(value or "").strip()
    if any(token in text for token in ("边界", "敏感", "压力")):
        return "boundary"
    if "冷" in text:
        return "cold"
    if "尴尬" in text or "生硬" in text:
        return "awkward"
    if "卡住" in text or "僵" in text:
        return "stuck"
    if "冒犯" in text or "冲" in text:
        return "rude"
    if "跑题" in text:
        return "off_topic"
    return "none"


def _default_problem_tags(
    *,
    situation: str,
    mutual_intent_assessment: str,
    interaction_mode: str,
) -> list[str]:
    tags = list(_DEFAULT_PROBLEM_TAGS_BY_SITUATION.get(situation, ()))
    if interaction_mode == "repair" and situation == "stuck":
        tags.append("missed_connection")
    return _dedupe_strs(tags)


def _normalize_rescue_style(
    value: Any,
    *,
    interaction_mode: str,
    mutual_intent_assessment: str,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in _ALLOWED_RESCUE_STYLES:
        return raw
    text = str(value or "").strip()
    if "低压" in text or "试探" in text:
        return "none"
    if "换题" in text:
        return "switch_topic"
    if any(token in text for token in ("收住", "止损", "退出")):
        return "none"
    if "接住" in text:
        return "reengage"
    if interaction_mode == "repair":
        return "switch_topic"
    return "none"


def normalize_route_decision(
    data: dict[str, Any],
    *,
    decision_source: str,
) -> dict[str, Any]:
    raw_need = bool(data.get("need_rescue"))
    situation = _normalize_situation(data.get("situation"))
    raw_assessment = str(data.get("mutual_intent_assessment") or "").strip()
    if raw_assessment:
        mutual_intent_assessment = normalize_mutual_intent_assessment(raw_assessment)
    elif not raw_need and situation == "none":
        mutual_intent_assessment = "normal"
    elif raw_need and str(data.get("rescue_style") or "").strip().lower() in {"reengage", "switch_topic"}:
        mutual_intent_assessment = "communication_problem"
    else:
        mutual_intent_assessment = normalize_mutual_intent_assessment(raw_assessment)
    interaction_mode = normalize_interaction_mode(
        data.get("interaction_mode"),
        mutual_intent_assessment=mutual_intent_assessment,
        need_rescue=raw_need,
    )
    need_rescue = is_rescue_interaction_mode(interaction_mode)
    rescue_style = _normalize_rescue_style(
        data.get("rescue_style"),
        interaction_mode=interaction_mode,
        mutual_intent_assessment=mutual_intent_assessment,
    )
    if interaction_mode == "none":
        rescue_style = "none"
    problem_tags = (
        _to_clean_list(data.get("problem_tags"))
        or _default_problem_tags(
            situation=situation,
            mutual_intent_assessment=mutual_intent_assessment,
            interaction_mode=interaction_mode,
        )
    )
    out = {
        "need_rescue": need_rescue,
        "situation": situation,
        "problem_tags": problem_tags,
        "rescue_style": rescue_style,
        "mutual_intent_assessment": mutual_intent_assessment,
        "interaction_mode": interaction_mode,
        "reason": str(data.get("reason") or "").strip(),
        "decision_source": decision_source,
        "engagement_level": _normalize_engagement_level(data.get("engagement_level")),
        "warmth_level": _normalize_warmth_level(data.get("warmth_level")),
        "irritation_level": _normalize_irritation_level(data.get("irritation_level")),
        "state_trend": _normalize_state_trend(data.get("state_trend")),
    }
    if data.get("parse_error"):
        out["parse_error"] = True
    return out


def fast_mode_route(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    dyadic = [m for m in messages if str(m.get("visibility") or "") == VIS_DYADIC]
    snapshot = _state_snapshot(dyadic)

    def _decision(payload: dict[str, Any], source: str) -> dict[str, Any]:
        return normalize_route_decision({**snapshot, **payload}, decision_source=source)

    def _none(reason: str, source: str = "heuristic") -> dict[str, Any]:
        return _decision(
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": reason,
            },
            source,
        )

    if not dyadic:
        return _none("首轮开场，先正常聊，不需要提前介入。", "heuristic_bootstrap")

    last_body = str(dyadic[-1].get("body") or "").strip()
    prev_body = str(dyadic[-2].get("body") or "").strip() if len(dyadic) >= 2 else ""
    last_author = str(dyadic[-1].get("author_id") or "")
    recent = [str(m.get("body") or "").strip() for m in dyadic[-3:]]
    prior_mutual_engagement = _recent_mutual_engagement(dyadic[:-1])
    last_author_recent_engagement = _speaker_recent_engagement(dyadic[:-1], last_author)
    last_author_low_streak = _speaker_low_energy_streak(dyadic, last_author)
    recent_risk_flags = _recent_risk_flags(dyadic)
    awkward_cold_question_repair = _should_repair_cold_prefix_question(dyadic)
    awkward_reply_repair = _should_repair_after_awkward_reply(dyadic)
    recent_low_energy = sum(1 for body in recent if is_low_energy_like(body))

    if recent_risk_flags or _is_boundary_like(last_body) or _is_pressure_like(last_body):
        return _none(
            "这轮更像边界、冒犯或施压问题，不属于回温助手职责，先不主动提示。",
            "heuristic_scope_filter",
        )
    if _is_dismissive_like(last_body) or _is_defensive_like(last_body):
        return _none(
            "这轮已经带刺或对立了，不属于回温助手职责，先不主动提示。",
            "heuristic_scope_filter",
        )
    if _has_cold_prefix_question(last_body):
        if prior_mutual_engagement or awkward_cold_question_repair:
            return _decision(
                {
                    "need_rescue": True,
                    "situation": "cold",
                    "problem_tags": ["closed_reply", "low_energy", "awkward_transition"],
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic",
                    "reason": "上一句虽然带着问题，但最近这几拍一直没真正接顺，更像开局尬接，值得主动帮忙修一下。",
                },
                "heuristic",
            )
        return _none(
            "这轮虽然带着问题，但还看不出是典型的回温型卡点，先不主动提示。",
            "heuristic_scope_filter",
        )

    if is_low_energy_like(last_body):
        if len(recent) >= 2 and all(is_low_energy_like(body) for body in recent[-2:]):
            if _recent_mutual_engagement(dyadic[:-2]):
                return _decision(
                    {
                        "need_rescue": True,
                        "situation": "stuck",
                        "problem_tags": ["closed_reply", "low_energy", "topic_dead_end"],
                        "mutual_intent_assessment": "communication_problem",
                        "interaction_mode": "repair",
                        "rescue_style": "switch_topic",
                        "reason": "前面双方都有投入，但最近两拍都接空了，像是不会接而不是不想聊。",
                    },
                    "heuristic",
                )
            if any(is_question_like(body) for body in recent[:-1]) and last_author_low_streak < 2:
                return _decision(
                    {
                        "need_rescue": True,
                        "situation": "stuck",
                        "problem_tags": ["closed_reply", "low_energy", "awkward_transition"],
                        "mutual_intent_assessment": "communication_problem",
                        "interaction_mode": "repair",
                        "rescue_style": "switch_topic",
                        "reason": "最近两拍都偏冷，但前面还有人在试着往下接，更像聊尬了而不是已经不想聊。",
                    },
                    "heuristic",
                )
            return _none(
                "最近两边都偏冷，更像自然降温，不属于回温助手职责。",
                "heuristic_scope_filter",
            )
        if prior_mutual_engagement and last_author_recent_engagement >= 1:
            return _decision(
                {
                    "need_rescue": True,
                    "situation": "cold",
                    "problem_tags": ["closed_reply", "low_energy", "missed_connection"],
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic" if is_question_like(prev_body) else "reengage",
                    "reason": "前面双方本来聊得动，这一拍更像接话没接好。",
                },
                "heuristic",
            )
        if awkward_reply_repair:
            return _decision(
                {
                    "need_rescue": True,
                    "situation": "stuck",
                    "problem_tags": ["closed_reply", "low_energy", "awkward_transition", "missed_connection"],
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic",
                    "reason": "刚经历过一拍生硬追问，这一拍又回得很死，更像不会接话导致的冷场，还值得再修一下。",
                },
                "heuristic",
            )
        if last_author_low_streak >= 2:
            return _none(
                "对方已经连续低投入，更像兴趣不高，不属于回温助手职责。",
                "heuristic_scope_filter",
            )
        return _none(
            "这轮偏冷，但还不足以说明只是不会聊，先不主动提示。",
            "heuristic_scope_filter",
        )
    if is_question_like(last_body) and any(is_low_energy_like(body) for body in recent[:-1]) and (
        is_low_energy_like(prev_body) or is_question_like(prev_body)
    ):
        return _decision(
            {
                "need_rescue": True,
                "situation": "stuck",
                "problem_tags": ["closed_reply", "low_energy", "awkward_transition"],
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "reason": "前面刚经历冷回复或尬接，这一拍虽然继续提问，但还没真正恢复顺畅，适合帮忙回温。",
            },
            "heuristic",
        )
    if len(recent) >= 3 and recent_low_energy >= 2 and not any(is_question_like(body) for body in recent):
        if _recent_mutual_engagement(dyadic[:-3]):
            return _decision(
                {
                    "need_rescue": True,
                    "situation": "stuck",
                    "problem_tags": ["topic_dead_end", "conversation_stall", "low_energy"],
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic",
                    "reason": "前面聊得还行，但最近几轮连续接空，适合做一次轻修复。",
                },
                "heuristic",
            )
        return _none(
            "最近几轮连续偏冷又没有追问，更像自然降温，不属于回温助手职责。",
            "heuristic_scope_filter",
        )
    if (
        _engagement_score(last_body) >= 1
        and any(is_low_energy_like(body) for body in recent[:-1])
        and len(_compact_text(last_body)) >= 8
    ):
        return _decision(
            {
                "need_rescue": True,
                "situation": "stuck",
                "problem_tags": ["closed_reply", "awkward_transition", "missed_connection"],
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "reason": "这轮已经在努力把冷场接回来，但还没完全接顺，适合给一把回温建议。",
            },
            "heuristic",
        )
    if (
        is_question_like(last_body)
        and len(_compact_text(last_body)) >= 8
    ):
        return _none("上一句本身就是正常可接的问题，先别打断自然往下聊。", "heuristic_clear_continue")
    if (
        len(_compact_text(last_body)) >= 10
        and not is_cold_like(last_body)
        and is_question_like(prev_body)
    ):
        return _none("当前还有正常来回，先不额外介入。", "heuristic_clear_continue")
    if (
        _engagement_score(last_body) >= 1
        and not any(token in last_body for token in BOUNDARY_HINTS)
        and (
            len(dyadic) == 1
            or _engagement_score(prev_body) >= 1
            or is_question_like(prev_body)
        )
    ):
        return _none("最近这拍仍然有正常信息交换，先顺着自然聊。", "heuristic_clear_continue")
    return _none("当前没有明显的回温型卡点，先顺着自然聊。", "heuristic_default")


__all__ = [
    "BOUNDARY_HINTS",
    "fast_mode_route",
    "is_cold_like",
    "is_low_energy_like",
    "is_question_like",
    "normalize_route_decision",
]
