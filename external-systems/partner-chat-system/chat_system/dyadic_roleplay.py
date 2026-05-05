"""Two LLM personas chat in a real ``chat_threads`` row; proactive assistant rescue; persona self-evaluation."""

from __future__ import annotations

import json
import random
import re
import zlib
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from .scenario_stress import pick_stress_beat
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
        "当消息记录里出现 assistant 发给你的「仅自己可见」草稿时，你可以参考其方向，但最终发出的内容要是你自己的话。"
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
        '  "used_assistant": <true|false 你是否参考过助手草稿>,\n'
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
    fixed_assistant_query: str = "结合当前聊天记录，给我下一句发给对方的要点和一句可直接发送的中文示例（我会自己改）。",
    stress_mode: str | None = None,
    stress_beat_ids: list[str] | None = None,
    stress_seed: int | None = None,
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
    sm = (stress_mode or "none").strip().lower()
    only_stress = set(stress_beat_ids) if stress_beat_ids else None
    srng = _stress_rng(case_id, stress_seed)

    for i in range(rounds):
        ts = t0 + timedelta(seconds=i + 1)
        speaker = participant_a_id if i % 2 == 0 else participant_b_id
        brief = brief_a if i % 2 == 0 else brief_b

        beat = pick_stress_beat(turn_index=i, mode=sm, rng=srng, only_ids=only_stress)
        stress_directive = beat.directive if beat else None
        if beat:
            stress_events.append(
                {
                    "turn": i,
                    "speaker": speaker,
                    "beat_id": beat.id,
                    "category": beat.category,
                }
            )

        if mode == "fixed_turns" and i in fixed_turns:
            assistant_query(conn, thread_id, speaker, fixed_assistant_query, now=ts)
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
            if need:
                situation = str(decision.get("situation") or "awkward")
                reason = str(decision.get("reason") or "")
                q = (
                    f"（系统判断当前双方可见对话可能需要接话/救场，情况标签：{situation}。"
                    f"{reason}请给我自然、得体、适合我身份的下一句建议，并附一条可直接发送的中文示例。）"
                )
                assistant_query(conn, thread_id, speaker, q, now=ts)
                rescue_log.append({"turn": i, "speaker": speaker, "decision": decision})

        msgs = list_messages(conn, thread_id, speaker, limit=200)
        transcript = format_visible_transcript(msgs)
        body = _next_dyadic_message(
            llm=llm,
            user_id=speaker,
            brief=brief,
            transcript=transcript,
            stress_directive=stress_directive,
        )
        post_message(
            conn,
            thread_id,
            speaker,
            body,
            visibility=VIS_DYADIC,
            source=SRC_USER,
            now=ts + timedelta(milliseconds=1),
        )
        conn.commit()

    eval_a = _persona_self_evaluation(
        llm=llm,
        user_id=participant_a_id,
        brief=brief_a,
        transcript=format_visible_transcript(
            list_messages(conn, thread_id, participant_a_id, limit=500)
        ),
    )
    conn.commit()
    eval_b = _persona_self_evaluation(
        llm=llm,
        user_id=participant_b_id,
        brief=brief_b,
        transcript=format_visible_transcript(
            list_messages(conn, thread_id, participant_b_id, limit=500)
        ),
    )
    conn.commit()

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
