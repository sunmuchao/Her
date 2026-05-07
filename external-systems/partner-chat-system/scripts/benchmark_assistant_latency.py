#!/usr/bin/env python3
"""Benchmark assistant guidance latency for current vs legacy-like prompt shapes."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


def _load_repo_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "match_domain").is_dir() and (p / "pyproject.toml").is_file():
            env = p / ".env"
            if env.is_file():
                load_dotenv(env, override=True)
            return


_load_repo_dotenv()

PARTNER_CHAT_ROOT = Path(__file__).resolve().parents[1]
if str(PARTNER_CHAT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARTNER_CHAT_ROOT))

from chat_system.assistant_llm import (  # noqa: E402
    _clear_assistant_llm_caches_for_tests,
    _compact_thread_context_for_guidance,
    _env_float,
    _env_int,
    _finalize_guidance_with_profile_context,
    _openai_client_cached,
    _prepare_profile_context_for_guidance,
    _strip_json_object,
    align_guidance_to_route_decision,
    generate_assistant_guidance,
)


SAMPLE_ROUTE = {
    "preferred_mutual_intent_assessment": "communication_problem",
    "preferred_interaction_mode": "repair",
    "route_reason": "对方上一句太短，旧话题快聊干了。",
    "risk_axis": "",
    "hold_subtype": "",
    "engagement_level": "medium",
    "warmth_level": "cool",
    "irritation_level": "none",
    "state_trend": "cooling",
}

SAMPLE_NONE_ROUTE = {
    "preferred_mutual_intent_assessment": "normal",
    "preferred_interaction_mode": "none",
    "route_reason": "上一句本身就是正常可接的问题，先别打断自然往下聊。",
    "risk_axis": "",
    "hold_subtype": "",
    "engagement_level": "high",
    "warmth_level": "warm",
    "irritation_level": "none",
    "state_trend": "stable",
}

SAMPLE_INPUT = {
    "user_query": "这轮怎么接比较自然？",
    "thread_context": (
        "user-a: 你好，平时周末会做什么？\n"
        "user-b: 看情况。\n"
        "user-a: 哈哈那你最近忙吗？\n"
        "user-b: 还好。\n"
        "user-a: 我一般会出去走走或者找家店坐坐。\n"
        "user-b: 嗯。"
    ),
    "actor_profile_summary": (
        "name：小雨\n"
        "age：29\n"
        "settlement_city：无锡\n"
        "job：互联网运营\n"
        "lifestyle：咖啡、citywalk、运动\n"
        "hobbies：桌游、羽毛球、电影\n"
        "notes：周末会找家店坐坐慢慢聊。"
    ),
    "counterpart_profile_summary": (
        "name：阿杰\n"
        "age：30\n"
        "settlement_city：无锡\n"
        "job：工程师\n"
        "lifestyle：咖啡、早起\n"
        "hobbies：桌游、旅行\n"
        "notes：偏慢热。"
    ),
    "profile_hooks": ["电影", "旅行", "无锡", "咖啡", "桌游", "羽毛球", "运动"],
}


def _current_prompt_snapshot() -> dict[str, str]:
    profile_ctx = _prepare_profile_context_for_guidance(
        actor_profile_summary=SAMPLE_INPUT["actor_profile_summary"],
        counterpart_profile_summary=SAMPLE_INPUT["counterpart_profile_summary"],
        profile_hooks=SAMPLE_INPUT["profile_hooks"],
    )
    selected_hooks = list(profile_ctx.get("selected_hooks") or [])
    compact_context = _compact_thread_context_for_guidance(
        SAMPLE_INPUT["thread_context"],
        max_chars=max(180, min(_env_int("HER_CHAT_ASSISTANT_CONTEXT_CHARS", 420), 1000)),
    )
    system = (
        "你是相亲聊天回温教练，只处理双方还想继续聊、但这轮接话卡住的场景。"
        "只给策略，不代写可直接发送给对方的整句。"
        "只允许输出两种判断：communication_problem->repair，normal->none。"
        "如果这轮不需要回温介入，就明确给 normal/none。"
        "只输出一个极短 JSON 对象，不要 Markdown，不要代码块。"
    )
    prompt_parts = [
        f"对话:\n{compact_context}",
        f"用户问: {SAMPLE_INPUT['user_query']}",
        (
            "快照: "
            f"原因={SAMPLE_ROUTE['route_reason']} | "
            f"风险={SAMPLE_ROUTE['risk_axis'] or '无'} | "
            f"hold={SAMPLE_ROUTE['hold_subtype'] or '无'} | "
            f"投入={SAMPLE_ROUTE['engagement_level']} | "
            f"语气={SAMPLE_ROUTE['warmth_level']} | "
            f"压力={SAMPLE_ROUTE['irritation_level']} | "
            f"走势={SAMPLE_ROUTE['state_trend']}"
        ),
    ]
    actor_summary_safe = str(profile_ctx.get("actor_profile_summary_safe") or "")
    counterpart_summary_safe = str(profile_ctx.get("counterpart_profile_summary_safe") or "")
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
            '  "mutual_intent_assessment": "<communication_problem|normal>",',
            '  "interaction_mode": "<repair|none>",',
            '  "current_problem": ["<1 条最关键问题>"],',
            '  "avoid": ["<1-2 条，可省略>"],',
            '  "advice": ["<1-2 条方向性建议，不要代写整句>"],',
            '  "topic_directions": ["<0-2 个，可省略>"],',
            '  "profile_hooks_used": ["<0-2 个，必须来自优先钩子，可省略>"]',
            "}",
            "不要编造画像里没有的事实；没必要的字段直接省略。",
        ]
    )
    return {"system": system, "user": "\n\n".join(prompt_parts)}


def _legacy_prompt_snapshot() -> dict[str, str]:
    profile_ctx = _prepare_profile_context_for_guidance(
        actor_profile_summary=SAMPLE_INPUT["actor_profile_summary"],
        counterpart_profile_summary=SAMPLE_INPUT["counterpart_profile_summary"],
        profile_hooks=SAMPLE_INPUT["profile_hooks"],
    )
    selected_hooks = list(profile_ctx.get("selected_hooks") or [])
    actor_summary_safe = str(profile_ctx.get("actor_profile_summary_safe") or "")
    counterpart_summary_safe = str(profile_ctx.get("counterpart_profile_summary_safe") or "")
    compact_context = _compact_thread_context_for_guidance(
        SAMPLE_INPUT["thread_context"],
        max_chars=700,
        max_lines=10,
    )
    system = (
        "你是相亲聊天教练，不是代聊者。"
        "只分析问题和下一步策略，不写可以直接发送给对方的整句消息。"
        "先判断 mutual_intent_assessment：communication_problem 或 normal。"
        "模式映射：communication_problem->repair；normal->none。"
        "优先给：当前问题、别继续做什么、可换的话题、容易回答的问题、分步骤建议。"
        "如果这轮没有明显冷场卡点，就明确判断为 normal/none。"
        "若给了画像钩子，优先用双方交集或当前说话人的真实生活，避免电影、旅行、运动这类泛泛万能话题。"
        "只输出一个 JSON 对象，不要 Markdown、不要代码块。"
    )
    prompt_parts = [
        f"最近对话（双方可见）：\n{compact_context}",
        f"用户问题：{SAMPLE_INPUT['user_query']}",
        (
            "轻判断快照："
            f"原因={SAMPLE_ROUTE['route_reason']}；"
            f"投入度={SAMPLE_ROUTE['engagement_level']}；"
            f"语气={SAMPLE_ROUTE['warmth_level']}；"
            f"压力={SAMPLE_ROUTE['irritation_level']}；"
            f"走势={SAMPLE_ROUTE['state_trend']}。"
        ),
    ]
    if actor_summary_safe:
        prompt_parts.append(f"当前说话人画像摘要（已裁剪）：\n{actor_summary_safe}")
    if counterpart_summary_safe:
        prompt_parts.append(f"对方画像摘要（已裁剪）：\n{counterpart_summary_safe}")
    prompt_parts.extend(
        [
            f"优先画像钩子-双方交集：{', '.join(profile_ctx.get('shared_hooks') or []) or '（暂无）'}",
            f"优先画像钩子-当前说话人真实生活：{', '.join(profile_ctx.get('actor_hooks') or []) or '（暂无）'}",
            f"最终优先可用画像钩子：{', '.join(selected_hooks) or '（暂无）'}",
            "请输出 JSON，尽量短，只保留有内容的必要字段，不要输出空数组：",
            "{",
            '  "mutual_intent_assessment": "<communication_problem|normal>",',
            '  "interaction_mode": "<repair|none>",',
            '  "current_problem": ["<1 条最关键问题>"],',
            '  "avoid": ["<1-2 条>"],',
            '  "advice": ["<1-2 条方向性建议，不要代写整句>"],',
            '  "topic_directions": ["<0-2 个，可省略>"],',
            '  "rescue_flow": ["<0-2 条步骤，可省略>"],',
            '  "profile_hooks_used": ["<0-2 个，必须来自给定画像或钩子，可省略>"]',
            "}",
            "不要编造画像里没有的事实；不要代码块；没必要的字段直接省略。",
        ]
    )
    return {"system": system, "user": "\n\n".join(prompt_parts)}


def _call_legacy_like_guidance() -> dict[str, Any]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required")
    model = (
        os.environ.get("HER_CHAT_ASSISTANT_FAST_MODEL")
        or os.environ.get("HER_CHAT_ASSISTANT_RESCUE_MODEL")
        or os.environ.get("HER_CHAT_ASSISTANT_MODEL")
        or "gpt-4o-mini"
    ).strip()
    base = (os.environ.get("HER_CHAT_ASSISTANT_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip()
    timeout_sec = max(10.0, min(_env_float("HER_CHAT_ASSISTANT_TIMEOUT_SEC", 60.0), 180.0))
    prompt = _legacy_prompt_snapshot()
    client = _openai_client_cached(key, base, round(timeout_sec, 2))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        max_tokens=160,
        temperature=max(0.0, min(_env_float("HER_CHAT_ASSISTANT_TEMPERATURE", 0.1), 1.0)),
    )
    text = (response.choices[0].message.content or "").strip()
    profile_ctx = _prepare_profile_context_for_guidance(
        actor_profile_summary=SAMPLE_INPUT["actor_profile_summary"],
        counterpart_profile_summary=SAMPLE_INPUT["counterpart_profile_summary"],
        profile_hooks=SAMPLE_INPUT["profile_hooks"],
    )
    selected_hooks = list(profile_ctx.get("selected_hooks") or [])
    finalized = _finalize_guidance_with_profile_context(
        _strip_json_object(text),
        selected_hooks=selected_hooks,
    )
    finalized["guidance_source"] = "legacy_model"
    return align_guidance_to_route_decision(
        finalized,
        profile_hooks=selected_hooks,
        preferred_mutual_intent_assessment=SAMPLE_ROUTE["preferred_mutual_intent_assessment"],
        preferred_interaction_mode=SAMPLE_ROUTE["preferred_interaction_mode"],
        risk_axis=SAMPLE_ROUTE["risk_axis"],
        hold_subtype=SAMPLE_ROUTE["hold_subtype"],
        route_reason=SAMPLE_ROUTE["route_reason"],
        online_scope_only=True,
    )


def _measure(label: str, fn: Callable[[], Any], *, repeats: int) -> dict[str, Any]:
    times_ms: list[float] = []
    result_preview = None
    failures: list[dict[str, Any]] = []
    for idx in range(repeats):
        started = perf_counter()
        try:
            result = fn()
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            times_ms.append(elapsed_ms)
            if idx == 0:
                result_preview = result
        except Exception as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            failures.append(
                {
                    "attempt": idx + 1,
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return {
        "label": label,
        "repeats": repeats,
        "times_ms": times_ms,
        "success_count": len(times_ms),
        "failure_count": len(failures),
        "avg_ms": round(statistics.mean(times_ms), 2) if times_ms else None,
        "min_ms": round(min(times_ms), 2) if times_ms else None,
        "max_ms": round(max(times_ms), 2) if times_ms else None,
        "result_preview": result_preview,
        "failures": failures,
    }


def _guidance_result_preview(guidance: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(guidance or {})
    return {
        "guidance_source": payload.get("guidance_source"),
        "mutual_intent_assessment": payload.get("mutual_intent_assessment"),
        "interaction_mode": payload.get("interaction_mode"),
        "current_problem": list(payload.get("current_problem") or [])[:1],
        "advice": list(payload.get("advice") or [])[:2],
    }


def _run_benchmark(repeats: int) -> dict[str, Any]:
    _clear_assistant_llm_caches_for_tests()
    current_prompt = _current_prompt_snapshot()
    legacy_prompt = _legacy_prompt_snapshot()

    scenarios: list[dict[str, Any]] = []

    scenarios.append(
        _measure(
            "repair_current_uncached",
            lambda: _guidance_result_preview(
                generate_assistant_guidance(
                    **SAMPLE_INPUT,
                    **SAMPLE_ROUTE,
                    online_scope_only=True,
                )
            ),
            repeats=max(1, repeats),
        )
    )

    _clear_assistant_llm_caches_for_tests()
    warm_current = _guidance_result_preview(
        generate_assistant_guidance(**SAMPLE_INPUT, **SAMPLE_ROUTE, online_scope_only=True)
    )
    scenarios.append(
        _measure(
            "repair_current_cache_hit",
            lambda: _guidance_result_preview(
                generate_assistant_guidance(**SAMPLE_INPUT, **SAMPLE_ROUTE, online_scope_only=True)
            ),
            repeats=max(1, repeats),
        )
    )

    _clear_assistant_llm_caches_for_tests()
    scenarios.append(
        _measure(
            "none_online_short_circuit",
            lambda: _guidance_result_preview(
                generate_assistant_guidance(
                    **SAMPLE_INPUT,
                    **SAMPLE_NONE_ROUTE,
                    online_scope_only=True,
                )
            ),
            repeats=max(1, repeats),
        )
    )

    _clear_assistant_llm_caches_for_tests()
    scenarios.append(
        _measure(
            "repair_legacy_like_prompt",
            lambda: _guidance_result_preview(_call_legacy_like_guidance()),
            repeats=max(1, repeats),
        )
    )

    return {
        "model": (
            os.environ.get("HER_CHAT_ASSISTANT_FAST_MODEL")
            or os.environ.get("HER_CHAT_ASSISTANT_RESCUE_MODEL")
            or os.environ.get("HER_CHAT_ASSISTANT_MODEL")
            or "gpt-4o-mini"
        ),
        "prompt_comparison": {
            "current_user_prompt_chars": len(current_prompt["user"]),
            "legacy_user_prompt_chars": len(legacy_prompt["user"]),
            "current_system_prompt_chars": len(current_prompt["system"]),
            "legacy_system_prompt_chars": len(legacy_prompt["system"]),
        },
        "warm_current_preview": warm_current,
        "scenarios": scenarios,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1, help="Calls per scenario. Default 1 to control API cost.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = _run_benchmark(max(1, int(args.repeats)))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
