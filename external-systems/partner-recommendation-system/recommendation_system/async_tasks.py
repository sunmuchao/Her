"""Persisted async jobs for heavy recommendation operations."""

from __future__ import annotations

from typing import Any

from her_external_systems import AsyncJobHandler, build_external_async_job_helpers

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

(
    enqueue_recommendation_async_job,
    get_recommendation_async_job,
    list_recommendation_async_jobs,
    summarize_recommendation_async_jobs,
    summarize_recommendation_async_jobs_by_type,
    run_recommendation_async_job_worker,
) = build_external_async_job_helpers(
    handlers=_HANDLERS,
    subsystem_name="recommendation",
    system="recommendation",
    default_worker_name="recommendation-async-worker",
)
enqueue_recommendation_async_job.__name__ = "enqueue_recommendation_async_job"
get_recommendation_async_job.__name__ = "get_recommendation_async_job"
list_recommendation_async_jobs.__name__ = "list_recommendation_async_jobs"
summarize_recommendation_async_jobs.__name__ = "summarize_recommendation_async_jobs"
summarize_recommendation_async_jobs_by_type.__name__ = "summarize_recommendation_async_jobs_by_type"
run_recommendation_async_job_worker.__name__ = "run_recommendation_async_job_worker"


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
