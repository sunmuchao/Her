"""Optional LLM assistant replies via OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_VIS_DYADIC = "dyadic"

_DEFAULT_PROBLEM_TAGS = ["cold_reply"]
_DEFAULT_STRATEGY_TAGS = ["share_detail", "ask_easy_question"]


def build_dyadic_context_for_assistant(conn, thread_id: str, *, limit: int = 20) -> str:
    lim = max(1, min(int(limit), 50))
    cur = conn.execute(
        """
        SELECT author_id, body FROM chat_messages
        WHERE thread_id = ? AND visibility = ?
        ORDER BY message_id DESC LIMIT ?
        """,
        (thread_id, _VIS_DYADIC, lim),
    )
    rows = list(reversed(cur.fetchall()))
    return "\n".join(f"{r['author_id']}: {r['body']}" for r in rows)


def _strip_json_object(text: str) -> dict[str, Any]:
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


def _to_clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None or value == "":
        items = []
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def normalize_assistant_guidance(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "current_problem": _to_clean_list(data.get("current_problem")) or ["当前问题还不够明确。"],
        "problem_tags": _to_clean_list(data.get("problem_tags")) or list(_DEFAULT_PROBLEM_TAGS),
        "avoid": _to_clean_list(data.get("avoid")),
        "topic_directions": _to_clean_list(data.get("topic_directions")),
        "easy_question_types": _to_clean_list(data.get("easy_question_types")),
        "strategy_tags": _to_clean_list(data.get("strategy_tags")) or list(_DEFAULT_STRATEGY_TAGS),
        "reply_suggestions": _to_clean_list(data.get("reply_suggestions")) or ["先回应对方上一句里的具体信息。"],
        "profile_hooks_used": _to_clean_list(data.get("profile_hooks_used")),
    }


def build_placeholder_assistant_guidance(*, profile_hooks: list[str] | None = None) -> dict[str, Any]:
    hooks = list(profile_hooks or [])
    topic_directions = hooks[:2] if hooks else ["周末安排", "最近放松方式"]
    guidance = {
        "current_problem": ["暂未接入模型，暂时无法自动判断当前最核心的卡点。"],
        "problem_tags": ["placeholder"],
        "avoid": ["不要连续只回短句", "不要一直只抛封闭问题"],
        "topic_directions": topic_directions,
        "easy_question_types": ["低门槛生活习惯问题"],
        "strategy_tags": ["share_detail", "ask_easy_question", "switch_topic"],
        "reply_suggestions": [
            "先回应对方上一句里最具体的信息，再补一点自己的真实感受。",
            "如果旧话题已经聊干了，就顺势切到更生活化、更容易回答的话题。",
            "最终发出去的话请自己组织，不要照搬模板。",
        ],
        "profile_hooks_used": hooks[:3],
    }
    return normalize_assistant_guidance(guidance)


def render_assistant_guidance(guidance: dict[str, Any]) -> str:
    g = normalize_assistant_guidance(guidance)
    lines: list[str] = ["【助手建议】", "当前问题："]
    for idx, item in enumerate(g["current_problem"], start=1):
        lines.append(f"{idx}. {item}")
    if g["avoid"]:
        lines.append("先别继续这样聊：")
        for idx, item in enumerate(g["avoid"], start=1):
            lines.append(f"{idx}. {item}")
    if g["topic_directions"]:
        lines.append("建议优先换到这些话题类型：")
        for idx, item in enumerate(g["topic_directions"], start=1):
            lines.append(f"{idx}. {item}")
    if g["easy_question_types"]:
        lines.append("更容易回答的问题类型：")
        for idx, item in enumerate(g["easy_question_types"], start=1):
            lines.append(f"{idx}. {item}")
    lines.append("回复建议：")
    for idx, item in enumerate(g["reply_suggestions"], start=1):
        lines.append(f"{idx}. {item}")
    if g["profile_hooks_used"]:
        lines.append("已参考画像钩子：")
        for idx, item in enumerate(g["profile_hooks_used"], start=1):
            lines.append(f"{idx}. {item}")
    return "\n".join(lines)


def parse_assistant_guidance(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return normalize_assistant_guidance(_strip_json_object(raw))
    except (json.JSONDecodeError, ValueError):
        pass

    sections = {
        "current_problem": "当前问题：",
        "avoid": "先别继续这样聊：",
        "topic_directions": "建议优先换到这些话题类型：",
        "easy_question_types": "更容易回答的问题类型：",
        "reply_suggestions": "回复建议：",
        "profile_hooks_used": "已参考画像钩子：",
    }
    current: str | None = None
    data: dict[str, list[str]] = {k: [] for k in sections}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        matched = False
        for key, header in sections.items():
            if stripped == header:
                current = key
                matched = True
                break
        if matched or current is None:
            continue
        item = re.sub(r"^\d+\.\s*", "", stripped).strip()
        if item:
            data[current].append(item)
    if not any(data.values()):
        return None
    parsed = {
        "current_problem": data["current_problem"],
        "problem_tags": _DEFAULT_PROBLEM_TAGS,
        "avoid": data["avoid"],
        "topic_directions": data["topic_directions"],
        "easy_question_types": data["easy_question_types"],
        "strategy_tags": _DEFAULT_STRATEGY_TAGS,
        "reply_suggestions": data["reply_suggestions"],
        "profile_hooks_used": data["profile_hooks_used"],
    }
    return normalize_assistant_guidance(parsed)


def generate_assistant_guidance(
    *,
    user_query: str,
    thread_context: str,
    actor_profile_summary: str = "",
    counterpart_profile_summary: str = "",
    profile_hooks: list[str] | None = None,
) -> dict[str, Any] | None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    model = (os.environ.get("HER_CHAT_ASSISTANT_MODEL") or "gpt-4o-mini").strip()
    base = (
        os.environ.get("HER_CHAT_ASSISTANT_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    ).strip()
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client_kwargs: dict[str, str] = {"api_key": key}
    if base:
        client_kwargs["base_url"] = base
    client = OpenAI(**client_kwargs)
    system = (
        "你是相亲/交友场景下的对话教练，不是代聊者。"
        "你只负责指出当前对话问题，并给出下一步可执行的聊天策略，不要代写一条可以直接发送给对方的整句消息。"
        "若提供了画像钩子，请优先从双方交集或当前说话人的真实生活里选，而不是泛泛建议电影、旅行这类万能话题。"
        "你的建议必须足够具体，优先回答：现在最关键的问题是什么、别继续做什么、建议换到什么低门槛话题、适合问什么更容易回答的问题。"
        "只输出一个 JSON 对象，不要 Markdown、不要代码块。"
    )
    user_block = (
        f"最近对话（双方可见）：\n{thread_context or '（暂无）'}\n\n"
        f"当前说话人画像摘要：\n{actor_profile_summary or '（暂无）'}\n\n"
        f"对方画像摘要：\n{counterpart_profile_summary or '（暂无）'}\n\n"
        f"优先可用画像钩子：{', '.join(profile_hooks or []) or '（暂无）'}\n\n"
        f"用户问题：{user_query}\n\n"
        "输出 JSON：\n"
        "{\n"
        '  "current_problem": ["<1-3 条具体问题>"],\n'
        '  "problem_tags": ["<closed_reply|topic_dead_end|awkward_transition|low_energy|misread|boundary_risk 等>"],\n'
        '  "avoid": ["<1-3 条不要继续做的事>"],\n'
        '  "topic_directions": ["<1-3 个建议切换的话题类型>"],\n'
        '  "easy_question_types": ["<1-2 个更容易回答的问题类型>"],\n'
        '  "strategy_tags": ["<acknowledge_coldness|switch_topic|ask_easy_question|share_detail|expand_detail|graceful_exit 等>"],\n'
        '  "reply_suggestions": ["<2-4 条可执行建议，不要代写整句>"],\n'
        '  "profile_hooks_used": ["<实际用到的画像钩子，必须来自给定画像摘要或钩子>"]\n'
        "}\n"
        "要求：不要编造画像中没有的事实；不要写成整句代发文案；建议要口语场景可执行。"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            max_tokens=700,
            temperature=0.2,
        )
        choice = resp.choices[0].message.content
        out = (choice or "").strip()
        if not out:
            return None
        return normalize_assistant_guidance(_strip_json_object(out))
    except Exception:
        return None


def generate_assistant_reply(
    *,
    user_query: str,
    thread_context: str,
    actor_profile_summary: str = "",
    counterpart_profile_summary: str = "",
    profile_hooks: list[str] | None = None,
) -> str | None:
    guidance = generate_assistant_guidance(
        user_query=user_query,
        thread_context=thread_context,
        actor_profile_summary=actor_profile_summary,
        counterpart_profile_summary=counterpart_profile_summary,
        profile_hooks=profile_hooks,
    )
    if guidance is None:
        return None
    return render_assistant_guidance(guidance)


__all__ = [
    "build_assistant_profile_context",
    "build_dyadic_context_for_assistant",
    "build_placeholder_assistant_guidance",
    "generate_assistant_guidance",
    "generate_assistant_reply",
    "normalize_assistant_guidance",
    "parse_assistant_guidance",
    "render_assistant_guidance",
]
