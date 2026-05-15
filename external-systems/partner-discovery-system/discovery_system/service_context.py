"""Read-model and runtime-context helpers for discovery service."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from .storage import StoredSession


@dataclass(frozen=True)
class DiscoveryServiceContextRuntime:
    storage: Any
    clone_view: Callable[[dict[str, Any]], dict[str, Any]]


def build_visible_action_summaries(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for action_id in list(session.visible_action_ids)[:3]:
        action = runtime.storage.get_action(session.session_id, action_id)
        if action is None:
            continue
        items.append(
            {
                "action_id": action.action_id,
                "label": action.label,
                "style": action.style,
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
        return None
    search_run = runtime.storage.get_search_run(search_run_id)
    if search_run is None:
        return {
            "search_run_id": search_run_id,
            "result_count": int(session.state.get("last_search_result_count") or 0),
            "has_match": bool(session.state.get("last_search_has_match")),
        }
    return {
        "search_run_id": search_run.search_run_id,
        "result_count": int(search_run.result_count or 0),
        "has_match": bool(search_run.has_match),
        "criteria": deepcopy(search_run.criteria),
        "source": search_run.source,
    }


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
                "reason_summary": card.get("reason_summary"),
            }
            for card in list(item.get("cards") or [])[:3]
        ]
        break
    return summary


def build_runtime_context(
    runtime: DiscoveryServiceContextRuntime,
    session: StoredSession,
    *,
    recent_timeline: list[dict[str, Any]],
    requester_profile_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "session_status": session.status,
        "requester_profile_snapshot": requester_profile_snapshot,
        "recent_timeline_summary": list(recent_timeline),
        "visible_actions": build_visible_action_summaries(runtime, session),
        "last_search_summary": build_last_search_summary(runtime, session),
        "page_summary": build_page_summary(runtime, session),
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
            if reason_summary:
                return [f"红娘当时把这位放到你面前，主要因为：{reason_summary}"]
            return []
    return []


__all__ = [
    "DiscoveryServiceContextRuntime",
    "build_last_search_summary",
    "build_page_summary",
    "build_profile_detail_notes",
    "build_runtime_context",
    "build_visible_action_summaries",
]
