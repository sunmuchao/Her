"""Photo risk persistence and query helpers for profile review workflows."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Iterable

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

from partner_moderation import ACTION_NONE

from .profile_review_rules import profile_review_action_for_hits, profile_review_severity_for_hits
from .storage import inflate_json_columns, json_dumps, row_to_dict

PROFILE_REVIEW_STATUS_OPEN = "open"
PROFILE_REVIEW_STATUS_DISMISSED = "dismissed"
PROFILE_REVIEW_STATUS_RESOLVED = "resolved"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

PHOTO_RISK_ENGINE_NAME = "local_photo_authenticity"
PHOTO_RISK_ENGINE_VERSION = "local_photo_authenticity_v1"
PHOTO_RISK_FEATURE_VERSION = "local_photo_authenticity_features_v1"
PHOTO_RISK_ASSET_ROLE_SUBJECT = "subject_profile_photo"
PHOTO_RISK_ASSET_ROLE_COMPARISON = "comparison_profile_photo"


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _sha1_hex(value: Any) -> str:
    return hashlib.sha1(_as_text(value).encode("utf-8")).hexdigest()


def _inflate_photo_risk_asset(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return dict(row)


def _inflate_photo_risk_feature_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        embedding_preview=("embedding_preview_json", []),
        photo_edit_metrics=("photo_edit_metrics_json", None),
        deepfake_metrics=("deepfake_metrics_json", None),
        metadata=("metadata_json", {}),
    )


def _inflate_photo_risk_score_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        risk_flags=("risk_flags_json", []),
        score_payload=("score_payload_json", {}),
    )


def _inflate_photo_risk_decision(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        required_verifications=("required_verifications_json", []),
        rule_codes=("rule_codes_json", []),
        signal_codes=("signal_codes_json", []),
        decision_payload=("decision_payload_json", {}),
    )


def _inflate_photo_risk_review_queue_item(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        reason_codes=("reason_codes_json", []),
        queue_payload=("queue_payload_json", {}),
    )


def _load_photo_risk_decision_by_score_run(conn, score_run_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM photo_risk_decisions
        WHERE score_run_id = ?
        LIMIT 1
        """,
        (int(score_run_id),),
    ).fetchone()
    return _inflate_photo_risk_decision(row_to_dict(row))


def _load_photo_risk_review_queue_by_score_run(conn, score_run_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM photo_risk_review_queue
        WHERE score_run_id = ?
        LIMIT 1
        """,
        (int(score_run_id),),
    ).fetchone()
    return _inflate_photo_risk_review_queue_item(row_to_dict(row))


def _photo_risk_priority_from_severity(severity: Any) -> str:
    normalized = _as_text(severity)
    if normalized == SEVERITY_HIGH:
        return "high"
    if normalized == SEVERITY_MEDIUM:
        return "medium"
    return "low"


def _upsert_photo_risk_asset(
    conn,
    *,
    source_dsn: str,
    source_table_name: str,
    source_profile_id: int | None,
    asset_origin: str,
    photo_source: str,
    now: datetime,
) -> int:
    normalized_source = _as_text(photo_source)
    photo_source_sha1 = _sha1_hex(normalized_source)
    row = conn.execute(
        """
        SELECT asset_id
        FROM photo_risk_assets
        WHERE source_dsn = ?
          AND source_table_name = ?
          AND ((source_profile_id IS NULL AND ? IS NULL) OR source_profile_id = ?)
          AND photo_source_sha1 = ?
        LIMIT 1
        """,
        (
            source_dsn,
            source_table_name,
            source_profile_id,
            source_profile_id,
            photo_source_sha1,
        ),
    ).fetchone()
    if row:
        asset_id = int(row["asset_id"])
        conn.execute(
            """
            UPDATE photo_risk_assets
            SET asset_origin = ?,
                photo_source = ?,
                last_seen_at = ?,
                updated_at = ?
            WHERE asset_id = ?
            """,
            (
                _as_text(asset_origin) or "photo_table",
                normalized_source,
                now,
                now,
                asset_id,
            ),
        )
        return asset_id
    conn.execute(
        """
        INSERT INTO photo_risk_assets (
          source_dsn, source_table_name, source_profile_id, asset_origin,
          photo_source, photo_source_sha1, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_dsn,
            source_table_name,
            source_profile_id,
            _as_text(asset_origin) or "photo_table",
            normalized_source,
            photo_source_sha1,
            now,
            now,
            now,
            now,
        ),
    )
    return int(conn.lastrowid)


