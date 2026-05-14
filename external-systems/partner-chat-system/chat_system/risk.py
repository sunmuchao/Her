"""Minimal member-report and risk-case loop for chat fraud / mismatch handling."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

try:
    from pymysql.err import IntegrityError
except ImportError:  # pragma: no cover
    IntegrityError = Exception  # type: ignore[misc,assignment]

from match_domain.outbox import append_outbox_pending
from observability import alert_signal
from partner_moderation import (
    clear_moderation_state,
    get_active_moderation_state,
    infer_required_verifications,
    parse_source_ref,
    upsert_moderation_state,
)

from .events import (
    chat_member_report_submitted_event,
    chat_meeting_feedback_submitted_event,
    chat_risk_case_event,
    chat_risk_case_reviewed_event,
    chat_risk_signal_detected_event,
)
from .fraud_graph import get_fraud_network_profile, record_fraud_network_observation
from .storage import json_dumps, json_loads, row_to_dict
from .verification import sync_photo_review_request_from_risk_case

REPORT_SOURCE_USER = "user_report"
REPORT_SOURCE_SYSTEM = "system_rule"

RISK_STATUS_OPEN = "open"
RISK_STATUS_UNDER_REVIEW = "under_review"
RISK_STATUS_ACTION_APPLIED = "action_applied"
RISK_STATUS_DISMISSED = "dismissed"
RISK_STATUS_RESOLVED = "resolved"

ACTION_NONE = "none"
ACTION_WARN = "warn"
ACTION_MANUAL_REVIEW = "manual_review"
ACTION_REQUIRE_VERIFICATION = "require_verification"
ACTION_LIMIT_CHAT = "limit_chat"
ACTION_FREEZE = "freeze"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

SCAM_SIGNAL_RULES = (
    ("investment", ("投资", "理财", "带单", "内幕", "稳赚", "保本", "高收益", "币圈", "虚拟币", "炒币")),
    ("money_transfer", ("借钱", "转账", "打款", "汇款", "垫付", "周转", "红包", "手续费")),
    ("off_platform", ("加微信", "加微", "微信聊", "vx", "vx", "v信", "telegram", "tg", "whatsapp", "line", "外部群")),
)

INVESTMENT_SOLICITATION_MARKERS = (
    "带你",
    "带单",
    "收益",
    "稳赚",
    "高收益",
    "进群",
    "项目",
    "跟投",
    "老师",
    "内幕",
    "保本",
    "翻倍",
    "入金",
)
BENIGN_INVESTMENT_CONTEXT_MARKERS = (
    "投资研究",
    "研究员",
    "券商",
    "基金公司",
    "私募工作",
    "工作内容",
    "岗位",
    "职业",
    "行业",
    "宏观",
    "二级市场",
    "一级市场",
    "分析师",
)
BENIGN_PAYMENT_CONTEXT_MARKERS = (
    "aa",
    "饭钱",
    "餐费",
    "车费",
    "门票",
    "拼单",
    "报销",
)

REPORT_TYPE_SIGNAL_MAP = {
    "fraud": ("fraud_report",),
    "investment": ("investment",),
    "money": ("money_transfer",),
    "off_platform": ("off_platform",),
    "suspected_fake_photo": ("suspected_fake_photo",),
    "photo_heavily_edited": ("photo_heavily_edited",),
    "photo_mismatch": ("photo_mismatch",),
    "profile_mismatch": ("profile_mismatch",),
    "income_mismatch": ("income_mismatch",),
    "job_mismatch": ("job_mismatch",),
    "education_mismatch": ("education_mismatch",),
    "identity_mismatch": ("identity_mismatch",),
    "behavior_pattern": ("behavior_pattern",),
    "video_refusal": ("video_refusal",),
}

SEVERITY_ORDER = {
    SEVERITY_LOW: 1,
    SEVERITY_MEDIUM: 2,
    SEVERITY_HIGH: 3,
}

ACTION_ORDER = {
    ACTION_NONE: 0,
    ACTION_WARN: 1,
    ACTION_MANUAL_REVIEW: 2,
    ACTION_REQUIRE_VERIFICATION: 3,
    ACTION_LIMIT_CHAT: 4,
    ACTION_FREEZE: 5,
}

VIDEO_REFUSAL_MARKERS = (
    "不方便视频",
    "先别视频",
    "不想视频",
    "先不视频",
    "不方便语音",
    "先别语音",
    "不想语音",
    "先不语音",
    "先不见面",
    "暂时不见面",
    "先别见面",
)

SAFETY_SIGNAL_CODE_ORDER = {
    "fraud_report",
    "investment",
    "money_transfer",
    "off_platform",
    "repeated_off_platform_request",
    "high_frequency_outreach",
    "repeated_opening",
    "multi_party_reports",
    "verification_avoidance",
    "photo_mismatch",
    "suspected_fake_photo",
    "photo_heavily_edited",
    "profile_mismatch",
    "income_mismatch",
    "job_mismatch",
    "education_mismatch",
    "identity_mismatch",
    "video_refusal",
}


def current_time(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def _generate_risk_case_id() -> str:
    return f"rsk-{uuid.uuid4().hex[:16]}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _unique_ordered(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _as_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _severity_from_signals(signal_codes: list[str], report_type: str) -> str:
    codes = set(signal_codes)
    if "fraud_report" in codes or report_type == "fraud":
        return SEVERITY_HIGH
    if "investment" in codes or "money_transfer" in codes:
        return SEVERITY_HIGH
    if "high_frequency_outreach" in codes and "repeated_off_platform_request" in codes:
        return SEVERITY_HIGH
    if "multi_party_reports" in codes:
        return SEVERITY_HIGH
    if "off_platform" in codes:
        return SEVERITY_MEDIUM
    if "suspected_fake_photo" in codes or "photo_heavily_edited" in codes:
        return SEVERITY_MEDIUM
    if "repeated_opening" in codes or "verification_avoidance" in codes or "behavior_pattern" in codes:
        return SEVERITY_MEDIUM
    if "photo_mismatch" in codes or "profile_mismatch" in codes:
        return SEVERITY_LOW
    if "income_mismatch" in codes or "job_mismatch" in codes or "education_mismatch" in codes or "identity_mismatch" in codes:
        return SEVERITY_MEDIUM
    return SEVERITY_MEDIUM if report_type == "other" else SEVERITY_LOW


def _recommended_action_for(severity: str, report_count: int, signal_codes: list[str]) -> str:
    codes = set(signal_codes)
    if severity == SEVERITY_HIGH:
        if "fraud_report" in codes or "investment" in codes or "money_transfer" in codes:
            return ACTION_LIMIT_CHAT
        if "multi_party_reports" in codes or "high_frequency_outreach" in codes:
            return ACTION_REQUIRE_VERIFICATION
        return ACTION_MANUAL_REVIEW
    if severity == SEVERITY_MEDIUM:
        if "suspected_fake_photo" in codes or "photo_heavily_edited" in codes or "photo_mismatch" in codes:
            return ACTION_REQUIRE_VERIFICATION
        if "income_mismatch" in codes or "job_mismatch" in codes or "education_mismatch" in codes or "identity_mismatch" in codes:
            return ACTION_REQUIRE_VERIFICATION
        if report_count >= 2:
            return ACTION_LIMIT_CHAT
        return ACTION_MANUAL_REVIEW
    if report_count >= 3:
        return ACTION_MANUAL_REVIEW
    return ACTION_WARN


def _merge_severity(left: str, right: str) -> str:
    return left if SEVERITY_ORDER.get(left, 0) >= SEVERITY_ORDER.get(right, 0) else right


def _merge_action(left: str, right: str) -> str:
    return left if ACTION_ORDER.get(left, 0) >= ACTION_ORDER.get(right, 0) else right


def _contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _normalize_message_pattern(body: str) -> str:
    text = _as_text(body).lower()
    if not text:
        return ""
    text = re.sub(r"\d+", "#", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，,。.!！?？:：;；\-_/\\|]+", "", text)
    return text[:96]


def _distinct_thread_count(rows: list[dict[str, Any]]) -> int:
    return len({_as_text(row.get("thread_id")) for row in rows if _as_text(row.get("thread_id"))})


def _insert_risk_signal(
    conn,
    *,
    thread_id: str,
    case_id: str,
    subject_user_id: str,
    signal_code: str,
    severity: str,
    source_type: str,
    created_at: datetime,
    message_id: int | None = None,
    report_id: int | None = None,
    risk_case_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO chat_risk_signals (
          thread_id, case_id, subject_user_id, message_id, report_id, risk_case_id,
          source_type, signal_code, severity, evidence_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            case_id,
            subject_user_id,
            int(message_id) if message_id is not None else None,
            int(report_id) if report_id is not None else None,
            risk_case_id,
            source_type,
            signal_code,
            severity,
            json_dumps(evidence or {}),
            created_at,
        ),
    )
    signal_id = int(conn.lastrowid)
    append_outbox_pending(
        conn,
        event=chat_risk_signal_detected_event(
            signal_id=signal_id,
            thread_id=thread_id,
            case_id=case_id,
            subject_user_id=subject_user_id,
            signal_code=signal_code,
            severity=severity,
            source_type=source_type,
            occurred_at=created_at,
        ),
        source_row_table="chat_risk_signals",
        source_row_id=signal_id,
        created_at_str=created_at.isoformat(sep=" "),
    )
    return signal_id


def _inflate_risk_signal(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["evidence"] = json_loads(out.pop("evidence_json", None), {})
    return out


def _inflate_meeting_feedback(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["derived_report_ids"] = json_loads(out.pop("derived_report_ids_json", None), [])
    return out


def _get_thread(conn, thread_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM chat_threads WHERE thread_id = ? LIMIT 1", (thread_id,))
    row = row_to_dict(cur.fetchone())
    if not row:
        return None
    row["metadata"] = json_loads(row.pop("metadata_json", None), {})
    return row


def _get_message(conn, message_id: int) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM chat_messages WHERE message_id = ? LIMIT 1", (int(message_id),))
    row = row_to_dict(cur.fetchone())
    if not row:
        return None
    row["metadata"] = json_loads(row.pop("metadata_json", None), {})
    return row


def _other_participant(thread: dict[str, Any], user_id: str) -> str:
    if user_id == thread["participant_a_id"]:
        return str(thread["participant_b_id"])
    return str(thread["participant_a_id"])


def _participant_profile_ref(thread: dict[str, Any], user_id: str) -> dict[str, Any]:
    metadata = thread.get("metadata") or {}
    participant_profiles = metadata.get("participant_profiles") if isinstance(metadata, dict) else None
    if not isinstance(participant_profiles, dict):
        return {}
    raw = participant_profiles.get(user_id) or {}
    if not isinstance(raw, dict):
        return {}
    source_dsn, source_table_name = parse_source_ref(
        raw.get("source_dsn") or raw.get("source"),
        raw.get("source_table_name") or raw.get("table_name"),
    )
    try:
        profile_id = int(raw.get("profile_id")) if raw.get("profile_id") is not None else None
    except (TypeError, ValueError):
        profile_id = None
    return {
        "profile_id": profile_id,
        "source_dsn": source_dsn,
        "source_table_name": source_table_name,
    }


def _merge_subject_profile_ref(
    thread: dict[str, Any],
    target_user: str,
    *,
    reported_profile_id: int | None = None,
    reported_source_dsn: str | None = None,
    reported_source_table_name: str | None = None,
) -> dict[str, Any]:
    explicit_source_dsn, explicit_source_table_name = parse_source_ref(
        reported_source_dsn,
        reported_source_table_name,
    )
    if reported_profile_id is not None and explicit_source_dsn and explicit_source_table_name:
        return {
            "profile_id": int(reported_profile_id),
            "source_dsn": explicit_source_dsn,
            "source_table_name": explicit_source_table_name,
        }
    derived = _participant_profile_ref(thread, target_user)
    if reported_profile_id is not None:
        derived["profile_id"] = int(reported_profile_id)
    if explicit_source_dsn:
        derived["source_dsn"] = explicit_source_dsn
    if explicit_source_table_name:
        derived["source_table_name"] = explicit_source_table_name
    return derived


def _inflate_report(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["signal_codes"] = json_loads(out.pop("signal_codes_json", None), [])
    out["evidence"] = json_loads(out.pop("evidence_json", None), {})
    return out


def _inflate_risk_case(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["source_types"] = json_loads(out.pop("source_types_json", None), [])
    out["signal_codes"] = json_loads(out.pop("signal_codes_json", None), [])
    out["evidence_summary"] = json_loads(out.pop("evidence_summary_json", None), {})
    return out


def detect_risk_signals(*, message_body: str | None = None, reason_text: str | None = None, report_type: str = "other") -> list[str]:
    corpus = " ".join(part for part in (_as_text(message_body), _as_text(reason_text)) if part).lower()
    signal_codes: list[str] = list(REPORT_TYPE_SIGNAL_MAP.get(report_type, ()))
    for signal_code, keywords in SCAM_SIGNAL_RULES:
        if not _contains_any(corpus, keywords):
            continue
        if signal_code == "investment":
            if _contains_any(corpus, BENIGN_INVESTMENT_CONTEXT_MARKERS) and not _contains_any(
                corpus,
                INVESTMENT_SOLICITATION_MARKERS + SCAM_SIGNAL_RULES[1][1] + SCAM_SIGNAL_RULES[2][1],
            ):
                continue
            if not _contains_any(corpus, INVESTMENT_SOLICITATION_MARKERS) and not _contains_any(
                corpus,
                ("带单", "内幕", "稳赚", "高收益", "币圈", "虚拟币", "炒币"),
            ):
                continue
        if signal_code == "money_transfer":
            if _contains_any(corpus, BENIGN_PAYMENT_CONTEXT_MARKERS) and not _contains_any(
                corpus,
                ("借钱", "手续费", "周转", "垫付"),
            ):
                continue
        signal_codes.append(signal_code)
    return _unique_ordered(signal_codes)


def detect_behavior_risk_signals(
    conn,
    *,
    thread_id: str,
    author_id: str,
    body: str,
    now: datetime,
) -> tuple[list[str], dict[str, Any]]:
    signal_codes: list[str] = []
    evidence: dict[str, Any] = {}
    normalized_body = _normalize_message_pattern(body)

    recent_rows = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT thread_id, body, created_at
            FROM chat_messages
            WHERE author_id = ?
              AND visibility = ?
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (author_id, "dyadic", now - timedelta(hours=24)),
        ).fetchall()
    ]
    recent_rows = [row for row in recent_rows if row]

    recent_30m = [
        row
        for row in recent_rows
        if datetime.fromisoformat(_as_text(row.get("created_at"))) >= now - timedelta(minutes=30)
    ]
    if _distinct_thread_count(recent_30m) >= 3:
        signal_codes.append("high_frequency_outreach")
        evidence["distinct_threads_30m"] = _distinct_thread_count(recent_30m)

    if normalized_body:
        repeated_threads = {
            _as_text(row.get("thread_id"))
            for row in recent_rows
            if _normalize_message_pattern(_as_text(row.get("body"))) == normalized_body
        }
        if len(repeated_threads) >= 3:
            signal_codes.append("repeated_opening")
            evidence["repeated_opening_threads_24h"] = len(repeated_threads)
            evidence["message_pattern"] = normalized_body

    if _contains_any(_as_text(body).lower(), SCAM_SIGNAL_RULES[2][1]):
        prior_off_platform = conn.execute(
            """
            SELECT COUNT(DISTINCT thread_id) AS c
            FROM chat_risk_signals
            WHERE subject_user_id = ?
              AND signal_code IN (?, ?)
              AND created_at >= ?
            """,
            (
                author_id,
                "off_platform",
                "repeated_off_platform_request",
                now - timedelta(days=7),
            ),
        ).fetchone()
        prior_count = int((prior_off_platform or {}).get("c") or 0) + (1 if thread_id else 0)
        if prior_count >= 2:
            signal_codes.append("repeated_off_platform_request")
            evidence["off_platform_threads_7d"] = prior_count

    if _contains_any(_as_text(body).lower(), VIDEO_REFUSAL_MARKERS):
        refusals = conn.execute(
            """
            SELECT COUNT(DISTINCT thread_id) AS c
            FROM chat_messages
            WHERE author_id = ?
              AND visibility = ?
              AND created_at >= ?
              AND (
                LOWER(body) LIKE ? OR LOWER(body) LIKE ? OR LOWER(body) LIKE ?
                OR LOWER(body) LIKE ? OR LOWER(body) LIKE ? OR LOWER(body) LIKE ?
              )
            """,
            (
                author_id,
                "dyadic",
                now - timedelta(days=14),
                "%视频%",
                "%语音%",
                "%见面%",
                "%不方便%",
                "%先别%",
                "%不想%",
            ),
        ).fetchone()
        refusal_count = int((refusals or {}).get("c") or 0)
        if refusal_count >= 2:
            signal_codes.append("verification_avoidance")
            evidence["verification_avoidance_threads_14d"] = refusal_count

    return _unique_ordered(signal_codes), evidence


def _subject_user_report_threads(conn, subject_user_id: str, *, now: datetime) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT thread_id) AS c
        FROM chat_member_reports
        WHERE reported_user_id = ?
          AND report_source = ?
          AND created_at >= ?
        """,
        (subject_user_id, REPORT_SOURCE_USER, now - timedelta(days=30)),
    ).fetchone()
    return int((row or {}).get("c") or 0)


