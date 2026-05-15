"""Persisted async jobs for heavy matchmaking operations."""

from __future__ import annotations

from typing import Any

from her_external_systems import AsyncJobHandler, build_external_async_job_helpers

from .service import build_mutual_pairs, close_stale_cases, open_match_cases, parse_dt, refresh_active_pool


JOB_REFRESH_ACTIVE_POOL = "matchmaking.refresh_active_pool"
JOB_BUILD_MUTUAL_PAIRS = "matchmaking.build_mutual_pairs"
JOB_OPEN_MATCH_CASES = "matchmaking.open_match_cases"
JOB_CLOSE_STALE_CASES = "matchmaking.close_stale_cases"


def _run_refresh_active_pool(conn, payload: dict[str, Any]) -> list[dict[str, Any]]:
    return refresh_active_pool(
        conn,
        now=parse_dt(payload.get("now")),
        member_ids=payload.get("member_ids"),
    )


def _run_build_mutual_pairs(conn, payload: dict[str, Any]) -> list[dict[str, Any]]:
    return build_mutual_pairs(
        conn,
        now=parse_dt(payload.get("now")),
    )


def _run_open_match_cases(conn, payload: dict[str, Any]) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if payload.get("case_expires_hours") is not None:
        kwargs["case_expires_hours"] = int(payload["case_expires_hours"])
    job_now = parse_dt(payload.get("now"))
    if job_now is not None:
        kwargs["now"] = job_now
    return open_match_cases(conn, **kwargs)


def _run_close_stale_cases(conn, payload: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if payload.get("timeout_cooling_days") is not None:
        kwargs["timeout_cooling_days"] = int(payload["timeout_cooling_days"])
    job_now = parse_dt(payload.get("now"))
    if job_now is not None:
        kwargs["now"] = job_now
    return close_stale_cases(conn, **kwargs)


_HANDLERS: dict[str, AsyncJobHandler] = {
    JOB_REFRESH_ACTIVE_POOL: AsyncJobHandler(
        job_type=JOB_REFRESH_ACTIVE_POOL,
        execute_fn=_run_refresh_active_pool,
        max_attempts=3,
    ),
    JOB_BUILD_MUTUAL_PAIRS: AsyncJobHandler(
        job_type=JOB_BUILD_MUTUAL_PAIRS,
        execute_fn=_run_build_mutual_pairs,
        max_attempts=3,
    ),
    JOB_OPEN_MATCH_CASES: AsyncJobHandler(
        job_type=JOB_OPEN_MATCH_CASES,
        execute_fn=_run_open_match_cases,
        max_attempts=3,
    ),
    JOB_CLOSE_STALE_CASES: AsyncJobHandler(
        job_type=JOB_CLOSE_STALE_CASES,
        execute_fn=_run_close_stale_cases,
        max_attempts=3,
    ),
}

(
    enqueue_matchmaking_async_job,
    get_matchmaking_async_job,
    list_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs_by_type,
    run_matchmaking_async_job_worker,
) = build_external_async_job_helpers(
    handlers=_HANDLERS,
    subsystem_name="matchmaking",
    system="matchmaking",
    default_worker_name="matchmaking-async-worker",
)
enqueue_matchmaking_async_job.__name__ = "enqueue_matchmaking_async_job"
get_matchmaking_async_job.__name__ = "get_matchmaking_async_job"
list_matchmaking_async_jobs.__name__ = "list_matchmaking_async_jobs"
summarize_matchmaking_async_jobs.__name__ = "summarize_matchmaking_async_jobs"
summarize_matchmaking_async_jobs_by_type.__name__ = "summarize_matchmaking_async_jobs_by_type"
run_matchmaking_async_job_worker.__name__ = "run_matchmaking_async_job_worker"


__all__ = [
    "JOB_BUILD_MUTUAL_PAIRS",
    "JOB_CLOSE_STALE_CASES",
    "JOB_OPEN_MATCH_CASES",
    "JOB_REFRESH_ACTIVE_POOL",
    "enqueue_matchmaking_async_job",
    "get_matchmaking_async_job",
    "list_matchmaking_async_jobs",
    "run_matchmaking_async_job_worker",
    "summarize_matchmaking_async_jobs",
    "summarize_matchmaking_async_jobs_by_type",
]
