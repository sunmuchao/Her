"""Curated stress beats for dating chat roleplay (awkward, boundary, extreme situations)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StressBeat:
    id: str
    category: str
    directive: str


# 覆盖：冷场/尬聊、边界/冒犯、物质与隐私、情绪极端、话题雷区、节奏失控等（演员仍用人设，不跳出角色）
STRESS_BEATS: tuple[StressBeat, ...] = (
    StressBeat("cold_short", "冷场", "本回合只发极简回复（不超过10个字），语气偏淡，不要道歉。"),
    StressBeat("awkward_topic_jump", "尬聊", "本回合接话明显生硬，强行换到一个和对方上一句不太相关的话题。"),
    StressBeat("one_word", "冷场", "本回合只回复一个字或一个词（如「嗯」「还好」），不要补充。"),
    StressBeat("slow_reply_energy", "冷场", "本回合表现得兴致不高，回答敷衍，但不说自己在忙。"),
    StressBeat("missed_point", "误解", "本回合故意轻微会错意，把对方的话理解偏一点，仍保持礼貌。"),
    StressBeat("micro_rude", "边界", "本回合带一点刺（挑剔或不耐烦），但不要用脏话、不人身攻击。"),
    StressBeat("money_pry", "物质敏感", "本回合自然地把话题引向收入/房车/彩礼等（择一），问得略直接。"),
    StressBeat("appearance_pry", "隐私", "本回合追问外貌/身材/照片真实性，语气略急切。"),
    StressBeat("ex_partner_bait", "雷区", "本回合不经意提到前任或过去感情经历的一点点，观察对方反应（不编具体人名）。"),
    StressBeat("family_pressure", "家庭压力", "本回合透露家里催婚/相亲压力，语气有点焦虑。"),
    StressBeat("schedule_conflict", "节奏", "本回合提出很难对齐的时间安排，显得不太好约。"),
    StressBeat("overshare", "过度分享", "本回合说太多个人琐事/TMI，略啰嗦。"),
    StressBeat("love_bomb_hint", "节奏极端", "本回合显得过快热情（过度赞美或过快表态），仍要符合你的人设年龄感。"),
    StressBeat("skeptic_grill", "不信任", "本回合像「审问」一样连续追问对方两句里的矛盾点（语气仍中文社交可接受）。"),
    StressBeat("dismissive", "不尊重风险", "本回合对对方的兴趣点表现得不屑或贬低一点点（不涉歧视用语）。"),
    StressBeat("topic_hijack", "话不投机", "本回合打断对方话题脉络，强推自己只关心的事。"),
    StressBeat("jealous_hint", "情绪", "本回合带一点吃醋或占有欲的暗示（轻度）。"),
    StressBeat("comparison_trap", "雷区", "本回合拿「别人/闺蜜说的标准」来压对方，制造一点不适。"),
    StressBeat("health_tmi", "边界", "本回合聊到身体不适/病史细节略多，让对方不好接。"),
    StressBeat("work_rant", "情绪", "本回合把工作怨气带进来，略负能量。"),
    StressBeat("political_social_bait", "敏感话题", "本回合轻触社会/价值观话题，点到为止，不要吵架式对立。"),
    StressBeat("double_bind", "两难问题", "本回合问一个让对方怎么答都尴尬的选择题（仍相亲语境）。"),
    StressBeat("ghosting_tone", "冷场", "本回合像要结束聊天：短、冷、没有追问，但不要明确说再见。"),
    StressBeat("boundary_test", "边界", "本回合试探对方底线：比如过快问私密安排或见面地点，语气假装随意。"),
    StressBeat("silent_judgment", "尬聊", "本回合用「哦」「这样啊」式应对，不展开，制造一点沉默压力。"),
    StressBeat("competitive", "话不投机", "本回合处处想压对方一头（工作/学历/生活），轻度炫耀。"),
    StressBeat("vague_answer", "误解风险", "本回合故意回答模糊、回避关键信息，让对方难接。"),
    StressBeat("moral_pedagogy", "价值观", "本回合说教式劝对方改变生活方式或观念，略令人不适。"),
    StressBeat("urgent_need", "节奏极端", "本回合表现得很急（想马上确定关系/见面），与人设一致地推进。"),
    StressBeat("petty_spat", "轻微对立", "本回合揪对方上一句的小毛病抬杠，仍保持可挽回的相亲礼貌。"),
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
    }


__all__ = [
    "STRESS_BEATS",
    "StressBeat",
    "list_beat_ids",
    "pick_stress_beat",
    "stress_log_entry",
]
