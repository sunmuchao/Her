"""Generic persisted async job queue for outer systems."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from outer_mysql_compat import json_dumps, json_loads, row_to_dict
from outer_system_mysql_schema import ASYNC_JOB_TABLE

ASYNC_JOB_PENDING = "pending"
ASYNC_JOB_PROCESSING = "processing"
ASYNC_JOB_RETRY_PENDING = "retry_pending"
ASYNC_JOB_SUCCEEDED = "succeeded"
ASYNC_JOB_FAILED = "failed"


def current_time(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return current_time(value).isoformat(sep=" ")


def _generate_job_id() -> str:
    return f"job-{uuid.uuid4().hex[:16]}"


def _inflate_job(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    raw = row_to_dict(row)
    if not raw:
        return None
    out = dict(raw)
    out["payload"] = json_loads(out.pop("payload_json", None), {})
    out["result"] = json_loads(out.pop("result_json", None), None)
    out["attempt_count"] = int(out.get("attempt_count") or 0)
    out["max_attempts"] = int(out.get("max_attempts") or 0)
    return out


def _empty_async_job_status_counts() -> dict[str, int]:
    return {
        ASYNC_JOB_PENDING: 0,
        ASYNC_JOB_PROCESSING: 0,
        ASYNC_JOB_RETRY_PENDING: 0,
        ASYNC_JOB_SUCCEEDED: 0,
        ASYNC_JOB_FAILED: 0,
    }


def _build_async_job_summary(
    status_counts: Mapping[str, int],
    *,
    due_now: int,
    processing_overdue: int,
    oldest_due_created_at: str | None,
    latest_finished_at: str | None,
) -> dict[str, Any]:
    normalized = _empty_async_job_status_counts()
    for status in normalized:
        normalized[status] = int(status_counts.get(status) or 0)
    total = sum(normalized.values())
    backlog_open = (
        normalized[ASYNC_JOB_PENDING]
        + normalized[ASYNC_JOB_RETRY_PENDING]
        + normalized[ASYNC_JOB_PROCESSING]
    )
    return {
        "total": total,
        "backlog_open": backlog_open,
        "due_now": int(due_now),
        "processing_overdue": int(processing_overdue),
        "oldest_due_created_at": oldest_due_created_at,
        "latest_finished_at": latest_finished_at,
        "by_status": normalized,
    }


def get_async_job(conn, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM async_jobs WHERE job_id = ? LIMIT 1",
        (job_id,),
    ).fetchone()
    return _inflate_job(row)


def list_async_jobs(
    conn,
    *,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM async_jobs"
    params: list[Any] = []
    if statuses:
        placeholders = ", ".join(["?"] * len(statuses))
        sql += f" WHERE status IN ({placeholders})"
        params.extend(statuses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(int(limit), 1))
    rows = conn.execute(sql, params).fetchall()
    return [item for item in (_inflate_job(row) for row in rows) if item]


def summarize_async_jobs(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
) -> dict[str, Any]:
    ts = current_time(now)
    status_counts = _empty_async_job_status_counts()
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM async_jobs
        GROUP BY status
        """
    ).fetchall()
    for row in rows:
        raw = row_to_dict(row) or {}
        status = str(raw.get("status") or "")
        if status in status_counts:
            status_counts[status] = int(raw.get("c") or 0)
    due_now_row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM async_jobs
        WHERE status = ?
           OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
        """,
        (ASYNC_JOB_PENDING, ASYNC_JOB_RETRY_PENDING, format_dt(ts)),
    ).fetchone()
    processing_cutoff = format_dt(ts - timedelta(seconds=max(int(claim_timeout_seconds), 1)))
    overdue_row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM async_jobs
        WHERE status = ?
          AND claim_started_at IS NOT NULL
          AND claim_started_at < ?
        """,
        (ASYNC_JOB_PROCESSING, processing_cutoff),
    ).fetchone()
    oldest_due_row = conn.execute(
        """
        SELECT created_at
        FROM async_jobs
        WHERE status = ?
           OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
        ORDER BY COALESCE(next_attempt_at, created_at) ASC, created_at ASC
        LIMIT 1
        """,
        (ASYNC_JOB_PENDING, ASYNC_JOB_RETRY_PENDING, format_dt(ts)),
    ).fetchone()
    latest_finished_row = conn.execute(
        """
        SELECT finished_at
        FROM async_jobs
        WHERE status IN (?, ?)
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (ASYNC_JOB_SUCCEEDED, ASYNC_JOB_FAILED),
    ).fetchone()
    return _build_async_job_summary(
        status_counts,
        due_now=int((due_now_row or {}).get("c") or 0),
        processing_overdue=int((overdue_row or {}).get("c") or 0),
        oldest_due_created_at=(row_to_dict(oldest_due_row) or {}).get("created_at"),
        latest_finished_at=(row_to_dict(latest_finished_row) or {}).get("finished_at"),
    )


def summarize_async_jobs_by_type(
    conn,
    *,
    now: datetime | None = None,
    claim_timeout_seconds: int = 300,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ts = current_time(now)
    processing_cutoff = format_dt(ts - timedelta(seconds=max(int(claim_timeout_seconds), 1)))
    sql = """
        SELECT
          job_type,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS pending_count,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS processing_count,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS retry_pending_count,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS succeeded_count,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failed_count,
          SUM(CASE WHEN status IN (?, ?, ?) THEN 1 ELSE 0 END) AS backlog_open_count,
          SUM(CASE WHEN status = ? OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?)) THEN 1 ELSE 0 END) AS due_now_count,
          SUM(CASE WHEN status = ? AND claim_started_at IS NOT NULL AND claim_started_at < ? THEN 1 ELSE 0 END) AS processing_overdue_count,
          MIN(CASE WHEN status = ? OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?)) THEN created_at ELSE NULL END) AS oldest_due_created_at,
          MAX(CASE WHEN status IN (?, ?) THEN finished_at ELSE NULL END) AS latest_finished_at,
          COUNT(*) AS total_count
        FROM async_jobs
        GROUP BY job_type
        ORDER BY backlog_open_count DESC, due_now_count DESC, failed_count DESC, total_count DESC, job_type ASC
    """
    params: list[Any] = [
        ASYNC_JOB_PENDING,
        ASYNC_JOB_PROCESSING,
        ASYNC_JOB_RETRY_PENDING,
        ASYNC_JOB_SUCCEEDED,
        ASYNC_JOB_FAILED,
        ASYNC_JOB_PENDING,
        ASYNC_JOB_RETRY_PENDING,
        ASYNC_JOB_PROCESSING,
        ASYNC_JOB_PENDING,
        ASYNC_JOB_RETRY_PENDING,
        format_dt(ts),
        ASYNC_JOB_PROCESSING,
        processing_cutoff,
        ASYNC_JOB_PENDING,
        ASYNC_JOB_RETRY_PENDING,
        format_dt(ts),
        ASYNC_JOB_SUCCEEDED,
        ASYNC_JOB_FAILED,
    ]
    if limit is not None:
        sql += "\nLIMIT ?"
        params.append(max(int(limit), 1))
    rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = row_to_dict(row) or {}
        status_counts = {
            ASYNC_JOB_PENDING: int(raw.get("pending_count") or 0),
            ASYNC_JOB_PROCESSING: int(raw.get("processing_count") or 0),
            ASYNC_JOB_RETRY_PENDING: int(raw.get("retry_pending_count") or 0),
            ASYNC_JOB_SUCCEEDED: int(raw.get("succeeded_count") or 0),
            ASYNC_JOB_FAILED: int(raw.get("failed_count") or 0),
        }
        summary = _build_async_job_summary(
            status_counts,
            due_now=int(raw.get("due_now_count") or 0),
            processing_overdue=int(raw.get("processing_overdue_count") or 0),
            oldest_due_created_at=str(raw.get("oldest_due_created_at")) if raw.get("oldest_due_created_at") is not None else None,
            latest_finished_at=str(raw.get("latest_finished_at")) if raw.get("latest_finished_at") is not None else None,
        )
        out.append({"job_type": str(raw.get("job_type") or ""), **summary})
    return out


def enqueue_async_job(
    conn,
    *,
    job_type: str,
    payload: Mapping[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    job_id = _generate_job_id()
    conn.execute(
        """
        INSERT INTO async_jobs (
          job_id,
          job_type,
          status,
          payload_json,
          result_json,
          error_text,
          attempt_count,
          max_attempts,
          next_attempt_at,
          created_by,
          trace_id,
          claim_token,
          claim_started_at,
          claim_worker,
          created_at,
          started_at,
          finished_at
        ) VALUES (?, ?, ?, ?, NULL, NULL, 0, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
        """,
        (
            job_id,
            job_type,
            ASYNC_JOB_PENDING,
            json_dumps(dict(payload or {})),
            max(int(max_attempts), 1),
            format_dt(ts),
            created_by,
            trace_id,
            format_dt(ts),
        ),
    )
    conn.commit()
    job = get_async_job(conn, job_id)
    if job is None:
        raise RuntimeError(f"failed to load async job after insert: {job_id}")
    return job


@dataclass(frozen=True)
class AsyncJobHandler:
    job_type: str
    execute_fn: Callable[[Any, Mapping[str, Any]], Any]
    max_attempts: int = 3


def _mark_timed_out_jobs(
    conn,
    *,
    now: datetime,
    claim_timeout_seconds: int,
) -> int:
    cutoff = format_dt(now - timedelta(seconds=max(int(claim_timeout_seconds), 1)))
    rows = conn.execute(
        """
        SELECT job_id, attempt_count, max_attempts
        FROM async_jobs
        WHERE status = ?
          AND claim_started_at IS NOT NULL
          AND claim_started_at < ?
        ORDER BY claim_started_at ASC
        """,
        (ASYNC_JOB_PROCESSING, cutoff),
    ).fetchall()
    recovered = 0
    for row in rows:
        raw = row_to_dict(row) or {}
        attempt_count = int(raw.get("attempt_count") or 0)
        max_attempts = int(raw.get("max_attempts") or 1)
        if attempt_count >= max_attempts:
            conn.execute(
                """
                UPDATE async_jobs
                SET status = ?,
                    error_text = ?,
                    claim_token = NULL,
                    claim_started_at = NULL,
                    claim_worker = NULL,
                    next_attempt_at = NULL,
                    finished_at = ?
                WHERE job_id = ?
                  AND status = ?
                """,
                (
                    ASYNC_JOB_FAILED,
                    "processing_timeout",
                    format_dt(now),
                    raw["job_id"],
                    ASYNC_JOB_PROCESSING,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE async_jobs
                SET status = ?,
                    error_text = ?,
                    claim_token = NULL,
                    claim_started_at = NULL,
                    claim_worker = NULL,
                    next_attempt_at = ?
                WHERE job_id = ?
                  AND status = ?
                """,
                (
                    ASYNC_JOB_RETRY_PENDING,
                    "processing_timeout",
                    format_dt(now),
                    raw["job_id"],
                    ASYNC_JOB_PROCESSING,
                ),
            )
        recovered += 1
    if recovered:
        conn.commit()
    return recovered


