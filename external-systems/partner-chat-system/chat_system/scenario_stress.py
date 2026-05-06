"""Curated stress beats for dating chat roleplay (awkward, boundary, extreme situations)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .assistant_contract import (
    INTERACTION_MODE_SET,
    MUTUAL_INTENT_ASSESSMENT_SET,
    default_interaction_mode,
)


_BOUNDARY_RISK_PROBLEM_TAGS = frozenset(
    {
        "appearance_pry",
        "boundary_risk",
        "comparison",
        "competitive",
        "cross_exam",
        "defensive_tone",
        "dismissive",
        "jealous_hint",
        "micro_conflict",
        "micro_rude",
        "money_pry",
        "nitpicking",
        "no_good_answer",
        "one_upmanship",
        "pressure",
        "too_fast",
        "value_tension",
    }
)
_INTEREST_UNCLEAR_PROBLEM_TAGS = frozenset(
    {
        "closed_reply",
        "cold_end",
        "disengaged",
        "low_energy",
        "one_word_reply",
        "topic_dead_end",
        "vague_answer",
    }
)
_BOUNDARY_RISK_STRATEGY_TAGS = frozenset({"graceful_exit", "set_boundary", "slow_pace"})
_EXPECTED_ASSESSMENT_OVERRIDES = {
    "ex_partner_bait": "communication_problem",
    "family_pressure": "communication_problem",
    "ghosting_tone": "interest_low",
    "petty_spat": "communication_problem",
}


@dataclass(frozen=True)
class StressBeat:
    id: str
    category: str
    directive: str
    severity: int
    expected_problem_tags: tuple[str, ...]
    suggested_strategy_tags: tuple[str, ...]
    expected_mutual_intent_assessment: str
    expected_interaction_mode: str
    expected_need_rescue_after_turns: int = 0


def _infer_expected_mutual_intent_assessment(
    beat_id: str,
    *,
    problems: tuple[str, ...],
    strategies: tuple[str, ...],
) -> str:
    if beat_id in _EXPECTED_ASSESSMENT_OVERRIDES:
        return _EXPECTED_ASSESSMENT_OVERRIDES[beat_id]
    if any(tag in _BOUNDARY_RISK_PROBLEM_TAGS for tag in problems):
        return "boundary_risk"
    if any(tag in _BOUNDARY_RISK_STRATEGY_TAGS for tag in strategies):
        return "boundary_risk"
    if "shutdown" in problems:
        return "interest_low"
    if any(tag in _INTEREST_UNCLEAR_PROBLEM_TAGS for tag in problems):
        return "interest_unclear"
    return "communication_problem"


def _infer_expected_interaction_mode(expected_mutual_intent_assessment: str) -> str:
    return default_interaction_mode(expected_mutual_intent_assessment, need_rescue=True)


def _beat(
    beat_id: str,
    category: str,
    directive: str,
    *,
    severity: int,
    problems: tuple[str, ...],
    strategies: tuple[str, ...],
    expected_mutual_intent_assessment: str | None = None,
    expected_interaction_mode: str | None = None,
    rescue_after: int = 0,
) -> StressBeat:
    resolved_assessment = expected_mutual_intent_assessment or _infer_expected_mutual_intent_assessment(
        beat_id,
        problems=problems,
        strategies=strategies,
    )
    if resolved_assessment not in MUTUAL_INTENT_ASSESSMENT_SET:
        raise ValueError(f"invalid expected_mutual_intent_assessment for {beat_id}: {resolved_assessment}")
    resolved_mode = expected_interaction_mode or _infer_expected_interaction_mode(resolved_assessment)
    if resolved_mode not in INTERACTION_MODE_SET:
        raise ValueError(f"invalid expected_interaction_mode for {beat_id}: {resolved_mode}")
    return StressBeat(
        beat_id,
        category,
        directive,
        severity,
        problems,
        strategies,
        resolved_assessment,
        resolved_mode,
        rescue_after,
    )


# 覆盖：冷场/尬聊、边界/冒犯、物质与隐私、情绪极端、话题雷区、节奏失控等（演员仍用人设，不跳出角色）
STRESS_BEATS: tuple[StressBeat, ...] = (
    _beat(
        "cold_short",
        "冷场",
        "本回合只发极简回复（不超过10个字），语气偏淡，不要道歉。",
        severity=3,
        problems=("closed_reply", "low_energy"),
        strategies=("share_detail", "ask_easy_question"),
    ),
    _beat(
        "awkward_topic_jump",
        "尬聊",
        "本回合接话明显生硬，强行换到一个和对方上一句不太相关的话题。",
        severity=2,
        problems=("awkward_transition", "topic_drift"),
        strategies=("acknowledge_coldness", "switch_topic"),
    ),
    _beat(
        "one_word",
        "冷场",
        "本回合只回复一个字或一个词（如「嗯」「还好」），不要补充。",
        severity=4,
        problems=("one_word_reply", "topic_dead_end"),
        strategies=("share_detail", "ask_easy_question", "switch_topic"),
    ),
    _beat(
        "slow_reply_energy",
        "冷场",
        "本回合表现得兴致不高，回答敷衍，但不说自己在忙。",
        severity=3,
        problems=("low_energy", "closed_reply"),
        strategies=("share_detail", "ask_easy_question"),
    ),
    _beat(
        "missed_point",
        "误解",
        "本回合故意轻微会错意，把对方的话理解偏一点，仍保持礼貌。",
        severity=3,
        problems=("misread", "awkward_transition"),
        strategies=("clarify", "share_detail"),
    ),
    _beat(
        "micro_rude",
        "边界",
        "本回合带一点刺（挑剔或不耐烦），但不要用脏话、不人身攻击。",
        severity=4,
        problems=("micro_rude", "boundary_risk"),
        strategies=("deescalate", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "money_pry",
        "物质敏感",
        "本回合自然地把话题引向收入/房车/彩礼等（择一），问得略直接。",
        severity=4,
        problems=("money_pry", "boundary_risk"),
        strategies=("set_boundary", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "appearance_pry",
        "隐私",
        "本回合追问外貌/身材/照片真实性，语气略急切。",
        severity=4,
        problems=("appearance_pry", "boundary_risk"),
        strategies=("set_boundary", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "ex_partner_bait",
        "雷区",
        "本回合不经意提到前任或过去感情经历的一点点，观察对方反应（不编具体人名）。",
        severity=3,
        problems=("sensitive_topic", "past_relationship"),
        strategies=("acknowledge_coldness", "switch_topic", "ask_easy_question"),
    ),
    _beat(
        "family_pressure",
        "家庭压力",
        "本回合透露家里催婚/相亲压力，语气有点焦虑。",
        severity=3,
        problems=("pressure_dump", "low_energy"),
        strategies=("acknowledge_coldness", "share_detail", "ask_easy_question"),
    ),
    _beat(
        "schedule_conflict",
        "节奏",
        "本回合提出很难对齐的时间安排，显得不太好约。",
        severity=3,
        problems=("scheduling_friction", "topic_dead_end"),
        strategies=("offer_alternative", "ask_easy_question"),
    ),
    _beat(
        "overshare",
        "过度分享",
        "本回合说太多个人琐事/TMI，略啰嗦。",
        severity=2,
        problems=("overshare", "topic_overload"),
        strategies=("gently_refocus", "ask_easy_question"),
    ),
    _beat(
        "love_bomb_hint",
        "节奏极端",
        "本回合显得过快热情（过度赞美或过快表态），仍要符合你的人设年龄感。",
        severity=4,
        problems=("too_fast", "boundary_risk"),
        strategies=("slow_pace", "set_boundary", "switch_topic"),
    ),
    _beat(
        "skeptic_grill",
        "不信任",
        "本回合像「审问」一样连续追问对方两句里的矛盾点（语气仍中文社交可接受）。",
        severity=4,
        problems=("cross_exam", "defensive_tone"),
        strategies=("deescalate", "share_detail", "ask_easy_question"),
    ),
    _beat(
        "dismissive",
        "不尊重风险",
        "本回合对对方的兴趣点表现得不屑或贬低一点点（不涉歧视用语）。",
        severity=4,
        problems=("dismissive", "boundary_risk"),
        strategies=("deescalate", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "topic_hijack",
        "话不投机",
        "本回合打断对方话题脉络，强推自己只关心的事。",
        severity=3,
        problems=("topic_hijack", "low_reciprocity"),
        strategies=("acknowledge_coldness", "switch_topic"),
    ),
    _beat(
        "jealous_hint",
        "情绪",
        "本回合带一点吃醋或占有欲的暗示（轻度）。",
        severity=3,
        problems=("jealous_hint", "boundary_risk"),
        strategies=("deescalate", "clarify", "switch_topic"),
    ),
    _beat(
        "comparison_trap",
        "雷区",
        "本回合拿「别人/闺蜜说的标准」来压对方，制造一点不适。",
        severity=4,
        problems=("comparison", "pressure"),
        strategies=("deescalate", "set_boundary", "switch_topic"),
    ),
    _beat(
        "health_tmi",
        "边界",
        "本回合聊到身体不适/病史细节略多，让对方不好接。",
        severity=3,
        problems=("tmi", "topic_overload"),
        strategies=("acknowledge_coldness", "gently_refocus", "switch_topic"),
    ),
    _beat(
        "work_rant",
        "情绪",
        "本回合把工作怨气带进来，略负能量。",
        severity=3,
        problems=("negative_energy", "topic_overload"),
        strategies=("acknowledge_coldness", "switch_topic", "ask_easy_question"),
    ),
    _beat(
        "political_social_bait",
        "敏感话题",
        "本回合轻触社会/价值观话题，点到为止，不要吵架式对立。",
        severity=4,
        problems=("sensitive_topic", "value_tension"),
        strategies=("deescalate", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "double_bind",
        "两难问题",
        "本回合问一个让对方怎么答都尴尬的选择题（仍相亲语境）。",
        severity=4,
        problems=("no_good_answer", "pressure"),
        strategies=("reframe", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "ghosting_tone",
        "冷场",
        "本回合像要结束聊天：短、冷、没有追问，但不要明确说再见。",
        severity=5,
        problems=("shutdown", "closed_reply"),
        strategies=("acknowledge_coldness", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "boundary_test",
        "边界",
        "本回合试探对方底线：比如过快问私密安排或见面地点，语气假装随意。",
        severity=4,
        problems=("boundary_risk", "too_fast"),
        strategies=("set_boundary", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "silent_judgment",
        "尬聊",
        "本回合用「哦」「这样啊」式应对，不展开，制造一点沉默压力。",
        severity=4,
        problems=("low_energy", "topic_dead_end"),
        strategies=("acknowledge_coldness", "switch_topic", "ask_easy_question"),
    ),
    _beat(
        "competitive",
        "话不投机",
        "本回合处处想压对方一头（工作/学历/生活），轻度炫耀。",
        severity=4,
        problems=("competitive", "one_upmanship"),
        strategies=("deescalate", "switch_topic", "share_detail"),
    ),
    _beat(
        "vague_answer",
        "误解风险",
        "本回合故意回答模糊、回避关键信息，让对方难接。",
        severity=3,
        problems=("vague_answer", "topic_dead_end"),
        strategies=("ask_easy_question", "switch_topic"),
    ),
    _beat(
        "moral_pedagogy",
        "价值观",
        "本回合说教式劝对方改变生活方式或观念，略令人不适。",
        severity=4,
        problems=("preachy", "value_tension"),
        strategies=("deescalate", "switch_topic", "graceful_exit"),
    ),
    _beat(
        "urgent_need",
        "节奏极端",
        "本回合表现得很急（想马上确定关系/见面），与人设一致地推进。",
        severity=4,
        problems=("too_fast", "pressure"),
        strategies=("slow_pace", "set_boundary", "switch_topic"),
    ),
    _beat(
        "petty_spat",
        "轻微对立",
        "本回合揪对方上一句的小毛病抬杠，仍保持可挽回的相亲礼貌。",
        severity=4,
        problems=("nitpicking", "micro_conflict"),
        strategies=("deescalate", "acknowledge_coldness", "graceful_exit"),
    ),
)

_BEAT_BY_ID: dict[str, StressBeat] = {b.id: b for b in STRESS_BEATS}


def list_beat_ids() -> list[str]:
    return [b.id for b in STRESS_BEATS]


def pick_stress_beat(
    *,
    turn_index: int,
    mode: str,
    rng: random.Random | None = None,
    only_ids: set[str] | None = None,
) -> StressBeat | None:
    """Return the beat for this turn, or None if stress disabled."""
    m = (mode or "").strip().lower()
    if m in ("", "none", "off"):
        return None
    pool = list(STRESS_BEATS)
    if only_ids:
        pool = [b for b in pool if b.id in only_ids]
        if not pool:
            pool = list(STRESS_BEATS)
    r = rng or random.Random()
    if m == "rotate":
        return pool[turn_index % len(pool)]
    if m == "random":
        return r.choice(pool)
    raise ValueError("stress_mode must be none|rotate|random")


def stress_log_entry(turn: int, speaker: str, beat: StressBeat | None) -> dict[str, Any] | None:
    if beat is None:
        return None
    return {
        "turn": turn,
        "speaker": speaker,
        "beat_id": beat.id,
        "category": beat.category,
        "severity": beat.severity,
        "expected_problem_tags": list(beat.expected_problem_tags),
        "suggested_strategy_tags": list(beat.suggested_strategy_tags),
        "expected_mutual_intent_assessment": beat.expected_mutual_intent_assessment,
        "expected_interaction_mode": beat.expected_interaction_mode,
        "expected_need_rescue_after_turns": beat.expected_need_rescue_after_turns,
    }


__all__ = [
    "STRESS_BEATS",
    "StressBeat",
    "list_beat_ids",
    "pick_stress_beat",
    "stress_log_entry",
]
