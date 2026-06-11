"""Report discovery agent context size for representative prompt scenarios."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agents import AgentOutputSchema, function_tool

from discovery_system.agent_runtime import (
    DiscoveryDecisionModel,
    DiscoveryRunInput,
    _build_discovery_agent_instructions,
    _build_runtime_prompt,
    _safe_json_length,
    _tool_schema_debug_payload,
)

WARN_THRESHOLD_CHARS = 16000
ERROR_THRESHOLD_CHARS = 32000


def _stub_result(*args: Any, **kwargs: Any) -> dict[str, Any]:
    del args, kwargs
    return {}


def _build_base_context() -> dict[str, Any]:
    return {
        "session": {
            "session_id": "discovery-session-benchmark",
            "phase": "results_shown",
            "status": "active",
            "criteria_labels": ["苏州", "女", "26-36岁", "先谈恋爱"],
        },
        "user_profile": {
            "age": 31,
            "city": "苏州",
            "gender": "male",
            "has_children": False,
            "marital_status": "未婚",
            "relationship_goal": "dating",
            "self_city": "苏州",
            "self_job": "产品经理",
            "self_relationship_goal": "先谈恋爱",
            "target_gender": "女",
            "target_age_min": 26,
            "target_age_max": 36,
            "target_cities": ["苏州"],
            "preferred_traits": ["情绪稳定", "生活规律"],
            "personality_traits": {
                "mbti": {"type_code": "ISTP"},
                "attachment": {"type_code": "secure"},
                "values": {
                    "value_type": "稳定经营型",
                    "top_values": ["稳定经营", "家庭责任", "独立空间"],
                },
            },
        },
        "memory_summary": {
            "stable_preferences_summary": "目标城市偏向苏州；期望年龄26-36岁；关系目标是dating；更看重情绪稳定、生活规律。",
            "recent_feedback_summary": "最近没有明确负反馈，仍按稳定职业与长期关系方向筛选。",
            "recent_conversation_summary": "刚展示过一轮候选人，第一位是陈雨桐 30。",
        },
        "visible_actions": [
            {"label": "看看更多", "kind": "show_more_candidates", "hint": {"kind": "show_more_candidates"}},
            {"label": "调整条件", "kind": "refine_preferences", "hint": {"kind": "refine_preferences"}},
        ],
        "last_search": {
            "status": "success",
            "result_count": 5,
            "criteria_summary": "苏州，女，26-36岁，先谈恋爱",
        },
        "current_results": [
            {
                "profile_id": 573,
                "title": "陈雨桐 30",
                "reason_summary": "工作稳定，作息规律",
                "compatibility_summary": "MBTI ISTJ；依恋偏secure",
                "personality_signals": {
                    "mbti": {"type_code": "ISTJ"},
                    "attachment": {"type_code": "secure"},
                    "values": {"value_type": "稳定经营型", "top_values": ["稳定经营", "家庭责任"]},
                },
            },
            {
                "profile_id": 6609,
                "title": "周可心 32",
                "reason_summary": "情绪稳定，长期定居",
                "compatibility_summary": "MBTI ISFJ；价值观重家庭责任",
                "personality_signals": {
                    "mbti": {"type_code": "ISFJ"},
                    "attachment": {"type_code": "secure"},
                    "values": {"value_type": "稳定经营型", "top_values": ["家庭责任", "稳定经营"]},
                },
            },
        ],
    }


def _build_run_input(runtime_context: dict[str, Any]) -> DiscoveryRunInput:
    return DiscoveryRunInput(
        session_id="discovery-session-benchmark",
        requester_id=10001,
        profile_id=10001,
        phase="results_shown",
        criteria_labels=["苏州", "女", "26-36岁", "先谈恋爱"],
        recent_timeline=[],
        runtime_context=runtime_context,
        search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
        sync_requester_persona_memory=lambda _patch: {"synced": True},
        propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
        create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
        tool_call_buffer=[],
        agent_session=None,
    )


def _build_tool_debug_payload() -> list[dict[str, Any]]:
    @function_tool
    def sync_requester_persona_memory(patch_json: str) -> dict[str, Any]:
        return _stub_result(patch_json)

    @function_tool
    def propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
        return _stub_result(patch_json, evidence_text)

    @function_tool
    def search_partner_candidates(criteria_json: str, limit: int = 5) -> dict[str, Any]:
        return _stub_result(criteria_json, limit)

    @function_tool
    def create_saved_search_subscription_from_last_search() -> dict[str, Any]:
        return _stub_result()

    tools = [
        sync_requester_persona_memory,
        propose_requester_profile_update,
        search_partner_candidates,
        create_saved_search_subscription_from_last_search,
    ]
    return _tool_schema_debug_payload(tools)


def _legacy_runtime_context() -> dict[str, Any]:
    return {
        "requester_profile_snapshot": {
            "age": 31,
            "city": "苏州",
            "gender": "male",
            "has_children": False,
            "marital_status": "未婚",
            "relationship_goal": "dating",
            "self_city": "苏州",
            "self_job": "产品经理",
            "self_relationship_goal": "先谈恋爱",
            "target_gender": "女",
            "target_age_min": 26,
            "target_age_max": 36,
            "target_cities": ["苏州"],
            "preferred_traits": ["情绪稳定", "生活规律"],
            "personality_traits": {
                "mbti": {"type_code": "ISTP"},
                "attachment": {"type_code": "secure", "anxiety": 18, "avoidance": 21},
                "values": {
                    "value_type": "稳定经营型",
                    "top_values": ["稳定经营", "家庭责任", "独立空间"],
                },
            },
        },
        "recent_timeline_summary": [
            {"item_type": "user_message", "body": "我要找对象，你给我推荐几个合适的吧"},
            {"item_type": "assistant_message", "body": "好的，我按稳定职业方向帮你看几位。"},
            {
                "item_type": "result_group",
                "title": "先看这几位",
                "cards": [
                    {
                        "profile_id": 573,
                        "title": "陈雨桐 30",
                        "reason_summary": "工作稳定，作息规律",
                        "personality_match_context": {
                            "mbti": {"type_code": "ISTJ"},
                            "attachment": {"type_code": "secure", "anxiety": 24, "avoidance": 19},
                            "values": {
                                "value_type": "稳定经营型",
                                "top_values": ["稳定经营", "家庭责任", "长期投入"],
                            },
                            "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                        },
                    },
                    {
                        "profile_id": 6609,
                        "title": "周可心 32",
                        "reason_summary": "情绪稳定，长期定居",
                        "personality_match_context": {
                            "mbti": {"type_code": "ISFJ"},
                            "attachment": {"type_code": "secure", "anxiety": 20, "avoidance": 22},
                            "values": {
                                "value_type": "稳定经营型",
                                "top_values": ["家庭责任", "稳定经营", "长期主义"],
                            },
                            "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                        },
                    },
                ],
            },
        ],
        "visible_actions": [
            {"label": "看看更多", "kind": "show_more_candidates", "hint": {"kind": "show_more_candidates"}},
            {"label": "调整条件", "kind": "refine_preferences", "hint": {"kind": "refine_preferences"}},
        ],
        "last_search_summary": {
            "status": "success",
            "result_count": 5,
            "criteria_summary": "苏州，女，26-36岁，先谈恋爱",
            "request_meta": {
                "criteria": {
                    "gender": "女",
                    "cities": ["苏州"],
                    "age_min": 26,
                    "age_max": 36,
                    "relationship_goals": ["先谈恋爱"],
                },
                "limit_count": 5,
            },
        },
        "page_summary": {
            "criteria_labels": ["苏州", "女", "26-36岁", "先谈恋爱"],
            "suggested_action_labels": ["看看更多", "调整条件"],
            "result_cards": [
                {
                    "profile_id": 573,
                    "title": "陈雨桐 30",
                    "subtitle": "苏州 · 公务员 · 硕士",
                    "match_score": 94,
                    "reason_summary": "工作稳定，作息规律，倾向长期关系",
                    "personality_match_context": {
                        "mbti": {"type_code": "ISTJ"},
                        "attachment": {"type_code": "secure", "anxiety": 24, "avoidance": 19},
                        "values": {
                            "value_type": "稳定经营型",
                            "top_values": ["稳定经营", "家庭责任", "长期投入"],
                        },
                        "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                    },
                    "personality_availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                },
                {
                    "profile_id": 6609,
                    "title": "周可心 32",
                    "subtitle": "苏州 · 药师 · 本科",
                    "match_score": 91,
                    "reason_summary": "情绪稳定，长期定居",
                    "personality_match_context": {
                        "mbti": {"type_code": "ISFJ"},
                        "attachment": {"type_code": "secure", "anxiety": 20, "avoidance": 22},
                        "values": {
                            "value_type": "稳定经营型",
                            "top_values": ["家庭责任", "稳定经营", "长期主义"],
                        },
                        "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                    },
                    "personality_availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                },
            ],
        },
    }


def _legacy_instructions(instructions: str) -> str:
    return (
        instructions
        + "\n\n补充规则：\n"
        + "始终保留测评推荐规则、换一批反馈闭环、详细页面解释规则，不按场景裁剪。"
    )


def _legacy_payload(
    *,
    event: str,
    user_message: str | None,
    action_context: dict[str, Any] | None,
) -> str:
    runtime_context = _legacy_runtime_context()
    payload = {
        "event": event,
        "session": {
            "session_id": "discovery-session-benchmark",
            "phase": "results_shown",
            "criteria_labels": ["苏州", "女", "26-36岁", "先谈恋爱"],
            "requester_id": 10001,
            "profile_id": 10001,
        },
        "latest_user_message": str(user_message or "").strip() or None,
        "clicked_action": {
            "label": str((action_context or {}).get("label") or "").strip() or None,
            "hint": dict((action_context or {}).get("semantic_payload") or {}),
        }
        if action_context
        else None,
        "note": "优先参考官方上下文，必要时再调用工具。",
        "official_context": runtime_context,
        "session_replay": [runtime_context for _ in range(3)],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _measure_scenario(
    *,
    name: str,
    event: str,
    user_message: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_context = _build_base_context()
    run_input = _build_run_input(runtime_context)
    instructions = _build_discovery_agent_instructions(
        event=event,
        user_message=user_message,
        action_context=action_context,
    )
    payload = _build_runtime_prompt(
        run_input=run_input,
        event=event,
        user_message=user_message,
        action_context=action_context,
    )
    output_schema = AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=True)
    tool_payload = _build_tool_debug_payload()
    instructions_chars = len(instructions)
    input_chars = len(payload)
    schema_chars = _safe_json_length(output_schema.json_schema())
    tools_chars = _safe_json_length(tool_payload)
    total_chars = instructions_chars + input_chars + schema_chars + tools_chars
    return {
        "scenario": name,
        "instructions_chars": instructions_chars,
        "input_chars": input_chars,
        "schema_chars": schema_chars,
        "tools_chars": tools_chars,
        "total_chars": total_chars,
        "rough_tokens": round(total_chars / 4),
    }


def _measure_legacy_scenario(
    *,
    name: str,
    event: str,
    user_message: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    instructions = _legacy_instructions(
        _build_discovery_agent_instructions(
            event=event,
            user_message=user_message,
            action_context=action_context,
        )
    )
    payload = _legacy_payload(
        event=event,
        user_message=user_message,
        action_context=action_context,
    )
    output_schema = AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=True)
    tool_payload = _build_tool_debug_payload()
    instructions_chars = len(instructions)
    input_chars = len(payload)
    schema_chars = _safe_json_length(output_schema.json_schema())
    tools_chars = _safe_json_length(tool_payload)
    total_chars = instructions_chars + input_chars + schema_chars + tools_chars
    return {
        "scenario": name,
        "instructions_chars": instructions_chars,
        "input_chars": input_chars,
        "schema_chars": schema_chars,
        "tools_chars": tools_chars,
        "total_chars": total_chars,
        "rough_tokens": round(total_chars / 4),
    }


def _all_scenarios() -> list[dict[str, Any]]:
    return [
        _measure_scenario(
            name="plain_recommendation",
            event="user_message",
            user_message="我要找对象，你给我推荐几个合适的吧",
        ),
        _measure_scenario(
            name="assessment_question",
            event="user_message",
            user_message="我的 MBTI 适合什么人？",
        ),
        _measure_scenario(
            name="batch_refresh",
            event="user_message",
            user_message="帮我换一批",
        ),
        _measure_scenario(
            name="feedback_click",
            event="action_click",
            action_context={
                "label": "职业不太匹配",
                "semantic_payload": {
                    "kind": "rejection_feedback",
                    "feedback_type": "occupation_mismatch",
                },
            },
        ),
    ]


def _comparison_report() -> list[dict[str, Any]]:
    optimized = {item["scenario"]: item for item in _all_scenarios()}
    scenarios = [
        ("plain_recommendation", "user_message", "我要找对象，你给我推荐几个合适的吧", None),
        ("assessment_question", "user_message", "我的 MBTI 适合什么人？", None),
        ("batch_refresh", "user_message", "帮我换一批", None),
        (
            "feedback_click",
            "action_click",
            None,
            {
                "label": "职业不太匹配",
                "semantic_payload": {
                    "kind": "rejection_feedback",
                    "feedback_type": "occupation_mismatch",
                },
            },
        ),
    ]
    report: list[dict[str, Any]] = []
    for name, event, user_message, action_context in scenarios:
        baseline = _measure_legacy_scenario(
            name=name,
            event=event,
            user_message=user_message,
            action_context=action_context,
        )
        current = optimized[name]
        chars_saved = baseline["total_chars"] - current["total_chars"]
        tokens_saved = baseline["rough_tokens"] - current["rough_tokens"]
        report.append(
            {
                "scenario": name,
                "baseline": baseline,
                "optimized": current,
                "diff": {
                    "chars_saved": chars_saved,
                    "token_saved": tokens_saved,
                    "char_reduction_ratio": round(chars_saved / baseline["total_chars"], 4)
                    if baseline["total_chars"]
                    else 0.0,
                    "under_warn_threshold": current["total_chars"] < WARN_THRESHOLD_CHARS,
                    "under_error_threshold": current["total_chars"] < ERROR_THRESHOLD_CHARS,
                    "baseline_is_approximation": True,
                },
            }
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=["plain_recommendation", "assessment_question", "batch_refresh", "feedback_click", "all"],
        default="all",
        help="Only report one scenario; default reports all representative scenarios.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Include a legacy-structure approximation to show before/after savings.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    results: Any = _comparison_report() if args.compare_baseline else _all_scenarios()
    if args.scenario != "all":
        results = [item for item in results if item["scenario"] == args.scenario]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
