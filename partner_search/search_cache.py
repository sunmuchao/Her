"""In-process LRU cache for hot partner_search criteria (§10.3 performance)."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Mapping

from her_env import env_int

from .search_snapshot_store import (
    get_persisted_search_run,
    store_persisted_search_run,
)


def _cache_enabled() -> bool:
    return env_int("PARTNER_SEARCH_CACHE_TTL_SECONDS", 0) > 0


def _ttl_seconds() -> int:
    return max(0, env_int("PARTNER_SEARCH_CACHE_TTL_SECONDS", 0))


def _max_entries() -> int:
    return max(1, env_int("PARTNER_SEARCH_CACHE_MAX_ENTRIES", 256))


def _criteria_fingerprint(
    *,
    criteria: Mapping[str, Any],
    self_id: int | None,
    limit: int,
    source: str | None,
) -> str:
    payload = {
        "criteria": dict(criteria or {}),
        "self_id": self_id,
        "limit": int(limit),
        "source": str(source or ""),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def criteria_cache_key(
    *,
    criteria: Mapping[str, Any],
    self_id: int | None,
    limit: int,
    source: str | None,
) -> str:
    return _criteria_fingerprint(
        criteria=criteria,
        self_id=self_id,
        limit=limit,
        source=source,
    )


class _SearchRunCache:
    def __init__(self) -> None:
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def get(self, key: str) -> dict[str, Any] | None:
        if not _cache_enabled():
            return None
        item = self._entries.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return dict(value)

    def set(self, key: str, value: Mapping[str, Any]) -> None:
        if not _cache_enabled():
            return
        ttl = _ttl_seconds()
        self._entries[key] = (time.monotonic() + ttl, dict(value))
        self._entries.move_to_end(key)
        while len(self._entries) > _max_entries():
            self._entries.popitem(last=False)


_CACHE = _SearchRunCache()


def get_cached_search_run(
    *,
    criteria: Mapping[str, Any],
    self_id: int | None,
    limit: int,
    source: str | None,
) -> dict[str, Any] | None:
    key = criteria_cache_key(
        criteria=criteria,
        self_id=self_id,
        limit=limit,
        source=source,
    )
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    persisted = get_persisted_search_run(key)
    if persisted is not None:
        _CACHE.set(key, persisted)
    return persisted


def store_cached_search_run(
    *,
    criteria: Mapping[str, Any],
    self_id: int | None,
    limit: int,
    source: str | None,
    search_run: Mapping[str, Any],
) -> None:
    key = criteria_cache_key(
        criteria=criteria,
        self_id=self_id,
        limit=limit,
        source=source,
    )
    _CACHE.set(key, search_run)
    store_persisted_search_run(key, search_run)


def clear_search_cache() -> None:
    _CACHE._entries.clear()


__all__ = [
    "clear_search_cache",
    "criteria_cache_key",
    "get_cached_search_run",
    "store_cached_search_run",
]