def _claim_due_job(
    conn,
    *,
    now: datetime,
    worker_name: str,
) -> dict[str, Any] | None:
    candidate = conn.execute(
        """
        SELECT job_id
        FROM async_jobs
        WHERE status = ?
           OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
        ORDER BY
          CASE WHEN status = ? THEN 0 ELSE 1 END,
          COALESCE(next_attempt_at, created_at) ASC,
          created_at ASC
        LIMIT 1
        """,
        (
            ASYNC_JOB_PENDING,
            ASYNC_JOB_RETRY_PENDING,
            format_dt(now),
            ASYNC_JOB_PENDING,
        ),
    ).fetchone()
    raw = row_to_dict(candidate)
    if not raw:
        return None
    claim_token = uuid.uuid4().hex
    updated = conn.execute(
        """
        UPDATE async_jobs
        SET status = ?,
            claim_token = ?,
            claim_started_at = ?,
            claim_worker = ?,
            started_at = COALESCE(started_at, ?),
            finished_at = NULL,
            attempt_count = attempt_count + 1
        WHERE job_id = ?
          AND (status = ? OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?)))
        """,
        (
            ASYNC_JOB_PROCESSING,
            claim_token,
            format_dt(now),
            worker_name[:191],
            format_dt(now),
            raw["job_id"],
            ASYNC_JOB_PENDING,
            ASYNC_JOB_RETRY_PENDING,
            format_dt(now),
        ),
    ).rowcount
    if updated <= 0:
        conn.rollback()
        return None
    conn.commit()
    row = conn.execute(
        "SELECT * FROM async_jobs WHERE job_id = ? AND claim_token = ? LIMIT 1",
        (raw["job_id"], claim_token),
    ).fetchone()
    return _inflate_job(row)


