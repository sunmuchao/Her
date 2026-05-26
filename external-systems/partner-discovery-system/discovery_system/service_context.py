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
        error_code = str(session.state.get("last_search_error_code") or "").strip()
        error_message = str(session.state.get("last_search_error_message") or "").strip()
        if not error_code and not error_message:
            return None
        summary = {
            "search_run_id": None,
            "result_count": int(session.state.get("last_search_result_count") or 0),
            "has_match": bool(session.state.get("last_search_has_match")),
        }
        if error_code:
            summary["error_code"] = error_code
        if error_message:
            summary["error"] = error_message
        return summary
    search_run = runtime.storage.get_search_run(search_run_id)
    if search_run is None:
        summary = {
            "search_run_id": search_run_id,
            "result_count": int(session.state.get("last_search_result_count") or 0),
            "has_match": bool(session.state.get("last_search_has_match")),
        }
        error_code = str(session.state.get("last_search_error_code") or "").strip()
        error_message = str(session.state.get("last_search_error_message") or "").strip()
        if error_code:
            summary["error_code"] = error_code
        if error_message:
            summary["error"] = error_message
        return summary
    summary = {
        "search_run_id": search_run.search_run_id,
        "result_count": int(search_run.result_count or 0),
        "has_match": bool(search_run.has_match),
        "criteria": deepcopy(search_run.criteria),
        "source": search_run.source,
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
    "search_error_summary",
]