def _insert_photo_risk_feature_snapshot(
    conn,
    *,
    asset_id: int,
    score_run_id: int,
    asset_role: str,
    feature_entry: dict[str, Any] | None,
    record: dict[str, Any],
    now: datetime,
) -> int:
    feature_payload = dict(feature_entry or {})
    metadata = {
        "source_profile_id": record.get("source_profile_id"),
        "asset_origin": record.get("asset_origin"),
        "photo_source": record.get("photo_source"),
        "load_status": "loaded" if feature_entry else "not_loaded",
    }
    conn.execute(
        """
        INSERT INTO photo_risk_feature_snapshots (
          asset_id, score_run_id, asset_role, feature_version, face_count, face_detection_score,
          image_hash_hex, embedding_available, embedding_dim, embedding_preview_json,
          photo_edit_metrics_json, deepfake_metrics_json, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(asset_id),
            int(score_run_id),
            _as_text(asset_role),
            PHOTO_RISK_FEATURE_VERSION,
            int(feature_payload.get("face_count") or 0),
            int(feature_payload.get("face_detection_score") or 0),
            _as_text(feature_payload.get("image_hash_hex")) or None,
            1 if bool(feature_payload.get("embedding_available")) else 0,
            int(feature_payload.get("embedding_dim") or 0),
            json_dumps(list(feature_payload.get("embedding_preview") or [])),
            json_dumps(_json_safe(feature_payload.get("photo_edit_metrics")))
            if feature_payload.get("photo_edit_metrics") is not None
            else None,
            json_dumps(_json_safe(feature_payload.get("deepfake_metrics")))
            if feature_payload.get("deepfake_metrics") is not None
            else None,
            json_dumps(_json_safe(metadata)),
            now,
        ),
    )
    return int(conn.lastrowid)


def _create_photo_risk_score_run(
    conn,
    *,
    profile_id: int,
    subject_user_id: str | None,
    source_dsn: str,
    source_table_name: str,
    profile_review_case_id: str | None,
    review: dict[str, Any],
    now: datetime,
) -> int:
    conn.execute(
        """
        INSERT INTO photo_risk_score_runs (
          profile_id, subject_user_id, source_dsn, source_table_name, profile_review_case_id,
          trigger_source, engine_name, engine_version, analysis_status, photo_authenticity_score,
          same_person_score, photo_edit_risk_score, deepfake_risk_score, stolen_media_risk_score,
          source_count, loaded_source_count, valid_face_photo_count, multiple_face_photo_count,
          comparison_source_count, risk_flags_json, score_payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(profile_id),
            _as_text(subject_user_id) or None,
            source_dsn,
            source_table_name,
            _as_text(profile_review_case_id) or None,
            "profile_review_evaluate",
            PHOTO_RISK_ENGINE_NAME,
            PHOTO_RISK_ENGINE_VERSION,
            _as_text(review.get("analysis_status")) or "unavailable",
            int(review.get("photo_authenticity_score") or 0),
            int(review.get("same_person_score") or 0),
            int(review.get("photo_edit_risk_score") or 0),
            int(review.get("deepfake_risk_score") or 0),
            int(review.get("stolen_media_risk_score") or 0),
            int(review.get("source_count") or 0),
            int(review.get("loaded_source_count") or 0),
            int(review.get("valid_face_photo_count") or 0),
            int(review.get("multiple_face_photo_count") or 0),
            int(review.get("comparison_source_count") or 0),
            json_dumps(list(review.get("risk_flags") or [])),
            json_dumps(_json_safe(review)),
            now,
        ),
    )
    return int(conn.lastrowid)


