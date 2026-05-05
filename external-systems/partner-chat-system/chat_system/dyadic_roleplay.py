"""Two LLM personas chat in a real ``chat_threads`` row; proactive assistant rescue; persona self-evaluation."""

from __future__ import annotations

import json
import random
import re
import zlib
from datetime import datetime, timedelta
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
        "你只阅读「双方可见」记录，判断在**下一位用户即将开口前**，是否应由系统助手介入**救场**。\n"
        "需要救场的典型信号：明显冷场、尬聊、话不投机、轻微冒犯或僵持、反复寒暄无实质进展、出现误解或对立苗头、对方明显接不下去等。\n"
        "不要过度干预：自然、有来有往、气氛正常时不要救场。\n"
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
        '  "situation": "<cold|awkward|stuck|rude|off_topic|none 选一>",\n'
        '  "reason": "<极短中文，说明为何需要或不需要救场>"\n'
        "}\n"
        "若 need_rescue 为 true，含义是：建议系统助手**仅对下一位发言者**提供私下回复建议，帮其自然接话、化解尴尬或缓和气氛。"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        return strip_json_object(raw)
    except (json.JSONDecodeError, ValueError):
        return {"need_rescue": False, "situation": "none", "reason": "调度解析失败，默认不介入", "parse_error": True}


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
        f"{stress_block}"
    )
    raw = llm([{"role": "system", "content": system}, {"role": "user", "content": user}]).strip()
    raw = raw.strip('"').strip()
    return raw or "我先了解一下你的情况～"


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


def _naturalness_assessment(text: str) -> dict[str, Any]:
    t = str(text or "").strip()
    flags: list[str] = []
    for phrase in _ANALYTIC_PHRASES:
        if phrase in t:
            flags.append(f"analytic_phrase:{phrase}")
    if len(t) >= 48 and t.count("，") >= 3:
        flags.append("too_expository")
    if "首先" in t or "其次" in t or "总之" in t:
        flags.append("structured_monologue")
    return {
        "score": max(1, 5 - len(flags)),
        "flags": flags,
    }


def _gold_rescue_for_turn(beats: list[StressBeat]) -> dict[str, Any]:
    return {
        "need_rescue": bool(beats),
        "source_beats": [b.id for b in beats],
        "expected_problem_tags": _dedupe_strs([tag for b in beats for tag in b.expected_problem_tags]),
        "suggested_strategy_tags": _dedupe_strs([tag for b in beats for tag in b.suggested_strategy_tags]),
        "max_severity": max([b.severity for b in beats], default=0),
    }


def _assistant_follow_assessment(message: str, guidance: dict[str, Any] | None) -> dict[str, Any]:
    if not guidance:
        return {"level": "not_applicable", "score": 0, "signals": []}
    text = str(message or "").strip()
    signals: list[str] = []
    score = 0
    strategy_tags = set(str(x) for x in guidance.get("strategy_tags") or [])
    hooks = [str(x) for x in guidance.get("profile_hooks_used") or []]

    if _is_cold_like(text):
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
    if hooks and any(hook and hook in text for hook in hooks):
        score += 1
        signals.append("used_profile_hook")
    if "switch_topic" in strategy_tags and len(text) >= 12 and not any(
        token in text for token in ("桌游", "推荐")
    ):
        score += 1
        signals.append("switched_topic")

    if score >= 3:
        level = "strong"
    elif score >= 1:
        level = "partial"
    else:
        level = "none"
    return {"level": level, "score": score, "signals": signals}