def get_active_chat_restriction(conn, thread_id: str, subject_user_id: str) -> str | None:
    cur = conn.execute(
        """
        SELECT applied_action
        FROM chat_risk_cases
        WHERE thread_id = ?
          AND subject_user_id = ?
          AND status = ?
          AND applied_action IN (?, ?)
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (
            thread_id,
            subject_user_id,
            RISK_STATUS_ACTION_APPLIED,
            ACTION_LIMIT_CHAT,
            ACTION_FREEZE,
        ),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _as_text(row["applied_action"]) or None


def _global_chat_restriction(conn, subject_user_id: str) -> str | None:
    state = get_active_moderation_state(conn, subject_user_id=subject_user_id)
    action = _as_text((state or {}).get("applied_action"))
    if action in {ACTION_LIMIT_CHAT, ACTION_FREEZE}:
        return action
    return None


def _is_proactive_outreach(conn, thread_id: str, subject_user_id: str) -> bool:
    thread = _get_thread(conn, thread_id)
    if not thread:
        return False
    counterpart = _other_participant(thread, subject_user_id)
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM chat_messages
        WHERE thread_id = ?
          AND visibility = ?
          AND author_id = ?
        """,
        (thread_id, "dyadic", counterpart),
    ).fetchone()
    return int((row or {}).get("c") or 0) == 0


