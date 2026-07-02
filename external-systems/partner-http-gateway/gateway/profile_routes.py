"""Profile verification and review HTTP handlers for the gateway."""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

from chat_system import (  # type: ignore[import-untyped]
    dispute_profile_field_verification,
    evaluate_profile_consistency,
    expire_due_profile_field_verifications,
    field_verification_policies,
    get_photo_risk_score_run,
    get_profile_field_verification_submission,
    get_profile_review_case,
    get_profile_review_case_appeal,
    list_photo_risk_review_queue,
    list_photo_risk_score_runs,
    list_profile_field_verification_submissions,
    list_profile_review_case_appeals,
    list_profile_review_cases,
    resubmit_profile_field_verification,
    review_profile_field_verification,
    review_profile_review_case,
    review_profile_review_case_appeal,
    submit_profile_field_verification,
    submit_profile_review_case_appeal,
)
from profile_service import get_profile  # type: ignore[import-untyped]

from .http_helpers import (
    _json_safe,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _statuses_from_query,
)
from .profile_access import resolve_optional_subject_user_id, resolve_visible_subject_user_id
from .profile_source_defaults import body_with_default_profile_source
from .role_sets import INTERNAL_WRITE_ROLES, PROFILE_REVIEW_ROLES, STAFF_OVERRIDE_ROLES


class ProfileGateway(Protocol):
    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

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


def _dispute_statuses_from_query(q: dict[str, str]) -> list[str] | None:
    return _statuses_from_query(
        {
            "status": q.get("dispute_status"),
            "statuses": q.get("dispute_statuses"),
        }
    )


