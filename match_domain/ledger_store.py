"""Append-only ledger store protocol and in-memory implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .ledger import sort_ledger_events
from .model import MatchEvent


@runtime_checkable
class LedgerStore(Protocol):
    """Physical store for ordered MatchEvent streams keyed by aggregate."""

    def append(self, event: MatchEvent) -> None:
        """Persist one event (idempotent consumers should dedupe on idempotency_key)."""

    def load_stream(self, *, aggregate_type: str, aggregate_id: str) -> list[MatchEvent]:
        """Return all events for the aggregate in append order."""


@dataclass
class InMemoryLedgerStore:
    """Process-local ledger for tests and single-process tooling."""

    _streams: dict[tuple[str, str], list[MatchEvent]] = field(default_factory=dict)

    def append(self, event: MatchEvent) -> None:
        key = (event.aggregate_type, event.aggregate_id)
        self._streams.setdefault(key, []).append(event)

    def load_stream(self, *, aggregate_type: str, aggregate_id: str) -> list[MatchEvent]:
        raw = self._streams.get((aggregate_type, aggregate_id), [])
        return sort_ledger_events(raw)

    def clear(self) -> None:
        self._streams.clear()


__all__ = ["InMemoryLedgerStore", "LedgerStore"]
