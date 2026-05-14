"""Worker helpers for chat outbox consumption and retry operations."""

from __future__ import annotations

import os
import socket
import time
from datetime import datetime
from typing import Any

from .outbox_admin import summarize_outbox
from .outbox_consumer import consume_chat_outbox_batch


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def _default_worker_name() -> str:
    configured = str(os.environ.get("HER_CHAT_OUTBOX_WORKER_NAME") or "").strip()
    if configured:
        return configured
    return f"chat-outbox@{socket.gethostname()}:{os.getpid()}"


def resolve_outbox_consume_config() -> dict[str, Any]:
    return {
        "limit": max(1, _env_int("HER_CHAT_OUTBOX_BATCH_LIMIT", 200)),
        "max_batches": max(1, _env_int("HER_CHAT_OUTBOX_MAX_BATCHES", 1)),
        "retry_delay_seconds": max(1, _env_int("HER_CHAT_OUTBOX_RETRY_DELAY_SECONDS", 60)),
        "retry_backoff_multiplier": max(1, _env_int("HER_CHAT_OUTBOX_RETRY_BACKOFF_MULTIPLIER", 2)),
        "retry_max_delay_seconds": max(1, _env_int("HER_CHAT_OUTBOX_RETRY_MAX_DELAY_SECONDS", 600)),
        "max_attempts": max(1, _env_int("HER_CHAT_OUTBOX_MAX_ATTEMPTS", 3)),
        "claim_timeout_seconds": max(1, _env_int("HER_CHAT_OUTBOX_CLAIM_TIMEOUT_SECONDS", 300)),
        "poll_interval_seconds": max(1, _env_int("HER_CHAT_OUTBOX_POLL_INTERVAL_SECONDS", 15)),
        "max_idle_polls": max(1, _env_int("HER_CHAT_OUTBOX_MAX_IDLE_POLLS", 3)),
        "worker_name": _default_worker_name(),
    }


