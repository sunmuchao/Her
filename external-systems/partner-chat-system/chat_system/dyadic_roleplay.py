"""Two LLM personas chat in a real ``chat_threads`` row; proactive assistant rescue; persona self-evaluation."""

from __future__ import annotations

import json
import random
import re
import zlib
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Callable, Protocol

from .scenario_stress import StressBeat, pick_stress_beat, stress_log_entry
from .service import (
    SRC_USER,
    VIS_DYADIC,
    assistant_query,
    get_or_create_thread,
    get_thread_by_case,
    list_messages,
    post_message,
)

LLMFn = Callable[[list[dict[str, str]]], str]

_ANALYTIC_PHRASES = (
    "你是在认可",
    "我理解你的意思是",
    "从你的表述来看",
    "如果我没理解错",
    "从你的角度看",
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
_ALLOWED_SITUATIONS = {"cold", "awkward", "stuck", "rude", "boundary", "off_topic", "none"}
_ALLOWED_RESCUE_STYLES = {"reengage", "switch_topic", "low_pressure_probe", "graceful_exit", "none"}
_ALLOWED_MUTUAL_INTENT_ASSESSMENTS = {
    "communication_problem",
    "interest_unclear",
    "interest_low",
    "boundary_risk",
    "normal",
}
_ALLOWED_INTERACTION_MODES = {"repair", "probe_lightly", "hold", "none"}


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
        "像真人即时聊天，优先短句和口语，不要写成分析、解释、客服、复盘或小作文口吻。\n"
        "避免出现「你是在认可……吗」「从你的表述来看」「我理解你的意思是」这类书面分析腔。\n"
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
        '  "mutual_intent_assessment": "<communication_problem|interest_unclear|interest_low|boundary_risk|normal 选一>",\n'
        '  "interaction_mode": "<repair|probe_lightly|hold|none 选一>",\n'
        '  "rescue_style": "<reengage|switch_topic|low_pressure_probe|graceful_exit|none 选一>",\n'
        '  "reason": "<极短中文，说明为何需要或不需要救场>"\n'
        "}\n"
        "规则：只有 interaction_mode 为 repair 或 probe_lightly 时，need_rescue 才能为 true。"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        return _normalize_rescue_decision(strip_json_object(raw), decision_source="llm")
    except (json.JSONDecodeError, ValueError):
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "none",
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
) -> str:
    system = _persona_system(user_id=user_id, brief=brief)
    stress_block = ""
    if stress_directive:
        stress_block = (
            "\n\n【本回合剧情压力（只体现效果，不要提起「剧情」「导演」「压力测试」等词）】\n"
            f"{stress_directive}"
        )
    user = (
        "以下是你在这个会话里**当前能看到的全部消息**（按时间顺序）：\n\n"
        f"{transcript}\n\n"
        "请写出下一条你要发给对方的聊天内容（**只输出正文**，不要引号、不要「对方：」等前缀、不要解释）。"
        "像真实聊天，不要分析对方措辞，不要写成说明文。"
        "尽量像微信里会发的 1-2 句短消息，能口语就别分析；先接住具体信息，再补一点自己的话。"
        "如果要提问，优先问轻一点、容易回答的问题。"
        f"{stress_block}"
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


def _contains_any_phrase_signal(text: str, phrases: list[str]) -> bool:
    body = _compact_text(text)
    if not body:
        return False
    for phrase in phrases:
        for frag in _phrase_fragments(phrase):
            if frag and frag in body:
                return True
    return False


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
    if len(t) >= 42 and (t.count("，") + t.count("。")) >= 3:
        flags.append("too_expository")
    if "首先" in t or "其次" in t or "总之" in t:
        flags.append("structured_monologue")
    return {
        "score": max(1, 5 - len(flags)),
        "flags": flags,
    }


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


def _normalize_mutual_intent_assessment(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in _ALLOWED_MUTUAL_INTENT_ASSESSMENTS:
        return raw
    text = str(value or "").strip()
    if "双方" in text and any(token in text for token in ("还想聊", "想继续聊", "继续聊")):
        return "communication_problem"
    if any(token in text for token in ("边界", "敏感", "压力")):
        return "boundary_risk"
    if any(token in text for token in ("兴趣低", "意愿低", "不想聊", "敷衍", "别硬推", "别讨好")):
        return "interest_low"
    if any(token in text for token in ("不明确", "不确定", "试探", "先探")):
        return "interest_unclear"
    if any(token in text for token in ("正常", "自然聊", "顺着聊")):
        return "normal"
    return "interest_unclear"


def _default_interaction_mode(mutual_intent_assessment: str, *, need_rescue: bool) -> str:
    if mutual_intent_assessment == "communication_problem":
        return "repair" if need_rescue else "none"
    if mutual_intent_assessment == "interest_unclear":
        return "probe_lightly" if need_rescue else "none"
    if mutual_intent_assessment in {"interest_low", "boundary_risk"}:
        return "hold"
    return "none"


def _normalize_interaction_mode(
    value: Any,
    *,
    mutual_intent_assessment: str,
    need_rescue: bool,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in _ALLOWED_INTERACTION_MODES:
        return raw
    text = str(value or "").strip()
    if "低压试探" in text or "轻试" in text:
        return "probe_lightly"
    if any(token in text for token in ("先收住", "别硬推", "别推进", "别讨好")):
        return "hold"
    if any(token in text for token in ("正常修复", "接住", "往下聊")):
        return "repair"
    if any(token in text for token in ("不用介入", "顺着聊", "自然往下聊")):
        return "none"
    return _default_interaction_mode(mutual_intent_assessment, need_rescue=need_rescue)


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
        return "low_pressure_probe"
    if "换题" in text:
        return "switch_topic"
    if any(token in text for token in ("收住", "止损", "退出")):
        return "graceful_exit"
    if "接住" in text:
        return "reengage"
    if interaction_mode == "repair":
        return "switch_topic"
    if interaction_mode == "probe_lightly":
        return "low_pressure_probe"
    if interaction_mode == "hold" and mutual_intent_assessment in {"interest_low", "boundary_risk"}:
        return "graceful_exit"
    return "none"


def _normalize_rescue_decision(
    data: dict[str, Any],
    *,
    decision_source: str,
) -> dict[str, Any]:
    raw_need = bool(data.get("need_rescue"))
    mutual_intent_assessment = _normalize_mutual_intent_assessment(
        data.get("mutual_intent_assessment")
    )
    interaction_mode = _normalize_interaction_mode(
        data.get("interaction_mode"),
        mutual_intent_assessment=mutual_intent_assessment,
        need_rescue=raw_need,
    )
    need_rescue = interaction_mode in {"repair", "probe_lightly"}
    rescue_style = _normalize_rescue_style(
        data.get("rescue_style"),
        interaction_mode=interaction_mode,
        mutual_intent_assessment=mutual_intent_assessment,
    )
    if interaction_mode == "none":
        rescue_style = "none"
    out = {
        "need_rescue": need_rescue,
        "situation": _normalize_situation(data.get("situation")),
        "rescue_style": rescue_style,
        "mutual_intent_assessment": mutual_intent_assessment,
        "interaction_mode": interaction_mode,
        "reason": str(data.get("reason") or "").strip(),
        "decision_source": decision_source,
    }
    if data.get("parse_error"):
        out["parse_error"] = True
    return out


def _engagement_score(text: str) -> int:
    compact = _compact_text(text)
    if not compact or _is_low_energy_like(text):
        return 0
    score = 0
    if len(compact) >= 8:
        score += 1
    if _is_question_like(text):
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
        if _is_low_energy_like(body):
            streak += 1
            continue
        break
    return streak


def _gold_rescue_for_turn(beats: list[StressBeat]) -> dict[str, Any]:
    return {
        "need_rescue": bool(beats),
        "source_beats": [b.id for b in beats],
        "expected_problem_tags": _dedupe_strs([tag for b in beats for tag in b.expected_problem_tags]),
        "suggested_strategy_tags": _dedupe_strs([tag for b in beats for tag in b.suggested_strategy_tags]),
        "max_severity": max([b.severity for b in beats], default=0),
    }


def _fast_rescue_decision(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    dyadic = [m for m in messages if str(m.get("visibility") or "") == VIS_DYADIC]
    if not dyadic:
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "none",
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "首轮开场，先正常聊，不需要提前介入。",
            },
            decision_source="heuristic_bootstrap",
        )

    last_body = str(dyadic[-1].get("body") or "").strip()
    prev_body = str(dyadic[-2].get("body") or "").strip() if len(dyadic) >= 2 else ""
    last_author = str(dyadic[-1].get("author_id") or "")
    recent = [str(m.get("body") or "").strip() for m in dyadic[-3:]]
    prior_mutual_engagement = _recent_mutual_engagement(dyadic[:-1])
    last_author_recent_engagement = _speaker_recent_engagement(dyadic[:-1], last_author)
    last_author_low_streak = _speaker_low_energy_streak(dyadic, last_author)

    if _is_low_energy_like(last_body):
        if len(recent) >= 2 and all(_is_low_energy_like(body) for body in recent[-2:]):
            if _recent_mutual_engagement(dyadic[:-2]):
                return _normalize_rescue_decision(
                    {
                        "need_rescue": True,
                        "situation": "stuck",
                        "mutual_intent_assessment": "communication_problem",
                        "interaction_mode": "repair",
                        "rescue_style": "switch_topic",
                        "reason": "前面双方都有投入，但最近两拍都接空了，像是不会接而不是不想聊。",
                    },
                    decision_source="heuristic",
                )
            return _normalize_rescue_decision(
                {
                    "need_rescue": False,
                    "situation": "stuck",
                    "mutual_intent_assessment": "interest_low",
                    "interaction_mode": "hold",
                    "rescue_style": "graceful_exit",
                    "reason": "最近两边都低投入，更像没人想继续推进，不适合再往救场上推。",
                },
                decision_source="heuristic",
            )
        if prior_mutual_engagement and last_author_recent_engagement >= 1:
            return _normalize_rescue_decision(
                {
                    "need_rescue": True,
                    "situation": "cold",
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic" if _is_question_like(prev_body) else "reengage",
                    "reason": "前面双方本来聊得动，这一拍更像接话没接好。",
                },
                decision_source="heuristic",
            )
        if last_author_low_streak >= 2:
            return _normalize_rescue_decision(
                {
                    "need_rescue": False,
                    "situation": "cold",
                    "mutual_intent_assessment": "interest_low",
                    "interaction_mode": "hold",
                    "rescue_style": "graceful_exit",
                    "reason": "对方已经连续低投入，别把它当成单纯不会聊。",
                },
                decision_source="heuristic",
            )
        return _normalize_rescue_decision(
            {
                "need_rescue": True,
                "situation": "cold",
                "mutual_intent_assessment": "interest_unclear",
                "interaction_mode": "probe_lightly",
                "rescue_style": "low_pressure_probe",
                "reason": "这轮偏冷，但还看不出是不会聊还是没兴趣，先低压试探。",
            },
            decision_source="heuristic",
        )
    if any(token in last_body for token in _BOUNDARY_HINTS):
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "boundary",
                "mutual_intent_assessment": "boundary_risk",
                "interaction_mode": "hold",
                "rescue_style": "graceful_exit",
                "reason": "上一句已经碰到敏感或有压力的话题，不适合按正常推进来处理。",
            },
            decision_source="heuristic",
        )
    if len(recent) >= 3 and sum(1 for body in recent if _is_low_energy_like(body)) >= 2 and not any(
        _is_question_like(body) for body in recent
    ):
        if _recent_mutual_engagement(dyadic[:-3]):
            return _normalize_rescue_decision(
                {
                    "need_rescue": True,
                    "situation": "stuck",
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "rescue_style": "switch_topic",
                    "reason": "前面聊得还行，但最近几轮连续接空，适合做一次轻修复。",
                },
                decision_source="heuristic",
            )
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "stuck",
                "mutual_intent_assessment": "interest_low",
                "interaction_mode": "hold",
                "rescue_style": "graceful_exit",
                "reason": "最近几轮连续偏冷又没有追问，更像双方都不想继续加码。",
            },
            decision_source="heuristic",
        )
    if _is_question_like(last_body) and len(_compact_text(last_body)) >= 8:
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "none",
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "上一句本身就是正常可接的问题，先别打断自然往下聊。",
            },
            decision_source="heuristic_clear_continue",
        )
    if len(_compact_text(last_body)) >= 10 and not _is_cold_like(last_body) and _is_question_like(prev_body):
        return _normalize_rescue_decision(
            {
                "need_rescue": False,
                "situation": "none",
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "当前还有正常来回，先不额外介入。",
            },
            decision_source="heuristic_clear_continue",
        )
    return None


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


