"""Optional LLM assistant replies via OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .assistant_contract import (
    DEFAULT_MUTUAL_INTENT_ASSESSMENT,
    GUIDANCE_SCHEMA_VERSION,
    INTERACTION_MODES,
    MUTUAL_INTENT_ASSESSMENTS,
    format_choice_values,
    normalize_interaction_mode as _normalize_contract_interaction_mode,
    normalize_mutual_intent_assessment as _normalize_contract_mutual_intent_assessment,
)

_VIS_DYADIC = "dyadic"

_DEFAULT_PROBLEM_TAGS = ["cold_reply"]
_DEFAULT_STRATEGY_TAGS = ["share_detail", "ask_easy_question"]
_MUTUAL_INTENT_CHOICES = format_choice_values(MUTUAL_INTENT_ASSESSMENTS)
_INTERACTION_MODE_CHOICES = format_choice_values(INTERACTION_MODES)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return float(default)


def _default_rescue_flow() -> list[str]:
    return [
        "先接住对方上一句里还能接的话点，不要像没看到一样硬换题。",
        "如果已经明显有点冷，就轻轻承认一下节奏有点干，再换到更生活化的话题。",
        "优先问对方一句就能回答的问题，让对方更容易接回来。",
    ]


def _default_graceful_exit_plan() -> list[str]:
    return [
        "如果对方连续两轮都很冷，别硬拽，轻轻收一下就行。",
        "可以把节奏放慢，留一句以后再聊也行，别把气氛越救越僵。",
    ]


def _default_why_not_to_push(mutual_intent_assessment: str, interaction_mode: str) -> list[str]:
    if interaction_mode == "probe_lightly":
        return ["先别默认对方很想继续聊，避免一上来就重投入或连环追问。"]
    if interaction_mode == "hold":
        if mutual_intent_assessment == "boundary_risk":
            return ["这轮已经碰到边界或压力点，不适合再按推进关系的方式处理。"]
        return ["对方当前投入偏低，再主动加码很容易把自己放到被动位置。"]
    return []


def _default_low_pressure_options(interaction_mode: str) -> list[str]:
    if interaction_mode != "probe_lightly":
        return []
    return [
        "先丢一个低门槛、对方一句就能接的问题试一下。",
        "如果对方还是冷，就别继续加码输出，先把节奏放慢。",
    ]


def _humanize_mutual_intent_assessment(value: str) -> str:
    mapping = {
        "communication_problem": "更像双方都还想继续聊，只是这轮卡在表达或接话上。",
        "interest_unclear": "目前更像意愿还不够明确，先别默认对方很想继续聊。",
        "interest_low": "对方继续聊的投入偏低，不适合再靠主动讨好去硬拉。",
        "boundary_risk": "这轮已经碰到边界或压力点，不适合按正常推进来处理。",
        "normal": "当前没有明显卡点，先顺着自然聊就行。",
    }
    return mapping.get(value, mapping[DEFAULT_MUTUAL_INTENT_ASSESSMENT])


def _humanize_interaction_mode(value: str) -> str:
    mapping = {
        "repair": "正常修复：接住问题，再自然把话题往下带。",
        "probe_lightly": "低压试探：先轻轻试一下，不要一上来就重投入救场。",
        "hold": "先收住：别再加码推进，也别做讨好式救场。",
        "none": "正常继续：这轮不需要额外介入。",
    }
    return mapping.get(value, mapping["probe_lightly"])


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
    mutual_intent_assessment = _normalize_contract_mutual_intent_assessment(
        data.get("mutual_intent_assessment")
    )
    interaction_mode = _normalize_contract_interaction_mode(
        data.get("interaction_mode"),
        mutual_intent_assessment=mutual_intent_assessment,
    )
    return {
        "schema_version": GUIDANCE_SCHEMA_VERSION,
        "mutual_intent_assessment": mutual_intent_assessment,
        "interaction_mode": interaction_mode,
        "current_problem": _to_clean_list(data.get("current_problem")) or ["当前问题还不够明确。"],
        "problem_tags": _to_clean_list(data.get("problem_tags")) or list(_DEFAULT_PROBLEM_TAGS),
        "why_not_to_push": _to_clean_list(data.get("why_not_to_push"))
        or _default_why_not_to_push(mutual_intent_assessment, interaction_mode),
        "low_pressure_options": _to_clean_list(data.get("low_pressure_options"))
        or _default_low_pressure_options(interaction_mode),
        "avoid": _to_clean_list(data.get("avoid")),
        "topic_directions": _to_clean_list(data.get("topic_directions")),
        "easy_question_types": _to_clean_list(data.get("easy_question_types")),
        "rescue_flow": _to_clean_list(data.get("rescue_flow")) or _default_rescue_flow(),
        "graceful_exit_plan": _to_clean_list(data.get("graceful_exit_plan")) or _default_graceful_exit_plan(),
        "strategy_tags": _to_clean_list(data.get("strategy_tags")) or list(_DEFAULT_STRATEGY_TAGS),
        "reply_suggestions": _to_clean_list(data.get("reply_suggestions")) or ["先回应对方上一句里的具体信息。"],
        "profile_hooks_used": _to_clean_list(data.get("profile_hooks_used")),
    }


def build_placeholder_assistant_guidance(*, profile_hooks: list[str] | None = None) -> dict[str, Any]:
    hooks = list(profile_hooks or [])
    topic_directions = hooks[:2] if hooks else ["周末安排", "最近放松方式"]
    guidance = {
        "mutual_intent_assessment": "interest_unclear",
        "interaction_mode": "probe_lightly",
        "current_problem": ["暂未接入模型，暂时无法自动判断当前最核心的卡点。"],
        "problem_tags": ["placeholder"],
        "why_not_to_push": ["先别默认对方一定想继续聊，先用低压方式试一下。"],
        "low_pressure_options": ["先问一个更容易回答的小问题，再看对方愿不愿意继续接。"],
        "avoid": ["不要连续只回短句", "不要一直只抛封闭问题"],
        "topic_directions": topic_directions,
        "easy_question_types": ["低门槛生活习惯问题"],
        "rescue_flow": [
            "先接住对方上一句，不要马上把话题扔空。",
            "如果旧话题已经聊干了，就切到更容易回答的生活化话题。",
            "最后优先问一句轻一点、对方更容易回的问题。",
        ],
        "graceful_exit_plan": [
            "如果对方还是连续很冷，就别硬拉，先把节奏收住。",
            "可以留个轻一点的收口，给下次再聊留余地。",
        ],
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
    lines: list[str] = [
        "【助手建议】",
        "意愿判断：",
        f"1. {_humanize_mutual_intent_assessment(g['mutual_intent_assessment'])}",
        "这轮处理方式：",
        f"1. {_humanize_interaction_mode(g['interaction_mode'])}",
        "当前问题：",
    ]
    for idx, item in enumerate(g["current_problem"], start=1):
        lines.append(f"{idx}. {item}")
    if g["why_not_to_push"]:
        lines.append("现在别硬推的原因：")
        for idx, item in enumerate(g["why_not_to_push"], start=1):
            lines.append(f"{idx}. {item}")
    if g["low_pressure_options"]:
        lines.append("如果只适合低压试探：")
        for idx, item in enumerate(g["low_pressure_options"], start=1):
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
    if g["rescue_flow"]:
        lines.append("建议按这个顺序来：")
        for idx, item in enumerate(g["rescue_flow"], start=1):
            lines.append(f"{idx}. {item}")
    if g["graceful_exit_plan"]:
        lines.append("如果还是接不动：")
        for idx, item in enumerate(g["graceful_exit_plan"], start=1):
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
        "mutual_intent_assessment": "意愿判断：",
        "interaction_mode": "这轮处理方式：",
        "current_problem": "当前问题：",
        "why_not_to_push": "现在别硬推的原因：",
        "low_pressure_options": "如果只适合低压试探：",
        "avoid": "先别继续这样聊：",
        "topic_directions": "建议优先换到这些话题类型：",
        "easy_question_types": "更容易回答的问题类型：",
        "rescue_flow": "建议按这个顺序来：",
        "graceful_exit_plan": "如果还是接不动：",
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
        "mutual_intent_assessment": data["mutual_intent_assessment"][0]
        if data["mutual_intent_assessment"]
        else DEFAULT_MUTUAL_INTENT_ASSESSMENT,
        "interaction_mode": data["interaction_mode"][0] if data["interaction_mode"] else "",
        "current_problem": data["current_problem"],
        "problem_tags": _DEFAULT_PROBLEM_TAGS,
        "why_not_to_push": data["why_not_to_push"],
        "low_pressure_options": data["low_pressure_options"],
        "avoid": data["avoid"],
        "topic_directions": data["topic_directions"],
        "easy_question_types": data["easy_question_types"],
        "rescue_flow": data["rescue_flow"],
        "graceful_exit_plan": data["graceful_exit_plan"],
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
    model = (
        os.environ.get("HER_CHAT_ASSISTANT_FAST_MODEL")
        or os.environ.get("HER_CHAT_ASSISTANT_RESCUE_MODEL")
        or os.environ.get("HER_CHAT_ASSISTANT_MODEL")
        or "gpt-4o-mini"
    ).strip()
    base = (
        os.environ.get("HER_CHAT_ASSISTANT_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    ).strip()
    try:
        from openai import OpenAI
    except ImportError:
        return None
    assistant_timeout_sec = max(10.0, min(_env_float("HER_CHAT_ASSISTANT_TIMEOUT_SEC", 40.0), 120.0))
    client_kwargs: dict[str, Any] = {
        "api_key": key,
        "max_retries": 0,
        "timeout": assistant_timeout_sec,
    }
    if base:
        client_kwargs["base_url"] = base
    client = OpenAI(**client_kwargs)
    system = (
        "你是相亲/交友场景下的对话教练，不是代聊者。"
        "你只负责指出当前对话问题，并给出下一步可执行的聊天策略，不要代写一条可以直接发送给对方的整句消息。"
        "你的职责重点是帮助“双方都还想继续聊，但这轮沟通卡住了”的人。"
        "如果你判断当前更像意愿不明确、对方投入偏低，或已经碰到边界/压力点，就不要给讨好型救场，而是改成低压试探或先收住。"
        "请先判断当前属于 communication_problem、interest_unclear、interest_low、boundary_risk、normal 哪一类。"
        "只有 communication_problem 才使用 repair；interest_unclear 使用 probe_lightly；interest_low 或 boundary_risk 使用 hold。"
        "若提供了画像钩子，请优先从双方交集或当前说话人的真实生活里选，而不是泛泛建议电影、旅行这类万能话题。"
        "你的建议必须足够具体，优先回答：现在最关键的问题是什么、别继续做什么、建议换到什么低门槛话题、适合问什么更容易回答的问题。"
        "建议尽量写成步骤感强的教练提示，比如先接住、再换题、最后问轻一点的问题。"
        "如果当前局面已经连续偏冷、明显顶不动，允许直接给出体面收口或暂时放慢节奏的止损建议。"
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
        f'  "mutual_intent_assessment": "<{_MUTUAL_INTENT_CHOICES}>",\n'
        f'  "interaction_mode": "<{_INTERACTION_MODE_CHOICES}>",\n'
        '  "current_problem": ["<1-3 条具体问题>"],\n'
        '  "problem_tags": ["<closed_reply|topic_dead_end|awkward_transition|low_energy|misread|boundary_risk 等>"],\n'
        '  "why_not_to_push": ["<0-2 条，说明为什么别讨好式硬推>"],\n'
        '  "low_pressure_options": ["<0-2 条，仅在 probe_lightly 时给>"],\n'
        '  "avoid": ["<1-3 条不要继续做的事>"],\n'
        '  "topic_directions": ["<1-3 个建议切换的话题类型>"],\n'
        '  "easy_question_types": ["<1-2 个更容易回答的问题类型>"],\n'
        '  "rescue_flow": ["<2-4 条分步骤建议，强调先接住、再换题、再问轻问题>"],\n'
        '  "graceful_exit_plan": ["<0-2 条止损建议；只有在局面明显难救时才写>"],\n'
        '  "strategy_tags": ["<acknowledge_coldness|switch_topic|ask_easy_question|share_detail|expand_detail|graceful_exit|probe_lightly 等>"],\n'
        '  "reply_suggestions": ["<2-4 条可执行建议，不要代写整句>"],\n'
        '  "profile_hooks_used": ["<实际用到的画像钩子，必须来自给定画像摘要或钩子>"]\n'
        "}\n"
        "要求：不要编造画像中没有的事实；不要写成整句代发文案；建议要口语场景可执行；"
        "如果 interaction_mode 不是 repair，就明确告诉用户为什么不要硬推。"
    )
    try:
        max_tokens = _env_int("HER_CHAT_ASSISTANT_MAX_TOKENS", 500)
        temperature = _env_float("HER_CHAT_ASSISTANT_TEMPERATURE", 0.1)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            max_tokens=max(200, min(max_tokens, 900)),
            temperature=max(0.0, min(temperature, 1.0)),
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
    "build_dyadic_context_for_assistant",
    "build_placeholder_assistant_guidance",
    "generate_assistant_guidance",
    "generate_assistant_reply",
    "normalize_assistant_guidance",
    "parse_assistant_guidance",
    "render_assistant_guidance",
]
