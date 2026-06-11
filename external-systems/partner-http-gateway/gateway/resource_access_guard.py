"""Unified resource access control framework for the gateway.

This module provides a centralized, declarative approach to resource-level
authorization, eliminating scattered IDOR vulnerabilities across routes.

Design Principles:
1. Hard constraints (security boundaries) in code layer
2. Soft constraints (business rules) expressed via configuration
3. All access decisions audited
4. Single source of truth for resource ownership

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                  ResourceAccessGuard                         │
│                                                              │
│  Responsibilities:                                           │
│  - Verify resource exists                                    │
│  - Resolve resource owner                                    │
│  - Check actor-owner relationship                            │
│  - Apply role-based overrides                                │
│  - Audit all decisions                                       │
│                                                              │
│  NOT responsible for:                                        │
│  - Input validation (handled by http_helpers)               │
│  - Business logic (handled by services)                     │
│  - Output formatting (handled by routes)                    │
└─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from observability import audit_event

from .identity import ActorPrincipal, GatewayPermissionError, get_current_actor
from .role_sets import STAFF_OVERRIDE_ROLES


class ResourceType(str, Enum):
    """Enumeration of protected resource types."""

    PROFILE = "profile"
    RECOMMENDATION = "recommendation"
    SUBSCRIPTION = "subscription"
    MATCH_CASE = "match_case"
    DISCOVERY_SESSION = "discovery_session"
    CHAT_THREAD = "chat_thread"
    VERIFICATION_SUBMISSION = "verification_submission"
    MEDIA = "media"
    RELATION = "relation"
    RISK_CASE = "risk_case"
    ASSESSMENT = "assessment"
    CALL_SESSION = "call_session"


class AccessAction(str, Enum):
    """Enumeration of access actions."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    REVIEW = "review"
    OVERRIDE = "override"


@dataclass(frozen=True)
class ResourceAccessDecision:
    """Result of an access control decision."""

    allowed: bool
    resource_type: ResourceType
    resource_id: str
    owner_id: str | None
    actor_id: str | None
    action: AccessAction
    reason: str | None = None
    override_used: bool = False
    override_role: str | None = None


