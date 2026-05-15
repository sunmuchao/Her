"""Heuristic persona sync jobs from chat messages (``docs/chat-agent-architecture.md`` §7)."""

from __future__ import annotations

import hashlib
import zlib
from typing import Any

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from datetime import datetime

from match_domain.trace_context import get_trace_id
from observability import CHAT_FUNNEL_PERSONA_JOB_ENQUEUED, funnel_stage
from profile_service import apply_persona_patch

from .persona_source import persona_mysql_source
from .storage import json_dumps, json_loads, row_to_dict

_SRC_USER = "user"
_VIS_DYADIC = "dyadic"
_VIS_OWNER_ONLY = "owner_only"
SUPPORTED_PERSONA_SOURCE_TYPES = {"explicit", "strong_inference", "weak_inference"}
SUPPORTED_PERSONA_APPLY_SCOPES = {"observation_only", "persona_only", "persona_and_profile"}


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


def enqueue_persona_sync_job(
    conn,
    *,
    thread_id: str,
    message_id: int,
    subject_user_id: str,
    patch: dict[str, Any] | None,
    evidence: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    ts = _ts(now)
    patch_payload = dict(patch) if isinstance(patch, dict) and patch else None
    evidence_payload = dict(evidence or {})
    source_type = str(evidence_payload.get("source_type") or "").strip()
    basis = str(evidence_payload.get("basis") or "").strip()
    apply_scope = str(evidence_payload.get("apply_scope") or "").strip()
    update_key_payload = {
        "message_id": int(message_id),
        "subject_user_id": str(subject_user_id),
        "source_type": source_type,
        "basis": basis,
        "apply_scope": apply_scope,
        "patch": patch_payload or {},
    }
    update_key = hashlib.sha1(json_dumps(update_key_payload).encode("utf-8")).hexdigest()
    stored_message_id = int(message_id) * 1_000_000 + (zlib.crc32(update_key.encode("utf-8")) % 1_000_000)
    try:
        conn.execute(
            """
            INSERT INTO persona_sync_jobs (
              thread_id, message_id, subject_user_id, update_key, status, patch_json, evidence_json, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                str(thread_id),
                stored_message_id,
                str(subject_user_id),
                update_key,
                json_dumps(patch_payload) if patch_payload is not None else None,
                json_dumps(evidence_payload),
                ts,
            ),
        )
    except IntegrityError:
        return False
    funnel_stage(
        system="chat",
        stage=CHAT_FUNNEL_PERSONA_JOB_ENQUEUED,
        trace_id=get_trace_id(),
        thread_id=str(thread_id),
        message_id=stored_message_id,
        subject_user_id=str(subject_user_id),
    )
    return True


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
    # Live chat messages should not trigger persona sync directly.
    # Persona changes are decided in a dedicated post-chat review step.
    return


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

def process_pending_persona_jobs(conn, *, limit: int = 20, now=None) -> dict[str, Any]:
    """Consume pending jobs: call persona-memory-sync when ``HER_CHAT_PERSONA_MYSQL_SOURCE`` is set; else ``needs_review``."""

    ts = _ts(now)
    rows = list_pending_persona_jobs(conn, limit=limit)
    source = persona_mysql_source()
    applied = 0
    review = 0

    for row in rows:
        job_id = int(row["job_id"])
        subject = str(row["subject_user_id"])
        patch = json_loads(row.get("patch_json"), None)
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
            conv = str(evidence.get("conversation_ref") or "")
            snippet = str(evidence.get("body_snippet") or "")
            evidence_text = str(evidence.get("evidence_text") or snippet)
            source_type = str(evidence.get("source_type") or "").strip()
            apply_scope = str(evidence.get("apply_scope") or "").strip()
            raw_confidence = evidence.get("confidence_score")
            try:
                confidence_score = int(raw_confidence) if raw_confidence is not None else None
            except (TypeError, ValueError):
                confidence_score = None
            sync_profile = bool(evidence.get("sync_profile"))
            if not apply_scope:
                apply_scope = "persona_and_profile" if sync_profile else "persona_only"
            if not isinstance(patch, dict) or not patch:
                _finish(
                    "needs_review",
                    {
                        "skipped": True,
                        "reason": "missing_persona_patch",
                        "evidence_reason": str(evidence.get("reason") or ""),
                    },
                )
                review += 1
                continue
            if source_type not in SUPPORTED_PERSONA_SOURCE_TYPES:
                _finish(
                    "needs_review",
                    {
                        "skipped": True,
                        "reason": "unsupported_source_type",
                        "source_type": source_type,
                    },
                )
                review += 1
                continue
            if apply_scope not in SUPPORTED_PERSONA_APPLY_SCOPES:
                _finish(
                    "needs_review",
                    {
                        "skipped": True,
                        "reason": "unsupported_apply_scope",
                        "apply_scope": apply_scope,
                    },
                )
                review += 1
                continue
            result = apply_persona_patch(
                {
                    "source": source,
                    "user_key": subject,
                    "source_type": source_type,
                    "patch": patch,
                    "confidence_score": confidence_score,
                    "evidence_text": evidence_text,
                    "conversation_ref": conv,
                    "sync_profile": apply_scope == "persona_and_profile",
                    "apply_scope": apply_scope,
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
    "SUPPORTED_PERSONA_SOURCE_TYPES",
    "PERSONA_HINT_MARKERS",
    "body_suggests_persona_update",
    "enqueue_persona_sync_job",
    "get_persona_job",
    "list_pending_persona_jobs",
    "maybe_enqueue_persona_sync_job",
    "process_pending_persona_jobs",
]
