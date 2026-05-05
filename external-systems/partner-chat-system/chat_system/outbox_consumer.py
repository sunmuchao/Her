"""Consume pending chat outbox rows: emit pipeline funnel + mark published."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from match_domain.trace_context import get_trace_id
from observability import CHAT_FUNNEL_OUTBOX_DISPATCHED, funnel_stage

from .outbox_admin import list_pending_outbox, mark_outbox_rows_published


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def consume_chat_outbox_batch(conn, *, limit: int = 100, now=None) -> dict[str, Any]:
    rows = list_pending_outbox(conn, limit=limit)
    ids: list[int] = []
    ts = _ts(now)
    for r in rows:
        oid = int(r["outbox_id"])
        ids.append(oid)
        payload: dict[str, Any] = {}
        raw = r.get("canonical_event_json")
        if raw:
            try:
                payload = json.loads(str(raw))
            except json.JSONDecodeError:
                payload = {}
        event_type = payload.get("event_type") or r.get("event_type")
        case_id = None
        if isinstance(payload.get("payload"), dict):
            case_id = payload["payload"].get("case_id")
        funnel_stage(
            system="chat",
            stage=CHAT_FUNNEL_OUTBOX_DISPATCHED,
            trace_id=get_trace_id(),
            outbox_id=oid,
            event_type=event_type,
            aggregate_id=r.get("aggregate_id"),
            case_id=case_id,
            source_row_table=r.get("source_row_table"),
            source_row_id=r.get("source_row_id"),
        )
    marked = mark_outbox_rows_published(conn, ids, now=ts)
    conn.commit()
    return {"examined": len(rows), "marked_published": marked}


__all__ = ["consume_chat_outbox_batch"]
