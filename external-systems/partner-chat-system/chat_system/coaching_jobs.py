"""Async detail-generation jobs for proactive coaching entries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from .storage import json_dumps, json_loads, row_to_dict

_STATUS_PENDING = "pending"
_STATUS_PROCESSING = "processing"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED_HIDDEN = "failed_hidden"


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def _job_result_payload(value: dict[str, Any] | None) -> str | None:
    payload = value if isinstance(value, dict) else None
    return json_dumps(payload) if payload is not None else None


def get_coaching_entry_job(conn, job_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_coaching_entry_jobs WHERE job_id = ? LIMIT 1",
        (int(job_id),),
    )
    row = row_to_dict(cur.fetchone())
    return dict(row) if row else None


def get_coaching_entry_job_by_entry_message(conn, entry_message_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_coaching_entry_jobs WHERE entry_message_id = ? LIMIT 1",
        (int(entry_message_id),),
    )
    row = row_to_dict(cur.fetchone())
    return dict(row) if row else None


def enqueue_coaching_entry_detail_job(
    conn,
    *,
    thread_id: str,
    entry_message_id: int,
    user_id: str,
    route_decision: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _ts(now)
    existing = get_coaching_entry_job_by_entry_message(conn, int(entry_message_id))
    route_payload = json_dumps(route_decision or {})

    if existing is None:
        try:
            conn.execute(
                """
                INSERT INTO chat_coaching_entry_jobs (
                  thread_id, entry_message_id, user_id, status,
                  route_decision_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(thread_id),
                    int(entry_message_id),
                    str(user_id),
                    _STATUS_PENDING,
                    route_payload,
                    ts,
                ),
            )
            conn.commit()
        except IntegrityError:
            conn.rollback()
        created = get_coaching_entry_job_by_entry_message(conn, int(entry_message_id))
        out = dict(created or {})
        out["job_enqueued"] = created is not None and existing is None
        return out

    status = str(existing.get("status") or "").strip().lower()
    if status in {_STATUS_PENDING, _STATUS_PROCESSING, _STATUS_COMPLETED}:
        out = dict(existing)
        out["job_enqueued"] = False
        return out

    conn.execute(
        """
        UPDATE chat_coaching_entry_jobs
        SET status = ?, route_decision_json = ?, result_json = NULL,
            detail_message_id = NULL, created_at = ?, processed_at = NULL
        WHERE job_id = ?
        """,
        (_STATUS_PENDING, route_payload, ts, int(existing["job_id"])),
    )
    conn.commit()
    refreshed = get_coaching_entry_job(conn, int(existing["job_id"]))
    out = dict(refreshed or {})
    out["job_enqueued"] = True
    return out


def list_pending_coaching_entry_jobs(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        """
        SELECT * FROM chat_coaching_entry_jobs
        WHERE status = ?
        ORDER BY job_id ASC
        LIMIT ?
        """,
        (_STATUS_PENDING, lim),
    )
    return [dict(r) for r in cur.fetchall()]


def _finish_job(
    conn,
    *,
    job_id: int,
    status: str,
    result: dict[str, Any] | None,
    detail_message_id: int | None,
    now: datetime | None = None,
) -> None:
    ts = _ts(now)
    conn.execute(
        """
        UPDATE chat_coaching_entry_jobs
        SET status = ?, result_json = ?, detail_message_id = ?, processed_at = ?
        WHERE job_id = ?
        """,
        (
            str(status),
            _job_result_payload(result),
            int(detail_message_id) if detail_message_id is not None else None,
            ts,
            int(job_id),
        ),
    )
    conn.commit()


