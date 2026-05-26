"""Outbox backlog / failure depth alerts via observability.alert_signal."""

from __future__ import annotations

import os
from datetime import datetime

from match_domain.outbox_runtime import summarize_outbox

from . import alert_signal, metric_gauge


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def emit_outbox_health_alerts(
    conn,
    *,
    system: str,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, int]:
    """Evaluate outbox summary and emit threshold alerts. Returns summarize_outbox dict."""
    summary = summarize_outbox(
        conn,
        now=now,
        claim_timeout_seconds=claim_timeout_seconds,
    )
    upper = system.upper()
    pending = int(summary.get("pending_rows") or 0)
    retry_due = int(summary.get("retry_due_rows") or 0)
    failed = int(summary.get("failed_rows") or 0)
    stale = int(summary.get("processing_stale_rows") or 0)
    backlog = pending + retry_due

    metric_gauge(f"{system}.outbox.pending", pending)
    metric_gauge(f"{system}.outbox.retry_due", retry_due)
    metric_gauge(f"{system}.outbox.failed", failed)
    metric_gauge(f"{system}.outbox.processing_stale", stale)
    metric_gauge(f"{system}.outbox.backlog_open", backlog)

    backlog_threshold = _env_int(f"HER_ALERT_{upper}_OUTBOX_BACKLOG", 50)
    if backlog >= backlog_threshold:
        alert_signal(
            f"{system}.outbox_backlog",
            (
                f"{system} outbox backlog={backlog} "
                f"(pending={pending}, retry_due={retry_due}, threshold {backlog_threshold})."
            ),
            severity="warning",
            backlog=backlog,
            pending=pending,
            retry_due=retry_due,
            threshold=backlog_threshold,
        )

    failed_threshold = _env_int(f"HER_ALERT_{upper}_OUTBOX_FAILED", 10)
    if failed >= failed_threshold:
        alert_signal(
            f"{system}.outbox_failed_depth",
            f"{system} outbox failed_rows={failed} (threshold {failed_threshold}).",
            severity="warning",
            failed_rows=failed,
            threshold=failed_threshold,
        )

    stale_threshold = _env_int(f"HER_ALERT_{upper}_OUTBOX_PROCESSING_STALE", 5)
    if stale >= stale_threshold:
        alert_signal(
            f"{system}.outbox_processing_stale",
            f"{system} outbox processing_stale={stale} (threshold {stale_threshold}).",
            severity="warning",
            processing_stale=stale,
            threshold=stale_threshold,
        )

    return summary


__all__ = ["emit_outbox_health_alerts"]
