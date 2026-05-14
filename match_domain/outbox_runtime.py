"""Reusable outbox runtime helpers: claim, retry, consume, and worker loops."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Optional

from observability import alert_signal, funnel_stage

from .outbox import (
    PUBLISH_STATUS_FAILED,
    PUBLISH_STATUS_PENDING,
    PUBLISH_STATUS_PROCESSING,
    PUBLISH_STATUS_PUBLISHED,
    PUBLISH_STATUS_RETRY_PENDING,
)
from .trace_context import get_trace_id

OutboxHandler = Callable[[Any, dict[str, Any], dict[str, Any], datetime], Optional[Any]]

OUTBOX_FUNNEL_DISPATCHED = "outbox_dispatched"


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def _default_worker_name(system: str) -> str:
    return f"{system}-outbox@{socket.gethostname()}:{os.getpid()}"


def resolve_outbox_consume_config(
    *,
    env_prefix: str,
    system: str,
    default_limit: int = 200,
    default_max_batches: int = 1,
    default_retry_delay_seconds: int = 60,
    default_retry_backoff_multiplier: int = 2,
    default_retry_max_delay_seconds: int = 600,
    default_max_attempts: int = 3,
    default_claim_timeout_seconds: int = 300,
    default_poll_interval_seconds: int = 15,
    default_max_idle_polls: int = 3,
    default_worker_name: str | None = None,
) -> dict[str, Any]:
    worker_name = str(
        os.environ.get(f"{env_prefix}_WORKER_NAME")
        or default_worker_name
        or _default_worker_name(system)
    ).strip() or _default_worker_name(system)
    return {
        "limit": max(1, _env_int(f"{env_prefix}_BATCH_LIMIT", default_limit)),
        "max_batches": max(1, _env_int(f"{env_prefix}_MAX_BATCHES", default_max_batches)),
        "retry_delay_seconds": max(
            1,
            _env_int(f"{env_prefix}_RETRY_DELAY_SECONDS", default_retry_delay_seconds),
        ),
        "retry_backoff_multiplier": max(
            1,
            _env_int(
                f"{env_prefix}_RETRY_BACKOFF_MULTIPLIER",
                default_retry_backoff_multiplier,
            ),
        ),
        "retry_max_delay_seconds": max(
            1,
            _env_int(
                f"{env_prefix}_RETRY_MAX_DELAY_SECONDS",
                default_retry_max_delay_seconds,
            ),
        ),
        "max_attempts": max(1, _env_int(f"{env_prefix}_MAX_ATTEMPTS", default_max_attempts)),
        "claim_timeout_seconds": max(
            1,
            _env_int(
                f"{env_prefix}_CLAIM_TIMEOUT_SECONDS",
                default_claim_timeout_seconds,
            ),
        ),
        "poll_interval_seconds": max(
            1,
            _env_int(
                f"{env_prefix}_POLL_INTERVAL_SECONDS",
                default_poll_interval_seconds,
            ),
        ),
        "max_idle_polls": max(
            1,
            _env_int(f"{env_prefix}_MAX_IDLE_POLLS", default_max_idle_polls),
        ),
        "worker_name": worker_name,
    }


def list_pending_outbox(conn, *, limit: int = 100, now: datetime | None = None) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    ts = _ts(now)
    cur = conn.execute(
        """
        SELECT * FROM outbox_events
        WHERE publish_status IN (?, ?)
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY outbox_id ASC
        LIMIT ?
        """,
        (PUBLISH_STATUS_PENDING, PUBLISH_STATUS_RETRY_PENDING, ts, lim),
    )
    return [dict(r) for r in cur.fetchall()]


def list_retry_pending_outbox(
    conn,
    *,
    limit: int = 100,
    now: datetime | None = None,
    due_only: bool = False,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    ts = _ts(now)
    if due_only:
        cur = conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE publish_status = ?
              AND next_retry_at IS NOT NULL
              AND next_retry_at <= ?
            ORDER BY next_retry_at ASC, outbox_id ASC
            LIMIT ?
            """,
            (PUBLISH_STATUS_RETRY_PENDING, ts, lim),
        )
    else:
        cur = conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE publish_status = ?
            ORDER BY COALESCE(next_retry_at, created_at) ASC, outbox_id ASC
            LIMIT ?
            """,
            (PUBLISH_STATUS_RETRY_PENDING, lim),
        )
    return [dict(r) for r in cur.fetchall()]


def list_processing_outbox(
    conn,
    *,
    limit: int = 100,
    now: datetime | None = None,
    stale_only: bool = False,
    claim_timeout_seconds: int = 300,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    ts = _ts(now)
    cutoff = ts - timedelta(seconds=max(1, int(claim_timeout_seconds)))
    if stale_only:
        cur = conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE publish_status = ?
              AND processing_started_at IS NOT NULL
              AND processing_started_at <= ?
            ORDER BY processing_started_at ASC, outbox_id ASC
            LIMIT ?
            """,
            (PUBLISH_STATUS_PROCESSING, cutoff, lim),
        )
    else:
        cur = conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE publish_status = ?
            ORDER BY processing_started_at ASC, outbox_id ASC
            LIMIT ?
            """,
            (PUBLISH_STATUS_PROCESSING, lim),
        )
    return [dict(r) for r in cur.fetchall()]


def list_failed_outbox(conn, *, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    cur = conn.execute(
        """
        SELECT * FROM outbox_events
        WHERE publish_status = ?
        ORDER BY last_attempt_at DESC, outbox_id DESC
        LIMIT ?
        """,
        (PUBLISH_STATUS_FAILED, lim),
    )
    return [dict(r) for r in cur.fetchall()]


def get_outbox_row(conn, outbox_id: int) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM outbox_events WHERE outbox_id = ? LIMIT 1", (outbox_id,))
    row = cur.fetchone()
    return None if row is None else dict(row)


def mark_outbox_rows_published(conn, outbox_ids: list[int], *, now=None) -> int:
    if not outbox_ids:
        return 0
    ts = _ts(now)
    placeholders = ",".join("?" * len(outbox_ids))
    res = conn.execute(
        f"""
        UPDATE outbox_events
        SET publish_status = ?,
            published_at = ?,
            publish_attempts = publish_attempts + 1,
            last_attempt_at = ?,
            next_retry_at = NULL,
            last_error = NULL,
            processing_token = NULL,
            processing_started_at = NULL,
            processing_worker = NULL
        WHERE outbox_id IN ({placeholders}) AND publish_status IN (?, ?)
        """,
        (
            PUBLISH_STATUS_PUBLISHED,
            ts,
            ts,
            *outbox_ids,
            PUBLISH_STATUS_PENDING,
            PUBLISH_STATUS_RETRY_PENDING,
        ),
    )
    return int(res.rowcount)


def mark_claimed_outbox_rows_published(
    conn,
    outbox_ids: list[int],
    *,
    processing_token: str,
    now=None,
) -> int:
    if not outbox_ids:
        return 0
    ts = _ts(now)
    placeholders = ",".join("?" * len(outbox_ids))
    res = conn.execute(
        f"""
        UPDATE outbox_events
        SET publish_status = ?,
            published_at = ?,
            publish_attempts = publish_attempts + 1,
            last_attempt_at = ?,
            next_retry_at = NULL,
            last_error = NULL,
            processing_token = NULL,
            processing_started_at = NULL,
            processing_worker = NULL
        WHERE outbox_id IN ({placeholders})
          AND publish_status = ?
          AND processing_token = ?
        """,
        (
            PUBLISH_STATUS_PUBLISHED,
            ts,
            ts,
            *outbox_ids,
            PUBLISH_STATUS_PROCESSING,
            str(processing_token or "").strip(),
        ),
    )
    return int(res.rowcount)


def mark_pending_outbox_published_batch(conn, *, limit: int = 100, now=None) -> int:
    rows = list_pending_outbox(conn, limit=limit, now=now)
    ids = [int(r["outbox_id"]) for r in rows]
    n = mark_outbox_rows_published(conn, ids, now=now)
    conn.commit()
    return n


def _compute_retry_delay_seconds(
    current_attempts: int,
    *,
    retry_delay_seconds: int,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int | None = None,
) -> int:
    base_delay = max(1, int(retry_delay_seconds))
    multiplier = max(1, int(retry_backoff_multiplier))
    delay = base_delay * (multiplier ** max(0, int(current_attempts)))
    cap = None if retry_max_delay_seconds is None else max(1, int(retry_max_delay_seconds))
    if cap is not None:
        delay = min(delay, cap)
    return int(delay)


def mark_outbox_row_retry_pending(
    conn,
    outbox_id: int,
    *,
    error: str,
    now: datetime | None = None,
    retry_delay_seconds: int = 60,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int | None = None,
    max_attempts: int = 3,
    processing_token: str | None = None,
) -> dict[str, Any]:
    row = get_outbox_row(conn, outbox_id)
    if row is None:
        return {"outbox_id": outbox_id, "status": "missing", "publish_attempts": 0}

    current_attempts = int(row.get("publish_attempts") or 0)
    next_attempts = current_attempts + 1
    ts = _ts(now)
    attempt_cap = max(1, int(max_attempts))
    publish_status = (
        PUBLISH_STATUS_FAILED
        if next_attempts >= attempt_cap
        else PUBLISH_STATUS_RETRY_PENDING
    )
    retry_delay = _compute_retry_delay_seconds(
        current_attempts,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
    )
    next_retry_at = None if publish_status == PUBLISH_STATUS_FAILED else ts + timedelta(seconds=retry_delay)
    message = str(error or "").strip() or "unknown outbox dispatch error"
    token = str(processing_token or "").strip()

    if token:
        res = conn.execute(
            """
            UPDATE outbox_events
            SET publish_status = ?,
                publish_attempts = ?,
                last_attempt_at = ?,
                next_retry_at = ?,
                last_error = ?,
                published_at = NULL,
                processing_token = NULL,
                processing_started_at = NULL,
                processing_worker = NULL
            WHERE outbox_id = ?
              AND publish_status = ?
              AND processing_token = ?
            """,
            (
                publish_status,
                next_attempts,
                ts,
                next_retry_at,
                message[:4000],
                outbox_id,
                PUBLISH_STATUS_PROCESSING,
                token,
            ),
        )
    else:
        res = conn.execute(
            """
            UPDATE outbox_events
            SET publish_status = ?,
                publish_attempts = ?,
                last_attempt_at = ?,
                next_retry_at = ?,
                last_error = ?,
                published_at = NULL,
                processing_token = NULL,
                processing_started_at = NULL,
                processing_worker = NULL
            WHERE outbox_id = ?
              AND publish_status IN (?, ?)
            """,
            (
                publish_status,
                next_attempts,
                ts,
                next_retry_at,
                message[:4000],
                outbox_id,
                PUBLISH_STATUS_PENDING,
                PUBLISH_STATUS_RETRY_PENDING,
            ),
        )
    if int(res.rowcount or 0) <= 0:
        return {
            "outbox_id": outbox_id,
            "status": str(row.get("publish_status") or ""),
            "publish_attempts": current_attempts,
        }
    return {
        "outbox_id": outbox_id,
        "status": publish_status,
        "publish_attempts": next_attempts,
        "retry_delay_seconds": 0 if next_retry_at is None else retry_delay,
        "next_retry_at": None if next_retry_at is None else next_retry_at.isoformat(sep=" "),
    }


def recover_stale_outbox_claims(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    retry_delay_seconds: int = 60,
    max_attempts: int = 3,
    error_message: str = "outbox processing timed out",
) -> int:
    ts = _ts(now)
    cutoff = ts - timedelta(seconds=max(1, int(claim_timeout_seconds)))
    retry_at = ts + timedelta(seconds=max(1, int(retry_delay_seconds)))
    attempt_cap = max(1, int(max_attempts))
    res = conn.execute(
        """
        UPDATE outbox_events
        SET publish_status = CASE
                WHEN publish_attempts + 1 >= ? THEN ?
                ELSE ?
            END,
            publish_attempts = publish_attempts + 1,
            last_attempt_at = ?,
            next_retry_at = CASE
                WHEN publish_attempts + 1 >= ? THEN NULL
                ELSE ?
            END,
            last_error = ?,
            published_at = NULL,
            processing_token = NULL,
            processing_started_at = NULL,
            processing_worker = NULL
        WHERE publish_status = ?
          AND processing_started_at IS NOT NULL
          AND processing_started_at <= ?
        """,
        (
            attempt_cap,
            PUBLISH_STATUS_FAILED,
            PUBLISH_STATUS_RETRY_PENDING,
            ts,
            attempt_cap,
            retry_at,
            str(error_message or "outbox processing timed out").strip()[:4000],
            PUBLISH_STATUS_PROCESSING,
            cutoff,
        ),
    )
    return int(res.rowcount)


def claim_pending_outbox_batch(
    conn,
    *,
    limit: int = 100,
    claim_token: str,
    worker_name: str,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    stale_retry_delay_seconds: int = 60,
    max_attempts: int = 3,
) -> dict[str, Any]:
    lim = max(1, min(int(limit), 500))
    token = str(claim_token or "").strip()
    worker = str(worker_name or "").strip()[:191] or "outbox-worker"
    if not token:
        raise ValueError("claim_token is required")
    ts = _ts(now)
    recovered = recover_stale_outbox_claims(
        conn,
        now=ts,
        claim_timeout_seconds=claim_timeout_seconds,
        retry_delay_seconds=stale_retry_delay_seconds,
        max_attempts=max_attempts,
    )
    candidates = list_pending_outbox(conn, limit=lim, now=ts)
    candidate_ids = [int(row["outbox_id"]) for row in candidates]
    claimed_rows: list[dict[str, Any]] = []
    if candidate_ids:
        placeholders = ",".join("?" * len(candidate_ids))
        conn.execute(
            f"""
            UPDATE outbox_events
            SET publish_status = ?,
                processing_token = ?,
                processing_started_at = ?,
                processing_worker = ?
            WHERE outbox_id IN ({placeholders})
              AND publish_status IN (?, ?)
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            """,
            (
                PUBLISH_STATUS_PROCESSING,
                token,
                ts,
                worker,
                *candidate_ids,
                PUBLISH_STATUS_PENDING,
                PUBLISH_STATUS_RETRY_PENDING,
                ts,
            ),
        )
        cur = conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE processing_token = ?
            ORDER BY outbox_id ASC
            """,
            (token,),
        )
        claimed_rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return {
        "stale_recovered": recovered,
        "rows": claimed_rows,
    }