def _assistant_recovery_assessment(current_turn: dict[str, Any], next_turn: dict[str, Any] | None) -> dict[str, Any]:
    follow = current_turn.get("assistant_follow_assessment") or {}
    score = 0
    signals: list[str] = []
    if follow.get("level") == "strong":
        score += 1
        signals.append("speaker_followed_guidance_well")
    elif follow.get("level") == "partial":
        signals.append("speaker_partially_followed_guidance")

    if next_turn is None:
        signals.append("no_following_reply")
    else:
        reply = str(next_turn.get("generated_message") or "")
        if not _is_cold_like(reply):
            score += 1
            signals.append("counterpart_replied_with_more_than_cold_phrase")
        else:
            score -= 1
            signals.append("counterpart_reply_still_cold")
        if len(reply.strip()) >= 10:
            score += 1
            signals.append("counterpart_added_detail")

    if score >= 2:
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
            hint = assistant_query(conn, thread_id, speaker, fixed_assistant_query, now=ts)
            turn_record["assistant_invoked"] = True
            turn_record["assistant_message_id"] = hint.get("message_id")
            turn_record["assistant_guidance"] = hint.get("assistant_guidance")
            turn_record["assistant_profile_context"] = hint.get("assistant_profile_context")
        elif mode == "proactive":
            pub = dyadic_public_transcript(conn, thread_id, participant_a_id)
            decision = _orchestrator_rescue_decision(
                llm=llm,
                next_speaker_id=speaker,
                participant_a_id=participant_a_id,
                participant_b_id=participant_b_id,
                dyadic_transcript=pub,
            )
            need = bool(decision.get("need_rescue"))
            emit(
                f"{turn_label}: rescue need={need} situation={decision.get('situation') or 'none'} "
                f"reason={_preview_text(str(decision.get('reason') or ''))}"
            )
            turn_record["rescue_decision"] = decision
            if need:
                situation = str(decision.get("situation") or "awkward")
                reason = str(decision.get("reason") or "")
                q = (
                    f"（系统判断当前双方可见对话可能需要接话/救场，情况标签：{situation}。"
                    f"{reason}请先指出我这边当前最需要注意的问题，再给我自然、得体、适合我身份的接话建议。"
                    "不要直接代写成一条可发送消息。）"
                )
                hint = assistant_query(conn, thread_id, speaker, q, now=ts)
                turn_record["assistant_invoked"] = True
                turn_record["assistant_message_id"] = hint.get("message_id")
                turn_record["assistant_guidance"] = hint.get("assistant_guidance")
                turn_record["assistant_profile_context"] = hint.get("assistant_profile_context")
                rescue_log.append(
                    {
                        "turn": i,
                        "speaker": speaker,
                        "decision": decision,
                        "assistant_guidance": hint.get("assistant_guidance"),
                    }
                )
                emit(f"{turn_label}: assistant hint posted for {speaker}")

        msgs = list_messages(conn, thread_id, speaker, limit=200)
        transcript = format_visible_transcript(msgs)
        body = _next_dyadic_message(
            llm=llm,
            user_id=speaker,
            brief=brief,
            transcript=transcript,
            stress_directive=stress_directive,
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
    strong_follow = [
        r for r in intervention_records if (r.get("assistant_follow_assessment") or {}).get("level") == "strong"
    ]
    improved_recovery = [
        r
        for r in intervention_records
        if (r.get("assistant_recovery_assessment") or {}).get("label") == "improved"
    ]

    emit(f"starting self-evaluation for {participant_a_id}")
    eval_a = _persona_self_evaluation(
        llm=llm,
        user_id=participant_a_id,
        brief=brief_a,
        transcript=format_visible_transcript(
            list_messages(conn, thread_id, participant_a_id, limit=500)
        ),
    )
    conn.commit()
    emit(
        f"self-evaluation ready for {participant_a_id}: conversation_score={eval_a.get('conversation_score')}, "
        f"assistant_score={eval_a.get('assistant_score')}"
    )
    emit(f"starting self-evaluation for {participant_b_id}")
    eval_b = _persona_self_evaluation(
        llm=llm,
        user_id=participant_b_id,
        brief=brief_b,
        transcript=format_visible_transcript(
            list_messages(conn, thread_id, participant_b_id, limit=500)
        ),
    )
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
            "strong_follow_rate": round(len(strong_follow) / len(intervention_records), 4)
            if intervention_records
            else None,
            "improved_recovery_rate": round(len(improved_recovery) / len(intervention_records), 4)
            if intervention_records
            else None,
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
