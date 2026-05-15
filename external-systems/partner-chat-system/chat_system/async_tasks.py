"""Persisted async jobs for heavy chat maintenance operations."""

from __future__ import annotations

from typing import Any

from her_external_systems import AsyncJobHandler, build_external_async_job_helpers
from her_time_utils import parse_dt_trimmed

from .maintenance import run_chat_maintenance


JOB_RUN_CHAT_MAINTENANCE = "chat.run_maintenance"


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
    job_now = parse_dt_trimmed(payload.get("now"))
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

(
    enqueue_chat_async_job,
    get_chat_async_job,
    list_chat_async_jobs,
    summarize_chat_async_jobs,
    summarize_chat_async_jobs_by_type,
    run_chat_async_job_worker,
) = build_external_async_job_helpers(
    handlers=_HANDLERS,
    subsystem_name="chat",
    system="chat",
    default_worker_name="chat-async-worker",
)
enqueue_chat_async_job.__name__ = "enqueue_chat_async_job"
get_chat_async_job.__name__ = "get_chat_async_job"
list_chat_async_jobs.__name__ = "list_chat_async_jobs"
summarize_chat_async_jobs.__name__ = "summarize_chat_async_jobs"
summarize_chat_async_jobs_by_type.__name__ = "summarize_chat_async_jobs_by_type"
run_chat_async_job_worker.__name__ = "run_chat_async_job_worker"


__all__ = [
    "JOB_RUN_CHAT_MAINTENANCE",
    "enqueue_chat_async_job",
    "get_chat_async_job",
    "list_chat_async_jobs",
    "run_chat_async_job_worker",
    "summarize_chat_async_jobs",
    "summarize_chat_async_jobs_by_type",
]
