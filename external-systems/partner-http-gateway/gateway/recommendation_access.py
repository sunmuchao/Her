"""Shared access and payload helpers for recommendation gateway transports."""

from __future__ import annotations

from typing import Any, Protocol

from .http_helpers import _payload_without_keys, _trimmed_client_idempotency_key


class RecommendationAccessGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
    ) -> dict[str, Any]: ...

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...


def resolve_optional_requester_id(
    gateway: RecommendationAccessGateway,
    environ: dict[str, Any],
    raw_requester_id: Any,
    *,
    treat_empty_as_missing: bool,
) -> int | None:
    missing_values = (None, "") if treat_empty_as_missing else (None,)
    if raw_requester_id not in missing_values or gateway._current_actor(environ) is not None:
        return gateway._resolve_int_actor_bound_id(
            environ,
            raw_requester_id,
            field_name="requester_id",
        )
    return None


def recommendation_mutation_payload(
    gateway: RecommendationAccessGateway,
    environ: dict[str, Any],
    params: dict[str, Any],
    *,
    client_idempotency_key: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    payload = _payload_without_keys(params, {"idempotency_key", "client_idempotency_key"})
    subscription = gateway._get_recommendation_subscription_for_actor(
        environ,
        str(payload.get("subscription_id") or ""),
    )
    client_key = client_idempotency_key
    if client_key is None:
        client_key = _trimmed_client_idempotency_key(
            params.get("client_idempotency_key") or params.get("idempotency_key")
        )
    if client_key is not None:
        payload["client_idempotency_key"] = client_key
    payload["subscription_id"] = subscription["subscription_id"]
    actor = gateway._current_actor(environ)
    if actor is not None:
        payload["actor_id"] = actor.actor_id
    return payload, client_key


__all__ = ["recommendation_mutation_payload", "resolve_optional_requester_id"]