def requeue_outbox_rows(
    conn,
    outbox_ids: list[int],
    *,
    reset_attempts: bool = False,
    clear_error: bool = True,
) -> int:
    if not outbox_ids:
        return 0
    placeholders = ",".join("?" * len(outbox_ids))
    attempt_sql = "0" if reset_attempts else "publish_attempts"
    error_sql = "NULL" if clear_error else "last_error"
    res = conn.execute(
        f"""
        UPDATE outbox_events
        SET publish_status = ?,
            next_retry_at = NULL,
            published_at = NULL,
            publish_attempts = {attempt_sql},
            last_error = {error_sql},
            processing_token = NULL,
            processing_started_at = NULL,
            processing_worker = NULL
        WHERE outbox_id IN ({placeholders}) AND publish_status IN (?, ?)
        """,
        (
            PUBLISH_STATUS_PENDING,
            *outbox_ids,
            PUBLISH_STATUS_RETRY_PENDING,
            PUBLISH_STATUS_FAILED,
        ),
    )
    return int(res.rowcount)


def summarize_outbox(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, int]:
    ts = _ts(now)
    cutoff = ts - timedelta(seconds=max(1, int(claim_timeout_seconds)))
    cur = conn.execute(
        """
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN publish_status = ? THEN 1 ELSE 0 END) AS pending_rows,
          SUM(CASE WHEN publish_status = ? THEN 1 ELSE 0 END) AS processing_rows,
          SUM(CASE WHEN publish_status = ? AND processing_started_at IS NOT NULL AND processing_started_at <= ? THEN 1 ELSE 0 END) AS processing_stale_rows,
          SUM(CASE WHEN publish_status = ? THEN 1 ELSE 0 END) AS retry_pending_rows,
          SUM(CASE WHEN publish_status = ? AND next_retry_at IS NOT NULL AND next_retry_at <= ? THEN 1 ELSE 0 END) AS retry_due_rows,
          SUM(CASE WHEN publish_status = ? AND (next_retry_at IS NULL OR next_retry_at > ?) THEN 1 ELSE 0 END) AS retry_waiting_rows,
          SUM(CASE WHEN publish_status = ? THEN 1 ELSE 0 END) AS failed_rows,
          SUM(CASE WHEN publish_status = ? THEN 1 ELSE 0 END) AS published_rows
        FROM outbox_events
        """,
        (
            PUBLISH_STATUS_PENDING,
            PUBLISH_STATUS_PROCESSING,
            PUBLISH_STATUS_PROCESSING,
            cutoff,
            PUBLISH_STATUS_RETRY_PENDING,
            PUBLISH_STATUS_RETRY_PENDING,
            ts,
            PUBLISH_STATUS_RETRY_PENDING,
            ts,
            PUBLISH_STATUS_FAILED,
            PUBLISH_STATUS_PUBLISHED,
        ),
    )
    row = cur.fetchone() or {}
    return {key: int((row or {}).get(key) or 0) for key in row}


