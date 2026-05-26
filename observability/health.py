"""Threshold-based health signals and depth gauges (runs inside scheduled jobs / workers)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from async_jobs import summarize_async_jobs
from match_domain.proxy_intro_storage import table_names

from . import alert_signal, metric_gauge


def _sql_datetime(now: datetime) -> str:
    dt = now.replace(microsecond=0)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(sep=" ")

OPEN_PROXY_CASE_STATUSES = ("pending_outreach", "awaiting_reply", "accepted")
OPEN_MATCHMAKING_CASE_STATUSES = (
    "pending_first_contact",
    "awaiting_first_reply",
    "pending_second_contact",
    "awaiting_second_reply",
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def count_proxy_intro_cases_past_deadline(conn, *, now: datetime) -> int:
    tn = table_names()
    placeholders = ", ".join(["?"] * len(OPEN_PROXY_CASE_STATUSES))
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM {tn.cases}
        WHERE case_status IN ({placeholders})
          AND reply_deadline_at IS NOT NULL
          AND reply_deadline_at < ?
        """,
        [*OPEN_PROXY_CASE_STATUSES, _sql_datetime(now)],
    ).fetchone()
    return int(row["c"]) if row else 0


def count_proxy_cases_past_deadline(conn, *, now: datetime) -> int:
    """Deprecated alias — use count_proxy_intro_cases_past_deadline on matchmaking DB."""
    return count_proxy_intro_cases_past_deadline(conn, now=now)


def count_matchmaking_cases_past_expiry(conn, *, now: datetime) -> int:
    placeholders = ", ".join(["?"] * len(OPEN_MATCHMAKING_CASE_STATUSES))
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM match_cases
        WHERE status IN ({placeholders})
          AND expires_at IS NOT NULL
          AND expires_at < ?
        """,
        [*OPEN_MATCHMAKING_CASE_STATUSES, _sql_datetime(now)],
    ).fetchone()
    return int(row["c"]) if row else 0


def count_pool_members_needing_refresh(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM matchmaking_pool_members
        WHERE status = 'active_single'
          AND is_still_searching = 1
          AND needs_refresh = 1
        """
    ).fetchone()
    return int(row["c"]) if row else 0


def recommendation_queue_depths(conn) -> dict[str, int]:
    out: dict[str, int] = {}
    for status in ("review_pending", "pending_delivery", "delivered"):
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM profile_recommendations
            WHERE delivery_status = ?
            """,
            (status,),
        ).fetchone()
        out[status] = int(row["c"]) if row else 0
    return out


def emit_recommendation_gauges(conn) -> None:
    depths = recommendation_queue_depths(conn)
    for k, v in depths.items():
        metric_gauge(f"recommendation.queue.{k}", v)
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM saved_search_subscriptions
        WHERE status = 'active' AND is_still_searching = 1
        """
    ).fetchone()
    metric_gauge("recommendation.active_subscriptions", int(row["c"]) if row else 0)


