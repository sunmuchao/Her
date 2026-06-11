"""Discovery-specific HTTP handlers for the gateway.

SECURITY FIX: Added path parameter validation using input_validator.

Changes:
1. All path parameters {session_id} now validated before processing
2. Validation prevents injection attacks on session IDs
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from discovery_system import DiscoveryServiceError  # type: ignore[import-untyped]
from match_domain import get_trace_id  # noqa: E402
from match_domain.principal import coalesce_profile_id_param

from .http_helpers import (  # noqa: E402
    _json_safe,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
)
from .input_validator import validate_id, ValidationError


class DiscoveryGateway(Protocol):
    _discovery: Any

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: int,
        *,
        field_name: str,
    ) -> None: ...


def _discovery_error(exc: DiscoveryServiceError) -> tuple[int, dict[str, Any]]:
    return exc.status_code, {
        "error": {"code": exc.code, "message": exc.message},
        "error_code": exc.code,
        "error_message": exc.message,
        "retryable": exc.retryable,
        "trace_id": get_trace_id(),
    }


def rest_discovery_create_session(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            coalesce_profile_id_param(body.get("profile_id"), body.get("requester_id")),
            field_name="profile_id",
        )
        out = gateway._discovery.create_session(
            requester_id=profile_id,
            profile_id=profile_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 201, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_list_sessions(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """获取用户的 Discovery 会话列表。"""
    try:
        query = _query_dict(environ)
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            coalesce_profile_id_param(query.get("profile_id"), query.get("requester_id")),
            field_name="profile_id",
        )
        limit = int(query.get("limit", "20") or "20")
        if limit < 1 or limit > 100:
            limit = 20
        out = gateway._discovery.list_sessions(
            profile_id=profile_id,
            limit=limit,
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_process_turn(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.process_turn(
            session_id=session_id,
            user_message_text=body.get("user_message"),
            action_id=body.get("action_id"),
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_get_session(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.get_session_view(session_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_express_interest(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    candidate_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.express_interest(
            session_id,
            candidate_id=candidate_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def dispatch_discovery_rest(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Discovery REST 路由分发 - 带路径参数验证

    SECURITY: 所有路径参数 {session_id} 先验证格式，防止注入攻击
    """
    def _validate_session_id(raw_id: str) -> tuple[str | None, dict[str, Any] | None]:
        """验证 session_id 格式，返回 (safe_id, error_response)"""
        try:
            return validate_id(raw_id, "session_id"), None
        except ValidationError as e:
            return None, {
                "error": {"code": "invalid_session_id", "message": str(e)},
                "trace_id": get_trace_id(),
            }

    if path == "/v1/discovery/sessions" and method == "POST":
        return rest_discovery_create_session(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )

    if path == "/v1/discovery/sessions" and method == "GET":
        return rest_discovery_list_sessions(gateway, environ)

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/turns", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_process_turn(
            gateway,
            environ,
            safe_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/express-interest", path)
    if match and method == "POST":
        safe_session_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        # candidate_id 是整数，额外验证
        try:
            candidate_id = int(match.group(2))
            if candidate_id <= 0 or candidate_id > 10**9:
                return 400, {
                    "error": {"code": "invalid_candidate_id", "message": "candidate_id must be between 1 and 10^9"},
                    "trace_id": get_trace_id(),
                }
        except ValueError:
            return 400, {
                "error": {"code": "invalid_candidate_id", "message": "candidate_id must be an integer"},
                "trace_id": get_trace_id(),
            }
        return rest_discovery_express_interest(
            gateway,
            environ,
            safe_session_id,
            candidate_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)", path)
    if match and method == "GET":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_get_session(gateway, environ, safe_id)

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/confirm",
        path,
    )
    if match and method == "POST":
        safe_session_id, error1 = _validate_session_id(match.group(1))
        if error1:
            return 400, error1
        safe_request_id, error2 = _validate_session_id(match.group(2))  # request_id 格式类似 session_id
        if error2:
            return 400, error2
        return rest_discovery_confirm_profile_update(
            gateway,
            environ,
            safe_session_id,
            safe_request_id,
        )

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/reject",
        path,
    )
    if match and method == "POST":
        safe_session_id, error1 = _validate_session_id(match.group(1))
        if error1:
            return 400, error1
        safe_request_id, error2 = _validate_session_id(match.group(2))
        if error2:
            return 400, error2
        return rest_discovery_reject_profile_update(
            gateway,
            environ,
            safe_session_id,
            safe_request_id,
        )

    # 反馈收集路由
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_submit_feedback(
            gateway,
            environ,
            safe_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/skip", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_skip_feedback(gateway, environ, safe_id)

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/options", path)
    if match and method == "GET":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_get_feedback_options(gateway, environ, safe_id)

    return None


def rest_discovery_confirm_profile_update(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    request_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.confirm_profile_update(session_id, request_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_reject_profile_update(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    request_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.reject_profile_update(session_id, request_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


# ========== 新增：反馈收集API handler ==========

def rest_discovery_submit_feedback(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """提交拒绝反馈。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.submit_rejection_feedback(
            session_id=session_id,
            feedback_text=body.get("feedback_text", ""),
            feedback_type=body.get("feedback_type"),
            feedback_detail=body.get("feedback_detail"),
            rejected_candidate_ids=body.get("rejected_candidate_ids"),
            is_secondary=body.get("is_secondary", False),
            primary_feedback_id=body.get("primary_feedback_id"),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_skip_feedback(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    """跳过反馈。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.skip_rejection_feedback(session_id=session_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_get_feedback_options(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    """获取反馈选项列表。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        # 从query参数获取secondary相关参数
        query = _query_dict(environ)
        include_secondary = query.get("include_secondary", "false").lower() == "true"
        primary_option = query.get("primary_option")

        out = gateway._discovery.get_feedback_options(
            session_id=session_id,
            include_secondary=include_secondary,
            primary_option=primary_option,
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}
