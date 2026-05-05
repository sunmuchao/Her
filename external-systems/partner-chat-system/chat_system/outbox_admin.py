"""Read and mark chat DB outbox rows (``match_domain.outbox`` semantics)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from match_domain.outbox import PUBLISH_STATUS_PENDING, PUBLISH_STATUS_PUBLISHED

from .storage import row_to_dict


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def list_pending_outbox(conn, *, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    cur = conn.execute(
        """
        SELECT * FROM outbox_events
        WHERE publish_status = ?
        ORDER BY outbox_id ASC
        LIMIT ?
        """,
        (PUBLISH_STATUS_PENDING, lim),
    )
    return [dict(r) for r in cur.fetchall()]


def mark_outbox_rows_published(conn, outbox_ids: list[int], *, now=None) -> int:
    if not outbox_ids:
        return 0
    ts = _ts(now)
    placeholders = ",".join("?" * len(outbox_ids))
    res = conn.execute(
        f"""
        UPDATE outbox_events
        SET publish_status = ?, published_at = ?
        WHERE outbox_id IN ({placeholders}) AND publish_status = ?
        """,
        (PUBLISH_STATUS_PUBLISHED, ts, *outbox_ids, PUBLISH_STATUS_PENDING),
    )
    return int(res.rowcount)


def mark_pending_outbox_published_batch(conn, *, limit: int = 100, now=None) -> int:
    rows = list_pending_outbox(conn, limit=limit)
    ids = [int(r["outbox_id"]) for r in rows]
    n = mark_outbox_rows_published(conn, ids, now=now)
    conn.commit()
    return n


def get_outbox_row(conn, outbox_id: int) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM outbox_events WHERE outbox_id = ? LIMIT 1", (outbox_id,))
    return row_to_dict(cur.fetchone())


__all__ = [
    "get_outbox_row",
    "list_pending_outbox",
    "mark_outbox_rows_published",
    "mark_pending_outbox_published_batch",
]
