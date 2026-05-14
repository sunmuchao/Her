"""Persisted async jobs for heavy chat maintenance operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from async_jobs import (
    AsyncJobHandler,
    enqueue_async_job,
    get_async_job,
    list_async_jobs,
    run_async_job_worker,
    summarize_async_jobs,
    summarize_async_jobs_by_type,
)
from observability.health import emit_async_job_gauges

from .maintenance import run_chat_maintenance


JOB_RUN_CHAT_MAINTENANCE = "chat.run_maintenance"


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    return datetime.fromisoformat(str(value)).replace(microsecond=0)


def _normalize_flush_outbox(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def _run_maintenance(conn, payload: dict[str, Any]) -> dict[str, Any]:
    kwargs = {
        "persona_limit": int(payload.get("persona_limit", 20)),
        "summary_max_threads": int(payload.get("summary_max_threads", 30)),
        "flush_outbox": _normalize_flush_outbox(payload.get("flush_outbox")),
    }
    job_now = _parse_dt(payload.get("now"))
    if job_now is not None:
        kwargs["now"] = job_now
    return run_chat_maintenance(conn, **kwargs)


_HANDLERS: dict[str, AsyncJobHandler] = {
    JOB_RUN_CHAT_MAINTENANCE: AsyncJobHandler(
        job_type=JOB_RUN_CHAT_MAINTENANCE,
        execute_fn=_run_maintenance,
        max_attempts=3,
    ),
}


def enqueue_chat_async_job(
    conn,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    handler = _HANDLERS.get(job_type)
    if handler is None:
        raise ValueError(f"unsupported chat async job type: {job_type}")
    return enqueue_async_job(
        conn,
        job_type=job_type,
        payload=payload,
        created_by=created_by,
        trace_id=trace_id,
        max_attempts=handler.max_attempts,
        now=now,
    )


def get_chat_async_job(conn, job_id: str) -> dict[str, Any] | None:
    return get_async_job(conn, job_id)


def list_chat_async_jobs(
    conn,
    *,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_async_jobs(conn, statuses=statuses, limit=limit)


def summarize_chat_async_jobs(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, Any]:
    return summarize_async_jobs(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)


def summarize_chat_async_jobs_by_type(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return summarize_async_jobs_by_type(conn, now=now, claim_timeout_seconds=claim_timeout_seconds, limit=limit)


def run_chat_async_job_worker(
    conn,
    *,
    limit: int = 10,
    retry_delay_seconds: int = 15,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int = 300,
    claim_timeout_seconds: int = 300,
    worker_name: str = "chat-async-worker",
    now: datetime | None = None,
) -> dict[str, Any]:
    out = run_async_job_worker(
        conn,
        handlers=_HANDLERS,
        limit=limit,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
        claim_timeout_seconds=claim_timeout_seconds,
        worker_name=worker_name,
        now=now,
    )
    out["summary"] = emit_async_job_gauges(
        conn,
        system="chat",
        now=(now or datetime.now()).replace(microsecond=0),
        claim_timeout_seconds=claim_timeout_seconds,
    )
    return out


__all__ = [
    "JOB_RUN_CHAT_MAINTENANCE",
    "enqueue_chat_async_job",
    "get_chat_async_job",
    "list_chat_async_jobs",
    "run_chat_async_job_worker",
    "summarize_chat_async_jobs",
    "summarize_chat_async_jobs_by_type",
]