def _default_profile_source() -> str:
    """Get default profile source DSN."""
    for name in (
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def rest_profile_get_basic_info(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    profile_id: str,
) -> tuple[int, dict[str, Any]]:
    """Get profile basic info for review purposes.

    SECURITY: Requires PROFILE_REVIEW_ROLES or STAFF_OVERRIDE_ROLES.
    """
    # 验证权限
    gateway._require_roles(
        environ,
        PROFILE_REVIEW_ROLES | STAFF_OVERRIDE_ROLES,
        message="current actor cannot access profile basic info",
    )

    # 验证 profile_id 格式
    try:
        profile_id_int = int(profile_id)
    except ValueError:
        return 400, {"error": {"code": "invalid_request", "message": "Invalid profile_id format"}}

    q = _query_dict(environ)
    source_dsn = q.get("source_dsn") or _default_profile_source()
    source_table_name = q.get("source_table_name") or "profiles"
    if not source_dsn:
        return 500, {"error": {"code": "config_error", "message": "Profile source not configured"}}

    # 获取 profile 信息（get_profile 只接受 keyword-only arguments）
    try:
        profile = get_profile(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=profile_id_int,
        )

        if not profile:
            return 404, {"error": {"code": "not_found", "message": "Profile not found"}}

        # 提取基本信息
        basic_info = {
            "profile_id": profile_id_int,
            "user_id": profile.get("user_id"),
            "user_name": profile.get("user_name") or profile.get("name"),
            "nickname": profile.get("nickname"),
            "avatar_url": profile.get("avatar_url") or profile.get("photo_url"),
            "education": profile.get("education"),
        }

        return 200, {"profile": _json_safe(basic_info)}
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": f"Failed to get profile: {e}"}}


def rest_profile_verification_policies(
    _gateway: ProfileGateway,
    _environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return 200, {"policies": _json_safe(field_verification_policies())}


def rest_profile_submit_field_verification(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    body = body_with_default_profile_source(body)
    now = _parse_optional_now(body)
    for key in ("field_key", "profile_id"):
        if body.get(key) in (None, ""):
            raise ValueError(f"{key} is required")
    submission = gateway._with_chat(
        submit_profile_field_verification,
        field_key=str(body["field_key"]),
        profile_id=int(body["profile_id"]),
        source_dsn=str(body["source_dsn"]),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        subject_user_id=resolve_optional_subject_user_id(
            gateway,
            environ,
            body.get("subject_user_id"),
            treat_empty_as_missing=True,
        ),
        declared_value=body.get("declared_value"),
        evidence=body.get("evidence"),
        evidence_type=body.get("evidence_type"),
        evidence_channel=body.get("evidence_channel"),
        required_documents=body.get("required_documents"),
        now=now,
    )
    return 201, {"submission": _json_safe(submission)}


def rest_profile_list_field_verifications(
    gateway: ProfileGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    rows = gateway._with_chat(
        list_profile_field_verification_submissions,
        field_key=q.get("field_key") or None,
        subject_user_id=resolve_visible_subject_user_id(
            gateway,
            environ,
            q.get("subject_user_id") or None,
        ),
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        statuses=_statuses_from_query(q),
        dispute_statuses=_dispute_statuses_from_query(q),
        limit=int(q.get("limit", 100)),
    )
    return 200, {"submissions": _json_safe(rows)}


def rest_profile_get_field_verification(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    submission_id: str,
) -> tuple[int, dict[str, Any]]:
    submission = gateway._with_chat(get_profile_field_verification_submission, submission_id)
    if not submission:
        return 404, {"error": {"code": "not_found", "message": "profile verification submission not found"}}
    gateway._assert_actor_can_access_owner(environ, submission.get("subject_user_id"), field_name="subject_user_id")
    return 200, {"submission": _json_safe(submission)}


def rest_profile_resubmit_field_verification(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    submission_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    submission = gateway._with_chat(
        resubmit_profile_field_verification,
        submission_id,
        subject_user_id=resolve_optional_subject_user_id(
            gateway,
            environ,
            body.get("subject_user_id"),
            treat_empty_as_missing=True,
        ),
        declared_value=body.get("declared_value"),
        evidence=body.get("evidence"),
        evidence_type=body.get("evidence_type"),
        evidence_channel=body.get("evidence_channel"),
        required_documents=body.get("required_documents"),
        now=now,
    )
    return 200, {"submission": _json_safe(submission)}


def rest_profile_dispute_field_verification(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    submission_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    if body.get("dispute_reason") in (None, ""):
        raise ValueError("dispute_reason is required")
    submission = gateway._with_chat(
        dispute_profile_field_verification,
        submission_id,
        subject_user_id=resolve_optional_subject_user_id(
            gateway,
            environ,
            body.get("subject_user_id"),
            treat_empty_as_missing=True,
        ),
        dispute_reason=str(body["dispute_reason"]),
        evidence=body.get("evidence"),
        now=now,
    )
    return 200, {"submission": _json_safe(submission)}


def rest_profile_review_field_verification(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    submission_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    reviewer_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("reviewer_id"),
        field_name="reviewer_id",
        roles=PROFILE_REVIEW_ROLES,
        message="current actor cannot review profile verifications",
    )
    if body.get("decision") in (None, ""):
        raise ValueError("decision is required")
    submission = gateway._with_chat(
        review_profile_field_verification,
        submission_id,
        reviewer_id,
        decision=str(body["decision"]),
        review_note=body.get("review_note"),
        approved_value=body.get("approved_value"),
        requested_documents=body.get("requested_documents"),
        metadata=body.get("metadata"),
        validity_days=body.get("validity_days"),
        next_review_days=body.get("next_review_days"),
        reverify_strategy=body.get("reverify_strategy"),
        now=now,
    )
    return 200, {"submission": _json_safe(submission)}


def rest_profile_expire_due_field_verifications(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
        message="current actor cannot expire due profile verifications",
    )
    result = gateway._with_chat(
        expire_due_profile_field_verifications,
        now=_parse_optional_now(body),
        limit=int(body.get("limit", 100)),
    )
    return 200, _json_safe(result)


def rest_profile_evaluate_review(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
        message="current actor cannot evaluate profile review cases",
    )
    now = _parse_optional_now(body)
    for key in ("profile_id", "source_dsn"):
        if body.get(key) in (None, ""):
            raise ValueError(f"{key} is required")
    out = gateway._with_chat(
        evaluate_profile_consistency,
        profile_id=int(body["profile_id"]),
        source_dsn=str(body["source_dsn"]),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        subject_user_id=body.get("subject_user_id"),
        now=now,
    )
    return 200, _json_safe(out)


def rest_profile_list_review_cases(
    gateway: ProfileGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    rows = gateway._with_chat(
        list_profile_review_cases,
        statuses=_statuses_from_query(q),
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        subject_user_id=resolve_visible_subject_user_id(
            gateway,
            environ,
            q.get("subject_user_id") or None,
        ),
        limit=int(q.get("limit", 100)),
    )
    return 200, {"risk_cases": _json_safe(rows)}


def rest_profile_get_review_case(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    profile_review_case_id: str,
) -> tuple[int, dict[str, Any]]:
    risk_case = gateway._with_chat(get_profile_review_case, profile_review_case_id)
    if not risk_case:
        return 404, {"error": {"code": "not_found", "message": "profile review case not found"}}
    gateway._assert_actor_can_access_owner(environ, risk_case.get("subject_user_id"), field_name="subject_user_id")
    return 200, {"risk_case": _json_safe(risk_case)}


def rest_profile_list_photo_risk_runs(
    gateway: ProfileGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    rows = gateway._with_chat(
        list_photo_risk_score_runs,
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        subject_user_id=resolve_visible_subject_user_id(
            gateway,
            environ,
            q.get("subject_user_id") or None,
        ),
        profile_review_case_id=q.get("profile_review_case_id") or None,
        limit=int(q.get("limit", 100)),
    )
    return 200, {"score_runs": _json_safe(rows)}


def rest_profile_get_photo_risk_run(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    score_run_id: int,
) -> tuple[int, dict[str, Any]]:
    row = gateway._with_chat(get_photo_risk_score_run, int(score_run_id))
    if not row:
        return 404, {"error": {"code": "not_found", "message": "photo risk score run not found"}}
    gateway._assert_actor_can_access_owner(environ, row.get("subject_user_id"), field_name="subject_user_id")
    return 200, {"score_run": _json_safe(row)}


def rest_profile_list_photo_risk_review_queue(
    gateway: ProfileGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        PROFILE_REVIEW_ROLES,
        message="current actor cannot view the photo risk review queue",
    )
    q = _query_dict(environ)
    rows = gateway._with_chat(
        list_photo_risk_review_queue,
        statuses=_statuses_from_query(q, key="queue_status"),
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        subject_user_id=q.get("subject_user_id") or None,
        limit=int(q.get("limit", 100)),
    )
    return 200, {"review_queue": _json_safe(rows)}


def rest_profile_review_case(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    profile_review_case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    resolver_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("resolver_id"),
        field_name="resolver_id",
        roles=PROFILE_REVIEW_ROLES,
        message="current actor cannot review profile risk cases",
    )
    if body.get("status") in (None, ""):
        raise ValueError("status is required")
    risk_case = gateway._with_chat(
        review_profile_review_case,
        profile_review_case_id,
        resolver_id,
        status=str(body["status"]),
        applied_action=body.get("applied_action"),
        resolution_note=body.get("resolution_note"),
        now=now,
    )
    return 200, {"risk_case": _json_safe(risk_case)}


def rest_profile_submit_review_case_appeal(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    profile_review_case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    appellant_id = gateway._resolve_actor_bound_id(environ, body.get("appellant_id"), field_name="appellant_id")
    if body.get("reason_text") in (None, ""):
        raise ValueError("reason_text is required")
    appeal = gateway._with_chat(
        submit_profile_review_case_appeal,
        profile_review_case_id,
        appellant_id,
        reason_text=str(body["reason_text"]),
        evidence=body.get("evidence"),
        now=now,
    )
    return 201, {"appeal": _json_safe(appeal)}


def rest_profile_list_review_case_appeals(
    gateway: ProfileGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    rows = gateway._with_chat(
        list_profile_review_case_appeals,
        statuses=_statuses_from_query(q),
        profile_review_case_id=q.get("profile_review_case_id") or None,
        subject_user_id=resolve_visible_subject_user_id(
            gateway,
            environ,
            q.get("subject_user_id") or None,
        ),
        limit=int(q.get("limit", 100)),
    )
    return 200, {"appeals": _json_safe(rows)}


def rest_profile_get_review_case_appeal(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    appeal_id: int,
) -> tuple[int, dict[str, Any]]:
    appeal = gateway._with_chat(get_profile_review_case_appeal, int(appeal_id))
    if not appeal:
        return 404, {"error": {"code": "not_found", "message": "profile review appeal not found"}}
    gateway._assert_actor_can_access_owner(environ, appeal.get("subject_user_id"), field_name="subject_user_id")
    return 200, {"appeal": _json_safe(appeal)}


def rest_profile_review_review_case_appeal(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    appeal_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    resolver_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("resolver_id"),
        field_name="resolver_id",
        roles=PROFILE_REVIEW_ROLES,
        message="current actor cannot review profile appeals",
    )
    if body.get("appeal_status") in (None, ""):
        raise ValueError("appeal_status is required")
    appeal = gateway._with_chat(
        review_profile_review_case_appeal,
        int(appeal_id),
        resolver_id,
        appeal_status=str(body["appeal_status"]),
        resolution_note=body.get("resolution_note"),
        now=now,
    )
    return 200, {"appeal": _json_safe(appeal)}


def dispatch_profile_rest(
    gateway: ProfileGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/profile-verifications/policies" and method == "GET":
        return rest_profile_verification_policies(gateway, environ)
    if path == "/v1/profile-verifications/submissions" and method == "POST":
        return rest_profile_submit_field_verification(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/profile-verifications/submissions" and method == "GET":
        return rest_profile_list_field_verifications(gateway, environ)
    match = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/resubmit", path)
    if match and method == "POST":
        return rest_profile_resubmit_field_verification(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/dispute", path)
    if match and method == "POST":
        return rest_profile_dispute_field_verification(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/review", path)
    if match and method == "POST":
        return rest_profile_review_field_verification(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)", path)
    if match and method == "GET":
        return rest_profile_get_field_verification(gateway, environ, match.group(1))
    if path == "/v1/profile-verifications/expire-due" and method == "POST":
        return rest_profile_expire_due_field_verifications(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/profile-review/risk-cases/evaluate" and method == "POST":
        return rest_profile_evaluate_review(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/profile-review/risk-cases" and method == "GET":
        return rest_profile_list_review_cases(gateway, environ)
    if path == "/v1/profile-review/photo-risk/runs" and method == "GET":
        return rest_profile_list_photo_risk_runs(gateway, environ)
    if path == "/v1/profile-review/photo-risk/review-queue" and method == "GET":
        return rest_profile_list_photo_risk_review_queue(gateway, environ)
    if path == "/v1/profile-review/appeals" and method == "GET":
        return rest_profile_list_review_case_appeals(gateway, environ)
    match = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)/review", path)
    if match and method == "POST":
        return rest_profile_review_case(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)/appeals", path)
    if match and method == "POST":
        return rest_profile_submit_review_case_appeal(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-review/appeals/([^/]+)/review", path)
    if match and method == "POST":
        return rest_profile_review_review_case_appeal(
            gateway,
            environ,
            int(match.group(1)),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/profile-review/appeals/([^/]+)", path)
    if match and method == "GET":
        return rest_profile_get_review_case_appeal(gateway, environ, int(match.group(1)))
    match = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)", path)
    if match and method == "GET":
        return rest_profile_get_review_case(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/profile-review/photo-risk/runs/([^/]+)", path)
    if match and method == "GET":
        return rest_profile_get_photo_risk_run(gateway, environ, int(match.group(1)))
    # 新增：获取 profile 基本信息（用于审核详情面板）
    match = re.fullmatch(r"/v1/profiles/([^/]+)/basic-info", path)
    if match and method == "GET":
        return rest_profile_get_basic_info(gateway, environ, match.group(1))
    return None