def _create_photo_risk_decision(
    conn,
    *,
    score_run_id: int,
    profile_review_case_id: str | None,
    photo_hits: list[dict[str, Any]],
    photo_review_signal_codes: list[str],
    now: datetime,
) -> int:
    required_verifications = _unique_ordered(
        rv for hit in photo_hits for rv in list(hit.get("required_verifications") or [])
    )
    severity = profile_review_severity_for_hits(photo_hits) if photo_hits else SEVERITY_LOW
    recommended_action = profile_review_action_for_hits(photo_hits) if photo_hits else ACTION_NONE
    decision_payload = {
        "photo_rule_hits": photo_hits,
        "required_verifications": required_verifications,
        "signal_codes": list(photo_review_signal_codes or []),
    }
    conn.execute(
        """
        INSERT INTO photo_risk_decisions (
          score_run_id, profile_review_case_id, decision_source, decision_status, severity,
          recommended_action, required_verifications_json, rule_codes_json, signal_codes_json,
          decision_payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(score_run_id),
            _as_text(profile_review_case_id) or None,
            "profile_photo_rules",
            recommended_action,
            severity,
            recommended_action,
            json_dumps(required_verifications),
            json_dumps([hit["rule_code"] for hit in photo_hits]),
            json_dumps(list(photo_review_signal_codes or [])),
            json_dumps(_json_safe(decision_payload)),
            now,
            now,
        ),
    )
    return int(conn.lastrowid)


def _upsert_photo_risk_review_queue(
    conn,
    *,
    profile_id: int,
    subject_user_id: str | None,
    source_dsn: str,
    source_table_name: str,
    profile_review_case_id: str,
    score_run_id: int,
    decision_id: int,
    severity: str,
    photo_review_signal_codes: list[str],
    queue_payload: dict[str, Any],
    now: datetime,
) -> int:
    existing = conn.execute(
        """
        SELECT queue_item_id
        FROM photo_risk_review_queue
        WHERE profile_review_case_id = ?
        LIMIT 1
        """,
        (profile_review_case_id,),
    ).fetchone()
    if existing:
        queue_item_id = int(existing["queue_item_id"])
        conn.execute(
            """
            UPDATE photo_risk_review_queue
            SET profile_id = ?,
                subject_user_id = ?,
                source_dsn = ?,
                source_table_name = ?,
                score_run_id = ?,
                decision_id = ?,
                queue_status = ?,
                priority = ?,
                reason_codes_json = ?,
                queue_payload_json = ?,
                updated_at = ?,
                resolved_at = NULL
            WHERE queue_item_id = ?
            """,
            (
                int(profile_id),
                _as_text(subject_user_id) or None,
                source_dsn,
                source_table_name,
                int(score_run_id),
                int(decision_id),
                PROFILE_REVIEW_STATUS_OPEN,
                _photo_risk_priority_from_severity(severity),
                json_dumps(list(photo_review_signal_codes or [])),
                json_dumps(_json_safe(queue_payload)),
                now,
                queue_item_id,
            ),
        )
        return queue_item_id
    conn.execute(
        """
        INSERT INTO photo_risk_review_queue (
          profile_id, subject_user_id, source_dsn, source_table_name, profile_review_case_id,
          score_run_id, decision_id, queue_status, priority, reason_codes_json, queue_payload_json,
          created_at, updated_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(profile_id),
            _as_text(subject_user_id) or None,
            source_dsn,
            source_table_name,
            profile_review_case_id,
            int(score_run_id),
            int(decision_id),
            PROFILE_REVIEW_STATUS_OPEN,
            _photo_risk_priority_from_severity(severity),
            json_dumps(list(photo_review_signal_codes or [])),
            json_dumps(_json_safe(queue_payload)),
            now,
            now,
            None,
        ),
    )
    return int(conn.lastrowid)


def sync_photo_risk_review_queue_status(
    conn,
    *,
    profile_review_case_id: str,
    status: str,
    applied_action: str | None,
    resolution_note: str | None,
    resolver_id: str | None,
    now: datetime,
) -> dict[str, Any] | None:
    current = conn.execute(
        """
        SELECT *
        FROM photo_risk_review_queue
        WHERE profile_review_case_id = ?
        LIMIT 1
        """,
        (profile_review_case_id,),
    ).fetchone()
    item = _inflate_photo_risk_review_queue_item(row_to_dict(current))
    if not item:
        return None
    payload = dict(item.get("queue_payload") or {})
    payload["last_case_status"] = _as_text(status)
    if _as_text(applied_action):
        payload["last_applied_action"] = _as_text(applied_action)
    if _as_text(resolution_note):
        payload["last_resolution_note"] = _as_text(resolution_note)
    if _as_text(resolver_id):
        payload["last_resolver_id"] = _as_text(resolver_id)
    resolved_at = now if _as_text(status) in {PROFILE_REVIEW_STATUS_RESOLVED, PROFILE_REVIEW_STATUS_DISMISSED} else None
    conn.execute(
        """
        UPDATE photo_risk_review_queue
        SET queue_status = ?,
            queue_payload_json = ?,
            updated_at = ?,
            resolved_at = ?
        WHERE queue_item_id = ?
        """,
        (
            _as_text(status),
            json_dumps(_json_safe(payload)),
            now,
            resolved_at,
            int(item["queue_item_id"]),
        ),
    )
    return get_photo_risk_review_queue_item(conn, int(item["queue_item_id"]))


