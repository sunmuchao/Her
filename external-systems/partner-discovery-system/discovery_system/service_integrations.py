"""External-system bindings and persistence helpers for discovery service."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Callable

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from match_domain.criteria_compiler import build_discovery_search_request
from match_domain.criteria_snapshots import save_compiled_snapshot
from match_domain.persona_loader import load_persona_row
from match_domain.search_visibility import search_profiles_with_visibility_gate
from observability import metric_gauge
from partner_search import load_self_profile, search_profiles

from .agent_runtime import DiscoveryDecision
from .service_context import search_error_summary
from .storage import StoredSession


def profile_source() -> str:
    for name in (
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def persona_memory_source() -> str:
    for name in (
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def load_requester_profile(
    session: StoredSession,
    *,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
) -> dict[str, Any] | None:
    resolved_source = source if source is not None else profile_source()
    return load_requester_profile_with(
        session,
        source=resolved_source,
        load_profile=load_profile or load_self_profile,
    )


def load_requester_profile_with(
    session: StoredSession,
    *,
    source: str,
    load_profile: Callable[..., Any],
) -> dict[str, Any] | None:
    if not source or session.profile_id <= 0:
        return None
    try:
        profile = load_profile(
            source=source,
            self_id=session.profile_id,
        )
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(profile, dict):
        return None
    return profile


def _search_request_meta(
    session: StoredSession,
    *,
    source: str,
    criteria: dict[str, Any],
    self_profile: dict[str, Any] | None,
    effective_self_id: int | None,
    normalized_limit: int,
    compiled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "criteria": dict(criteria or {}),
        "self_profile": deepcopy(self_profile),
        "self_id": effective_self_id,
        "requested_self_id": session.profile_id,
        "self_profile_lookup_failed": effective_self_id is None and session.profile_id > 0,
        "table_name": None,
        "photos_table_name": None,
        "limit_count": normalized_limit,
        "compiled": deepcopy(compiled or {}),
        "source_map": deepcopy((compiled or {}).get("source_map") or {}),
    }


def search_partner_candidates(
    session: StoredSession,
    *,
    criteria: dict[str, Any],
    limit: int,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    search: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return search_partner_candidates_with(
        session,
        criteria=criteria,
        limit=limit,
        source=source if source is not None else profile_source(),
        load_profile=load_profile or load_self_profile,
        search=search or search_profiles,
    )


def search_partner_candidates_with(
    session: StoredSession,
    *,
    criteria: dict[str, Any],
    limit: int,
    source: str,
    load_profile: Callable[..., Any],
    search: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    if not source:
        return {
            "error_code": "search_source_not_configured",
            "has_match": False,
            "result_count": 0,
            "results": [],
            "fallback_results": [],
            "diagnostics": {
                "error": "search_source_not_configured",
            },
        }
    self_profile = load_requester_profile_with(
        session,
        source=source,
        load_profile=load_profile,
    )
    if isinstance(self_profile, dict) and not self_profile:
        self_profile = None
    effective_self_id = session.profile_id if isinstance(self_profile, dict) and self_profile else None
    normalized_limit = max(1, min(int(limit or 5), 10))
    persona_row = None
    persona_source = persona_memory_source() or source
    if persona_source:
        try:
            persona_row = load_persona_row(source=persona_source, user_key=str(session.requester_id))
        except Exception:  # noqa: BLE001
            persona_row = None
    compiled_request = build_discovery_search_request(
        source=source,
        profile_row=self_profile,
        persona_row=persona_row,
        criteria_overrides=dict(criteria or {}),
        self_id=effective_self_id,
        limit=normalized_limit,
    )
    compiled = dict(compiled_request.get("compiled") or {})
    request_meta = _search_request_meta(
        session,
        source=source,
        criteria=compiled_request.get("criteria") or {},
        self_profile=compiled_request.get("self_profile"),
        effective_self_id=effective_self_id,
        normalized_limit=normalized_limit,
        compiled=compiled,
    )
    try:
        save_compiled_snapshot(
            compiled,
            scene="discovery_search",
            profile_id=session.profile_id,
            requester_id=session.requester_id,
            user_key=str(session.requester_id),
            discovery_session_id=session.session_id,
        )
        compiled_self_profile = compiled_request.get("self_profile")
        if isinstance(compiled_self_profile, dict) and not compiled_self_profile:
            compiled_self_profile = None
        response = search_profiles_with_visibility_gate(
            search,
            source=source,
            criteria=dict(compiled_request.get("criteria") or {}),
            self_profile=compiled_self_profile,
            self_id=effective_self_id,
            limit=normalized_limit,
            photo_preview_count=3,
            moderation_dsn=os.environ.get("PARTNER_CHAT_DB"),
        )
        response["request_meta"] = request_meta
        return response
    except Exception as exc:  # noqa: BLE001
        return {
            "error_code": "partner_search_failed",
            "has_match": False,
            "result_count": 0,
            "results": [],
            "fallback_results": [],
            "diagnostics": {
                "error": str(exc)[:200],
            },
            "request_meta": request_meta,
        }


def sync_requester_persona_memory(
    session: StoredSession,
    *,
    patch: dict[str, Any],
    now: datetime | None = None,
    load_persona_memory: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_patch = dict(patch or {})
    if not normalized_patch:
        return {
            "synced": False,
            "error_code": "empty_persona_patch",
            "message": "没有可写入画像的字段。",
        }
    source = persona_memory_source()
    if not source:
        return {
            "synced": False,
            "error_code": "persona_memory_source_not_configured",
            "message": "当前没有配置 persona-memory-sync 数据源。",
        }
    current = now or datetime.now()
    try:
        upsert_persona_memory = load_persona_memory or load_persona_memory_bindings()
        upsert_result = upsert_persona_memory(
            {
                "source": source,
                "user_key": str(session.requester_id),
                "source_type": "explicit",
                "patch": normalized_patch,
                "sync_profile": True,
                "conversation_ref": f"discovery/{session.session_id}",
                "basis": "discovery_agent",
            },
            include_normalized_patch=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "synced": False,
            "error_code": "persona_memory_sync_failed",
            "message": str(exc)[:200],
        }
    session.state["last_persona_sync_at"] = current.isoformat()
    session.state["last_persona_sync_fields"] = sorted(
        str(key).strip()
        for key in normalized_patch.keys()
        if str(key or "").strip()
    )
    return {
        "synced": True,
        "user_key": str(session.requester_id),
        "patch_keys": list(session.state["last_persona_sync_fields"]),
        "upsert": upsert_result,
    }


def run_discovery_collect_then_search(
    session: StoredSession,
    *,
    persona_patch: dict[str, Any] | None = None,
    criteria: dict[str, Any] | None = None,
    limit: int = 5,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    search: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Service-layer orchestration: explicit collect first, then compile/search."""
    collect_result = None
    if persona_patch:
        collect_result = sync_requester_persona_memory(session, patch=persona_patch)
        if not collect_result.get("synced"):
            return {
                "orchestration": "collect_failed",
                "collect": collect_result,
                "search": None,
            }
    search_response = search_partner_candidates(
        session,
        criteria=criteria or {},
        limit=limit,
        source=source,
        load_profile=load_profile,
        search=search,
    )
    return {
        "orchestration": "collect_then_search" if persona_patch else "search_only",
        "collect": collect_result,
        "search": search_response,
    }