def _load_outbox_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("canonical_event_json")
    if not raw:
        return {}
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return {}


def consume_outbox_batch(
    conn,
    *,
    system: str,
    limit: int = 100,
    now: datetime | None = None,
    retry_delay_seconds: int = 60,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int | None = None,
    max_attempts: int = 3,
    claim_timeout_seconds: int = 300,
    worker_name: str | None = None,
    handler: OutboxHandler | None = None,
) -> dict[str, Any]:
    claim_token = uuid.uuid4().hex
    resolved_worker_name = str(worker_name or "").strip() or _default_worker_name(system)
    ts = _ts(now)
    claim_result = claim_pending_outbox_batch(
        conn,
        limit=limit,
        claim_token=claim_token,
        worker_name=resolved_worker_name,
        now=ts,
        claim_timeout_seconds=claim_timeout_seconds,
        stale_retry_delay_seconds=retry_delay_seconds,
        max_attempts=max_attempts,
    )
    rows = list(claim_result.get("rows") or [])
    stale_recovered = int(claim_result.get("stale_recovered") or 0)
    ids: list[int] = []
    handler_results: list[Any] = []
    errors: list[dict[str, Any]] = []
    retry_scheduled = 0
    failed = 0

    for row in rows:
        oid = int(row["outbox_id"])
        payload = _load_outbox_payload(row)
        event_type = payload.get("event_type") or row.get("event_type")
        case_id = None
        if isinstance(payload.get("payload"), dict):
            case_id = payload["payload"].get("case_id")
        funnel_stage(
            system=system,
            stage=OUTBOX_FUNNEL_DISPATCHED,
            trace_id=get_trace_id(),
            outbox_id=oid,
            event_type=event_type,
            aggregate_id=row.get("aggregate_id"),
            case_id=case_id,
            source_row_table=row.get("source_row_table"),
            source_row_id=row.get("source_row_id"),
        )
        try:
            handler_result = None if handler is None else handler(conn, payload, dict(row), ts)
        except Exception as exc:
            retry_state = mark_outbox_row_retry_pending(
                conn,
                oid,
                error=str(exc),
                now=ts,
                retry_delay_seconds=retry_delay_seconds,
                retry_backoff_multiplier=retry_backoff_multiplier,
                retry_max_delay_seconds=retry_max_delay_seconds,
                max_attempts=max_attempts,
                processing_token=claim_token,
            )
            status = str(retry_state.get("status") or "")
            if status == PUBLISH_STATUS_RETRY_PENDING:
                retry_scheduled += 1
            elif status == PUBLISH_STATUS_FAILED:
                failed += 1
            alert_signal(
                f"{system}.outbox_dispatch_failed",
                str(exc),
                severity="warning",
                subsystem=system,
                worker_name=resolved_worker_name,
                outbox_id=oid,
                event_type=event_type,
                error_type=type(exc).__name__,
                publish_attempts=int(retry_state.get("publish_attempts") or 0),
                next_retry_at=retry_state.get("next_retry_at"),
            )
            errors.append(
                {
                    "outbox_id": oid,
                    "error": str(exc),
                    "status": status,
                    "publish_attempts": int(retry_state.get("publish_attempts") or 0),
                    "retry_delay_seconds": int(retry_state.get("retry_delay_seconds") or 0),
                    "next_retry_at": retry_state.get("next_retry_at"),
                }
            )
            continue
        ids.append(oid)
        if handler_result is not None:
            handler_results.append(handler_result)

    marked = mark_claimed_outbox_rows_published(conn, ids, now=ts, processing_token=claim_token)
    conn.commit()
    return {
        "worker_name": resolved_worker_name,
        "claimed": len(rows),
        "examined": len(rows),
        "marked_published": marked,
        "handler_result_count": len(handler_results),
        "handler_results": handler_results,
        "retry_scheduled": retry_scheduled,
        "failed": failed,
        "stale_recovered": stale_recovered,
        "errors": errors,
    }


