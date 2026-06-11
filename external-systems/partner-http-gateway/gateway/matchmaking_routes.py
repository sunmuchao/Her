"""Matchmaking-specific HTTP handlers for the gateway.

SECURITY FIX: Added path parameter validation using input_validator.

Changes:
1. All path parameters {member_id}, {case_id}, {pair_key} now validated
2. Validation happens before processing, preventing injection attacks
"""

from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import unquote

from matchmaking_system import (  # type: ignore[import-untyped]
    create_pool_member,
    dispatch_case_contact,
    get_pair,
    get_pool_member,
    list_match_cases,
    list_pairs,
    record_case_reply,
    record_feedback,
    refresh_pool_member,
    set_pool_member_status,
)
from matchmaking_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_BUILD_MUTUAL_PAIRS,
    JOB_CLOSE_STALE_CASES,
    JOB_OPEN_MATCH_CASES,
    JOB_REFRESH_ACTIVE_POOL,
    enqueue_matchmaking_async_job,
    get_matchmaking_async_job,
    list_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs,
)

from match_domain import get_trace_id

from .http_helpers import (
    _json_safe,
    _normalize_optional_now_text,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _statuses_from_query,
)
from .identity import GatewayPermissionError
from .input_validator import validate_id, ValidationError
from .role_sets import INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES


class MatchmakingGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _enqueue_async_job(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Any,
        enqueue_fn: Any,
        job_type: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]: ...

    def _get_async_job(
        self,
        *,
        target: str,
        with_fn: Any,
        get_fn: Any,
        job_id: str,
    ) -> tuple[int, dict[str, Any]]: ...

    def _get_matchmaking_case_for_actor(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]: ...

    def _get_matchmaking_member_for_actor(
        self,
        environ: dict[str, Any],
        member_id: str,
    ) -> dict[str, Any]: ...

    def _list_async_jobs(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Any,
        list_fn: Any,
        summary_fn: Any,
    ) -> tuple[int, dict[str, Any]]: ...

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

    def _with_mm(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _enqueue_matchmaking_job(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
    *,
    job_type: str,
    message: str,
    extra_int_fields: tuple[str, ...] = (),
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(environ, INTERNAL_WRITE_ROLES, message=message)
    payload: dict[str, Any] = {}
    now_text = _normalize_optional_now_text(body.get("now"))
    if now_text is not None:
        payload["now"] = now_text
    for field_name in extra_int_fields:
        raw_value = body.get(field_name)
        if raw_value is not None:
            payload[field_name] = int(raw_value)
    return gateway._enqueue_async_job(
        environ,
        target="matchmaking",
        with_fn=gateway._with_mm,
        enqueue_fn=enqueue_matchmaking_async_job,
        job_type=job_type,
        payload=payload,
    )


def rest_mm_create_member(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    if "user_key" in kwargs or gateway._current_actor(environ) is not None:
        kwargs["user_key"] = gateway._resolve_actor_bound_id(
            environ,
            kwargs.get("user_key"),
            field_name="user_key",
        )
    if now is not None:
        kwargs["now"] = now
    member = gateway._with_mm(create_pool_member, **kwargs)
    return 201, {"member": _json_safe(member)}


def rest_mm_get_member(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    member_id: str,
) -> tuple[int, dict[str, Any]]:
    member = gateway._get_matchmaking_member_for_actor(environ, member_id)
    return 200, {"member": _json_safe(member)}


def rest_mm_set_status(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    member_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._get_matchmaking_member_for_actor(environ, member_id)
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    if now is not None:
        kwargs["now"] = now
    member = gateway._with_mm(set_pool_member_status, member_id, **kwargs)
    return 200, {"member": _json_safe(member)}


def rest_mm_refresh_member(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    member_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._get_matchmaking_member_for_actor(environ, member_id)
    out = gateway._with_mm(refresh_pool_member, member_id, now=_parse_optional_now(body))
    return 200, _json_safe(out)


def rest_mm_refresh_pool(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot refresh the matchmaking pool",
    )
    ids = body.get("member_ids")
    if ids is not None and not isinstance(ids, list):
        raise ValueError("member_ids must be a list")
    payload: dict[str, Any] = {}
    if ids is not None:
        payload["member_ids"] = [str(item) for item in ids]
    now_text = _normalize_optional_now_text(body.get("now"))
    if now_text is not None:
        payload["now"] = now_text
    return gateway._enqueue_async_job(
        environ,
        target="matchmaking",
        with_fn=gateway._with_mm,
        enqueue_fn=enqueue_matchmaking_async_job,
        job_type=JOB_REFRESH_ACTIVE_POOL,
        payload=payload,
    )


def rest_mm_build_pairs(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _enqueue_matchmaking_job(
        gateway,
        environ,
        body,
        job_type=JOB_BUILD_MUTUAL_PAIRS,
        message="current actor cannot build matchmaking pairs",
    )


def rest_mm_open_cases(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _enqueue_matchmaking_job(
        gateway,
        environ,
        body,
        job_type=JOB_OPEN_MATCH_CASES,
        message="current actor cannot open matchmaking cases",
        extra_int_fields=("case_expires_hours",),
    )


def rest_mm_get_case(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    case_id: str,
) -> tuple[int, dict[str, Any]]:
    case = gateway._get_matchmaking_case_for_actor(environ, case_id)
    return 200, {"case": _json_safe(case)}


def rest_mm_list_cases(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot list matchmaking cases",
    )
    cases = gateway._with_mm(list_match_cases, statuses=_statuses_from_query(_query_dict(environ)))
    return 200, {"cases": _json_safe(cases)}


def rest_mm_list_pairs(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot list matchmaking pairs",
    )
    pairs = gateway._with_mm(list_pairs, statuses=_statuses_from_query(_query_dict(environ)))
    return 200, {"pairs": _json_safe(pairs)}


def rest_mm_get_pair(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    pair_key: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect matchmaking pairs",
    )
    pair = gateway._with_mm(get_pair, unquote(pair_key))
    if not pair:
        return 404, {"error": {"code": "not_found", "message": "pair not found"}}
    return 200, {"pair": _json_safe(pair)}


def rest_mm_dispatch(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot dispatch matchmaking contacts",
    )
    case = gateway._with_mm(dispatch_case_contact, case_id, now=_parse_optional_now(body))
    return 200, {"case": _json_safe(case)}


def rest_mm_reply(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    case = gateway._get_matchmaking_case_for_actor(environ, case_id)
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    actor = gateway._current_actor(environ)
    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
        allowed_member_ids: list[str] = []
        for field_name in ("first_contact_member_id", "second_contact_member_id"):
            member_id = str(case.get(field_name) or "").strip()
            if not member_id:
                continue
            member = gateway._with_mm(get_pool_member, member_id)
            if str(member.get("user_key") or "").strip() == actor.actor_id:
                allowed_member_ids.append(member_id)
        supplied_member_id = str(kwargs.get("member_id") or "").strip()
        if supplied_member_id and supplied_member_id not in allowed_member_ids:
            raise GatewayPermissionError("member_id does not belong to current actor")
        if not supplied_member_id:
            if len(allowed_member_ids) != 1:
                raise GatewayPermissionError("member_id is required for this actor")
            kwargs["member_id"] = allowed_member_ids[0]
    if now is not None:
        kwargs["now"] = now
    case = gateway._with_mm(record_case_reply, case_id, **kwargs)
    return 200, {"case": _json_safe(case)}


def rest_mm_feedback(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    if "member_id" in kwargs or gateway._current_actor(environ) is not None:
        member = gateway._get_matchmaking_member_for_actor(
            environ,
            str(kwargs.get("member_id") or ""),
        )
        kwargs["member_id"] = member["member_id"]
    if now is not None:
        kwargs["now"] = now
    fb = gateway._with_mm(record_feedback, **kwargs)
    return 200, {"feedback": _json_safe(fb)}


def rest_mm_close_stale(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _enqueue_matchmaking_job(
        gateway,
        environ,
        body,
        job_type=JOB_CLOSE_STALE_CASES,
        message="current actor cannot close stale matchmaking cases",
        extra_int_fields=("timeout_cooling_days",),
    )


def rest_get_matchmaking_job(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    job_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect matchmaking jobs",
    )
    return gateway._get_async_job(
        target="matchmaking",
        with_fn=gateway._with_mm,
        get_fn=get_matchmaking_async_job,
        job_id=job_id,
    )


def rest_list_matchmaking_jobs(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect matchmaking jobs",
    )
    return gateway._list_async_jobs(
        environ,
        target="matchmaking",
        with_fn=gateway._with_mm,
        list_fn=list_matchmaking_async_jobs,
        summary_fn=summarize_matchmaking_async_jobs,
    )


def dispatch_matchmaking_rest(
    gateway: MatchmakingGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Matchmaking REST 路由分发 - 带路径参数验证

    SECURITY: 所有路径参数 {id} 先验证格式，防止注入攻击
    """
    def _validate_path_id(raw_id: str, field_name: str) -> tuple[str | None, dict[str, Any] | None]:
        """验证路径参数 ID，返回 (safe_id, error_response)"""
        try:
            return validate_id(raw_id, field_name), None
        except ValidationError as e:
            return None, {
                "error": {"code": f"invalid_{field_name}", "message": str(e)},
                "trace_id": get_trace_id(),
            }

    if path == "/v1/matchmaking/members" and method == "POST":
        return rest_mm_create_member(gateway, environ, _parse_json_body(_read_body(environ)))

    match = re.fullmatch(r"/v1/matchmaking/members/([^/]+)/status", path)
    if match and method == "PATCH":
        safe_id, error = _validate_path_id(match.group(1), "member_id")
        if error:
            return 400, error
        return rest_mm_set_status(gateway, environ, safe_id, _parse_json_body(_read_body(environ)))

    match = re.fullmatch(r"/v1/matchmaking/members/([^/]+)/refresh", path)
    if match and method == "POST":
        safe_id, error = _validate_path_id(match.group(1), "member_id")
        if error:
            return 400, error
        return rest_mm_refresh_member(gateway, environ, safe_id, _parse_json_body(_read_body(environ)))

    match = re.fullmatch(r"/v1/matchmaking/members/([^/]+)", path)
    if match and method == "GET":
        safe_id, error = _validate_path_id(match.group(1), "member_id")
        if error:
            return 400, error
        return rest_mm_get_member(gateway, environ, safe_id)

    if path == "/v1/matchmaking/pool/refresh" and method == "POST":
        return rest_mm_refresh_pool(gateway, environ, _parse_json_body(_read_body(environ)))

    if path == "/v1/matchmaking/jobs" and method == "GET":
        return rest_list_matchmaking_jobs(gateway, environ)

    match = re.fullmatch(r"/v1/matchmaking/jobs/([^/]+)", path)
    if match and method == "GET":
        safe_id, error = _validate_path_id(match.group(1), "job_id")
        if error:
            return 400, error
        return rest_get_matchmaking_job(gateway, environ, safe_id)

    if path == "/v1/matchmaking/pairs/build" and method == "POST":
        return rest_mm_build_pairs(gateway, environ, _parse_json_body(_read_body(environ)))

    if path == "/v1/matchmaking/pairs" and method == "GET":
        return rest_mm_list_pairs(gateway, environ)

    match = re.fullmatch(r"/v1/matchmaking/pairs/(.+)", path)
    if match and method == "GET":
        # pair_key 可能包含特殊字符，使用 URL decode 后再验证
        raw_pair_key = unquote(match.group(1))
        safe_pair_key, error = _validate_path_id(raw_pair_key, "pair_key")
        if error:
            return 400, error
        return rest_mm_get_pair(gateway, environ, safe_pair_key)

    if path == "/v1/matchmaking/cases/open" and method == "POST":
        return rest_mm_open_cases(gateway, environ, _parse_json_body(_read_body(environ)))

    if path == "/v1/matchmaking/cases/close-stale" and method == "POST":
        return rest_mm_close_stale(gateway, environ, _parse_json_body(_read_body(environ)))

    if path == "/v1/matchmaking/cases" and method == "GET":
        return rest_mm_list_cases(gateway, environ)

    match = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)/dispatch", path)
    if match and method == "POST":
        safe_id, error = _validate_path_id(match.group(1), "case_id")
        if error:
            return 400, error
        return rest_mm_dispatch(gateway, environ, safe_id, _parse_json_body(_read_body(environ)))

    match = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)/reply", path)
    if match and method == "POST":
        safe_id, error = _validate_path_id(match.group(1), "case_id")
        if error:
            return 400, error
        return rest_mm_reply(gateway, environ, safe_id, _parse_json_body(_read_body(environ)))

    match = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)", path)
    if match and method == "GET":
        safe_id, error = _validate_path_id(match.group(1), "case_id")
        if error:
            return 400, error
        return rest_mm_get_case(gateway, environ, safe_id)

    if path == "/v1/matchmaking/feedback" and method == "POST":
        return rest_mm_feedback(gateway, environ, _parse_json_body(_read_body(environ)))

    return None