def persist_search_run(
    storage: Any,
    increment_metric: Callable[[str], int],
    session: StoredSession,
    *,
    search_response: dict[str, Any],
    now: datetime,
) -> int | None:
    error_summary = search_error_summary(search_response)
    session.state["last_search_result_count"] = int(search_response.get("result_count") or 0)
    session.state["last_search_has_match"] = bool(search_response.get("has_match"))
    if error_summary is None:
        session.state.pop("last_search_error_code", None)
        session.state.pop("last_search_error_message", None)
    else:
        session.state["last_search_error_code"] = str(error_summary.get("error_code") or "")
        session.state["last_search_error_message"] = str(error_summary.get("error") or "")
    request_meta = dict(search_response.get("request_meta") or {})
    source = str(request_meta.get("source") or "").strip()
    if not source:
        session.state.pop("last_search_run_id", None)
        return None
    search_run_id = storage.create_search_run(
        session_id=session.session_id,
        requester_id=session.requester_id,
        profile_id=session.profile_id,
        source=source,
        criteria=dict(request_meta.get("criteria") or {}),
        self_profile=request_meta.get("self_profile"),
        limit_count=int(request_meta.get("limit_count") or 5),
        response=search_response,
        created_at=now,
    )
    session.state["last_search_run_id"] = search_run_id
    increment_metric("search_runs.created")
    metric_gauge(
        "discovery.search_runs.result_count",
        int(search_response.get("result_count") or 0),
        session_id=session.session_id,
        search_run_id=search_run_id,
    )
    return search_run_id


def load_recommendation_bindings():
    ensure_partner_system_roots_on_sys_path(Path(__file__).resolve().parents[3])
    from recommendation_system import (  # type: ignore[import-untyped]
        connect_db as connect_recommendation_db,
        handle_opt_in_decision,
        initialize_database as initialize_recommendation_database,
    )

    return (
        connect_recommendation_db,
        handle_opt_in_decision,
        initialize_recommendation_database,
    )


def open_recommendation_conn(*, load_bindings: Callable[[], tuple[Any, Any, Any]] | None = None):
    connect_recommendation_db, _, initialize_recommendation_database = (
        load_bindings() if load_bindings is not None else load_recommendation_bindings()
    )
    dsn = str(
        os.environ.get("PARTNER_RECOMMENDATION_DB")
        or "mysql://root@127.0.0.1:3307/her_recommendation"
    ).strip()
    conn = connect_recommendation_db(dsn)
    initialize_recommendation_database(
        conn,
        mode=(os.environ.get("HER_SCHEMA_INIT_MODE") or "").strip() or None,
    )
    return conn


def load_persona_memory_bindings():
    from persona_memory_sync import upsert_persona_memory

    return upsert_persona_memory


def decision_payload(decision: DiscoveryDecision) -> dict[str, Any]:
    return {
        "phase": decision.phase,
        "assistant_message": decision.assistant_message,
        "criteria_labels": list(decision.criteria_labels),
        "suggested_actions": [
            {
                "label": action.label,
                "style": action.style,
                "semantic_payload": deepcopy(action.semantic_payload),
            }
            for action in list(decision.suggested_actions)
        ],
        "result_group_title": decision.result_group_title,
        "selected_candidates": [
            {
                "profile_id": candidate.profile_id,
                "reason_summary": candidate.reason_summary,
            }
            for candidate in list(decision.selected_candidates)
        ],
    }


__all__ = [
    "decision_payload",
    "load_persona_memory_bindings",
    "load_recommendation_bindings",
    "load_requester_profile",
    "open_recommendation_conn",
    "persona_memory_source",
    "persist_search_run",
    "profile_source",
    "run_discovery_collect_then_search",
    "search_partner_candidates",
    "sync_requester_persona_memory",
]