def assert_message_allowed(conn, thread_id: str, subject_user_id: str) -> None:
    restriction = get_active_chat_restriction(conn, thread_id, subject_user_id)
    if restriction:
        raise ValueError(f"author is currently restricted by risk action: {restriction}")
    global_restriction = _global_chat_restriction(conn, subject_user_id)
    if global_restriction == ACTION_FREEZE:
        raise ValueError("author is currently restricted by risk action: freeze")
    if global_restriction == ACTION_LIMIT_CHAT and _is_proactive_outreach(conn, thread_id, subject_user_id):
        raise ValueError("author is currently restricted by risk action: limit_chat")


def _find_open_risk_case(conn, thread_id: str, subject_user_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT *
        FROM chat_risk_cases
        WHERE thread_id = ?
          AND subject_user_id = ?
          AND status IN (?, ?, ?)
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (
            thread_id,
            subject_user_id,
            RISK_STATUS_OPEN,
            RISK_STATUS_UNDER_REVIEW,
            RISK_STATUS_ACTION_APPLIED,
        ),
    )
    return _inflate_risk_case(row_to_dict(cur.fetchone()))


def get_risk_case(conn, risk_case_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_risk_cases WHERE risk_case_id = ? LIMIT 1",
        (risk_case_id,),
    )
    return _inflate_risk_case(row_to_dict(cur.fetchone()))


