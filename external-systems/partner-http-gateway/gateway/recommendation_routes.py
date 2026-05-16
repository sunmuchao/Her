"""Recommendation-specific HTTP handlers for the gateway."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    create_subscription,
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

from .http_helpers import (
    _extract_client_idempotency_key,
    _json_safe,
    _normalize_optional_now_text,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _subscription_ids_from_query,
)
from .recommendation_access import recommendation_mutation_payload, resolve_optional_requester_id
from .role_sets import INTERNAL_WRITE_ROLES


class RecommendationGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _get_async_job(
        self,
        *,
        target: str,
        with_fn: Any,
        get_fn: Any,
        job_id: str,
    ) -> tuple[int, dict[str, Any]]: ...

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
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


def _rest_record_recommendation_mutation(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
    *,
    record_fn: Any,
) -> tuple[int, dict[str, Any]]:
    kwargs, idem = recommendation_mutation_payload(
        gateway,
        environ,
        body,
        client_idempotency_key=_extract_client_idempotency_key(environ, body),
    )
    now = _parse_optional_now(body)
    if now is not None:
        kwargs["now"] = now
    rec = gateway._with_rec(record_fn, **kwargs)
    out: dict[str, Any] = {"recommendation": _json_safe(rec)}
    if idem:
        out["client_idempotency_key"] = idem
    out["trace_id"] = get_trace_id()
    return 200, out


def rest_get_subscription(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    subscription_id: str,
) -> tuple[int, dict[str, Any]]:
    sub = gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    return 200, {"subscription": _json_safe(sub)}


def rest_create_subscription(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    requester_id = resolve_optional_requester_id(
        gateway,
        environ,
        kwargs.get("requester_id"),
        treat_empty_as_missing=True,
    )
    if requester_id is not None:
        kwargs["requester_id"] = requester_id
    if now is not None:
        kwargs["now"] = now
    sub = gateway._with_rec(create_subscription, **kwargs)
    return 201, {"subscription": _json_safe(sub)}


def rest_patch_overrides(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    subscription_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    now = _parse_optional_now(body)
    overrides = body.get("overrides")
    if overrides is None:
        overrides = {key: value for key, value in body.items() if key not in {"now"}}
    sub = gateway._with_rec(update_subscription_overrides, subscription_id, overrides, now=now)
    return 200, {"subscription": _json_safe(sub)}


def rest_refresh_subscription(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    subscription_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    out = gateway._with_rec(refresh_subscription, subscription_id, now=_parse_optional_now(body))
    return 200, _json_safe(out)


def rest_refresh_due(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot refresh due recommendation subscriptions",
    )
    q = _query_dict(environ)
    ids = _subscription_ids_from_query(q) or body.get("subscription_ids")
    if ids is not None and not isinstance(ids, list):
        raise ValueError("subscription_ids must be a list")
    payload: dict[str, Any] = {}
    if ids is not None:
        payload["subscription_ids"] = [str(item) for item in ids]
    now_text = _normalize_optional_now_text(
        body.get("now") if body.get("now") not in (None, "") else q.get("now")
    )
    if now_text is not None:
        payload["now"] = now_text
    return gateway._enqueue_async_job(
        environ,
        target="recommendation",
        with_fn=gateway._with_rec,
        enqueue_fn=enqueue_recommendation_async_job,
        job_type=JOB_REFRESH_DUE_SUBSCRIPTIONS,
        payload=payload,
    )


def rest_list_recommendations(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    subscription_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    rows = gateway._with_rec(list_recommendations_for_subscription, subscription_id)
    return 200, {"recommendations": _json_safe(rows)}


def rest_list_runs(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    subscription_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    rows = gateway._with_rec(list_search_runs_for_subscription, subscription_id)
    return 200, {"runs": _json_safe(rows)}


def rest_list_cards(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    cards = gateway._with_rec(
        list_in_app_cards,
        requester_id=resolve_optional_requester_id(
            gateway,
            environ,
            q.get("requester_id"),
            treat_empty_as_missing=True,
        ),
        unread_only=str(q.get("unread_only", "")).lower() in ("1", "true", "yes"),
    )
    return 200, {"cards": _json_safe(cards)}


def rest_deliver(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot deliver recommendation cards",
    )
    payload: dict[str, Any] = {}
    now_text = _normalize_optional_now_text(body.get("now"))
    if now_text is not None:
        payload["now"] = now_text
    return gateway._enqueue_async_job(
        environ,
        target="recommendation",
        with_fn=gateway._with_rec,
        enqueue_fn=enqueue_recommendation_async_job,
        job_type=JOB_DELIVER_IN_APP_RECOMMENDATIONS,
        payload=payload,
    )


def rest_get_recommendation_job(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    job_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect recommendation jobs",
    )
    return gateway._get_async_job(
        target="recommendation",
        with_fn=gateway._with_rec,
        get_fn=get_recommendation_async_job,
        job_id=job_id,
    )


def rest_list_recommendation_jobs(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect recommendation jobs",
    )
    return gateway._list_async_jobs(
        environ,
        target="recommendation",
        with_fn=gateway._with_rec,
        list_fn=list_recommendation_async_jobs,
        summary_fn=summarize_recommendation_async_jobs,
    )


def rest_record_action(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _rest_record_recommendation_mutation(
        gateway,
        environ,
        body,
        record_fn=record_recommendation_action,
    )


def rest_record_review(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _rest_record_recommendation_mutation(
        gateway,
        environ,
        body,
        record_fn=record_user_review,
    )


def rest_mark_cards_read(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    rid_int = gateway._resolve_int_actor_bound_id(
        environ,
        body.get("requester_id"),
        field_name="requester_id",
    )
    card_ids = body.get("card_ids")
    if not isinstance(card_ids, list):
        raise ValueError("card_ids must be a list of card_id strings")
    out = gateway._with_rec(
        mark_in_app_cards_read,
        requester_id=rid_int,
        card_ids=[str(item) for item in card_ids],
        now=now,
    )
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def dispatch_recommendation_rest(
    gateway: RecommendationGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    match = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)", path)
    if match and method == "GET":
        return rest_get_subscription(gateway, environ, match.group(1))
    if path == "/v1/recommendation/subscriptions" and method == "POST":
        return rest_create_subscription(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/overrides", path)
    if match and method == "PATCH":
        return rest_patch_overrides(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/refresh", path)
    if match and method == "POST":
        return rest_refresh_subscription(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/recommendation/subscriptions/refresh-due" and method == "POST":
        return rest_refresh_due(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/recommendation/jobs" and method == "GET":
        return rest_list_recommendation_jobs(gateway, environ)
    match = re.fullmatch(r"/v1/recommendation/jobs/([^/]+)", path)
    if match and method == "GET":
        return rest_get_recommendation_job(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/recommendations", path)
    if match and method == "GET":
        return rest_list_recommendations(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/runs", path)
    if match and method == "GET":
        return rest_list_runs(gateway, environ, match.group(1))
    if path == "/v1/recommendation/cards/read" and method == "POST":
        return rest_mark_cards_read(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/recommendation/cards" and method == "GET":
        return rest_list_cards(gateway, environ)
    if path == "/v1/recommendation/deliver" and method == "POST":
        return rest_deliver(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/recommendation/actions" and method == "POST":
        return rest_record_action(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/recommendation/reviews" and method == "POST":
        return rest_record_review(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    return None
