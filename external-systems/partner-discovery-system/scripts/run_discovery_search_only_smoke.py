#!/usr/bin/env python3
"""Compare discovery agent behavior: structured JSON output vs search-tool-only.

Hypothesis (situation B): forcing DiscoveryDecision JSON makes the model skip
search_partner_candidates. This script runs the same user scenario twice:

  1. production-like agent (strict JSON + tools) — current discovery runtime shape
  2. search-only agent (no output_type, must call search tool)

Exit 0 if search-only invoked the tool; prints a side-by-side summary.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from dotenv import load_dotenv

SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

for root in (SYSTEM_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from discovery_system.agent_runtime import (  # noqa: E402
    _configure_agents_sdk_provider,
    _resolve_discovery_api_key,
    _resolve_discovery_model,
    _resolve_discovery_wire_api,
)
from partner_search import search_profiles  # noqa: E402


DEFAULT_PROMPT = """\
用户（男，31岁，上海，结婚目的）刚刚在发现页点了选项「26-28岁」。
当前已确认条件：只看上海，女生，26-28岁，认真找结婚对象。

请根据这些条件搜索候选人。\
"""

# 仅含搜索意图、不附带城市/年龄等条件（测模型会不会仍调工具）
MINIMAL_SEARCH_PROMPTS: dict[str, str] = {
    "请搜索": "请搜索",
    "开始搜索": "开始搜索",
    "帮我搜索": "帮我搜索一下",
    "找对象请搜索": "帮我找对象，请搜索",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default=None,
        help="User scenario text passed to agents (overrides --prompt-style)",
    )
    parser.add_argument(
        "--prompt-style",
        choices=("full", "minimal"),
        default="full",
        help="full=DEFAULT_PROMPT with criteria; minimal=run MINIMAL_SEARCH_PROMPTS suite",
    )
    parser.add_argument("--self-id", type=int, default=9005, help="Requester profile id for search")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--skip-json-agent",
        action="store_true",
        help="Only run the search-only agent (faster)",
    )
    parser.add_argument(
        "--minimal-only",
        action="store_true",
        help="Alias for --prompt-style minimal --skip-json-agent",
    )
    return parser.parse_args()


def _profile_source() -> str:
    import os

    from her_env import env_first

    return env_first(
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PARTNER_PROFILE_SOURCE",
        default="",
    )


def _make_search_tool(*, self_id: int, limit: int, trace: dict[str, Any]):
    from agents import function_tool

    source = _profile_source()
    if not source:
        raise RuntimeError("HER_DISCOVERY_PROFILE_SOURCE (or PARTNER_SEARCH_MYSQL_SOURCE) is not set")

    @function_tool
    def search_partner_candidates(criteria_json: str, search_limit: int = 5) -> dict[str, Any]:
        trace["invoked"] = True
        criteria = json.loads(str(criteria_json or "{}"))
        if not isinstance(criteria, dict):
            raise ValueError("criteria_json must be a JSON object")
        normalized_limit = max(1, min(int(search_limit or limit), 10))
        try:
            response = search_profiles(
                source=source,
                criteria=criteria,
                self_id=self_id,
                limit=normalized_limit,
                photo_preview_count=3,
            )
        except Exception as exc:  # noqa: BLE001
            trace["tool_error"] = f"{type(exc).__name__}: {exc}"
            raise
        trace["called"] = True
        trace["criteria"] = criteria
        trace["has_match"] = bool(response.get("has_match"))
        trace["result_count"] = int(response.get("result_count") or 0)
        trace["error_code"] = str(response.get("error_code") or "").strip() or None
        return response

    return search_partner_candidates


def _run_search_only_agent(
    *,
    prompt: str,
    self_id: int,
    limit: int,
    force_tool: bool = False,
) -> dict[str, Any]:
    from agents import Agent, Runner
    from agents.model_settings import ModelSettings

    trace: dict[str, Any] = {"called": False}
    tool = _make_search_tool(self_id=self_id, limit=limit, trace=trace)

    mode = "search_only_forced_tool" if force_tool else "search_only"
    agent_kwargs: dict[str, Any] = {
        "name": "discovery_search_only_smoke",
        "instructions": (
            "你是发现页红娘。本轮不要做结构化 JSON 输出。\n"
            "你的唯一任务：根据用户已确认的条件，调用 search_partner_candidates 工具完成搜索。\n"
            "调用工具后，用一两句中文告诉用户搜索是否完成、找到几位；数字必须与工具返回的 result_count 一致。\n"
            "禁止在未调用工具的情况下声称已经找到候选人。\n"
            "如果条件已经明确，禁止只口头说「我去搜」而不调用工具。"
        ),
        "model": _resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
        "tools": [tool],
    }
    if force_tool:
        agent_kwargs["model_settings"] = ModelSettings(tool_choice="required")

    agent = Agent(**agent_kwargs)
    result = Runner.run_sync(agent, input=prompt)
    final = getattr(result, "final_output", result)
    new_items = getattr(result, "new_items", None)
    return {
        "mode": mode,
        "search_tool_invoked": bool(trace.get("invoked")),
        "search_tool_called": bool(trace.get("called")),
        "tool_error": trace.get("tool_error"),
        "criteria": trace.get("criteria"),
        "has_match": trace.get("has_match"),
        "result_count": trace.get("result_count"),
        "error_code": trace.get("error_code"),
        "final_output_preview": str(final)[:500],
        "new_items_count": len(new_items) if new_items is not None else None,
    }


def _run_json_agent(*, prompt: str, self_id: int, limit: int) -> dict[str, Any]:
    from agents import Agent, AgentOutputSchema, Runner, function_tool

    from discovery_system.decision_models import DiscoveryDecisionModel

    trace: dict[str, Any] = {"called": False}
    tool = _make_search_tool(self_id=self_id, limit=limit, trace=trace)

    agent = Agent(
        name="discovery_json_smoke",
        instructions=(
            "你是发现页红娘。输出必须是 DiscoveryDecision JSON（由系统 schema 约束）。\n"
            "如果条件已经够用，应调用 search_partner_candidates，再输出最终 JSON。\n"
            "phase 可以是 collecting_preferences、searching、results_shown、no_result。"
        ),
        model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
        output_type=AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=True),
        tools=[tool],
    )
    result = Runner.run_sync(agent, input=prompt)
    final = getattr(result, "final_output", result)
    phase = None
    message = None
    if hasattr(final, "phase"):
        phase = final.phase
        message = final.assistant_message
    elif isinstance(final, dict):
        phase = final.get("phase")
        message = final.get("assistant_message") or final.get("message")
    return {
        "mode": "structured_json",
        "search_tool_invoked": bool(trace.get("invoked")),
        "search_tool_called": bool(trace.get("called")),
        "tool_error": trace.get("tool_error"),
        "criteria": trace.get("criteria"),
        "has_match": trace.get("has_match"),
        "result_count": trace.get("result_count"),
        "error_code": trace.get("error_code"),
        "phase": phase,
        "assistant_message_preview": (str(message or ""))[:300],
    }


def _resolve_prompt_plan(args: argparse.Namespace) -> list[tuple[str, str]]:
    if args.minimal_only:
        args.prompt_style = "minimal"
        args.skip_json_agent = True
    if args.prompt is not None:
        return [("custom", args.prompt.strip())]
    if args.prompt_style == "minimal":
        return list(MINIMAL_SEARCH_PROMPTS.items())
    return [("full_scenario", DEFAULT_PROMPT.strip())]


def _run_scenario(
    *,
    label: str,
    prompt: str,
    self_id: int,
    limit: int,
    skip_json_agent: bool,
    include_forced_tool: bool,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    print(f"=== Scenario [{label}] ===")
    print(prompt)
    print()

    if not skip_json_agent:
        print("--- production-like agent (strict JSON + tools) ---")
        try:
            row = _run_json_agent(prompt=prompt, self_id=self_id, limit=limit)
            row["prompt_label"] = label
            summaries.append(row)
        except Exception as exc:  # noqa: BLE001
            summaries.append(
                {"mode": "structured_json", "prompt_label": label, "error": f"{type(exc).__name__}: {exc}"}
            )
        print(json.dumps(summaries[-1], ensure_ascii=False, indent=2))
        print()

    print("--- search-only (no JSON) ---")
    try:
        row = _run_search_only_agent(prompt=prompt, self_id=self_id, limit=limit)
        row["prompt_label"] = label
        summaries.append(row)
    except Exception as exc:  # noqa: BLE001
        summaries.append({"mode": "search_only", "prompt_label": label, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(summaries[-1], ensure_ascii=False, indent=2))
    print()

    if include_forced_tool:
        print("--- search-only + tool_choice=required ---")
        try:
            row = _run_search_only_agent(prompt=prompt, self_id=self_id, limit=limit, force_tool=True)
            row["prompt_label"] = label
            summaries.append(row)
        except Exception as exc:  # noqa: BLE001
            summaries.append(
                {
                    "mode": "search_only_forced_tool",
                    "prompt_label": label,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        print(json.dumps(summaries[-1], ensure_ascii=False, indent=2))
        print()

    return summaries


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    args = _parse_args()

    api_key = _resolve_discovery_api_key().strip()
    if not api_key or api_key.startswith("replace-with-"):
        print("ERROR: HER_DISCOVERY_AGENT_API_KEY / DASHSCOPE_API_KEY not configured", file=sys.stderr)
        return 2

    _configure_agents_sdk_provider()

    prompt_plan = _resolve_prompt_plan(args)
    include_forced_tool = args.prompt_style == "full" and not args.skip_json_agent and len(prompt_plan) == 1

    all_summaries: list[dict[str, Any]] = []
    for label, prompt in prompt_plan:
        all_summaries.extend(
            _run_scenario(
                label=label,
                prompt=prompt,
                self_id=args.self_id,
                limit=args.limit,
                skip_json_agent=args.skip_json_agent,
                include_forced_tool=include_forced_tool,
            )
        )

    print("=== Conclusion ===")
    for row in all_summaries:
        if row.get("mode") != "search_only":
            continue
        label = row.get("prompt_label", "?")
        if "error" in row:
            print(f"[{label}] search-only ERROR: {row['error'][:120]}")
            continue
        called = row.get("search_tool_called")
        count = row.get("result_count")
        preview = (row.get("final_output_preview") or "")[:80]
        print(f"[{label}] search-only called_tool={called} result_count={count} | {preview}")

    search_only_rows = [r for r in all_summaries if r.get("mode") == "search_only" and "error" not in r]
    any_called = any(r.get("search_tool_called") for r in search_only_rows)
    if args.prompt_style == "minimal":
        called_labels = [r.get("prompt_label") for r in search_only_rows if r.get("search_tool_called")]
        print(f"Minimal suite: {len(called_labels)}/{len(search_only_rows)} prompts triggered search: {called_labels}")
        return 0 if any_called else 1

    search_row = next((r for r in all_summaries if r.get("mode") == "search_only"), None)
    if search_row and search_row.get("search_tool_called"):
        print("Search-only: YES — tool was called for this prompt.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
