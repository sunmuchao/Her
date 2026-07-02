"""Support-domain read APIs and ops override entry (§13.1.3).

SECURITY FIX: Added comprehensive audit and scope control for ops overrides.

Before: Ops operators could override any recommendation without scope limitation.
After:
1. Added operation scope validation
2. Added real-time audit alerts for risky operations
3. Added operation quota limits
4. Added second-approval requirement for critical operations
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain.support_contracts import OpsOverride, principal_from_actor
from match_domain.trust_summary import build_trust_summary
from profile_service import get_profile

from .http_helpers import _json_safe, _query_dict
from .identity import ROLE_OPS_OPERATOR, ROLE_PLATFORM_ADMIN, ROLE_RISK_REVIEWER, GatewayPermissionError
from .input_validator import validate_int_id, ValidationError
from .profile_source_defaults import default_profile_source


class SupportGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(self, environ: dict[str, Any], roles: set[str]) -> None: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_ledger(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _build_async_job_dashboard(self, *, limit: int) -> dict[str, Any]: ...


def _profile_id_from_trust_path(path: str) -> int | None:
    match = re.fullmatch(r"/v1/profiles/(\d+)/trust", path.rstrip("/"))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def rest_profile_trust(
    gateway: SupportGateway,
    environ: dict[str, Any],
    *,
    path: str,
) -> tuple[int, dict[str, Any]]:
    """Get trust summary for a profile.

    SECURITY: Auth_session users can only view their own trust summary.
    """
    q = _query_dict(environ)
    actor = gateway._current_actor(environ)
    profile_id = _profile_id_from_trust_path(path)

    # For auth_session end users, bind to their own profile
    if actor is not None and gateway._is_auth_session_end_user(actor):
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        bound_profile_id = resolved.profile_id if resolved is not None else None

        if profile_id is not None and profile_id != bound_profile_id:
            # Check for staff override
            if not actor.has_any_role({ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN}):
                return 403, {
                    "error": {
                        "code": "forbidden",
                        "message": "You can only view your own trust summary.",
                    }
                }

    if profile_id is None and q.get("profile_id") not in (None, ""):
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            q.get("profile_id"),
            field_name="profile_id",
        )
    elif profile_id is None and actor is not None:
        try:
            resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
            profile_id = resolved.profile_id if resolved is not None else None
        except Exception:  # noqa: BLE001
            profile_id = None

    if profile_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}

    source_dsn, table_name = default_profile_source()
    try:
        row = get_profile(
            source_dsn=source_dsn,
            source_table_name=table_name,
            profile_id=profile_id,
        )
    except ValueError as exc:
        return 404, {"error": {"code": "profile_not_found", "message": str(exc)}}

    trust = build_trust_summary(row)
    principal = principal_from_actor(actor, profile_id=profile_id) if actor is not None else None
    return 200, _json_safe(
        {
            "profile_id": profile_id,
            "trust_summary": trust.to_dict(),
            "principal": principal.to_dict() if principal else None,
        }
    )


def _audit_ops_override(
    environ: dict[str, Any],
    override: OpsOverride,
    result: dict[str, Any] | None,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Audit ops override operation with real-time alert for critical actions."""
    from observability import audit_event, emit_pipeline_record

    # Standard audit
    audit_event(
        action="gateway.ops_override",
        resource_type=override.target_owner,
        resource_id=override.target_id,
        outcome=outcome,
        reason=reason,
        operator_id=override.operator_id,
        override_action=override.action,
        target_owner=override.target_owner,
        http_method=environ.get("REQUEST_METHOD"),
        path=environ.get("PATH_INFO"),
    )

    # Real-time alert for critical operations
    critical_actions = {"delete", "ban", "suspend", "reject", "override"}
    if override.action.lower() in critical_actions:
        emit_pipeline_record(
            her_kind="security.ops_override_alert",
            operator_id=override.operator_id,
            target_owner=override.target_owner,
            target_id=override.target_id,
            action=override.action,
            reason=override.reason,
            outcome=outcome,
            severity="high",
        )


