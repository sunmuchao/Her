"""REST routes for call session management."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from chat_system import (  # type: ignore[import-untyped]
    create_call_session,
    end_call_session,
    get_call_session,
    list_call_sessions_by_case,
    update_call_status,
    CALL_STATUS_ACTIVE,
    CALL_STATUS_PENDING,
    CALL_STATUS_ENDED,
)

from .http_helpers import (
    _json_safe,
    _parse_json_body,
    _parse_optional_now,
    _payload_without_keys,
    _query_dict,
    _read_body,
)
from .role_sets import INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES


class CallGateway(Protocol):
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

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def call_require_requester(
    gateway: CallGateway,
    environ: dict[str, Any],
    q: dict[str, str],
    body: dict[str, Any] | None = None,
) -> str:
    requester_id = (q.get("requester_id") or "").strip()
    if not requester_id and body:
        requester_id = str(body.get("requester_id") or "").strip()
    return gateway._resolve_actor_bound_id(environ, requester_id, field_name="requester_id")


def rest_create_call_session(
    gateway: CallGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """POST /v2/call/sessions - Create a new call session."""
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot create call sessions",
    )

    now = _parse_optional_now(body)
    kwargs = _payload_without_keys(body, {"now"})

    for key in ("case_id", "caller_id", "callee_id", "call_type"):
        if not kwargs.get(key):
            raise ValueError(f"{key} is required")

    case_id = str(kwargs.get("case_id") or "").strip()
    caller_id = gateway._resolve_actor_bound_id(
        environ,
        kwargs.get("caller_id"),
        field_name="caller_id",
    )
    callee_id = str(kwargs.get("callee_id") or "").strip()
    call_type = str(kwargs.get("call_type") or "").strip()
    conversation_id = kwargs.get("conversation_id")

    if call_type not in ("audio", "video"):
        raise ValueError("call_type must be 'audio' or 'video'")

    session = gateway._with_chat(
        create_call_session,
        case_id=case_id,
        conversation_id=conversation_id,
        caller_id=caller_id,
        callee_id=callee_id,
        call_type=call_type,
        now=now,
    )

    return 201, {
        "call_session": _json_safe(session),
        "trace_id": get_trace_id(),
    }


def rest_get_call_session(
    gateway: CallGateway,
    environ: dict[str, Any],
    call_id: str,
) -> tuple[int, dict[str, Any]]:
    """GET /v2/call/sessions/{call_id} - Get call session status."""
    q = _query_dict(environ)
    requester_id = call_require_requester(gateway, environ, q)

    session = gateway._with_chat(get_call_session, call_id)

    if not session:
        return 404, {"error": {"code": "not_found", "message": "call session not found"}}

    # Check if requester is participant
    caller_id = str(session.get("caller_id") or "")
    callee_id = str(session.get("callee_id") or "")
    if requester_id not in (caller_id, callee_id):
        return 403, {
            "error": {"code": "forbidden", "message": "requester is not a participant of this call"}
        }

    return 200, {"call_session": _json_safe(session), "trace_id": get_trace_id()}


def rest_update_call_status(
    gateway: CallGateway,
    environ: dict[str, Any],
    call_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """POST /v2/call/sessions/{call_id}/status - Update call status."""
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot update call status",
    )

    now = _parse_optional_now(body)
    status = str(body.get("status") or "").strip()
    started_at = body.get("started_at")

    if status not in (CALL_STATUS_PENDING, CALL_STATUS_ACTIVE, CALL_STATUS_ENDED):
        raise ValueError(f"invalid status: {status}")

    session = gateway._with_chat(
        update_call_status,
        call_id,
        status,
        started_at=started_at,
        now=now,
    )

    return 200, {"call_session": _json_safe(session), "trace_id": get_trace_id()}


def rest_end_call_session(
    gateway: CallGateway,
    environ: dict[str, Any],
    call_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """POST /v2/call/sessions/{call_id}/end - End a call session."""
    q = _query_dict(environ)
    requester_id = call_require_requester(gateway, environ, q, body)

    # First verify the call exists and requester is participant
    session = gateway._with_chat(get_call_session, call_id)

    if not session:
        return 404, {"error": {"code": "not_found", "message": "call session not found"}}

    caller_id = str(session.get("caller_id") or "")
    callee_id = str(session.get("callee_id") or "")
    if requester_id not in (caller_id, callee_id):
        return 403, {
            "error": {"code": "forbidden", "message": "requester is not a participant of this call"}
        }

    now = _parse_optional_now(body)
    end_reason = body.get("end_reason")

    ended_session = gateway._with_chat(
        end_call_session,
        call_id,
        end_reason=end_reason,
        now=now,
    )

    return 200, {"call_session": _json_safe(ended_session), "trace_id": get_trace_id()}


def rest_list_call_sessions_by_case(
    gateway: CallGateway,
    environ: dict[str, Any],
    case_id: str,
) -> tuple[int, dict[str, Any]]:
    """GET /v2/call/sessions?case_id={case_id} - List call sessions for a case."""
    q = _query_dict(environ)
    requester_id = call_require_requester(gateway, environ, q)

    limit = int(q.get("limit") or "50")

    sessions = gateway._with_chat(
        list_call_sessions_by_case,
        case_id,
        limit=limit,
    )

    return 200, {
        "case_id": case_id,
        "requester_id": requester_id,
        "call_count": len(sessions),
        "call_sessions": _json_safe(sessions),
        "trace_id": get_trace_id(),
    }


def dispatch_call_rest(
    gateway: CallGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Dispatch call-related REST endpoints."""

    # POST /v2/call/sessions - Create call session
    if path == "/v2/call/sessions" and method == "POST":
        return rest_create_call_session(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )

    # GET /v2/call/sessions/{call_id} - Get call session
    match = re.fullmatch(r"/v2/call/sessions/([^/]+)", path)
    if match and method == "GET":
        return rest_get_call_session(gateway, environ, match.group(1))

    # POST /v2/call/sessions/{call_id}/status - Update call status
    match = re.fullmatch(r"/v2/call/sessions/([^/]+)/status", path)
    if match and method == "POST":
        return rest_update_call_status(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )

    # POST /v2/call/sessions/{call_id}/end - End call session
    match = re.fullmatch(r"/v2/call/sessions/([^/]+)/end", path)
    if match and method == "POST":
        return rest_end_call_session(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )

    # GET /v2/call/cases/{case_id}/sessions - List calls by case
    match = re.fullmatch(r"/v2/call/cases/([^/]+)/sessions", path)
    if match and method == "GET":
        return rest_list_call_sessions_by_case(gateway, environ, match.group(1))

    return None


__all__ = ["dispatch_call_rest"]