def _assistant_follow_assessment(
    message: str,
    guidance: dict[str, Any] | None,
    *,
    assistant_invoked: bool,
) -> dict[str, Any]:
    if not assistant_invoked or not guidance:
        return {"level": "not_applicable", "score": 0, "signals": []}
    text = str(message or "").strip()
    signals: list[str] = []
    score = 0
    strategy_tags = set(str(x) for x in guidance.get("strategy_tags") or [])
    interaction_mode = str(guidance.get("interaction_mode") or "repair")
    hooks = [str(x) for x in guidance.get("profile_hooks_used") or []]
    topic_directions = [str(x) for x in guidance.get("topic_directions") or []]
    easy_question_types = [str(x) for x in guidance.get("easy_question_types") or []]
    graceful_exit_used = "graceful_exit" in strategy_tags and _is_graceful_exit_like(text)

    if graceful_exit_used:
        score += 2
        signals.append("used_graceful_exit")

    if _is_low_energy_like(text) and not graceful_exit_used:
        return {"level": "none", "score": 0, "signals": ["message_still_cold"]}
    if _is_question_like(text):
        score += 1
        signals.append("asked_question")
    if len(text) >= 18:
        score += 1
        signals.append("shared_detail")
    if "acknowledge_coldness" in strategy_tags and any(
        token in text for token in ("聊不下去", "冷场", "接不下去", "不太擅长找话题")
    ):
        score += 1
        signals.append("acknowledged_awkwardness")
    if hooks and _contains_any_phrase_signal(text, hooks):
        score += 1
        signals.append("used_profile_hook")
    if topic_directions and _contains_any_phrase_signal(text, topic_directions):
        score += 1
        signals.append("used_topic_direction")
    if easy_question_types and _is_question_like(text) and any(token in text for token in _LOW_BAR_QUESTION_TOKENS):
        score += 1
        signals.append("asked_low_bar_question")
    if interaction_mode == "probe_lightly" and _is_question_like(text) and len(text.strip()) >= 8:
        score += 1
        signals.append("used_low_pressure_probe")
    if "switch_topic" in strategy_tags and len(text) >= 12 and (hooks or topic_directions):
        score += 1
        signals.append("switched_topic")

    if score >= 4:
        level = "strong"
    elif score >= 2:
        level = "partial"
    else:
        level = "none"
    return {"level": level, "score": score, "signals": signals}