def run_outbox_worker(
    conn,
    *,
    system: str,
    config: Mapping[str, Any],
    handler: OutboxHandler | None = None,
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
    consume_claim_timeout = max(
        1,
        int(claim_timeout_seconds or config["claim_timeout_seconds"]),
    )
    resolved_worker_name = str(worker_name or config["worker_name"]).strip() or _default_worker_name(system)

    before = summarize_outbox(conn, now=now, claim_timeout_seconds=consume_claim_timeout)
    batches: list[dict[str, Any]] = []
    totals = {
        "claimed": 0,
        "examined": 0,
        "marked_published": 0,
        "handler_result_count": 0,
        "retry_scheduled": 0,
        "failed": 0,
        "stale_recovered": 0,
        "error_count": 0,
    }
    for _ in range(batch_cap):
        batch = consume_outbox_batch(
            conn,
            system=system,
            limit=consume_limit,
            now=now,
            retry_delay_seconds=consume_retry_delay,
            retry_backoff_multiplier=consume_backoff_multiplier,
            retry_max_delay_seconds=consume_retry_max_delay,
            max_attempts=consume_max_attempts,
            claim_timeout_seconds=consume_claim_timeout,
            worker_name=resolved_worker_name,
            handler=handler,
        )
        batches.append(batch)
        totals["claimed"] += int(batch.get("claimed") or 0)
        totals["examined"] += int(batch.get("examined") or 0)
        totals["marked_published"] += int(batch.get("marked_published") or 0)
        totals["handler_result_count"] += int(batch.get("handler_result_count") or 0)
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


def serve_outbox_worker(
    conn,
    *,
    system: str,
    config: Mapping[str, Any],
    handler: OutboxHandler | None = None,
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
    cycle_batch_cap = max(1, int(max_batches_per_cycle or config["max_batches"]))
    poll_interval = max(1, int(poll_interval_seconds or config["poll_interval_seconds"]))
    idle_cap = max(1, int(max_idle_polls or config["max_idle_polls"]))
    runtime_cap = None if max_runtime_seconds is None else max(1, int(max_runtime_seconds))
    now_fn = clock_fn or datetime.now
    sleeper = sleep_fn or time.sleep
    resolved_worker_name = str(worker_name or config["worker_name"]).strip() or _default_worker_name(system)

    started_at = now_fn()
    cycles: list[dict[str, Any]] = []
    totals = {
        "claimed": 0,
        "examined": 0,
        "marked_published": 0,
        "handler_result_count": 0,
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
        cycle = run_outbox_worker(
            conn,
            system=system,
            config=config,
            handler=handler,
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
    "OUTBOX_FUNNEL_DISPATCHED",
    "claim_pending_outbox_batch",
    "consume_outbox_batch",
    "get_outbox_row",
    "list_failed_outbox",
    "list_pending_outbox",
    "list_processing_outbox",
    "list_retry_pending_outbox",
    "mark_claimed_outbox_rows_published",
    "mark_outbox_row_retry_pending",
    "mark_outbox_rows_published",
    "mark_pending_outbox_published_batch",
    "recover_stale_outbox_claims",
    "requeue_outbox_rows",
    "resolve_outbox_consume_config",
    "run_outbox_worker",
    "serve_outbox_worker",
    "summarize_outbox",
]
