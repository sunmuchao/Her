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
    "create_default_discovery_agent_session_store",
]
