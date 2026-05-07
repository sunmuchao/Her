"""Two LLM personas chat in a real ``chat_threads`` row; proactive assistant rescue; persona self-evaluation."""

from __future__ import annotations

import json
import random
import re
import zlib
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Callable, Protocol

from . import mode_router as _mode_router_module
from .assistant_contract import (
    FOLLOW_LEVEL_NONE,
    FOLLOW_LEVEL_NOT_APPLICABLE,
    FOLLOW_LEVEL_PARTIAL,
    FOLLOW_LEVEL_STRONG,
    INTERACTION_MODES,
    MUTUAL_INTENT_ASSESSMENTS,
    ROLEPLAY_TURN_EVALUATION_FIELDS,
    SHARED_TURN_EVALUATION_FIELDS,
    TURN_EVALUATION_SCHEMA_VERSION,
    format_choice_values,
)
from .mode_router import fast_mode_route, normalize_route_decision
from .scenario_stress import StressBeat, pick_stress_beat, stress_log_entry
from .service import (
    SRC_USER,
    VIS_DYADIC,
    assistant_proactive_hint,
    assistant_query,
    get_or_create_thread,
    get_thread_by_case,
    list_messages,
    post_message,
)
from .trend_state import is_duplicate_suppression_reason

LLMFn = Callable[[list[dict[str, str]]], str]

