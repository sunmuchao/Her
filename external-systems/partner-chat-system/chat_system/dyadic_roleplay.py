"""Two LLM personas chat in a real ``chat_threads`` row; proactive assistant rescue; persona self-evaluation."""

from __future__ import annotations

import json
import random
import re
import zlib
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Callable, Protocol

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


class SupportsConn(Protocol):
    def commit(self) -> None: ...


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
        "先分清楚：这到底是“双方都还想继续聊，但这轮卡在沟通上”，还是“意愿不明确 / 对方投入偏低 / 已经碰到边界”。\n"
        "只有在更像沟通问题时，才应该让助手做 repair。若只是意愿不明确，只能做低压试探；若对方明显低投入或碰到边界，就不要再往救场上推。\n"
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
        f'  "mutual_intent_assessment": "<{_MUTUAL_INTENT_CHOICES} 选一>",\n'
        f'  "interaction_mode": "<{_INTERACTION_MODE_CHOICES} 选一>",\n'
        '  "rescue_style": "<reengage|switch_topic|low_pressure_probe|graceful_exit|none 选一>",\n'
        '  "reason": "<极短中文，说明为何需要或不需要救场>"\n'
        "}\n"
        "规则：只有 interaction_mode 为 repair 或 probe_lightly 时，need_rescue 才能为 true。"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        return normalize_route_decision(strip_json_object(raw), decision_source="llm")
    except (json.JSONDecodeError, ValueError):
        return normalize_route_decision(
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "调度解析失败，默认不介入",
                "parse_error": True,
            },
            decision_source="llm_parse_fallback",
        )


