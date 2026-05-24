from __future__ import annotations

from typing import Any, Callable

from match_domain import get_trace_id

from recommendation_system.async_tasks import (  # type: ignore[import-untyped]
    list_recommendation_async_jobs,
    summarize_recommendation_async_jobs,
    summarize_recommendation_async_jobs_by_type,
)
from matchmaking_system.async_tasks import (  # type: ignore[import-untyped]
    list_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs_by_type,
)
from chat_system.async_tasks import (  # type: ignore[import-untyped]
    list_chat_async_jobs,
    summarize_chat_async_jobs,
    summarize_chat_async_jobs_by_type,
)
from relationship_ledger import build_cross_system_funnel_dashboard, build_relation_dashboard  # type: ignore[import-untyped]

from .http_helpers import _json_safe, _query_dict, _statuses_from_query


class AsyncJobGatewayMixin:
    def _decorate_async_job(self, target: str, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job)
        payload["target"] = target
        payload["poll_path"] = f"/v1/{target}/jobs/{payload['job_id']}"
        return _json_safe(payload)

    def _decorate_async_jobs(self, target: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._decorate_async_job(target, job) for job in jobs]

    def _decorate_async_job_type_summary(self, target: str, summary: dict[str, Any]) -> dict[str, Any]:
        payload = {"target": target}
        payload.update(summary)
        return _json_safe(payload)

    def _decorate_async_job_type_summaries(self, target: str, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._decorate_async_job_type_summary(target, summary) for summary in summaries]

    def _empty_async_job_summary(self) -> dict[str, Any]:
        return {
            "total": 0,
            "backlog_open": 0,
            "due_now": 0,
            "processing_overdue": 0,
            "oldest_due_created_at": None,
            "latest_finished_at": None,
            "by_status": {
                "pending": 0,
                "processing": 0,
                "retry_pending": 0,
                "succeeded": 0,
                "failed": 0,
            },
        }

    def _job_payload(self, target: str, job: dict[str, Any]) -> dict[str, Any]:
        return {"job": self._decorate_async_job(target, job), "trace_id": get_trace_id()}

    def _job_collection_payload(self, target: str, jobs: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": _json_safe(summary),
            "jobs": self._decorate_async_jobs(target, jobs),
            "trace_id": get_trace_id(),
        }

    def _async_job_dashboard_system(
        self,
        *,
        target: str,
        with_fn: Callable[..., Any],
        list_fn: Callable[..., Any],
        summary_fn: Callable[..., Any],
        summary_by_type_fn: Callable[..., Any],
        limit: int,
    ) -> dict[str, Any]:
        try:
            summary = with_fn(summary_fn)
            job_types = with_fn(summary_by_type_fn)
            jobs = with_fn(list_fn, limit=limit)
        except Exception as exc:  # noqa: BLE001 - dashboard should degrade per subsystem
            return {
                "available": False,
                "error": str(exc),
                "summary": self._empty_async_job_summary(),
                "job_types": [],
                "recent_jobs": [],
            }
        return {
            "available": True,
            "summary": _json_safe(summary),
            "job_types": self._decorate_async_job_type_summaries(target, job_types),
            "recent_jobs": self._decorate_async_jobs(target, jobs),
        }

    def _async_job_dashboard_payload(self, systems: dict[str, dict[str, Any]]) -> dict[str, Any]:
        totals = {
            "total": 0,
            "backlog_open": 0,
            "due_now": 0,
            "processing_overdue": 0,
            "pending": 0,
            "processing": 0,
            "retry_pending": 0,
            "succeeded": 0,
            "failed": 0,
        }
        job_types: list[dict[str, Any]] = []
        for system_payload in systems.values():
            summary = system_payload.get("summary") or {}
            by_status = summary.get("by_status") or {}
            totals["total"] += int(summary.get("total") or 0)
            totals["backlog_open"] += int(summary.get("backlog_open") or 0)
            totals["due_now"] += int(summary.get("due_now") or 0)
            totals["processing_overdue"] += int(summary.get("processing_overdue") or 0)
            totals["pending"] += int(by_status.get("pending") or 0)
            totals["processing"] += int(by_status.get("processing") or 0)
            totals["retry_pending"] += int(by_status.get("retry_pending") or 0)
            totals["succeeded"] += int(by_status.get("succeeded") or 0)
            totals["failed"] += int(by_status.get("failed") or 0)
            for item in system_payload.get("job_types") or []:
                if isinstance(item, dict):
                    job_types.append(item)
        job_types.sort(
            key=lambda item: (
                -int(item.get("backlog_open") or 0),
                -int(item.get("due_now") or 0),
                -int((item.get("by_status") or {}).get("failed") or 0),
                -int(item.get("total") or 0),
                str(item.get("target") or ""),
                str(item.get("job_type") or ""),
            )
        )
        return {
            "systems": systems,
            "ledger": getattr(self, "_relation_ledger_summary", {}),
            "funnel": getattr(self, "_relation_funnel_summary", {}),
            "totals": totals,
            "job_types": job_types,
            "trace_id": get_trace_id(),
        }

    def _build_async_job_dashboard(self, *, limit: int) -> dict[str, Any]:
        safe_limit = max(int(limit), 1)
        try:
            self._relation_ledger_summary = _json_safe(self._with_ledger(build_relation_dashboard))
        except Exception:
            self._relation_ledger_summary = {}
        try:
            self._relation_funnel_summary = _json_safe(self._with_ledger(build_cross_system_funnel_dashboard))
        except Exception:
            self._relation_funnel_summary = {}
        systems = {
            "recommendation": self._async_job_dashboard_system(
                target="recommendation",
                with_fn=self._with_rec,
                list_fn=list_recommendation_async_jobs,
                summary_fn=summarize_recommendation_async_jobs,
                summary_by_type_fn=summarize_recommendation_async_jobs_by_type,
                limit=safe_limit,
            ),
            "matchmaking": self._async_job_dashboard_system(
                target="matchmaking",
                with_fn=self._with_mm,
                list_fn=list_matchmaking_async_jobs,
                summary_fn=summarize_matchmaking_async_jobs,
                summary_by_type_fn=summarize_matchmaking_async_jobs_by_type,
                limit=safe_limit,
            ),
            "chat": self._async_job_dashboard_system(
                target="chat",
                with_fn=self._with_chat,
                list_fn=list_chat_async_jobs,
                summary_fn=summarize_chat_async_jobs,
                summary_by_type_fn=summarize_chat_async_jobs_by_type,
                limit=safe_limit,
            ),
        }
        return self._async_job_dashboard_payload(systems)

    def _enqueue_async_job(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Callable[..., Any],
        enqueue_fn: Callable[..., Any],
        job_type: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        actor = self._current_actor(environ)
        job = with_fn(
            enqueue_fn,
            job_type=job_type,
            payload=payload,
            created_by=actor.actor_id if actor is not None else None,
            trace_id=get_trace_id(),
        )
        return 202, self._job_payload(target, job)

    def _get_async_job(
        self,
        *,
        target: str,
        with_fn: Callable[..., Any],
        get_fn: Callable[..., Any],
        job_id: str,
    ) -> tuple[int, dict[str, Any]]:
        job = with_fn(get_fn, job_id)
        if not job:
            return 404, {"error": {"code": "not_found", "message": "job not found"}, "trace_id": get_trace_id()}
        return 200, self._job_payload(target, job)

    def _list_async_jobs(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Callable[..., Any],
        list_fn: Callable[..., Any],
        summary_fn: Callable[..., Any],
    ) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        limit_raw = q.get("limit") or "50"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 50
        jobs = with_fn(list_fn, statuses=statuses, limit=limit)
        summary = with_fn(summary_fn)
        return 200, self._job_collection_payload(target, jobs, summary)
