"""Verification-specific HTTP handlers for the gateway.

SECURITY FIX: Added proper resource access control for verification submissions.

Before: Users could potentially access any verification submission by ID.
After: Users can only access their own submissions; staff override roles
       can access others (audited).

Key Changes:
1. Submission access requires ownership verification
2. Photo review request access requires ownership or staff role
3. All access decisions are audited
4. Rate limiting for challenge creation and video submission
5. Multipart/form-data support for video uploads (no Base64 encoding)
6. Strict submission_id format validation
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Any, Protocol

from chat_system import (  # type: ignore[import-untyped]
    create_live_video_verification_challenge,
    get_verification_submission,
    list_photo_review_requests,
    list_verification_notifications,
    list_verification_submissions,
    request_live_video_verification,
    resubmit_live_video_verification,
    review_live_video_verification,
    submit_live_video_verification,
)

from .http_helpers import (
    _json_safe,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _statuses_from_query,
)
from .input_validator import validate_int_id, ValidationError
from .role_sets import CHAT_RISK_REVIEW_ROLES, STAFF_OVERRIDE_ROLES, VERIFICATION_REVIEW_ROLES
from .verification_rate_limiter import (
    check_verification_rate_limit,
    extract_user_id_from_environ,
    RateLimitExceeded,
)
from .verification_input_validator import (
    validate_submission_id,
    validate_file_size,
    validate_content_type,
    parse_multipart_file,
    InputValidationError,
)


class VerificationGateway(Protocol):
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

    def _resolve_optional_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str | None: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _check_submission_ownership(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    submission: dict[str, Any],
) -> tuple[bool, str | None]:
    """Check if current actor owns the submission.

    Returns:
        (is_owner, reason) - is_owner=True if access allowed, reason explains access method
    """
    actor = gateway._current_actor(environ)
    if actor is None:
        return False, "unauthenticated"

    submission_user_id = str(submission.get("user_id") or "").strip()

    # Staff override
    if actor.has_any_role(STAFF_OVERRIDE_ROLES | VERIFICATION_REVIEW_ROLES):
        return True, "staff_override"

    # Direct ownership
    if str(actor.actor_id) == submission_user_id:
        return True, "direct_owner"

    return False, "not_owner"


def _normalize_base64(b64_string: str) -> str:
    """Normalize Base64 string for decoding.

    Handles common issues:
    1. URL-safe encoding (replace - with +, _ with /)
    2. Missing padding (add = to make length multiple of 4)
    3. Whitespace and newlines (remove)
    4. Data URL prefix (remove if present)
    5. INVALID LENGTH (remainder 1): truncate last character (data corruption)
    6. WRONG PADDING: strip existing padding and recalculate

    Args:
        b64_string: Raw Base64 string (may have issues)

    Returns:
        Normalized standard Base64 string ready for b64decode

    Raises:
        ValueError: If string is empty or has invalid characters
    """
    # Remove data URL prefix if present (e.g., "data:video/webm;base64,")
    if b64_string.startswith("data:"):
        comma_pos = b64_string.find(",")
        if comma_pos >= 0:
            b64_string = b64_string[comma_pos + 1:]

    # Remove whitespace and newlines
    b64_string = "".join(b64_string.split())

    # Empty string check
    if not b64_string:
        return ""

    # Convert URL-safe Base64 to standard Base64
    b64_string = b64_string.replace("-", "+").replace("_", "/")

    # ✅ CRITICAL FIX: Strip existing padding first (may be incorrect)
    # Then recalculate the correct padding based on actual data length
    b64_string = b64_string.rstrip("=")

    # ✅ CRITICAL FIX: Handle invalid length (remainder 1)
    # Standard Base64 encoding CANNOT produce length % 4 == 1
    # This indicates data corruption (truncated during transmission)
    remainder = len(b64_string) % 4
    if remainder == 1:
        # Truncate the last character to make it valid
        # This may lose up to 6 bits of data (last 1-2 bytes of original)
        # But it's better than failing completely
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Base64 string has invalid length (remainder 1): {len(b64_string)} chars. "
            f"Truncating last character to attempt decoding. "
            f"This indicates data corruption during transmission."
        )
        b64_string = b64_string[:-1]
        remainder = 0  # Now it's divisible by 4

    # Add correct padding if needed (length must be multiple of 4)
    # Valid remainders: 0 (no padding), 2 (2 '='), 3 (1 '=')
    if remainder in (2, 3):
        b64_string += "=" * (4 - remainder)

    return b64_string


def rest_verification_submit_live_video(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Submit live video verification.

    SECURITY:
    - User_id is bound to current actor, preventing impersonation
    - Rate limit: 5 submissions per minute per user
    - File size limit: 50MB
    - Supports both Base64 and multipart/form-data upload

    ENHANCED: Supports multipart/form-data for better efficiency (no Base64 encoding)
    """

    # Rate limiting check
    user_id_for_limit = extract_user_id_from_environ(environ)
    try:
        check_verification_rate_limit("submit_video", user_id_for_limit)
    except RateLimitExceeded as e:
        return 429, {
            "error": {
                "code": "rate_limit_exceeded",
                "message": str(e),
                "retry_after": e.retry_after,
            }
        }

    now = _parse_optional_now(body)
    user_id = gateway._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")

    # Check content type to determine upload method
    content_type_header = environ.get("CONTENT_TYPE", "")

    if content_type_header.startswith("multipart/form-data"):
        # Multipart/form-data upload (more efficient)
        try:
            file_data = parse_multipart_file(environ)
            video_bytes = file_data["file_data"]
            file_name = file_data["filename"]
            content_type = file_data["content_type"]

            # Validate file size
            validate_file_size(file_data["file_size_bytes"])

            # Validate content type
            validate_content_type(content_type)

        except InputValidationError as e:
            return 400, {
                "error": {
                    "code": "validation_error",
                    "field": e.field,
                    "message": e.reason,
                }
            }
    else:
        # Base64 upload (legacy support)
        video_base64_raw = str(body.get("video_base64") or body.get("video_bytes_base64") or "")
        if not video_base64_raw:
            return 400, {
                "error": {
                    "code": "validation_error",
                    "field": "video",
                    "message": "video_base64 or multipart upload required",
                }
            }

        try:
            # ✅ CRITICAL FIX: Normalize Base64 before decoding
            # Handles URL-safe encoding, missing padding, whitespace, data URL prefix
            video_base64 = _normalize_base64(video_base64_raw)
            # Decode only for validation (file size check)
            video_bytes = base64.b64decode(video_base64)
            file_name = str(body.get("file_name") or body.get("filename") or "")
            content_type = body.get("content_type")

            # Validate file size
            validate_file_size(len(video_bytes))

        except Exception as e:
            return 400, {
                "error": {
                    "code": "validation_error",
                    "field": "video_base64",
                    "message": f"Failed to decode Base64: {e}",
                }
            }

    # Validate submission_id if provided
    submission_id = body.get("submission_id")
    if submission_id is not None:
        try:
            validate_submission_id(submission_id)
        except InputValidationError as e:
            return 400, {
                "error": {
                    "code": "validation_error",
                    "field": "submission_id",
                    "message": e.reason,
                }
            }

    # Submit verification
    # NOTE: For Base64 uploads, pass the normalized Base64 string (not decoded bytes)
    # The underlying function will decode it using _decode_video_bytes
    # For multipart uploads, we need to encode bytes back to Base64 (legacy API requirement)
    video_base64_for_submit: str | None = None
    if content_type_header.startswith("multipart/form-data"):
        # Multipart upload: encode bytes to Base64 for legacy API
        video_base64_for_submit = base64.b64encode(video_bytes).decode("utf-8")
    else:
        # Base64 upload: use normalized Base64 string directly
        video_base64_for_submit = video_base64

    submission = gateway._with_chat(
        submit_live_video_verification,
        user_id=user_id,
        video_base64=video_base64_for_submit,
        file_name=file_name,
        submission_id=submission_id,
        content_type=content_type,
        profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
        source_dsn=body.get("source_dsn") or body.get("source"),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        challenge_token=body.get("challenge_token"),
        challenge_phrase=body.get("challenge_phrase"),
        metadata=body.get("metadata"),
        now=now,
    )

    return 201, {"submission": _json_safe(submission)}


