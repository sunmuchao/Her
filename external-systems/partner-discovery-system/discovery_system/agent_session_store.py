"""Persistent session-memory store for discovery agent conversations."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import os
from pathlib import Path
import threading
from typing import Any

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from .storage import connect_db, json_dumps, json_loads  # noqa: E402


def _session_memory_enabled() -> bool:
    raw = (os.environ.get("HER_DISCOVERY_AGENT_SESSION_MEMORY") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _session_settings() -> Any | None:
    try:
        from agents.memory import SessionSettings
    except Exception:  # noqa: BLE001
        return None

    raw = (os.environ.get("HER_DISCOVERY_AGENT_SESSION_LIMIT") or "80").strip().lower()
    if raw in {"", "none", "null", "all", "unlimited", "0"}:
        return SessionSettings(limit=None)
    try:
        limit = max(1, int(raw))
    except ValueError:
        limit = 80
    return SessionSettings(limit=limit)


def _resolve_session_limit(limit: int | None, session_settings: Any | None) -> int | None:
    if limit is not None:
        try:
            return max(1, int(limit))
        except (TypeError, ValueError):
            return None
    value = getattr(session_settings, "limit", None)
    try:
        return max(1, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_string_list(values: Any, *, max_items: int | None = None) -> list[str]:
    items: list[str] = []
    for raw in list(values or []):
        text = _clean_text(raw)
        if not text or text in items:
            continue
        items.append(text)
        if max_items is not None and len(items) >= max_items:
            break
    return items


def normalize_visual_memory(value: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(value or {})
    if isinstance(source.get("visual_memory"), dict):
        source = dict(source.get("visual_memory") or {})

    reference = dict(source.get("active_reference") or source.get("active_reference_image") or {})
    preference = dict(source.get("active_preference") or source.get("active_visual_intent") or {})
    constraints = dict(source.get("active_constraints") or {})
    last_result = dict(source.get("last_result") or {})

    last_result_profile_ids = [
        int(item)
        for item in list(
            last_result.get("profile_ids")
            or source.get("last_result_profile_ids")
            or []
        )
        if str(item).strip().isdigit() and int(item) > 0
    ][:30]
    refinement_history = _clean_string_list(
        source.get("refinement_history") or constraints.get("refinement_texts"),
        max_items=12,
    )

    return {
        "active_reference": {
            "source": _clean_text(reference.get("source")),
            "mime_type": _clean_text(reference.get("mime_type")),
            "role": _clean_text(reference.get("role")) or "reference",
            "updated_at": _clean_text(reference.get("updated_at")),
        },
        "active_preference": {
            "legacy_mode": _clean_text(preference.get("legacy_mode") or preference.get("mode")),
            "intent_type": _clean_text(preference.get("intent_type")),
            "query_text": _clean_text(preference.get("query_text")),
            "raw_text": _clean_text(preference.get("raw_text")),
            "reference_person": _clean_text(
                preference.get("reference_person") or preference.get("celebrity_name")
            ),
            "visual_axes": _clean_string_list(
                preference.get("visual_axes") or preference.get("style_keywords"),
                max_items=8,
            ),
            "search_strategy": _clean_text(preference.get("search_strategy")),
            "updated_at": _clean_text(preference.get("updated_at")),
        },
        "active_constraints": {
            "attribute_filters": dict(constraints.get("attribute_filters") or {}),
            "hard_filters": dict(constraints.get("hard_filters") or {}),
            "style_keywords": _clean_string_list(constraints.get("style_keywords"), max_items=8),
            "appearance_notes": _clean_string_list(constraints.get("appearance_notes"), max_items=8),
            "updated_at": _clean_text(constraints.get("updated_at")),
        },
        "refinement_history": refinement_history,
        "last_result": {
            "group_id": _clean_text(last_result.get("group_id") or source.get("last_result_group_id")),
            "profile_ids": last_result_profile_ids,
            "query_text": _clean_text(last_result.get("query_text") or source.get("last_query_text")),
            "summary": _clean_text(last_result.get("summary")),
        },
        "updated_at": _clean_text(source.get("updated_at")),
    }


def build_visual_memory_runtime_summary(value: dict[str, Any] | None) -> dict[str, Any] | None:
    visual_memory = normalize_visual_memory(value)
    reference = dict(visual_memory.get("active_reference") or {})
    preference = dict(visual_memory.get("active_preference") or {})
    constraints = dict(visual_memory.get("active_constraints") or {})
    last_result = dict(visual_memory.get("last_result") or {})
    has_reference_image = bool(reference.get("source"))
    if (
        not has_reference_image
        and not preference.get("query_text")
        and not list(last_result.get("profile_ids") or [])
    ):
        return None
    return {
        "has_reference_image": has_reference_image,
        "active_reference": {
            "source": reference.get("source"),
            "mime_type": reference.get("mime_type"),
            "role": reference.get("role"),
        },
        "active_preference": {
            "legacy_mode": preference.get("legacy_mode"),
            "intent_type": preference.get("intent_type"),
            "query_text": preference.get("query_text"),
            "reference_person": preference.get("reference_person"),
            "visual_axes": list(preference.get("visual_axes") or []),
            "search_strategy": preference.get("search_strategy"),
        },
        "active_constraints": {
            "attribute_filters": dict(constraints.get("attribute_filters") or {}),
            "hard_filters": dict(constraints.get("hard_filters") or {}),
            "style_keywords": list(constraints.get("style_keywords") or []),
            "appearance_notes": list(constraints.get("appearance_notes") or []),
        },
        "refinement_history": list(visual_memory.get("refinement_history") or [])[-4:],
        "last_result": {
            "group_id": last_result.get("group_id"),
            "profile_ids": list(last_result.get("profile_ids") or []),
            "query_text": last_result.get("query_text"),
            "summary": last_result.get("summary"),
        },
        "updated_at": visual_memory.get("updated_at"),
    }


def visual_memory_to_legacy_context(value: dict[str, Any] | None) -> dict[str, Any]:
    visual_memory = normalize_visual_memory(value)
    reference = dict(visual_memory.get("active_reference") or {})
    preference = dict(visual_memory.get("active_preference") or {})
    constraints = dict(visual_memory.get("active_constraints") or {})
    last_result = dict(visual_memory.get("last_result") or {})

    return {
        "active_reference_image": {
            "source": reference.get("source"),
            "mime_type": reference.get("mime_type"),
            "role": reference.get("role"),
            "updated_at": reference.get("updated_at"),
        },
        "active_visual_intent": {
            "mode": preference.get("legacy_mode"),
            "intent_type": preference.get("intent_type"),
            "query_text": preference.get("query_text"),
            "raw_text": preference.get("query_text"),
            "celebrity_name": preference.get("reference_person"),
            "updated_at": preference.get("updated_at"),
        },
        "active_constraints": {
            "attribute_filters": dict(constraints.get("attribute_filters") or {}),
            "hard_filters": dict(constraints.get("hard_filters") or {}),
            "style_keywords": list(constraints.get("style_keywords") or []),
            "appearance_notes": list(constraints.get("appearance_notes") or []),
            "refinement_texts": list(visual_memory.get("refinement_history") or []),
            "updated_at": constraints.get("updated_at"),
        },
        "last_result_group_id": last_result.get("group_id"),
        "last_result_profile_ids": list(last_result.get("profile_ids") or []),
        "last_query_text": last_result.get("query_text"),
        "updated_at": visual_memory.get("updated_at"),
    }


def normalize_visual_context(value: dict[str, Any] | None) -> dict[str, Any]:
    return visual_memory_to_legacy_context(value)


def build_visual_context_runtime_summary(value: dict[str, Any] | None) -> dict[str, Any] | None:
    visual_context = normalize_visual_context(value)
    reference = dict(visual_context.get("active_reference_image") or {})
    intent = dict(visual_context.get("active_visual_intent") or {})
    constraints = dict(visual_context.get("active_constraints") or {})
    has_reference_image = bool(reference.get("source"))
    if not has_reference_image and not intent.get("query_text") and not visual_context.get("last_result_profile_ids"):
        return None
    return {
        "has_reference_image": has_reference_image,
        "active_visual_intent": {
            "mode": intent.get("mode"),
            "intent_type": intent.get("intent_type"),
            "query_text": intent.get("query_text"),
            "celebrity_name": intent.get("celebrity_name"),
        },
        "active_constraints": {
            "attribute_filters": dict(constraints.get("attribute_filters") or {}),
            "hard_filters": dict(constraints.get("hard_filters") or {}),
            "style_keywords": list(constraints.get("style_keywords") or []),
            "appearance_notes": list(constraints.get("appearance_notes") or []),
            "refinement_texts": list(constraints.get("refinement_texts") or [])[-4:],
        },
        "last_result_group_id": visual_context.get("last_result_group_id"),
        "last_result_profile_ids": list(visual_context.get("last_result_profile_ids") or []),
        "last_query_text": visual_context.get("last_query_text"),
        "updated_at": visual_context.get("updated_at"),
    }


class InMemoryDiscoveryAgentSession:
    def __init__(
        self,
        session_id: str,
        *,
        sessions: dict[str, list[dict[str, Any]]],
        lock: threading.Lock,
        session_settings: Any | None,
    ) -> None:
        self.session_id = session_id
        self.session_settings = session_settings
        self._sessions = sessions
        self._lock = lock

    async def get_items(self, limit: int | None = None) -> list[dict[str, Any]]:
        session_limit = _resolve_session_limit(limit, self.session_settings)

        def _get_items_sync() -> list[dict[str, Any]]:
            with self._lock:
                items = deepcopy(self._sessions.get(self.session_id) or [])
            if session_limit is None:
                return items
            return items[-session_limit:]

        return await asyncio.to_thread(_get_items_sync)

    async def add_items(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return

        def _add_items_sync() -> None:
            with self._lock:
                bucket = self._sessions.setdefault(self.session_id, [])
                bucket.extend(deepcopy(items))

        await asyncio.to_thread(_add_items_sync)

    async def pop_item(self) -> dict[str, Any] | None:
        def _pop_item_sync() -> dict[str, Any] | None:
            with self._lock:
                bucket = self._sessions.get(self.session_id) or []
                if not bucket:
                    return None
                item = deepcopy(bucket[-1])
                del bucket[-1]
                if not bucket:
                    self._sessions.pop(self.session_id, None)
                else:
                    self._sessions[self.session_id] = bucket
                return item

        return await asyncio.to_thread(_pop_item_sync)

    async def clear_session(self) -> None:
        def _clear_session_sync() -> None:
            with self._lock:
                self._sessions.pop(self.session_id, None)

        await asyncio.to_thread(_clear_session_sync)


class InMemoryDiscoveryAgentSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._session_settings = _session_settings()

    def get_session(self, session_id: str) -> InMemoryDiscoveryAgentSession:
        return InMemoryDiscoveryAgentSession(
            session_id,
            sessions=self._sessions,
            lock=self._lock,
            session_settings=self._session_settings,
        )


class MySQLDiscoveryAgentSession:
    def __init__(self, session_id: str, *, dsn: str, session_settings: Any | None) -> None:
        self.session_id = session_id
        self.session_settings = session_settings
        self._dsn = str(dsn or "").strip()
        if not self._dsn:
            raise ValueError("discovery MySQL DSN is required for agent session memory")

    async def get_items(self, limit: int | None = None) -> list[dict[str, Any]]:
        session_limit = _resolve_session_limit(limit, self.session_settings)

        def _get_items_sync() -> list[dict[str, Any]]:
            conn = connect_db(self._dsn)
            try:
                if session_limit is None:
                    rows = conn.execute(
                        """
                        SELECT item_json
                        FROM discovery_agent_session_memory_items
                        WHERE session_id = ?
                        ORDER BY item_id ASC
                        """,
                        (self.session_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT item_json
                        FROM discovery_agent_session_memory_items
                        WHERE session_id = ?
                        ORDER BY item_id DESC
                        LIMIT ?
                        """,
                        (self.session_id, session_limit),
                    ).fetchall()
                    rows = list(reversed(rows))
            finally:
                conn.close()

            items: list[dict[str, Any]] = []
            for row in rows:
                item = json_loads(str(row.get("item_json") or "null"), None)
                if isinstance(item, dict):
                    items.append(item)
            return items

        return await asyncio.to_thread(_get_items_sync)

    async def add_items(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return

        def _add_items_sync() -> None:
            conn = connect_db(self._dsn)
            try:
                conn.execute(
                    """
                    INSERT INTO discovery_agent_session_memory_items (
                        session_id, item_json, created_at
                    ) VALUES (?, ?, NOW())
                    """,
                    (self.session_id, json_dumps(items[0])),
                )
                for item in items[1:]:
                    conn.execute(
                        """
                        INSERT INTO discovery_agent_session_memory_items (
                            session_id, item_json, created_at
                        ) VALUES (?, ?, NOW())
                        """,
                        (self.session_id, json_dumps(item)),
                    )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_add_items_sync)

    async def pop_item(self) -> dict[str, Any] | None:
        def _pop_item_sync() -> dict[str, Any] | None:
            conn = connect_db(self._dsn)
            try:
                row = conn.execute(
                    """
                    SELECT item_id, item_json
                    FROM discovery_agent_session_memory_items
                    WHERE session_id = ?
                    ORDER BY item_id DESC
                    LIMIT 1
                    """,
                    (self.session_id,),
                ).fetchone()
                if row is None:
                    return None
                conn.execute(
                    """
                    DELETE FROM discovery_agent_session_memory_items
                    WHERE item_id = ?
                    """,
                    (int(row["item_id"]),),
                )
                conn.commit()
                item = json_loads(str(row.get("item_json") or "null"), None)
                return item if isinstance(item, dict) else None
            finally:
                conn.close()

        return await asyncio.to_thread(_pop_item_sync)

    async def clear_session(self) -> None:
        def _clear_session_sync() -> None:
            conn = connect_db(self._dsn)
            try:
                conn.execute(
                    """
                    DELETE FROM discovery_agent_session_memory_items
                    WHERE session_id = ?
                    """,
                    (self.session_id,),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_clear_session_sync)


class MySQLDiscoveryAgentSessionStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = str(dsn or "").strip()
        if not self._dsn:
            raise ValueError("discovery MySQL DSN is required")
        self._session_settings = _session_settings()

    def get_session(self, session_id: str) -> MySQLDiscoveryAgentSession:
        return MySQLDiscoveryAgentSession(
            session_id,
            dsn=self._dsn,
            session_settings=self._session_settings,
        )


def create_default_discovery_agent_session_store(
    *,
    discovery_dsn: str | None = None,
) -> InMemoryDiscoveryAgentSessionStore | MySQLDiscoveryAgentSessionStore | None:
    if not _session_memory_enabled():
        return None
    resolved_dsn = str(discovery_dsn or os.environ.get("PARTNER_DISCOVERY_DB") or "").strip()
    if resolved_dsn:
        return MySQLDiscoveryAgentSessionStore(resolved_dsn)
    return InMemoryDiscoveryAgentSessionStore()


__all__ = [
    "InMemoryDiscoveryAgentSession",
    "InMemoryDiscoveryAgentSessionStore",
    "MySQLDiscoveryAgentSession",
    "MySQLDiscoveryAgentSessionStore",
    "build_visual_context_runtime_summary",
    "build_visual_memory_runtime_summary",
    "create_default_discovery_agent_session_store",
    "normalize_visual_memory",
    "normalize_visual_context",
    "visual_memory_to_legacy_context",
]