def _next_retry_at(
    *,
    now: datetime,
    attempt_count: int,
    retry_delay_seconds: int,
    retry_backoff_multiplier: int,
    retry_max_delay_seconds: int,
) -> datetime:
    base = max(int(retry_delay_seconds), 1)
    multiplier = max(int(retry_backoff_multiplier), 1)
    max_delay = max(int(retry_max_delay_seconds), base)
    delay = base * (multiplier ** max(attempt_count - 1, 0))
    delay = min(delay, max_delay)
    return now + timedelta(seconds=delay)


def run_async_job_worker(
    conn,
    *,
    handlers: Mapping[str, AsyncJobHandler],
    limit: int = 10,
    retry_delay_seconds: int = 15,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int = 300,
    claim_timeout_seconds: int = 300,
    worker_name: str = "async-job-worker",
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    recovered_count = _mark_timed_out_jobs(conn, now=ts, claim_timeout_seconds=claim_timeout_seconds)
    processed: list[dict[str, Any]] = []
    success_count = 0
    retry_count = 0
    failed_count = 0
    skipped_unknown = 0
    for _ in range(max(int(limit), 1)):
        job = _claim_due_job(conn, now=ts, worker_name=worker_name)
        if job is None:
            break
        handler = handlers.get(str(job["job_type"]))
        if handler is None:
            conn.execute(
                """
                UPDATE async_jobs
                SET status = ?,
                    error_text = ?,
                    claim_token = NULL,
                    claim_started_at = NULL,
                    claim_worker = NULL,
                    finished_at = ?
                WHERE job_id = ?
                """,
                (
                    ASYNC_JOB_FAILED,
                    f"unknown_job_type:{job['job_type']}",
                    format_dt(ts),
                    job["job_id"],
                ),
            )
            conn.commit()
            failed_count += 1
            skipped_unknown += 1
            processed.append({"job_id": job["job_id"], "job_type": job["job_type"], "status": ASYNC_JOB_FAILED})
            continue
        try:
            result = handler.execute_fn(conn, job["payload"])
        except Exception as exc:
            attempt_count = int(job.get("attempt_count") or 0)
            if attempt_count >= int(job.get("max_attempts") or handler.max_attempts):
                conn.execute(
                    """
                    UPDATE async_jobs
                    SET status = ?,
                        result_json = NULL,
                        error_text = ?,
                        claim_token = NULL,
                        claim_started_at = NULL,
                        claim_worker = NULL,
                        finished_at = ?,
                        next_attempt_at = NULL
                    WHERE job_id = ?
                    """,
                    (
                        ASYNC_JOB_FAILED,
                        str(exc),
                        format_dt(ts),
                        job["job_id"],
                    ),
                )
                conn.commit()
                failed_count += 1
                processed.append(
                    {
                        "job_id": job["job_id"],
                        "job_type": job["job_type"],
                        "status": ASYNC_JOB_FAILED,
                        "error": str(exc),
                    }
                )
            else:
                next_retry_at = _next_retry_at(
                    now=ts,
                    attempt_count=attempt_count,
                    retry_delay_seconds=retry_delay_seconds,
                    retry_backoff_multiplier=retry_backoff_multiplier,
                    retry_max_delay_seconds=retry_max_delay_seconds,
                )
                conn.execute(
                    """
                    UPDATE async_jobs
                    SET status = ?,
                        result_json = NULL,
                        error_text = ?,
                        claim_token = NULL,
                        claim_started_at = NULL,
                        claim_worker = NULL,
                        next_attempt_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        ASYNC_JOB_RETRY_PENDING,
                        str(exc),
                        format_dt(next_retry_at),
                        job["job_id"],
                    ),
                )
                conn.commit()
                retry_count += 1
                processed.append(
                    {
                        "job_id": job["job_id"],
                        "job_type": job["job_type"],
                        "status": ASYNC_JOB_RETRY_PENDING,
                        "error": str(exc),
                        "next_attempt_at": format_dt(next_retry_at),
                    }
                )
            continue
        conn.execute(
            """
            UPDATE async_jobs
            SET status = ?,
                result_json = ?,
                error_text = NULL,
                claim_token = NULL,
                claim_started_at = NULL,
                claim_worker = NULL,
                finished_at = ?,
                next_attempt_at = NULL
            WHERE job_id = ?
            """,
            (
                ASYNC_JOB_SUCCEEDED,
                json_dumps(result),
                format_dt(ts),
                job["job_id"],
            ),
        )
        conn.commit()
        success_count += 1
        processed.append(
            {
                "job_id": job["job_id"],
                "job_type": job["job_type"],
                "status": ASYNC_JOB_SUCCEEDED,
            }
        )
    return {
        "processed_count": len(processed),
        "success_count": success_count,
        "retry_count": retry_count,
        "failed_count": failed_count,
        "recovered_count": recovered_count,
        "unknown_job_count": skipped_unknown,
        "jobs": processed,
    }