def emit_matchmaking_gauges(conn) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM matchmaking_pool_members
        WHERE status = 'active_single' AND is_still_searching = 1
        """
    ).fetchone()
    metric_gauge("matchmaking.active_pool_members", int(row["c"]) if row else 0)
    metric_gauge("matchmaking.pool.needs_refresh_members", count_pool_members_needing_refresh(conn))
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM matchmaking_edges
        WHERE edge_status = 'active'
        """
    ).fetchone()
    metric_gauge("matchmaking.active_edges", int(row["c"]) if row else 0)
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM matchmaking_pairs
        WHERE pair_status = 'eligible'
        """
    ).fetchone()
    metric_gauge("matchmaking.pairs_eligible", int(row["c"]) if row else 0)


def emit_async_job_gauges(
    conn,
    *,
    system: str,
    now: datetime,
    claim_timeout_seconds: int = 300,
) -> dict[str, Any]:
    summary = summarize_async_jobs(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)
    metric_gauge(f"{system}.async_jobs.total", int(summary["total"]))
    metric_gauge(f"{system}.async_jobs.backlog_open", int(summary["backlog_open"]))
    metric_gauge(f"{system}.async_jobs.due_now", int(summary["due_now"]))
    metric_gauge(f"{system}.async_jobs.processing_overdue", int(summary["processing_overdue"]))
    by_status = dict(summary.get("by_status") or {})
    for status, count in by_status.items():
        metric_gauge(f"{system}.async_jobs.{status}", int(count))

    upper = system.upper()
    backlog_threshold = _env_int(f"HER_ALERT_{upper}_ASYNC_JOB_BACKLOG", 20)
    if int(summary["backlog_open"]) >= backlog_threshold:
        alert_signal(
            f"{system}.async_job_backlog",
            f"{system} async job backlog_open={summary['backlog_open']} (threshold {backlog_threshold}).",
            severity="warning",
            backlog_open=int(summary["backlog_open"]),
            threshold=backlog_threshold,
        )
    failed_threshold = _env_int(f"HER_ALERT_{upper}_ASYNC_JOB_FAILED", 5)
    if int(by_status.get("failed", 0)) >= failed_threshold:
        alert_signal(
            f"{system}.async_job_failed_depth",
            f"{system} async job failed={by_status.get('failed', 0)} (threshold {failed_threshold}).",
            severity="warning",
            failed_count=int(by_status.get("failed", 0) or 0),
            threshold=failed_threshold,
        )
    overdue_threshold = _env_int(f"HER_ALERT_{upper}_ASYNC_JOB_PROCESSING_OVERDUE", 1)
    if int(summary["processing_overdue"]) >= overdue_threshold:
        alert_signal(
            f"{system}.async_job_processing_overdue",
            f"{system} async job processing_overdue={summary['processing_overdue']} (threshold {overdue_threshold}).",
            severity="warning",
            processing_overdue=int(summary["processing_overdue"]),
            threshold=overdue_threshold,
        )
    return summary


def check_low_refresh_scan(
    summaries: list[Mapping[str, Any]],
    *,
    min_results: int | None = None,
) -> None:
    threshold = min_results if min_results is not None else _env_int("HER_ALERT_MIN_REC_SCAN_RESULTS", 2)
    for s in summaries:
        rc = int(s.get("result_count") or 0)
        if rc < threshold:
            alert_signal(
                "recommendation.candidate_scan_low",
                f"Refresh returned {rc} candidates (threshold {threshold}).",
                severity="warning",
                subscription_id=s.get("subscription_id"),
                result_count=rc,
                threshold=threshold,
            )


def check_refresh_failures(errors: list[Mapping[str, Any]]) -> None:
    for err in errors:
        alert_signal(
            "recommendation.refresh_failed",
            str(err.get("error") or "refresh error"),
            severity="error",
            subscription_id=err.get("subscription_id"),
            error_type=err.get("error_type"),
        )


def run_recommendation_health(
    conn,
    *,
    now: datetime,
    refresh_summaries: list[Mapping[str, Any]] | None = None,
    refresh_errors: list[Mapping[str, Any]] | None = None,
) -> None:
    emit_recommendation_gauges(conn)
    emit_async_job_gauges(conn, system="recommendation", now=now)

    if refresh_summaries:
        check_low_refresh_scan(refresh_summaries)
    if refresh_errors:
        check_refresh_failures(refresh_errors)


def run_matchmaking_health(
    conn,
    *,
    now: datetime,
    pool_refresh_summaries: list[Mapping[str, Any]] | None = None,
) -> None:
    emit_matchmaking_gauges(conn)
    emit_async_job_gauges(conn, system="matchmaking", now=now)
    proxy_backlog = count_proxy_intro_cases_past_deadline(conn, now=now)
    metric_gauge("matchmaking.proxy_intro_cases_past_reply_deadline", proxy_backlog)
    max_proxy = _env_int("HER_ALERT_PROXY_CASE_BACKLOG", 20)
    if proxy_backlog >= max_proxy:
        alert_signal(
            "matchmaking.proxy_intro_case_backlog",
            f"{proxy_backlog} proxy intro cases past reply_deadline (threshold {max_proxy}).",
            severity="warning",
            backlog=proxy_backlog,
            threshold=max_proxy,
        )
    mm_backlog = count_matchmaking_cases_past_expiry(conn, now=now)
    metric_gauge("matchmaking.cases_past_expires_at", mm_backlog)
    max_mm = _env_int("HER_ALERT_MATCHMAKING_CASE_BACKLOG", 10)
    if mm_backlog >= max_mm:
        alert_signal(
            "matchmaking.case_timeout_backlog",
            f"{mm_backlog} matchmaking cases past expires_at while still open (threshold {max_mm}).",
            severity="warning",
            backlog=mm_backlog,
            threshold=max_mm,
        )

    needs = count_pool_members_needing_refresh(conn)
    max_pool = _env_int("HER_ALERT_POOL_NEEDS_REFRESH", 30)
    if needs >= max_pool:
        alert_signal(
            "matchmaking.pool_refill_insufficient",
            f"{needs} active members still need_refresh=1 (threshold {max_pool}).",
            severity="warning",
            needs_refresh_count=needs,
            threshold=max_pool,
        )

    scan_threshold = _env_int("HER_ALERT_MIN_MM_SCAN_RESULTS", 2)
    if pool_refresh_summaries:
        for s in pool_refresh_summaries:
            if s.get("skipped"):
                continue
            rc = int(s.get("result_count") or 0)
            if rc < scan_threshold:
                alert_signal(
                    "matchmaking.candidate_scan_low",
                    f"Pool refresh scanned {rc} candidates (threshold {scan_threshold}).",
                    severity="warning",
                    member_id=s.get("member_id"),
                    result_count=rc,
                    threshold=scan_threshold,
                )