def list_risk_cases(
    conn,
    *,
    statuses: list[str] | None = None,
    subject_user_id: str | None = None,
    thread_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if statuses:
        placeholders = ", ".join(["?"] * len(statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend([_as_text(item) for item in statuses])
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(subject_user_id)
    if thread_id:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        f"""
        SELECT *
        FROM chat_risk_cases
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params + [lim]),
    )
    return [_inflate_risk_case(row_to_dict(row)) for row in cur.fetchall()]


def list_member_reports(
    conn,
    *,
    thread_id: str | None = None,
    risk_case_id: str | None = None,
    reported_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if thread_id:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    if risk_case_id:
        clauses.append("risk_case_id = ?")
        params.append(risk_case_id)
    if reported_user_id:
        clauses.append("reported_user_id = ?")
        params.append(reported_user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        f"""
        SELECT *
        FROM chat_member_reports
        {where}
        ORDER BY created_at DESC, report_id DESC
        LIMIT ?
        """,
        tuple(params + [lim]),
    )
    return [_inflate_report(row_to_dict(row)) for row in cur.fetchall()]


def list_risk_signals(
    conn,
    *,
    thread_id: str | None = None,
    subject_user_id: str | None = None,
    signal_code: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if thread_id:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(subject_user_id)
    if signal_code:
        clauses.append("signal_code = ?")
        params.append(signal_code)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        f"""
        SELECT *
        FROM chat_risk_signals
        {where}
        ORDER BY created_at DESC, signal_id DESC
        LIMIT ?
        """,
        tuple(params + [lim]),
    )
    return [_inflate_risk_signal(row_to_dict(row)) for row in cur.fetchall()]


def list_meeting_feedback(
    conn,
    *,
    thread_id: str | None = None,
    counterpart_user_id: str | None = None,
    reviewer_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if thread_id:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    if counterpart_user_id:
        clauses.append("counterpart_user_id = ?")
        params.append(counterpart_user_id)
    if reviewer_id:
        clauses.append("reviewer_id = ?")
        params.append(reviewer_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    cur = conn.execute(
        f"""
        SELECT *
        FROM chat_meeting_feedback
        {where}
        ORDER BY created_at DESC, feedback_id DESC
        LIMIT ?
        """,
        tuple(params + [lim]),
    )
    return [_inflate_meeting_feedback(row_to_dict(row)) for row in cur.fetchall()]


def build_thread_risk_overview(conn, thread_id: str, viewer_id: str) -> dict[str, Any]:
    thread = _get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    if viewer_id not in {thread["participant_a_id"], thread["participant_b_id"]}:
        raise ValueError("viewer is not a participant of this thread")

    counterpart_user_id = _other_participant(thread, viewer_id)
    risk_cases = list_risk_cases(
        conn,
        thread_id=thread_id,
        subject_user_id=counterpart_user_id,
        statuses=[RISK_STATUS_OPEN, RISK_STATUS_UNDER_REVIEW, RISK_STATUS_ACTION_APPLIED],
        limit=20,
    )
    signal_codes = _unique_ordered(
        [code for risk_case in risk_cases for code in list(risk_case.get("signal_codes") or [])]
    )
    active_action = get_active_chat_restriction(conn, thread_id, counterpart_user_id)
    moderation_state = get_active_moderation_state(conn, subject_user_id=counterpart_user_id)
    fraud_network_profile = get_fraud_network_profile(conn, counterpart_user_id)
    global_action = _as_text((moderation_state or {}).get("applied_action")) or None
    caution_messages: list[str] = []
    if any(code in signal_codes for code in {"investment", "money_transfer", "off_platform", "repeated_off_platform_request"}):
        caution_messages.append("对方存在导流 / 投资类风险信号，请勿转账或离开平台沟通。")
    if any(code in signal_codes for code in {"high_frequency_outreach", "repeated_opening", "multi_party_reports"}):
        caution_messages.append("对方存在批量接触或多方举报信号，建议先视频核验再继续。")
    if any(code in signal_codes for code in {"photo_mismatch", "suspected_fake_photo", "photo_heavily_edited", "profile_mismatch", "income_mismatch", "identity_mismatch"}):
        caution_messages.append("对方存在资料一致性风险，建议先确认照片、职业和收入信息。")
    if any(code in signal_codes for code in {"verification_avoidance", "video_refusal"}):
        caution_messages.append("对方存在回避视频或线下核验信号，建议不要过早投入或转移平台。")
    if int((fraud_network_profile or {}).get("graph_risk_score") or 0) >= 60:
        caution_messages.append("对方存在设备 / 联系方式 / 话术模板关联风险，建议只在平台内谨慎沟通。")
    if global_action == ACTION_LIMIT_CHAT:
        caution_messages.append("对方当前处于平台限聊状态，只允许在已有沟通中回复。")
    if global_action == ACTION_FREEZE:
        caution_messages.append("对方当前处于平台冻结状态，请勿继续线下推进。")
    return {
        "thread_id": thread_id,
        "viewer_id": viewer_id,
        "counterpart_user_id": counterpart_user_id,
        "risk_case_count": len(risk_cases),
        "signal_codes": signal_codes,
        "active_action": active_action,
        "global_action": global_action,
        "fraud_network_profile": fraud_network_profile,
        "moderation_state": moderation_state,
        "caution_messages": caution_messages,
        "risk_cases": risk_cases,
    }


def _upsert_risk_case_from_report(
    conn,
    *,
    thread: dict[str, Any],
    report: dict[str, Any],
    signal_codes: list[str],
    severity: str,
    recommended_action: str,
    evidence_summary: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], str]:
    existing = _find_open_risk_case(conn, report["thread_id"], report["reported_user_id"])
    event_type = "risk.case.updated"
    if existing:
        source_types = _unique_ordered(list(existing.get("source_types") or []) + [report["report_source"]])
        merged_signals = _unique_ordered(list(existing.get("signal_codes") or []) + list(signal_codes))
        merged_severity = _merge_severity(_as_text(existing.get("severity")) or SEVERITY_LOW, severity)
        report_count = int(existing.get("report_count") or 0) + 1
        merged_recommended = _merge_action(
            _as_text(existing.get("recommended_action")) or ACTION_NONE,
            _recommended_action_for(merged_severity, report_count, merged_signals),
        )
        evidence_summary_payload = {
            **(existing.get("evidence_summary") or {}),
            **evidence_summary,
            "latest_report_id": report["report_id"],
            "latest_report_source": report["report_source"],
        }
        conn.execute(
            """
            UPDATE chat_risk_cases
            SET severity = ?,
                source_types_json = ?,
                signal_codes_json = ?,
                evidence_summary_json = ?,
                report_count = ?,
                recommended_action = ?,
                last_reported_at = ?,
                updated_at = ?
            WHERE risk_case_id = ?
            """,
            (
                merged_severity,
                json_dumps(source_types),
                json_dumps(merged_signals),
                json_dumps(evidence_summary_payload),
                report_count,
                merged_recommended,
                now,
                now,
                existing["risk_case_id"],
            ),
        )
        row = get_risk_case(conn, existing["risk_case_id"])
        assert row is not None
        return row, event_type

    risk_case_id = _generate_risk_case_id()
    source_types = [report["report_source"]]
    payload = {
        **evidence_summary,
        "latest_report_id": report["report_id"],
        "latest_report_source": report["report_source"],
    }
    conn.execute(
        """
        INSERT INTO chat_risk_cases (
          risk_case_id, thread_id, case_id, subject_user_id, status, severity,
          source_types_json, signal_codes_json, evidence_summary_json, report_count,
          recommended_action, applied_action, resolver_id, resolution_note,
          last_reported_at, created_at, updated_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            risk_case_id,
            report["thread_id"],
            report["case_id"],
            report["reported_user_id"],
            RISK_STATUS_OPEN,
            severity,
            json_dumps(source_types),
            json_dumps(signal_codes),
            json_dumps(payload),
            1,
            recommended_action,
            None,
            None,
            None,
            now,
            now,
            now,
            None,
        ),
    )
    row = get_risk_case(conn, risk_case_id)
    assert row is not None
    return row, "risk.case.opened"


def submit_member_report(
    conn,
    thread_id: str,
    reporter_id: str,
    report_type: str,
    *,
    reason_text: str | None = None,
    message_id: int | None = None,
    reported_user_id: str | None = None,
    reported_profile_id: int | None = None,
    reported_source_dsn: str | None = None,
    reported_source_table_name: str | None = None,
    report_source: str = REPORT_SOURCE_USER,
    signal_codes: list[str] | None = None,
    severity: str | None = None,
    evidence: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    thread = _get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")

    participants = {thread["participant_a_id"], thread["participant_b_id"]}
    reporter_id = _as_text(reporter_id)
    if report_source == REPORT_SOURCE_USER and reporter_id not in participants:
        raise ValueError("reporter is not a participant of this thread")

    message = None
    if message_id is not None:
        message = _get_message(conn, int(message_id))
        if not message or message["thread_id"] != thread_id:
            raise ValueError("message not found in thread")

    target_user = _as_text(reported_user_id)
    if not target_user and message:
        target_user = _as_text(message.get("author_id"))
    if not target_user and report_source == REPORT_SOURCE_USER:
        target_user = _other_participant(thread, reporter_id)
    if not target_user:
        raise ValueError("reported_user_id is required")
    if report_source == REPORT_SOURCE_USER and target_user == reporter_id:
        raise ValueError("cannot report your own message or identity")
    profile_ref = _merge_subject_profile_ref(
        thread,
        target_user,
        reported_profile_id=reported_profile_id,
        reported_source_dsn=reported_source_dsn,
        reported_source_table_name=reported_source_table_name,
    )

    if report_source == REPORT_SOURCE_SYSTEM and message_id is not None:
        cur = conn.execute(
            """
            SELECT *
            FROM chat_member_reports
            WHERE message_id = ? AND report_source = ?
            LIMIT 1
            """,
            (int(message_id), REPORT_SOURCE_SYSTEM),
        )
        existing = _inflate_report(row_to_dict(cur.fetchone()))
        if existing:
            linked_case = get_risk_case(conn, existing["risk_case_id"]) if existing.get("risk_case_id") else None
            return {"report": existing, "risk_case": linked_case}

    derived_signal_codes = detect_risk_signals(
        message_body=_as_text((message or {}).get("body")),
        reason_text=reason_text,
        report_type=report_type,
    )
    prior_cross_thread_reports = _subject_user_report_threads(conn, target_user, now=ts)
    cross_thread_reports = prior_cross_thread_reports + (1 if report_source == REPORT_SOURCE_USER else 0)
    extra_signal_codes: list[str] = []
    if cross_thread_reports >= 3:
        extra_signal_codes.append("multi_party_reports")
    merged_signal_codes = _unique_ordered(list(signal_codes or []) + derived_signal_codes + extra_signal_codes)
    merged_severity = severity or _severity_from_signals(merged_signal_codes, report_type)
    recommended_action = _recommended_action_for(merged_severity, 1, merged_signal_codes)
    evidence = {
        **dict(evidence or {}),
        "reason_text": _as_text(reason_text),
        "message_id": int(message_id) if message_id is not None else None,
        "message_preview": _as_text((message or {}).get("body"))[:512],
        "message_metadata": dict((message or {}).get("metadata") or {}),
        "report_source": report_source,
        "cross_thread_reports_30d": cross_thread_reports,
        "profile_id": profile_ref.get("profile_id"),
        "source_dsn": profile_ref.get("source_dsn"),
        "source_table_name": profile_ref.get("source_table_name"),
    }

    try:
        conn.execute(
            """
            INSERT INTO chat_member_reports (
              thread_id, case_id, message_id, reporter_id, reported_user_id, report_source,
              report_type, status, severity, reason_text, signal_codes_json, evidence_json,
              risk_case_id, created_at, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                thread["case_id"],
                int(message_id) if message_id is not None else None,
                reporter_id,
                target_user,
                report_source,
                report_type,
                "submitted",
                merged_severity,
                reason_text,
                json_dumps(merged_signal_codes),
                json_dumps(evidence),
                None,
                ts,
                None,
            ),
        )
    except IntegrityError:
        conn.rollback()
        if report_source == REPORT_SOURCE_SYSTEM and message_id is not None:
            cur = conn.execute(
                """
                SELECT *
                FROM chat_member_reports
                WHERE message_id = ? AND report_source = ?
                LIMIT 1
                """,
                (int(message_id), REPORT_SOURCE_SYSTEM),
            )
            existing = _inflate_report(row_to_dict(cur.fetchone()))
            if existing:
                linked_case = get_risk_case(conn, existing["risk_case_id"]) if existing.get("risk_case_id") else None
                return {"report": existing, "risk_case": linked_case}
        raise

    report_id = int(conn.lastrowid)
    report = {
        "report_id": report_id,
        "thread_id": thread_id,
        "case_id": thread["case_id"],
        "message_id": int(message_id) if message_id is not None else None,
        "reporter_id": reporter_id,
        "reported_user_id": target_user,
        "report_source": report_source,
        "report_type": report_type,
        "status": "submitted",
        "severity": merged_severity,
        "signal_codes": merged_signal_codes,
        "evidence": evidence,
        "created_at": ts,
    }

    risk_case, risk_case_event_type = _upsert_risk_case_from_report(
        conn,
        thread=thread,
        report=report,
        signal_codes=merged_signal_codes,
        severity=merged_severity,
        recommended_action=recommended_action,
        evidence_summary={
            "thread_id": thread_id,
            "message_id": int(message_id) if message_id is not None else None,
            "signal_codes": merged_signal_codes,
            "severity": merged_severity,
            "recommended_action": recommended_action,
            "profile_id": profile_ref.get("profile_id"),
            "source_dsn": profile_ref.get("source_dsn"),
            "source_table_name": profile_ref.get("source_table_name"),
        },
        now=ts,
    )
    conn.execute(
        """
        UPDATE chat_member_reports
        SET risk_case_id = ?, status = ?
        WHERE report_id = ?
        """,
        (risk_case["risk_case_id"], "linked", report_id),
    )
    append_outbox_pending(
        conn,
        event=chat_member_report_submitted_event(
            thread_id=thread_id,
            case_id=thread["case_id"],
            report_id=report_id,
            reporter_id=reporter_id,
            reported_user_id=target_user,
            report_type=report_type,
            severity=merged_severity,
            signal_codes=merged_signal_codes,
            risk_case_id=risk_case["risk_case_id"],
            occurred_at=ts,
        ),
        source_row_table="chat_member_reports",
        source_row_id=report_id,
        created_at_str=ts.isoformat(sep=" "),
    )
    append_outbox_pending(
        conn,
        event=chat_risk_case_event(
            event_type=risk_case_event_type,
            risk_case_id=risk_case["risk_case_id"],
            case_id=thread["case_id"],
            thread_id=thread_id,
            subject_user_id=target_user,
            severity=risk_case["severity"],
            recommended_action=risk_case["recommended_action"],
            report_count=int(risk_case["report_count"] or 0),
            occurred_at=ts,
        ),
        source_row_table="chat_risk_cases",
        source_row_id=None,
        created_at_str=ts.isoformat(sep=" "),
    )
    for signal_code in merged_signal_codes:
        _insert_risk_signal(
            conn,
            thread_id=thread_id,
            case_id=thread["case_id"],
            subject_user_id=target_user,
            message_id=int(message_id) if message_id is not None else None,
            report_id=report_id,
            risk_case_id=risk_case["risk_case_id"],
            source_type=report_source,
            signal_code=signal_code,
            severity=merged_severity,
            evidence=evidence,
            created_at=ts,
        )
    record_fraud_network_observation(
        conn,
        subject_user_id=target_user,
        source_dsn=profile_ref.get("source_dsn"),
        source_table_name=profile_ref.get("source_table_name"),
        profile_id=profile_ref.get("profile_id"),
        thread_id=thread_id,
        case_id=thread["case_id"],
        risk_case_id=risk_case["risk_case_id"],
        report_id=report_id,
        source_type=report_source,
        event_type="member_report" if report_source == REPORT_SOURCE_USER else "system_rule",
        signal_codes=merged_signal_codes,
        evidence=evidence,
        message_body=_as_text((message or {}).get("body")),
        now=ts,
    )
    conn.commit()

    if merged_severity == SEVERITY_HIGH:
        alert_signal(
            "chat_risk_high_severity",
            "chat risk case triggered high severity signals",
            severity="critical",
            thread_id=thread_id,
            case_id=thread["case_id"],
            report_id=report_id,
            risk_case_id=risk_case["risk_case_id"],
            signal_codes=merged_signal_codes,
        )

    fresh_report = _inflate_report(
        row_to_dict(
            conn.execute(
                "SELECT * FROM chat_member_reports WHERE report_id = ? LIMIT 1",
                (report_id,),
            ).fetchone()
        )
    )
    assert fresh_report is not None
    return {"report": fresh_report, "risk_case": risk_case}


def maybe_capture_message_risk_signal(
    conn,
    *,
    thread_id: str,
    message_id: int,
    author_id: str,
    body: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    ts = current_time(now)
    signal_codes = detect_risk_signals(message_body=body, reason_text=None, report_type="other")
    behavior_signal_codes, behavior_evidence = detect_behavior_risk_signals(
        conn,
        thread_id=thread_id,
        author_id=author_id,
        body=body,
        now=ts,
    )
    signal_codes = _unique_ordered(signal_codes + behavior_signal_codes)
    if not signal_codes:
        return None
    severity = _severity_from_signals(signal_codes, "other")
    reason = "system_rule:auto_keyword_hit"
    report_type = "auto_keyword"
    if behavior_signal_codes and not detect_risk_signals(message_body=body, reason_text=None, report_type="other"):
        reason = "system_rule:behavior_pattern_hit"
        report_type = "behavior_pattern"
    elif behavior_signal_codes:
        reason = "system_rule:keyword_and_behavior_hit"
    return submit_member_report(
        conn,
        thread_id,
        "system",
        report_type,
        reason_text=reason,
        message_id=message_id,
        reported_user_id=author_id,
        report_source=REPORT_SOURCE_SYSTEM,
        signal_codes=signal_codes,
        severity=severity,
        now=ts,
    )


def submit_meeting_feedback(
    conn,
    thread_id: str,
    reviewer_id: str,
    *,
    counterpart_user_id: str | None = None,
    counterpart_profile_id: int | None = None,
    counterpart_source_dsn: str | None = None,
    counterpart_source_table_name: str | None = None,
    photo_match_status: str = "unclear",
    profile_consistency_status: str = "unclear",
    income_job_consistency_status: str = "unclear",
    safety_concern_status: str = "none",
    willing_video_status: str = "unknown",
    willing_offline_status: str = "unknown",
    notes: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    thread = _get_thread(conn, thread_id)
    if not thread:
        raise ValueError("thread not found")
    reviewer_id = _as_text(reviewer_id)
    if reviewer_id not in {thread["participant_a_id"], thread["participant_b_id"]}:
        raise ValueError("reviewer is not a participant of this thread")
    target_user = _as_text(counterpart_user_id) or _other_participant(thread, reviewer_id)
    if target_user == reviewer_id:
        raise ValueError("counterpart_user_id cannot be reviewer")
    profile_ref = _merge_subject_profile_ref(
        thread,
        target_user,
        reported_profile_id=counterpart_profile_id,
        reported_source_dsn=counterpart_source_dsn,
        reported_source_table_name=counterpart_source_table_name,
    )

    report_specs: list[tuple[str, str]] = []
    if _as_text(photo_match_status) in {"mismatch", "very_different", "heavily_edited"}:
        report_specs.append(("photo_mismatch", "见面后反馈：照片与真人差异较大"))
    if _as_text(profile_consistency_status) in {"mismatch", "hidden_info"}:
        report_specs.append(("profile_mismatch", "见面后反馈：资料与真人表达存在明显不一致"))
    if _as_text(income_job_consistency_status) in {"mismatch", "exaggerated"}:
        report_specs.append(("income_mismatch", "见面后反馈：收入或职业信息存在明显夸大"))
    if _as_text(safety_concern_status) in {"money_request", "investment_pitch", "off_platform_pressure"}:
        report_specs.append(("fraud", "见面后反馈：存在借钱、投资或强导流风险"))
    if _as_text(willing_video_status) == "refused":
        report_specs.append(("video_refusal", "见面后反馈：长期拒绝视频或语音核验"))

    generated_reports: list[dict[str, Any]] = []
    risk_cases_by_id: dict[str, dict[str, Any]] = {}
    for report_type, reason_text in report_specs:
        out = submit_member_report(
            conn,
            thread_id,
            reviewer_id,
            report_type,
            reason_text=reason_text,
            reported_user_id=target_user,
            reported_profile_id=profile_ref.get("profile_id"),
            reported_source_dsn=profile_ref.get("source_dsn"),
            reported_source_table_name=profile_ref.get("source_table_name"),
            now=ts,
        )
        if out.get("report"):
            generated_reports.append(out["report"])
        if out.get("risk_case"):
            risk_cases_by_id[str(out["risk_case"]["risk_case_id"])] = out["risk_case"]

    conn.execute(
        """
        INSERT INTO chat_meeting_feedback (
          thread_id, case_id, reviewer_id, counterpart_user_id,
          photo_match_status, profile_consistency_status, income_job_consistency_status,
          safety_concern_status, willing_video_status, willing_offline_status,
          notes, derived_report_ids_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            thread["case_id"],
            reviewer_id,
            target_user,
            _as_text(photo_match_status) or "unclear",
            _as_text(profile_consistency_status) or "unclear",
            _as_text(income_job_consistency_status) or "unclear",
            _as_text(safety_concern_status) or "none",
            _as_text(willing_video_status) or "unknown",
            _as_text(willing_offline_status) or "unknown",
            notes,
            json_dumps([int(report["report_id"]) for report in generated_reports]),
            ts,
        ),
    )
    feedback_id = int(conn.lastrowid)
    append_outbox_pending(
        conn,
        event=chat_meeting_feedback_submitted_event(
            feedback_id=feedback_id,
            thread_id=thread_id,
            case_id=thread["case_id"],
            reviewer_id=reviewer_id,
            counterpart_user_id=target_user,
            derived_report_ids=[int(report["report_id"]) for report in generated_reports],
            occurred_at=ts,
        ),
        source_row_table="chat_meeting_feedback",
        source_row_id=feedback_id,
        created_at_str=ts.isoformat(sep=" "),
    )
    conn.commit()
    feedback = _inflate_meeting_feedback(
        row_to_dict(
            conn.execute(
                "SELECT * FROM chat_meeting_feedback WHERE feedback_id = ? LIMIT 1",
                (feedback_id,),
            ).fetchone()
        )
    )
    assert feedback is not None
    return {
        "feedback": feedback,
        "generated_reports": generated_reports,
        "risk_cases": list(risk_cases_by_id.values()),
    }


def review_risk_case(
    conn,
    risk_case_id: str,
    resolver_id: str,
    *,
    status: str,
    applied_action: str | None = None,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = current_time(now)
    current = get_risk_case(conn, risk_case_id)
    if not current:
        raise ValueError("risk case not found")

    status = _as_text(status)
    if status not in {
        RISK_STATUS_OPEN,
        RISK_STATUS_UNDER_REVIEW,
        RISK_STATUS_ACTION_APPLIED,
        RISK_STATUS_DISMISSED,
        RISK_STATUS_RESOLVED,
    }:
        raise ValueError("invalid risk case status")
    applied_action = _as_text(applied_action) or None
    if status == RISK_STATUS_ACTION_APPLIED and applied_action not in {
        ACTION_WARN,
        ACTION_REQUIRE_VERIFICATION,
        ACTION_LIMIT_CHAT,
        ACTION_FREEZE,
    }:
        raise ValueError("applied_action must be warn, require_verification, limit_chat, or freeze when status=action_applied")

    resolved_at = ts if status in {RISK_STATUS_DISMISSED, RISK_STATUS_RESOLVED} else None
    conn.execute(
        """
        UPDATE chat_risk_cases
        SET status = ?,
            applied_action = ?,
            resolver_id = ?,
            resolution_note = ?,
            updated_at = ?,
            resolved_at = ?
        WHERE risk_case_id = ?
        """,
        (
            status,
            applied_action,
            resolver_id,
            resolution_note,
            ts,
            resolved_at,
            risk_case_id,
        ),
    )
    report_status = "dismissed" if status == RISK_STATUS_DISMISSED else "reviewed"
    conn.execute(
        """
        UPDATE chat_member_reports
        SET status = ?, reviewed_at = ?
        WHERE risk_case_id = ?
        """,
        (report_status, ts, risk_case_id),
    )
    updated = get_risk_case(conn, risk_case_id)
    assert updated is not None
    profile_id = updated.get("evidence_summary", {}).get("profile_id")
    source_dsn = updated.get("evidence_summary", {}).get("source_dsn")
    source_table_name = updated.get("evidence_summary", {}).get("source_table_name")
    photo_sync_kwargs = {
        "subject_user_id": updated.get("subject_user_id"),
        "profile_id": int(profile_id) if profile_id is not None else None,
        "source_dsn": source_dsn,
        "source_table_name": source_table_name,
        "signal_codes": list(updated.get("signal_codes") or []),
        "risk_case_id": risk_case_id,
        "applied_action": applied_action,
        "status": status,
        "resolution_note": resolution_note,
        "resolver_id": resolver_id,
        "now": ts,
    }
    if status == RISK_STATUS_ACTION_APPLIED and applied_action:
        upsert_moderation_state(
            conn,
            subject_user_id=updated.get("subject_user_id"),
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=int(profile_id) if profile_id is not None else None,
            action=applied_action,
            reason_code="chat_risk_case",
            reason_summary=resolution_note or "聊天风险案件已执行人工处置",
            required_verifications=infer_required_verifications(updated.get("signal_codes")),
            evidence={"risk_case_id": risk_case_id, "signal_codes": updated.get("signal_codes")},
            linked_risk_case_id=risk_case_id,
            resolver_id=resolver_id,
            now=ts,
        )
    elif status in {RISK_STATUS_DISMISSED, RISK_STATUS_RESOLVED}:
        clear_moderation_state(
            conn,
            subject_user_id=updated.get("subject_user_id"),
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=int(profile_id) if profile_id is not None else None,
            resolver_id=resolver_id,
            reason_summary=resolution_note or "聊天风险案件已关闭",
            now=ts,
        )
    append_outbox_pending(
        conn,
        event=chat_risk_case_reviewed_event(
            risk_case_id=risk_case_id,
            case_id=updated["case_id"],
            thread_id=updated["thread_id"],
            resolver_id=resolver_id,
            status=status,
            applied_action=applied_action,
            occurred_at=ts,
        ),
        source_row_table="chat_risk_cases",
        source_row_id=None,
        created_at_str=ts.isoformat(sep=" "),
    )
    sync_photo_review_request_from_risk_case(conn, **photo_sync_kwargs)
    conn.commit()
    return updated


__all__ = [
    "ACTION_FREEZE",
    "ACTION_LIMIT_CHAT",
    "ACTION_MANUAL_REVIEW",
    "ACTION_REQUIRE_VERIFICATION",
    "ACTION_WARN",
    "REPORT_SOURCE_SYSTEM",
    "REPORT_SOURCE_USER",
    "RISK_STATUS_ACTION_APPLIED",
    "RISK_STATUS_DISMISSED",
    "RISK_STATUS_OPEN",
    "RISK_STATUS_RESOLVED",
    "RISK_STATUS_UNDER_REVIEW",
    "assert_message_allowed",
    "detect_risk_signals",
    "get_active_chat_restriction",
    "get_risk_case",
    "build_thread_risk_overview",
    "list_member_reports",
    "list_meeting_feedback",
    "list_risk_cases",
    "list_risk_signals",
    "maybe_capture_message_risk_signal",
    "review_risk_case",
    "submit_meeting_feedback",
    "submit_member_report",
]