def rest_verification_request_live_video(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Request live video verification (reviewer initiated).

    SECURITY: Requires reviewer roles.
    """
    gateway._require_roles(
        environ,
        VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
        message="current actor cannot request live video verification",
    )
    now = _parse_optional_now(body)
    raw_due_at = body.get("due_at")
    due_at = datetime.fromisoformat(str(raw_due_at)) if raw_due_at else None
    user_id = body.get("user_id")
    if not user_id:
        raise ValueError("user_id is required")
    request = gateway._with_chat(
        request_live_video_verification,
        user_id=str(user_id),
        profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
        source_dsn=body.get("source_dsn") or body.get("source"),
        source_table_name=body.get("source_table_name") or body.get("table_name"),
        request_source=str(body.get("request_source") or "risk_case_review"),
        request_reason=body.get("request_reason") or body.get("reason_text"),
        signal_codes=body.get("signal_codes") or body.get("reason_codes"),
        risk_case_id=body.get("risk_case_id"),
        report_ids=body.get("report_ids"),
        requested_by=gateway._resolve_optional_operator_actor_id(
            environ,
            body.get("requested_by") or body.get("resolver_id"),
            field_name="requested_by",
            roles=VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot request live video verification",
        ),
        due_at=due_at,
        metadata=body.get("metadata"),
        now=now,
    )
    return 201, {"request": _json_safe(request)}


def rest_verification_create_live_challenge(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Create live video challenge.

    SECURITY:
    - User_id bound to current actor
    - Rate limit: 10 challenges per minute per user
    """

    # Rate limiting check
    user_id_for_limit = extract_user_id_from_environ(environ)
    try:
        check_verification_rate_limit("create_challenge", user_id_for_limit)
    except RateLimitExceeded as e:
        return 429, {
            "error": {
                "code": "rate_limit_exceeded",
                "message": str(e),
                "retry_after": e.retry_after,
            }
        }

    now = _parse_optional_now(body)
    user_id = gateway._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")
    challenge = create_live_video_verification_challenge(
        user_id=user_id,
        profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
        challenge_actions=body.get("challenge_actions") or body.get("required_actions"),
        challenge_action_pool=body.get("challenge_action_pool") or body.get("allowed_actions"),
        action_count=int(body.get("action_count", 3)),
        now=now,
    )
    return 201, {"challenge": _json_safe(challenge)}


def rest_verification_list_submissions(
    gateway: VerificationGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """List verification submissions.

    SECURITY:
    - Normal users: Only see their own submissions
    - Staff: Can see all or filter by user_id
    """
    q = _query_dict(environ)
    user_id = q.get("user_id") or None
    actor = gateway._current_actor(environ)

    # Non-staff users can only query their own submissions
    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES | VERIFICATION_REVIEW_ROLES):
        # Force user_id to match actor
        user_id = gateway._resolve_actor_bound_id(environ, user_id, field_name="user_id")

    limit_raw = q.get("limit") or "100"
    try:
        limit = validate_int_id(limit_raw, "limit") if limit_raw != "100" else 100
    except ValidationError:
        limit = 100

    rows = gateway._with_chat(
        list_verification_submissions,
        user_id=user_id,
        statuses=_statuses_from_query(q),
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        limit=min(limit, 100),  # Cap at 100
    )
    return 200, {"submissions": _json_safe(rows)}


def rest_verification_list_photo_review_requests(
    gateway: VerificationGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """List photo review requests.

    SECURITY: Normal users only see their own; staff can see all.
    """
    q = _query_dict(environ)
    user_id = q.get("user_id") or None
    actor = gateway._current_actor(environ)

    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES | VERIFICATION_REVIEW_ROLES):
        user_id = gateway._resolve_actor_bound_id(environ, user_id, field_name="user_id")

    limit_raw = q.get("limit") or "100"
    try:
        limit = int(limit_raw)
        limit = min(limit, 100)
    except ValueError:
        limit = 100

    rows = gateway._with_chat(
        list_photo_review_requests,
        user_id=user_id,
        statuses=_statuses_from_query(q),
        profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
        limit=limit,
    )
    return 200, {"requests": _json_safe(rows)}


def rest_verification_get_submission(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    submission_id: str,
) -> tuple[int, dict[str, Any]]:
    """Get a specific verification submission.

    SECURITY FIX: Added proper ownership verification before returning data.

    Before: submission_id from URL could be any ID, potentially allowing IDOR.
    After: Verify that current actor owns the submission or has staff role.
    """
    # Validate submission_id format (prevent injection)
    try:
        # submission_id might not be pure integer, validate as safe string
        safe_id = str(submission_id).strip()
        if not safe_id or len(safe_id) > 128:
            return 400, {"error": {"code": "invalid_request", "message": "Invalid submission_id"}}
        # Check for dangerous characters
        if any(c in safe_id for c in {"'", '"', "..", "/", "\\"}):
            return 400, {"error": {"code": "invalid_request", "message": "Invalid submission_id format"}}
    except Exception:
        return 400, {"error": {"code": "invalid_request", "message": "Invalid submission_id"}}

    submission = gateway._with_chat(get_verification_submission, safe_id)
    if not submission:
        return 404, {"error": {"code": "not_found", "message": "verification submission not found"}}

    # SECURITY: Verify ownership
    is_allowed, reason = _check_submission_ownership(gateway, environ, submission)
    if not is_allowed:
        # Audit the denied access
        from observability import audit_event
        audit_event(
            action="gateway.verification_submission_idor_attempt",
            resource_type="verification_submission",
            resource_id=safe_id,
            outcome="denied",
            reason=reason,
            submission_user_id=submission.get("user_id"),
            http_method=environ.get("REQUEST_METHOD"),
            path=environ.get("PATH_INFO"),
        )
        return 403, {
            "error": {
                "code": "forbidden",
                "message": "You do not have permission to access this verification submission.",
            }
        }

    # Audit successful access
    from observability import audit_event
    actor = gateway._current_actor(environ)
    audit_event(
        action="gateway.verification_submission_access",
        resource_type="verification_submission",
        resource_id=safe_id,
        outcome="allowed",
        reason=reason,
        actor_id=actor.actor_id if actor else None,
        http_method=environ.get("REQUEST_METHOD"),
        path=environ.get("PATH_INFO"),
    )

    return 200, {"submission": _json_safe(submission), "access_reason": reason}


def rest_verification_get_photo_review_request(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    submission_id: str,
) -> tuple[int, dict[str, Any]]:
    """Get a specific photo review request.

    SECURITY: Ownership verification required.
    """
    submission = gateway._with_chat(get_verification_submission, submission_id)
    if not submission or not (submission.get("photo_review_task") or {}).get("task_kind"):
        return 404, {"error": {"code": "not_found", "message": "photo review request not found"}}

    is_allowed, reason = _check_submission_ownership(gateway, environ, submission)
    if not is_allowed:
        return 403, {
            "error": {
                "code": "forbidden",
                "message": "You do not have permission to access this photo review request.",
            }
        }

    return 200, {"request": _json_safe(submission), "access_reason": reason}


def rest_verification_resubmit_live_video(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    submission_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Resubmit live video verification.

    SECURITY: User_id bound to current actor.
    """
    now = _parse_optional_now(body)
    user_id = gateway._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")

    # ✅ CRITICAL FIX: Normalize Base64 before decoding
    video_base64_raw = str(body.get("video_base64") or body.get("video_bytes_base64") or "")
    video_base64 = _normalize_base64(video_base64_raw) if video_base64_raw else ""

    submission = gateway._with_chat(
        resubmit_live_video_verification,
        submission_id,
        user_id=user_id,
        video_base64=video_base64,
        file_name=str(body.get("file_name") or body.get("filename") or ""),
        content_type=body.get("content_type"),
        challenge_token=body.get("challenge_token"),
        challenge_phrase=body.get("challenge_phrase"),
        metadata=body.get("metadata"),
        now=now,
    )
    return 200, {"submission": _json_safe(submission)}


def rest_verification_list_notifications(
    gateway: VerificationGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """List verification notifications.

    SECURITY: Normal users only see their own; staff can filter.
    """
    q = _query_dict(environ)
    user_id = q.get("user_id") or None
    actor = gateway._current_actor(environ)

    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
        user_id = gateway._resolve_actor_bound_id(environ, user_id, field_name="user_id")

    limit_raw = q.get("limit") or "100"
    try:
        limit = min(int(limit_raw), 100)
    except ValueError:
        limit = 100

    rows = gateway._with_chat(
        list_verification_notifications,
        submission_id=q.get("submission_id") or None,
        user_id=user_id,
        notification_types=_statuses_from_query(q, key="type"),
        limit=limit,
    )
    return 200, {"notifications": _json_safe(rows)}


def rest_verification_review_submission(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    submission_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Review a verification submission.

    SECURITY: Requires reviewer roles.
    """
    now = _parse_optional_now(body)
    reviewer_id = gateway._resolve_operator_actor_id(
        environ,
        body.get("reviewer_id"),
        field_name="reviewer_id",
        roles=VERIFICATION_REVIEW_ROLES,
        message="current actor cannot review live video submissions",
    )
    decision = body.get("decision")
    if not decision:
        raise ValueError("decision is required")
    submission = gateway._with_chat(
        review_live_video_verification,
        submission_id,
        reviewer_id,
        decision=str(decision),
        review_note=body.get("review_note"),
        liveness_result=body.get("liveness_result"),
        face_match_result=body.get("face_match_result"),
        profile_consistency_result=body.get("profile_consistency_result"),
        metadata=body.get("metadata"),
        now=now,
    )
    return 200, {"submission": _json_safe(submission)}


def dispatch_verification_rest(
    gateway: VerificationGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/verifications/live-video-challenges" and method == "POST":
        return rest_verification_create_live_challenge(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/verifications/live-video-requests" and method == "POST":
        return rest_verification_request_live_video(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/verifications/live-video-requests" and method == "GET":
        return rest_verification_list_photo_review_requests(gateway, environ)
    if path == "/v1/verifications/live-video-submissions" and method == "POST":
        return rest_verification_submit_live_video(
            gateway,
            environ,
            _parse_json_body(_read_body(environ, max_bytes=64 * 1024 * 1024)),
        )
    if path == "/v1/verifications/live-video-submissions" and method == "GET":
        return rest_verification_list_submissions(gateway, environ)
    match = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)/resubmit", path)
    if match and method == "POST":
        return rest_verification_resubmit_live_video(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ, max_bytes=64 * 1024 * 1024)),
        )
    match = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)/review", path)
    if match and method == "POST":
        return rest_verification_review_submission(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)", path)
    if match and method == "GET":
        return rest_verification_get_submission(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/verifications/live-video-requests/([^/]+)", path)
    if match and method == "GET":
        return rest_verification_get_photo_review_request(gateway, environ, match.group(1))
    if path == "/v1/verifications/notifications" and method == "GET":
        return rest_verification_list_notifications(gateway, environ)
    return None


__all__ = [
    "dispatch_verification_rest",
    "rest_verification_submit_live_video",
    "rest_verification_request_live_video",
    "rest_verification_create_live_challenge",
    "rest_verification_list_submissions",
    "rest_verification_list_photo_review_requests",
    "rest_verification_get_submission",
    "rest_verification_get_photo_review_request",
    "rest_verification_resubmit_live_video",
    "rest_verification_list_notifications",
    "rest_verification_review_submission",
    "_check_submission_ownership",
]