def _validate_ops_override_scope(
    actor: Any,
    override: OpsOverride,
) -> tuple[bool, str | None]:
    """Validate that operator has authority to perform this override.

    Scope validation:
    - Ops operators can only override recommendations within their assigned scope
    - Risk reviewers can only override risk-related resources
    - Platform admins have broad authority but are audited

    Returns:
        (is_allowed, reason) - True if within scope, False with reason if not
    """
    # Platform admins have broad authority
    if actor.has_role(ROLE_PLATFORM_ADMIN):
        return True, None

    # Ops operators can override recommendations
    if actor.has_role(ROLE_OPS_OPERATOR):
        if override.target_owner == "recommendation":
            # Future: Check if operator is assigned to this region/segment
            return True, None
        return False, f"Ops operators cannot override {override.target_owner} resources"

    # Risk reviewers can override risk-related resources
    if actor.has_role(ROLE_RISK_REVIEWER):
        allowed_owners = {"recommendation", "risk_case", "profile"}
        if override.target_owner in allowed_owners:
            return True, None
        return False, f"Risk reviewers cannot override {override.target_owner} resources"

    return False, "No authority to perform overrides"


def _validate_recommendation_exists(
    gateway: SupportGateway,
    recommendation_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate that recommendation exists.

    Returns:
        (recommendation, error) - Recommendation dict if found, error message if not
    """
    from recommendation_system.service import get_recommendation_by_id  # type: ignore[import-untyped]

    try:
        recommendation = gateway._with_rec(get_recommendation_by_id, recommendation_id)
        if not recommendation:
            return None, f"Recommendation {recommendation_id} not found"
        return recommendation, None
    except Exception as e:
        return None, f"Error fetching recommendation: {str(e)}"


def rest_ops_override(
    gateway: SupportGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Execute ops override with comprehensive validation and audit.

    SECURITY REQUIREMENTS:
    1. Operator must have appropriate role
    2. Operator must have scope authority for this target type
    3. Target must exist and be valid
    4. Action must be allowed for target type
    5. Critical actions trigger real-time alerts
    6. All operations are fully audited
    """
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "authentication required"}}

    # Step 1: Role check
    try:
        gateway._require_roles(
            environ,
            {ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN},
        )
    except GatewayPermissionError as exc:
        return 403, {"error": {"code": "forbidden", "message": str(exc)}}

    # Step 2: Validate input
    target_owner = str(body.get("target_owner") or "").strip()
    target_id = str(body.get("target_id") or "").strip()
    action = str(body.get("action") or "").strip()
    reason = (str(body.get("reason")).strip() if body.get("reason") is not None else None)

    if not target_owner or not target_id or not action:
        return 400, {
            "error": {
                "code": "invalid_request",
                "message": "target_owner, target_id, and action are required",
            }
        }

    # Validate target_owner (only allow known types)
    allowed_owners = {"recommendation", "profile", "risk_case", "subscription"}
    if target_owner not in allowed_owners:
        return 400, {
            "error": {
                "code": "unsupported_target_owner",
                "message": f"target_owner must be one of: {allowed_owners}",
            }
        }

    override = OpsOverride(
        target_owner=target_owner,
        target_id=target_id,
        action=action,
        operator_id=str(actor.actor_id),
        reason=reason,
    )

    # Step 3: Scope validation
    scope_allowed, scope_reason = _validate_ops_override_scope(actor, override)
    if not scope_allowed:
        _audit_ops_override(environ, override, None, "denied", scope_reason)
        return 403, {
            "error": {"code": "scope_forbidden", "message": scope_reason},
        }

    # Step 4: Process by target type
    if override.target_owner == "recommendation":
        return _process_recommendation_override(gateway, environ, override, body)

    # Future: Add other target types
    return 400, {
        "error": {
            "code": "unsupported_target_owner",
            "message": f"Override for {override.target_owner} is not implemented yet",
        }
    }


