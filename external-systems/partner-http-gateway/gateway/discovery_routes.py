"""Discovery-specific HTTP handlers for the gateway."""

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
    if path == "/v1/discovery/sessions" and method == "POST":
        return rest_discovery_create_session(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/turns", path)
    if match and method == "POST":
        return rest_discovery_process_turn(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/express-interest", path)
    if match and method == "POST":
        return rest_discovery_express_interest(
            gateway,
            environ,
            match.group(1),
            int(match.group(2)),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)", path)
    if match and method == "GET":
        return rest_discovery_get_session(gateway, environ, match.group(1))

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/confirm",
        path,
    )
    if match and method == "POST":
        return rest_discovery_confirm_profile_update(
            gateway,
            environ,
            match.group(1),
            match.group(2),
        )

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/reject",
        path,
    )
    if match and method == "POST":
        return rest_discovery_reject_profile_update(
            gateway,
            environ,
            match.group(1),
            match.group(2),
        )

    # 新增：反馈收集路由
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback", path)
    if match and method == "POST":
        return rest_discovery_submit_feedback(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/skip", path)
    if match and method == "POST":
        return rest_discovery_skip_feedback(
            gateway,
            environ,
            match.group(1),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/options", path)
    if match and method == "GET":
        return rest_discovery_get_feedback_options(
            gateway,
            environ,
            match.group(1),
        )

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
