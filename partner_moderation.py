"""Shared moderation helpers across chat, search, recommendation, and matchmaking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from her_time_utils import as_text, current_time, unique_ordered_texts
from outer_mysql_compat import connect_mysql_repo_db, json_dumps, json_loads, row_to_dict
from profile_source_refs import build_source_file_ref, resolve_profile_source, split_source_file_ref

MODERATION_STATUS_ACTIVE = "active"
MODERATION_STATUS_CLEARED = "cleared"

ACTION_NONE = "none"
ACTION_WARN = "warn"
ACTION_REQUIRE_VERIFICATION = "require_verification"
ACTION_LIMITED_EXPOSURE = "limited_exposure"
ACTION_LIMIT_CHAT = "limit_chat"
ACTION_FREEZE = "freeze"

ACTION_PRIORITY = {
    ACTION_NONE: 0,
    ACTION_WARN: 1,
    ACTION_REQUIRE_VERIFICATION: 2,
    ACTION_LIMITED_EXPOSURE: 3,
    ACTION_LIMIT_CHAT: 4,
    ACTION_FREEZE: 5,
}

PHOTO_SIGNAL_CODES = {
    "photo_mismatch",
    "suspected_fake_photo",
    "photo_heavily_edited",
}
PROFILE_SIGNAL_CODES = {
    "profile_mismatch",
    "income_mismatch",
    "job_mismatch",
    "education_mismatch",
    "identity_mismatch",
}

FIELD_KEY_TO_STATUS_COLUMN = {
    "education": "education_verification_status",
    "job": "job_verification_status",
    "income": "income_verification_status",
}
def _as_text(value: Any) -> str:
    return as_text(value)


def _unique_ordered(values: Iterable[Any]) -> list[str]:
    return unique_ordered_texts(values)


def _merge_action(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if ACTION_PRIORITY.get(left, 0) >= ACTION_PRIORITY.get(right, 0) else right


def parse_source_ref(source_dsn: str | None, source_table_name: str | None = None) -> tuple[str | None, str | None]:
    dsn = _as_text(source_dsn) or None
    table_name = _as_text(source_table_name) or None
    if not dsn:
        return None, table_name
    return resolve_profile_source(dsn, table_name)


def source_ref_from_record(record: dict[str, Any]) -> tuple[str | None, str | None, int | None]:
    source_file = _as_text(record.get("source_file"))
    source_dsn = None
    table_name = None
    if source_file:
        source_dsn, table_name = split_source_file_ref(source_file)
    else:
        source_dsn = _as_text(record.get("source_dsn")) or None
        table_name = _as_text(record.get("source_table_name")) or None
    normalized_source, normalized_table = parse_source_ref(source_dsn, table_name)
    profile_id = record.get("id")
    try:
        profile_id = int(profile_id) if profile_id is not None else None
    except (TypeError, ValueError):
        profile_id = None
    return normalized_source, normalized_table, profile_id


def build_subject_key(
    *,
    subject_user_id: str | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
) -> str:
    user_id = _as_text(subject_user_id)
    if user_id:
        return f"user:{user_id}"
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    if normalized_source and normalized_table and profile_id is not None:
        return f"profile:{build_source_file_ref(normalized_source, normalized_table)}:{int(profile_id)}"
    raise ValueError("subject_user_id or complete profile source reference is required")


def normalize_required_verifications(values: Iterable[Any] | None) -> list[str]:
    allowed = {"live_video", "education", "job", "income", "identity"}
    return [item for item in _unique_ordered(values or []) if item in allowed]


def infer_required_verifications(signal_codes: Iterable[Any] | None) -> list[str]:
    codes = set(_unique_ordered(signal_codes or []))
    required: list[str] = []
    if codes & PHOTO_SIGNAL_CODES:
        required.append("live_video")
    if "education_mismatch" in codes:
        required.append("education")
    if "job_mismatch" in codes:
        required.append("job")
    if "income_mismatch" in codes:
        required.append("income")
    if "identity_mismatch" in codes or "fraud_report" in codes:
        required.append("identity")
    return normalize_required_verifications(required)


def _inflate_moderation_state(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["required_verifications"] = json_loads(out.pop("required_verifications_json", None), [])
    out["evidence"] = json_loads(out.pop("evidence_json", None), {})
    return out


def get_moderation_state_by_subject_key(conn, subject_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM account_moderation_states
        WHERE subject_key = ?
        LIMIT 1
        """,
        (subject_key,),
    ).fetchone()
    return _inflate_moderation_state(row_to_dict(row))