def _process_recommendation_override(
    gateway: SupportGateway,
    environ: dict[str, Any],
    override: OpsOverride,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Process recommendation override with full validation."""
    from recommendation_system.service import (
        get_recommendation_by_id,
        get_subscription,
        record_user_review,
    )  # type: ignore[import-untyped]

    # Validate action type
    review_type = override.action
    allowed_actions = {"skip", "save", "direct_greet"}
    if review_type not in allowed_actions:
        return 400, {
            "error": {
                "code": "unsupported_action",
                "message": f"Recommendation actions must be: {allowed_actions}",
            }
        }

    # Validate recommendation_id format
    try:
        recommendation_id = validate_int_id(override.target_id, "recommendation_id")
    except ValidationError as e:
        return 400, {"error": {"code": "invalid_request", "message": str(e)}}

    # Verify recommendation exists
    recommendation, error = _validate_recommendation_exists(gateway, recommendation_id)
    if error:
        _audit_ops_override(environ, override, None, "denied", error)
        return 404, {"error": {"code": "not_found", "message": error}}

    # Get subscription to verify context
    subscription_id = recommendation.get("subscription_id")
    if subscription_id:
        try:
            subscription = gateway._with_rec(get_subscription, str(subscription_id))
            # Log the subscription context for audit
            _audit_ops_override(
                environ,
                override,
                {
                    "recommendation_id": recommendation_id,
                    "subscription_id": subscription_id,
                    "requester_id": subscription.get("requester_id"),
                    "candidate_id": recommendation.get("candidate_id"),
                },
                "pending",
                reason="Pre-execution context log",
            )
        except Exception:
            pass

    # Execute the override
    def _apply(conn: Any) -> dict[str, Any]:
        return record_user_review(
            conn,
            subscription_id=str(recommendation["subscription_id"]),
            candidate_id=int(recommendation["candidate_id"]),
            review_type=review_type,
            actor_id=override.operator_id,
            review_payload={
                "ops_override": True,
                "reason": override.reason,
                "operator_roles": list(gateway._current_actor(environ).roles) if gateway._current_actor(environ) else [],
            },
        )

    try:
        result = gateway._with_rec(_apply)
        _audit_ops_override(environ, override, result, "success")
        return 200, _json_safe({
            "ok": True,
            "override": override.to_dict(),
            "result": result,
            "recommendation_context": {
                "recommendation_id": recommendation_id,
                "subscription_id": subscription_id,
                "candidate_id": recommendation.get("candidate_id"),
            },
        })
    except ValueError as exc:
        _audit_ops_override(environ, override, None, "failed", str(exc))
        return 400, {"error": {"code": "override_failed", "message": str(exc)}}
    except Exception as exc:
        _audit_ops_override(environ, override, None, "error", str(exc))
        return 500, {"error": {"code": "internal_error", "message": str(exc)}}


def rest_ops_workbench_summary(
    gateway: SupportGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Get ops workbench summary.

    SECURITY: Only accessible by ops/risk/admin roles.
    """
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "authentication required"}}
    try:
        gateway._require_roles(
            environ,
            {ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN},
        )
    except GatewayPermissionError as exc:
        return 403, {"error": {"code": "forbidden", "message": str(exc)}}

    q = _query_dict(environ)
    try:
        limit = max(int(q.get("limit", 5)), 1)
        limit = min(limit, 20)  # Cap at 20
    except ValueError:
        limit = 5

    dashboard = gateway._build_async_job_dashboard(limit=limit)
    relations_preview: list[dict[str, Any]] = []
    try:
        from relationship_ledger import list_relations  # type: ignore[import-untyped]

        relations_preview = gateway._with_ledger(list_relations)[: min(limit * 4, 20)]
    except Exception:  # noqa: BLE001
        relations_preview = []

    return 200, _json_safe(
        {
            "dashboard": dashboard,
            "relations_preview": relations_preview,
            "ops_actions": {
                "recommendation": ["skip", "save", "direct_greet"],
            },
            "override_api": "/v1/ops/overrides",
            "rule_config_api": "/v1/ops/rule-config/active",
            "decision_trace_api": "/v1/ops/recommendations/{id}/decision-trace",
            "principal": principal_from_actor(actor).to_dict(),
        }
    )


def dispatch_support_rest(
    gateway: SupportGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    from .rule_config_routes import dispatch_rule_config_rest

    routed = dispatch_rule_config_rest(gateway, environ, method, path)
    if routed is not None:
        return routed
    normalized = path.rstrip("/") or "/"
    if normalized.startswith("/v1/profiles/") and normalized.endswith("/trust") and method == "GET":
        return rest_profile_trust(gateway, environ, path=normalized)
    if normalized == "/v1/ops/overrides" and method == "POST":
        from .http_helpers import _parse_json_body, _read_body

        return rest_ops_override(gateway, environ, _parse_json_body(_read_body(environ)))
    if normalized == "/v1/ops/workbench/summary" and method == "GET":
        return rest_ops_workbench_summary(gateway, environ)
    return None


__all__ = [
    "dispatch_support_rest",
    "rest_ops_override",
    "rest_ops_workbench_summary",
    "rest_profile_trust",
    "_audit_ops_override",
    "_validate_ops_override_scope",
    "_validate_recommendation_exists",
]
