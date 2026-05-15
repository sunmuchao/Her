"""Profile field verification and profile consistency review workflows."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

from partner_moderation import (
    ACTION_LIMITED_EXPOSURE,
    ACTION_NONE,
    ACTION_REQUIRE_VERIFICATION,
    FIELD_KEY_TO_STATUS_COLUMN,
    clear_moderation_state,
    current_time,
    get_active_moderation_state,
    upsert_moderation_state,
)
from profile_service import (
    apply_profile_updates,
    get_profile,
    list_comparison_profile_photos,
    list_profile_photos,
    resolve_profile_source,
)

from .storage import inflate_json_columns, json_dumps, json_loads, row_to_dict

FIELD_SUBMISSION_STATUS_SUBMITTED = "submitted"
FIELD_SUBMISSION_STATUS_UNDER_REVIEW = "under_review"
FIELD_SUBMISSION_STATUS_APPROVED = "approved"
FIELD_SUBMISSION_STATUS_REJECTED = "rejected"
FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED = "resubmission_required"
FIELD_SUBMISSION_STATUS_EXPIRED = "expired"

FIELD_REVIEW_DECISION_APPROVE = "approve"
FIELD_REVIEW_DECISION_REJECT = "reject"
FIELD_REVIEW_DECISION_REQUEST_RESUBMISSION = "request_resubmission"
FIELD_REVIEW_EVENT_DISPUTE_OPENED = "dispute_opened"
FIELD_REVIEW_EVENT_MARK_EXPIRED = "mark_expired"

FIELD_DISPUTE_STATUS_NONE = "none"
FIELD_DISPUTE_STATUS_OPEN = "open"
FIELD_DISPUTE_STATUS_RESOLVED = "resolved"

FIELD_REVERIFY_STRATEGY_ON_CHANGE = "on_profile_change"
FIELD_REVERIFY_STRATEGY_ANNUAL_REFRESH = "annual_refresh"
FIELD_REVERIFY_STRATEGY_SEMIANNUAL_REFRESH = "semiannual_refresh"

PROFILE_REVIEW_STATUS_OPEN = "open"
PROFILE_REVIEW_STATUS_UNDER_REVIEW = "under_review"
PROFILE_REVIEW_STATUS_ACTION_APPLIED = "action_applied"
PROFILE_REVIEW_STATUS_DISMISSED = "dismissed"
PROFILE_REVIEW_STATUS_RESOLVED = "resolved"
PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED = "submitted"
PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW = "under_review"
PROFILE_REVIEW_APPEAL_STATUS_UPHELD = "upheld"
PROFILE_REVIEW_APPEAL_STATUS_REJECTED = "rejected"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

VALID_FIELD_KEYS = {"education", "job", "income"}
FIELD_VALUE_COLUMNS = {
    "education": "education",
    "job": "job",
    "income": "income_range",
}

FIELD_POLICIES = {
    "education": {
        "label": "学历",
        "accepted_documents": ["毕业证", "学位证", "学信网截图", "在读证明"],
        "accepted_evidence_types": ["graduation_certificate", "degree_certificate", "education_registry", "student_status_proof"],
        "accepted_evidence_channels": ["document_upload", "authority_lookup", "manual_review"],
        "review_focus": ["姓名与资料是否一致", "学历层级是否匹配", "是否需要补充在读/毕业状态说明"],
        "status_labels": ["verified", "self_reported", "pending", "needs_review", "missing", "expired", "disputed"],
        "resubmission_examples": ["证件模糊", "毕业院校或层级无法辨认", "姓名遮挡过多"],
        "default_validity_days": 3650,
        "default_next_review_days": 3650,
        "default_reverify_strategy": FIELD_REVERIFY_STRATEGY_ON_CHANGE,
    },
    "job": {
        "label": "职业",
        "accepted_documents": ["工牌", "在职证明", "名片", "社保截图", "劳动合同首页"],
        "accepted_evidence_types": ["employee_badge", "employment_letter", "business_card", "social_security_record", "labor_contract"],
        "accepted_evidence_channels": ["document_upload", "enterprise_email", "manual_review"],
        "review_focus": ["岗位是否真实存在", "岗位和公司类型是否匹配", "是否存在明显包装"],
        "status_labels": ["verified", "self_reported", "pending", "needs_review", "missing", "expired", "disputed"],
        "resubmission_examples": ["证明材料缺少岗位信息", "公司名称与资料不一致", "证明已过期"],
        "default_validity_days": 365,
        "default_next_review_days": 365,
        "default_reverify_strategy": FIELD_REVERIFY_STRATEGY_ANNUAL_REFRESH,
    },
    "income": {
        "label": "收入区间",
        "accepted_documents": ["近半年工资流水", "个税截图", "收入证明", "offer/合同含薪酬页"],
        "accepted_evidence_types": ["salary_slip", "tax_record", "income_certificate", "offer_letter"],
        "accepted_evidence_channels": ["document_upload", "manual_review", "bank_statement"],
        "review_focus": ["只核收入区间，不核精确值", "收入区间是否与职业阶段匹配", "材料时间是否足够新"],
        "status_labels": ["verified", "self_reported", "pending", "needs_review", "missing", "expired", "disputed"],
        "resubmission_examples": ["缺少近半年材料", "无法证明区间", "材料与声明区间差异过大"],
        "default_validity_days": 180,
        "default_next_review_days": 180,
        "default_reverify_strategy": FIELD_REVERIFY_STRATEGY_SEMIANNUAL_REFRESH,
    },
}
INCOME_BRACKETS = [
    "0-10万/年",
    "10-20万/年",
    "20-30万/年",
    "30-50万/年",
    "50-80万/年",
    "80-120万/年",
    "120万+/年",
]

LOW_WAGE_JOB_KEYWORDS = ("助理", "文员", "行政", "客服", "店员", "实习")
HIGH_INCOME_CITY_MISMATCH = {
    "镇江",
    "扬州",
    "湖州",
    "嘉兴",
    "南通",
    "常州",
    "无锡",
}
DEFAULT_PROFILE_PHOTO_COMPARISON_LIMIT = 24
PHOTO_RISK_ENGINE_NAME = "local_photo_authenticity"
PHOTO_RISK_ENGINE_VERSION = "local_photo_authenticity_v1"
PHOTO_RISK_FEATURE_VERSION = "local_photo_authenticity_features_v1"
PHOTO_RISK_ASSET_ROLE_SUBJECT = "subject_profile_photo"
PHOTO_RISK_ASSET_ROLE_COMPARISON = "comparison_profile_photo"


def _generate_submission_id() -> str:
    return f"pfv-{uuid.uuid4().hex[:16]}"


def _generate_profile_review_case_id() -> str:
    return f"prc-{uuid.uuid4().hex[:16]}"


def _profile_photo_authenticity_unavailable_bundle(
    image_sources: list[str] | None,
    *,
    comparison_image_sources: list[str] | None = None,
    reason: str,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "review": {
            "analysis_status": "unavailable",
            "photo_authenticity_score": 0,
            "risk_flags": [],
            "analysis_reason": reason,
            "error_type": type(exc).__name__,
            "error_message": str(exc) or type(exc).__name__,
            "source_count": len(list(image_sources or [])),
            "comparison_source_count": len(list(comparison_image_sources or [])),
            "loaded_source_count": 0,
            "valid_face_photo_count": 0,
            "multiple_face_photo_count": 0,
        },
        "photo_entries": [],
        "comparison_entries": [],
    }


def _analyze_profile_photo_authenticity_with_fallback(
    image_sources: list[str] | None,
    *,
    comparison_image_sources: list[str] | None = None,
) -> dict[str, Any]:
    try:
        module = importlib.import_module(".live_video_local", __package__)
    except Exception as exc:  # noqa: BLE001
        return _profile_photo_authenticity_unavailable_bundle(
            image_sources,
            comparison_image_sources=comparison_image_sources,
            reason="runtime_dependency_unavailable",
            exc=exc,
        )
    try:
        return module.analyze_profile_photo_authenticity_detailed(
            image_sources,
            comparison_image_sources=comparison_image_sources,
        )
    except Exception as exc:  # noqa: BLE001
        return _profile_photo_authenticity_unavailable_bundle(
            image_sources,
            comparison_image_sources=comparison_image_sources,
            reason="analysis_exception",
            exc=exc,
        )


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


def _normalize_evidence_type(field_key: str, evidence_type: Any = None, evidence: dict[str, Any] | None = None) -> str | None:
    raw = _as_text(evidence_type) or _as_text((evidence or {}).get("doc_type")) or _as_text((evidence or {}).get("evidence_type"))
    if not raw:
        return None
    return raw[:64]


def _normalize_evidence_channel(evidence_channel: Any = None, evidence: dict[str, Any] | None = None) -> str | None:
    raw = _as_text(evidence_channel) or _as_text((evidence or {}).get("channel")) or _as_text((evidence or {}).get("evidence_channel"))
    if not raw:
        return "document_upload"
    return raw[:64]


def _normalize_reverify_strategy(field_key: str, reverify_strategy: Any = None) -> str:
    raw = _as_text(reverify_strategy)
    if raw:
        return raw[:32]
    return _as_text(FIELD_POLICIES[field_key].get("default_reverify_strategy")) or FIELD_REVERIFY_STRATEGY_ON_CHANGE


def _build_verification_schedule(
    field_key: str,
    *,
    reviewed_at: datetime,
    validity_days: Any = None,
    next_review_days: Any = None,
    reverify_strategy: Any = None,
) -> dict[str, Any]:
    policy = FIELD_POLICIES[field_key]
    normalized_validity_days = _as_int(validity_days)
    if normalized_validity_days is None or normalized_validity_days <= 0:
        normalized_validity_days = int(policy.get("default_validity_days") or 0)
    normalized_next_review_days = _as_int(next_review_days)
    if normalized_next_review_days is None or normalized_next_review_days <= 0:
        normalized_next_review_days = int(policy.get("default_next_review_days") or normalized_validity_days)
    strategy = _normalize_reverify_strategy(field_key, reverify_strategy)
    expires_at = reviewed_at + timedelta(days=max(1, normalized_validity_days))
    next_review_due_at = reviewed_at + timedelta(days=max(1, normalized_next_review_days))
    if next_review_due_at > expires_at:
        next_review_due_at = expires_at
    return {
        "reverify_strategy": strategy,
        "validity_days": normalized_validity_days,
        "next_review_days": normalized_next_review_days,
        "verification_expires_at": expires_at,
        "next_review_due_at": next_review_due_at,
    }


def _submission_field_status(
    submission_status: str,
    *,
    dispute_status: str | None = None,
) -> str:
    if _as_text(dispute_status) == FIELD_DISPUTE_STATUS_OPEN:
        return "disputed"
    if submission_status in {FIELD_SUBMISSION_STATUS_SUBMITTED, FIELD_SUBMISSION_STATUS_UNDER_REVIEW}:
        return "pending"
    if submission_status == FIELD_SUBMISSION_STATUS_APPROVED:
        return "verified"
    if submission_status == FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED:
        return FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED
    if submission_status == FIELD_SUBMISSION_STATUS_REJECTED:
        return FIELD_SUBMISSION_STATUS_REJECTED
    if submission_status == FIELD_SUBMISSION_STATUS_EXPIRED:
        return FIELD_SUBMISSION_STATUS_EXPIRED
    return "needs_review"


def _parse_income_max_wan(value: Any) -> int | None:
    text = _as_text(value)
    if not text:
        return None
    matches = [int(item) for item in re.findall(r"(\d+)", text)]
    if not matches:
        return None
    if "+" in text:
        return matches[0]
    return max(matches)


def _normalize_income_bracket(value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    if text in INCOME_BRACKETS:
        return text
    compact = text.replace(" ", "")
    if compact.endswith("万") and "/" not in compact and "-" not in compact:
        compact = f"{compact}/年"
    if compact.endswith("万/年") and compact in INCOME_BRACKETS:
        return compact
    if compact.endswith("万+") or compact.endswith("万+/年"):
        amount = _parse_income_max_wan(compact)
        if amount is not None:
            return f"{amount}万+/年"
    matches = re.findall(r"(\d+)", compact)
    if len(matches) >= 2:
        return f"{matches[0]}-{matches[1]}万/年"
    if len(matches) == 1 and "+" in compact:
        return f"{matches[0]}万+/年"
    return text


def _normalize_field_value(field_key: str, value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    if field_key == "income":
        return _normalize_income_bracket(text)
    return text[:255]


def field_verification_policies() -> dict[str, Any]:
    return {
        "fields": FIELD_POLICIES,
        "income_brackets": list(INCOME_BRACKETS),
        "review_statuses": [
            FIELD_SUBMISSION_STATUS_SUBMITTED,
            FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
            FIELD_SUBMISSION_STATUS_APPROVED,
            FIELD_SUBMISSION_STATUS_REJECTED,
            FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
            FIELD_SUBMISSION_STATUS_EXPIRED,
        ],
        "review_decisions": [
            FIELD_REVIEW_DECISION_APPROVE,
            FIELD_REVIEW_DECISION_REJECT,
            FIELD_REVIEW_DECISION_REQUEST_RESUBMISSION,
        ],
        "dispute_statuses": [
            FIELD_DISPUTE_STATUS_NONE,
            FIELD_DISPUTE_STATUS_OPEN,
            FIELD_DISPUTE_STATUS_RESOLVED,
        ],
        "reverify_strategies": [
            FIELD_REVERIFY_STRATEGY_ON_CHANGE,
            FIELD_REVERIFY_STRATEGY_ANNUAL_REFRESH,
            FIELD_REVERIFY_STRATEGY_SEMIANNUAL_REFRESH,
        ],
    }


def _inflate_field_review(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        requested_documents=("requested_documents_json", []),
        metadata=("metadata_json", {}),
    )


def _inflate_field_submission(conn, row: dict[str, Any] | None) -> dict[str, Any] | None:
    out = inflate_json_columns(
        row,
        required_documents=("required_documents_json", []),
        evidence=("evidence_json", {}),
        dispute_evidence=("dispute_evidence_json", {}),
    )
    if not out:
        return None
    out["dispute_status"] = _as_text(out.get("dispute_status")) or FIELD_DISPUTE_STATUS_NONE
    out["reviews"] = list_profile_field_verification_reviews(conn, out["submission_id"])
    out["review_count"] = len(out["reviews"])
    return out


def list_profile_field_verification_reviews(conn, submission_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM profile_field_verification_reviews
        WHERE submission_id = ?
        ORDER BY review_id ASC
        """,
        (submission_id,),
    ).fetchall()
    return [_inflate_field_review(row_to_dict(row)) for row in rows if row]


