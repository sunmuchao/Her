"""Pending profile update proposals and confirm/reject for discovery chat."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from match_domain.profile_write_guard import build_profile_change_rows, split_persona_patch

from .storage import StoredSession


class ProfileUpdateRequestNotFoundError(LookupError):
    pass


class ProfileUpdateRequestConflictError(ValueError):
    pass


def _utcnow(now: datetime | None = None) -> datetime:
    return now or datetime.now()


def _new_request_id() -> str:
    return f"pur-{uuid4().hex[:16]}"


def propose_profile_update(
    storage: Any,
    session: StoredSession,
    *,
    patch: dict[str, Any],
    evidence_text: str | None = None,
    current_profile: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    profile_part, _persona_part, _search_part = split_persona_patch(patch)
    if not profile_part:
        return {
            "proposed": False,
            "error_code": "empty_profile_patch",
            "message": "没有需要确认的资料字段。",
        }

    changes = build_profile_change_rows(current_profile=current_profile, proposed_patch=profile_part)
    if not changes:
        return {
            "proposed": False,
            "error_code": "no_profile_changes",
            "message": "资料没有实际变化。",
        }

    compact_changes = [
        {
            "field": row.get("field"),
            "label": row.get("label") or row.get("field"),
            "from": row.get("from"),
            "to": row.get("to"),
        }
        for row in changes[:3]
    ]

    ts = _utcnow(now)
    request_id = _new_request_id()
    record = storage.create_profile_update_request(
        request_id=request_id,
        session_id=session.session_id,
        profile_id=int(session.profile_id),
        proposed_patch=profile_part,
        current_snapshot=dict(current_profile or {}),
        evidence_text=str(evidence_text or "").strip() or None,
        expires_at=ts + timedelta(days=7),
        created_at=ts,
    )
    pending_ids = list(session.state.get("pending_profile_update_ids") or [])
    pending_ids.append(record["request_id"])
    session.state["pending_profile_update_ids"] = pending_ids[-5:]

    return {
        "proposed": True,
        "request_id": record["request_id"],
        "status": record["status"],
        "changes": compact_changes,
        "title": "更新资料",
        "summary": "",
    }


def confirm_profile_update(
    storage: Any,
    session: StoredSession,
    *,
    request_id: str,
    apply_profile_updates_fn: Any,
    source_dsn: str,
    source_table_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    record = _require_pending_request(storage, session, request_id)
    ts = _utcnow(now)
    apply_profile_updates_fn(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=int(session.profile_id),
        updates=dict(record.get("proposed_patch") or {}),
    )
    storage.mark_profile_update_request(
        request_id=request_id,
        status="confirmed",
        now=ts,
    )
    return {
        "ok": True,
        "request_id": request_id,
        "status": "confirmed",
        "applied_fields": sorted(str(key) for key in dict(record.get("proposed_patch") or {}).keys()),
    }


def reject_profile_update(
    storage: Any,
    session: StoredSession,
    *,
    request_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    _require_pending_request(storage, session, request_id)
    ts = _utcnow(now)
    storage.mark_profile_update_request(
        request_id=request_id,
        status="rejected",
        now=ts,
    )
    return {
        "ok": True,
        "request_id": request_id,
        "status": "rejected",
    }


def _require_pending_request(storage: Any, session: StoredSession, request_id: str) -> dict[str, Any]:
    record = storage.get_profile_update_request(str(request_id or "").strip())
    if not record:
        raise ProfileUpdateRequestNotFoundError(f"profile update request not found: {request_id}")
    if str(record.get("session_id") or "") != session.session_id:
        raise ProfileUpdateRequestNotFoundError("profile update request does not belong to this session")
    if int(record.get("profile_id") or 0) != int(session.profile_id):
        raise ProfileUpdateRequestNotFoundError("profile update request profile mismatch")
    if str(record.get("status") or "") != "pending":
        raise ProfileUpdateRequestConflictError(f"profile update request is not pending: {record.get('status')}")
    expires_at = record.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at < datetime.now():
        raise ProfileUpdateRequestConflictError("profile update request expired")
    return record


def profile_update_prompt_item(
    *,
    item_id: str,
    request: dict[str, Any],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_type": "profile_update_prompt",
        "item_id": item_id,
        "prompt": {
            "request_id": request.get("request_id"),
            "title": request.get("title") or "更新资料",
            "summary": request.get("summary") or "",
            "changes": list(request.get("changes") or []),
            "status": request.get("status") or "pending",
        },
    }
    if created_at is not None:
        item["created_at"] = created_at.isoformat()
    return item


__all__ = [
    "ProfileUpdateRequestConflictError",
    "ProfileUpdateRequestNotFoundError",
    "confirm_profile_update",
    "profile_update_prompt_item",
    "propose_profile_update",
    "reject_profile_update",
]
