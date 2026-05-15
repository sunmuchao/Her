"""Persisted async jobs for heavy matchmaking operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from async_jobs import (
    get_async_job,
    list_async_jobs,
    summarize_async_jobs,
    summarize_async_jobs_by_type,
)
from her_external_systems import AsyncJobHandler, enqueue_external_async_job, run_external_async_job_worker

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


def enqueue_matchmaking_async_job(
    conn,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return enqueue_external_async_job(
        conn,
        handlers=_HANDLERS,
        subsystem_name="matchmaking",
        job_type=job_type,
        payload=payload,
        created_by=created_by,
        trace_id=trace_id,
        now=now,
    )


def get_matchmaking_async_job(conn, job_id: str) -> dict[str, Any] | None:
    return get_async_job(conn, job_id)


def list_matchmaking_async_jobs(
    conn,
    *,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_async_jobs(conn, statuses=statuses, limit=limit)


def summarize_matchmaking_async_jobs(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, Any]:
    return summarize_async_jobs(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)


def summarize_matchmaking_async_jobs_by_type(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return summarize_async_jobs_by_type(conn, now=now, claim_timeout_seconds=claim_timeout_seconds, limit=limit)


def run_matchmaking_async_job_worker(
    conn,
    *,
    limit: int = 10,
    retry_delay_seconds: int = 15,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int = 300,
    claim_timeout_seconds: int = 300,
    worker_name: str = "matchmaking-async-worker",
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_external_async_job_worker(
        conn,
        handlers=_HANDLERS,
        system="matchmaking",
        limit=limit,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
        claim_timeout_seconds=claim_timeout_seconds,
        worker_name=worker_name,
        now=now,
    )


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
