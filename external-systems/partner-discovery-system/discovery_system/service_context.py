"""Read-model and runtime-context helpers for discovery service."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from .agent_session_store import (
    build_visual_context_runtime_summary,
    build_visual_memory_runtime_summary,
)
from .storage import StoredSession


@dataclass(frozen=True)
class DiscoveryServiceContextRuntime:
    storage: Any
    clone_view: Callable[[dict[str, Any]], dict[str, Any]]


def _compact_personality_signals(value: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(value or {})
    compact: dict[str, Any] = {}
    mbti = dict(context.get("mbti") or {})
    mbti_type = str(mbti.get("type_code") or "").strip()
    if mbti_type:
        compact["mbti"] = {"type_code": mbti_type}

    attachment = dict(context.get("attachment") or {})
    attachment_type = str(attachment.get("type_code") or "").strip()
    if attachment_type:
        compact["attachment"] = {"type_code": attachment_type}

    values = dict(context.get("values") or {})
    top_values = [str(item).strip() for item in list(values.get("top_values") or []) if str(item).strip()][:2]
    value_type = str(values.get("value_type") or "").strip()
    compact_values: dict[str, Any] = {}
    if value_type:
        compact_values["value_type"] = value_type
    if top_values:
        compact_values["top_values"] = top_values
    if compact_values:
        compact["values"] = compact_values
    return compact


def _compatibility_summary(card: dict[str, Any]) -> str:
    reasoning = dict(card.get("personality_reasoning") or {})
    summary = str(reasoning.get("summary") or "").strip()
    if summary:
        return summary
    context = _compact_personality_signals(card.get("personality_match_context"))
    hints: list[str] = []
    mbti_type = str(((context.get("mbti") or {}).get("type_code")) or "").strip()
    attachment_type = str(((context.get("attachment") or {}).get("type_code")) or "").strip()
    top_values = list((context.get("values") or {}).get("top_values") or [])
    if mbti_type:
        hints.append(f"MBTI {mbti_type}")
    if attachment_type:
        hints.append(f"依恋偏{attachment_type}")
    if top_values:
        hints.append(f"价值观重{('、'.join(top_values[:2]))}")
    return "；".join(hints[:2])


def _compact_recent_timeline_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items[-4:]:
        item_type = str(item.get("item_type") or "").strip()
        if item_type in {"assistant_message", "user_message"}:
            body = str(item.get("body") or "").strip()
            if body:
                compacted.append({"item_type": item_type, "body": body})
            continue
        if item_type == "result_group":
            title = str(item.get("title") or "").strip()
            compacted.append(
                {
                    "item_type": "result_group",
                    "title": title,
                    "cards": [
                        {
                            "profile_id": card.get("profile_id"),
                            "title": card.get("title"),
                            "reason_summary": card.get("reason_summary"),
                        }
                        for card in list(item.get("cards") or [])[:2]
                    ],
                }
            )
            continue
        if item_type == "assessment_result":
            card = dict(item.get("card") or {})
            result_data = dict(card.get("result_data") or {})
            assessment_type = card.get("assessment_type") or result_data.get("assessment_type")
            compacted.append(
                {
                    "item_type": "assessment_result",
                    "assessment_type": assessment_type,
                    "type_code": result_data.get("type_code"),
                    "summary": (
                        (result_data.get("interpretation_data") or {}).get("summary")
                        if isinstance(result_data.get("interpretation_data"), dict)
                        else None
                    ),
                }
            )
    return compacted


def _stable_preferences_summary(requester_profile_snapshot: dict[str, Any] | None) -> str:
    profile = dict(requester_profile_snapshot or {})
    bits: list[str] = []
    target_cities = [str(item).strip() for item in list(profile.get("target_cities") or []) if str(item).strip()]
    if target_cities:
        bits.append(f"目标城市偏向{ '、'.join(target_cities[:2]) }")
    age_min = profile.get("target_age_min")
    age_max = profile.get("target_age_max")
    if age_min or age_max:
        bits.append(f"期望年龄{age_min or '?'}-{age_max or '?'}岁")
    relationship_goal = str(profile.get("relationship_goal") or "").strip()
    # self_relationship_goal 已删除，relationship_goal 现在只在 profiles 表中（硬条件）
    if relationship_goal:
        bits.append(f"关系目标是{relationship_goal}")
    preferred_traits = [str(item).strip() for item in list(profile.get("preferred_traits") or []) if str(item).strip()]
    if preferred_traits:
        bits.append(f"更看重{'、'.join(preferred_traits[:3])}")
    compact_traits = _compact_personality_signals(profile.get("personality_traits"))
    mbti_type = str(((compact_traits.get("mbti") or {}).get("type_code")) or "").strip()
    if mbti_type:
        bits.append(f"本人MBTI是{mbti_type}")
    return "；".join(bits[:4])


def _recent_feedback_summary(items: list[dict[str, Any]], visible_actions: list[dict[str, Any]]) -> str:
    feedback_types = [
        str(dict(action.get("hint") or {}).get("feedback_type") or "").strip()
        for action in list(visible_actions or [])
        if str(action.get("kind") or "").strip() == "rejection_feedback"
    ]
    feedback_types = [item for item in feedback_types if item and item != "skip_feedback"]
    if feedback_types:
        # ✅ Agent Native：移除硬编码 feedback_type 映射表
        # Agent 自主根据 feedback_type 生成追问文案
        # 只传递原始 feedback_type 列表
        labels = feedback_types[:3]  # 直接使用原始值
        return f"当前在追问上一批不合适的原因，重点方向是{'、'.join(labels)}。"

    recent_user_feedback: list[str] = []
    for item in reversed(list(items)[-6:]):
        if str(item.get("item_type") or "").strip() != "user_message":
            continue
        body = str(item.get("body") or "").strip()
        if any(marker in body for marker in ("不合适", "不匹配", "换一批", "重新找", "再看")):
            recent_user_feedback.append(body)
        if len(recent_user_feedback) >= 2:
            break
    if recent_user_feedback:
        return "；".join(reversed(recent_user_feedback))
    return ""


def _recent_conversation_summary(items: list[dict[str, Any]]) -> str:
    compacted = _compact_recent_timeline_items(items)
    if not compacted:
        return ""

    latest_result_group = next(
        (item for item in reversed(compacted) if str(item.get("item_type") or "") == "result_group"),
        None,
    )
    latest_assessment = next(
        (item for item in reversed(compacted) if str(item.get("item_type") or "") == "assessment_result"),
        None,
    )
    latest_user = next(
        (item for item in reversed(compacted) if str(item.get("item_type") or "") == "user_message"),
        None,
    )

    if latest_result_group is not None:
        cards = list(latest_result_group.get("cards") or [])
        title = str(latest_result_group.get("title") or "").strip() or "最近一轮候选人"
        if cards:
            first_title = str(cards[0].get("title") or "").strip()
            return f"{title}刚展示过，第一位是{first_title}。"
        return f"{title}刚展示过。"
    if latest_assessment is not None:
        assessment_type = str(latest_assessment.get("assessment_type") or "").strip()
        type_code = str(latest_assessment.get("type_code") or "").strip()
        summary = str(latest_assessment.get("summary") or "").strip()
        bits = [bit for bit in (assessment_type, type_code, summary) if bit]
        return f"最近刚看过测评结果：{'，'.join(bits[:3])}。"
    if latest_user is not None:
        body = str(latest_user.get("body") or "").strip()
        return f"用户最近一句是：{body}"
    return ""


def _build_memory_summary(
    requester_profile_snapshot: dict[str, Any] | None,
    recent_timeline: list[dict[str, Any]],
    visible_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "stable_preferences_summary": _stable_preferences_summary(requester_profile_snapshot),
        "recent_feedback_summary": _recent_feedback_summary(recent_timeline, visible_actions),
        "recent_conversation_summary": _recent_conversation_summary(recent_timeline),
    }


def search_error_summary(search_response: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(search_response, dict):
        return None
    error_code = str(search_response.get("error_code") or "").strip()
    diagnostics = dict(search_response.get("diagnostics") or {})
    error_message = str(diagnostics.get("error") or "").strip()
    if not error_code and not error_message:
        return None
    summary: dict[str, Any] = {}
    if error_code:
        summary["error_code"] = error_code
    if error_message:
        summary["error"] = error_message
    return summary


def build_visible_action_summaries(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
) -> list[dict[str, Any]]:
    visible_action_ids = [str(action_id) for action_id in list(session.visible_action_ids)[:3]]
    actions_by_id = runtime.storage.get_actions(session.session_id, visible_action_ids)
    items: list[dict[str, Any]] = []
    for action_id in visible_action_ids:
        action = actions_by_id.get(action_id)
        if action is None:
            continue
        items.append(
            {
                "label": action.label,
                "kind": str(dict(action.semantic_payload or {}).get("kind") or "").strip() or None,
                "hint": deepcopy(action.semantic_payload),
            }
        )
    return items


def build_last_search_summary(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
) -> dict[str, Any] | None:
    search_run_id = int(session.state.get("last_search_run_id") or 0)
    if search_run_id <= 0:
        error_code = str(session.state.get("last_search_error_code") or "").strip()
        error_message = str(session.state.get("last_search_error_message") or "").strip()
        if not error_code and not error_message:
            return None
        summary = {
            "status": "error",
            "result_count": int(session.state.get("last_search_result_count") or 0),
        }
        if error_code:
            summary["error_code"] = error_code
        if error_message:
            summary["error"] = error_message
        return summary
    search_run = runtime.storage.get_search_run(search_run_id)
    if search_run is None:
        summary = {
            "status": "success" if bool(session.state.get("last_search_has_match")) else "empty",
            "result_count": int(session.state.get("last_search_result_count") or 0),
        }
        error_code = str(session.state.get("last_search_error_code") or "").strip()
        error_message = str(session.state.get("last_search_error_message") or "").strip()
        if error_code:
            summary["error_code"] = error_code
        if error_message:
            summary["error"] = error_message
        return summary
    criteria = deepcopy(search_run.criteria)
    criteria_bits: list[str] = []
    cities = list(criteria.get("cities") or [])
    if cities:
        criteria_bits.append("/".join(str(item).strip() for item in cities[:2] if str(item).strip()))
    gender = str(criteria.get("gender") or "").strip()
    if gender:
        criteria_bits.append(gender)
    age_min = criteria.get("age_min")
    age_max = criteria.get("age_max")
    if age_min or age_max:
        criteria_bits.append(f"{age_min or '?'}-{age_max or '?'}岁")
    relationship_goals = list(criteria.get("relationship_goals") or [])
    if relationship_goals:
        criteria_bits.append(str(relationship_goals[0]))
    summary = {
        "status": "success" if bool(search_run.has_match) else "empty",
        "result_count": int(search_run.result_count or 0),
        "criteria_summary": "，".join(bit for bit in criteria_bits if bit) or None,
    }
    error_summary = search_error_summary(dict(search_run.response or {}))
    if error_summary:
        summary.update(error_summary)
    return summary


def build_page_summary(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
) -> dict[str, Any]:
    summary = {
        "criteria_labels": [
            str(item.get("label") or "").strip()
            for item in list(session.view.get("criteria_chips") or [])
            if str(item.get("label") or "").strip()
        ],
        "suggested_action_labels": [
            str(item.get("label") or "").strip()
            for item in build_visible_action_summaries(runtime, session)
            if str(item.get("label") or "").strip()
        ],
        "result_cards": [],
    }
    for item in reversed(list(session.view.get("timeline") or [])):
        if item.get("item_type") != "result_group":
            continue
        summary["result_cards"] = [
            {
                "profile_id": card.get("profile_id"),
                "title": card.get("title"),
                "subtitle": card.get("subtitle"),  # 包含城市·职业·学历，供 Agent 介绍候选人时使用
                "reason_summary": card.get("reason_summary"),
                "compatibility_summary": _compatibility_summary(card),
                "personality_match_context": _compact_personality_signals(card.get("personality_match_context")),
            }
            for card in list(item.get("cards") or [])  # 不再截断 [:3]
        ]
        break
    return summary


def build_current_results(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
) -> list[dict[str, Any]]:
    page_summary = build_page_summary(runtime, session)
    return [
        {
            "profile_id": card.get("profile_id"),
            "title": card.get("title"),
            "subtitle": card.get("subtitle"),  # 包含城市·职业·学历，供 Agent 介绍候选人时使用
            "reason_summary": card.get("reason_summary"),
            "compatibility_summary": card.get("compatibility_summary"),
            "personality_signals": deepcopy(card.get("personality_match_context") or {}),
        }
        for card in list(page_summary.get("result_cards") or [])  # 不再截断 [:3]
    ]


def build_runtime_context(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
    *,
    recent_timeline: list[dict[str, Any]],
    requester_profile_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    visible_actions = build_visible_action_summaries(runtime, session)
    return {
        "session": {
            "session_id": session.session_id,
            "phase": session.phase,
            "status": session.status,
            "criteria_labels": [
                str(item.get("label") or "").strip()
                for item in list(session.view.get("criteria_chips") or [])
                if str(item.get("label") or "").strip()
            ],
        },
        "user_profile": requester_profile_snapshot,
        "current_results": build_current_results(runtime, session),
        "visible_actions": visible_actions,
        "last_search": build_last_search_summary(runtime, session),
        "visual_context": build_visual_context_runtime_summary(
            session.state.get("visual_memory") or session.state.get("visual_context")
        ),
        "visual_memory": build_visual_memory_runtime_summary(
            session.state.get("visual_memory") or session.state.get("visual_context")
        ),
        "memory_summary": _build_memory_summary(requester_profile_snapshot, list(recent_timeline), visible_actions),
    }


def build_profile_detail_notes(
    session: StoredSession | None,
    profile_id: int,
) -> list[str]:
    if session is None:
        return []
    for item in reversed(list(session.view.get("timeline") or [])):
        if item.get("item_type") != "result_group":
            continue
        for card in list(item.get("cards") or []):
            if int(card.get("profile_id") or 0) != profile_id:
                continue
            reason_summary = str(card.get("reason_summary") or "").strip()
            personality_summary = str((card.get("personality_reasoning") or {}).get("summary") or "").strip()
            if personality_summary:
                return [f"红娘当时把这位放到你面前，主要因为：{personality_summary}"]
            if reason_summary:
                return [f"红娘当时把这位放到你面前，主要因为：{reason_summary}"]
            return []
    return []


__all__ = [
    "DiscoveryServiceContextRuntime",
    "build_current_results",
    "build_last_search_summary",
    "build_page_summary",
    "build_profile_detail_notes",
    "build_runtime_context",
    "build_visible_action_summaries",
    "search_error_summary",
]
