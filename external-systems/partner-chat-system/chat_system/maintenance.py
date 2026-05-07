"""Batch operations: outbox flush stub + persona job processor."""

from __future__ import annotations

import os
from typing import Any

from .coaching_jobs import process_pending_coaching_entry_jobs
from .outbox_admin import mark_pending_outbox_published_batch
from .outbox_consumer import consume_chat_outbox_batch
from .persona_jobs import process_pending_persona_jobs
from .summaries import refresh_stale_thread_summaries


def run_chat_maintenance(
    conn,
    *,
    coaching_limit: int = 20,
    persona_limit: int = 20,
    flush_outbox: bool | None = None,
    summary_max_threads: int = 30,
) -> dict[str, Any]:
    """Outbox consume (funnel + published) or silent mark; persona jobs; thread summaries."""

    flush = flush_outbox
    if flush is None:
        flush = os.environ.get("HER_SCHED_CHAT_FLUSH_OUTBOX", "").lower() in ("1", "true", "yes")
    use_consume = os.environ.get("HER_SCHED_CHAT_OUTBOX_CONSUME", "1").lower() in ("1", "true", "yes")
    out: dict[str, Any] = {
        "outbox_marked_published": 0,
        "outbox_consume": {},
        "coaching": {},
        "persona": {},
        "summaries": {},
    }
    if flush:
        if use_consume:
            oc = consume_chat_outbox_batch(conn, limit=200)
            out["outbox_consume"] = oc
            out["outbox_marked_published"] = int(oc.get("marked_published", 0))
        else:
            out["outbox_marked_published"] = mark_pending_outbox_published_batch(conn, limit=200)
    if coaching_limit > 0:
        out["coaching"] = process_pending_coaching_entry_jobs(conn, limit=coaching_limit)
    else:
        out["coaching"] = {"skipped": True}
    if persona_limit > 0:
        out["persona"] = process_pending_persona_jobs(conn, limit=persona_limit)
    else:
        out["persona"] = {"skipped": True}
    if os.environ.get("HER_CHAT_MAINTENANCE_SKIP_SUMMARY", "").lower() in ("1", "true", "yes"):
        out["summaries"] = {"skipped": True}
    else:
        out["summaries"] = refresh_stale_thread_summaries(
            conn, max_threads=summary_max_threads, messages_per_thread=25
        )
    return out


__all__ = ["run_chat_maintenance"]