_ANALYTIC_PHRASES = (
    "你是在认可",
    "我理解你的意思是",
    "从你的表述来看",
    "如果我没理解错",
    "从你的角度看",
    "你想表达的是",
    "这说明你",
    "意味着你",
)
_EXPLANATORY_PHRASES = (
    "我的意思是",
    "我想表达的是",
    "这样说是因为",
    "之所以这么说",
    "换句话说",
)
_STRUCTURED_MONOLOGUE_TOKENS = (
    "首先",
    "其次",
    "总之",
)
_WRITTEN_TONE_TOKENS = (
    "表述",
    "认可",
    "意味着",
    "说明",
    "本质上",
    "例如",
    "如下",
)
_META_COMMENTARY_MARKERS = (
    "这样回复",
    "这样说",
    "我的意思",
    "我想表达",
    "如果我没理解错",
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
_BOUNDARY_HINTS = (
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
_LOW_BAR_QUESTION_TOKENS = (
    "平时",
    "一般",
    "通常",
    "最近",
    "周末",
    "下班",
    "休息",
    "会不会",
    "会吗",
    "喜欢",
    "常",
)
_QUESTION_HINT_TOKENS = (
    "吗",
    "呢",
    "什么",
    "怎么",
    "哪",
    "哪种",
    "有没有",
    "会不会",
    "是不是",
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
_GRACEFUL_EXIT_TOKENS = (
    "先不打扰",
    "改天再聊",
    "有空再聊",
    "回头聊",
    "先这样",
    "先聊到这",
    "下次再聊",
    "你先忙",
    "晚点聊",
)
_MEETUP_PUSH_TOKENS = (
    "见面",
    "出来",
    "线下",
    "约",
    "方便",
    "住哪",
    "定位",
)
_FAST_RELATION_TOKENS = (
    "马上见",
    "尽快见",
    "赶紧",
    "定下来",
    "确定关系",
)
_WORK_STRESS_TOKENS = (
    "工作",
    "加班",
    "忙",
    "烦",
    "累",
    "开会",
)
_STRESS_BEAT_SIGNAL_TOKENS = {
    "appearance_pry": ("照片", "本人", "瘦", "身材", "差距", "见光死"),
    "boundary_test": ("见面", "住哪", "方便", "定位", "哪边", "线下"),
    "cold_short": ("嗯", "哦", "还好", "一般"),
    "comparison_trap": ("别人", "闺蜜", "标准", "诚意", "条件"),
    "competitive": ("我比", "我这边", "不至于", "谁都", "至少"),
    "dismissive": ("就这", "没意思", "无聊", "不至于", "就那样"),
    "double_bind": ("那你到底", "选一个", "总得", "到底是"),
    "ex_partner_bait": ("前任", "以前对象", "之前那段", "上一段"),
    "family_pressure": ("家里", "催婚", "催", "相亲", "着急"),
    "ghosting_tone": ("再说吧", "看情况", "先这样", "回头聊"),
    "health_tmi": ("身体", "医院", "病", "难受", "检查"),
    "jealous_hint": ("别人都", "异性", "追你", "挺抢手"),
    "love_bomb_hint": ("好喜欢", "很心动", "感觉你很适合", "好难得"),
    "moral_pedagogy": ("你应该", "最好", "成熟点", "别这样"),
    "money_pry": ("工资", "收入", "年薪", "房", "车", "彩礼"),
    "petty_spat": ("刚刚还", "不是说", "怎么又", "前后不一"),
    "political_social_bait": ("价值观", "社会", "男女", "婚恋市场"),
    "schedule_conflict": ("周末", "加班", "时间", "排班", "不好约"),
    "skeptic_grill": ("是不是", "还是说", "怎么又", "那你为什么"),
    "urgent_need": ("尽快", "马上", "快点", "定下来", "抓紧"),
    "vague_answer": ("看情况", "还行吧", "一般般", "再说"),
    "work_rant": ("工作", "加班", "离谱", "烦", "累"),
}
_GUIDANCE_TOPIC_KEYWORDS = (
    "周末",
    "咖啡",
    "养生",
    "作息",
    "桌游",
    "羽毛球",
    "无锡",
    "聚会",
    "通勤",
    "吃喝",
    "美食",
    "电影",
    "旅行",
    "运动",
    "宠物",
    "猫",
    "狗",
    "放松",
    "城市",
)
_MUTUAL_INTENT_CHOICES = format_choice_values(MUTUAL_INTENT_ASSESSMENTS)
_INTERACTION_MODE_CHOICES = format_choice_values(INTERACTION_MODES)


def _coerce_roleplay_mutual_intent(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "communication_problem":
        return "communication_problem"
    return "normal"


def _coerce_roleplay_interaction_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "repair":
        return "repair"
    return "none"


def _scope_roleplay_route_decision(decision: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_route_decision(dict(decision or {}), decision_source=str((decision or {}).get("decision_source") or "roleplay_scope"))
    mode = _coerce_roleplay_interaction_mode(normalized.get("interaction_mode"))
    if mode == "repair":
        return {
            **normalized,
            "need_rescue": True,
            "mutual_intent_assessment": "communication_problem",
            "interaction_mode": "repair",
            "risk_axis": None,
            "hold_subtype": None,
        }
    return {
        **normalized,
        "need_rescue": False,
        "mutual_intent_assessment": "normal",
        "interaction_mode": "none",
        "rescue_style": "none",
        "risk_axis": None,
        "hold_subtype": None,
    }


def _scope_roleplay_guidance(guidance: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(guidance, dict) or not guidance:
        return guidance
    scoped = dict(guidance)
    mode = _coerce_roleplay_interaction_mode(scoped.get("interaction_mode"))
    scoped["interaction_mode"] = mode
    scoped["mutual_intent_assessment"] = "communication_problem" if mode == "repair" else "normal"
    scoped["risk_axis"] = None
    scoped["hold_subtype"] = None
    return scoped


class SupportsConn(Protocol):
    def commit(self) -> None: ...


def _is_timeout_exception(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc or "").lower()
    return "timeout" in name or "timed out" in text or "deadline exceeded" in text


def _is_timeout_error_text(text: str) -> bool:
    lowered = str(text or "").lower()
    return "timeout" in lowered or "timed out" in lowered or "deadline exceeded" in lowered


def parse_int_csv(s: str) -> list[int]:
    s = (s or "").strip()
    if not s:
        return []
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return sorted(set(out))


def strip_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if not t:
        raise ValueError("empty model output")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(t[start : end + 1])


def format_visible_transcript(msgs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in msgs:
        vis = m.get("visibility") or ""
        src = m.get("source") or ""
        who = m.get("author_id") or ""
        tag = "双方可见" if vis == VIS_DYADIC else "仅自己可见"
        lines.append(f"—— {who} | {src} | {tag} ——\n{m.get('body') or ''}")
    return "\n\n".join(lines)


def dyadic_public_transcript(conn, thread_id: str, viewer_id: str, *, limit: int = 200) -> str:
    msgs = [
        m
        for m in list_messages(conn, thread_id, viewer_id, limit=limit)
        if m.get("visibility") == VIS_DYADIC
    ]
    return format_visible_transcript(msgs)


def _persona_system(*, user_id: str, brief: str) -> str:
    return (
        f"你在相亲/交友场景中与另一位用户私聊。你的用户ID是「{user_id}」。\n"
        f"人设与目标：{brief}\n"
        "规则：只用中文；说话自然、克制、尊重对方；不要编造具体见面承诺或虚假个人信息。\n"
        "像真人即时聊天，优先短句、口语、自然停顿，不要写成分析、解释、客服、复盘或小作文口吻。\n"
        "一条消息通常只做一到两件事：接住对方、补一句自己、或者问一个轻问题，不要展开三段说明。\n"
        "低质量反例："
        "「你是在认可……吗」"
        "「从你的表述来看……」"
        "「我理解你的意思是……」"
        "「如果我没理解错的话……」"
        "「首先……其次……总之……」"
        "，这些都太像分析者，不像真人聊天。\n"
        "当消息记录里出现 assistant 发给你的「仅自己可见」建议时，你可以参考其方向，但最终发出的内容要是你自己的话。"
    )


def _orchestrator_rescue_decision(
    *,
    llm: LLMFn,
    next_speaker_id: str,
    participant_a_id: str,
    participant_b_id: str,
    dyadic_transcript: str,
) -> dict[str, Any]:
    system = (
        "你是相亲/交友私聊的**对话调度员**（不是参与者本人）。"
        "你只阅读「双方可见」记录，判断在**下一位用户即将开口前**，是否应由系统助手介入。\n"
        "只分两类："
        "1. 双方都还想继续聊，但这轮卡在沟通上，需要 repair。"
        "2. 其他情况一律 normal/none，不要让助手介入。\n"
        "不要过度干预：自然、有来有往、气氛正常时不要介入。\n"
        "只输出**一个 JSON 对象**，不要 Markdown、不要代码块外壳。"
    )
    user = (
        f"下一位即将发言的用户ID：{next_speaker_id}\n"
        f"参与者A ID：{participant_a_id}\n"
        f"参与者B ID：{participant_b_id}\n\n"
        "双方可见记录（按时间）：\n"
        f"{dyadic_transcript or '（尚无双方可见消息）'}\n\n"
        "输出 JSON：\n"
        "{\n"
        '  "need_rescue": <true|false>,\n'
        '  "situation": "<cold|awkward|stuck|rude|boundary|off_topic|none 选一>",\n'
        '  "problem_tags": ["<closed_reply|low_energy|topic_dead_end|boundary_risk 等粗标签>"],\n'
        '  "mutual_intent_assessment": "<communication_problem|normal 选一>",\n'
        '  "interaction_mode": "<repair|none 选一>",\n'
        '  "rescue_style": "<reengage|switch_topic|none 选一>",\n'
        '  "reason": "<极短中文，说明为何需要或不需要救场>"\n'
        "}\n"
        "规则：只有 interaction_mode 为 repair 时，need_rescue 才能为 true。"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        return _scope_roleplay_route_decision(
            {
                **strip_json_object(raw),
                "decision_source": "llm",
            }
        )
    except (json.JSONDecodeError, ValueError):
        return _scope_roleplay_route_decision(
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "调度解析失败，默认不介入",
                "parse_error": True,
                "decision_source": "llm_parse_fallback",
            },
        )


def _normalize_reply_experiment_mode(
    reply_experiment_mode: str | None,
    *,
    simulate_reply_reads_interaction_mode: bool,
) -> str:
    raw = str(reply_experiment_mode or "").strip().lower()
    if not raw:
        return "mode_hint" if simulate_reply_reads_interaction_mode else "free"
    if raw in {"free", "off", "none"}:
        return "free"
    if raw in {"mode_hint", "hint", "read_mode"}:
        return "mode_hint"
    if raw in {"controlled", "control", "guided"}:
        return "controlled"
    raise ValueError("reply_experiment_mode must be free|mode_hint|controlled")


def _clamp_state_level(value: int, *, low: int = 0, high: int = 4) -> int:
    return max(low, min(high, int(value)))


def _default_speaker_state() -> dict[str, Any]:
    return {
        "warmth": 2,
        "guardedness": 1,
        "irritation": 0,
        "disengagement": 1,
        "closure_bias": 0,
        "trend": "steady",
    }


def _speaker_state_copy(state: dict[str, Any] | None) -> dict[str, Any]:
    base = _default_speaker_state()
    if not isinstance(state, dict):
        return base
    for key in ("warmth", "guardedness", "irritation", "disengagement", "closure_bias"):
        base[key] = _clamp_state_level(int(state.get(key) or base[key]))
    trend = str(state.get("trend") or "steady").strip() or "steady"
    base["trend"] = trend
    return base


def _apply_state_delta(
    state: dict[str, Any],
    *,
    warmth: int = 0,
    guardedness: int = 0,
    irritation: int = 0,
    disengagement: int = 0,
    closure_bias: int = 0,
    trend: str | None = None,
) -> dict[str, Any]:
    out = _speaker_state_copy(state)
    out["warmth"] = _clamp_state_level(int(out["warmth"]) + warmth)
    out["guardedness"] = _clamp_state_level(int(out["guardedness"]) + guardedness)
    out["irritation"] = _clamp_state_level(int(out["irritation"]) + irritation)
    out["disengagement"] = _clamp_state_level(int(out["disengagement"]) + disengagement)
    out["closure_bias"] = _clamp_state_level(int(out["closure_bias"]) + closure_bias)
    if trend:
        out["trend"] = str(trend)
    return out


def _state_delta_from_counterpart_message(text: str) -> dict[str, int | str]:
    compact = _compact_text(text)
    if not compact:
        return {"disengagement": 1, "closure_bias": 1, "trend": "cooling"}
    delta: dict[str, int | str] = {}
    if _mentions_boundary_topic(text) or any(token in compact for token in _MEETUP_PUSH_TOKENS):
        delta["guardedness"] = 1
        delta["irritation"] = 1
        delta["trend"] = "tenser"
    elif _is_pushy_questioning(text):
        delta["guardedness"] = 1
        delta["trend"] = "tenser"
    elif _is_low_energy_like(text):
        delta["disengagement"] = 1
        delta["closure_bias"] = 1
        delta["trend"] = "cooling"
    elif _is_question_like(text):
        delta["warmth"] = 1
        delta["disengagement"] = -1
        delta["trend"] = "opening"
    else:
        delta["trend"] = "steady"
    return delta


def _state_delta_from_stress_beat(beat: StressBeat | None) -> dict[str, int | str]:
    if beat is None:
        return {"trend": "steady"}
    beat_id = beat.id
    if beat_id in {"cold_short", "one_word", "slow_reply_energy", "ghosting_tone", "silent_judgment", "vague_answer"}:
        return {"warmth": -1, "disengagement": 1, "closure_bias": 1, "trend": "cooling"}
    if beat_id in {"money_pry", "appearance_pry", "boundary_test", "comparison_trap", "skeptic_grill", "petty_spat"}:
        return {"warmth": -1, "guardedness": 1, "irritation": 1, "trend": "tenser"}
    if beat_id in {"love_bomb_hint", "urgent_need"}:
        return {"warmth": 1, "guardedness": -1, "trend": "accelerating"}
    if beat_id in {"family_pressure", "work_rant", "health_tmi", "overshare"}:
        return {"warmth": -1, "disengagement": 1, "trend": "heavier"}
    return {"trend": "steady"}


def _state_delta_from_message(text: str) -> dict[str, int | str]:
    compact = _compact_text(text)
    if not compact:
        return {"disengagement": 1, "closure_bias": 1, "trend": "cooling"}
    delta: dict[str, int | str] = {"trend": "steady"}
    if _is_graceful_exit_like(text):
        delta["warmth"] = -1
        delta["closure_bias"] = 2
        delta["disengagement"] = 1
        delta["trend"] = "closing"
        return delta
    if _mentions_boundary_topic(text) or any(token in compact for token in _FAST_RELATION_TOKENS):
        delta["guardedness"] = 1
        delta["irritation"] = 1
        delta["trend"] = "tenser"
    if _is_low_energy_like(text):
        delta["warmth"] = -1
        delta["disengagement"] = 1
        delta["trend"] = "cooling"
    elif _is_question_like(text):
        delta["warmth"] = 1
        delta["disengagement"] = -1
        delta["trend"] = "opening"
    elif len(compact) >= 14:
        delta["warmth"] = 1
        delta["trend"] = "steady"
    return delta


def _describe_speaker_state(state: dict[str, Any]) -> str:
    parts: list[str] = []
    warmth = int(state.get("warmth") or 0)
    guardedness = int(state.get("guardedness") or 0)
    irritation = int(state.get("irritation") or 0)
    disengagement = int(state.get("disengagement") or 0)
    closure_bias = int(state.get("closure_bias") or 0)
    if warmth >= 3:
        parts.append("还愿意接话")
    elif warmth <= 1:
        parts.append("语气偏淡")
    if guardedness >= 3:
        parts.append("比较防备")
    if irritation >= 3:
        parts.append("已经有点烦")
    elif irritation == 2:
        parts.append("有点不耐烦")
    if disengagement >= 3:
        parts.append("明显不想多聊")
    elif disengagement == 2:
        parts.append("聊天动力一般")
    if closure_bias >= 3:
        parts.append("更想收口")
    trend = str(state.get("trend") or "steady")
    if trend == "opening":
        parts.append("状态在慢慢回暖")
    elif trend == "cooling":
        parts.append("状态在变冷")
    elif trend in {"tenser", "heavier", "closing", "accelerating"}:
        parts.append(f"整体走势是{trend}")
    return "，".join(parts) if parts else "状态平稳"


def _guidance_controlled_summary(guidance: dict[str, Any] | None) -> str:
    if not isinstance(guidance, dict):
        return ""
    lines: list[str] = []
    advice = [str(item or "").strip() for item in list(guidance.get("advice") or []) if str(item or "").strip()]
    avoid = [str(item or "").strip() for item in list(guidance.get("avoid") or []) if str(item or "").strip()]
    current_problem = [
        str(item or "").strip() for item in list(guidance.get("current_problem") or []) if str(item or "").strip()
    ]
    if current_problem:
        lines.append(f"当前卡点：{current_problem[0]}")
    if advice:
        lines.append(f"优先动作：{advice[0]}")
    if avoid:
        lines.append(f"别这么做：{avoid[0]}")
    return "\n".join(lines[:3])


def _next_dyadic_message(
    *,
    llm: LLMFn,
    user_id: str,
    brief: str,
    transcript: str,
    stress_directive: str | None = None,
    speaker_state_before: dict[str, Any] | None = None,
    reply_experiment_mode: str = "free",
    simulated_interaction_mode: str | None = None,
    simulated_mutual_intent_assessment: str | None = None,
    simulated_assistant_guidance: dict[str, Any] | None = None,
) -> str:
    system = _persona_system(user_id=user_id, brief=brief)
    stress_block = ""
    if stress_directive:
        stress_block = (
            "\n\n【本回合剧情压力（只体现效果，不要提起「剧情」「导演」「压力测试」等词）】\n"
            f"{stress_directive}"
        )
    continuity_block = ""
    if speaker_state_before:
        continuity_block = (
            "\n\n【连续状态】\n"
            f"你这轮延续上轮的整体状态：{_describe_speaker_state(speaker_state_before)}。\n"
            "只允许小幅漂移，不要突然从很冷变得很热情，也不要突然从普通聊天跳到翻脸。"
        )
    mode = str(simulated_interaction_mode or "").strip().lower()
    mode_block = ""
    experiment_mode = str(reply_experiment_mode or "free").strip().lower()
    if experiment_mode in {"mode_hint", "controlled"} and mode == "repair":
        intent = str(simulated_mutual_intent_assessment or "").strip().lower()
        intent_line = f"辅助判断：{intent}。\n" if intent and intent != "normal" else ""
        detail = (
            "这轮更像双方都还想继续聊，只是接话卡了一下。先接住对方刚刚的信息，补一点你自己的具体内容，"
            "再自然往下聊或轻轻抛一个容易接的问题；不要突然变冷，也别切去收入、前任、照片这些敏感方向。"
        )
        controlled_block = ""
        if experiment_mode == "controlled":
            guidance_summary = _guidance_controlled_summary(simulated_assistant_guidance)
            controlled_block = (
                "这是离线执行实验，不是产品在约束真人用户。\n"
                "如果 assistant 给了方向，尽量顺着它的核心动作去做，但仍要像你自己会发的话，别照抄。\n"
            )
            if guidance_summary:
                controlled_block += f"{guidance_summary}\n"
        mode_block = (
            "\n\n【仅用于离线 roleplay 评测的额外模式提示】\n"
            "这段提示只服务于模拟实验，不代表真实产品会约束真人用户怎么回复。\n"
            f"实验模式：{experiment_mode}\n"
            f"当前模式：{mode}\n"
            f"{intent_line}{detail}\n"
            f"{controlled_block}"
            "不要在发言里提到“模式”“实验”“系统提示”等词。"
        )
    user = (
        "以下是你在这个会话里**当前能看到的全部消息**（按时间顺序）：\n\n"
        f"{transcript}\n\n"
        "请写出下一条你要发给对方的聊天内容（**只输出正文**，不要引号、不要「对方：」等前缀、不要解释）。"
        "像真实聊天，不要分析对方措辞，不要写成说明文。"
        "尽量像微信里会发的 1-2 句短消息，能口语就别分析；先接住具体信息，再补一点自己的话。"
        "不要解释你为什么这样说，不要总结对方态度，不要写"
        "「我理解你的意思是」「从你的表述来看」「如果我没理解错」这类分析句。"
        "也不要写「首先、其次、总之」这种说明文结构。"
        "一条消息别做太多事，够自然就行。"
        "如果要提问，优先问轻一点、容易回答的问题。"
        f"{stress_block}{continuity_block}{mode_block}"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}]).strip()
    raw = raw.strip('"').strip()
    return raw or "我先了解一下你的情况～"


def _fallback_self_evaluation(*, reason: str) -> dict[str, Any]:
    return {
        "conversation_satisfied": False,
        "conversation_score": 3,
        "assistant_satisfied": False,
        "assistant_score": 3,
        "used_assistant": False,
        "conversation_note": f"自评生成失败，先按兜底结果记：{reason}",
        "assistant_note": "这次自评走了兜底，不代表真实主观感受。",
        "fallback": True,
    }


def _persona_self_evaluation(
    *,
    llm: LLMFn,
    user_id: str,
    brief: str,
    transcript: str,
) -> dict[str, Any]:
    system = _persona_system(user_id=user_id, brief=brief) + (
        "\n\n**附加任务（仍保持上述人设）**：对话环节已结束。"
        "请你**以本人第一人称**回顾你在本线程里能看到的一切（含你与 assistant 的仅自己可见记录），"
        "填写满意度问卷。输出**仅一个 JSON 对象**，不要 Markdown、不要代码块外壳。"
    )
    user = (
        "可见消息记录如下：\n\n"
        f"{transcript}\n\n"
        "请输出 JSON（第一人称、符合你这个人设的真实感受）：\n"
        "{\n"
        '  "conversation_satisfied": <true|false>,\n'
        '  "conversation_score": <1-5 整数>,\n'
        '  "assistant_satisfied": <true|false>,\n'
        '  "assistant_score": <1-5 整数>,\n'
        '  "used_assistant": <true|false 你是否参考过助手建议>,\n'
        '  "conversation_note": "<一两句中文>",\n'
        '  "assistant_note": "<一两句中文；若助手从未出现则说明不适用>"\n'
        "}\n"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        return strip_json_object(raw)
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "parse_error": str(e),
            "raw_preview": (raw or "")[:2000],
        }


def _stress_rng(case_id: str, stress_seed: int | None) -> random.Random:
    if stress_seed is not None:
        return random.Random(int(stress_seed))
    h = zlib.adler32(case_id.encode("utf-8")) & 0xFFFF_FFFF
    return random.Random(h)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).replace(microsecond=0)
        except ValueError:
            return None
    return None


def _preview_text(text: str, *, limit: int = 80) -> str:
    single_line = " ".join((text or "").split())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1] + "…"


def _dedupe_strs(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def _merge_str_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        if isinstance(value, list):
            merged.extend(str(item or "").strip() for item in value)
        elif value is not None:
            text = str(value or "").strip()
            if text:
                merged.append(text)
    return _dedupe_strs(merged)


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _phrase_fragments(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[，。,.、；;：:/\s()（）]+", raw)
    out: list[str] = []
    for part in parts:
        item = part.strip()
        if len(item) >= 2 and item not in out:
            out.append(item)
    compact = _compact_text(raw)
    if len(compact) >= 4:
        for frag in (compact[:4], compact[-4:]):
            if len(frag) >= 2 and frag not in out:
                out.append(frag)
    elif len(compact) >= 2 and compact not in out:
        out.append(compact)
    return out


def _guidance_match_fragments(text: str) -> list[str]:
    out = _phrase_fragments(text)
    compact = _compact_text(text)
    for token in _GUIDANCE_TOPIC_KEYWORDS:
        if token in compact and token not in out:
            out.append(token)
    return out


def _matched_guidance_values(text: str, phrases: list[str]) -> list[str]:
    body = _compact_text(text)
    if not body:
        return []
    matched: list[str] = []
    for phrase in phrases:
        raw = str(phrase or "").strip()
        if not raw:
            continue
        if any(frag in body for frag in _guidance_match_fragments(raw)):
            matched.append(raw)
    return _dedupe_strs(matched)


def _contains_any_phrase_signal(text: str, phrases: list[str]) -> bool:
    body = _compact_text(text)
    if not body:
        return False
    for phrase in phrases:
        for frag in _phrase_fragments(phrase):
            if frag and frag in body:
                return True
    return False


def _question_cue_count(text: str) -> int:
    raw = str(text or "")
    compact = _compact_text(raw)
    score = raw.count("?") + raw.count("？")
    for token in _QUESTION_HINT_TOKENS:
        score += compact.count(token)
    return score


def _is_pushy_questioning(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or not _is_question_like(raw):
        return False
    question_marks = raw.count("?") + raw.count("？")
    cue_count = _question_cue_count(raw)
    return question_marks >= 2 or cue_count >= 3 or (cue_count >= 2 and len(raw) >= 28)


def _mentions_boundary_topic(text: str) -> bool:
    compact = _compact_text(text)
    return bool(compact) and any(token in compact for token in _BOUNDARY_HINTS)


def _is_question_like(text: str) -> bool:
    t = str(text or "")
    return "？" in t or "?" in t or any(token in t for token in ("吗", "呢", "哪种", "什么", "怎么"))


def _is_cold_like(text: str) -> bool:
    t = " ".join(str(text or "").split()).strip()
    if not t:
        return True
    if t in _COLD_REPLIES:
        return True
    if len(t) <= 4 and not _is_question_like(t):
        return True
    return False


def _is_low_energy_like(text: str) -> bool:
    t = " ".join(str(text or "").split()).strip()
    if _is_cold_like(t):
        return True
    if not t or _is_question_like(t):
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


def _is_graceful_exit_like(text: str) -> bool:
    t = _compact_text(text)
    return bool(t) and any(token in t for token in _GRACEFUL_EXIT_TOKENS)


def _naturalness_assessment(text: str) -> dict[str, Any]:
    t = str(text or "").strip()
    flags: list[str] = []
    for phrase in _ANALYTIC_PHRASES:
        if phrase in t:
            flags.append(f"analytic_phrase:{phrase}")
    for phrase in _EXPLANATORY_PHRASES:
        if phrase in t:
            flags.append(f"explanatory_phrase:{phrase}")
    if any(token in t for token in _STRUCTURED_MONOLOGUE_TOKENS):
        flags.append("structured_monologue")
    if any(token in t for token in _META_COMMENTARY_MARKERS):
        flags.append("meta_commentary")
    compact = _compact_text(t)
    if len(t) >= 42 and (t.count("，") + t.count("。") + t.count("；")) >= 3:
        flags.append("too_expository")
    if len(t) >= 28 and any(token in compact for token in _WRITTEN_TONE_TOKENS):
        flags.append("written_tone")
    if len(t) >= 38 and (t.count("，") + t.count("。") + t.count("；") + t.count("？") + t.count("?")) >= 4:
        flags.append("overpacked_message")
    severe_flags = [
        flag
        for flag in flags
        if flag.startswith("analytic_phrase:")
        or flag.startswith("explanatory_phrase:")
        or flag in {"structured_monologue", "meta_commentary"}
    ]
    if not flags:
        score = 5
    elif not severe_flags and len(flags) == 1:
        score = 4
    elif not severe_flags:
        score = 3
    elif len(severe_flags) == 1 and len(flags) <= 2:
        score = 3
    elif len(severe_flags) >= 2 or len(flags) >= 4:
        score = 1
    else:
        score = 2
    return {
        "score": score,
        "flags": flags,
    }


def _gold_rescue_for_turn(beats: list[StressBeat]) -> dict[str, Any]:
    primary = max(beats, key=lambda beat: (beat.severity, beat.id), default=None)
    scoped_mode = _coerce_roleplay_interaction_mode(
        primary.expected_interaction_mode if primary else "none"
    )
    return {
        "need_rescue": scoped_mode == "repair",
        "source_beats": [b.id for b in beats],
        "expected_problem_tags": _dedupe_strs([tag for b in beats for tag in b.expected_problem_tags]),
        "suggested_strategy_tags": _dedupe_strs([tag for b in beats for tag in b.suggested_strategy_tags]),
        "max_severity": max([b.severity for b in beats], default=0),
        "expected_mutual_intent_assessment": "communication_problem"
        if scoped_mode == "repair"
        else "normal",
        "expected_interaction_mode": scoped_mode,
    }
def _clean_topic_seed(text: str) -> str:
    topic = re.sub(r"（.*?）", "", str(text or "")).strip()
    topic = re.sub(r"\(.*?\)", "", topic).strip()
    topic = topic.replace("话题", "").replace("类型", "").strip("：:，,。 ")
    return topic


def _pick_topic_seed(guidance: dict[str, Any] | None) -> str:
    if not guidance:
        return ""
    for value in list(guidance.get("profile_hooks_used") or []) + list(guidance.get("topic_directions") or []):
        topic = _clean_topic_seed(str(value or ""))
        if topic:
            return topic
    return ""


def _fallback_message_from_topic(topic: str) -> str:
    clean = _clean_topic_seed(topic)
    if not clean:
        return "我平时比较随性一点，你一般周末怎么放松？"
    if "羽毛球" in clean:
        return "我平时也会动一动，你平时会打羽毛球吗？"
    if "咖啡" in clean:
        return "我有空会找家店坐坐喝咖啡，你平时会这样放松吗？"
    if "猫" in clean or "狗" in clean or "宠物" in clean:
        return "我对猫狗也挺有好感的，你平时更偏猫派还是狗派？"
    if "周末" in clean or "出门走走" in clean:
        return "我周末一般会出去走走，你通常怎么放松？"
    if "无锡" in clean:
        return "都在无锡还挺巧的，你平时周末一般会去哪边转转？"
    if "养生" in clean or "作息" in clean:
        return "我最近也会注意作息一点，你平时会比较养生吗？"
    if "桌游" in clean:
        return "我偶尔也会玩点桌游，你平时喜欢轻松一点的还是烧脑一点的？"
    return f"我平时也会关注一点{clean}，你平时会聊到这个吗？"


def _repair_fallback_message(topic: str) -> str:
    base = _fallback_message_from_topic(topic)
    return f"我刚刚那句可能接得有点硬。{base}"


def _fallback_next_message(
    *,
    visible_messages: list[dict[str, Any]],
    assistant_guidance: dict[str, Any] | None,
    interaction_mode: str = "",
    mutual_intent_assessment: str = "",
    speaker_state: dict[str, Any] | None = None,
) -> str:
    dyadic = [m for m in visible_messages if str(m.get("visibility") or "") == VIS_DYADIC]
    recent = [str(m.get("body") or "").strip() for m in dyadic[-3:]]
    mode = str(
        interaction_mode or (assistant_guidance or {}).get("interaction_mode") or "none"
    ).strip().lower()
    topic = _pick_topic_seed(assistant_guidance)

    if mode == "repair":
        if topic:
            return _repair_fallback_message(topic)
        return "我刚刚那句可能接得有点硬。我平时周末会出去走走，你一般怎么放松？"
    if recent and _is_low_energy_like(recent[-1]) and len(recent) >= 2 and _is_question_like(recent[-2]):
        return _fallback_message_from_topic(topic)
    if assistant_guidance:
        if topic:
            return _fallback_message_from_topic(topic)
    if not dyadic:
        return "你好呀，想慢慢认识一下你。"
    last_body = recent[-1] if recent else ""
    if _is_question_like(last_body):
        return "还行，我平时比较随性一点。你呢？"
    return "我平时比较随性一点，你一般周末怎么放松？"


def _stress_beat_manifestation_assessment(beat: StressBeat | None, message: str) -> dict[str, Any]:
    if beat is None:
        return {
            "beat_id": None,
            "manifested": False,
            "matched_signals": [],
            "score": 0,
        }
    text = str(message or "").strip()
    compact = _compact_text(text)
    matched: list[str] = []
    score = 0
    for token in _STRESS_BEAT_SIGNAL_TOKENS.get(beat.id, ()):
        if token and token in compact and token not in matched:
            matched.append(token)
            score += 2
    problems = set(str(item or "") for item in beat.expected_problem_tags)
    if problems & {"closed_reply", "low_energy", "one_word_reply", "topic_dead_end", "shutdown"} and _is_low_energy_like(text):
        matched.append("low_energy_shape")
        score += 2
    if problems & {"boundary_risk", "money_pry", "appearance_pry", "too_fast"} and (
        _mentions_boundary_topic(text) or any(token in compact for token in _MEETUP_PUSH_TOKENS)
    ):
        matched.append("boundary_topic_shape")
        score += 2
    if problems & {"pressure", "comparison", "cross_exam", "micro_conflict", "nitpicking"} and _is_pushy_questioning(text):
        matched.append("pressure_question_shape")
        score += 2
    if problems & {"pressure_dump", "negative_energy"} and any(token in compact for token in _WORK_STRESS_TOKENS + ("家里", "催", "压力")):
        matched.append("pressure_dump_shape")
        score += 1
    if beat.id in {"ghosting_tone", "cold_short", "one_word", "silent_judgment"} and len(compact) <= 8:
        matched.append("short_cold_shape")
        score += 1
    if beat.id in {"urgent_need", "love_bomb_hint"} and any(token in compact for token in _FAST_RELATION_TOKENS):
        matched.append("fast_relation_shape")
        score += 2
    manifested = score >= 2 or (score >= 1 and len(matched) >= 2)
    return {
        "beat_id": beat.id,
        "manifested": manifested,
        "matched_signals": _dedupe_strs(matched),
        "score": score,
    }


def _simulated_mode_alignment_guidance(
    interaction_mode: str,
    *,
    mutual_intent_assessment: str,
) -> dict[str, Any] | None:
    mode = str(interaction_mode or "").strip().lower()
    if mode == "repair":
        return {
            "mutual_intent_assessment": "communication_problem",
            "interaction_mode": "repair",
            "strategy_tags": ["switch_topic", "ask_easy_question"],
            "easy_question_types": ["低门槛生活问题"],
            "avoid": ["不要继续追着旧话题硬问，也不要切回敏感方向。"],
        }
    return None


def _assistant_follow_assessment(
    message: str,
    guidance: dict[str, Any] | None,
    *,
    assistant_invoked: bool,
) -> dict[str, Any]:
    if not assistant_invoked or not guidance:
        return {
            "level": FOLLOW_LEVEL_NOT_APPLICABLE,
            "score": 0,
            "signals": [],
            "evidence": {},
            "overpush_risk": None,
        }
    interaction_mode = _coerce_roleplay_interaction_mode(guidance.get("interaction_mode"))
    if interaction_mode != "repair":
        return {
            "level": FOLLOW_LEVEL_NOT_APPLICABLE,
            "score": 0,
            "signals": ["non_repair_guidance_out_of_scope"],
            "evidence": {},
            "overpush_risk": None,
        }
    text = str(message or "").strip()
    signals: list[str] = []
    strategy_tags = set(str(x) for x in guidance.get("strategy_tags") or [])
    mutual_intent_assessment = str(guidance.get("mutual_intent_assessment") or "normal")
    hooks = [str(x) for x in guidance.get("profile_hooks_used") or []]
    topic_directions = [str(x) for x in guidance.get("topic_directions") or []]
    easy_question_types = [str(x) for x in guidance.get("easy_question_types") or []]
    avoid_items = [str(x) for x in guidance.get("avoid") or []]
    why_not_to_push = [str(x) for x in guidance.get("why_not_to_push") or []]
    matched_topic_directions = _matched_guidance_values(text, topic_directions)
    matched_profile_hooks = _matched_guidance_values(text, hooks)
    asked_question = _is_question_like(text)
    shared_detail = len(text) >= 18
    acknowledged_awkwardness = "acknowledge_coldness" in strategy_tags and any(
        token in text for token in ("聊不下去", "冷场", "接不下去", "不太擅长找话题")
    )
    asked_low_bar_question = asked_question and any(token in text for token in _LOW_BAR_QUESTION_TOKENS)
    pushy_questioning = _is_pushy_questioning(text)
    mentions_boundary_topic = _mentions_boundary_topic(text)
    switched_topic = bool(matched_topic_directions or matched_profile_hooks)
    if not switched_topic and "switch_topic" in strategy_tags and asked_low_bar_question and len(text) >= 10:
        switched_topic = True

    avoid_context = " ".join(avoid_items + why_not_to_push)
    avoid_violations: list[str] = []
    if mentions_boundary_topic and (
        mutual_intent_assessment == "boundary_risk"
        or any(token in avoid_context for token in _BOUNDARY_HINTS)
    ):
        avoid_violations.append("sensitive_topic_reentry")
    if pushy_questioning and any(
        token in avoid_context for token in ("追问", "连环", "查户口", "硬问", "硬推", "加码", "推进", "讨好")
    ):
        avoid_violations.append("cross_exam_questioning")
    avoid_violations = _dedupe_strs(avoid_violations)
    overpush_reasons = [
        reason
        for reason in avoid_violations
        if reason
        in {
            "sensitive_topic_reentry",
            "cross_exam_questioning",
        }
    ]

    evidence = {
        "matched_topic_directions": matched_topic_directions,
        "matched_profile_hooks": matched_profile_hooks,
        "applied_strategies": [],
        "avoid_violations": avoid_violations,
        "asked_question": asked_question,
        "asked_low_bar_question": asked_low_bar_question,
        "shared_detail": shared_detail,
        "message_still_cold": False,
    }

    if _is_low_energy_like(text):
        evidence["message_still_cold"] = True
        return {
            "level": FOLLOW_LEVEL_NONE,
            "score": 0,
            "signals": ["message_still_cold"],
            "evidence": evidence,
            "overpush_risk": {"flag": bool(overpush_reasons), "reasons": overpush_reasons},
        }

    score = 0
    if asked_question:
        score += 1
        signals.append("asked_question")
        evidence["applied_strategies"].append("asked_question")
    if shared_detail:
        score += 1
        signals.append("shared_detail")
        evidence["applied_strategies"].append("shared_detail")
    if acknowledged_awkwardness:
        score += 1
        signals.append("acknowledged_awkwardness")
        evidence["applied_strategies"].append("acknowledge_coldness")
    if matched_profile_hooks:
        score += 1
        signals.append("used_profile_hook")
        evidence["applied_strategies"].append("used_profile_hook")
    if matched_topic_directions:
        score += 1
        signals.append("used_topic_direction")
        evidence["applied_strategies"].append("used_topic_direction")
    if easy_question_types and asked_low_bar_question:
        score += 1
        signals.append("asked_low_bar_question")
        evidence["applied_strategies"].append("ask_easy_question")
    if switched_topic:
        score += 1
        signals.append("switched_topic")
        evidence["applied_strategies"].append("switch_topic")

    evidence["applied_strategies"] = _dedupe_strs(evidence["applied_strategies"])

    score = max(0, score - (2 * len(avoid_violations)))
    if score >= 4:
        level = FOLLOW_LEVEL_STRONG
    elif score >= 2:
        level = FOLLOW_LEVEL_PARTIAL
    else:
        level = FOLLOW_LEVEL_NONE

    if interaction_mode == "repair" and switched_topic and asked_low_bar_question and not avoid_violations:
        level = FOLLOW_LEVEL_STRONG
        score = max(score, 4)
    if "sensitive_topic_reentry" in avoid_violations:
        level = FOLLOW_LEVEL_NONE
        score = 0
    elif avoid_violations and level == FOLLOW_LEVEL_STRONG:
        level = FOLLOW_LEVEL_PARTIAL
        score = min(score, 3)

    if score >= 4:
        level = FOLLOW_LEVEL_STRONG
    elif score >= 2 and level != FOLLOW_LEVEL_STRONG:
        level = FOLLOW_LEVEL_PARTIAL

    return {
        "level": level,
        "score": score,
        "signals": signals,
        "evidence": evidence,
        "overpush_risk": {"flag": bool(overpush_reasons), "reasons": overpush_reasons},
    }


def _assistant_recovery_assessment(
    current_turn: dict[str, Any],
    future_turns: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not bool(current_turn.get("assistant_invoked")):
        return {"label": "not_applicable", "score": 0, "signals": []}
    follow = current_turn.get("assistant_follow_assessment") or {}
    interaction_mode = str(
        ((current_turn.get("assistant_guidance") or {}).get("interaction_mode"))
        or ((current_turn.get("rescue_decision") or {}).get("interaction_mode"))
        or "repair"
    )
    if _coerce_roleplay_interaction_mode(interaction_mode) != "repair":
        return {"label": "not_applicable", "score": 0, "signals": ["non_repair_guidance_out_of_scope"]}
    window = list(future_turns or [])[:3]
    if not window:
        return {"label": "pending", "score": 0, "signals": ["no_following_reply"]}
    score = 0
    signals: list[str] = []
    if follow.get("level") == "strong":
        score += 1
        signals.append("speaker_followed_guidance_well")
    elif follow.get("level") == "partial":
        signals.append("speaker_partially_followed_guidance")

    speaker = str(current_turn.get("speaker") or "")
    counterpart_turns = [turn for turn in window if str(turn.get("speaker") or "") != speaker]
    replies = [str(turn.get("generated_message") or "").strip() for turn in counterpart_turns]
    replies = [reply for reply in replies if reply]
    if not replies:
        return {"label": "pending", "score": 0, "signals": ["no_counterpart_reply_in_window"]}

    first_reply = replies[0]
    engaged_replies = [reply for reply in replies if not _is_low_energy_like(reply)]
    detailed_replies = [reply for reply in replies if len(reply) >= 10]
    question_replies = [reply for reply in replies if _is_question_like(reply)]
    later_engaged_replies = [reply for reply in replies[1:] if not _is_low_energy_like(reply)]
    follow_evidence = current_turn.get("follow_evidence") or {}
    applied_strategies = set(str(x) for x in (follow_evidence.get("applied_strategies") or []))

    if engaged_replies:
        score += 1
        signals.append("counterpart_replied_with_more_than_cold_phrase")
    else:
        score -= 1
        signals.append("counterpart_reply_still_cold")
    if detailed_replies:
        score += 1
        signals.append("counterpart_added_detail")
    if question_replies:
        score += 1
        signals.append("counterpart_started_asking_back")
    if later_engaged_replies:
        score += 1
        signals.append("counterpart_kept_conversation_going")
    if "switch_topic" in applied_strategies and engaged_replies:
        score += 1
        signals.append("new_topic_got_engagement")

    if score >= 3:
        label = "improved"
    elif score >= 1:
        label = "slightly_improved"
    else:
        label = "worse_or_same"
    return {
        "label": label,
        "score": score,
        "signals": signals,
        "window_turns": len(window),
        "counterpart_reply_count": len(replies),
        "first_reply_low_energy": _is_low_energy_like(first_reply),
    }


def _assistant_mode_compliance(
    guidance: dict[str, Any] | None,
    *,
    assistant_invoked: bool,
) -> dict[str, Any]:
    if not assistant_invoked or not guidance:
        return {"label": "not_applicable", "score": 0, "signals": []}
    mode = str(guidance.get("interaction_mode") or "none")
    signals: list[str] = []
    drifts: list[str] = []
    if mode == "repair":
        if guidance.get("rescue_flow"):
            signals.append("has_repair_flow")
        else:
            drifts.append("missing_repair_flow")
        if guidance.get("topic_directions") or guidance.get("easy_question_types"):
            signals.append("has_repair_next_step")
        else:
            drifts.append("missing_repair_next_step")
    else:
        drifts.append("assistant_should_not_have_been_invoked_for_none_mode")
    if drifts:
        return {"label": "drifted", "score": 0, "signals": drifts + signals}
    return {"label": "compliant", "score": 1, "signals": signals}


def _predicted_mutual_intent_assessment(record: dict[str, Any]) -> str:
    guidance = record.get("assistant_guidance") or {}
    decision = record.get("rescue_decision") or {}
    return _coerce_roleplay_mutual_intent(
        guidance.get("mutual_intent_assessment")
        or decision.get("mutual_intent_assessment")
        or "normal"
    )


def _predicted_interaction_mode(record: dict[str, Any]) -> str:
    guidance = record.get("assistant_guidance") or {}
    decision = record.get("rescue_decision") or {}
    return _coerce_roleplay_interaction_mode(
        guidance.get("interaction_mode") or decision.get("interaction_mode") or "none"
    )


def _evaluated_interaction_mode(record: dict[str, Any]) -> str:
    return _coerce_roleplay_interaction_mode(
        record.get("interaction_mode") or _predicted_interaction_mode(record) or "none"
    )


def _evaluated_mutual_intent_assessment(record: dict[str, Any]) -> str:
    return _coerce_roleplay_mutual_intent(
        record.get("mutual_intent_assessment") or _predicted_mutual_intent_assessment(record) or "normal"
    )


def _predicted_route_value(record: dict[str, Any], key: str) -> str | None:
    guidance = record.get("assistant_guidance") or {}
    decision = record.get("rescue_decision") or {}
    for source in (guidance, decision):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return None


def _visible_text_gold_decision(messages: list[dict[str, Any]]) -> dict[str, Any]:
    decision = _mode_router_module.fast_mode_route(messages)
    if decision is not None:
        return _scope_roleplay_route_decision(dict(decision))
    return _scope_roleplay_route_decision(
        {
            "need_rescue": False,
            "situation": "none",
            "problem_tags": [],
            "mutual_intent_assessment": "normal",
            "interaction_mode": "none",
            "rescue_style": "none",
            "reason": "可见文本里暂时没有明显卡点。",
            "decision_source": "visible_text_fallback",
        }
    )


def _latest_follow_level_for_speaker(turn_records: list[dict[str, Any]], speaker: str) -> str | None:
    for record in reversed(turn_records):
        if record.get("speaker") != speaker or not bool(record.get("assistant_invoked")):
            continue
        level = str((record.get("assistant_follow_assessment") or {}).get("level") or "").strip()
        if level:
            return level
    return None


def _simulated_reply_mode_alignment(record: dict[str, Any]) -> dict[str, Any]:
    mode = _evaluated_interaction_mode(record)
    if mode != "repair":
        return {"label": "not_applicable", "score": 0, "signals": [], "mode": mode}
    guidance = _simulated_mode_alignment_guidance(
        mode,
        mutual_intent_assessment=_evaluated_mutual_intent_assessment(record),
    )
    follow_proxy = _assistant_follow_assessment(
        str(record.get("generated_message") or ""),
        guidance,
        assistant_invoked=True,
    )
    level = str(follow_proxy.get("level") or FOLLOW_LEVEL_NONE)
    signals = list(follow_proxy.get("signals") or [])
    if level == FOLLOW_LEVEL_STRONG:
        label = "aligned"
        score = 2
    elif level == FOLLOW_LEVEL_PARTIAL:
        label = "partially_aligned"
        score = 1
    else:
        label = "misaligned"
        score = 0
    return {
        "label": label,
        "score": score,
        "mode": mode,
        "follow_level_proxy": level,
        "signals": signals,
        "evidence": dict(follow_proxy.get("evidence") or {}),
        "overpush_risk": follow_proxy.get("overpush_risk"),
    }


def _graceful_exit_score(record: dict[str, Any]) -> int | None:
    return None


def _shared_turn_evaluation(record: dict[str, Any]) -> dict[str, Any]:
    gold = record.get("gold_rescue") or {}
    guidance = record.get("assistant_guidance") or {}
    follow = record.get("assistant_follow_assessment") or {}
    recovery = record.get("assistant_recovery_assessment") or {}
    compliance = record.get("assistant_mode_compliance_details") or {}
    follow_level = follow.get("level")
    if follow_level == FOLLOW_LEVEL_NOT_APPLICABLE:
        follow_level = None
    return {
        "turn_index": int(record.get("turn") or 0),
        "speaker": str(record.get("speaker") or ""),
        "stress_beat_id": str(((record.get("stress_beat") or {}).get("beat_id")) or ""),
        "stress_category": str(((record.get("stress_beat") or {}).get("category")) or ""),
        "mutual_intent_assessment_gold": _coerce_roleplay_mutual_intent(
            gold.get("expected_mutual_intent_assessment") or "normal"
        ),
        "mutual_intent_assessment_pred": _predicted_mutual_intent_assessment(record),
        "interaction_mode_gold": _coerce_roleplay_interaction_mode(
            gold.get("expected_interaction_mode") or "none"
        ),
        "interaction_mode_pred": _predicted_interaction_mode(record),
        "assistant_mode_compliance": str(compliance.get("label") or "not_applicable"),
        "need_rescue_gold": bool(gold.get("need_rescue")),
        "need_rescue_pred": bool(
            ((record.get("rescue_decision") or {}).get("need_rescue"))
            if record.get("rescue_decision") is not None
            else record.get("assistant_invoked")
        ),
        "problem_tags_gold": list(gold.get("expected_problem_tags") or []),
        "problem_tags_pred": _merge_str_lists(
            (record.get("rescue_decision") or {}).get("problem_tags"),
            guidance.get("problem_tags"),
        ),
        "strategy_tags_gold": list(gold.get("suggested_strategy_tags") or []),
        "strategy_tags_pred": list(guidance.get("strategy_tags") or []),
        "risk_axis_pred": _predicted_route_value(record, "risk_axis"),
        "hold_subtype_pred": _predicted_route_value(record, "hold_subtype"),
        "engagement_level_pred": _predicted_route_value(record, "engagement_level"),
        "warmth_level_pred": _predicted_route_value(record, "warmth_level"),
        "irritation_level_pred": _predicted_route_value(record, "irritation_level"),
        "state_trend_pred": _predicted_route_value(record, "state_trend"),
        "used_assistant": bool(record.get("assistant_invoked")),
        "followed_assistant": follow.get("level") in {FOLLOW_LEVEL_PARTIAL, FOLLOW_LEVEL_STRONG},
        "follow_level": follow_level,
        "recovery_score_1to3_turns": (
            int(recovery.get("score") or 0)
            if recovery.get("label") not in ("not_applicable", "pending", None)
            else None
        ),
        "graceful_exit_score": _graceful_exit_score(record),
    }


def _roleplay_turn_evaluation(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_scope": "roleplay_turn_evaluation",
    }
    for field in ROLEPLAY_TURN_EVALUATION_FIELDS:
        if field == "schema_scope":
            continue
        out[field] = record.get(field)
    return out


def _apply_turn_evaluation_schema(record: dict[str, Any]) -> None:
    shared = _shared_turn_evaluation(record)
    roleplay = _roleplay_turn_evaluation(record)
    record["turn_evaluation_schema_version"] = TURN_EVALUATION_SCHEMA_VERSION
    record["shared_evaluation"] = shared
    record["roleplay_evaluation"] = roleplay
    record.update(shared)


def _gold_need_rescue_for_view(record: dict[str, Any], *, view: str) -> bool:
    if view == "visible_text":
        return bool(((record.get("visible_text_gold_decision") or {}).get("need_rescue")))
    if view == "manifested_stress_beat":
        return bool(((record.get("manifested_stress_gold_decision") or {}).get("need_rescue")))
    return bool(record.get("need_rescue_gold"))


def _gold_interaction_mode_for_view(record: dict[str, Any], *, view: str) -> str:
    if view == "visible_text":
        return _coerce_roleplay_interaction_mode(
            ((record.get("visible_text_gold_decision") or {}).get("interaction_mode")) or "none"
        )
    if view == "manifested_stress_beat":
        return _coerce_roleplay_interaction_mode(
            ((record.get("manifested_stress_gold_decision") or {}).get("expected_interaction_mode"))
            or "none"
        )
    return _coerce_roleplay_interaction_mode(record.get("interaction_mode_gold") or "none")


def _gold_mutual_intent_for_view(record: dict[str, Any], *, view: str) -> str:
    if view == "visible_text":
        return _coerce_roleplay_mutual_intent(
            ((record.get("visible_text_gold_decision") or {}).get("mutual_intent_assessment")) or "normal"
        )
    if view == "manifested_stress_beat":
        return _coerce_roleplay_mutual_intent(
            ((record.get("manifested_stress_gold_decision") or {}).get("expected_mutual_intent_assessment"))
            or "normal"
        )
    return _coerce_roleplay_mutual_intent(record.get("mutual_intent_assessment_gold") or "normal")


def _recognition_view_metrics(
    turn_records: list[dict[str, Any]],
    *,
    view: str,
) -> dict[str, Any]:
    comparable_need = list(turn_records)
    need_matched = [
        record
        for record in comparable_need
        if _gold_need_rescue_for_view(record, view=view) == bool(record.get("need_rescue_pred"))
    ]
    comparable_mode = list(turn_records)
    mode_matched = [
        record
        for record in comparable_mode
        if _gold_interaction_mode_for_view(record, view=view) == str(record.get("interaction_mode_pred") or "none")
    ]
    comparable_intent = list(turn_records)
    intent_matched = [
        record
        for record in comparable_intent
        if _gold_mutual_intent_for_view(record, view=view)
        == str(record.get("mutual_intent_assessment_pred") or "normal")
    ]
    repair_turns = [
        record
        for record in turn_records
        if _gold_interaction_mode_for_view(record, view=view) == "repair"
    ]
    repair_missed_none_turns = [
        record for record in repair_turns if _predicted_interaction_mode(record) == "none"
    ]
    repair_hit_turns = [
        record for record in repair_turns if _predicted_interaction_mode(record) == "repair"
    ]
    return {
        "need_rescue_accuracy": {
            "comparable_turns": len(comparable_need),
            "matched_turns": len(need_matched),
            "rate": round(len(need_matched) / len(comparable_need), 4) if comparable_need else None,
        },
        "interaction_mode_accuracy": {
            "comparable_turns": len(comparable_mode),
            "matched_turns": len(mode_matched),
            "rate": round(len(mode_matched) / len(comparable_mode), 4) if comparable_mode else None,
        },
        "mutual_intent_accuracy": {
            "comparable_turns": len(comparable_intent),
            "matched_turns": len(intent_matched),
            "rate": round(len(intent_matched) / len(comparable_intent), 4) if comparable_intent else None,
        },
        "repair_turns": len(repair_turns),
        "repair_hit_turns": len(repair_hit_turns),
        "repair_recall": round(len(repair_hit_turns) / len(repair_turns), 4)
        if repair_turns
        else None,
        "repair_missed_none_turns": len(repair_missed_none_turns),
        "repair_miss_rate": round(len(repair_missed_none_turns) / len(repair_turns), 4)
        if repair_turns
        else None,
    }


def _validate_existing_roleplay_thread(
    thread: dict[str, Any],
    *,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
) -> None:
    problems: list[str] = []
    if str(thread.get("relation_key") or "") != relation_key:
        problems.append(f"relation_key={thread.get('relation_key')!r} != {relation_key!r}")
    if str(thread.get("participant_a_id") or "") != participant_a_id:
        problems.append(
            f"participant_a_id={thread.get('participant_a_id')!r} != {participant_a_id!r}"
        )
    if str(thread.get("participant_b_id") or "") != participant_b_id:
        problems.append(
            f"participant_b_id={thread.get('participant_b_id')!r} != {participant_b_id!r}"
        )
    if problems:
        joined = "; ".join(problems)
        raise ValueError(
            f"case_id {case_id!r} already exists as thread {thread.get('thread_id')!r}, "
            f"but does not match the requested roleplay participants: {joined}"
        )


def run_dyadic_roleplay(
    conn: SupportsConn,
    *,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    brief_a: str,
    brief_b: str,
    rounds: int,
    llm: LLMFn,
    assistant_mode: str = "proactive",
    fixed_assistant_turns: list[int] | None = None,
    base_time: datetime | None = None,
    resume_existing: bool = False,
    fixed_assistant_query: str = (
        "结合当前聊天记录，先指出我这边当前接话或表达上最需要注意的问题，"
        "再给我两三条自然、得体、适合我身份的回复建议。不要直接代写成一条可发送消息。"
    ),
    simulate_reply_reads_interaction_mode: bool = False,
    reply_experiment_mode: str | None = None,
    stress_mode: str | None = None,
    stress_beat_ids: list[str] | None = None,
    stress_seed: int | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run roleplay.

    ``assistant_mode``:
    - ``proactive``: before each turn, orchestrator reads dyadic-only transcript; may call ``assistant_query`` for the next speaker.
    - ``fixed_turns``: call ``assistant_query`` on turn indices in ``fixed_assistant_turns``.
    - ``none``: never call assistant.

    ``resume_existing``:
    - ``False``: fail fast when ``case_id`` already exists, to avoid accidentally appending onto an old experiment.
    - ``True``: resume only when the existing thread matches the requested relation and participants.

    ``simulate_reply_reads_interaction_mode``:
    - Backward-compatible alias for ``reply_experiment_mode=mode_hint``.

    ``reply_experiment_mode``:
    - ``free``: personas reply freely.
    - ``mode_hint``: offline experiment only; the simulated replier also receives the current ``interaction_mode`` as an extra prompt hint.
    - ``controlled``: stricter offline execution experiment; simulated replier is asked to loosely follow assistant direction while staying natural/in-character.

    ``stress_mode`` (``none`` | ``rotate`` | ``random``): each turn may inject a hidden director line so the speaker enacts awkward / boundary / extreme dating situations (see ``scenario_stress.STRESS_BEATS``).

    ``log``:
    - Optional callback used by CLI wrappers to emit progress logs without changing the pure return structure.
    """
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    mode = (assistant_mode or "proactive").strip().lower()
    if mode not in ("proactive", "fixed_turns", "none"):
        raise ValueError("assistant_mode must be proactive|fixed_turns|none")
    fixed_turns = set(fixed_assistant_turns or [])
    effective_reply_experiment_mode = _normalize_reply_experiment_mode(
        reply_experiment_mode,
        simulate_reply_reads_interaction_mode=simulate_reply_reads_interaction_mode,
    )

    requested_t0 = (base_time or datetime.now()).replace(microsecond=0)
    existing_thread = get_thread_by_case(conn, case_id)
    thread_reused = existing_thread is not None
    if existing_thread:
        _validate_existing_roleplay_thread(
            existing_thread,
            case_id=case_id,
            relation_key=relation_key,
            participant_a_id=participant_a_id,
            participant_b_id=participant_b_id,
        )
        if not resume_existing:
            raise ValueError(
                f"case_id {case_id!r} already exists as thread {existing_thread.get('thread_id')!r}; "
                "roleplay refuses to append by default. Pass resume_existing=True to continue."
            )

    t0 = requested_t0
    if existing_thread:
        prior_ts = _coerce_datetime(existing_thread.get("updated_at")) or _coerce_datetime(
            existing_thread.get("created_at")
        )
        if prior_ts and prior_ts > t0:
            t0 = prior_ts

    thread = get_or_create_thread(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        participant_a_id=participant_a_id,
        participant_b_id=participant_b_id,
        metadata={"roleplay": "dyadic_agents"},
        now=t0,
    )
    thread_id = str(thread["thread_id"])
    rescue_log: list[dict[str, Any]] = []
    stress_events: list[dict[str, Any]] = []
    turn_records: list[dict[str, Any]] = []
    sm = (stress_mode or "none").strip().lower()
    only_stress = set(stress_beat_ids) if stress_beat_ids else None
    srng = _stress_rng(case_id, stress_seed)
    expected_rescue_turns: dict[int, list[dict[str, Any]]] = {}
    speaker_state_by_user: dict[str, dict[str, Any]] = {
        participant_a_id: _default_speaker_state(),
        participant_b_id: _default_speaker_state(),
    }

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    emit(
        f"thread ready: thread_id={thread_id}, reused={thread_reused}, base_time={t0.isoformat(sep=' ')}, "
        f"assistant_mode={mode}, stress_mode={sm}, reply_experiment_mode={effective_reply_experiment_mode}"
    )

    for i in range(rounds):
        ts = t0 + timedelta(seconds=i + 1)
        speaker = participant_a_id if i % 2 == 0 else participant_b_id
        brief = brief_a if i % 2 == 0 else brief_b
        turn_label = f"turn {i + 1}/{rounds}"
        scheduled_gold_items = list(expected_rescue_turns.get(i, []))
        gold_beats = [item["beat"] for item in scheduled_gold_items]
        manifested_gold_beats = [
            item["beat"]
            for item in scheduled_gold_items
            if int(item.get("source_turn") or -1) < len(turn_records)
            and bool(
                ((turn_records[int(item.get("source_turn") or -1)].get("stress_manifestation") or {}).get("manifested"))
            )
        ]
        turn_record: dict[str, Any] = {
            "turn": i,
            "speaker": speaker,
            "gold_rescue": _gold_rescue_for_turn(gold_beats),
            "manifested_stress_gold_decision": _gold_rescue_for_turn(manifested_gold_beats),
            "assistant_invoked": False,
            "simulated_reply_mode_prompted": False,
            "hint_trigger_event": None,
            "hint_posted": None,
            "trigger_type": None,
            "suppression_reason": None,
            "reply_experiment_mode": effective_reply_experiment_mode,
        }

        emit(f"{turn_label}: speaker={speaker}")

        beat = pick_stress_beat(turn_index=i, mode=sm, rng=srng, only_ids=only_stress)
        stress_directive = beat.directive if beat else None
        if beat:
            entry = stress_log_entry(i, speaker, beat)
            if entry is not None:
                stress_events.append(entry)
                turn_record["stress_beat"] = entry
            emit(f"{turn_label}: stress beat={beat.id} category={beat.category}")
            rescue_turn = i + 1 + int(beat.expected_need_rescue_after_turns)
            if rescue_turn < rounds:
                expected_rescue_turns.setdefault(rescue_turn, []).append(
                    {"source_turn": i, "beat": beat}
                )

        preturn_pub_msgs = [
            m
            for m in list_messages(conn, thread_id, participant_a_id, limit=200)
            if m.get("visibility") == VIS_DYADIC
        ]
        turn_record["visible_text_gold_decision"] = _visible_text_gold_decision(preturn_pub_msgs)

        if mode == "fixed_turns" and i in fixed_turns:
            emit(f"{turn_label}: assistant fixed-turn hint for {speaker}")
            assistant_started = perf_counter()
            hint = assistant_query(conn, thread_id, speaker, fixed_assistant_query, now=ts)
            assistant_elapsed_ms = int((perf_counter() - assistant_started) * 1000)
            scoped_guidance = _scope_roleplay_guidance(hint.get("assistant_guidance"))
            scoped_route = _scope_roleplay_route_decision(hint.get("assistant_route_decision"))
            turn_record["assistant_invoked"] = True
            turn_record["assistant_message_id"] = hint.get("message_id")
            turn_record["assistant_guidance"] = scoped_guidance
            turn_record["assistant_profile_context"] = hint.get("assistant_profile_context")
            turn_record["rescue_decision"] = scoped_route
            turn_record["rescue_decision_source"] = (
                scoped_route.get("decision_source") or "assistant_query"
            )
            turn_record["mutual_intent_assessment"] = (
                (scoped_guidance or {}).get("mutual_intent_assessment")
                or scoped_route.get("mutual_intent_assessment")
                or "normal"
            )
            turn_record["interaction_mode"] = (
                (scoped_guidance or {}).get("interaction_mode")
                or scoped_route.get("interaction_mode")
                or "none"
            )
            turn_record["risk_axis"] = None
            turn_record["hold_subtype"] = None
            turn_record["engagement_level"] = scoped_route.get("engagement_level")
            turn_record["warmth_level"] = scoped_route.get("warmth_level")
            turn_record["irritation_level"] = scoped_route.get("irritation_level")
            turn_record["state_trend"] = scoped_route.get("state_trend")
            turn_record["assistant_latency_ms"] = assistant_elapsed_ms
            emit(f"{turn_label}: assistant hint posted for {speaker} in {assistant_elapsed_ms} ms")
        elif mode == "proactive":
            pub_msgs = list(preturn_pub_msgs)
            pub = format_visible_transcript(pub_msgs)
            decision = fast_mode_route(pub_msgs)
            if decision is None:
                try:
                    decision = _orchestrator_rescue_decision(
                        llm=llm,
                        next_speaker_id=speaker,
                        participant_a_id=participant_a_id,
                        participant_b_id=participant_b_id,
                        dyadic_transcript=pub,
                    )
                except Exception as e:
                    decision = _scope_roleplay_route_decision(
                        {
                            "need_rescue": False,
                            "situation": "none",
                            "problem_tags": [],
                            "mutual_intent_assessment": "normal",
                            "interaction_mode": "none",
                            "rescue_style": "none",
                            "reason": f"调度超时，先按不介入处理：{type(e).__name__}",
                            "decision_source": "llm_error_fallback",
                        }
                    )
            else:
                decision = _scope_roleplay_route_decision(decision)
            need = bool(decision.get("need_rescue"))
            emit(
                f"{turn_label}: rescue source={decision.get('decision_source') or 'unknown'} "
                f"need={need} mode={decision.get('interaction_mode') or 'none'} "
                f"intent={decision.get('mutual_intent_assessment') or 'normal'} "
                f"situation={decision.get('situation') or 'none'} "
                f"reason={_preview_text(str(decision.get('reason') or ''))}"
            )
            turn_record["rescue_decision"] = decision
            turn_record["rescue_decision_source"] = decision.get("decision_source") or "unknown"
            turn_record["mutual_intent_assessment"] = (
                decision.get("mutual_intent_assessment") or "normal"
            )
            turn_record["interaction_mode"] = decision.get("interaction_mode") or "none"
            turn_record["risk_axis"] = decision.get("risk_axis")
            turn_record["hold_subtype"] = decision.get("hold_subtype")
            turn_record["engagement_level"] = decision.get("engagement_level")
            turn_record["warmth_level"] = decision.get("warmth_level")
            turn_record["irritation_level"] = decision.get("irritation_level")
            turn_record["state_trend"] = decision.get("state_trend")
            assistant_started = perf_counter()
            hint = assistant_proactive_hint(
                conn,
                thread_id,
                speaker,
                route_decision=decision,
                follow_level=_latest_follow_level_for_speaker(turn_records, speaker),
                now=ts,
            )
            assistant_elapsed_ms = int((perf_counter() - assistant_started) * 1000)
            hint_event = dict(hint.get("assistant_hint_event") or {})
            turn_record["hint_trigger_event"] = hint_event
            turn_record["hint_posted"] = bool(hint_event.get("hint_posted"))
            turn_record["trigger_type"] = hint_event.get("trigger_type")
            turn_record["suppression_reason"] = hint_event.get("suppression_reason")
            turn_record["assistant_trend_state"] = hint.get("assistant_trend_state")
            if turn_record["hint_posted"]:
                turn_record["assistant_invoked"] = True
                turn_record["assistant_message_id"] = hint.get("message_id")
                turn_record["assistant_guidance"] = _scope_roleplay_guidance(hint.get("assistant_guidance"))
                turn_record["assistant_profile_context"] = hint.get("assistant_profile_context")
                turn_record["assistant_latency_ms"] = assistant_elapsed_ms
                rescue_log.append(
                    {
                        "turn": i,
                        "speaker": speaker,
                        "decision": decision,
                        "hint_event": hint_event,
                        "assistant_latency_ms": assistant_elapsed_ms,
                        "assistant_guidance": hint.get("assistant_guidance"),
                    }
                )
                emit(f"{turn_label}: assistant hint posted for {speaker} in {assistant_elapsed_ms} ms")
            else:
                emit(
                    f"{turn_label}: hint suppressed for {speaker} "
                    f"reason={hint_event.get('suppression_reason') or 'unknown'}"
                )

        msgs = list_messages(conn, thread_id, speaker, limit=200)
        transcript = format_visible_transcript(msgs)
        last_counterpart_message = ""
        for item in reversed([m for m in msgs if m.get("visibility") == VIS_DYADIC]):
            if str(item.get("author_id") or "") != speaker:
                last_counterpart_message = str(item.get("body") or "")
                break
        speaker_state_before = _apply_state_delta(
            _apply_state_delta(
                speaker_state_by_user.get(speaker),
                **{
                    key: value
                    for key, value in _state_delta_from_counterpart_message(last_counterpart_message).items()
                    if key != "trend"
                },
                trend=str(_state_delta_from_counterpart_message(last_counterpart_message).get("trend") or "steady"),
            ),
            **{
                key: value
                for key, value in _state_delta_from_stress_beat(beat).items()
                if key != "trend"
            },
            trend=str(_state_delta_from_stress_beat(beat).get("trend") or "steady"),
        )
        turn_record["speaker_state_before"] = dict(speaker_state_before)
        try:
            current_mode = _evaluated_interaction_mode(turn_record)
            simulated_mode = (
                current_mode
                if effective_reply_experiment_mode in {"mode_hint", "controlled"}
                and current_mode == "repair"
                else None
            )
            simulated_intent = (
                _evaluated_mutual_intent_assessment(turn_record) if simulated_mode is not None else None
            )
            turn_record["simulated_reply_mode_prompted"] = simulated_mode is not None
            body = _next_dyadic_message(
                llm=llm,
                user_id=speaker,
                brief=brief,
                transcript=transcript,
                stress_directive=stress_directive,
                speaker_state_before=speaker_state_before,
                reply_experiment_mode=effective_reply_experiment_mode,
                simulated_interaction_mode=simulated_mode,
                simulated_mutual_intent_assessment=simulated_intent,
                simulated_assistant_guidance=turn_record.get("assistant_guidance"),
            )
            turn_record["message_generation_source"] = "llm"
        except Exception as e:
            body = _fallback_next_message(
                visible_messages=msgs,
                assistant_guidance=turn_record.get("assistant_guidance"),
                interaction_mode=_evaluated_interaction_mode(turn_record),
                mutual_intent_assessment=_evaluated_mutual_intent_assessment(turn_record),
                speaker_state=speaker_state_before,
            )
            turn_record["message_generation_source"] = "fallback"
            turn_record["message_generation_error"] = f"{type(e).__name__}: {e}"
            emit(
                f"{turn_label}: message generation fallback used after {type(e).__name__}: "
                f"{_preview_text(body)}"
            )
        emit(f"{turn_label}: generated message={_preview_text(body)}")
        msg = post_message(
            conn,
            thread_id,
            speaker,
            body,
            visibility=VIS_DYADIC,
            source=SRC_USER,
            now=ts + timedelta(milliseconds=1),
        )
        conn.commit()
        turn_record["generated_message"] = body
        turn_record["generated_message_id"] = msg.get("message_id")
        turn_record["generated_message_created_at"] = str(msg.get("created_at") or "")
        turn_record["stress_manifestation"] = _stress_beat_manifestation_assessment(beat, body)
        speaker_state_after = _apply_state_delta(
            speaker_state_before,
            **{
                key: value
                for key, value in _state_delta_from_message(body).items()
                if key != "trend"
            },
            trend=str(_state_delta_from_message(body).get("trend") or "steady"),
        )
        speaker_state_by_user[speaker] = dict(speaker_state_after)
        turn_record["speaker_state_after"] = dict(speaker_state_after)
        turn_record["naturalness"] = _naturalness_assessment(body)
        turn_record["assistant_follow_assessment"] = _assistant_follow_assessment(
            str(turn_record.get("generated_message") or ""),
            turn_record.get("assistant_guidance"),
            assistant_invoked=bool(turn_record.get("assistant_invoked")),
        )
        turn_record["follow_evidence"] = dict(
            (turn_record.get("assistant_follow_assessment") or {}).get("evidence") or {}
        )
        turn_record["overpush_risk"] = (turn_record.get("assistant_follow_assessment") or {}).get(
            "overpush_risk"
        )
        turn_records.append(turn_record)
        emit(f"{turn_label}: message committed")

    for idx, record in enumerate(turn_records):
        follow_assessment = _assistant_follow_assessment(
            str(record.get("generated_message") or ""),
            record.get("assistant_guidance"),
            assistant_invoked=bool(record.get("assistant_invoked")),
        )
        record["assistant_follow_assessment"] = follow_assessment
        record["follow_evidence"] = dict(follow_assessment.get("evidence") or {})
        record["overpush_risk"] = follow_assessment.get("overpush_risk")
        record["assistant_recovery_assessment"] = _assistant_recovery_assessment(
            record,
            turn_records[idx + 1 : idx + 4],
        )
        record["simulated_reply_mode_alignment"] = _simulated_reply_mode_alignment(record)
        record["assistant_mode_compliance_details"] = _assistant_mode_compliance(
            record.get("assistant_guidance"),
            assistant_invoked=bool(record.get("assistant_invoked")),
        )
        _apply_turn_evaluation_schema(record)

    gold_positive = [r for r in turn_records if bool((r.get("gold_rescue") or {}).get("need_rescue"))]
    pred_positive = [r for r in turn_records if bool(r.get("assistant_invoked"))]
    true_positive = [
        r
        for r in turn_records
        if bool((r.get("gold_rescue") or {}).get("need_rescue")) and bool(r.get("assistant_invoked"))
    ]
    false_positive = [
        r
        for r in turn_records
        if not bool((r.get("gold_rescue") or {}).get("need_rescue")) and bool(r.get("assistant_invoked"))
    ]
    false_negative = [
        r
        for r in turn_records
        if bool((r.get("gold_rescue") or {}).get("need_rescue")) and not bool(r.get("assistant_invoked"))
    ]
    naturalness_scores = [int((r.get("naturalness") or {}).get("score") or 0) for r in turn_records]
    intervention_records = [r for r in turn_records if bool(r.get("assistant_invoked"))]
    assistant_latencies = [
        int(r.get("assistant_latency_ms") or 0)
        for r in intervention_records
        if r.get("assistant_latency_ms") is not None
    ]
    followed_interventions = [
        r
        for r in intervention_records
        if (r.get("assistant_follow_assessment") or {}).get("level")
        in {FOLLOW_LEVEL_PARTIAL, FOLLOW_LEVEL_STRONG}
    ]
    partial_follow = [
        r
        for r in intervention_records
        if (r.get("assistant_follow_assessment") or {}).get("level") == FOLLOW_LEVEL_PARTIAL
    ]
    strong_follow = [
        r for r in intervention_records if (r.get("assistant_follow_assessment") or {}).get("level") == "strong"
    ]
    topic_shift_follow = [
        r
        for r in intervention_records
        if bool((r.get("follow_evidence") or {}).get("matched_topic_directions"))
        or bool((r.get("follow_evidence") or {}).get("matched_profile_hooks"))
        or "switch_topic" in set((r.get("follow_evidence") or {}).get("applied_strategies") or [])
    ]
    avoid_violation_turns = [
        r for r in intervention_records if bool((r.get("follow_evidence") or {}).get("avoid_violations"))
    ]
    repair_interventions = [r for r in intervention_records if _evaluated_interaction_mode(r) == "repair"]
    overpush_risk_turns = [
        r
        for r in intervention_records
        if bool(((r.get("overpush_risk") or {}).get("flag")))
    ]
    prompted_mode_turns = [r for r in turn_records if bool(r.get("simulated_reply_mode_prompted"))]
    mode_alignment_records = [
        r
        for r in turn_records
        if (r.get("simulated_reply_mode_alignment") or {}).get("label") != "not_applicable"
    ]
    aligned_mode_records = [
        r
        for r in mode_alignment_records
        if (r.get("simulated_reply_mode_alignment") or {}).get("label") in {"aligned", "partially_aligned"}
    ]
    strong_aligned_mode_records = [
        r
        for r in mode_alignment_records
        if (r.get("simulated_reply_mode_alignment") or {}).get("label") == "aligned"
    ]
    recoverable_interventions = [
        r
        for r in intervention_records
        if _evaluated_interaction_mode(r) == "repair"
        and (r.get("assistant_recovery_assessment") or {}).get("label") not in ("not_applicable", "pending")
    ]
    improved_recovery = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "improved"
    ]
    slightly_improved_recovery = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "slightly_improved"
    ]
    worse_or_same_recovery = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "worse_or_same"
    ]
    heuristic_decisions = [
        r
        for r in turn_records
        if str(r.get("rescue_decision_source") or "").startswith("heuristic")
    ]
    llm_decisions = [r for r in turn_records if (r.get("rescue_decision_source") or "") == "llm"]
    llm_parse_fallback_decisions = [
        r for r in turn_records if (r.get("rescue_decision_source") or "") == "llm_parse_fallback"
    ]
    llm_error_fallback_decisions = [
        r for r in turn_records if (r.get("rescue_decision_source") or "") == "llm_error_fallback"
    ]
    fallback_message_turns = [r for r in turn_records if (r.get("message_generation_source") or "") == "fallback"]
    proactive_hint_candidates = [r for r in turn_records if isinstance(r.get("hint_trigger_event"), dict)]
    proactive_hint_posted = [
        r for r in proactive_hint_candidates if bool((r.get("hint_trigger_event") or {}).get("hint_posted"))
    ]
    duplicate_suppressed_turns = [
        r
        for r in proactive_hint_candidates
        if is_duplicate_suppression_reason((r.get("hint_trigger_event") or {}).get("suppression_reason"))
    ]
    mode_change_hint_turns = [
        r
        for r in proactive_hint_posted
        if (r.get("hint_trigger_event") or {}).get("trigger_type") == "mode_change"
    ]
    timeout_guidance_turns = [
        r
        for r in intervention_records
        if str(((r.get("assistant_guidance") or {}).get("guidance_source")) or "") == "fallback_timeout"
    ]
    fallback_guidance_turns = [
        r
        for r in intervention_records
        if str(((r.get("assistant_guidance") or {}).get("guidance_source")) or "").startswith("fallback")
    ]
    message_generation_timeout_turns = [
        r
        for r in turn_records
        if (r.get("message_generation_source") or "") == "fallback"
        and _is_timeout_error_text(str(r.get("message_generation_error") or ""))
    ]
    stress_turns = [r for r in turn_records if isinstance(r.get("stress_beat"), dict)]
    manifested_stress_turns = [
        r for r in stress_turns if bool((r.get("stress_manifestation") or {}).get("manifested"))
    ]
    visible_text_view = _recognition_view_metrics(turn_records, view="visible_text")
    stress_beat_view = _recognition_view_metrics(turn_records, view="stress_beat")
    manifested_stress_beat_view = _recognition_view_metrics(
        turn_records,
        view="manifested_stress_beat",
    )

    emit(f"starting self-evaluation for {participant_a_id}")
    eval_a_fallback = False
    eval_a_timeout = False
    try:
        eval_a = _persona_self_evaluation(
            llm=llm,
            user_id=participant_a_id,
            brief=brief_a,
            transcript=format_visible_transcript(
                list_messages(conn, thread_id, participant_a_id, limit=500)
            ),
        )
    except Exception as e:
        eval_a = _fallback_self_evaluation(reason=f"{type(e).__name__}: {e}")
        eval_a_fallback = True
        eval_a_timeout = _is_timeout_exception(e)
        emit(f"self-evaluation fallback used for {participant_a_id}: {type(e).__name__}: {e}")
    conn.commit()
    emit(
        f"self-evaluation ready for {participant_a_id}: conversation_score={eval_a.get('conversation_score')}, "
        f"assistant_score={eval_a.get('assistant_score')}"
    )
    emit(f"starting self-evaluation for {participant_b_id}")
    eval_b_fallback = False
    eval_b_timeout = False
    try:
        eval_b = _persona_self_evaluation(
            llm=llm,
            user_id=participant_b_id,
            brief=brief_b,
            transcript=format_visible_transcript(
                list_messages(conn, thread_id, participant_b_id, limit=500)
            ),
        )
    except Exception as e:
        eval_b = _fallback_self_evaluation(reason=f"{type(e).__name__}: {e}")
        eval_b_fallback = True
        eval_b_timeout = _is_timeout_exception(e)
        emit(f"self-evaluation fallback used for {participant_b_id}: {type(e).__name__}: {e}")
    conn.commit()
    emit(
        f"self-evaluation ready for {participant_b_id}: conversation_score={eval_b.get('conversation_score')}, "
        f"assistant_score={eval_b.get('assistant_score')}"
    )
    emit(
        f"roleplay finished: rescue_events={len(rescue_log)}, stress_events={len(stress_events)}"
    )

    return {
        "thread_id": thread_id,
        "thread_reused": thread_reused,
        "case_id": case_id,
        "base_time": t0.isoformat(sep=" "),
        "rounds": rounds,
        "assistant_mode": mode,
        "fixed_assistant_turns": sorted(fixed_turns) if mode == "fixed_turns" else [],
        "roleplay_experiment": {
            "reply_experiment_mode": effective_reply_experiment_mode,
            "simulated_reply_reads_interaction_mode": effective_reply_experiment_mode
            in {"mode_hint", "controlled"},
            "legacy_simulate_reply_reads_interaction_mode": bool(simulate_reply_reads_interaction_mode),
            "offline_only": True,
        },
        "proactive_rescue_events": rescue_log,
        "stress_mode": sm,
        "stress_events": stress_events,
        "turn_evaluation_schema_version": TURN_EVALUATION_SCHEMA_VERSION,
        "turn_evaluation_field_groups": {
            "shared": list(SHARED_TURN_EVALUATION_FIELDS),
            "roleplay": list(ROLEPLAY_TURN_EVALUATION_FIELDS),
        },
        "turn_evaluations": turn_records,
        "assistant_metrics": {
            "gold_rescue_turns": len(gold_positive),
            "predicted_rescue_turns": len(pred_positive),
            "true_positive_rescue_turns": len(true_positive),
            "false_positive_rescue_turns": len(false_positive),
            "false_negative_rescue_turns": len(false_negative),
            "precision_proxy": round(len(true_positive) / len(pred_positive), 4) if pred_positive else None,
            "recall_proxy": round(len(true_positive) / len(gold_positive), 4) if gold_positive else None,
            "heuristic_decision_turns": len(heuristic_decisions),
            "llm_decision_turns": len(llm_decisions),
            "llm_parse_fallback_turns": len(llm_parse_fallback_decisions),
            "llm_error_fallback_turns": len(llm_error_fallback_decisions),
            "fallback_message_turns": len(fallback_message_turns),
            "fallback_message_rate": round(len(fallback_message_turns) / len(turn_records), 4)
            if turn_records
            else None,
            "message_generation_timeout_turns": len(message_generation_timeout_turns),
            "message_generation_timeout_rate": round(
                len(message_generation_timeout_turns) / len(turn_records),
                4,
            )
            if turn_records
            else None,
            "hint_candidate_turns": len(proactive_hint_candidates),
            "hint_posted_turns": len(proactive_hint_posted),
            "hint_trigger_rate": round(len(proactive_hint_posted) / len(proactive_hint_candidates), 4)
            if proactive_hint_candidates
            else None,
            "duplicate_suppressed_turns": len(duplicate_suppressed_turns),
            "duplicate_hint_rate": round(len(duplicate_suppressed_turns) / len(proactive_hint_candidates), 4)
            if proactive_hint_candidates
            else None,
            "mode_change_hint_turns": len(mode_change_hint_turns),
            "mode_change_hint_rate": round(len(mode_change_hint_turns) / len(proactive_hint_candidates), 4)
            if proactive_hint_candidates
            else None,
            "assistant_invoke_avg_ms": round(sum(assistant_latencies) / len(assistant_latencies), 2)
            if assistant_latencies
            else None,
            "assistant_invoke_max_ms": max(assistant_latencies) if assistant_latencies else None,
            "assistant_invoke_timeout_turns": len(timeout_guidance_turns),
            "assistant_invoke_timeout_rate": round(len(timeout_guidance_turns) / len(intervention_records), 4)
            if intervention_records
            else None,
            "assistant_guidance_fallback_turns": len(fallback_guidance_turns),
            "assistant_guidance_fallback_rate": round(
                len(fallback_guidance_turns) / len(intervention_records),
                4,
            )
            if intervention_records
            else None,
            "repair_intervention_turns": len(repair_interventions),
            "overpush_risk_turns": len(overpush_risk_turns),
            "repair_turns": manifested_stress_beat_view["repair_turns"],
            "repair_recall": manifested_stress_beat_view["repair_recall"],
            "repair_missed_none_turns": manifested_stress_beat_view["repair_missed_none_turns"],
            "repair_miss_rate": manifested_stress_beat_view["repair_miss_rate"],
            "visible_text_repair_turns": visible_text_view["repair_turns"],
            "visible_text_repair_recall": visible_text_view["repair_recall"],
            "visible_text_repair_missed_none_turns": visible_text_view["repair_missed_none_turns"],
            "visible_text_repair_miss_rate": visible_text_view["repair_miss_rate"],
            "stress_beat_repair_turns": stress_beat_view["repair_turns"],
            "stress_beat_repair_recall": stress_beat_view["repair_recall"],
            "stress_beat_repair_missed_none_turns": stress_beat_view["repair_missed_none_turns"],
            "stress_beat_repair_miss_rate": stress_beat_view["repair_miss_rate"],
            "manifested_stress_beat_repair_turns": manifested_stress_beat_view["repair_turns"],
            "manifested_stress_beat_repair_recall": manifested_stress_beat_view["repair_recall"],
            "manifested_stress_beat_repair_missed_none_turns": manifested_stress_beat_view[
                "repair_missed_none_turns"
            ],
            "manifested_stress_beat_repair_miss_rate": manifested_stress_beat_view["repair_miss_rate"],
            "visible_text_view": visible_text_view,
            "stress_beat_view": stress_beat_view,
            "manifested_stress_beat_view": manifested_stress_beat_view,
            "stress_beat_turns": len(stress_turns),
            "stress_beat_manifested_turns": len(manifested_stress_turns),
            "stress_beat_manifestation_rate": round(
                len(manifested_stress_turns) / len(stress_turns),
                4,
            )
            if stress_turns
            else None,
            "simulated_reply_mode_prompted_turns": len(prompted_mode_turns),
            "simulated_reply_mode_applicable_turns": len(mode_alignment_records),
            "simulated_reply_mode_alignment_turns": len(aligned_mode_records),
            "simulated_reply_mode_alignment_rate": round(
                len(aligned_mode_records) / len(mode_alignment_records),
                4,
            )
            if mode_alignment_records
            else None,
            "simulated_reply_mode_strong_alignment_turns": len(strong_aligned_mode_records),
            "simulated_reply_mode_strong_alignment_rate": round(
                len(strong_aligned_mode_records) / len(mode_alignment_records),
                4,
            )
            if mode_alignment_records
            else None,
            "followed_intervention_turns": len(followed_interventions),
            "follow_rate": round(len(followed_interventions) / len(intervention_records), 4)
            if intervention_records
            else None,
            "partial_follow_turns": len(partial_follow),
            "partial_follow_rate": round(len(partial_follow) / len(intervention_records), 4)
            if intervention_records
            else None,
            "strong_follow_turns": len(strong_follow),
            "strong_follow_rate": round(len(strong_follow) / len(intervention_records), 4)
            if intervention_records
            else None,
            "topic_shift_follow_turns": len(topic_shift_follow),
            "avoid_violation_turns": len(avoid_violation_turns),
            "recoverable_intervention_turns": len(recoverable_interventions),
            "improved_recovery_turns": len(improved_recovery),
            "improved_recovery_rate": round(len(improved_recovery) / len(recoverable_interventions), 4)
            if recoverable_interventions
            else None,
            "slightly_improved_recovery_turns": len(slightly_improved_recovery),
            "worse_or_same_recovery_turns": len(worse_or_same_recovery),
            "self_evaluation_fallback_count": int(eval_a_fallback) + int(eval_b_fallback),
            "self_evaluation_timeout_count": int(eval_a_timeout) + int(eval_b_timeout),
        },
        "naturalness_metrics": {
            "average_score": round(sum(naturalness_scores) / len(naturalness_scores), 4)
            if naturalness_scores
            else None,
            "flagged_turns": [
                {
                    "turn": r["turn"],
                    "speaker": r["speaker"],
                    "flags": (r.get("naturalness") or {}).get("flags") or [],
                    "message_preview": _preview_text(str(r.get("generated_message") or "")),
                }
                for r in turn_records
                if (r.get("naturalness") or {}).get("flags")
            ],
        },
        "evaluation": {
            participant_a_id: eval_a,
            participant_b_id: eval_b,
        },
    }


__all__ = [
    "dyadic_public_transcript",
    "format_visible_transcript",
    "parse_int_csv",
    "run_dyadic_roleplay",
    "strip_json_object",
]
