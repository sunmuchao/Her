"""Safety, trust, and risk HTTP handlers for chat-facing gateway routes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import unquote

from chat_system import (  # type: ignore[import-untyped]
    batch_review_risk_cases,
    build_fraud_network_overview,
    build_risk_case_playback,
    build_risk_weekly_dashboard,
    build_thread_risk_overview,
    build_user_trust_hub,
    evaluate_fraud_network,
    get_fraud_network_profile,
    get_risk_appeal,
    list_fraud_network_profiles,
    list_member_reports,
    list_meeting_feedback,
    list_risk_appeals,
    list_risk_cases,
    list_risk_signals,
    record_fraud_network_observation,
    review_risk_appeal,
    review_risk_case,
    submit_meeting_feedback,
    submit_member_report,
    submit_risk_appeal,
)

from .chat_routes import chat_require_requester
from .http_helpers import (
    _json_safe,
    _normalize_boolish,
    _parse_int,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _statuses_from_query,
)
from .role_sets import CHAT_RISK_REVIEW_ROLES, INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES


class ChatSafetyGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

    def _resolve_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...
def rest_user_trust_hub(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    user_id = gateway._resolve_actor_bound_id(environ, q.get("user_id"), field_name="user_id")
    profile_id = int(q["profile_id"]) if q.get("profile_id") not in (None, "") else None
    limit = _parse_int(q.get("limit", 20), 20)

    # 🔧 FIX: build_user_trust_hub 是跨数据库聚合函数，需要拆分调用
    # 1. Verification 相关（查询 her_verification 或 her_chat）
    try:
        verification_data = gateway._with_chat(
            lambda conn: {
                "photo_requests": list_photo_review_requests(conn, user_id=user_id, profile_id=profile_id, limit=limit),
                "field_submissions": list_profile_field_verification_submissions(conn, subject_user_id=user_id, profile_id=profile_id, limit=limit),
                "notifications": list_verification_notifications(conn, user_id=user_id, limit=limit * 5),
            }
        )
    except Exception:
        verification_data = {}

    # 2. Risk 相关（查询 her_risk）
    try:
        risk_data = gateway._with_risk(
            lambda conn: {
                "profile_cases": list_profile_review_cases(
                    conn, subject_user_id=user_id, profile_id=profile_id,
                    statuses=["open", "under_review", "action_applied", "dismissed", "resolved"],
                    limit=limit
                ),
                "chat_cases": list_risk_cases(conn, subject_user_id=user_id, limit=limit),
                "chat_appeals": list_risk_appeals(conn, subject_user_id=user_id, limit=limit * 3),
                "profile_appeals": list_profile_review_case_appeals(conn, subject_user_id=user_id, limit=limit * 3),
            }
        )
    except Exception:
        risk_data = {}

    # 3. 合并数据并构建 trust_hub
    hub = {
        "user_id": user_id,
        "verification_items": verification_data.get("photo_requests", []),
        "field_submissions": verification_data.get("field_submissions", []),
        "profile_cases": risk_data.get("profile_cases", []),
        "chat_cases": risk_data.get("chat_cases", []),
        "trust_score": None,  # 需要计算
        "risk_level": "normal",
    }
    return 200, {"trust_hub": _json_safe(hub)}


def rest_chat_submit_report(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    thread_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    reporter_id = gateway._resolve_actor_bound_id(environ, body.get("reporter_id"), field_name="reporter_id")
    report_type = body.get("report_type")
    if not report_type:
        raise ValueError("report_type is required")
    out = gateway._with_risk(
        submit_member_report,
        thread_id,
        reporter_id,
        str(report_type),
        reason_text=body.get("reason_text"),
        message_id=int(body["message_id"]) if body.get("message_id") is not None else None,
        reported_user_id=str(body["reported_user_id"]) if body.get("reported_user_id") is not None else None,
        reported_profile_id=int(body["reported_profile_id"]) if body.get("reported_profile_id") is not None else None,
        reported_source_dsn=body.get("reported_source_dsn") or body.get("source_dsn"),
        reported_source_table_name=body.get("reported_source_table_name") or body.get("source_table_name"),
        evidence=body.get("evidence"),
        now=now,
    )
    return 201, {"report": _json_safe(out.get("report")), "risk_case": _json_safe(out.get("risk_case"))}


def rest_chat_submit_meeting_feedback(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    thread_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    reviewer_id = gateway._resolve_actor_bound_id(environ, body.get("reviewer_id"), field_name="reviewer_id")
    out = gateway._with_risk(
        submit_meeting_feedback,
        thread_id,
        reviewer_id,
        counterpart_user_id=str(body["counterpart_user_id"]) if body.get("counterpart_user_id") is not None else None,
        counterpart_profile_id=int(body["counterpart_profile_id"]) if body.get("counterpart_profile_id") is not None else None,
        counterpart_source_dsn=body.get("counterpart_source_dsn") or body.get("source_dsn"),
        counterpart_source_table_name=body.get("counterpart_source_table_name") or body.get("source_table_name"),
        photo_match_status=body.get("photo_match_status") or "unclear",
        profile_consistency_status=body.get("profile_consistency_status") or "unclear",
        income_job_consistency_status=body.get("income_job_consistency_status") or "unclear",
        safety_concern_status=body.get("safety_concern_status") or "none",
        willing_video_status=body.get("willing_video_status") or "unknown",
        willing_offline_status=body.get("willing_offline_status") or "unknown",
        notes=body.get("notes"),
        now=now,
    )
    return 201, _json_safe(out)


def rest_chat_list_reports(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot list chat reports",
    )
    q = _query_dict(environ)
    rows = gateway._with_risk(
        list_member_reports,
        thread_id=q.get("thread_id") or None,
        risk_case_id=q.get("risk_case_id") or None,
        reported_user_id=q.get("reported_user_id") or None,
        limit=_parse_int(q.get("limit") or "100", 100),
    )
    return 200, {"reports": _json_safe(rows)}


def rest_chat_list_meeting_feedback(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    reviewer_id = q.get("reviewer_id") or None
    actor = gateway._current_actor(environ)
    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
        reviewer_id = gateway._resolve_actor_bound_id(environ, reviewer_id, field_name="reviewer_id")
    rows = gateway._with_risk(
        list_meeting_feedback,
        thread_id=q.get("thread_id") or None,
        counterpart_user_id=q.get("counterpart_user_id") or None,
        reviewer_id=reviewer_id,
        limit=_parse_int(q.get("limit") or "100", 100),
    )
    return 200, {"meeting_feedback": _json_safe(rows)}


def rest_chat_list_risk_cases(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot list chat risk cases",
    )
    q = _query_dict(environ)
    rows = gateway._with_risk(
        list_risk_cases,
        statuses=_statuses_from_query(q),
        subject_user_id=q.get("subject_user_id") or None,
        thread_id=q.get("thread_id") or None,
        limit=_parse_int(q.get("limit") or "100", 100),
    )
    return 200, {"risk_cases": _json_safe(rows)}


def rest_chat_list_risk_signals(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot list chat risk signals",
    )
    q = _query_dict(environ)
    rows = gateway._with_risk(
        list_risk_signals,
        thread_id=q.get("thread_id") or None,
        subject_user_id=q.get("subject_user_id") or None,
        signal_code=q.get("signal_code") or None,
        limit=_parse_int(q.get("limit") or "100", 100),
    )
    return 200, {"risk_signals": _json_safe(rows)}


def rest_chat_record_fraud_network_observation(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
        message="current actor cannot record fraud network observations",
    )
    now = _parse_optional_now(body)
    subject_user_id = body.get("subject_user_id")
    if not subject_user_id:
        raise ValueError("subject_user_id is required")
    out = gateway._with_risk(
        record_fraud_network_observation,
        subject_user_id=str(subject_user_id),
        source_dsn=body.get("source_dsn") or body.get("source"),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
        thread_id=body.get("thread_id"),
        case_id=body.get("case_id"),
        risk_case_id=body.get("risk_case_id"),
        report_id=int(body["report_id"]) if body.get("report_id") is not None else None,
        source_type=str(body.get("source_type") or body.get("report_source") or "system_rule"),
        event_type=str(body.get("event_type") or "manual_observation"),
        signal_codes=body.get("signal_codes"),
        evidence=body.get("evidence"),
        message_body=body.get("message_body"),
        now=now,
        evaluate=_normalize_boolish(body.get("evaluate"), default=True),
    )
    return 201, {"observation": _json_safe(out)}


def rest_chat_evaluate_fraud_network(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
        message="current actor cannot evaluate fraud networks",
    )
    now = _parse_optional_now(body)
    subject_user_id = body.get("subject_user_id")
    if not subject_user_id:
        raise ValueError("subject_user_id is required")
    out = gateway._with_risk(
        evaluate_fraud_network,
        str(subject_user_id),
        source_dsn=body.get("source_dsn") or body.get("source"),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
        now=now,
        propagate=_normalize_boolish(body.get("propagate"), default=True),
    )
    return 200, {"fraud_network": _json_safe(out)}


def rest_chat_list_fraud_networks(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot list fraud networks",
    )
    q = _query_dict(environ)
    min_score_raw = q.get("minimum_score") or q.get("min_score")
    try:
        minimum_score = int(min_score_raw) if min_score_raw not in (None, "") else None
    except ValueError:
        minimum_score = None
    rows = gateway._with_risk(
        list_fraud_network_profiles,
        review_statuses=_statuses_from_query(q),
        subject_user_id=q.get("subject_user_id") or None,
        minimum_score=minimum_score,
        limit=_parse_int(q.get("limit") or "100", 100),
    )
    return 200, {"fraud_networks": _json_safe(rows)}


def rest_chat_get_fraud_network(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    subject_user_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot inspect fraud networks",
    )
    profile = gateway._with_risk(get_fraud_network_profile, subject_user_id)
    if not profile:
        return 404, {"error": {"code": "not_found", "message": "fraud network not found"}}
    overview = gateway._with_risk(build_fraud_network_overview, subject_user_id)
    return 200, {"fraud_network": _json_safe(overview)}


def rest_chat_get_risk_case(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    risk_case_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot inspect chat risk cases",
    )
    try:
        playback = gateway._with_risk(build_risk_case_playback, risk_case_id)
    except ValueError:
        return 404, {"error": {"code": "not_found", "message": "risk case not found"}}
    return 200, _json_safe(playback)


def rest_chat_thread_risk_overview(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    thread_id: str,
) -> tuple[int, dict[str, Any]]:
    requester_id = chat_require_requester(gateway, environ, _query_dict(environ))
    out = gateway._with_risk(build_thread_risk_overview, thread_id, requester_id)
    return 200, {"risk_overview": _json_safe(out)}


def rest_chat_review_risk_case(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    risk_case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    resolver_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("resolver_id"),
        field_name="resolver_id",
        roles=CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot review chat risk cases",
    )
    status = body.get("status")
    if not status:
        raise ValueError("status is required")
    risk_case = gateway._with_risk(
        review_risk_case,
        risk_case_id,
        resolver_id,
        status=str(status),
        applied_action=body.get("applied_action"),
        resolution_note=body.get("resolution_note"),
        now=now,
    )
    return 200, {"risk_case": _json_safe(risk_case)}


def rest_chat_batch_review_risk_cases(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    resolver_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("resolver_id"),
        field_name="resolver_id",
        roles=CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot batch review chat risk cases",
    )
    if body.get("status") in (None, ""):
        raise ValueError("status is required")
    risk_case_ids = body.get("risk_case_ids")
    if not isinstance(risk_case_ids, list):
        raise ValueError("risk_case_ids must be a list")
    out = gateway._with_risk(
        batch_review_risk_cases,
        risk_case_ids=risk_case_ids,
        resolver_id=resolver_id,
        status=str(body["status"]),
        applied_action=body.get("applied_action"),
        resolution_note=body.get("resolution_note"),
        now=now,
    )
    return 200, _json_safe(out)


def rest_chat_submit_risk_appeal(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    risk_case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    appellant_id = gateway._resolve_actor_bound_id(environ, body.get("appellant_id"), field_name="appellant_id")
    if body.get("reason_text") in (None, ""):
        raise ValueError("reason_text is required")
    appeal = gateway._with_risk(
        submit_risk_appeal,
        risk_case_id,
        appellant_id,
        reason_text=str(body["reason_text"]),
        evidence=body.get("evidence"),
        now=now,
    )
    return 201, {"appeal": _json_safe(appeal)}


def rest_chat_list_risk_appeals(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot list chat risk appeals",
    )
    q = _query_dict(environ)
    rows = gateway._with_risk(
        list_risk_appeals,
        statuses=_statuses_from_query(q),
        risk_case_id=q.get("risk_case_id") or None,
        subject_user_id=q.get("subject_user_id") or None,
        limit=_parse_int(q.get("limit", 100), 100),
    )
    return 200, {"appeals": _json_safe(rows)}


def rest_chat_get_risk_appeal(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    appeal_id: int,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot inspect chat risk appeals",
    )
    appeal = gateway._with_risk(get_risk_appeal, int(appeal_id))
    if not appeal:
        return 404, {"error": {"code": "not_found", "message": "risk appeal not found"}}
    return 200, {"appeal": _json_safe(appeal)}


def rest_chat_review_risk_appeal(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    appeal_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    resolver_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("resolver_id"),
        field_name="resolver_id",
        roles=CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot review chat risk appeals",
    )
    if body.get("appeal_status") in (None, ""):
        raise ValueError("appeal_status is required")
    appeal = gateway._with_risk(
        review_risk_appeal,
        int(appeal_id),
        resolver_id,
        appeal_status=str(body["appeal_status"]),
        resolution_note=body.get("resolution_note"),
        now=now,
    )
    return 200, {"appeal": _json_safe(appeal)}


def rest_chat_risk_dashboard(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
        message="current actor cannot view the risk dashboard",
    )
    q = _query_dict(environ)
    now = datetime.fromisoformat(q["now"]) if q.get("now") else None
    dashboard = gateway._with_risk(
        build_risk_weekly_dashboard,
        now=now,
        days=_parse_int(q.get("days", 7), 7),
    )
    return 200, {"dashboard": _json_safe(dashboard)}


def dispatch_chat_safety_rest(
    gateway: ChatSafetyGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/user-center/trust-hub" and method == "GET":
        return rest_user_trust_hub(gateway, environ)
    if path == "/v1/chat/reports" and method == "GET":
        return rest_chat_list_reports(gateway, environ)
    if path == "/v1/chat/meeting-feedback" and method == "GET":
        return rest_chat_list_meeting_feedback(gateway, environ)
    if path == "/v1/chat/risk-cases" and method == "GET":
        return rest_chat_list_risk_cases(gateway, environ)
    if path == "/v1/chat/risk-cases/batch-review" and method == "POST":
        return rest_chat_batch_review_risk_cases(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/chat/risk-signals" and method == "GET":
        return rest_chat_list_risk_signals(gateway, environ)
    if path == "/v1/chat/fraud-networks" and method == "GET":
        return rest_chat_list_fraud_networks(gateway, environ)
    if path == "/v1/chat/fraud-networks/observations" and method == "POST":
        return rest_chat_record_fraud_network_observation(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/chat/fraud-networks/evaluate" and method == "POST":
        return rest_chat_evaluate_fraud_network(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/chat/risk-appeals" and method == "GET":
        return rest_chat_list_risk_appeals(gateway, environ)
    if path == "/v1/chat/risk-dashboard/weekly" and method == "GET":
        return rest_chat_risk_dashboard(gateway, environ)
    match = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)/review", path)
    if match and method == "POST":
        return rest_chat_review_risk_case(gateway, environ, match.group(1), _parse_json_body(_read_body(environ)))
    match = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)/appeals", path)
    if match and method == "POST":
        return rest_chat_submit_risk_appeal(gateway, environ, match.group(1), _parse_json_body(_read_body(environ)))
    match = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)", path)
    if match and method == "GET":
        return rest_chat_get_risk_case(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/chat/risk-appeals/([^/]+)", path)
    if match and method == "GET":
        return rest_chat_get_risk_appeal(gateway, environ, int(match.group(1)))
    match = re.fullmatch(r"/v1/chat/risk-appeals/([^/]+)/review", path)
    if match and method == "POST":
        return rest_chat_review_risk_appeal(gateway, environ, int(match.group(1)), _parse_json_body(_read_body(environ)))
    match = re.fullmatch(r"/v1/chat/fraud-networks/([^/]+)", path)
    if match and method == "GET":
        return rest_chat_get_fraud_network(gateway, environ, unquote(match.group(1)))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)/risk-overview", path)
    if match and method == "GET":
        return rest_chat_thread_risk_overview(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)/reports", path)
    if match and method == "POST":
        return rest_chat_submit_report(gateway, environ, match.group(1), _parse_json_body(_read_body(environ)))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)/meeting-feedback", path)
    if match and method == "POST":
        return rest_chat_submit_meeting_feedback(gateway, environ, match.group(1), _parse_json_body(_read_body(environ)))
    return None