def _next_dyadic_message(
    *,
    llm: LLMFn,
    user_id: str,
    brief: str,
    transcript: str,
    stress_directive: str | None = None,
    simulated_interaction_mode: str | None = None,
    simulated_mutual_intent_assessment: str | None = None,
) -> str:
    system = _persona_system(user_id=user_id, brief=brief)
    stress_block = ""
    if stress_directive:
        stress_block = (
            "\n\n【本回合剧情压力（只体现效果，不要提起「剧情」「导演」「压力测试」等词）】\n"
            f"{stress_directive}"
        )
    mode = str(simulated_interaction_mode or "").strip().lower()
    mode_block = ""
    if mode in {"repair", "probe_lightly", "hold"}:
        intent = str(simulated_mutual_intent_assessment or "").strip().lower()
        intent_line = f"辅助判断：{intent}。\n" if intent and intent != "normal" else ""
        if mode == "repair":
            detail = (
                "这轮更像双方都还想继续聊，只是接话卡了一下。先接住对方刚刚的信息，补一点你自己的具体内容，"
                "再自然往下聊或轻轻抛一个容易接的问题；不要突然变冷，也别切去收入、前任、照片这些敏感方向。"
            )
        elif mode == "probe_lightly":
            detail = (
                "这轮更像意愿还不够明确，只能轻轻试一下。最多一句低压、好回答的问题，简短一点；"
                "不要连环追问，不要太用力，也不要讨好式硬拉。"
            )
        else:
            detail = (
                "这轮更像该收住了。不要继续追问，也不要推进收入、前任、照片等敏感方向；"
                "优先自然收口，或者发一条不施压的轻收住消息。"
            )
        mode_block = (
            "\n\n【仅用于离线 roleplay 评测的额外模式提示】\n"
            "这段提示只服务于模拟实验，不代表真实产品会约束真人用户怎么回复。\n"
            f"当前模式：{mode}\n"
            f"{intent_line}{detail}\n"
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
        f"{stress_block}{mode_block}"
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
    return {
        "need_rescue": bool(beats),
        "source_beats": [b.id for b in beats],
        "expected_problem_tags": _dedupe_strs([tag for b in beats for tag in b.expected_problem_tags]),
        "suggested_strategy_tags": _dedupe_strs([tag for b in beats for tag in b.suggested_strategy_tags]),
        "max_severity": max([b.severity for b in beats], default=0),
        "expected_mutual_intent_assessment": (
            primary.expected_mutual_intent_assessment if primary else "normal"
        ),
        "expected_interaction_mode": primary.expected_interaction_mode if primary else "none",
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


def _fallback_next_message(
    *,
    visible_messages: list[dict[str, Any]],
    assistant_guidance: dict[str, Any] | None,
) -> str:
    dyadic = [m for m in visible_messages if str(m.get("visibility") or "") == VIS_DYADIC]
    recent = [str(m.get("body") or "").strip() for m in dyadic[-3:]]
    strategy_tags = set(str(x) for x in (assistant_guidance or {}).get("strategy_tags") or [])

    if "graceful_exit" in strategy_tags and len(recent) >= 2 and all(_is_low_energy_like(body) for body in recent[-2:]):
        return "感觉今天节奏有点慢，我们先轻松点，改天有空再接着聊也行。"
    if recent and _is_low_energy_like(recent[-1]) and len(recent) >= 2 and _is_question_like(recent[-2]):
        topic = _pick_topic_seed(assistant_guidance)
        return _fallback_message_from_topic(topic)
    if assistant_guidance:
        topic = _pick_topic_seed(assistant_guidance)
        if topic:
            return _fallback_message_from_topic(topic)
    if not dyadic:
        return "你好呀，想慢慢认识一下你。"
    last_body = recent[-1] if recent else ""
    if _is_question_like(last_body):
        return "还行，我平时比较随性一点。你呢？"
    return "我平时比较随性一点，你一般周末怎么放松？"


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
    if mode == "probe_lightly":
        return {
            "mutual_intent_assessment": "interest_unclear",
            "interaction_mode": "probe_lightly",
            "strategy_tags": ["probe_lightly"],
            "easy_question_types": ["低门槛生活问题"],
            "low_pressure_options": ["一句轻问题"],
            "why_not_to_push": ["这轮只低压试一下，不要连环追问，不要讨好式硬拉。"],
            "avoid": ["不要连环追问，不要硬推，也不要切回敏感方向。"],
        }
    if mode == "hold":
        return {
            "mutual_intent_assessment": str(mutual_intent_assessment or "interest_low"),
            "interaction_mode": "hold",
            "strategy_tags": ["graceful_exit"],
            "why_not_to_push": ["这轮更像该收住，不要继续推进。"],
            "avoid": ["不要继续追问，也不要切回敏感方向。"],
            "graceful_exit_plan": ["先轻轻收住，必要时体面止损。"],
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
    text = str(message or "").strip()
    signals: list[str] = []
    strategy_tags = set(str(x) for x in guidance.get("strategy_tags") or [])
    interaction_mode = str(guidance.get("interaction_mode") or "repair")
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
    graceful_exit_used = "graceful_exit" in strategy_tags and _is_graceful_exit_like(text)
    switched_topic = bool(matched_topic_directions or matched_profile_hooks)
    if not switched_topic and "switch_topic" in strategy_tags and asked_low_bar_question and len(text) >= 10:
        switched_topic = True
    low_pressure_probe = (
        interaction_mode == "probe_lightly"
        and asked_question
        and asked_low_bar_question
        and not pushy_questioning
        and len(text) <= 28
    )

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
    if interaction_mode == "probe_lightly" and pushy_questioning:
        avoid_violations.append("too_heavy_for_probe")
    if interaction_mode == "hold" and asked_question and not graceful_exit_used:
        avoid_violations.append("continued_pushing_in_hold_mode")
    avoid_violations = _dedupe_strs(avoid_violations)
    overpush_reasons = [
        reason
        for reason in avoid_violations
        if reason
        in {
            "sensitive_topic_reentry",
            "cross_exam_questioning",
            "too_heavy_for_probe",
            "continued_pushing_in_hold_mode",
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
        "used_graceful_exit": graceful_exit_used,
        "message_still_cold": False,
    }

    if graceful_exit_used:
        signals.append("used_graceful_exit")
        evidence["applied_strategies"].append("graceful_exit")

    if _is_low_energy_like(text) and not graceful_exit_used:
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
    if low_pressure_probe:
        score += 1
        signals.append("used_low_pressure_probe")
        evidence["applied_strategies"].append("probe_lightly")
    if switched_topic:
        score += 1
        signals.append("switched_topic")
        evidence["applied_strategies"].append("switch_topic")
    if interaction_mode == "hold" and not asked_question and not mentions_boundary_topic:
        score += 1
        signals.append("respected_hold_boundary")
        evidence["applied_strategies"].append("hold_boundary")

    evidence["applied_strategies"] = _dedupe_strs(evidence["applied_strategies"])

    if interaction_mode in {"probe_lightly", "hold"} and avoid_violations:
        level = FOLLOW_LEVEL_NONE
        score = 0
    else:
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
    if interaction_mode == "probe_lightly" and low_pressure_probe and not avoid_violations:
        if score >= 2:
            level = FOLLOW_LEVEL_STRONG
            score = max(score, 4)
        elif level == FOLLOW_LEVEL_NONE:
            level = FOLLOW_LEVEL_PARTIAL
            score = max(score, 2)
    if interaction_mode == "hold":
        if graceful_exit_used and not avoid_violations:
            level = FOLLOW_LEVEL_STRONG
            score = max(score, 4)
        elif level == FOLLOW_LEVEL_NONE and not avoid_violations and not asked_question and not mentions_boundary_topic:
            level = FOLLOW_LEVEL_PARTIAL
            score = max(score, 2)
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
    if interaction_mode == "hold":
        return {"label": "not_applicable", "score": 0, "signals": ["hold_mode_scored_separately"]}
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
        if interaction_mode == "probe_lightly":
            signals.append("probe_confirmed_counterpart_still_low_energy")
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

    if interaction_mode == "probe_lightly" and not engaged_replies and not detailed_replies and not question_replies:
        label = "clarified_low_interest"
        score = 0
    elif score >= 3:
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
    elif mode == "probe_lightly":
        if guidance.get("why_not_to_push"):
            signals.append("has_probe_caution")
        else:
            drifts.append("missing_probe_caution")
        if guidance.get("low_pressure_options"):
            signals.append("has_low_pressure_options")
        else:
            drifts.append("missing_low_pressure_options")
    elif mode == "hold":
        if guidance.get("why_not_to_push"):
            signals.append("has_hold_rationale")
        else:
            drifts.append("missing_hold_rationale")
        if guidance.get("avoid") or guidance.get("graceful_exit_plan"):
            signals.append("has_hold_stop_signal")
        else:
            drifts.append("missing_hold_stop_signal")
    else:
        drifts.append("assistant_should_not_have_been_invoked_for_none_mode")
    if drifts:
        return {"label": "drifted", "score": 0, "signals": drifts + signals}
    return {"label": "compliant", "score": 1, "signals": signals}


def _predicted_mutual_intent_assessment(record: dict[str, Any]) -> str:
    guidance = record.get("assistant_guidance") or {}
    decision = record.get("rescue_decision") or {}
    return str(
        guidance.get("mutual_intent_assessment")
        or decision.get("mutual_intent_assessment")
        or "normal"
    )


def _predicted_interaction_mode(record: dict[str, Any]) -> str:
    guidance = record.get("assistant_guidance") or {}
    decision = record.get("rescue_decision") or {}
    return str(guidance.get("interaction_mode") or decision.get("interaction_mode") or "none")


def _evaluated_interaction_mode(record: dict[str, Any]) -> str:
    return str(record.get("interaction_mode") or _predicted_interaction_mode(record) or "none")


def _evaluated_mutual_intent_assessment(record: dict[str, Any]) -> str:
    return str(record.get("mutual_intent_assessment") or _predicted_mutual_intent_assessment(record) or "normal")


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
    if mode not in {"repair", "probe_lightly", "hold"}:
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
    mode = _evaluated_interaction_mode(record)
    if mode != "hold":
        return None
    message = str(record.get("generated_message") or "")
    if not message.strip():
        return 0
    if bool(((record.get("overpush_risk") or {}).get("flag"))):
        return 0
    if _mentions_boundary_topic(message):
        return 0
    score = 0
    if _is_graceful_exit_like(message):
        score += 1 if _is_question_like(message) else 2
    elif not _is_question_like(message):
        score += 1
    if _is_low_energy_like(message) and not _is_graceful_exit_like(message):
        score = max(0, score - 1)
    return score


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
        "mutual_intent_assessment_gold": str(
            gold.get("expected_mutual_intent_assessment") or "normal"
        ),
        "mutual_intent_assessment_pred": _predicted_mutual_intent_assessment(record),
        "interaction_mode_gold": str(gold.get("expected_interaction_mode") or "none"),
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
    - ``False``: roleplay personas reply freely.
    - ``True``: offline experiment only; the simulated replier also receives the current ``interaction_mode`` as an extra prompt hint.

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
    expected_rescue_turns: dict[int, list[StressBeat]] = {}

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    emit(
        f"thread ready: thread_id={thread_id}, reused={thread_reused}, base_time={t0.isoformat(sep=' ')}, "
        f"assistant_mode={mode}, stress_mode={sm}"
    )

    for i in range(rounds):
        ts = t0 + timedelta(seconds=i + 1)
        speaker = participant_a_id if i % 2 == 0 else participant_b_id
        brief = brief_a if i % 2 == 0 else brief_b
        turn_label = f"turn {i + 1}/{rounds}"
        gold_beats = list(expected_rescue_turns.get(i, []))
        turn_record: dict[str, Any] = {
            "turn": i,
            "speaker": speaker,
            "gold_rescue": _gold_rescue_for_turn(gold_beats),
            "assistant_invoked": False,
            "simulated_reply_mode_prompted": False,
            "hint_trigger_event": None,
            "hint_posted": None,
            "trigger_type": None,
            "suppression_reason": None,
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
                expected_rescue_turns.setdefault(rescue_turn, []).append(beat)

        if mode == "fixed_turns" and i in fixed_turns:
            emit(f"{turn_label}: assistant fixed-turn hint for {speaker}")
            assistant_started = perf_counter()
            hint = assistant_query(conn, thread_id, speaker, fixed_assistant_query, now=ts)
            assistant_elapsed_ms = int((perf_counter() - assistant_started) * 1000)
            turn_record["assistant_invoked"] = True
            turn_record["assistant_message_id"] = hint.get("message_id")
            turn_record["assistant_guidance"] = hint.get("assistant_guidance")
            turn_record["assistant_profile_context"] = hint.get("assistant_profile_context")
            turn_record["assistant_latency_ms"] = assistant_elapsed_ms
            emit(f"{turn_label}: assistant hint posted for {speaker} in {assistant_elapsed_ms} ms")
        elif mode == "proactive":
            pub_msgs = [
                m
                for m in list_messages(conn, thread_id, participant_a_id, limit=200)
                if m.get("visibility") == VIS_DYADIC
            ]
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
                    decision = normalize_route_decision(
                        {
                            "need_rescue": False,
                            "situation": "none",
                            "problem_tags": [],
                            "mutual_intent_assessment": "normal",
                            "interaction_mode": "none",
                            "rescue_style": "none",
                            "reason": f"调度超时，先按不介入处理：{type(e).__name__}",
                        },
                        decision_source="llm_error_fallback",
                    )
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
                turn_record["assistant_guidance"] = hint.get("assistant_guidance")
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
        try:
            current_mode = _evaluated_interaction_mode(turn_record)
            simulated_mode = (
                current_mode
                if simulate_reply_reads_interaction_mode and current_mode in {"repair", "probe_lightly", "hold"}
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
                simulated_interaction_mode=simulated_mode,
                simulated_mutual_intent_assessment=simulated_intent,
            )
            turn_record["message_generation_source"] = "llm"
        except Exception as e:
            body = _fallback_next_message(
                visible_messages=msgs,
                assistant_guidance=turn_record.get("assistant_guidance"),
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
    probe_interventions = [
        r for r in intervention_records if _evaluated_interaction_mode(r) == "probe_lightly"
    ]
    hold_decisions = [r for r in turn_records if _evaluated_interaction_mode(r) == "hold"]
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
        if _evaluated_interaction_mode(r) in {"repair", "probe_lightly"}
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
    clarified_low_interest = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "clarified_low_interest"
    ]
    worse_or_same_recovery = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "worse_or_same"
    ]
    recoverable_probe_interventions = [
        r
        for r in probe_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") not in ("not_applicable", "pending")
    ]
    graceful_exit_turns = [r for r in hold_decisions if int(_graceful_exit_score(r) or 0) > 0]
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
    hold_repeat_candidates = [
        r
        for r in proactive_hint_candidates
        if (r.get("hint_trigger_event") or {}).get("mode_after") == "hold"
        and int((r.get("hint_trigger_event") or {}).get("same_mode_turns") or 0) > 1
    ]
    hold_repeat_posted = [
        r for r in hold_repeat_candidates if bool((r.get("hint_trigger_event") or {}).get("hint_posted"))
    ]
    graceful_exit_advice_turns = [
        r
        for r in intervention_records
        if "graceful_exit"
        in set(str(x) for x in ((r.get("assistant_guidance") or {}).get("strategy_tags") or []))
    ]
    graceful_exit_used_turns = [
        r for r in intervention_records if _is_graceful_exit_like(str(r.get("generated_message") or ""))
    ]

    emit(f"starting self-evaluation for {participant_a_id}")
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
        emit(f"self-evaluation fallback used for {participant_a_id}: {type(e).__name__}: {e}")
    conn.commit()
    emit(
        f"self-evaluation ready for {participant_a_id}: conversation_score={eval_a.get('conversation_score')}, "
        f"assistant_score={eval_a.get('assistant_score')}"
    )
    emit(f"starting self-evaluation for {participant_b_id}")
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
            "simulated_reply_reads_interaction_mode": bool(simulate_reply_reads_interaction_mode),
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
            "hold_repeat_hint_turns": len(hold_repeat_posted),
            "hold_repeat_hint_rate": round(len(hold_repeat_posted) / len(hold_repeat_candidates), 4)
            if hold_repeat_candidates
            else None,
            "assistant_invoke_avg_ms": round(sum(assistant_latencies) / len(assistant_latencies), 2)
            if assistant_latencies
            else None,
            "assistant_invoke_max_ms": max(assistant_latencies) if assistant_latencies else None,
            "repair_intervention_turns": len(repair_interventions),
            "probe_intervention_turns": len(probe_interventions),
            "hold_decision_turns": len(hold_decisions),
            "overpush_risk_turns": len(overpush_risk_turns),
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
            "clarified_low_interest_turns": len(clarified_low_interest),
            "clarified_low_interest_rate": round(
                len(clarified_low_interest) / len(recoverable_probe_interventions),
                4,
            )
            if recoverable_probe_interventions
            else None,
            "graceful_exit_turns": len(graceful_exit_turns),
            "graceful_exit_rate": round(len(graceful_exit_turns) / len(hold_decisions), 4)
            if hold_decisions
            else None,
            "graceful_exit_advice_turns": len(graceful_exit_advice_turns),
            "graceful_exit_used_turns": len(graceful_exit_used_turns),
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