def get_photo_risk_score_run(
    conn,
    score_run_id: int,
    *,
    include_assets: bool = True,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM photo_risk_score_runs
        WHERE score_run_id = ?
        LIMIT 1
        """,
        (int(score_run_id),),
    ).fetchone()
    result = _inflate_photo_risk_score_run(row_to_dict(row))
    if not result:
        return None
    result["decision"] = _load_photo_risk_decision_by_score_run(conn, int(score_run_id))
    result["review_queue_item"] = _load_photo_risk_review_queue_by_score_run(conn, int(score_run_id))
    if include_assets:
        feature_rows = conn.execute(
            f"""
            SELECT *
            FROM photo_risk_feature_snapshots
            WHERE score_run_id = ?
            ORDER BY CASE WHEN asset_role = '{PHOTO_RISK_ASSET_ROLE_SUBJECT}' THEN 0 ELSE 1 END,
                     feature_snapshot_id ASC
            """,
            (int(score_run_id),),
        ).fetchall()
        assets: list[dict[str, Any]] = []
        for feature_row in feature_rows:
            feature_snapshot = _inflate_photo_risk_feature_snapshot(row_to_dict(feature_row))
            if not feature_snapshot:
                continue
            asset_row = conn.execute(
                """
                SELECT *
                FROM photo_risk_assets
                WHERE asset_id = ?
                LIMIT 1
                """,
                (int(feature_snapshot["asset_id"]),),
            ).fetchone()
            asset = _inflate_photo_risk_asset(row_to_dict(asset_row))
            if not asset:
                continue
            asset["feature_snapshot"] = feature_snapshot
            assets.append(asset)
        result["assets"] = assets
    return result


def list_photo_risk_score_runs(
    conn,
    *,
    profile_id: int | None = None,
    subject_user_id: str | None = None,
    profile_review_case_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if profile_id is not None:
        clauses.append("profile_id = ?")
        params.append(int(profile_id))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    if profile_review_case_id:
        clauses.append("profile_review_case_id = ?")
        params.append(_as_text(profile_review_case_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM photo_risk_score_runs
        {where}
        ORDER BY score_run_id DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _inflate_photo_risk_score_run(row_to_dict(row))
        if not item:
            continue
        item["decision"] = _load_photo_risk_decision_by_score_run(conn, int(item["score_run_id"]))
        item["review_queue_item"] = _load_photo_risk_review_queue_by_score_run(conn, int(item["score_run_id"]))
        out.append(item)
    return out


def get_photo_risk_review_queue_item(conn, queue_item_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM photo_risk_review_queue
        WHERE queue_item_id = ?
        LIMIT 1
        """,
        (int(queue_item_id),),
    ).fetchone()
    return _inflate_photo_risk_review_queue_item(row_to_dict(row))


def list_photo_risk_review_queue(
    conn,
    *,
    statuses: Iterable[Any] | None = None,
    profile_id: int | None = None,
    subject_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    normalized_statuses = _unique_ordered(statuses or [])
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"queue_status IN ({placeholders})")
        params.extend(normalized_statuses)
    if profile_id is not None:
        clauses.append("profile_id = ?")
        params.append(int(profile_id))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM photo_risk_review_queue
        {where}
        ORDER BY updated_at DESC, queue_item_id DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_photo_risk_review_queue_item(row_to_dict(row)) for row in rows if row]