def get_active_moderation_state(
    conn,
    *,
    subject_user_id: str | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
) -> dict[str, Any] | None:
    user_id = _as_text(subject_user_id)
    if user_id:
        row = conn.execute(
            """
            SELECT *
            FROM account_moderation_states
            WHERE subject_user_id = ?
              AND moderation_status = ?
            ORDER BY updated_at DESC, state_id DESC
            LIMIT 1
            """,
            (user_id, MODERATION_STATUS_ACTIVE),
        ).fetchone()
        out = _inflate_moderation_state(row_to_dict(row))
        if out:
            return out
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    if normalized_source and normalized_table and profile_id is not None:
        row = conn.execute(
            """
            SELECT *
            FROM account_moderation_states
            WHERE source_dsn = ?
              AND source_table_name = ?
              AND profile_id = ?
              AND moderation_status = ?
            ORDER BY updated_at DESC, state_id DESC
            LIMIT 1
            """,
            (
                normalized_source,
                normalized_table,
                int(profile_id),
                MODERATION_STATUS_ACTIVE,
            ),
        ).fetchone()
        return _inflate_moderation_state(row_to_dict(row))
    return None


def list_moderation_states(
    conn,
    *,
    moderation_status: str | None = None,
    subject_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if moderation_status:
        clauses.append("moderation_status = ?")
        params.append(_as_text(moderation_status))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    rows = conn.execute(
        f"""
        SELECT *
        FROM account_moderation_states
        {where}
        ORDER BY updated_at DESC, state_id DESC
        LIMIT ?
        """,
        tuple(params + [lim]),
    ).fetchall()
    return [_inflate_moderation_state(row_to_dict(row)) for row in rows if row]


def upsert_moderation_state(
    conn,
    *,
    subject_user_id: str | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
    action: str,
    moderation_status: str = MODERATION_STATUS_ACTIVE,
    reason_code: str | None = None,
    reason_summary: str | None = None,
    required_verifications: Iterable[Any] | None = None,
    evidence: dict[str, Any] | None = None,
    linked_risk_case_id: str | None = None,
    linked_profile_review_case_id: str | None = None,
    resolver_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    normalized_action = _as_text(action) or ACTION_NONE
    if normalized_action not in ACTION_PRIORITY:
        raise ValueError("invalid moderation action")
    if moderation_status not in {MODERATION_STATUS_ACTIVE, MODERATION_STATUS_CLEARED}:
        raise ValueError("invalid moderation_status")
    subject_key = build_subject_key(
        subject_user_id=subject_user_id,
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=profile_id,
    )
    existing = get_moderation_state_by_subject_key(conn, subject_key)
    normalized_required = normalize_required_verifications(required_verifications)
    payload = dict(evidence or {})
    if existing:
        merged_action = normalized_action
        if moderation_status == MODERATION_STATUS_ACTIVE and existing.get("moderation_status") == MODERATION_STATUS_ACTIVE:
            merged_action = _merge_action(existing.get("applied_action"), normalized_action) or normalized_action
        merged_required = normalize_required_verifications(
            list(existing.get("required_verifications") or []) + normalized_required
        )
        merged_evidence = {**(existing.get("evidence") or {}), **payload}
        conn.execute(
            """
            UPDATE account_moderation_states
            SET subject_user_id = ?,
                source_dsn = ?,
                source_table_name = ?,
                profile_id = ?,
                moderation_status = ?,
                applied_action = ?,
                reason_code = ?,
                reason_summary = ?,
                required_verifications_json = ?,
                evidence_json = ?,
                linked_risk_case_id = COALESCE(?, linked_risk_case_id),
                linked_profile_review_case_id = COALESCE(?, linked_profile_review_case_id),
                resolver_id = ?,
                updated_at = ?,
                cleared_at = ?
            WHERE subject_key = ?
            """,
            (
                _as_text(subject_user_id) or None,
                normalized_source,
                normalized_table,
                int(profile_id) if profile_id is not None else None,
                moderation_status,
                merged_action,
                _as_text(reason_code) or None,
                _as_text(reason_summary) or None,
                json_dumps(merged_required),
                json_dumps(merged_evidence),
                _as_text(linked_risk_case_id) or None,
                _as_text(linked_profile_review_case_id) or None,
                _as_text(resolver_id) or None,
                ts,
                ts if moderation_status == MODERATION_STATUS_CLEARED else None,
                subject_key,
            ),
        )
        row = get_moderation_state_by_subject_key(conn, subject_key)
        assert row is not None
        return row

    conn.execute(
        """
        INSERT INTO account_moderation_states (
          subject_key, subject_user_id, source_dsn, source_table_name, profile_id,
          moderation_status, applied_action, reason_code, reason_summary,
          required_verifications_json, evidence_json, linked_risk_case_id,
          linked_profile_review_case_id, resolver_id, created_at, updated_at, cleared_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subject_key,
            _as_text(subject_user_id) or None,
            normalized_source,
            normalized_table,
            int(profile_id) if profile_id is not None else None,
            moderation_status,
            normalized_action,
            _as_text(reason_code) or None,
            _as_text(reason_summary) or None,
            json_dumps(normalized_required),
            json_dumps(payload),
            _as_text(linked_risk_case_id) or None,
            _as_text(linked_profile_review_case_id) or None,
            _as_text(resolver_id) or None,
            ts,
            ts,
            ts if moderation_status == MODERATION_STATUS_CLEARED else None,
        ),
    )
    row = get_moderation_state_by_subject_key(conn, subject_key)
    assert row is not None
    return row


def clear_moderation_state(
    conn,
    *,
    subject_user_id: str | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
    resolver_id: str | None = None,
    reason_summary: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    existing = get_active_moderation_state(
        conn,
        subject_user_id=subject_user_id,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
    )
    if not existing:
        return None
    return upsert_moderation_state(
        conn,
        subject_user_id=existing.get("subject_user_id"),
        source_dsn=existing.get("source_dsn"),
        source_table_name=existing.get("source_table_name"),
        profile_id=existing.get("profile_id"),
        action=existing.get("applied_action") or ACTION_NONE,
        moderation_status=MODERATION_STATUS_CLEARED,
        reason_code=existing.get("reason_code"),
        reason_summary=reason_summary or existing.get("reason_summary"),
        required_verifications=existing.get("required_verifications"),
        evidence=existing.get("evidence") or {},
        linked_risk_case_id=existing.get("linked_risk_case_id"),
        linked_profile_review_case_id=existing.get("linked_profile_review_case_id"),
        resolver_id=resolver_id,
        now=now,
    )


def moderation_labels_for_action(action: str) -> tuple[str | None, str | None]:
    normalized = _as_text(action)
    if normalized == ACTION_LIMITED_EXPOSURE:
        return "limited_exposure", "账号当前处于资料复核限制，默认降低曝光"
    if normalized == ACTION_FREEZE:
        return "limited_exposure", "账号当前已被冻结，不对外曝光"
    if normalized == ACTION_REQUIRE_VERIFICATION:
        return "needs_review", "账号当前被要求补充核验"
    return None, None


def overlay_record_with_moderation(record: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return record
    out = dict(record)
    action = _as_text(state.get("applied_action"))
    review_status, caution = moderation_labels_for_action(action)
    required = normalize_required_verifications(state.get("required_verifications"))
    if review_status:
        out["profile_review_status"] = review_status
    if "education" in required:
        out["education_verification_status"] = "needs_review"
    if "job" in required:
        out["job_verification_status"] = "needs_review"
    if "income" in required:
        out["income_verification_status"] = "needs_review"
    if action:
        out["account_moderation_action"] = action
    if caution:
        existing = list(out.get("moderation_caution_items") or [])
        existing.append(caution)
        out["moderation_caution_items"] = _unique_ordered(existing)
    if state.get("reason_summary"):
        out["moderation_reason_summary"] = state.get("reason_summary")
    if required:
        out["required_verifications"] = required
    return out


def overlay_records_with_moderation(
    records: list[dict[str, Any]],
    *,
    moderation_dsn: str | None,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    if not moderation_dsn or not records:
        return list(records)

    grouped_ids: dict[tuple[str, str], list[int]] = {}
    for record in records:
        source_dsn, table_name, profile_id = source_ref_from_record(record)
        if not source_dsn or not table_name or profile_id is None:
            continue
        grouped_ids.setdefault((source_dsn, table_name), []).append(profile_id)

    if not grouped_ids:
        return list(records)

    conn = connect_mysql_repo_db(moderation_dsn, subsystem_name="ModerationOverlay")
    try:
        state_lookup: dict[tuple[str, str, int], dict[str, Any]] = {}
        for (source_dsn, table_name), profile_ids in grouped_ids.items():
            ids = sorted({int(item) for item in profile_ids})
            placeholders = ", ".join(["?"] * len(ids))
            rows = conn.execute(
                f"""
                SELECT *
                FROM account_moderation_states
                WHERE moderation_status = ?
                  AND source_dsn = ?
                  AND source_table_name = ?
                  AND profile_id IN ({placeholders})
                ORDER BY updated_at DESC, state_id DESC
                """,
                (MODERATION_STATUS_ACTIVE, source_dsn, table_name, *ids),
            ).fetchall()
            for row in rows:
                item = _inflate_moderation_state(row_to_dict(row))
                if not item or item.get("profile_id") is None:
                    continue
                key = (source_dsn, table_name, int(item["profile_id"]))
                state_lookup.setdefault(key, item)

        out: list[dict[str, Any]] = []
        for record in records:
            source_dsn, table_name, profile_id = source_ref_from_record(record)
            state = None
            if source_dsn and table_name and profile_id is not None:
                state = state_lookup.get((source_dsn, table_name, profile_id))
            updated = overlay_record_with_moderation(record, state)
            blocked_action = _as_text((state or {}).get("applied_action"))
            if not include_blocked and blocked_action in {ACTION_LIMITED_EXPOSURE, ACTION_FREEZE}:
                continue
            out.append(updated)
        return out
    finally:
        conn.close()


@dataclass
class ModerationPlaybackBundle:
    moderation_state: dict[str, Any] | None
    required_verifications: list[str]


def moderation_playback_bundle(state: dict[str, Any] | None) -> ModerationPlaybackBundle:
    required = normalize_required_verifications((state or {}).get("required_verifications"))
    return ModerationPlaybackBundle(moderation_state=state, required_verifications=required)


__all__ = [
    "ACTION_FREEZE",
    "ACTION_LIMIT_CHAT",
    "ACTION_LIMITED_EXPOSURE",
    "ACTION_NONE",
    "ACTION_REQUIRE_VERIFICATION",
    "ACTION_WARN",
    "FIELD_KEY_TO_STATUS_COLUMN",
    "MODERATION_STATUS_ACTIVE",
    "MODERATION_STATUS_CLEARED",
    "build_subject_key",
    "clear_moderation_state",
    "current_time",
    "get_active_moderation_state",
    "get_moderation_state_by_subject_key",
    "infer_required_verifications",
    "list_moderation_states",
    "moderation_playback_bundle",
    "overlay_record_with_moderation",
    "overlay_records_with_moderation",
    "parse_source_ref",
    "source_ref_from_record",
    "upsert_moderation_state",
]