class ResourceAccessGateway(Protocol):
    """Protocol for gateway implementations supporting resource access control."""

    def _current_actor(self, environ: dict[str, Any]) -> ActorPrincipal | None: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_mm(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_ledger(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _discovery(self) -> Any: ...

    def _is_auth_session_end_user(self, actor: ActorPrincipal | None) -> bool: ...

    def _resolve_end_user_principal(
        self, environ: dict[str, Any], *, require_profile: bool = False
    ) -> Any: ...


class ResourceAccessGuard:
    """Centralized resource access control guard.

    Usage:
        guard = ResourceAccessGuard(gateway, environ)

        # Check access before fetching resource
        decision = guard.check_access(ResourceType.PROFILE, "12345", AccessAction.READ)
        if not decision.allowed:
            raise GatewayPermissionError(decision.reason)

        # Or use assertion pattern
        guard.assert_access(ResourceType.PROFILE, "12345", AccessAction.READ)

    This eliminates IDOR vulnerabilities by:
    1. Centralizing owner resolution logic
    2. Enforcing consistent access checks
    3. Auditing all decisions
    4. Preventing bypass via query parameters
    """

    __slots__ = ("_gateway", "_environ", "_audit_enabled")

    # Resource owner resolution functions by type
    # Each function takes (gateway, resource_id) and returns owner_id
    _OWNER_RESOLVERS: dict[ResourceType, Callable[[Any, str], str | None]] = {}

    # Resource existence check functions by type
    # Each function takes (gateway, resource_id) and returns bool
    _EXISTENCE_CHECKERS: dict[ResourceType, Callable[[Any, str], bool]] = {}

    # Participant-based resources: owner is determined by checking if actor is participant
    _PARTICIPANT_RESOURCES: frozenset[ResourceType] = frozenset({
        ResourceType.CHAT_THREAD,
        ResourceType.MATCH_CASE,
        ResourceType.CALL_SESSION,
        ResourceType.RELATION,
    })

    def __init__(
        self,
        gateway: ResourceAccessGateway,
        environ: dict[str, Any],
        *,
        audit_enabled: bool = True,
    ) -> None:
        self._gateway = gateway
        self._environ = environ
        self._audit_enabled = audit_enabled

    def _audit_decision(self, decision: ResourceAccessDecision) -> None:
        """Record access decision in audit log."""
        if not self._audit_enabled:
            return
        audit_event(
            action=f"gateway.resource_access.{decision.action.value}",
            resource_type=decision.resource_type.value,
            resource_id=decision.resource_id,
            outcome="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            actor_id=decision.actor_id,
            owner_id=decision.owner_id,
            override_used=decision.override_used,
            override_role=decision.override_role,
            http_method=self._environ.get("REQUEST_METHOD"),
            path=self._environ.get("PATH_INFO"),
        )

    def _resolve_owner(self, resource_type: ResourceType, resource_id: str) -> str | None:
        """Resolve the owner of a resource.

        Returns:
            Owner identifier (user_id, profile_id, etc.)
            None if resource doesn't exist or has no owner
        """
        resolver = self._OWNER_RESOLVERS.get(resource_type)
        if resolver is not None:
            return resolver(self._gateway, resource_id)

        # Default: use resource_id as owner (for PROFILE type)
        if resource_type == ResourceType.PROFILE:
            return resource_id

        return None

    def _check_exists(self, resource_type: ResourceType, resource_id: str) -> bool:
        """Check if a resource exists."""
        checker = self._EXISTENCE_CHECKERS.get(resource_type)
        if checker is not None:
            return checker(self._gateway, resource_id)
        return True  # Assume exists if no checker registered

    def _get_actor_bound_profile_id(self) -> int | None:
        """Get the profile_id bound to current actor (for auth_session users)."""
        actor = self._gateway._current_actor(self._environ)
        if actor is None:
            return None
        if self._gateway._is_auth_session_end_user(actor):
            resolved = self._gateway._resolve_end_user_principal(
                self._environ, require_profile=True
            )
            if resolved is not None and resolved.profile_id is not None:
                return int(resolved.profile_id)
        return None

    def check_access(
        self,
        resource_type: ResourceType,
        resource_id: str,
        action: AccessAction,
        *,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
        participant_check_fn: Callable[[str, str], bool] | None = None,
    ) -> ResourceAccessDecision:
        """Check if current actor can access a resource.

        Args:
            resource_type: Type of the resource
            resource_id: Identifier of the resource
            action: Action being performed
            allow_override_roles: Roles that can override ownership check
            participant_check_fn: Custom function to check if actor is participant

        Returns:
            ResourceAccessDecision with details of the access check
        """
        actor = self._gateway._current_actor(self._environ)
        actor_id = actor.actor_id if actor is not None else None
        owner_id = None
        reason = None
        override_used = False
        override_role = None

        # Step 1: Actor must be authenticated
        if actor is None:
            decision = ResourceAccessDecision(
                allowed=False,
                resource_type=resource_type,
                resource_id=resource_id,
                owner_id=None,
                actor_id=None,
                action=action,
                reason="Authentication required",
            )
            self._audit_decision(decision)
            return decision

        # Step 2: Check if resource exists (for sensitive resources)
        if not self._check_exists(resource_type, resource_id):
            decision = ResourceAccessDecision(
                allowed=False,
                resource_type=resource_type,
                resource_id=resource_id,
                owner_id=None,
                actor_id=actor_id,
                action=action,
                reason="Resource not found",
            )
            self._audit_decision(decision)
            return decision

        # Step 3: Resolve resource owner
        owner_id = self._resolve_owner(resource_type, resource_id)

        # Step 4: Check role-based override
        if actor.has_any_role(allow_override_roles):
            # Staff override: allow access but audit it
            override_used = True
            override_role = next(
                (r for r in allow_override_roles if actor.has_role(r)), None
            )
            decision = ResourceAccessDecision(
                allowed=True,
                resource_type=resource_type,
                resource_id=resource_id,
                owner_id=owner_id,
                actor_id=actor_id,
                action=action,
                override_used=True,
                override_role=override_role,
            )
            self._audit_decision(decision)
            return decision

        # Step 5: Check ownership/participation
        if resource_type in self._PARTICIPANT_RESOURCES:
            # Participant-based resources: actor must be a participant
            if participant_check_fn is not None:
                is_participant = participant_check_fn(actor_id, resource_id)
            else:
                # Default participant check: owner_id matches actor_id
                is_participant = owner_id == actor_id

            if not is_participant:
                # For auth_session users, also check profile_id binding
                bound_profile_id = self._get_actor_bound_profile_id()
                if bound_profile_id is not None:
                    # Check if profile_id is in participant list
                    is_participant = str(bound_profile_id) in {
                        owner_id or "",
                        resource_id,
                    }

            if not is_participant:
                decision = ResourceAccessDecision(
                    allowed=False,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    owner_id=owner_id,
                    actor_id=actor_id,
                    action=action,
                    reason="Actor is not a participant of this resource",
                )
                self._audit_decision(decision)
                return decision

        else:
            # Owner-based resources: actor must be the owner
            bound_profile_id = self._get_actor_bound_profile_id()

            # For auth_session end_user, use profile_id binding
            if self._gateway._is_auth_session_end_user(actor) and bound_profile_id is not None:
                expected_owner = str(bound_profile_id)
                if owner_id != expected_owner:
                    decision = ResourceAccessDecision(
                        allowed=False,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        owner_id=owner_id,
                        actor_id=actor_id,
                        action=action,
                        reason=f"Resource owner mismatch: expected {expected_owner}, got {owner_id}",
                    )
                    self._audit_decision(decision)
                    return decision

            # For other actor types, check actor_id
            elif owner_id is not None and owner_id != actor_id:
                decision = ResourceAccessDecision(
                    allowed=False,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    owner_id=owner_id,
                    actor_id=actor_id,
                    action=action,
                    reason="Actor is not the owner of this resource",
                )
                self._audit_decision(decision)
                return decision

        # Step 6: Access allowed
        decision = ResourceAccessDecision(
            allowed=True,
            resource_type=resource_type,
            resource_id=resource_id,
            owner_id=owner_id,
            actor_id=actor_id,
            action=action,
        )
        self._audit_decision(decision)
        return decision

    def assert_access(
        self,
        resource_type: ResourceType,
        resource_id: str,
        action: AccessAction,
        *,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
        participant_check_fn: Callable[[str, str], bool] | None = None,
    ) -> str | None:
        """Assert that actor can access resource, raising exception if not.

        Args:
            Same as check_access

        Returns:
            Owner ID if access allowed

        Raises:
            GatewayPermissionError if access denied
        """
        decision = self.check_access(
            resource_type,
            resource_id,
            action,
            allow_override_roles=allow_override_roles,
            participant_check_fn=participant_check_fn,
        )
        if not decision.allowed:
            raise GatewayPermissionError(decision.reason or "Access denied")
        return decision.owner_id


# Register owner resolvers for specific resource types
def _register_owner_resolver(resource_type: ResourceType, resolver: Callable[[Any, str], str | None]) -> None:
    """Register a custom owner resolver for a resource type."""
    ResourceAccessGuard._OWNER_RESOLVERS[resource_type] = resolver


def _register_existence_checker(resource_type: ResourceType, checker: Callable[[Any, str], bool]) -> None:
    """Register a custom existence checker for a resource type."""
    ResourceAccessGuard._EXISTENCE_CHECKERS[resource_type] = checker


# Owner resolvers implementation
def _resolve_recommendation_owner(gateway: ResourceAccessGateway, recommendation_id: str) -> str | None:
    """Resolve owner of a recommendation."""
    from recommendation_system import get_recommendation_by_id  # type: ignore[import-untyped]
    try:
        rec = gateway._with_rec(get_recommendation_by_id, int(recommendation_id))
        if not rec:
            return None
        return str(rec.get("requester_id") or "")
    except (ValueError, TypeError):
        return None


def _resolve_subscription_owner(gateway: ResourceAccessGateway, subscription_id: str) -> str | None:
    """Resolve owner of a subscription."""
    from recommendation_system import get_subscription  # type: ignore[import-untyped]
    try:
        sub = gateway._with_rec(get_subscription, subscription_id)
        if not sub:
            return None
        return str(sub.get("requester_id") or "")
    except (ValueError, TypeError):
        return None


def _resolve_discovery_session_owner(gateway: ResourceAccessGateway, session_id: str) -> str | None:
    """Resolve owner of a discovery session."""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        return str(owner_id) if owner_id else None
    except Exception:
        return None


def _resolve_verification_submission_owner(gateway: ResourceAccessGateway, submission_id: str) -> str | None:
    """Resolve owner of a verification submission."""
    from chat_system import get_verification_submission  # type: ignore[import-untyped]
    try:
        submission = gateway._with_chat(get_verification_submission, submission_id)
        if not submission:
            return None
        return str(submission.get("user_id") or "")
    except (ValueError, TypeError):
        return None


def _resolve_chat_thread_owner(gateway: ResourceAccessGateway, thread_id: str) -> str | None:
    """Resolve owner of a chat thread (returns participants)."""
    from chat_system import get_thread  # type: ignore[import-untyped]
    try:
        thread = gateway._with_chat(get_thread, thread_id)
        if not thread:
            return None
        # Thread ownership is determined by participation
        return f"{thread.get('participant_a_id')},{thread.get('participant_b_id')}"
    except (ValueError, TypeError):
        return None


def _resolve_match_case_owner(gateway: ResourceAccessGateway, case_id: str) -> str | None:
    """Resolve owner of a match case (returns participants)."""
    from matchmaking_system import get_match_case, get_pool_member  # type: ignore[import-untyped]
    try:
        case = gateway._with_mm(get_match_case, case_id)
        if not case:
            return None
        member_ids = {
            str(case.get("first_contact_member_id") or "").strip(),
            str(case.get("second_contact_member_id") or "").strip(),
        }
        member_ids.discard("")
        user_keys = []
        for member_id in member_ids:
            member = gateway._with_mm(get_pool_member, member_id)
            user_keys.append(str(member.get("user_key") or ""))
        return ",".join(user_keys) if user_keys else None
    except (ValueError, TypeError):
        return None


# Register all resolvers
_register_owner_resolver(ResourceType.RECOMMENDATION, _resolve_recommendation_owner)
_register_owner_resolver(ResourceType.SUBSCRIPTION, _resolve_subscription_owner)
_register_owner_resolver(ResourceType.DISCOVERY_SESSION, _resolve_discovery_session_owner)
_register_owner_resolver(ResourceType.VERIFICATION_SUBMISSION, _resolve_verification_submission_owner)
_register_owner_resolver(ResourceType.CHAT_THREAD, _resolve_chat_thread_owner)
_register_owner_resolver(ResourceType.MATCH_CASE, _resolve_match_case_owner)


# Convenience functions for routes
def guard_resource_access(
    gateway: ResourceAccessGateway,
    environ: dict[str, Any],
    resource_type: ResourceType,
    resource_id: str,
    action: AccessAction,
    *,
    allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
) -> str | None:
    """Convenience function: assert access and return owner_id.

    Usage in routes:
        owner_id = guard_resource_access(
            gateway, environ,
            ResourceType.PROFILE, candidate_id,
            AccessAction.READ,
        )
    """
    guard = ResourceAccessGuard(gateway, environ)
    return guard.assert_access(resource_type, resource_id, action, allow_override_roles=allow_override_roles)


def check_resource_access(
    gateway: ResourceAccessGateway,
    environ: dict[str, Any],
    resource_type: ResourceType,
    resource_id: str,
    action: AccessAction,
    *,
    allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
) -> bool:
    """Convenience function: check access without raising exception.

    Usage in routes:
        if not check_resource_access(gateway, environ, ResourceType.PROFILE, id, AccessAction.READ):
            return 403, {"error": {"code": "forbidden"}}
    """
    guard = ResourceAccessGuard(gateway, environ)
    decision = guard.check_access(resource_type, resource_id, action, allow_override_roles=allow_override_roles)
    return decision.allowed


__all__ = [
    "AccessAction",
    "ResourceAccessDecision",
    "ResourceAccessGuard",
    "ResourceAccessGateway",
    "ResourceType",
    "guard_resource_access",
    "check_resource_access",
    "_register_existence_checker",
    "_register_owner_resolver",
]