def persist_photo_risk_service(
    conn,
    *,
    profile_id: int,
    subject_user_id: str | None,
    source_dsn: str,
    source_table_name: str,
    subject_photo_records: list[dict[str, Any]],
    comparison_photo_records: list[dict[str, Any]],
    photo_review_bundle: dict[str, Any],
    profile_review_case_id: str | None,
    photo_hits: list[dict[str, Any]],
    photo_review_signal_codes: list[str],
    now: datetime,
) -> dict[str, Any]:
    review = dict(photo_review_bundle.get("review") or {})
    score_run_id = _create_photo_risk_score_run(
        conn,
        profile_id=int(profile_id),
        subject_user_id=_as_text(subject_user_id) or None,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_review_case_id=_as_text(profile_review_case_id) or None,
        review=review,
        now=now,
    )
    feature_by_source = {
        _as_text(item.get("source")): dict(item)
        for item in list(photo_review_bundle.get("photo_entries") or [])
        if _as_text(item.get("source"))
    }
    comparison_feature_by_source = {
        _as_text(item.get("source")): dict(item)
        for item in list(photo_review_bundle.get("comparison_entries") or [])
        if _as_text(item.get("source"))
    }
    for record in subject_photo_records:
        photo_source = _as_text(record.get("photo_source"))
        if not photo_source:
            continue
        asset_id = _upsert_photo_risk_asset(
            conn,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            source_profile_id=_as_int(record.get("source_profile_id")),
            asset_origin=_as_text(record.get("asset_origin")) or "photo_table",
            photo_source=photo_source,
            now=now,
        )
        _insert_photo_risk_feature_snapshot(
            conn,
            asset_id=asset_id,
            score_run_id=score_run_id,
            asset_role=PHOTO_RISK_ASSET_ROLE_SUBJECT,
            feature_entry=feature_by_source.get(photo_source),
            record=record,
            now=now,
        )
    for record in comparison_photo_records:
        photo_source = _as_text(record.get("photo_source"))
        if not photo_source:
            continue
        asset_id = _upsert_photo_risk_asset(
            conn,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            source_profile_id=_as_int(record.get("source_profile_id")),
            asset_origin=_as_text(record.get("asset_origin")) or "photo_table",
            photo_source=photo_source,
            now=now,
        )
        _insert_photo_risk_feature_snapshot(
            conn,
            asset_id=asset_id,
            score_run_id=score_run_id,
            asset_role=PHOTO_RISK_ASSET_ROLE_COMPARISON,
            feature_entry=comparison_feature_by_source.get(photo_source),
            record=record,
            now=now,
        )
    decision_id = _create_photo_risk_decision(
        conn,
        score_run_id=score_run_id,
        profile_review_case_id=_as_text(profile_review_case_id) or None,
        photo_hits=photo_hits,
        photo_review_signal_codes=photo_review_signal_codes,
        now=now,
    )
    queue_item_id = None
    if photo_hits and _as_text(profile_review_case_id):
        queue_payload = {
            "photo_authenticity_score": review.get("photo_authenticity_score"),
            "risk_flags": list(review.get("risk_flags") or []),
            "photo_rule_codes": [hit["rule_code"] for hit in photo_hits],
        }
        queue_item_id = _upsert_photo_risk_review_queue(
            conn,
            profile_id=int(profile_id),
            subject_user_id=_as_text(subject_user_id) or None,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_review_case_id=_as_text(profile_review_case_id),
            score_run_id=score_run_id,
            decision_id=decision_id,
            severity=profile_review_severity_for_hits(photo_hits),
            photo_review_signal_codes=photo_review_signal_codes,
            queue_payload=queue_payload,
            now=now,
        )
    return {
        "score_run_id": score_run_id,
        "decision_id": decision_id,
        "review_queue_item_id": queue_item_id,
        "score_run": get_photo_risk_score_run(conn, score_run_id),
        "decision": _load_photo_risk_decision_by_score_run(conn, score_run_id),
        "review_queue_item": get_photo_risk_review_queue_item(conn, int(queue_item_id)) if queue_item_id else None,
    }


__all__ = [
    "get_photo_risk_review_queue_item",
    "get_photo_risk_score_run",
    "list_photo_risk_review_queue",
    "list_photo_risk_score_runs",
    "persist_photo_risk_service",
    "sync_photo_risk_review_queue_status",
]