def get_profile_field_verification_submission(conn, submission_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM profile_field_verification_submissions
        WHERE submission_id = ?
        LIMIT 1
        """,
        (submission_id,),
    ).fetchone()
    return _inflate_field_submission(conn, row_to_dict(row))


def list_profile_field_verification_submissions(
    conn,
    *,
    field_key: str | None = None,
    subject_user_id: str | None = None,
    profile_id: int | None = None,
    statuses: Iterable[Any] | None = None,
    dispute_statuses: Iterable[Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if field_key:
        clauses.append("field_key = ?")
        params.append(_as_text(field_key))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    if profile_id is not None:
        clauses.append("profile_id = ?")
        params.append(int(profile_id))
    normalized_statuses = _unique_ordered(statuses or [])
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(normalized_statuses)
    normalized_dispute_statuses = _unique_ordered(dispute_statuses or [])
    if normalized_dispute_statuses:
        placeholders = ", ".join(["?"] * len(normalized_dispute_statuses))
        clauses.append(f"dispute_status IN ({placeholders})")
        params.extend(normalized_dispute_statuses)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM profile_field_verification_submissions
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_field_submission(conn, row_to_dict(row)) for row in rows if row]


def _resolve_profile_source(source_dsn: str | None, source_table_name: str | None) -> tuple[str, str]:
    dsn, table_name = resolve_profile_source(source_dsn, source_table_name)
    if not dsn or not table_name:
        raise ValueError("source_dsn and source_table_name/profile table are required")
    return dsn, table_name


def _sync_profile_row(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    updates: dict[str, Any],
) -> dict[str, Any]:
    return apply_profile_updates(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
        updates=updates,
    )


def submit_profile_field_verification(
    conn,
    *,
    field_key: str,
    profile_id: int,
    source_dsn: str,
    source_table_name: str | None = None,
    subject_user_id: str | None = None,
    declared_value: Any = None,
    evidence: dict[str, Any] | None = None,
    evidence_type: str | None = None,
    evidence_channel: str | None = None,
    required_documents: Iterable[Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_field = _as_text(field_key)
    if normalized_field not in VALID_FIELD_KEYS:
        raise ValueError("field_key must be education, job, or income")
    ts = current_time(now)
    normalized_source, normalized_table = _resolve_profile_source(source_dsn, source_table_name)
    normalized_value = _normalize_field_value(normalized_field, declared_value)
    normalized_evidence_type = _normalize_evidence_type(normalized_field, evidence_type, evidence)
    normalized_evidence_channel = _normalize_evidence_channel(evidence_channel, evidence)
    submission_id = _generate_submission_id()
    conn.execute(
        """
        INSERT INTO profile_field_verification_submissions (
          submission_id, field_key, subject_user_id, profile_id, source_dsn, source_table_name,
          status, declared_value, approved_value, resubmission_count, required_documents_json,
          evidence_json, evidence_type, evidence_channel, reverify_strategy,
          verification_expires_at, next_review_due_at, dispute_status, dispute_reason,
          dispute_evidence_json, disputed_at, dispute_resolved_at, review_decision,
          review_note, reviewer_id, latest_sync_status, latest_sync_error, submitted_at,
          reviewed_at, approved_at, rejected_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            normalized_field,
            _as_text(subject_user_id) or None,
            int(profile_id),
            normalized_source,
            normalized_table,
            FIELD_SUBMISSION_STATUS_SUBMITTED,
            normalized_value,
            None,
            0,
            json_dumps(_unique_ordered(required_documents or FIELD_POLICIES[normalized_field]["accepted_documents"])),
            json_dumps(_json_safe(dict(evidence or {}))),
            normalized_evidence_type,
            normalized_evidence_channel,
            _normalize_reverify_strategy(normalized_field),
            None,
            None,
            FIELD_DISPUTE_STATUS_NONE,
            None,
            json_dumps({}),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            ts,
            None,
            None,
            None,
            ts,
            ts,
        ),
    )
    sync_result = _sync_profile_row(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
        updates={
            FIELD_KEY_TO_STATUS_COLUMN[normalized_field]: _submission_field_status(FIELD_SUBMISSION_STATUS_SUBMITTED),
            "profile_review_status": "under_review",
        },
    )
    conn.execute(
        """
        UPDATE profile_field_verification_submissions
        SET latest_sync_status = ?, latest_sync_error = ?
        WHERE submission_id = ?
        """,
        (
            sync_result.get("status"),
            sync_result.get("reason"),
            submission_id,
        ),
    )
    conn.commit()
    created = get_profile_field_verification_submission(conn, submission_id)
    assert created is not None
    created["profile_sync"] = sync_result
    return created