def run_chat_outbox_worker(
    conn,
    *,
    limit: int | None = None,
    max_batches: int | None = None,
    retry_delay_seconds: int | None = None,
    retry_backoff_multiplier: int | None = None,
    retry_max_delay_seconds: int | None = None,
    max_attempts: int | None = None,
    claim_timeout_seconds: int | None = None,
    worker_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = resolve_outbox_consume_config()
    consume_limit = max(1, int(limit or config["limit"]))
    batch_cap = max(1, int(max_batches or config["max_batches"]))
    consume_retry_delay = max(1, int(retry_delay_seconds or config["retry_delay_seconds"]))
    consume_backoff_multiplier = max(
        1,
        int(retry_backoff_multiplier or config["retry_backoff_multiplier"]),
    )
    consume_retry_max_delay = max(
        1,
        int(retry_max_delay_seconds or config["retry_max_delay_seconds"]),
    )
    consume_max_attempts = max(1, int(max_attempts or config["max_attempts"]))
    consume_claim_timeout = max(1, int(claim_timeout_seconds or config["claim_timeout_seconds"]))
    resolved_worker_name = str(worker_name or config["worker_name"]).strip() or _default_worker_name()

    before = summarize_outbox(conn, now=now, claim_timeout_seconds=consume_claim_timeout)
    batches: list[dict[str, Any]] = []
    totals = {
        "claimed": 0,
        "examined": 0,
        "marked_published": 0,
        "agent_tasks_enqueued": 0,
        "retry_scheduled": 0,
        "failed": 0,
        "stale_recovered": 0,
        "error_count": 0,
    }
    for _ in range(batch_cap):
        batch = consume_chat_outbox_batch(
            conn,
            limit=consume_limit,
            now=now,
            retry_delay_seconds=consume_retry_delay,
            retry_backoff_multiplier=consume_backoff_multiplier,
            retry_max_delay_seconds=consume_retry_max_delay,
            max_attempts=consume_max_attempts,
            claim_timeout_seconds=consume_claim_timeout,
            worker_name=resolved_worker_name,
        )
        batches.append(batch)
        totals["claimed"] += int(batch.get("claimed") or 0)
        totals["examined"] += int(batch.get("examined") or 0)
        totals["marked_published"] += int(batch.get("marked_published") or 0)
        totals["agent_tasks_enqueued"] += int(batch.get("agent_tasks_enqueued") or 0)
        totals["retry_scheduled"] += int(batch.get("retry_scheduled") or 0)
        totals["failed"] += int(batch.get("failed") or 0)
        totals["stale_recovered"] += int(batch.get("stale_recovered") or 0)
        totals["error_count"] += len(list(batch.get("errors") or []))
        if int(batch.get("examined") or 0) <= 0:
            break
    after = summarize_outbox(conn, now=now, claim_timeout_seconds=consume_claim_timeout)
    return {
        "config": {
            "limit": consume_limit,
            "worker_name": resolved_worker_name,
            "retry_delay_seconds": consume_retry_delay,
            "retry_backoff_multiplier": consume_backoff_multiplier,
            "retry_max_delay_seconds": consume_retry_max_delay,
            "max_attempts": consume_max_attempts,
            "claim_timeout_seconds": consume_claim_timeout,
            "max_batches": batch_cap,
        },
        "summary_before": before,
        "summary_after": after,
        "totals": totals,
        "batches": batches,
    }


def serve_chat_outbox_worker(
    conn,
    *,
    limit: int | None = None,
    max_batches_per_cycle: int | None = None,
    retry_delay_seconds: int | None = None,
    retry_backoff_multiplier: int | None = None,
    retry_max_delay_seconds: int | None = None,
    max_attempts: int | None = None,
    claim_timeout_seconds: int | None = None,
    poll_interval_seconds: int | None = None,
    max_idle_polls: int | None = None,
    max_runtime_seconds: int | None = None,
    worker_name: str | None = None,
    clock_fn=None,
    sleep_fn=None,
) -> dict[str, Any]:
    config = resolve_outbox_consume_config()
    cycle_batch_cap = max(1, int(max_batches_per_cycle or config["max_batches"]))
    poll_interval = max(1, int(poll_interval_seconds or config["poll_interval_seconds"]))
    idle_cap = max(1, int(max_idle_polls or config["max_idle_polls"]))
    runtime_cap = None if max_runtime_seconds is None else max(1, int(max_runtime_seconds))
    now_fn = clock_fn or datetime.now
    sleeper = sleep_fn or time.sleep
    resolved_worker_name = str(worker_name or config["worker_name"]).strip() or _default_worker_name()

    started_at = now_fn()
    cycles: list[dict[str, Any]] = []
    totals = {
        "claimed": 0,
        "examined": 0,
        "marked_published": 0,
        "agent_tasks_enqueued": 0,
        "retry_scheduled": 0,
        "failed": 0,
        "stale_recovered": 0,
        "error_count": 0,
    }
    idle_polls = 0
    slept_seconds = 0
    stopped_reason = "idle"

    while True:
        cycle_now = now_fn()
        cycle = run_chat_outbox_worker(
            conn,
            limit=limit,
            max_batches=cycle_batch_cap,
            retry_delay_seconds=retry_delay_seconds,
            retry_backoff_multiplier=retry_backoff_multiplier,
            retry_max_delay_seconds=retry_max_delay_seconds,
            max_attempts=max_attempts,
            claim_timeout_seconds=claim_timeout_seconds,
            worker_name=resolved_worker_name,
            now=cycle_now,
        )
        cycles.append(cycle)
        cycle_totals = dict(cycle.get("totals") or {})
        for key in totals:
            totals[key] += int(cycle_totals.get(key) or 0)

        busy = any(
            int(cycle_totals.get(key) or 0) > 0
            for key in ("claimed", "marked_published", "retry_scheduled", "failed", "stale_recovered")
        )
        if busy:
            idle_polls = 0
        else:
            idle_polls += 1

        if runtime_cap is not None and (now_fn() - started_at).total_seconds() >= runtime_cap:
            stopped_reason = "max_runtime_reached"
            break
        if idle_polls >= idle_cap:
            stopped_reason = "idle"
            break
        sleeper(poll_interval)
        slept_seconds += poll_interval

    return {
        "worker_name": resolved_worker_name,
        "cycles_run": len(cycles),
        "idle_polls": idle_polls,
        "slept_seconds": slept_seconds,
        "poll_interval_seconds": poll_interval,
        "max_idle_polls": idle_cap,
        "max_runtime_seconds": runtime_cap,
        "stopped_reason": stopped_reason,
        "totals": totals,
        "cycles": cycles,
    }


__all__ = [
    "resolve_outbox_consume_config",
    "run_chat_outbox_worker",
    "serve_chat_outbox_worker",
]
