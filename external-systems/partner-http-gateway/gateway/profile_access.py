"""Shared access helpers for profile gateway transports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .role_sets import STAFF_OVERRIDE_ROLES


class ProfileAccessGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...


def resolve_optional_subject_user_id(
    gateway: ProfileAccessGateway,
    environ: dict[str, Any],
    raw_subject_user_id: Any,
    *,
    treat_empty_as_missing: bool,
) -> str | None:
    missing_values = (None, "") if treat_empty_as_missing else (None,)
    if raw_subject_user_id not in missing_values or gateway._current_actor(environ) is not None:
        return gateway._resolve_actor_bound_id(
            environ,
            raw_subject_user_id,
            field_name="subject_user_id",
        )
    return None


def resolve_visible_subject_user_id(
    gateway: ProfileAccessGateway,
    environ: dict[str, Any],
    raw_subject_user_id: str | None,
) -> str | None:
    actor = gateway._current_actor(environ)
    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
        return gateway._resolve_actor_bound_id(
            environ,
            raw_subject_user_id,
            field_name="subject_user_id",
        )
    return raw_subject_user_id


def with_resolved_subject_user_id(
    gateway: ProfileAccessGateway,
    environ: dict[str, Any],
    params: Mapping[str, Any],
    *,
    treat_empty_as_missing: bool,
) -> dict[str, Any]:
    subject_user_id = resolve_optional_subject_user_id(
        gateway,
        environ,
        params.get("subject_user_id"),
        treat_empty_as_missing=treat_empty_as_missing,
    )
    if subject_user_id is None and params.get("subject_user_id") is None and gateway._current_actor(environ) is None:
        return dict(params)
    return {**params, "subject_user_id": subject_user_id}


def with_visible_subject_user_id(
    gateway: ProfileAccessGateway,
    environ: dict[str, Any],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **params,
        "subject_user_id": resolve_visible_subject_user_id(
            gateway,
            environ,
            params.get("subject_user_id"),
        ),
    }


__all__ = [
    "resolve_optional_subject_user_id",
    "resolve_visible_subject_user_id",
    "with_resolved_subject_user_id",
    "with_visible_subject_user_id",
]