def resubmit_profile_field_verification(
    conn,
    submission_id: str,
    *,
    subject_user_id: str | None = None,
    declared_value: Any = None,
    evidence: dict[str, Any] | None = None,
    evidence_type: str | None = None,
    evidence_channel: str | None = None,
    required_documents: Iterable[Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_profile_field_verification_submission(conn, submission_id)
    if not current:
        raise ValueError("profile field verification submission not found")
    if current["status"] not in {
        FIELD_SUBMISSION_STATUS_REJECTED,
        FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
        FIELD_SUBMISSION_STATUS_EXPIRED,
    }:
        raise ValueError("submission is not awaiting resubmission")
    ts = current_time(now)
    normalized_value = _normalize_field_value(current["field_key"], declared_value or current.get("declared_value"))
    merged_evidence = {**(current.get("evidence") or {}), **dict(evidence or {})}
    merged_documents = _unique_ordered(required_documents or current.get("required_documents") or [])
    normalized_evidence_type = _normalize_evidence_type(current["field_key"], evidence_type or current.get("evidence_type"), merged_evidence)
    normalized_evidence_channel = _normalize_evidence_channel(evidence_channel or current.get("evidence_channel"), merged_evidence)
    conn.execute(
        """
        UPDATE profile_field_verification_submissions
        SET status = ?,
            subject_user_id = COALESCE(?, subject_user_id),
            declared_value = ?,
            resubmission_count = resubmission_count + 1,
            required_documents_json = ?,
            evidence_json = ?,
            evidence_type = ?,
            evidence_channel = ?,
            verification_expires_at = NULL,
            next_review_due_at = NULL,
            dispute_status = ?,
            dispute_reason = NULL,
            dispute_evidence_json = ?,
            disputed_at = NULL,
            dispute_resolved_at = NULL,
            review_decision = NULL,
            review_note = NULL,
            reviewer_id = NULL,
            latest_sync_status = NULL,
            latest_sync_error = NULL,
            submitted_at = ?,
            reviewed_at = NULL,
            approved_at = NULL,
            rejected_at = NULL,
            updated_at = ?
        WHERE submission_id = ?
        """,
        (
            FIELD_SUBMISSION_STATUS_SUBMITTED,
            _as_text(subject_user_id) or None,
            normalized_value,
            json_dumps(merged_documents),
            json_dumps(_json_safe(merged_evidence)),
            normalized_evidence_type,
            normalized_evidence_channel,
            FIELD_DISPUTE_STATUS_NONE,
            json_dumps({}),
            ts,
            ts,
            submission_id,
        ),
    )
    sync_result = _sync_profile_row(
        source_dsn=current["source_dsn"],
        source_table_name=current["source_table_name"],
        profile_id=int(current["profile_id"]),
        updates={
            FIELD_KEY_TO_STATUS_COLUMN[current["field_key"]]: _submission_field_status(FIELD_SUBMISSION_STATUS_SUBMITTED),
            "profile_review_status": "under_review",
        },
    )
    conn.execute(
        """
        UPDATE profile_field_verification_submissions
        SET latest_sync_status = ?, latest_sync_error = ?
        WHERE submission_id = ?
        """,
        (sync_result.get("status"), sync_result.get("reason"), submission_id),
    )
    conn.commit()
    updated = get_profile_field_verification_submission(conn, submission_id)
    assert updated is not None
    updated["profile_sync"] = sync_result
    return updated


def review_profile_field_verification(
    conn,
    submission_id: str,
    reviewer_id: str,
    *,
    decision: str,
    review_note: str | None = None,
    approved_value: Any = None,
    requested_documents: Iterable[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    validity_days: int | None = None,
    next_review_days: int | None = None,
    reverify_strategy: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_profile_field_verification_submission(conn, submission_id)
    if not current:
        raise ValueError("profile field verification submission not found")
    if current["status"] not in {
        FIELD_SUBMISSION_STATUS_SUBMITTED,
        FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
    }:
        raise ValueError("submission is not awaiting review")
    normalized_decision = _as_text(decision).lower()
    if normalized_decision not in {
        FIELD_REVIEW_DECISION_APPROVE,
        FIELD_REVIEW_DECISION_REJECT,
        FIELD_REVIEW_DECISION_REQUEST_RESUBMISSION,
    }:
        raise ValueError("decision must be approve, reject, or request_resubmission")
    ts = current_time(now)
    approved_declared = _normalize_field_value(
        current["field_key"],
        approved_value if approved_value is not None else current.get("declared_value"),
    )
    schedule = None
    next_status = FIELD_SUBMISSION_STATUS_REJECTED
    approved_at = None
    rejected_at = None
    if normalized_decision == FIELD_REVIEW_DECISION_APPROVE:
        next_status = FIELD_SUBMISSION_STATUS_APPROVED
        approved_at = ts
        schedule = _build_verification_schedule(
            current["field_key"],
            reviewed_at=ts,
            validity_days=validity_days,
            next_review_days=next_review_days,
            reverify_strategy=reverify_strategy or current.get("reverify_strategy"),
        )
    elif normalized_decision == FIELD_REVIEW_DECISION_REQUEST_RESUBMISSION:
        next_status = FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED
        rejected_at = ts
    else:
        next_status = FIELD_SUBMISSION_STATUS_REJECTED
        rejected_at = ts
    sync_updates = {
        FIELD_KEY_TO_STATUS_COLUMN[current["field_key"]]: _submission_field_status(
            next_status,
            dispute_status=FIELD_DISPUTE_STATUS_NONE,
        ),
        "profile_review_status": "approved" if normalized_decision == FIELD_REVIEW_DECISION_APPROVE else "needs_review",
    }
    if normalized_decision == FIELD_REVIEW_DECISION_APPROVE and approved_declared is not None:
        sync_updates[FIELD_VALUE_COLUMNS[current["field_key"]]] = approved_declared
    sync_result = _sync_profile_row(
        source_dsn=current["source_dsn"],
        source_table_name=current["source_table_name"],
        profile_id=int(current["profile_id"]),
        updates=sync_updates,
    )
    conn.execute(
        """
        INSERT INTO profile_field_verification_reviews (
          submission_id, reviewer_id, decision, review_note, approved_value,
          requested_documents_json, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            _as_text(reviewer_id),
            normalized_decision,
            review_note,
            approved_declared,
            json_dumps(_unique_ordered(requested_documents or [])),
            json_dumps(
                _json_safe(
                {
                    **dict(metadata or {}),
                    "profile_sync": sync_result,
                    "verification_schedule": schedule,
                    "dispute_status_before": current.get("dispute_status") or FIELD_DISPUTE_STATUS_NONE,
                }
                )
            ),
            ts,
        ),
    )
    conn.execute(
        """
        UPDATE profile_field_verification_submissions
        SET status = ?,
            approved_value = ?,
            reverify_strategy = ?,
            verification_expires_at = ?,
            next_review_due_at = ?,
            dispute_status = ?,
            dispute_resolved_at = ?,
            review_decision = ?,
            review_note = ?,
            reviewer_id = ?,
            latest_sync_status = ?,
            latest_sync_error = ?,
            reviewed_at = ?,
            approved_at = ?,
            rejected_at = ?,
            updated_at = ?
        WHERE submission_id = ?
        """,
        (
            next_status,
            approved_declared if normalized_decision == FIELD_REVIEW_DECISION_APPROVE else current.get("approved_value"),
            (schedule or {}).get("reverify_strategy") or current.get("reverify_strategy"),
            (schedule or {}).get("verification_expires_at"),
            (schedule or {}).get("next_review_due_at"),
            FIELD_DISPUTE_STATUS_RESOLVED
            if _as_text(current.get("dispute_status")) == FIELD_DISPUTE_STATUS_OPEN
            else (current.get("dispute_status") or FIELD_DISPUTE_STATUS_NONE),
            ts if _as_text(current.get("dispute_status")) == FIELD_DISPUTE_STATUS_OPEN else current.get("dispute_resolved_at"),
            normalized_decision,
            review_note,
            _as_text(reviewer_id),
            sync_result.get("status"),
            sync_result.get("reason"),
            ts,
            approved_at,
            rejected_at,
            ts,
            submission_id,
        ),
    )
    conn.commit()
    updated = get_profile_field_verification_submission(conn, submission_id)
    assert updated is not None
    updated["profile_sync"] = sync_result
    return updated


def dispute_profile_field_verification(
    conn,
    submission_id: str,
    *,
    subject_user_id: str | None = None,
    dispute_reason: str,
    evidence: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_profile_field_verification_submission(conn, submission_id)
    if not current:
        raise ValueError("profile field verification submission not found")
    if _as_text(current.get("dispute_status")) == FIELD_DISPUTE_STATUS_OPEN:
        raise ValueError("submission dispute is already open")
    if current["status"] not in {
        FIELD_SUBMISSION_STATUS_APPROVED,
        FIELD_SUBMISSION_STATUS_REJECTED,
        FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
        FIELD_SUBMISSION_STATUS_EXPIRED,
    }:
        raise ValueError("submission cannot be disputed in current status")
    reason = _as_text(dispute_reason)
    if not reason:
        raise ValueError("dispute_reason is required")
    ts = current_time(now)
    dispute_evidence = _json_safe(dict(evidence or {}))
    sync_result = _sync_profile_row(
        source_dsn=current["source_dsn"],
        source_table_name=current["source_table_name"],
        profile_id=int(current["profile_id"]),
        updates={
            FIELD_KEY_TO_STATUS_COLUMN[current["field_key"]]: _submission_field_status(
                FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
                dispute_status=FIELD_DISPUTE_STATUS_OPEN,
            ),
            "profile_review_status": "under_review",
        },
    )
    conn.execute(
        """
        INSERT INTO profile_field_verification_reviews (
          submission_id, reviewer_id, decision, review_note, approved_value,
          requested_documents_json, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            _as_text(subject_user_id) or "subject_user",
            FIELD_REVIEW_EVENT_DISPUTE_OPENED,
            reason,
            current.get("approved_value"),
            json_dumps([]),
            json_dumps(_json_safe({"dispute_evidence": dispute_evidence, "profile_sync": sync_result})),
            ts,
        ),
    )
    conn.execute(
        """
        UPDATE profile_field_verification_submissions
        SET status = ?,
            subject_user_id = COALESCE(?, subject_user_id),
            dispute_status = ?,
            dispute_reason = ?,
            dispute_evidence_json = ?,
            disputed_at = ?,
            dispute_resolved_at = NULL,
            latest_sync_status = ?,
            latest_sync_error = ?,
            updated_at = ?
        WHERE submission_id = ?
        """,
        (
            FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
            _as_text(subject_user_id) or None,
            FIELD_DISPUTE_STATUS_OPEN,
            reason,
            json_dumps(dispute_evidence),
            ts,
            sync_result.get("status"),
            sync_result.get("reason"),
            ts,
            submission_id,
        ),
    )
    conn.commit()
    updated = get_profile_field_verification_submission(conn, submission_id)
    assert updated is not None
    updated["profile_sync"] = sync_result
    return updated


def expire_due_profile_field_verifications(
    conn,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ts = current_time(now)
    lim = max(1, min(int(limit), 200))
    rows = conn.execute(
        """
        SELECT submission_id
        FROM profile_field_verification_submissions
        WHERE status = ?
          AND verification_expires_at IS NOT NULL
          AND verification_expires_at <= ?
        ORDER BY verification_expires_at ASC, updated_at ASC
        LIMIT ?
        """,
        (
            FIELD_SUBMISSION_STATUS_APPROVED,
            ts,
            lim,
        ),
    ).fetchall()
    expired: list[dict[str, Any]] = []
    for row in rows:
        submission = get_profile_field_verification_submission(conn, row["submission_id"])
        if not submission:
            continue
        newer = conn.execute(
            """
            SELECT 1
            FROM profile_field_verification_submissions
            WHERE submission_id <> ?
              AND field_key = ?
              AND profile_id = ?
              AND source_dsn = ?
              AND source_table_name = ?
              AND status = ?
              AND COALESCE(approved_at, updated_at) > COALESCE(?, ?)
            LIMIT 1
            """,
            (
                submission["submission_id"],
                submission["field_key"],
                int(submission["profile_id"]),
                submission["source_dsn"],
                submission["source_table_name"],
                FIELD_SUBMISSION_STATUS_APPROVED,
                submission.get("approved_at"),
                submission.get("updated_at"),
            ),
        ).fetchone()
        if newer:
            continue
        sync_result = _sync_profile_row(
            source_dsn=submission["source_dsn"],
            source_table_name=submission["source_table_name"],
            profile_id=int(submission["profile_id"]),
            updates={
                FIELD_KEY_TO_STATUS_COLUMN[submission["field_key"]]: _submission_field_status(FIELD_SUBMISSION_STATUS_EXPIRED),
            },
        )
        conn.execute(
            """
            INSERT INTO profile_field_verification_reviews (
              submission_id, reviewer_id, decision, review_note, approved_value,
              requested_documents_json, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission["submission_id"],
                "system:verification_expiry",
                FIELD_REVIEW_EVENT_MARK_EXPIRED,
                "核验已到期，需重新提交材料复核",
                submission.get("approved_value"),
                json_dumps([]),
                json_dumps({"profile_sync": sync_result}),
                ts,
            ),
        )
        conn.execute(
            """
            UPDATE profile_field_verification_submissions
            SET status = ?,
                latest_sync_status = ?,
                latest_sync_error = ?,
                updated_at = ?
            WHERE submission_id = ?
            """,
            (
                FIELD_SUBMISSION_STATUS_EXPIRED,
                sync_result.get("status"),
                sync_result.get("reason"),
                ts,
                submission["submission_id"],
            ),
        )
        expired.append({"submission_id": submission["submission_id"], "profile_sync": sync_result})
    conn.commit()
    items = [get_profile_field_verification_submission(conn, item["submission_id"]) for item in expired]
    return {
        "expired_count": len(expired),
        "submissions": [
            {**item, "profile_sync": expired[idx]["profile_sync"]}
            for idx, item in enumerate(items)
            if item
        ],
    }


def _load_profile_row(source_dsn: str, source_table_name: str, profile_id: int) -> dict[str, Any]:
    return get_profile(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
    )


def _profile_photo_comparison_limit() -> int:
    try:
        value = int(
            os.environ.get(
                "HER_PROFILE_PHOTO_COMPARISON_LIMIT",
                DEFAULT_PROFILE_PHOTO_COMPARISON_LIMIT,
            )
        )
    except (TypeError, ValueError):
        value = DEFAULT_PROFILE_PHOTO_COMPARISON_LIMIT
    return max(4, min(value, 120))


def _load_profile_photo_records(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
) -> list[dict[str, Any]]:
    return list_profile_photos(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
    )


def _load_comparison_profile_photo_records(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
) -> list[dict[str, Any]]:
    return list_comparison_profile_photos(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
        limit=_profile_photo_comparison_limit(),
    )


def _photo_review_signal_codes_for_hits(hits: list[dict[str, Any]]) -> list[str]:
    signal_codes: list[str] = []
    for hit in hits:
        signal_codes.extend(list(hit.get("signal_codes") or []))
    return _unique_ordered(signal_codes)


def _build_profile_photo_rule_hits(photo_review: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(photo_review, dict) or photo_review.get("analysis_status") != "ok":
        return []

    hits: list[dict[str, Any]] = []
    same_person_score = _as_int(photo_review.get("same_person_score")) or 0
    photo_edit_risk_score = _as_int(photo_review.get("photo_edit_risk_score")) or 0
    deepfake_risk_score = _as_int(photo_review.get("deepfake_risk_score")) or 0
    stolen_media_risk_score = _as_int(photo_review.get("stolen_media_risk_score")) or 0
    risk_flags = set(photo_review.get("risk_flags") or [])

    if "mixed_identity_photos" in risk_flags or same_person_score < 45:
        hits.append(
            {
                "rule_code": "profile_photo_identity_mismatch",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "same_person_score": same_person_score,
                    "same_person_pair_count": photo_review.get("same_person_pair_count"),
                    "same_person_average_similarity": photo_review.get("same_person_average_similarity"),
                    "same_person_min_similarity": photo_review.get("same_person_min_similarity"),
                    "summary": "资料照之间像是混入了不同的人，不像同一个人整组上传。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_mismatch", "identity_mismatch"],
            }
        )
    elif "same_person_uncertain" in risk_flags or same_person_score < 70:
        hits.append(
            {
                "rule_code": "profile_photo_identity_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "same_person_score": same_person_score,
                    "same_person_pair_count": photo_review.get("same_person_pair_count"),
                    "summary": "资料照之间的人脸一致性不稳定，需要补录活体进一步确认。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_mismatch"],
            }
        )

    if "stolen_media_risk" in risk_flags or stolen_media_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_stolen_media_risk",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "stolen_media_risk_score": stolen_media_risk_score,
                    "cross_profile_duplicate_count": photo_review.get("cross_profile_duplicate_count"),
                    "exact_cross_profile_duplicate_count": photo_review.get("exact_cross_profile_duplicate_count"),
                    "summary": "资料照和别的资料高度重复，疑似盗图或多人复用。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )
    elif "duplicate_profile_photo" in risk_flags or stolen_media_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_duplicate_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "stolen_media_risk_score": stolen_media_risk_score,
                    "duplicate_photo_count": photo_review.get("duplicate_photo_count"),
                    "cross_profile_duplicate_count": photo_review.get("cross_profile_duplicate_count"),
                    "summary": "资料照存在重复或近似重复信号，需要进一步确认来源。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    if "deepfake_risk" in risk_flags or deepfake_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_deepfake_risk",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "deepfake_risk_score": deepfake_risk_score,
                    "deepfake_artifact_score": photo_review.get("deepfake_artifact_score"),
                    "deepfake_consistency_score": photo_review.get("deepfake_consistency_score"),
                    "summary": "资料照存在明显 AI 生成或换脸痕迹，不能直接放行。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo", "identity_mismatch"],
            }
        )
    elif "deepfake_uncertain" in risk_flags or deepfake_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_deepfake_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "deepfake_risk_score": deepfake_risk_score,
                    "deepfake_artifact_score": photo_review.get("deepfake_artifact_score"),
                    "summary": "资料照存在可疑的生成/换脸痕迹，需要补录真人活体验证。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    if "photo_heavily_edited" in risk_flags or photo_edit_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_heavily_edited",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "photo_edit_risk_score": photo_edit_risk_score,
                    "skin_smoothing_risk_score": photo_review.get("skin_smoothing_risk_score"),
                    "beauty_filter_risk_score": photo_review.get("beauty_filter_risk_score"),
                    "face_shape_delta_score": photo_review.get("face_shape_delta_score"),
                    "summary": "资料照修图太重，和自然真人状态差距过大。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_heavily_edited"],
            }
        )
    elif "photo_edit_uncertain" in risk_flags or photo_edit_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_edit_uncertain",
                "severity": SEVERITY_LOW,
                "evidence": {
                    "photo_edit_risk_score": photo_edit_risk_score,
                    "edited_photo_count": photo_review.get("edited_photo_count"),
                    "summary": "资料照存在明显美颜/磨皮信号，建议补录真人活体做交叉确认。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_heavily_edited"],
            }
        )

    if "multiple_faces_in_profile_photos" in risk_flags:
        hits.append(
            {
                "rule_code": "profile_photo_multiple_faces",
                "severity": SEVERITY_LOW,
                "evidence": {
                    "multiple_face_photo_count": photo_review.get("multiple_face_photo_count"),
                    "summary": "资料照里出现多人脸，主体验证不够干净。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    return hits


def _build_profile_rule_hits(profile: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    income_max = _parse_income_max_wan(profile.get("income_range"))
    job_text = _as_text(profile.get("job"))
    city = _as_text(profile.get("city"))
    if income_max is not None and income_max >= 80 and any(keyword in job_text for keyword in LOW_WAGE_JOB_KEYWORDS):
        hits.append(
            {
                "rule_code": "income_job_mismatch",
                "severity": SEVERITY_HIGH if income_max >= 120 else SEVERITY_MEDIUM,
                "evidence": {
                    "income_range": profile.get("income_range"),
                    "job": profile.get("job"),
                    "summary": "高收入声明与岗位类型存在明显落差",
                },
                "required_verifications": ["income", "job"],
            }
        )
    if income_max is not None and income_max >= 120 and city in HIGH_INCOME_CITY_MISMATCH:
        hits.append(
            {
                "rule_code": "income_city_mismatch",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "income_range": profile.get("income_range"),
                    "city": profile.get("city"),
                    "summary": "高收入声明与城市常见收入分布存在明显落差",
                },
                "required_verifications": ["income"],
            }
        )
    frequent_changes: dict[str, int] = {}
    for field_key in ("job_change_count_30d", "income_change_count_30d", "city_change_count_30d"):
        count = _as_int(profile.get(field_key))
        if count is not None and count >= 2:
            frequent_changes[field_key] = count
    if frequent_changes:
        hits.append(
            {
                "rule_code": "frequent_profile_changes",
                "severity": SEVERITY_MEDIUM if len(frequent_changes) >= 2 else SEVERITY_LOW,
                "evidence": {
                    "changes": frequent_changes,
                    "summary": "近 30 天关键信息修改频繁",
                },
                "required_verifications": ["job", "income"],
            }
        )
    return hits


def _profile_review_action_for_hits(hits: list[dict[str, Any]]) -> str:
    if any(hit["severity"] == SEVERITY_HIGH for hit in hits) or len(hits) >= 2:
        return ACTION_LIMITED_EXPOSURE
    return ACTION_REQUIRE_VERIFICATION


def _profile_review_severity_for_hits(hits: list[dict[str, Any]]) -> str:
    if any(hit["severity"] == SEVERITY_HIGH for hit in hits):
        return SEVERITY_HIGH
    if any(hit["severity"] == SEVERITY_MEDIUM for hit in hits):
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


def _inflate_profile_review_case(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        rule_codes=("rule_codes_json", []),
        evidence_summary=("evidence_summary_json", {}),
    )


def _inflate_profile_review_appeal(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, evidence=("evidence_json", {}))


def list_profile_review_events(conn, profile_review_case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM profile_review_events
        WHERE profile_review_case_id = ?
        ORDER BY event_id ASC
        """,
        (profile_review_case_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        if not item:
            continue
        item["evidence"] = json_loads(item.pop("evidence_json", None), {})
        out.append(item)
    return out


def get_profile_review_case(conn, profile_review_case_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM profile_review_cases
        WHERE profile_review_case_id = ?
        LIMIT 1
        """,
        (profile_review_case_id,),
    ).fetchone()
    result = _inflate_profile_review_case(row_to_dict(row))
    if result:
        result["events"] = list_profile_review_events(conn, profile_review_case_id)
    return result


def list_profile_review_cases(
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
        clauses.append(f"status IN ({placeholders})")
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
        FROM profile_review_cases
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_profile_review_case(row_to_dict(row)) for row in rows if row]


def get_profile_review_case_appeal(conn, appeal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM profile_review_case_appeals
        WHERE appeal_id = ?
        LIMIT 1
        """,
        (int(appeal_id),),
    ).fetchone()
    return _inflate_profile_review_appeal(row_to_dict(row))


def list_profile_review_case_appeals(
    conn,
    *,
    statuses: Iterable[Any] | None = None,
    profile_review_case_id: str | None = None,
    subject_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    normalized_statuses = _unique_ordered(statuses or [])
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"appeal_status IN ({placeholders})")
        params.extend(normalized_statuses)
    if profile_review_case_id:
        clauses.append("profile_review_case_id = ?")
        params.append(_as_text(profile_review_case_id))
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM profile_review_case_appeals
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_profile_review_appeal(row_to_dict(row)) for row in rows if row]


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
            json_dumps(_json_safe(feature_payload.get("photo_edit_metrics"))) if feature_payload.get("photo_edit_metrics") is not None else None,
            json_dumps(_json_safe(feature_payload.get("deepfake_metrics"))) if feature_payload.get("deepfake_metrics") is not None else None,
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
    severity = _profile_review_severity_for_hits(photo_hits) if photo_hits else SEVERITY_LOW
    recommended_action = _profile_review_action_for_hits(photo_hits) if photo_hits else ACTION_NONE
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


def _sync_photo_risk_review_queue_status(
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


def _persist_photo_risk_service(
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
            severity=_profile_review_severity_for_hits(photo_hits),
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


def _find_open_profile_review_case(
    conn,
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM profile_review_cases
        WHERE source_dsn = ?
          AND source_table_name = ?
          AND profile_id = ?
          AND status IN (?, ?, ?)
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (
            source_dsn,
            source_table_name,
            int(profile_id),
            PROFILE_REVIEW_STATUS_OPEN,
            PROFILE_REVIEW_STATUS_UNDER_REVIEW,
            PROFILE_REVIEW_STATUS_ACTION_APPLIED,
        ),
    ).fetchone()
    return _inflate_profile_review_case(row_to_dict(row))


def evaluate_profile_consistency(
    conn,
    *,
    profile_id: int,
    source_dsn: str,
    source_table_name: str | None = None,
    subject_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    normalized_source, normalized_table = _resolve_profile_source(source_dsn, source_table_name)
    profile = _load_profile_row(normalized_source, normalized_table, int(profile_id))
    from .verification import request_live_video_verification

    subject_photo_records = _load_profile_photo_records(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
    )
    comparison_photo_records = _load_comparison_profile_photo_records(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
    )
    photo_review_bundle = _analyze_profile_photo_authenticity_with_fallback(
        [item["photo_source"] for item in subject_photo_records],
        comparison_image_sources=[item["photo_source"] for item in comparison_photo_records],
    )
    photo_authenticity_review = dict(photo_review_bundle.get("review") or {})
    field_hits = _build_profile_rule_hits(profile)
    photo_hits = _build_profile_photo_rule_hits(photo_authenticity_review)
    hits = list(field_hits) + list(photo_hits)
    photo_review_signal_codes = _photo_review_signal_codes_for_hits(photo_hits)
    case_id: str | None = None
    summary: dict[str, Any] | None = None
    if not hits:
        photo_risk_service = _persist_photo_risk_service(
            conn,
            profile_id=int(profile_id),
            subject_user_id=_as_text(subject_user_id) or None,
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            subject_photo_records=subject_photo_records,
            comparison_photo_records=comparison_photo_records,
            photo_review_bundle=photo_review_bundle,
            profile_review_case_id=None,
            photo_hits=photo_hits,
            photo_review_signal_codes=photo_review_signal_codes,
            now=ts,
        )
        conn.commit()
        return {
            "profile_id": int(profile_id),
            "source_dsn": normalized_source,
            "source_table_name": normalized_table,
            "rule_hits": [],
            "risk_case": None,
            "photo_authenticity_review": photo_authenticity_review,
            "photo_review_request": None,
            "photo_risk_service": photo_risk_service,
        }

    severity = _profile_review_severity_for_hits(hits)
    recommended_action = _profile_review_action_for_hits(hits)
    required_verifications = _unique_ordered(
        rv for hit in hits for rv in list(hit.get("required_verifications") or [])
    )
    summary = {
        "rule_hits": hits,
        "required_verifications": required_verifications,
        "photo_review_signal_codes": photo_review_signal_codes,
        "photo_authenticity_review": photo_authenticity_review,
        "profile_snapshot": {
            "education": profile.get("education"),
            "job": profile.get("job"),
            "income_range": profile.get("income_range"),
            "city": profile.get("city"),
            "job_change_count_30d": profile.get("job_change_count_30d"),
            "income_change_count_30d": profile.get("income_change_count_30d"),
            "city_change_count_30d": profile.get("city_change_count_30d"),
        },
    }
    existing = _find_open_profile_review_case(
        conn,
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
    )
    if existing:
        case_id = existing["profile_review_case_id"]
        conn.execute(
            """
            UPDATE profile_review_cases
            SET subject_user_id = COALESCE(?, subject_user_id),
                severity = ?,
                rule_codes_json = ?,
                evidence_summary_json = ?,
                recommended_action = ?,
                last_evaluated_at = ?,
                updated_at = ?
            WHERE profile_review_case_id = ?
            """,
            (
                _as_text(subject_user_id) or None,
                severity,
                json_dumps([hit["rule_code"] for hit in hits]),
                json_dumps(summary),
                recommended_action,
                ts,
                ts,
                case_id,
            ),
        )
    else:
        case_id = _generate_profile_review_case_id()
        conn.execute(
            """
            INSERT INTO profile_review_cases (
              profile_review_case_id, subject_user_id, profile_id, source_dsn, source_table_name,
              status, severity, rule_codes_json, evidence_summary_json, recommended_action,
              applied_action, resolver_id, resolution_note, last_evaluated_at, created_at, updated_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                _as_text(subject_user_id) or None,
                int(profile_id),
                normalized_source,
                normalized_table,
                PROFILE_REVIEW_STATUS_OPEN,
                severity,
                json_dumps([hit["rule_code"] for hit in hits]),
                json_dumps(summary),
                recommended_action,
                None,
                None,
                None,
                ts,
                ts,
                ts,
                None,
            ),
        )
    photo_risk_service = _persist_photo_risk_service(
        conn,
        profile_id=int(profile_id),
        subject_user_id=_as_text(subject_user_id) or None,
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        subject_photo_records=subject_photo_records,
        comparison_photo_records=comparison_photo_records,
        photo_review_bundle=photo_review_bundle,
        profile_review_case_id=case_id,
        photo_hits=photo_hits,
        photo_review_signal_codes=photo_review_signal_codes,
        now=ts,
    )
    summary["photo_risk_service"] = {
        "score_run_id": photo_risk_service["score_run_id"],
        "decision_id": photo_risk_service["decision_id"],
        "review_queue_item_id": photo_risk_service["review_queue_item_id"],
    }
    conn.execute(
        """
        UPDATE profile_review_cases
        SET evidence_summary_json = ?,
            updated_at = ?
        WHERE profile_review_case_id = ?
        """,
        (
            json_dumps(summary),
            ts,
            case_id,
        ),
    )
    for hit in hits:
        conn.execute(
            """
            INSERT INTO profile_review_events (
              profile_review_case_id, rule_code, severity, evidence_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                hit["rule_code"],
                hit["severity"],
                json_dumps(hit["evidence"]),
                ts,
            ),
        )
    sync_result = _sync_profile_row(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
        updates={
            "profile_review_status": "limited_exposure"
            if recommended_action == ACTION_LIMITED_EXPOSURE
            else "needs_review",
            "job_verification_status": "needs_review" if "job" in required_verifications else None,
            "income_verification_status": "needs_review" if "income" in required_verifications else None,
            "education_verification_status": "needs_review" if "education" in required_verifications else None,
        },
    )
    upsert_moderation_state(
        conn,
        subject_user_id=_as_text(subject_user_id) or None,
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=int(profile_id),
        action=recommended_action,
        reason_code="profile_consistency_rules",
        reason_summary="资料存在明显不一致信号，已进入补件/复核",
        required_verifications=required_verifications,
        evidence={"profile_review_case_id": case_id, "rule_hits": hits},
        linked_profile_review_case_id=case_id,
        now=ts,
    )
    conn.commit()
    photo_review_request = None
    if photo_review_signal_codes and _as_text(subject_user_id):
        photo_review_request = request_live_video_verification(
            conn,
            user_id=_as_text(subject_user_id),
            profile_id=int(profile_id),
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            request_source="profile_photo_authenticity_engine",
            request_reason="平台检测到你的资料照片存在待复核信号，请补录真人活体视频。",
            signal_codes=photo_review_signal_codes,
            risk_case_id=case_id,
            requested_by="system:profile_photo_authenticity_engine",
            now=ts,
        )
    case = get_profile_review_case(conn, case_id)
    assert case is not None
    return {
        "profile_id": int(profile_id),
        "source_dsn": normalized_source,
        "source_table_name": normalized_table,
        "rule_hits": hits,
        "risk_case": case,
        "profile_sync": sync_result,
        "photo_authenticity_review": photo_authenticity_review,
        "photo_review_request": photo_review_request,
        "photo_risk_service": photo_risk_service,
    }


def review_profile_review_case(
    conn,
    profile_review_case_id: str,
    resolver_id: str,
    *,
    status: str,
    applied_action: str | None = None,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    from .verification import sync_photo_review_request_from_risk_case

    current = get_profile_review_case(conn, profile_review_case_id)
    if not current:
        raise ValueError("profile review case not found")
    normalized_status = _as_text(status)
    if normalized_status not in {
        PROFILE_REVIEW_STATUS_OPEN,
        PROFILE_REVIEW_STATUS_UNDER_REVIEW,
        PROFILE_REVIEW_STATUS_ACTION_APPLIED,
        PROFILE_REVIEW_STATUS_DISMISSED,
        PROFILE_REVIEW_STATUS_RESOLVED,
    }:
        raise ValueError("invalid profile review status")
    ts = current_time(now)
    resolved_at = ts if normalized_status in {PROFILE_REVIEW_STATUS_DISMISSED, PROFILE_REVIEW_STATUS_RESOLVED} else None
    conn.execute(
        """
        UPDATE profile_review_cases
        SET status = ?,
            applied_action = ?,
            resolver_id = ?,
            resolution_note = ?,
            updated_at = ?,
            resolved_at = ?
        WHERE profile_review_case_id = ?
        """,
        (
            normalized_status,
            _as_text(applied_action) or None,
            _as_text(resolver_id),
            resolution_note,
            ts,
            resolved_at,
            profile_review_case_id,
        ),
    )
    sync_updates = {}
    if normalized_status == PROFILE_REVIEW_STATUS_ACTION_APPLIED and applied_action:
        upsert_moderation_state(
            conn,
            subject_user_id=current.get("subject_user_id"),
            source_dsn=current["source_dsn"],
            source_table_name=current["source_table_name"],
            profile_id=int(current["profile_id"]),
            action=_as_text(applied_action),
            reason_code="profile_review_manual",
            reason_summary=resolution_note or "资料复核人工处置已生效",
            required_verifications=(current.get("evidence_summary") or {}).get("required_verifications"),
            evidence={"profile_review_case_id": profile_review_case_id},
            linked_profile_review_case_id=profile_review_case_id,
            resolver_id=_as_text(resolver_id),
            now=ts,
        )
        sync_updates["profile_review_status"] = (
            "limited_exposure" if _as_text(applied_action) == ACTION_LIMITED_EXPOSURE else "needs_review"
        )
    elif normalized_status in {PROFILE_REVIEW_STATUS_DISMISSED, PROFILE_REVIEW_STATUS_RESOLVED}:
        clear_moderation_state(
            conn,
            subject_user_id=current.get("subject_user_id"),
            source_dsn=current["source_dsn"],
            source_table_name=current["source_table_name"],
            profile_id=int(current["profile_id"]),
            resolver_id=_as_text(resolver_id),
            reason_summary=resolution_note or "资料复核已结束",
            now=ts,
        )
        sync_updates["profile_review_status"] = "approved"
    if sync_updates:
        _sync_profile_row(
            source_dsn=current["source_dsn"],
            source_table_name=current["source_table_name"],
            profile_id=int(current["profile_id"]),
            updates=sync_updates,
        )
    photo_request_sync = {"request": None, "updated": []}
    if _as_text(current.get("subject_user_id")) and (current.get("evidence_summary") or {}).get("photo_review_signal_codes"):
        photo_request_sync = sync_photo_review_request_from_risk_case(
            conn,
            subject_user_id=_as_text(current.get("subject_user_id")),
            profile_id=int(current["profile_id"]) if current.get("profile_id") is not None else None,
            source_dsn=current.get("source_dsn"),
            source_table_name=current.get("source_table_name"),
            signal_codes=(current.get("evidence_summary") or {}).get("photo_review_signal_codes"),
            risk_case_id=profile_review_case_id,
            applied_action=_as_text(applied_action) or None,
            status=normalized_status,
            resolution_note=resolution_note,
            resolver_id=_as_text(resolver_id),
            now=ts,
        )
    photo_risk_queue_sync = _sync_photo_risk_review_queue_status(
        conn,
        profile_review_case_id=profile_review_case_id,
        status=normalized_status,
        applied_action=_as_text(applied_action) or None,
        resolution_note=resolution_note,
        resolver_id=_as_text(resolver_id),
        now=ts,
    )
    conn.commit()
    updated = get_profile_review_case(conn, profile_review_case_id)
    assert updated is not None
    updated["photo_review_request_sync"] = photo_request_sync
    updated["photo_risk_queue_sync"] = photo_risk_queue_sync
    return updated


def submit_profile_review_case_appeal(
    conn,
    profile_review_case_id: str,
    appellant_id: str,
    *,
    reason_text: str,
    evidence: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_profile_review_case(conn, profile_review_case_id)
    if not current:
        raise ValueError("profile review case not found")
    moderation_state = get_active_moderation_state(
        conn,
        subject_user_id=current.get("subject_user_id"),
        source_dsn=current["source_dsn"],
        source_table_name=current["source_table_name"],
        profile_id=int(current["profile_id"]),
    )
    current_action = (
        _as_text((moderation_state or {}).get("applied_action"))
        or _as_text(current.get("applied_action"))
        or _as_text(current.get("recommended_action"))
    )
    if current_action != ACTION_LIMITED_EXPOSURE:
        raise ValueError("profile review case is not eligible for appeal")
    ts = current_time(now)
    conn.execute(
        """
        INSERT INTO profile_review_case_appeals (
          profile_review_case_id, subject_key, subject_user_id, appellant_id, appeal_status,
          reason_text, evidence_json, resolution_note, resolver_id, created_at, updated_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_review_case_id,
            (moderation_state or {}).get("subject_key"),
            current.get("subject_user_id"),
            _as_text(appellant_id),
            PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED,
            _as_text(reason_text),
            json_dumps(dict(evidence or {})),
            None,
            None,
            ts,
            ts,
            None,
        ),
    )
    conn.commit()
    appeal = get_profile_review_case_appeal(conn, int(conn.lastrowid))
    assert appeal is not None
    return appeal


def review_profile_review_case_appeal(
    conn,
    appeal_id: int,
    resolver_id: str,
    *,
    appeal_status: str,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = get_profile_review_case_appeal(conn, int(appeal_id))
    if not current:
        raise ValueError("profile review appeal not found")
    normalized_status = _as_text(appeal_status)
    if normalized_status not in {
        PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED,
        PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW,
        PROFILE_REVIEW_APPEAL_STATUS_UPHELD,
        PROFILE_REVIEW_APPEAL_STATUS_REJECTED,
    }:
        raise ValueError("invalid profile review appeal_status")
    ts = current_time(now)
    conn.execute(
        """
        UPDATE profile_review_case_appeals
        SET appeal_status = ?,
            resolution_note = ?,
            resolver_id = ?,
            updated_at = ?,
            resolved_at = ?
        WHERE appeal_id = ?
        """,
        (
            normalized_status,
            resolution_note,
            _as_text(resolver_id),
            ts,
            ts if normalized_status in {PROFILE_REVIEW_APPEAL_STATUS_UPHELD, PROFILE_REVIEW_APPEAL_STATUS_REJECTED} else None,
            int(appeal_id),
        ),
    )
    if normalized_status == PROFILE_REVIEW_APPEAL_STATUS_UPHELD:
        risk_case = get_profile_review_case(conn, current["profile_review_case_id"])
        if risk_case and risk_case["status"] not in {PROFILE_REVIEW_STATUS_DISMISSED, PROFILE_REVIEW_STATUS_RESOLVED}:
            review_profile_review_case(
                conn,
                current["profile_review_case_id"],
                _as_text(resolver_id),
                status=PROFILE_REVIEW_STATUS_RESOLVED,
                resolution_note=resolution_note or "申诉成立，恢复资料曝光",
                now=ts,
            )
    conn.commit()
    updated = get_profile_review_case_appeal(conn, int(appeal_id))
    assert updated is not None
    return updated


__all__ = [
    "dispute_profile_field_verification",
    "evaluate_profile_consistency",
    "expire_due_profile_field_verifications",
    "field_verification_policies",
    "get_photo_risk_review_queue_item",
    "get_photo_risk_score_run",
    "get_profile_field_verification_submission",
    "get_profile_review_case",
    "get_profile_review_case_appeal",
    "list_photo_risk_review_queue",
    "list_photo_risk_score_runs",
    "list_profile_field_verification_submissions",
    "list_profile_field_verification_reviews",
    "list_profile_review_case_appeals",
    "list_profile_review_cases",
    "list_profile_review_events",
    "resubmit_profile_field_verification",
    "review_profile_field_verification",
    "review_profile_review_case_appeal",
    "review_profile_review_case",
    "submit_profile_review_case_appeal",
    "submit_profile_field_verification",
]
