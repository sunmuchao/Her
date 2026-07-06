"""Resolve end-user Principal once per request and cache on environ (§13.3)."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain.principal import coalesce_profile_requester, user_key_from_profile_id
from match_domain.support_contracts import Principal, principal_from_actor

from .identity import GatewayPermissionError, get_current_actor

ENV_RESOLVED_PRINCIPAL = "partner_gateway.resolved_principal"


class PrincipalGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _is_auth_session_end_user(self, actor: Any) -> bool: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _lookup_onboarding_profile_id(gateway: PrincipalGateway, user_id: str) -> int | None:
    from chat_system.auth_accounts import get_onboarding_profile  # type: ignore[import-untyped]

    # 🔧 FIX: auth tables (user_onboarding_profiles) 在 her_auth 数据库，而不是 her_chat
    # 需要使用 gateway._with_auth 方法，但 Protocol 定义中没有，需要动态调用
    # 临时方案：直接使用 _with_chat，因为 gateway 实例会有 _with_auth 方法
    if hasattr(gateway, '_with_auth'):
        out = gateway._with_auth(get_onboarding_profile, str(user_id))
    else:
        # Fallback for old Protocol definition
        out = gateway._with_chat(get_onboarding_profile, str(user_id))
    return coalesce_profile_requester(
        profile_id=out.get("profile_id"),
        requester_id=out.get("requester_id"),
    )


def resolve_end_user_principal(
    gateway: PrincipalGateway,
    environ: dict[str, Any],
    *,
    require_profile: bool = False,
) -> Principal | None:
    cached = environ.get(ENV_RESOLVED_PRINCIPAL)
    if isinstance(cached, Principal):
        if require_profile and cached.profile_id is None:
            raise GatewayPermissionError("请先完成资料填写后再使用发现与推荐")
        return cached

    actor = gateway._current_actor(environ)
    if actor is None:
        if require_profile:
            raise GatewayPermissionError("请先登录后再使用发现与推荐")
        return None
    if not gateway._is_auth_session_end_user(actor):
        principal = principal_from_actor(actor, profile_id=None)
        environ[ENV_RESOLVED_PRINCIPAL] = principal
        return principal

    profile_id = _lookup_onboarding_profile_id(gateway, str(actor.actor_id))
    if profile_id is None and require_profile:
        raise GatewayPermissionError("请先完成资料填写后再使用发现与推荐")

    principal = Principal(
        user_id=str(actor.actor_id),
        profile_id=profile_id,
        roles=actor.roles if isinstance(actor.roles, frozenset) else frozenset(actor.roles or ()),
        auth_source=str(getattr(actor, "auth_source", "") or "auth_session"),
        user_key=user_key_from_profile_id(profile_id),
    )
    environ[ENV_RESOLVED_PRINCIPAL] = principal
    return principal


def principal_payload_for_actor(
    gateway: PrincipalGateway,
    environ: dict[str, Any],
) -> dict[str, Any] | None:
    principal = resolve_end_user_principal(gateway, environ, require_profile=False)
    if principal is None:
        actor = get_current_actor(environ)
        if actor is None:
            return None
        return principal_from_actor(actor, profile_id=None).to_dict()
    return principal.to_dict()


__all__ = [
    "ENV_RESOLVED_PRINCIPAL",
    "PrincipalGateway",
    "principal_payload_for_actor",
    "resolve_end_user_principal",
]
