"""Photo analysis event bus and async job subscriber."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping

import outer_system_mysql_schema as schema
from async_jobs import AsyncJobHandler, enqueue_async_job, run_async_job_worker
from outer_mysql_compat import MySQLCompatConnection
from partner_moderation import current_time

from .outbox import SyncEventBus


PHOTO_EVENT_TYPE_UPLOADED = "photo_uploaded"
PHOTO_EVENT_TYPE_REPLACED = "photo_replaced"
PHOTO_EVENT_TYPE_DELETED = "photo_deleted"
PHOTO_EVENT_TYPES = {
    PHOTO_EVENT_TYPE_UPLOADED,
    PHOTO_EVENT_TYPE_REPLACED,
    PHOTO_EVENT_TYPE_DELETED,
}
PHOTO_ANALYSIS_JOB_TYPE = "photo_feature_refresh"


@dataclass(frozen=True)
class PhotoAnalysisEvent:
    event_type: str
    profile_id: int
    persona_source_dsn: str
    profile_source_dsn: str
    source_table_name: str
    photos_table_name: str | None = None
    trigger_fields: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=current_time)

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "profile_id": int(self.profile_id),
            "persona_source_dsn": self.persona_source_dsn,
            "profile_source_dsn": self.profile_source_dsn,
            "source_table_name": self.source_table_name,
            "photos_table_name": self.photos_table_name,
            "trigger_fields": list(self.trigger_fields),
            "metadata": dict(self.metadata),
            "occurred_at": str(self.occurred_at),
        }


_PHOTO_EVENT_BUS = SyncEventBus()
_ASYNC_SUBSCRIBER_REGISTERED = False


def subscribe_photo_analysis_events(handler: Callable[[PhotoAnalysisEvent], None]) -> None:
    _PHOTO_EVENT_BUS.subscribe(handler)


def clear_photo_analysis_subscribers() -> None:
    global _ASYNC_SUBSCRIBER_REGISTERED
    _PHOTO_EVENT_BUS.clear()
    _ASYNC_SUBSCRIBER_REGISTERED = False


def build_photo_analysis_event(
    *,
    event_type: str,
    profile_id: int,
    persona_source_dsn: str,
    profile_source_dsn: str,
    source_table_name: str,
    photos_table_name: str | None = None,
    trigger_fields: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> PhotoAnalysisEvent:
    normalized_type = str(event_type or "").strip()
    if normalized_type not in PHOTO_EVENT_TYPES:
        raise ValueError(f"unsupported_photo_event_type:{normalized_type}")
    normalized_profile_id = int(profile_id or 0)
    if normalized_profile_id <= 0:
        raise ValueError("profile_id is required")
    return PhotoAnalysisEvent(
        event_type=normalized_type,
        profile_id=normalized_profile_id,
        persona_source_dsn=str(persona_source_dsn or "").strip(),
        profile_source_dsn=str(profile_source_dsn or "").strip(),
        source_table_name=str(source_table_name or "").strip(),
        photos_table_name=str(photos_table_name or "").strip() or None,
        trigger_fields=[str(item) for item in list(trigger_fields or []) if str(item).strip()],
        metadata=dict(metadata or {}),
    )


def _connect_job_db(source_dsn: str) -> MySQLCompatConnection:
    config = schema.parse_mysql_dsn(str(source_dsn))
    raw = schema.mysql_database_connect(config)
    return MySQLCompatConnection(raw, config)


def enqueue_photo_analysis_job_from_event(event: PhotoAnalysisEvent) -> dict[str, Any] | None:
    payload = event.to_payload()
    persona_source_dsn = str(payload.get("persona_source_dsn") or "").strip()
    if not persona_source_dsn:
        return None
    conn = _connect_job_db(persona_source_dsn)
    try:
        return enqueue_async_job(
            conn,
            job_type=PHOTO_ANALYSIS_JOB_TYPE,
            payload=payload,
            created_by="photo_event_bus",
            trace_id=f"photo:{payload['profile_id']}",
            max_attempts=3,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def ensure_photo_analysis_async_subscription() -> None:
    global _ASYNC_SUBSCRIBER_REGISTERED
    if _ASYNC_SUBSCRIBER_REGISTERED:
        return

    def _subscriber(event: PhotoAnalysisEvent) -> None:
        enqueue_photo_analysis_job_from_event(event)

    subscribe_photo_analysis_events(_subscriber)
    _ASYNC_SUBSCRIBER_REGISTERED = True


def publish_photo_analysis_event(event: PhotoAnalysisEvent) -> None:
    ensure_photo_analysis_async_subscription()
    _PHOTO_EVENT_BUS.publish(event)


def _handle_photo_analysis_job(_conn: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    from match_domain.appearance_features import refresh_profile_photo_features

    result = refresh_profile_photo_features(
        source_dsn=str(payload.get("persona_source_dsn") or "").strip(),
        profile_id=int(payload.get("profile_id") or 0),
        profile_source_dsn=str(payload.get("profile_source_dsn") or "").strip(),
        source_table_name=str(payload.get("source_table_name") or "").strip() or None,
        photos_table_name=str(payload.get("photos_table_name") or "").strip() or None,
        sync_embedding=False,
    )
    return {
        "profile_id": int(payload.get("profile_id") or 0),
        "event_type": str(payload.get("event_type") or ""),
        "analysis_status": result.get("analysis_status"),
    }


def run_photo_analysis_job_worker(
    *,
    source_dsn: str,
    limit: int = 10,
    worker_name: str = "photo-analysis-worker",
) -> dict[str, Any]:
    conn = _connect_job_db(source_dsn)
    try:
        return run_async_job_worker(
            conn,
            handlers={
                PHOTO_ANALYSIS_JOB_TYPE: AsyncJobHandler(
                    job_type=PHOTO_ANALYSIS_JOB_TYPE,
                    execute_fn=_handle_photo_analysis_job,
                    max_attempts=3,
                ),
            },
            limit=limit,
            worker_name=worker_name,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


__all__ = [
    "PHOTO_ANALYSIS_JOB_TYPE",
    "PHOTO_EVENT_TYPE_DELETED",
    "PHOTO_EVENT_TYPE_REPLACED",
    "PHOTO_EVENT_TYPE_UPLOADED",
    "PHOTO_EVENT_TYPES",
    "PhotoAnalysisEvent",
    "build_photo_analysis_event",
    "clear_photo_analysis_subscribers",
    "enqueue_photo_analysis_job_from_event",
    "ensure_photo_analysis_async_subscription",
    "publish_photo_analysis_event",
    "run_photo_analysis_job_worker",
    "subscribe_photo_analysis_events",
]
