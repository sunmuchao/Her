"""Discovery-specific HTTP handlers for the gateway."""

from __future__ import annotations

import re
from typing import Any, Protocol

from discovery_system import DiscoveryServiceError  # type: ignore[import-untyped]
from match_domain import get_trace_id  # noqa: E402

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
        requester_id = gateway._resolve_int_actor_bound_id(
            environ,
            body.get("requester_id"),
            field_name="requester_id",
        )
        profile_id = int(body["profile_id"])
        out = gateway._discovery.create_session(
            requester_id=requester_id,
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
            field_name="requester_id",
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
            field_name="requester_id",
        )
        out = gateway._discovery.get_session_view(session_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_get_profile_detail(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    profile_id: str,
) -> tuple[int, dict[str, Any]]:
    query = _query_dict(environ)
    session_id = (query.get("session_id") or "").strip() or None
    try:
        if session_id is not None:
            owner_id = gateway._discovery.get_session_owner_id(session_id)
            gateway._assert_actor_can_access_owner(
                environ,
                owner_id,
                field_name="requester_id",
            )
        out = gateway._discovery.get_profile_detail(
            int(profile_id),
            session_id=session_id,
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
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)", path)
    if match and method == "GET":
        return rest_discovery_get_session(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/discovery/profiles/([^/]+)", path)
    if match and method == "GET":
        return rest_discovery_get_profile_detail(gateway, environ, match.group(1))
    return None