def process_pending_coaching_entry_jobs(
    conn,
    *,
    limit: int = 20,
    now: datetime | None = None,
) -> dict[str, Any]:
    from .service import (
        _assistant_entry_detail_metadata,
        _assistant_generate_coaching_entry_detail,
        _load_coaching_entry,
        _update_message_metadata,
        get_thread,
    )

    ts = _ts(now)
    rows = list_pending_coaching_entry_jobs(conn, limit=limit)
    completed = 0
    failed_hidden = 0

    for row in rows:
        job_id = int(row["job_id"])
        thread_id = str(row["thread_id"])
        entry_message_id = int(row["entry_message_id"])
        user_id = str(row["user_id"])

        claimed = conn.execute(
            """
            UPDATE chat_coaching_entry_jobs
            SET status = ?
            WHERE job_id = ? AND status = ?
            """,
            (_STATUS_PROCESSING, job_id, _STATUS_PENDING),
        )
        conn.commit()
        if int(getattr(claimed, "rowcount", 0) or 0) <= 0:
            continue

        entry: dict[str, Any] | None = None
        entry_meta: dict[str, Any] | None = None
        try:
            entry = _load_coaching_entry(
                conn,
                thread_id,
                entry_message_id,
                recipient_user_id=user_id,
            )
            entry_meta = dict(entry.get("metadata") or {})
            entry_meta = _assistant_entry_detail_metadata(
                entry_meta,
                detail_status="processing",
                detail_job_id=job_id,
            )
            _update_message_metadata(conn, entry_message_id, entry_meta, now=ts)

            thread = get_thread(conn, thread_id)
            if not thread:
                raise ValueError("thread not found")

            route_decision = json_loads(row.get("route_decision_json"), {})
            if not route_decision:
                trace = dict(entry_meta.get("assistant_trace") or {})
                route_decision = dict(trace.get("route_decision") or {})

            out = _assistant_generate_coaching_entry_detail(
                conn,
                thread,
                user_id,
                entry_message_id,
                route_decision=route_decision,
                now=ts,
            )
            if bool(out.get("assistant_hidden")):
                hidden_reason = str(out.get("assistant_hidden_reason") or "guidance_error")
                failed_meta = _assistant_entry_detail_metadata(
                    entry_meta,
                    detail_status="hidden_failed",
                    detail_hidden_reason=hidden_reason,
                    detail_message_id=None,
                    detail_processed_at=ts.isoformat(sep=" "),
                    detail_job_id=job_id,
                )
                _update_message_metadata(conn, entry_message_id, failed_meta, now=ts)
                _finish_job(
                    conn,
                    job_id=job_id,
                    status=_STATUS_FAILED_HIDDEN,
                    result={
                        "ok": False,
                        "assistant_hidden": True,
                        "assistant_hidden_reason": hidden_reason,
                    },
                    detail_message_id=None,
                    now=ts,
                )
                failed_hidden += 1
                continue

            detail_message_id = int(out["message_id"])
            ready_meta = _assistant_entry_detail_metadata(
                entry_meta,
                detail_status="ready",
                detail_hidden_reason=None,
                detail_message_id=detail_message_id,
                detail_processed_at=ts.isoformat(sep=" "),
                detail_job_id=job_id,
            )
            _update_message_metadata(conn, entry_message_id, ready_meta, now=ts)
            _finish_job(
                conn,
                job_id=job_id,
                status=_STATUS_COMPLETED,
                result={"ok": True, "detail_message_id": detail_message_id},
                detail_message_id=detail_message_id,
                now=ts,
            )
            completed += 1
        except Exception as exc:  # noqa: BLE001
            if entry is not None and entry_meta is not None:
                failed_meta = _assistant_entry_detail_metadata(
                    entry_meta,
                    detail_status="hidden_failed",
                    detail_hidden_reason="job_error",
                    detail_message_id=None,
                    detail_processed_at=ts.isoformat(sep=" "),
                    detail_job_id=job_id,
                )
                _update_message_metadata(conn, entry_message_id, failed_meta, now=ts)
            _finish_job(
                conn,
                job_id=job_id,
                status=_STATUS_FAILED_HIDDEN,
                result={
                    "ok": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                detail_message_id=None,
                now=ts,
            )
            failed_hidden += 1

    return {
        "examined": len(rows),
        "completed": completed,
        "failed_hidden": failed_hidden,
    }


__all__ = [
    "enqueue_coaching_entry_detail_job",
    "get_coaching_entry_job",
    "get_coaching_entry_job_by_entry_message",
    "list_pending_coaching_entry_jobs",
    "process_pending_coaching_entry_jobs",
]
