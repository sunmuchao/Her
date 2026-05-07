"""Optional LLM assistant replies via OpenAI-compatible Chat Completions API."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
import re
from threading import RLock
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
_DIRECT_SEND_PREFIX_RE = re.compile(
    r"(?:可以说|可以回|回一句|回他|发一句|发给对方|直接说|你就说|例如|比如|试试说|可以发)\s*[：:]"
)
_COACHING_MARKERS = (
    "你可以",
    "可以先",
    "先回应",
    "先接住",
    "再换",
    "最后问",
    "别",
    "不要",
    "建议",
    "优先",
    "如果",
    "试着",
    "回应",
    "承认",
    "换到",
    "话题",
    "问题",
    "节奏",
    "收住",
    "低压",
)
_SUMMARY_ALLOWED_KEYS = (
    "settlement_city",
    "city",
    "job",
    "relationship_goal",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "marriage_timeline",
    "notes",
)
_SUMMARY_KEY_PRIORITY = {
    "settlement_city": 0,
    "city": 0,
    "job": 1,
    "relationship_goal": 2,
    "personality": 3,
    "values": 4,
    "lifestyle": 5,
    "hobbies": 6,
    "marriage_timeline": 7,
    "notes": 8,
}
_GENERIC_PROFILE_HOOKS = frozenset({"电影", "旅行", "旅游", "运动", "健身", "美食"})
_UNSAFE_PROFILE_HOOK_TOKENS = (
    "收入",
    "工资",
    "年薪",
    "房产",
    "彩礼",
    "前任",
    "婚史",
    "离异",
    "孩子",
    "照片",
    "身高",
    "体重",
)
_LOW_BAR_FALLBACK_HOOKS = (
    "周末安排",
    "最近放松方式",
    "同城吃喝",
    "作息节奏",
)
_GUIDANCE_PROMPT_VERSION = 2
_HOLD_CONFLICT_STRATEGY_TAGS = frozenset(
    {
        "probe_lightly",
        "ask_easy_question",
        "share_detail",
        "switch_topic",
    }
)
_RISK_AXIS_LABELS = {
    "appearance": "照片/外貌",
    "income_condition": "收入/条件",
    "privacy_ex": "前任/隐私",
    "meetup_push": "见面推进",
    "pressure_compare": "比较/施压",
    "other": "压力点",
}
_GUIDANCE_RESPONSE_CACHE_LOCK = RLock()
_GUIDANCE_RESPONSE_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


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


def _is_timeout_exception(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc or "").lower()
    return "timeout" in name or "timed out" in text or "deadline exceeded" in text


def _normalize_risk_axis(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    return raw if raw in _RISK_AXIS_LABELS else None


def _normalize_hold_subtype(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"interest_low", "boundary_risk"}:
        return raw
    return None


def _axis_guardrail(risk_axis: str | None) -> str:
    mapping = {
        "appearance": "别继续追着照片、外貌差距这些点问。",
        "income_condition": "别继续盘收入、房车、条件高低。",
        "privacy_ex": "别继续碰前任、婚史、隐私这些点。",
        "meetup_push": "别急着继续推进见面。",
        "pressure_compare": "别继续比较、抬杠、证明自己。",
        "other": "别继续沿当前压力点加码。",
    }
    return mapping.get(risk_axis or "", "别继续沿当前压力点加码。")


def _axis_problem_line(risk_axis: str | None) -> str:
    label = _RISK_AXIS_LABELS.get(risk_axis or "", "当前压力点")
    return f"这轮已经在往“{label}”这条线发紧，不适合再往前推。"


def _hold_quickpath_enabled() -> bool:
    raw = str(os.environ.get("HER_CHAT_ASSISTANT_FAST_BOUNDARY_HOLD") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _guidance_response_cache_enabled() -> bool:
    raw = str(os.environ.get("HER_CHAT_ASSISTANT_RESPONSE_CACHE") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _guidance_response_cache_size() -> int:
    return max(1, min(_env_int("HER_CHAT_ASSISTANT_RESPONSE_CACHE_SIZE", 128), 512))


def _guidance_response_cache_key(
    *,
    model: str,
    base: str,
    temperature: float,
    system: str,
    user_block: str,
) -> str:
    payload = {
        "v": _GUIDANCE_PROMPT_VERSION,
        "model": str(model or ""),
        "base": str(base or ""),
        "temperature": round(float(temperature), 3),
        "system": system,
        "user": user_block,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _guidance_response_cache_get(cache_key: str) -> dict[str, Any] | None:
    if not _guidance_response_cache_enabled():
        return None
    with _GUIDANCE_RESPONSE_CACHE_LOCK:
        cached = _GUIDANCE_RESPONSE_CACHE.get(cache_key)
        if cached is None:
            return None
        _GUIDANCE_RESPONSE_CACHE.move_to_end(cache_key)
        return deepcopy(cached)


def _guidance_response_cache_put(cache_key: str, guidance: dict[str, Any]) -> None:
    if not _guidance_response_cache_enabled():
        return
    with _GUIDANCE_RESPONSE_CACHE_LOCK:
        _GUIDANCE_RESPONSE_CACHE[cache_key] = deepcopy(guidance)
        _GUIDANCE_RESPONSE_CACHE.move_to_end(cache_key)
        while len(_GUIDANCE_RESPONSE_CACHE) > _guidance_response_cache_size():
            _GUIDANCE_RESPONSE_CACHE.popitem(last=False)


@lru_cache(maxsize=4)
def _openai_client_cached(
    api_key: str,
    base: str,
    timeout_sec: float,
):
    from openai import OpenAI

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "max_retries": 0,
        "timeout": timeout_sec,
    }
    if base:
        client_kwargs["base_url"] = base
    return OpenAI(**client_kwargs)


def _should_use_fast_hold_path(
    *,
    preferred_mutual_intent_assessment: str | None,
    preferred_interaction_mode: str | None,
    hold_subtype: str | None,
) -> bool:
    if not _hold_quickpath_enabled():
        return False
    mode = _normalize_contract_interaction_mode(
        preferred_interaction_mode,
        mutual_intent_assessment=_normalize_contract_mutual_intent_assessment(
            preferred_mutual_intent_assessment
        ),
    )
    if mode != "hold":
        return False
    subtype = _normalize_hold_subtype(hold_subtype)
    if subtype == "boundary_risk":
        return True
    return _normalize_contract_mutual_intent_assessment(preferred_mutual_intent_assessment) == "boundary_risk"


def _default_rescue_flow_for_mode(
    interaction_mode: str,
    *,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
) -> list[str]:
    if interaction_mode == "repair":
        return [
            "先接住对方上一句里还能接的话点，不要像没看到一样硬换题。",
            "如果已经明显有点冷，就轻轻承认一下节奏有点干，再换到更生活化的话题。",
            "优先问对方一句就能回答的问题，让对方更容易接回来。",
        ]
    if interaction_mode == "probe_lightly":
        return [
            "先只接一句，不要一下子铺太多解释。",
            "再丢一个低门槛、对方一句就能回的小问题试试看。",
            "如果对方还是冷，就先把节奏放慢，不要继续加码。",
        ]
    if interaction_mode == "hold":
        if hold_subtype == "boundary_risk":
            return [
                _axis_guardrail(risk_axis),
                "别继续解释拉扯，也别急着证明自己没恶意。",
                "如果对方已经明显不舒服，就直接收口。",
            ]
        return [
            "先别顺着敏感点继续往下问，也别急着证明自己没恶意。",
            "把语气收住，别再加码推进关系或推进见面。",
            "如果气氛已经僵了，就留一句体面收口的话，先止损。",
        ]
    return []


def _default_graceful_exit_plan(
    mutual_intent_assessment: str,
    interaction_mode: str,
) -> list[str]:
    if interaction_mode == "hold":
        if mutual_intent_assessment == "boundary_risk":
            return [
                "这轮先别继续碰敏感点，直接把话题收住更稳。",
                "如果对方已经不舒服，就别再解释拉扯，留个台阶先停下。",
            ]
        return [
            "如果对方连续两轮都很冷，别硬拽，轻轻收一下就行。",
            "可以把节奏放慢，留一句以后再聊也行，别把气氛越救越僵。",
        ]
    if interaction_mode == "probe_lightly":
        return [
            "如果试了一下对方还是很冷，就先收，不要继续追着聊。",
        ]
    return []


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


def _default_avoid(
    mutual_intent_assessment: str,
    interaction_mode: str,
    *,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
) -> list[str]:
    if interaction_mode == "repair":
        return ["不要继续追着已经聊干的话题硬问。"]
    if interaction_mode == "probe_lightly":
        return ["不要一上来就连发很多解释或追问。"]
    if interaction_mode == "hold":
        if hold_subtype == "boundary_risk":
            return [_axis_guardrail(risk_axis), "别继续解释拉扯。"]
        if mutual_intent_assessment == "boundary_risk":
            return ["不要继续往让对方有压力或越界的话题上推。"]
        return ["不要继续加码输出或讨好式硬聊。"]
    return []


def _default_advice(
    interaction_mode: str,
    *,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
) -> list[str]:
    if interaction_mode == "repair":
        return [
            "先回应对方上一句里的具体信息。",
            "再把话题换到更容易接、门槛更低的方向。",
            "最后只问一个轻一点、对方容易回答的问题。",
        ]
    if interaction_mode == "probe_lightly":
        return [
            "只丢一个低成本、对方一句就能接的问题试一下。",
            "如果对方还是冷，就别继续加码输出。",
        ]
    if interaction_mode == "hold":
        if hold_subtype == "boundary_risk":
            return [
                _axis_guardrail(risk_axis),
                "这轮先收口，别再往前顶。",
            ]
        return [
            "先把节奏收住，不要继续追着聊。",
            "如果要收口，就留一句轻一点的话给下次余地。",
        ]
    return ["顺着当前话题自然往下聊，不用刻意救场。"]


def _default_strategy_tags(interaction_mode: str) -> list[str]:
    if interaction_mode == "repair":
        return ["share_detail", "ask_easy_question", "switch_topic"]
    if interaction_mode == "probe_lightly":
        return ["probe_lightly", "ask_easy_question", "share_detail"]
    if interaction_mode == "hold":
        return ["graceful_exit", "deescalate", "set_boundary"]
    return []


def _default_current_problem(
    mutual_intent_assessment: str,
    interaction_mode: str,
    *,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
    route_reason: str = "",
) -> list[str]:
    if route_reason:
        return [route_reason]
    if interaction_mode == "repair":
        return ["当前没拿到更细分析，先按“双方还有意愿，但这轮接话卡住了”处理。"]
    if interaction_mode == "probe_lightly":
        return ["当前没拿到更细分析，先按“意愿还不够明确”做低压试探。"]
    if interaction_mode == "hold":
        if hold_subtype == "boundary_risk":
            return [_axis_problem_line(risk_axis)]
        if mutual_intent_assessment == "boundary_risk":
            return ["当前没拿到更细分析，但这轮已经有边界或压力风险，先按收住止损处理。"]
        return ["当前没拿到更细分析，先按“这轮更该收住而不是继续硬聊”处理。"]
    return ["当前没有明显异常，先顺着自然聊，不额外打断。"]


def _default_easy_question_types(interaction_mode: str) -> list[str]:
    if interaction_mode in {"repair", "probe_lightly"}:
        return ["低门槛生活习惯问题"]
    return []


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


def _render_dyadic_context_from_messages(
    messages: list[dict[str, Any]],
    *,
    limit: int,
) -> str:
    dyadic = [message for message in list(messages or []) if str(message.get("visibility") or "") == _VIS_DYADIC]
    tail = dyadic[-limit:]
    if not tail:
        return "（暂无）"
    return "\n".join(f"{message.get('author_id')}: {message.get('body')}" for message in tail)


def build_dyadic_context_for_assistant(
    conn,
    thread_id: str,
    *,
    limit: int = 20,
    visible_messages: list[dict[str, Any]] | None = None,
) -> str:
    lim = max(1, min(int(limit), 50))
    if visible_messages is not None:
        return _render_dyadic_context_from_messages(visible_messages, limit=lim)
    cur = conn.execute(
        """
        SELECT author_id, body FROM chat_messages
        WHERE thread_id = ? AND visibility = ?
        ORDER BY message_id DESC LIMIT ?
        """,
        (thread_id, _VIS_DYADIC, lim),
    )
    rows = list(reversed(cur.fetchall()))
    if not rows:
        return "（暂无）"
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


def _merge_clean_lists(*values: Any) -> list[str]:
    out: list[str] = []
    for value in values:
        for item in _to_clean_list(value):
            if item not in out:
                out.append(item)
    return out


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _clean_profile_hook(value: Any) -> str:
    text = str(value or "").strip().strip("，,。.;；：:")
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:24] if len(text) > 24 else text


def _is_generic_profile_hook(hook: str) -> bool:
    compact = _compact_text(hook)
    return compact in _GENERIC_PROFILE_HOOKS


def _is_safe_profile_hook(hook: str) -> bool:
    compact = _compact_text(hook)
    if not compact or len(compact) <= 1:
        return False
    if any(token in compact for token in _UNSAFE_PROFILE_HOOK_TOKENS):
        return False
    return True


def _profile_hook_fragments(text: str) -> list[str]:
    raw = _clean_profile_hook(text)
    if not raw:
        return []
    out: list[str] = []
    for part in re.split(r"[，,、/|；;：:\s()（）]+", raw):
        item = part.strip()
        if len(item) >= 2 and item not in out:
            out.append(item)
    compact = _compact_text(raw)
    if len(compact) >= 2 and compact not in out:
        out.append(compact)
    return out


def _summary_contains_hook(summary: str, hook: str) -> bool:
    body = _compact_text(summary)
    return bool(body) and any(fragment in body for fragment in _profile_hook_fragments(hook))


def _parse_profile_summary(summary: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in str(summary or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition("：")
        if not sep:
            key, sep, value = stripped.partition(":")
        if not sep:
            continue
        norm_key = key.strip()
        norm_val = value.strip()
        if not norm_key or not norm_val:
            continue
        out.append((norm_key, norm_val))
    return out


def _trim_summary_value(key: str, value: str, preferred_hooks: list[str]) -> str:
    raw = str(value or "").replace("\n", " ").strip()
    if key in {"lifestyle", "hobbies", "notes", "values", "personality"}:
        items = [item.strip() for item in re.split(r"[，,、；;]+", raw) if item.strip()]
        preferred_items = [
            item
            for item in items
            if any(_summary_contains_hook(item, hook) for hook in preferred_hooks)
        ]
        chosen = preferred_items or items[:2]
        raw = "、".join(chosen[:2])
    if len(raw) <= 28:
        return raw
    return raw[:27] + "…"


def _safe_profile_summary(summary: str, preferred_hooks: list[str]) -> str:
    rows: list[tuple[int, int, str]] = []
    for idx, (key, value) in enumerate(_parse_profile_summary(summary)):
        if key not in _SUMMARY_ALLOWED_KEYS:
            continue
        trimmed = _trim_summary_value(key, value, preferred_hooks)
        if not trimmed:
            continue
        hook_bonus = 0 if any(_summary_contains_hook(trimmed, hook) for hook in preferred_hooks) else 1
        priority = _SUMMARY_KEY_PRIORITY.get(key, 99)
        rows.append((hook_bonus, priority, idx, f"{key}：{trimmed}"))
    rows.sort()
    return "\n".join(item for _, _, _, item in rows[:5])


def _rank_profile_hooks(
    *,
    actor_profile_summary: str,
    counterpart_profile_summary: str,
    profile_hooks: list[str] | None,
) -> dict[str, list[str]]:
    actor_text = str(actor_profile_summary or "")
    counterpart_text = str(counterpart_profile_summary or "")
    shared: list[str] = []
    actor_only: list[str] = []
    counterpart_only: list[str] = []
    unmatched_specific: list[str] = []
    generic_only: list[str] = []
    for raw_hook in _to_clean_list(profile_hooks):
        hook = _clean_profile_hook(raw_hook)
        if not _is_safe_profile_hook(hook):
            continue
        in_actor = _summary_contains_hook(actor_text, hook)
        in_counterpart = _summary_contains_hook(counterpart_text, hook)
        if in_actor and in_counterpart:
            if hook not in shared:
                shared.append(hook)
            continue
        if in_actor and not _is_generic_profile_hook(hook):
            if hook not in actor_only:
                actor_only.append(hook)
            continue
        if in_counterpart and not _is_generic_profile_hook(hook):
            if hook not in counterpart_only:
                counterpart_only.append(hook)
            continue
        if not _is_generic_profile_hook(hook):
            if hook not in unmatched_specific:
                unmatched_specific.append(hook)
            continue
        if _is_generic_profile_hook(hook):
            if hook not in generic_only:
                generic_only.append(hook)
    selected: list[str] = []
    for hook in shared + actor_only + unmatched_specific:
        if hook not in selected:
            selected.append(hook)
    fallback: list[str] = []
    for hook in _LOW_BAR_FALLBACK_HOOKS:
        if hook not in selected and hook not in fallback:
            fallback.append(hook)
    if len(selected) < 4:
        for hook in counterpart_only:
            if hook not in selected:
                selected.append(hook)
            if len(selected) >= 4:
                break
    return {
        "shared_hooks": shared[:3],
        "actor_hooks": actor_only[:4],
        "counterpart_hooks": counterpart_only[:4],
        "unmatched_specific_hooks": unmatched_specific[:4],
        "generic_hooks": generic_only[:4],
        "fallback_hooks": fallback[:3],
        "selected_hooks": selected[:4],
    }


def _default_topic_directions(selected_hooks: list[str], *, interaction_mode: str) -> list[str]:
    if interaction_mode == "hold":
        return []
    topics: list[str] = []
    for hook in selected_hooks:
        if hook in _LOW_BAR_FALLBACK_HOOKS or not _is_generic_profile_hook(hook):
            topics.append(hook)
        if len(topics) >= 3:
            break
    if topics:
        return topics
    return list(_LOW_BAR_FALLBACK_HOOKS[:2])


def _infer_profile_hooks_used(guidance: dict[str, Any], selected_hooks: list[str]) -> list[str]:
    text_pool = "\n".join(
        _merge_clean_lists(
            guidance.get("topic_directions"),
            guidance.get("advice"),
            guidance.get("rescue_flow"),
            guidance.get("current_problem"),
            guidance.get("low_pressure_options"),
        )
    )
    inferred: list[str] = []
    for hook in selected_hooks:
        if _summary_contains_hook(text_pool, hook) and hook not in inferred:
            inferred.append(hook)
    return inferred[:3]


def _finalize_guidance_with_profile_context(
    guidance: dict[str, Any],
    *,
    selected_hooks: list[str],
) -> dict[str, Any]:
    out = normalize_assistant_guidance(guidance)
    topic_directions = _to_clean_list(out.get("topic_directions"))
    if selected_hooks and (
        not topic_directions or all(_is_generic_profile_hook(topic) for topic in topic_directions)
    ):
        topic_directions = _default_topic_directions(
            selected_hooks,
            interaction_mode=str(out.get("interaction_mode") or ""),
        )
    hooks_used = [hook for hook in _to_clean_list(out.get("profile_hooks_used")) if hook in selected_hooks]
    for hook in _infer_profile_hooks_used(out, selected_hooks):
        if hook not in hooks_used:
            hooks_used.append(hook)
    if not hooks_used and selected_hooks and str(out.get("interaction_mode") or "") != "hold":
        hooks_used = selected_hooks[: min(3, len(selected_hooks))]
    out["topic_directions"] = topic_directions
    out["profile_hooks_used"] = hooks_used[:3]
    return out


def _prepare_profile_context_for_guidance(
    *,
    actor_profile_summary: str,
    counterpart_profile_summary: str,
    profile_hooks: list[str] | None,
) -> dict[str, Any]:
    ranked = _rank_profile_hooks(
        actor_profile_summary=actor_profile_summary,
        counterpart_profile_summary=counterpart_profile_summary,
        profile_hooks=profile_hooks,
    )
    preferred_hooks = list(ranked.get("selected_hooks") or [])
    return {
        **ranked,
        "actor_profile_summary_safe": _safe_profile_summary(actor_profile_summary, preferred_hooks),
        "counterpart_profile_summary_safe": _safe_profile_summary(
            counterpart_profile_summary,
            list(ranked.get("shared_hooks") or preferred_hooks),
        ),
    }


def _compact_thread_context_for_guidance(
    thread_context: str,
    *,
    max_chars: int,
    max_lines: int = 8,
) -> str:
    lines = [line.rstrip() for line in str(thread_context or "").splitlines() if line.strip()]
    if not lines:
        return "（暂无）"
    text = "\n".join(lines[-max_lines:])
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:].lstrip()
    return f"…\n{tail}" if tail else "（暂无）"


def _looks_like_direct_send_message(text: str) -> bool:
    item = str(text or "").strip()
    if not item:
        return False
    if _DIRECT_SEND_PREFIX_RE.search(item):
        return True
    if any(marker in item for marker in _COACHING_MARKERS):
        return False
    if any(token in item for token in ("我", "你", "哈哈", "吗", "呢", "呀", "吧")) and item[-1] in "。！？?!~":
        return True
    return False


def _sanitize_advice(
    value: Any,
    *,
    interaction_mode: str,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
) -> list[str]:
    out: list[str] = []
    for item in _to_clean_list(value):
        if _looks_like_direct_send_message(item):
            continue
        out.append(item)
    if out:
        return out
    return _default_advice(
        interaction_mode,
        risk_axis=risk_axis,
        hold_subtype=hold_subtype,
    )


def normalize_assistant_guidance(data: dict[str, Any]) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    guidance_source = str(payload.get("guidance_source") or "").strip() or "model"
    mutual_intent_assessment = _normalize_contract_mutual_intent_assessment(
        payload.get("mutual_intent_assessment")
    )
    interaction_mode = _normalize_contract_interaction_mode(
        payload.get("interaction_mode"),
        mutual_intent_assessment=mutual_intent_assessment,
    )
    risk_axis = _normalize_risk_axis(payload.get("risk_axis"))
    hold_subtype = _normalize_hold_subtype(payload.get("hold_subtype"))
    advice = _sanitize_advice(
        _merge_clean_lists(payload.get("advice"), payload.get("reply_suggestions")),
        interaction_mode=interaction_mode,
        risk_axis=risk_axis,
        hold_subtype=hold_subtype,
    )
    return {
        "schema_version": GUIDANCE_SCHEMA_VERSION,
        "guidance_source": guidance_source,
        "mutual_intent_assessment": mutual_intent_assessment,
        "interaction_mode": interaction_mode,
        "risk_axis": risk_axis,
        "hold_subtype": hold_subtype,
        "current_problem": _to_clean_list(payload.get("current_problem"))
        or _default_current_problem(
            mutual_intent_assessment,
            interaction_mode,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
        ),
        "problem_tags": _to_clean_list(payload.get("problem_tags")) or list(_DEFAULT_PROBLEM_TAGS),
        "why_not_to_push": _to_clean_list(payload.get("why_not_to_push"))
        or _default_why_not_to_push(mutual_intent_assessment, interaction_mode),
        "low_pressure_options": _to_clean_list(payload.get("low_pressure_options"))
        or _default_low_pressure_options(interaction_mode),
        "advice": advice,
        "avoid": _to_clean_list(payload.get("avoid"))
        or _default_avoid(
            mutual_intent_assessment,
            interaction_mode,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
        ),
        "topic_directions": _to_clean_list(payload.get("topic_directions")),
        "easy_question_types": _to_clean_list(payload.get("easy_question_types"))
        or _default_easy_question_types(interaction_mode),
        "rescue_flow": _to_clean_list(payload.get("rescue_flow"))
        or _default_rescue_flow_for_mode(
            interaction_mode,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
        ),
        "graceful_exit_plan": _to_clean_list(payload.get("graceful_exit_plan"))
        or _default_graceful_exit_plan(mutual_intent_assessment, interaction_mode),
        "strategy_tags": _to_clean_list(payload.get("strategy_tags"))
        or _default_strategy_tags(interaction_mode),
        "reply_suggestions": list(advice),
        "profile_hooks_used": _to_clean_list(payload.get("profile_hooks_used")),
    }


def _hold_guidance_has_active_reengagement(guidance: dict[str, Any]) -> bool:
    if _to_clean_list(guidance.get("low_pressure_options")):
        return True
    if _to_clean_list(guidance.get("topic_directions")):
        return True
    if _to_clean_list(guidance.get("easy_question_types")):
        return True
    strategy_tags = set(_to_clean_list(guidance.get("strategy_tags")))
    return bool(strategy_tags & _HOLD_CONFLICT_STRATEGY_TAGS)


def align_guidance_to_route_decision(
    guidance: dict[str, Any] | None,
    *,
    profile_hooks: list[str] | None = None,
    preferred_mutual_intent_assessment: str | None = None,
    preferred_interaction_mode: str | None = None,
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
    route_reason: str = "",
) -> dict[str, Any]:
    preferred_mutual_intent = _normalize_contract_mutual_intent_assessment(
        preferred_mutual_intent_assessment
    )
    preferred_interaction_mode_normalized = _normalize_contract_interaction_mode(
        preferred_interaction_mode,
        mutual_intent_assessment=preferred_mutual_intent,
    )
    normalized = normalize_assistant_guidance(guidance or {})
    if preferred_interaction_mode_normalized != "hold":
        return normalized

    fallback = build_placeholder_assistant_guidance(
        profile_hooks=profile_hooks,
        mutual_intent_assessment=preferred_mutual_intent,
        interaction_mode=preferred_interaction_mode_normalized,
        route_reason=route_reason,
        risk_axis=risk_axis,
        hold_subtype=hold_subtype,
        guidance_source="fallback_alignment",
    )
    if normalized.get("interaction_mode") != "hold":
        return fallback
    if (
        preferred_mutual_intent in {"boundary_risk", "interest_low"}
        and normalized.get("mutual_intent_assessment") != preferred_mutual_intent
    ):
        return fallback
    if _hold_guidance_has_active_reengagement(normalized):
        return fallback

    sanitized = dict(normalized)
    sanitized["low_pressure_options"] = []
    sanitized["topic_directions"] = []
    sanitized["easy_question_types"] = []
    sanitized["profile_hooks_used"] = []
    sanitized["strategy_tags"] = list(_default_strategy_tags("hold"))
    sanitized["risk_axis"] = _normalize_risk_axis(risk_axis)
    sanitized["hold_subtype"] = _normalize_hold_subtype(hold_subtype)
    return normalize_assistant_guidance(sanitized)


def build_placeholder_assistant_guidance(
    *,
    profile_hooks: list[str] | None = None,
    mutual_intent_assessment: str | None = None,
    interaction_mode: str | None = None,
    route_reason: str = "",
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
    guidance_source: str = "fallback",
) -> dict[str, Any]:
    raw_hooks = [_clean_profile_hook(hook) for hook in list(profile_hooks or [])]
    hooks = [hook for hook in raw_hooks if hook and not _is_generic_profile_hook(hook)]
    normalized_mutual_intent = _normalize_contract_mutual_intent_assessment(
        mutual_intent_assessment
    )
    normalized_interaction_mode = _normalize_contract_interaction_mode(
        interaction_mode,
        mutual_intent_assessment=normalized_mutual_intent,
    )
    topic_directions = _default_topic_directions(
        hooks,
        interaction_mode=normalized_interaction_mode,
    )
    normalized_risk_axis = _normalize_risk_axis(risk_axis)
    normalized_hold_subtype = _normalize_hold_subtype(hold_subtype)
    advice = _default_advice(
        normalized_interaction_mode,
        risk_axis=normalized_risk_axis,
        hold_subtype=normalized_hold_subtype,
    )
    guidance = {
        "guidance_source": guidance_source,
        "mutual_intent_assessment": normalized_mutual_intent,
        "interaction_mode": normalized_interaction_mode,
        "current_problem": _default_current_problem(
            normalized_mutual_intent,
            normalized_interaction_mode,
            risk_axis=normalized_risk_axis,
            hold_subtype=normalized_hold_subtype,
            route_reason=route_reason,
        ),
        "risk_axis": normalized_risk_axis,
        "hold_subtype": normalized_hold_subtype,
        "problem_tags": ["fallback"],
        "why_not_to_push": _default_why_not_to_push(
            normalized_mutual_intent,
            normalized_interaction_mode,
        ),
        "low_pressure_options": _default_low_pressure_options(normalized_interaction_mode),
        "avoid": _default_avoid(
            normalized_mutual_intent,
            normalized_interaction_mode,
            risk_axis=normalized_risk_axis,
            hold_subtype=normalized_hold_subtype,
        ),
        "topic_directions": topic_directions,
        "easy_question_types": _default_easy_question_types(normalized_interaction_mode),
        "rescue_flow": _default_rescue_flow_for_mode(
            normalized_interaction_mode,
            risk_axis=normalized_risk_axis,
            hold_subtype=normalized_hold_subtype,
        ),
        "graceful_exit_plan": _default_graceful_exit_plan(
            normalized_mutual_intent,
            normalized_interaction_mode,
        ),
        "strategy_tags": _default_strategy_tags(normalized_interaction_mode),
        "advice": advice,
        "reply_suggestions": advice,
        "profile_hooks_used": hooks[:3],
    }
    return _finalize_guidance_with_profile_context(guidance, selected_hooks=hooks)


def build_fast_hold_guidance(
    *,
    profile_hooks: list[str] | None = None,
    route_reason: str = "",
    risk_axis: str | None = None,
    hold_subtype: str | None = None,
    hint_trigger_type: str = "",
) -> dict[str, Any]:
    normalized_risk_axis = _normalize_risk_axis(risk_axis)
    normalized_hold_subtype = _normalize_hold_subtype(hold_subtype) or "boundary_risk"
    trigger = str(hint_trigger_type or "").strip().lower()
    if trigger == "hold_stoploss":
        current_problem = (
            route_reason.strip()
            or "这轮已经沿同一条危险线继续加码了，再解释或再追只会更僵。"
        )
        advice = [
            _axis_guardrail(normalized_risk_axis),
            "别再证明自己，也别试图把话题拉回正常聊天。",
        ]
        avoid = [
            "不要继续解释动机。",
            "不要再抛新的泛聊天问题硬续上。",
        ]
    else:
        current_problem = route_reason.strip() or _axis_problem_line(normalized_risk_axis)
        advice = [
            _axis_guardrail(normalized_risk_axis),
            "这轮先收住，别再往前顶。",
        ]
        avoid = [
            _axis_guardrail(normalized_risk_axis),
            "别继续解释拉扯。",
        ]
    guidance = build_placeholder_assistant_guidance(
        profile_hooks=profile_hooks,
        mutual_intent_assessment="boundary_risk",
        interaction_mode="hold",
        route_reason=current_problem,
        risk_axis=normalized_risk_axis,
        hold_subtype=normalized_hold_subtype,
        guidance_source="fast_hold_policy",
    )
    guidance["current_problem"] = [current_problem]
    guidance["advice"] = list(advice)
    guidance["reply_suggestions"] = list(advice)
    guidance["avoid"] = list(avoid)
    guidance["low_pressure_options"] = []
    guidance["topic_directions"] = []
    guidance["easy_question_types"] = []
    guidance["strategy_tags"] = ["graceful_exit", "deescalate", "set_boundary"]
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
    for idx, item in enumerate(g["advice"], start=1):
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
        "mutual_intent_assessment": {"意愿判断："},
        "interaction_mode": {"这轮处理方式："},
        "current_problem": {"当前问题："},
        "why_not_to_push": {"现在别硬推的原因："},
        "low_pressure_options": {"如果只适合低压试探："},
        "avoid": {"先别继续这样聊："},
        "topic_directions": {"建议优先换到这些话题类型："},
        "easy_question_types": {"更容易回答的问题类型："},
        "rescue_flow": {"建议按这个顺序来："},
        "graceful_exit_plan": {"如果还是接不动："},
        "advice": {"回复建议：", "行动建议："},
        "profile_hooks_used": {"已参考画像钩子："},
    }
    current: str | None = None
    data: dict[str, list[str]] = {k: [] for k in sections}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        matched = False
        for key, headers in sections.items():
            if stripped in headers:
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
        "advice": data["advice"],
        "reply_suggestions": data["advice"],
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
    preferred_mutual_intent_assessment: str | None = None,
    preferred_interaction_mode: str | None = None,
    route_reason: str = "",
    risk_axis: str = "",
    hold_subtype: str = "",
    engagement_level: str = "",
    warmth_level: str = "",
    irritation_level: str = "",
    state_trend: str = "",
    hint_trigger_type: str = "",
) -> dict[str, Any] | None:
    profile_ctx = _prepare_profile_context_for_guidance(
        actor_profile_summary=actor_profile_summary,
        counterpart_profile_summary=counterpart_profile_summary,
        profile_hooks=profile_hooks,
    )
    selected_hooks = list(profile_ctx.get("selected_hooks") or [])
    actor_summary_safe = str(profile_ctx.get("actor_profile_summary_safe") or "")
    counterpart_summary_safe = str(profile_ctx.get("counterpart_profile_summary_safe") or "")
    compact_context = _compact_thread_context_for_guidance(
        thread_context,
        max_chars=max(180, min(_env_int("HER_CHAT_ASSISTANT_CONTEXT_CHARS", 420), 1000)),
    )
    fallback = build_placeholder_assistant_guidance(
        profile_hooks=selected_hooks,
        mutual_intent_assessment=preferred_mutual_intent_assessment,
        interaction_mode=preferred_interaction_mode,
        route_reason=route_reason,
        risk_axis=risk_axis,
        hold_subtype=hold_subtype,
        guidance_source="fallback_no_key",
    )
    if _should_use_fast_hold_path(
        preferred_mutual_intent_assessment=preferred_mutual_intent_assessment,
        preferred_interaction_mode=preferred_interaction_mode,
        hold_subtype=hold_subtype,
    ):
        return build_fast_hold_guidance(
            profile_hooks=selected_hooks,
            route_reason=route_reason,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
            hint_trigger_type=hint_trigger_type,
        )
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return fallback
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
        from openai import OpenAI  # noqa: F401
    except ImportError:
        return fallback
    assistant_timeout_sec = max(10.0, min(_env_float("HER_CHAT_ASSISTANT_TIMEOUT_SEC", 60.0), 180.0))
    client = _openai_client_cached(
        key,
        base,
        round(assistant_timeout_sec, 2),
    )
    system = (
        "你是相亲聊天教练，只给策略，不代写可直接发送给对方的整句。"
        "先判 mutual_intent_assessment 和 interaction_mode。"
        "映射：communication_problem->repair；interest_unclear->probe_lightly；"
        "interest_low/boundary_risk->hold；normal->none。"
        "局面偏冷或碰到边界/压力点时，优先给收住或止损建议。"
        "只输出一个极短 JSON 对象，不要 Markdown，不要代码块。"
    )
    prompt_parts = [
        f"对话:\n{compact_context}",
        f"用户问: {user_query}",
    ]
    if route_reason or risk_axis or hold_subtype or engagement_level or warmth_level or irritation_level or state_trend:
        prompt_parts.append(
            "快照: "
            f"原因={route_reason or '无'} | "
            f"风险={risk_axis or '无'} | "
            f"hold={hold_subtype or '无'} | "
            f"投入={engagement_level or 'unknown'} | "
            f"语气={warmth_level or 'unknown'} | "
            f"压力={irritation_level or 'unknown'} | "
            f"走势={state_trend or 'stable'}"
        )
    if actor_summary_safe:
        prompt_parts.append(f"我方画像:\n{actor_summary_safe}")
    if counterpart_summary_safe:
        prompt_parts.append(f"对方画像:\n{counterpart_summary_safe}")
    if selected_hooks:
        prompt_parts.append(f"优先钩子: {', '.join(selected_hooks[:3])}")
    prompt_parts.extend(
        [
            "输出极短 JSON，只保留必要字段，不要空数组：",
            "{",
            f'  "mutual_intent_assessment": "<{_MUTUAL_INTENT_CHOICES}>",',
            f'  "interaction_mode": "<{_INTERACTION_MODE_CHOICES}>",',
            '  "current_problem": ["<1 条最关键问题>"],',
            '  "avoid": ["<1-2 条，可省略>"],',
            '  "advice": ["<1-2 条方向性建议，不要代写整句>"],',
            '  "risk_axis": "<appearance|income_condition|privacy_ex|meetup_push|pressure_compare|other，可省略>",',
            '  "hold_subtype": "<interest_low|boundary_risk，可省略>",',
            '  "topic_directions": ["<0-2 个，可省略>"],',
            '  "profile_hooks_used": ["<0-2 个，必须来自优先钩子，可省略>"]',
            "}",
            "不要编造画像里没有的事实；没必要的字段直接省略。",
        ]
    )
    user_block = "\n\n".join(prompt_parts)
    try:
        max_tokens = _env_int("HER_CHAT_ASSISTANT_MAX_TOKENS", 120)
        temperature = _env_float("HER_CHAT_ASSISTANT_TEMPERATURE", 0.1)
        cache_key = _guidance_response_cache_key(
            model=model,
            base=base,
            temperature=temperature,
            system=system,
            user_block=user_block,
        )
        cached_guidance = _guidance_response_cache_get(cache_key)
        if cached_guidance is not None:
            return cached_guidance
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            max_tokens=max(80, min(max_tokens, 240)),
            temperature=max(0.0, min(temperature, 1.0)),
        )
        choice = resp.choices[0].message.content
        out = (choice or "").strip()
        if not out:
            return fallback
        finalized = _finalize_guidance_with_profile_context(
            _strip_json_object(out),
            selected_hooks=selected_hooks,
        )
        finalized["guidance_source"] = "model"
        aligned = align_guidance_to_route_decision(
            finalized,
            profile_hooks=selected_hooks,
            preferred_mutual_intent_assessment=preferred_mutual_intent_assessment,
            preferred_interaction_mode=preferred_interaction_mode,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
            route_reason=route_reason,
        )
        _guidance_response_cache_put(cache_key, aligned)
        return aligned
    except Exception as e:
        if _is_timeout_exception(e):
            return {
                "guidance_source": "timeout_hidden",
                "mutual_intent_assessment": _normalize_contract_mutual_intent_assessment(
                    preferred_mutual_intent_assessment
                ),
                "interaction_mode": _normalize_contract_interaction_mode(
                    preferred_interaction_mode,
                    mutual_intent_assessment=_normalize_contract_mutual_intent_assessment(
                        preferred_mutual_intent_assessment
                    ),
                ),
                "risk_axis": _normalize_risk_axis(risk_axis),
                "hold_subtype": _normalize_hold_subtype(hold_subtype),
            }
        source = "fallback_exception"
        return build_placeholder_assistant_guidance(
            profile_hooks=selected_hooks,
            mutual_intent_assessment=preferred_mutual_intent_assessment,
            interaction_mode=preferred_interaction_mode,
            route_reason=route_reason,
            risk_axis=risk_axis,
            hold_subtype=hold_subtype,
            guidance_source=source,
        )


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
    if str((guidance or {}).get("guidance_source") or "").strip() == "timeout_hidden":
        return None
    return render_assistant_guidance(guidance)


def _clear_assistant_llm_caches_for_tests() -> None:
    with _GUIDANCE_RESPONSE_CACHE_LOCK:
        _GUIDANCE_RESPONSE_CACHE.clear()
    _openai_client_cached.cache_clear()


__all__ = [
    "align_guidance_to_route_decision",
    "build_dyadic_context_for_assistant",
    "build_fast_hold_guidance",
    "build_placeholder_assistant_guidance",
    "generate_assistant_guidance",
    "generate_assistant_reply",
    "normalize_assistant_guidance",
    "parse_assistant_guidance",
    "render_assistant_guidance",
]
