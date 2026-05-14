"""Request actor resolution and role-based authorization helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

ROLE_END_USER = "end_user"
ROLE_OPS_OPERATOR = "ops_operator"
ROLE_RISK_REVIEWER = "risk_reviewer"
ROLE_PROFILE_REVIEWER = "profile_reviewer"
ROLE_CUSTOMER_SUPPORT = "customer_support"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_SERVICE_WORKER = "service_worker"

ENVIRO_ACTOR_KEY = "partner_gateway.actor"


class GatewayAuthError(Exception):
    """Authentication failed before the request reached a route handler."""

    def __init__(self, message: str = "Invalid or missing API credentials") -> None:
        super().__init__(message)


class GatewayPermissionError(Exception):
    """The caller is authenticated but not allowed to perform the action."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class ActorPrincipal:
    actor_id: str
    roles: frozenset[str]
    token_id: str
    auth_source: str

    def has_any_role(self, roles: Iterable[str]) -> bool:
        return any(str(role) in self.roles for role in roles)

    def has_role(self, role: str) -> bool:
        return str(role) in self.roles


def _normalize_roles(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        parts = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        parts = list(raw)
    else:
        raise ValueError("roles must be a string or list")
    normalized = [str(item).strip() for item in parts if str(item).strip()]
    return frozenset(normalized)


def _principal_from_mapping(token: str, raw: Any) -> ActorPrincipal:
    if isinstance(raw, str):
        actor_id = raw.strip()
        roles = frozenset({ROLE_END_USER})
        token_id = token[:12]
    elif isinstance(raw, dict):
        actor_id = str(raw.get("actor_id") or "").strip()
        roles = _normalize_roles(raw.get("roles") or [ROLE_END_USER])
        token_id = str(raw.get("token_id") or token[:12]).strip() or token[:12]
    else:
        raise ValueError("token config must be a string or object")
    if not actor_id:
        raise ValueError("actor_id is required for every token config")
    return ActorPrincipal(
        actor_id=actor_id,
        roles=roles,
        token_id=token_id,
        auth_source="static_token",
    )


def _load_static_tokens() -> dict[str, ActorPrincipal]:
    raw = (
        os.environ.get("PARTNER_GATEWAY_STATIC_TOKENS_JSON")
        or os.environ.get("PARTNER_GATEWAY_TOKENS_JSON")
        or ""
    ).strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    out: dict[str, ActorPrincipal] = {}
    if isinstance(parsed, dict):
        for token, config in parsed.items():
            normalized_token = str(token or "").strip()
            if not normalized_token:
                raise ValueError("token must not be empty")
            out[normalized_token] = _principal_from_mapping(normalized_token, config)
        return out
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("token list items must be objects")
            token = str(item.get("token") or "").strip()
            if not token:
                raise ValueError("token is required for every token config")
            out[token] = _principal_from_mapping(token, item)
        return out
    raise ValueError("static token config must be a JSON object or list")


def _extract_bearer_or_api_key(environ: dict[str, Any]) -> str:
    auth = str(environ.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return str(environ.get("HTTP_X_API_KEY") or "").strip()


class IdentityResolver:
    __slots__ = ("_legacy_key", "_legacy_actor_id", "_legacy_roles", "_static_tokens")

    def __init__(self) -> None:
        self._legacy_key = str(os.environ.get("PARTNER_GATEWAY_API_KEY") or "").strip()
        self._legacy_actor_id = (
            str(os.environ.get("PARTNER_GATEWAY_LEGACY_API_ACTOR_ID") or "").strip()
            or "internal:legacy-api-key"
        )
        self._legacy_roles = _normalize_roles(
            os.environ.get("PARTNER_GATEWAY_LEGACY_API_ROLES")
            or f"{ROLE_PLATFORM_ADMIN},{ROLE_SERVICE_WORKER}"
        )
        self._static_tokens = _load_static_tokens()

    @property
    def required(self) -> bool:
        return bool(self._legacy_key or self._static_tokens)

    @property
    def static_token_count(self) -> int:
        return len(self._static_tokens)

    @property
    def legacy_api_required(self) -> bool:
        return bool(self._legacy_key)

    def resolve(self, environ: dict[str, Any]) -> ActorPrincipal | None:
        token = _extract_bearer_or_api_key(environ)
        if token:
            principal = self._static_tokens.get(token)
            if principal is not None:
                return principal
            if self._legacy_key and token == self._legacy_key:
                return ActorPrincipal(
                    actor_id=self._legacy_actor_id,
                    roles=self._legacy_roles,
                    token_id="legacy-api-key",
                    auth_source="legacy_api_key",
                )
            raise GatewayAuthError()
        if self.required:
            raise GatewayAuthError()
        return None


def get_current_actor(environ: dict[str, Any]) -> ActorPrincipal | None:
    actor = environ.get(ENVIRO_ACTOR_KEY)
    if isinstance(actor, ActorPrincipal):
        return actor
    return None


def set_current_actor(environ: dict[str, Any], actor: ActorPrincipal | None) -> None:
    if actor is None:
        environ.pop(ENVIRO_ACTOR_KEY, None)
        return
    environ[ENVIRO_ACTOR_KEY] = actor


__all__ = [
    "ActorPrincipal",
    "GatewayAuthError",
    "GatewayPermissionError",
    "IdentityResolver",
    "ROLE_CUSTOMER_SUPPORT",
    "ROLE_END_USER",
    "ROLE_OPS_OPERATOR",
    "ROLE_PLATFORM_ADMIN",
    "ROLE_PROFILE_REVIEWER",
    "ROLE_RISK_REVIEWER",
    "ROLE_SERVICE_WORKER",
    "get_current_actor",
    "set_current_actor",
]
