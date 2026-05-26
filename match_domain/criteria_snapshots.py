"""In-memory + optional persistence for criteria compile snapshots (§13.1.2)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlparse

from her_time_utils import current_time, format_dt


@dataclass
class CriteriaSnapshotRecord:
    snapshot_id: int
    scene: str
    criteria_hash: str
    compiled_json: dict[str, Any]
    source_map_json: dict[str, Any]
    runtime_explanation_json: dict[str, Any] | None
    profile_id: int | None
    requester_id: int | None
    user_key: str | None
    subscription_id: str | None
    discovery_session_id: str | None
    recommendation_id: int | None
    created_at: str


class CriteriaSnapshotStore:
    def __init__(self) -> None:
        self._rows: list[CriteriaSnapshotRecord] = []
        self._next_id = 1

    def save(
        self,
        *,
        scene: str,
        criteria_hash: str,
        compiled: Mapping[str, Any],
        source_map: Mapping[str, Any],
        runtime_explanation: Mapping[str, Any] | None = None,
        profile_id: int | None = None,
        requester_id: int | None = None,
        user_key: str | None = None,
        subscription_id: str | None = None,
        discovery_session_id: str | None = None,
        recommendation_id: int | None = None,
        now: datetime | None = None,
    ) -> CriteriaSnapshotRecord:
        record = CriteriaSnapshotRecord(
            snapshot_id=self._next_id,
            scene=scene,
            criteria_hash=criteria_hash,
            compiled_json=dict(compiled),
            source_map_json=dict(source_map),
            runtime_explanation_json=dict(runtime_explanation) if runtime_explanation else None,
            profile_id=profile_id,
            requester_id=requester_id,
            user_key=user_key,
            subscription_id=subscription_id,
            discovery_session_id=discovery_session_id,
            recommendation_id=recommendation_id,
            created_at=format_dt(current_time(now)),
        )
        self._next_id += 1
        self._rows.append(record)
        return record

    def get(self, snapshot_id: int) -> CriteriaSnapshotRecord | None:
        for row in self._rows:
            if row.snapshot_id == snapshot_id:
                return row
        return None

    def get_latest_for_recommendation(self, recommendation_id: int) -> CriteriaSnapshotRecord | None:
        matches = [row for row in self._rows if row.recommendation_id == recommendation_id]
        if not matches:
            return None
        return sorted(matches, key=lambda item: item.snapshot_id)[-1]

    def list_for_profile(self, profile_id: int, *, limit: int = 20) -> list[CriteriaSnapshotRecord]:
        rows = [row for row in self._rows if row.profile_id == profile_id]
        rows.sort(key=lambda item: item.snapshot_id, reverse=True)
        return rows[:limit]


_GLOBAL_STORE = CriteriaSnapshotStore()


def _recommendation_db_dsn() -> str:
    return (os.environ.get("PARTNER_RECOMMENDATION_DB") or "").strip()


def _open_mysql_connection(dsn: str):
    import pymysql

    parsed = urlparse(dsn)
    database = (parsed.path or "").lstrip("/") or None
    kwargs: dict[str, Any] = {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "database": database,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    return pymysql.connect(**kwargs)


def _persist_snapshot_mysql(record: CriteriaSnapshotRecord) -> None:
    dsn = _recommendation_db_dsn()
    if not dsn:
        return
    conn = _open_mysql_connection(dsn)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO criteria_snapshots (
                    scene, criteria_hash, compiled_json, source_map_json,
                    runtime_explanation_json, profile_id, requester_id, user_key,
                    subscription_id, discovery_session_id, recommendation_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.scene,
                    record.criteria_hash,
                    json.dumps(record.compiled_json, ensure_ascii=False, sort_keys=True),
                    json.dumps(record.source_map_json, ensure_ascii=False, sort_keys=True),
                    json.dumps(record.runtime_explanation_json, ensure_ascii=False, sort_keys=True)
                    if record.runtime_explanation_json
                    else None,
                    record.profile_id,
                    record.requester_id,
                    record.user_key,
                    record.subscription_id,
                    record.discovery_session_id,
                    record.recommendation_id,
                    record.created_at,
                ),
            )
            mysql_id = int(cursor.lastrowid)
            if mysql_id > 0:
                record.snapshot_id = mysql_id
        conn.commit()
    finally:
        conn.close()


def get_criteria_snapshot_store() -> CriteriaSnapshotStore:
    return _GLOBAL_STORE


def snapshot_to_dict(record: CriteriaSnapshotRecord) -> dict[str, Any]:
    return {
        "snapshot_id": record.snapshot_id,
        "scene": record.scene,
        "criteria_hash": record.criteria_hash,
        "compiled": record.compiled_json,
        "source_map": record.source_map_json,
        "runtime_explanation": record.runtime_explanation_json,
        "profile_id": record.profile_id,
        "requester_id": record.requester_id,
        "user_key": record.user_key,
        "subscription_id": record.subscription_id,
        "discovery_session_id": record.discovery_session_id,
        "recommendation_id": record.recommendation_id,
        "created_at": record.created_at,
    }


def save_compiled_snapshot(
    compiled: Mapping[str, Any],
    *,
    scene: str,
    profile_id: int | None = None,
    requester_id: int | None = None,
    user_key: str | None = None,
    subscription_id: str | None = None,
    discovery_session_id: str | None = None,
    recommendation_id: int | None = None,
    runtime_explanation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    store = get_criteria_snapshot_store()
    record = store.save(
        scene=scene,
        criteria_hash=str(compiled.get("criteria_hash") or ""),
        compiled={
            "criteria": compiled.get("criteria") or {},
            "hard_filters": compiled.get("hard_filters") or {},
            "soft_preferences": compiled.get("soft_preferences") or {},
            "self_profile": compiled.get("self_profile") or {},
        },
        source_map=dict(compiled.get("source_map") or {}),
        runtime_explanation=runtime_explanation,
        profile_id=profile_id,
        requester_id=requester_id,
        user_key=user_key,
        subscription_id=subscription_id,
        discovery_session_id=discovery_session_id,
        recommendation_id=recommendation_id,
    )
    try:
        _persist_snapshot_mysql(record)
    except Exception:  # noqa: BLE001
        pass
    return snapshot_to_dict(record)
