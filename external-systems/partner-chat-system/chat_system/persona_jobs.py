"""Heuristic persona sync jobs from chat messages (``docs/chat-agent-architecture.md`` §7)."""

from __future__ import annotations

import os
from typing import Any

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from datetime import datetime

from match_domain.trace_context import get_trace_id
from observability import CHAT_FUNNEL_PERSONA_JOB_ENQUEUED, funnel_stage
from skill_runtime import ensure_persona_memory_skill_on_path

from .storage import json_dumps, json_loads, row_to_dict

_ASSISTANT = "assistant"
_SRC_USER = "user"
_VIS_DYADIC = "dyadic"
_VIS_OWNER_ONLY = "owner_only"


def _ts(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


# Substrings that suggest the author is stating profile-relevant facts about themselves.
PERSONA_HINT_MARKERS: tuple[str, ...] = (
    "工作",
    "职业",
    "收入",
    "月薪",
    "年薪",
    "择偶",
    "定居",
    "买房",
    "购房",
    "未婚",
    "离异",
    "爱好",
    "抽烟",
    "喝酒",
    "身高",
    "恋爱",
    "结婚",
    "老家",
    "本科",
    "硕士",
    "博士",
)


def body_suggests_persona_update(body: str) -> bool:
    text = (body or "").strip()
    if len(text) < 2:
        return False
    return any(m in text for m in PERSONA_HINT_MARKERS)


def maybe_enqueue_persona_sync_job(
    conn,
    thread: dict[str, Any],
    *,
    message_id: int,
    author_id: str,
    body: str,
    visibility: str,
    source: str,
    message_recipient_id: str | None,
    metadata: dict[str, Any] | None,
    ts,
) -> None:
    if source != _SRC_USER or author_id == _ASSISTANT:
        return
    msg_meta = metadata if isinstance(metadata, dict) else {}
    if bool(msg_meta.get("skip_persona_sync")):
        return
    if str(msg_meta.get("owner_only_kind") or "").strip() == "assistant_query":
        return
    pa, pb = thread["participant_a_id"], thread["participant_b_id"]
    if author_id not in (pa, pb):
        return
    if visibility == _VIS_DYADIC:
        pass
    elif visibility == _VIS_OWNER_ONLY and message_recipient_id == author_id:
        pass
    else:
        return
    if not body_suggests_persona_update(body):
        return

    evidence = json_dumps(
        {
            "conversation_ref": f"{thread['thread_id']}/{message_id}",
            "body_snippet": (body or "")[:2000],
            "reason": "keyword_heuristic",
        }
    )
    try:
        conn.execute(
            """
            INSERT INTO persona_sync_jobs (
              thread_id, message_id, subject_user_id, status, evidence_json, created_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (thread["thread_id"], int(message_id), author_id, evidence, ts),
        )
    except IntegrityError:
        return
    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_PERSONA_JOB_ENQUEUED,
        trace_id=get_trace_id(),
        case_id=str(thread.get("case_id")),
        thread_id=thread["thread_id"],
        message_id=int(message_id),
        subject_user_id=author_id,
    )


def list_pending_persona_jobs(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        """
        SELECT * FROM persona_sync_jobs
        WHERE status = 'pending'
        ORDER BY job_id ASC
        LIMIT ?
        """,
        (lim,),
    )
    return [dict(r) for r in cur.fetchall()]


def _persona_mysql_source() -> str | None:
    raw = (os.environ.get("HER_CHAT_PERSONA_MYSQL_SOURCE") or "").strip()
    return raw or None


def process_pending_persona_jobs(conn, *, limit: int = 20, now=None) -> dict[str, Any]:
    """Consume pending jobs: call persona-memory-sync when ``HER_CHAT_PERSONA_MYSQL_SOURCE`` is set; else ``needs_review``."""

    ts = _ts(now)
    rows = list_pending_persona_jobs(conn, limit=limit)
    source = _persona_mysql_source()
    applied = 0
    review = 0

    for row in rows:
        job_id = int(row["job_id"])
        subject = str(row["subject_user_id"])
        evidence = json_loads(row.get("evidence_json"), {})

        def _finish(status: str, result: dict[str, Any]) -> None:
            conn.execute(
                """
                UPDATE persona_sync_jobs
                SET status = ?, processed_at = ?, sync_result_json = ?
                WHERE job_id = ? AND status = 'pending'
                """,
                (status, ts, json_dumps(result), job_id),
            )

        if not source:
            _finish(
                "needs_review",
                {"skipped": True, "reason": "HER_CHAT_PERSONA_MYSQL_SOURCE unset"},
            )
            review += 1
            continue

        try:
            ensure_persona_memory_skill_on_path()
            from persona_memory_sync import upsert_persona_memory  # noqa: PLC0415

            conv = str(evidence.get("conversation_ref") or "")
            snippet = str(evidence.get("body_snippet") or "")
            result = upsert_persona_memory(
                {
                    "source": source,
                    "user_key": subject,
                    "source_type": "chat_message",
                    "patch": {},
                    "evidence_text": snippet,
                    "conversation_ref": conv,
                    "sync_profile": False,
                }
            )
            _finish("applied", {"ok": True, "upsert": result})
            applied += 1
        except Exception as exc:  # noqa: BLE001
            _finish(
                "needs_review",
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__},
            )
            review += 1

    conn.commit()
    return {"examined": len(rows), "applied": applied, "needs_review": review}


def get_persona_job(conn, job_id: int) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM persona_sync_jobs WHERE job_id = ? LIMIT 1", (job_id,))
    row = row_to_dict(cur.fetchone())
    return dict(row) if row else None


__all__ = [
    "PERSONA_HINT_MARKERS",
    "body_suggests_persona_update",
    "get_persona_job",
    "list_pending_persona_jobs",
    "maybe_enqueue_persona_sync_job",
    "process_pending_persona_jobs",
]
