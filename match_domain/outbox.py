"""Transactional outbox rows + optional in-process event dispatch."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .model import MatchEvent

PUBLISH_STATUS_PENDING = "pending"
PUBLISH_STATUS_PUBLISHED = "published"


def dump_canonical_event_json(event: MatchEvent) -> str:
    return json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True)


def append_outbox_pending(
    conn: Any,
    *,
    event: MatchEvent,
    source_row_table: str,
    source_row_id: int | None,
    created_at_str: str,
) -> None:
    """Insert a pending outbox row (same DB transaction as the source ledger write)."""

    # SQL uses ``?`` placeholders — must go through MySQLCompatConnection (maps to %s).
    conn.execute(
        """
        INSERT IGNORE INTO outbox_events (
          canonical_event_id,
          aggregate_type,
          aggregate_id,
          event_type,
          source_service,
          canonical_event_json,
          source_row_table,
          source_row_id,
          publish_status,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            event.source_service,
            dump_canonical_event_json(event),
            source_row_table,
            source_row_id,
            PUBLISH_STATUS_PENDING,
            created_at_str,
        ),
    )


class SyncEventBus:
    """Process-local publish/subscribe; use with outbox for synchronous side effects in tests or single-process apps."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: list[Callable[[MatchEvent], None]] = []

    def subscribe(self, handler: Callable[[MatchEvent], None]) -> None:
        self._handlers.append(handler)

    def publish(self, event: MatchEvent) -> None:
        for handler in self._handlers:
            handler(event)

    def clear(self) -> None:
        self._handlers.clear()


__all__ = [
    "PUBLISH_STATUS_PENDING",
    "PUBLISH_STATUS_PUBLISHED",
    "SyncEventBus",
    "append_outbox_pending",
    "dump_canonical_event_json",
]
