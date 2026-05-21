"""Shared actor binding and permission helpers for the gateway."""

from __future__ import annotations

from typing import Any

from observability import audit_event

from recommendation_system import get_subscription  # type: ignore[import-untyped]
from matchmaking_system import get_match_case, get_pool_member  # type: ignore[import-untyped]

from .identity import ROLE_END_USER, ActorPrincipal, GatewayPermissionError, get_current_actor
from .role_sets import STAFF_OVERRIDE_ROLES


class GatewayAccessMixin:
    def _current_actor(self, environ: dict[str, Any]) -> ActorPrincipal | None:
        return get_current_actor(environ)

    def _is_auth_session_end_user(self, actor: ActorPrincipal | None) -> bool:
        return (
            actor is not None
            and actor.auth_source == "auth_session"
            and actor.has_any_role(frozenset({ROLE_END_USER}))
        )

    def _auth_session_requester_id(self, user_id: str) -> int:
        from chat_system.auth_accounts import get_onboarding_profile  # type: ignore[import-untyped]

        out = self._with_chat(get_onboarding_profile, str(user_id))
        profile_id = out.get("profile_id") or out.get("requester_id")
        if profile_id is None:
            raise GatewayPermissionError("请先完成资料填写后再使用发现与推荐")
        return int(profile_id)

    def _audit_permission(
        self,
        environ: dict[str, Any],
        *,
        action: str,
        resource_type: str,
        outcome: str,
        resource_id: Any = None,
        reason: str | None = None,
        impersonated_owner_id: Any = None,
        **extra: Any,
    ) -> None:
        audit_event(
            action=action,
            resource_type=resource_type,
            outcome=outcome,
            resource_id=resource_id,
            reason=reason,
            impersonated_owner_id=impersonated_owner_id,
            http_method=environ.get("REQUEST_METHOD"),
            path=environ.get("PATH_INFO"),
            **extra,
        )

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str = "current actor is not allowed to access this route",
    ) -> ActorPrincipal | None:
        actor = self._current_actor(environ)
        if actor is None:
            return None
        if actor.has_any_role(roles):
            self._audit_permission(
                environ,
                action="gateway.role_guard",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="allowed",
                required_roles=sorted(roles),
            )
            return actor
        self._audit_permission(
            environ,
            action="gateway.role_guard",
            resource_type="route",
            resource_id=environ.get("PATH_INFO"),
            outcome="denied",
            reason=message,
            required_roles=sorted(roles),
        )
        raise GatewayPermissionError(message)

    def _resolve_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str:
        supplied_text = str(supplied_id or "").strip()
        actor = self._current_actor(environ)
        if actor is None:
            if not supplied_text:
                raise ValueError(f"{field_name} is required")
            return supplied_text
        if not actor.has_any_role(roles):
            self._audit_permission(
                environ,
                action="gateway.operator_binding",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="denied",
                reason=message,
                field_name=field_name,
            )
            raise GatewayPermissionError(message)
        if supplied_text and supplied_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.operator_binding",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="denied",
                reason=f"{field_name} must match current actor",
                field_name=field_name,
                impersonated_owner_id=supplied_text,
            )
            raise GatewayPermissionError(f"{field_name} must match current actor")
        self._audit_permission(
            environ,
            action="gateway.operator_binding",
            resource_type="route",
            resource_id=environ.get("PATH_INFO"),
            outcome="allowed",
            field_name=field_name,
        )
        return actor.actor_id

    def _resolve_optional_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str | None:
        supplied_text = str(supplied_id or "").strip() or None
        actor = self._current_actor(environ)
        if actor is None:
            return supplied_text
        if not actor.has_any_role(roles):
            raise GatewayPermissionError(message)
        if supplied_text and supplied_text != actor.actor_id:
            raise GatewayPermissionError(f"{field_name} must match current actor")
        return actor.actor_id

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str:
        supplied_text = str(supplied_id or "").strip()
        actor = self._current_actor(environ)
        if actor is None:
            if not supplied_text:
                raise ValueError(f"{field_name} is required")
            return supplied_text
        if actor.has_any_role(allow_override_roles):
            if supplied_text and supplied_text != actor.actor_id:
                self._audit_permission(
                    environ,
                    action="gateway.staff_override",
                    resource_type="actor_binding",
                    resource_id=field_name,
                    outcome="allowed",
                    impersonated_owner_id=supplied_text,
                )
            return supplied_text or actor.actor_id
        if supplied_text and supplied_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.owner_binding",
                resource_type="actor_binding",
                resource_id=field_name,
                outcome="denied",
                reason=f"{field_name} does not match current actor",
                impersonated_owner_id=supplied_text,
            )
            raise GatewayPermissionError(f"{field_name} does not match current actor")
        return actor.actor_id

    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str:
        owner_text = str(owner_id or "").strip()
        actor = self._current_actor(environ)
        if self._is_auth_session_end_user(actor) and field_name == "requester_id":
            bound = self._auth_session_requester_id(str(actor.actor_id))
            if owner_text:
                try:
                    if int(owner_text) != bound:
                        raise GatewayPermissionError(f"{field_name} does not match current actor")
                except (TypeError, ValueError) as exc:
                    raise GatewayPermissionError(f"{field_name} does not match current actor") from exc
            return str(bound)
        if actor is None or not owner_text or actor.has_any_role(allow_override_roles):
            if (
                actor is not None
                and owner_text
                and actor.has_any_role(allow_override_roles)
                and owner_text != actor.actor_id
            ):
                self._audit_permission(
                    environ,
                    action="gateway.staff_override",
                    resource_type="resource_owner",
                    resource_id=field_name,
                    outcome="allowed",
                    impersonated_owner_id=owner_text,
                )
            return owner_text
        if owner_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.owner_check",
                resource_type="resource_owner",
                resource_id=field_name,
                outcome="denied",
                reason=f"{field_name} does not match current actor",
                impersonated_owner_id=owner_text,
            )
            raise GatewayPermissionError(f"{field_name} does not match current actor")
        return owner_text

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> int:
        actor = self._current_actor(environ)
        if self._is_auth_session_end_user(actor) and field_name == "requester_id":
            bound = self._auth_session_requester_id(str(actor.actor_id))
            supplied_text = str(supplied_id or "").strip()
            if supplied_text:
                try:
                    if int(supplied_text) != bound:
                        self._audit_permission(
                            environ,
                            action="gateway.owner_binding",
                            resource_type="actor_binding",
                            resource_id=field_name,
                            outcome="denied",
                            reason=f"{field_name} does not match current actor",
                            impersonated_owner_id=supplied_text,
                        )
                        raise GatewayPermissionError(f"{field_name} does not match current actor")
                except (TypeError, ValueError) as exc:
                    raise GatewayPermissionError(f"{field_name} must be an integer") from exc
            return bound

        value = self._resolve_actor_bound_id(
            environ,
            supplied_id,
            field_name=field_name,
            allow_override_roles=allow_override_roles,
        )
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
    ) -> dict[str, Any]:
        subscription = self._with_rec(get_subscription, subscription_id)
        self._assert_actor_can_access_owner(
            environ,
            subscription.get("requester_id"),
            field_name="requester_id",
        )
        return subscription

    def _get_matchmaking_member_for_actor(
        self,
        environ: dict[str, Any],
        member_id: str,
    ) -> dict[str, Any]:
        member = self._with_mm(get_pool_member, member_id)
        self._assert_actor_can_access_owner(
            environ,
            member.get("user_key"),
            field_name="user_key",
        )
        return member

    def _get_matchmaking_case_for_actor(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]:
        case = self._with_mm(get_match_case, case_id)
        actor = self._current_actor(environ)
        if actor is None or actor.has_any_role(STAFF_OVERRIDE_ROLES):
            if actor is not None and actor.has_any_role(STAFF_OVERRIDE_ROLES):
                member_ids = {
                    str(case.get("first_contact_member_id") or "").strip(),
                    str(case.get("second_contact_member_id") or "").strip(),
                }
                member_ids.discard("")
                owner_keys = sorted(
                    {
                        str(self._with_mm(get_pool_member, member_id).get("user_key") or "").strip()
                        for member_id in member_ids
                    }
                )
                owner_keys = [value for value in owner_keys if value and value != actor.actor_id]
                if owner_keys:
                    self._audit_permission(
                        environ,
                        action="gateway.staff_override",
                        resource_type="matchmaking_case",
                        resource_id=case_id,
                        outcome="allowed",
                        impersonated_owner_id=",".join(owner_keys),
                    )
            return case
        member_ids = {
            str(case.get("first_contact_member_id") or "").strip(),
            str(case.get("second_contact_member_id") or "").strip(),
        }
        member_ids.discard("")
        for member_id in member_ids:
            member = self._with_mm(get_pool_member, member_id)
            if str(member.get("user_key") or "").strip() == actor.actor_id:
                return case
        self._audit_permission(
            environ,
            action="gateway.case_access",
            resource_type="matchmaking_case",
            resource_id=case_id,
            outcome="denied",
            reason="current actor is not a participant in this match case",
        )
        raise GatewayPermissionError("current actor is not allowed to access this match case")


__all__ = ["GatewayAccessMixin"]