def _assistant_recovery_assessment(current_turn: dict[str, Any], next_turn: dict[str, Any] | None) -> dict[str, Any]:
    if not bool(current_turn.get("assistant_invoked")):
        return {"label": "not_applicable", "score": 0, "signals": []}
    follow = current_turn.get("assistant_follow_assessment") or {}
    interaction_mode = str(
        ((current_turn.get("assistant_guidance") or {}).get("interaction_mode"))
        or ((current_turn.get("rescue_decision") or {}).get("interaction_mode"))
        or "repair"
    )
    if next_turn is None:
        return {"label": "pending", "score": 0, "signals": ["no_following_reply"]}
    score = 0
    signals: list[str] = []
    if follow.get("level") == "strong":
        score += 1
        signals.append("speaker_followed_guidance_well")
    elif follow.get("level") == "partial":
        signals.append("speaker_partially_followed_guidance")

    reply = str(next_turn.get("generated_message") or "")
    if not _is_low_energy_like(reply):
        score += 1
        signals.append("counterpart_replied_with_more_than_cold_phrase")
    else:
        if interaction_mode == "probe_lightly":
            signals.append("probe_confirmed_counterpart_still_low_energy")
        else:
            score -= 1
            signals.append("counterpart_reply_still_cold")
    if len(reply.strip()) >= 10:
        score += 1
        signals.append("counterpart_added_detail")

    if interaction_mode == "probe_lightly" and "probe_confirmed_counterpart_still_low_energy" in signals and score <= 0:
        label = "clarified_low_interest"
    elif score >= 2:
        label = "improved"
    elif score <= 0:
        label = "worse_or_same"
    else:
        label = "slightly_improved"
    return {"label": label, "score": score, "signals": signals}


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
            decision = _fast_rescue_decision(pub_msgs)
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
                    decision = _normalize_rescue_decision(
                        {
                            "need_rescue": False,
                            "situation": "none",
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
            if need:
                situation = str(decision.get("situation") or "awkward")
                mutual_intent_assessment = str(
                    decision.get("mutual_intent_assessment") or "interest_unclear"
                )
                interaction_mode = str(decision.get("interaction_mode") or "repair")
                rescue_style = str(decision.get("rescue_style") or "switch_topic")
                reason = str(decision.get("reason") or "")
                if interaction_mode == "repair":
                    q = (
                        f"（系统判断：当前更像双方都还想继续聊，但这轮卡在沟通上。"
                        f"情况标签：{situation}；意愿判断：{mutual_intent_assessment}；建议风格：{rescue_style}。"
                        f"{reason}请先指出我这边当前最需要注意的问题，再给我自然、得体、适合我身份的接话建议。"
                        "不要直接代写成一条可发送消息。）"
                    )
                else:
                    q = (
                        f"（系统判断：当前更像意愿还不够明确，不适合讨好式救场。"
                        f"情况标签：{situation}；意愿判断：{mutual_intent_assessment}；建议风格：{rescue_style}。"
                        f"{reason}请先指出我这边当前最需要注意的问题，再给我低压试探建议、别硬推的提醒，"
                        "以及如果对方继续很冷该怎么把节奏收住。不要直接代写成一条可发送消息。）"
                    )
                assistant_started = perf_counter()
                hint = assistant_query(conn, thread_id, speaker, q, now=ts)
                assistant_elapsed_ms = int((perf_counter() - assistant_started) * 1000)
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
                        "assistant_latency_ms": assistant_elapsed_ms,
                        "assistant_guidance": hint.get("assistant_guidance"),
                    }
                )
                emit(f"{turn_label}: assistant hint posted for {speaker} in {assistant_elapsed_ms} ms")

        msgs = list_messages(conn, thread_id, speaker, limit=200)
        transcript = format_visible_transcript(msgs)
        try:
            body = _next_dyadic_message(
                llm=llm,
                user_id=speaker,
                brief=brief,
                transcript=transcript,
                stress_directive=stress_directive,
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
        turn_records.append(turn_record)
        emit(f"{turn_label}: message committed")

    for idx, record in enumerate(turn_records):
        record["assistant_follow_assessment"] = _assistant_follow_assessment(
            str(record.get("generated_message") or ""),
            record.get("assistant_guidance"),
            assistant_invoked=bool(record.get("assistant_invoked")),
        )
        record["assistant_recovery_assessment"] = _assistant_recovery_assessment(
            record,
            turn_records[idx + 1] if idx + 1 < len(turn_records) else None,
        )

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
    strong_follow = [
        r for r in intervention_records if (r.get("assistant_follow_assessment") or {}).get("level") == "strong"
    ]
    repair_interventions = [r for r in intervention_records if (r.get("interaction_mode") or "") == "repair"]
    probe_interventions = [
        r for r in intervention_records if (r.get("interaction_mode") or "") == "probe_lightly"
    ]
    hold_decisions = [r for r in turn_records if (r.get("interaction_mode") or "") == "hold"]
    overpush_risk_turns = [
        r
        for r in intervention_records
        if (r.get("mutual_intent_assessment") or "") in {"interest_low", "boundary_risk"}
    ]
    recoverable_interventions = [
        r
        for r in intervention_records
        if (r.get("assistant_recovery_assessment") or {}).get("label") not in ("not_applicable", "pending")
    ]
    improved_recovery = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "improved"
    ]
    clarified_low_interest = [
        r
        for r in recoverable_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "clarified_low_interest"
    ]
    recoverable_probe_interventions = [
        r
        for r in probe_interventions
        if (r.get("assistant_recovery_assessment") or {}).get("label") not in ("not_applicable", "pending")
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
        "proactive_rescue_events": rescue_log,
        "stress_mode": sm,
        "stress_events": stress_events,
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
            "assistant_invoke_avg_ms": round(sum(assistant_latencies) / len(assistant_latencies), 2)
            if assistant_latencies
            else None,
            "assistant_invoke_max_ms": max(assistant_latencies) if assistant_latencies else None,
            "repair_intervention_turns": len(repair_interventions),
            "probe_intervention_turns": len(probe_interventions),
            "hold_decision_turns": len(hold_decisions),
            "overpush_risk_turns": len(overpush_risk_turns),
            "strong_follow_rate": round(len(strong_follow) / len(intervention_records), 4)
            if intervention_records
            else None,
            "recoverable_intervention_turns": len(recoverable_interventions),
            "improved_recovery_rate": round(len(improved_recovery) / len(recoverable_interventions), 4)
            if recoverable_interventions
            else None,
            "clarified_low_interest_rate": round(
                len(clarified_low_interest) / len(recoverable_probe_interventions),
                4,
            )
            if recoverable_probe_interventions
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
