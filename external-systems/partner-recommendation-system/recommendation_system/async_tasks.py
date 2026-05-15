"""Persisted async jobs for heavy recommendation operations."""

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

from .service import deliver_in_app_recommendations, parse_dt, refresh_due_subscriptions


JOB_REFRESH_DUE_SUBSCRIPTIONS = "recommendation.refresh_due_subscriptions"
JOB_DELIVER_IN_APP_RECOMMENDATIONS = "recommendation.deliver_in_app_recommendations"


def _run_refresh_due_subscriptions(conn, payload: dict[str, Any]) -> dict[str, Any]:
    return refresh_due_subscriptions(
        conn,
        now=parse_dt(payload.get("now")),
        subscription_ids=payload.get("subscription_ids"),
    )


def _run_deliver_in_app_recommendations(conn, payload: dict[str, Any]) -> dict[str, Any]:
    return deliver_in_app_recommendations(
        conn,
        now=parse_dt(payload.get("now")),
    )


_HANDLERS: dict[str, AsyncJobHandler] = {
    JOB_REFRESH_DUE_SUBSCRIPTIONS: AsyncJobHandler(
        job_type=JOB_REFRESH_DUE_SUBSCRIPTIONS,
        execute_fn=_run_refresh_due_subscriptions,
        max_attempts=3,
    ),
    JOB_DELIVER_IN_APP_RECOMMENDATIONS: AsyncJobHandler(
        job_type=JOB_DELIVER_IN_APP_RECOMMENDATIONS,
        execute_fn=_run_deliver_in_app_recommendations,
        max_attempts=3,
    ),
}


def enqueue_recommendation_async_job(
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
        subsystem_name="recommendation",
        job_type=job_type,
        payload=payload,
        created_by=created_by,
        trace_id=trace_id,
        now=now,
    )


def get_recommendation_async_job(conn, job_id: str) -> dict[str, Any] | None:
    return get_async_job(conn, job_id)


def list_recommendation_async_jobs(
    conn,
    *,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return list_async_jobs(conn, statuses=statuses, limit=limit)


def summarize_recommendation_async_jobs(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, Any]:
    return summarize_async_jobs(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)


def summarize_recommendation_async_jobs_by_type(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return summarize_async_jobs_by_type(conn, now=now, claim_timeout_seconds=claim_timeout_seconds, limit=limit)


def run_recommendation_async_job_worker(
    conn,
    *,
    limit: int = 10,
    retry_delay_seconds: int = 15,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int = 300,
    claim_timeout_seconds: int = 300,
    worker_name: str = "recommendation-async-worker",
    now: datetime | None = None,
) -> dict[str, Any]:
    return run_external_async_job_worker(
        conn,
        handlers=_HANDLERS,
        system="recommendation",
        limit=limit,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
        claim_timeout_seconds=claim_timeout_seconds,
        worker_name=worker_name,
        now=now,
    )


__all__ = [
    "JOB_DELIVER_IN_APP_RECOMMENDATIONS",
    "JOB_REFRESH_DUE_SUBSCRIPTIONS",
    "enqueue_recommendation_async_job",
    "get_recommendation_async_job",
    "list_recommendation_async_jobs",
    "run_recommendation_async_job_worker",
    "summarize_recommendation_async_jobs",
    "summarize_recommendation_async_jobs_by_type",
]
