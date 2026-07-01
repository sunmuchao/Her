"""Batch operations: outbox delivery, persona jobs, and summaries."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .assistant_orchestrator import process_pending_agent_tasks
from .assistant_feature_flags import is_match_chat_ai_assistant_enabled
from .assistant_sessions import (
    close_idle_agent_sessions,
    enqueue_due_opening_probe_tasks,
    enqueue_due_post_chat_followup_tasks,
    enqueue_due_silence_probe_tasks,
)
from .outbox import mark_pending_outbox_published_batch
from .outbox_consumer import consume_chat_outbox_batch
from .outbox import resolve_outbox_consume_config
from .persona_jobs import process_pending_persona_jobs
from .summaries import refresh_stale_thread_summaries


def run_chat_maintenance(
    conn,
    *,
    persona_limit: int = 20,
    assistant_limit: int = 10,
    assistant_opening_seconds: int = 30,
    assistant_silence_seconds: int = 45,
    assistant_post_chat_seconds: int = 720,
    assistant_idle_seconds: int = 10800,
    flush_outbox: bool | None = None,
    summary_max_threads: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Outbox delivery or mark-published, persona jobs, and thread summaries."""

    flush = flush_outbox
    if flush is None:
        flush = os.environ.get("HER_SCHED_CHAT_FLUSH_OUTBOX", "").lower() in ("1", "true", "yes")
    use_consume = os.environ.get("HER_SCHED_CHAT_OUTBOX_CONSUME", "1").lower() in ("1", "true", "yes")
    out: dict[str, Any] = {
        "outbox_marked_published": 0,
        "outbox_consume": {},
        "assistant_triggers": {},
        "assistant": {},
        "agent_sessions_closed": 0,
        "persona": {},
        "summaries": {},
    }
    if flush:
        outbox_config = resolve_outbox_consume_config()
        if use_consume:
            oc = consume_chat_outbox_batch(
                conn,
                limit=outbox_config["limit"],
                now=now,
                retry_delay_seconds=outbox_config["retry_delay_seconds"],
                retry_backoff_multiplier=outbox_config["retry_backoff_multiplier"],
                retry_max_delay_seconds=outbox_config["retry_max_delay_seconds"],
                max_attempts=outbox_config["max_attempts"],
                claim_timeout_seconds=outbox_config["claim_timeout_seconds"],
                worker_name=outbox_config["worker_name"],
            )
            out["outbox_consume"] = oc
            out["outbox_marked_published"] = int(oc.get("marked_published", 0))
        else:
            out["outbox_marked_published"] = mark_pending_outbox_published_batch(
                conn,
                limit=outbox_config["limit"],
                now=now,
            )
    if (
        assistant_limit > 0
        and is_match_chat_ai_assistant_enabled()
        and os.environ.get("HER_CHAT_MAINTENANCE_SKIP_ASSISTANT", "").lower() not in ("1", "true", "yes")
    ):
        trigger_out: dict[str, Any] = {
            "opening_probe": {"skipped": True},
            "silence_probe": {"skipped": True},
            "post_chat_followup": {"skipped": True},
            "enqueued": 0,
            "task_refs": [],
        }
        if assistant_opening_seconds > 0:
            trigger_out["opening_probe"] = enqueue_due_opening_probe_tasks(
                conn,
                limit=assistant_limit,
                opening_seconds=assistant_opening_seconds,
                now=now,
            )
            trigger_out["enqueued"] += int(trigger_out["opening_probe"].get("enqueued", 0))
            trigger_out["task_refs"].extend(list(trigger_out["opening_probe"].get("task_refs") or []))
            conn.commit()
        if assistant_silence_seconds > 0:
            trigger_out["silence_probe"] = enqueue_due_silence_probe_tasks(
                conn,
                limit=assistant_limit,
                silence_seconds=assistant_silence_seconds,
                now=now,
            )
            trigger_out["enqueued"] += int(trigger_out["silence_probe"].get("enqueued", 0))
            trigger_out["task_refs"].extend(list(trigger_out["silence_probe"].get("task_refs") or []))
            conn.commit()
        if assistant_post_chat_seconds > 0:
            trigger_out["post_chat_followup"] = enqueue_due_post_chat_followup_tasks(
                conn,
                limit=assistant_limit,
                followup_seconds=assistant_post_chat_seconds,
                now=now,
            )
            trigger_out["enqueued"] += int(trigger_out["post_chat_followup"].get("enqueued", 0))
            trigger_out["task_refs"].extend(list(trigger_out["post_chat_followup"].get("task_refs") or []))
            conn.commit()
        out["assistant_triggers"] = trigger_out
        out["assistant"] = process_pending_agent_tasks(conn, limit=assistant_limit, now=now)
    else:
        out["assistant_triggers"] = {"skipped": True, "disabled": not is_match_chat_ai_assistant_enabled()}
        out["assistant"] = {"skipped": True, "disabled": not is_match_chat_ai_assistant_enabled()}
    if assistant_idle_seconds > 0:
        out["agent_sessions_closed"] = close_idle_agent_sessions(
            conn,
            idle_seconds=assistant_idle_seconds,
            now=now,
        )
        conn.commit()
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
