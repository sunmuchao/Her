"""Recommendation JSON-RPC handlers for the gateway."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    create_subscription,
    get_subscription,
    list_in_app_cards,
    list_recommendations_for_subscription,
    list_search_runs_for_subscription,
    mark_in_app_cards_read,
    record_recommendation_action,
    record_user_review,
    refresh_subscription,
    update_subscription_overrides,
)
from recommendation_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_DELIVER_IN_APP_RECOMMENDATIONS,
    JOB_REFRESH_DUE_SUBSCRIPTIONS,
    enqueue_recommendation_async_job,
    get_recommendation_async_job,
    list_recommendation_async_jobs,
    summarize_recommendation_async_jobs,
)

from .http_helpers import _normalize_optional_now_text
from .role_sets import INTERNAL_WRITE_ROLES

JSONRPC_NOT_HANDLED = object()


class RecommendationJsonrpcGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
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

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _resolve_optional_requester_id(
    gateway: RecommendationJsonrpcGateway,
    environ: dict[str, Any],
    raw_requester_id: Any,
) -> int | None:
    if raw_requester_id is not None or gateway._current_actor(environ) is not None:
        return gateway._resolve_int_actor_bound_id(
            environ,
            raw_requester_id,
            field_name="requester_id",
        )
    return None


def _recommendation_job_payload(params: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    now_text = _normalize_optional_now_text(params.get("now"))
    if now_text is not None:
        payload["now"] = now_text
    return payload


def _mutation_payload(
    gateway: RecommendationJsonrpcGateway,
    environ: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in params.items()
        if key not in {"idempotency_key", "client_idempotency_key"}
    }
    subscription = gateway._get_recommendation_subscription_for_actor(
        environ,
        str(payload.get("subscription_id") or ""),
    )
    client_key = params.get("client_idempotency_key") or params.get("idempotency_key")
    if client_key is not None and str(client_key).strip():
        payload["client_idempotency_key"] = str(client_key).strip()[:191]
    payload["subscription_id"] = subscription["subscription_id"]
    actor = gateway._current_actor(environ)
    if actor is not None:
        payload["actor_id"] = actor.actor_id
    return payload


def handle_recommendation_jsonrpc(
    gateway: RecommendationJsonrpcGateway,
    environ: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> Any:
    if method == "recommendation.get_subscription":
        gateway._get_recommendation_subscription_for_actor(environ, params["subscription_id"])
        return gateway._with_rec(get_subscription, params["subscription_id"])
    if method == "recommendation.create_subscription":
        payload = dict(params)
        requester_id = _resolve_optional_requester_id(gateway, environ, payload.get("requester_id"))
        if requester_id is not None:
            payload["requester_id"] = requester_id
        return gateway._with_rec(create_subscription, **payload)
    if method == "recommendation.update_subscription_overrides":
        gateway._get_recommendation_subscription_for_actor(environ, params["subscription_id"])
        return gateway._with_rec(
            update_subscription_overrides,
            params["subscription_id"],
            params.get("overrides"),
            now=params.get("now"),
        )
    if method == "recommendation.refresh_subscription":
        gateway._get_recommendation_subscription_for_actor(environ, params["subscription_id"])
        return gateway._with_rec(refresh_subscription, params["subscription_id"], now=params.get("now"))
    if method == "recommendation.refresh_due_subscriptions":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot refresh due recommendation subscriptions",
        )
        ids = params.get("subscription_ids")
        if ids is not None and not isinstance(ids, list):
            raise ValueError("subscription_ids must be a list")
        payload = _recommendation_job_payload(params)
        if ids is not None:
            payload["subscription_ids"] = [str(item) for item in ids]
        actor = gateway._current_actor(environ)
        job = gateway._with_rec(
            enqueue_recommendation_async_job,
            job_type=JOB_REFRESH_DUE_SUBSCRIPTIONS,
            payload=payload,
            created_by=actor.actor_id if actor is not None else None,
            trace_id=get_trace_id(),
        )
        return gateway._job_payload("recommendation", job)
    if method == "recommendation.get_async_job":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect recommendation jobs",
        )
        job = gateway._with_rec(get_recommendation_async_job, str(params["job_id"]))
        if not job:
            raise ValueError("job not found")
        return gateway._job_payload("recommendation", job)
    if method == "recommendation.list_async_jobs":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect recommendation jobs",
        )
        statuses = params.get("statuses")
        if statuses is not None and not isinstance(statuses, list):
            raise ValueError("statuses must be a list")
        limit = int(params.get("limit", 50))
        jobs = gateway._with_rec(list_recommendation_async_jobs, statuses=statuses, limit=limit)
        summary = gateway._with_rec(summarize_recommendation_async_jobs)
        return gateway._job_collection_payload("recommendation", jobs, summary)
    if method == "recommendation.list_recommendations_for_subscription":
        gateway._get_recommendation_subscription_for_actor(environ, params["subscription_id"])
        return gateway._with_rec(list_recommendations_for_subscription, params["subscription_id"])
    if method == "recommendation.list_search_runs_for_subscription":
        gateway._get_recommendation_subscription_for_actor(environ, params["subscription_id"])
        return gateway._with_rec(list_search_runs_for_subscription, params["subscription_id"])
    if method == "recommendation.list_in_app_cards":
        return gateway._with_rec(
            list_in_app_cards,
            requester_id=_resolve_optional_requester_id(gateway, environ, params.get("requester_id")),
            unread_only=bool(params.get("unread_only", False)),
        )
    if method == "recommendation.deliver_in_app_recommendations":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot deliver recommendation cards",
        )
        payload = _recommendation_job_payload(params)
        actor = gateway._current_actor(environ)
        job = gateway._with_rec(
            enqueue_recommendation_async_job,
            job_type=JOB_DELIVER_IN_APP_RECOMMENDATIONS,
            payload=payload,
            created_by=actor.actor_id if actor is not None else None,
            trace_id=get_trace_id(),
        )
        return gateway._job_payload("recommendation", job)
    if method == "recommendation.record_recommendation_action":
        return gateway._with_rec(
            record_recommendation_action,
            **_mutation_payload(gateway, environ, params),
        )
    if method == "recommendation.record_user_review":
        return gateway._with_rec(
            record_user_review,
            **_mutation_payload(gateway, environ, params),
        )
    if method == "recommendation.mark_in_app_cards_read":
        requester_id = gateway._resolve_int_actor_bound_id(
            environ,
            params.get("requester_id"),
            field_name="requester_id",
        )
        card_ids = params.get("card_ids")
        if not isinstance(card_ids, list):
            raise ValueError("card_ids must be a list")
        return gateway._with_rec(
            mark_in_app_cards_read,
            requester_id=requester_id,
            card_ids=[str(item) for item in card_ids],
            now=params.get("now"),
        )
    return JSONRPC_NOT_HANDLED
