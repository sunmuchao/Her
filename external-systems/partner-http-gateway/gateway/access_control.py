"""Shared actor binding and permission helpers for the gateway."""

from __future__ import annotations

from typing import Any

from observability import audit_event

from recommendation_system import get_recommendation_by_id, get_subscription  # type: ignore[import-untyped]
from matchmaking_system.proxy_intro import get_match_case as get_proxy_intro_match_case  # type: ignore[import-untyped]
from matchmaking_system import get_match_case, get_pool_member  # type: ignore[import-untyped]

from match_domain.principal import PROFILE_ID_FIELD_ALIASES

from .identity import ROLE_END_USER, ActorPrincipal, GatewayPermissionError, get_current_actor
from .resolved_principal import resolve_end_user_principal
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

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False):
        return resolve_end_user_principal(self, environ, require_profile=require_profile)

    def _auth_session_profile_id(
        self,
        user_id: str,
        *,
        environ: dict[str, Any],
    ) -> int:
        actor = self._current_actor(environ)
        if (
            self._is_auth_session_end_user(actor)
            and actor is not None
            and str(actor.actor_id) == str(user_id)
        ):
            principal = self._resolve_end_user_principal(environ, require_profile=True)
            if principal is not None and principal.profile_id is not None:
                return int(principal.profile_id)
        raise GatewayPermissionError("请先完成资料填写后再使用发现与推荐")

    def _auth_session_requester_id(
        self,
        user_id: str,
        *,
        environ: dict[str, Any],
    ) -> int:
        """Deprecated alias for _auth_session_profile_id (§13.3)."""
        return self._auth_session_profile_id(user_id, environ=environ)

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
        if self._is_auth_session_end_user(actor) and field_name in PROFILE_ID_FIELD_ALIASES:
            bound = self._auth_session_profile_id(str(actor.actor_id), environ=environ)
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
        if self._is_auth_session_end_user(actor) and field_name in PROFILE_ID_FIELD_ALIASES:
            bound = self._auth_session_profile_id(str(actor.actor_id), environ=environ)
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

    def _get_recommendation_for_actor(
        self,
        environ: dict[str, Any],
        recommendation_id: int,
    ) -> dict[str, Any]:
        recommendation = self._with_rec(get_recommendation_by_id, int(recommendation_id))
        if not recommendation:
            raise ValueError("recommendation not found")
        self._assert_actor_can_access_owner(
            environ,
            recommendation.get("requester_id"),
            field_name="requester_id",
        )
        return recommendation

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

    def _get_case_for_actor(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]:
        try:
            return self._get_matchmaking_case_for_actor(environ, case_id)
        except GatewayPermissionError:
            raise
        except Exception:
            pass
        rec_case = self._with_proxy_intro(get_proxy_intro_match_case, case_id)
        if not rec_case:
            raise GatewayPermissionError("current actor is not allowed to access this match case")
        actor = self._current_actor(environ)
        if actor is None or actor.has_any_role(STAFF_OVERRIDE_ROLES):
            return rec_case
        requester_id = str(rec_case.get("requester_id") or "").strip()
        candidate_id = str(rec_case.get("candidate_id") or "").strip()
        participant_ids = {requester_id, candidate_id}
        matches_participant = actor.actor_id in participant_ids
        if self._is_auth_session_end_user(actor):
            try:
                resolved_profile_id = self._auth_session_profile_id(str(actor.actor_id), environ=environ)
            except GatewayPermissionError:
                resolved_profile_id = None
            if resolved_profile_id is not None:
                participant_ids.add(str(resolved_profile_id))
                if str(resolved_profile_id) in {requester_id, candidate_id}:
                    matches_participant = True
        if matches_participant:
            return rec_case
        self._audit_permission(
            environ,
            action="gateway.case_access",
            resource_type="proxy_intro_case",
            resource_id=case_id,
            outcome="denied",
            reason="current actor is not a participant in this proxy-intro case",
        )
        raise GatewayPermissionError("current actor is not allowed to access this proxy-intro case")

    def _assert_actor_can_access_ledger_relation(
        self,
        environ: dict[str, Any],
        relation: dict[str, Any],
    ) -> None:
        actor = self._current_actor(environ)
        if actor is None or actor.has_any_role(STAFF_OVERRIDE_ROLES):
            return
        owner_ref = str(relation.get("owner_profile_ref") or "").strip()
        target_ref = str(relation.get("target_profile_ref") or "").strip()
        allowed_refs: set[str] = set()
        if self._is_auth_session_end_user(actor):
            try:
                profile_id = self._auth_session_profile_id(str(actor.actor_id), environ=environ)
                allowed_refs.add(f"profile:{profile_id}")
            except GatewayPermissionError:
                pass
        if owner_ref and owner_ref == actor.actor_id:
            allowed_refs.add(owner_ref)
        if target_ref and target_ref == actor.actor_id:
            allowed_refs.add(target_ref)
        if owner_ref in allowed_refs or target_ref in allowed_refs:
            return
        self._audit_permission(
            environ,
            action="gateway.ledger_access",
            resource_type="relation",
            resource_id=relation.get("relation_key"),
            outcome="denied",
            reason="current actor is not a participant in this relation",
        )
        raise GatewayPermissionError("current actor is not allowed to access this relation")

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
