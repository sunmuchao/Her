"""Matchmaking JSON-RPC handlers for the gateway."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

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

from .http_helpers import _normalize_optional_now_text
from .identity import GatewayPermissionError
from .role_sets import INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES

JSONRPC_NOT_HANDLED = object()


class MatchmakingJsonrpcGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

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

    def _job_collection_payload(self, target: str, jobs: Any, summary: Any) -> Any: ...

    def _job_payload(self, target: str, job: Any) -> Any: ...

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
    gateway: MatchmakingJsonrpcGateway,
    environ: dict[str, Any],
    params: dict[str, Any],
    *,
    job_type: str,
    message: str,
    extra_int_fields: tuple[str, ...] = (),
) -> Any:
    gateway._require_roles(environ, INTERNAL_WRITE_ROLES, message=message)
    payload: dict[str, Any] = {}
    now_text = _normalize_optional_now_text(params.get("now"))
    if now_text is not None:
        payload["now"] = now_text
    for field_name in extra_int_fields:
        raw_value = params.get(field_name)
        if raw_value is not None:
            payload[field_name] = int(raw_value)
    if "member_ids" in params:
        member_ids = params.get("member_ids")
        if member_ids is not None and not isinstance(member_ids, list):
            raise ValueError("member_ids must be a list")
        if member_ids is not None:
            payload["member_ids"] = [str(item) for item in member_ids]
    actor = gateway._current_actor(environ)
    job = gateway._with_mm(
        enqueue_matchmaking_async_job,
        job_type=job_type,
        payload=payload,
        created_by=actor.actor_id if actor is not None else None,
        trace_id=get_trace_id(),
    )
    return gateway._job_payload("matchmaking", job)


def handle_matchmaking_jsonrpc(
    gateway: MatchmakingJsonrpcGateway,
    environ: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> Any:
    if method == "matchmaking.create_pool_member":
        payload = dict(params)
        if payload.get("user_key") is not None or gateway._current_actor(environ) is not None:
            payload["user_key"] = gateway._resolve_actor_bound_id(
                environ,
                payload.get("user_key"),
                field_name="user_key",
            )
        return gateway._with_mm(create_pool_member, **payload)
    if method == "matchmaking.get_pool_member":
        return gateway._get_matchmaking_member_for_actor(environ, params["member_id"])
    if method == "matchmaking.set_pool_member_status":
        payload = dict(params)
        member_id = payload.pop("member_id")
        gateway._get_matchmaking_member_for_actor(environ, member_id)
        return gateway._with_mm(set_pool_member_status, member_id, **payload)
    if method == "matchmaking.refresh_pool_member":
        gateway._get_matchmaking_member_for_actor(environ, params["member_id"])
        return gateway._with_mm(refresh_pool_member, params["member_id"], now=params.get("now"))
    if method == "matchmaking.refresh_active_pool":
        return _enqueue_matchmaking_job(
            gateway,
            environ,
            params,
            job_type=JOB_REFRESH_ACTIVE_POOL,
            message="current actor cannot refresh the matchmaking pool",
        )
    if method == "matchmaking.build_mutual_pairs":
        return _enqueue_matchmaking_job(
            gateway,
            environ,
            params,
            job_type=JOB_BUILD_MUTUAL_PAIRS,
            message="current actor cannot build matchmaking pairs",
        )
    if method == "matchmaking.open_match_cases":
        return _enqueue_matchmaking_job(
            gateway,
            environ,
            params,
            job_type=JOB_OPEN_MATCH_CASES,
            message="current actor cannot open matchmaking cases",
            extra_int_fields=("case_expires_hours",),
        )
    if method == "matchmaking.get_async_job":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking jobs",
        )
        job = gateway._with_mm(get_matchmaking_async_job, str(params["job_id"]))
        if not job:
            raise ValueError("job not found")
        return gateway._job_payload("matchmaking", job)
    if method == "matchmaking.list_async_jobs":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking jobs",
        )
        statuses = params.get("statuses")
        if statuses is not None and not isinstance(statuses, list):
            raise ValueError("statuses must be a list")
        limit = int(params.get("limit", 50))
        jobs = gateway._with_mm(list_matchmaking_async_jobs, statuses=statuses, limit=limit)
        summary = gateway._with_mm(summarize_matchmaking_async_jobs)
        return gateway._job_collection_payload("matchmaking", jobs, summary)
    if method == "matchmaking.get_match_case":
        return gateway._get_matchmaking_case_for_actor(environ, params["case_id"])
    if method == "matchmaking.list_match_cases":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot list matchmaking cases",
        )
        return gateway._with_mm(list_match_cases, statuses=params.get("statuses"))
    if method == "matchmaking.list_pairs":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot list matchmaking pairs",
        )
        return gateway._with_mm(list_pairs, statuses=params.get("statuses"))
    if method == "matchmaking.get_pair":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking pairs",
        )
        return gateway._with_mm(get_pair, params["pair_key"])
    if method == "matchmaking.dispatch_case_contact":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot dispatch matchmaking contacts",
        )
        return gateway._with_mm(dispatch_case_contact, params["case_id"], now=params.get("now"))
    if method == "matchmaking.record_case_reply":
        payload = dict(params)
        case_id = payload.pop("case_id")
        case = gateway._get_matchmaking_case_for_actor(environ, case_id)
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
            supplied_member_id = str(payload.get("member_id") or "").strip()
            if supplied_member_id and supplied_member_id not in allowed_member_ids:
                raise GatewayPermissionError("member_id does not belong to current actor")
            if not supplied_member_id:
                if len(allowed_member_ids) != 1:
                    raise GatewayPermissionError("member_id is required for this actor")
                payload["member_id"] = allowed_member_ids[0]
        return gateway._with_mm(record_case_reply, case_id, **payload)
    if method == "matchmaking.record_feedback":
        payload = dict(params)
        if payload.get("member_id") is not None or gateway._current_actor(environ) is not None:
            member = gateway._get_matchmaking_member_for_actor(environ, str(payload.get("member_id") or ""))
            payload["member_id"] = member["member_id"]
        return gateway._with_mm(record_feedback, **payload)
    if method == "matchmaking.close_stale_cases":
        return _enqueue_matchmaking_job(
            gateway,
            environ,
            params,
            job_type=JOB_CLOSE_STALE_CASES,
            message="current actor cannot close stale matchmaking cases",
            extra_int_fields=("timeout_cooling_days",),
        )
    return JSONRPC_NOT_HANDLED
