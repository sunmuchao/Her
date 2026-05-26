"""Support-domain read APIs and ops override entry (§13.1.3)."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain.support_contracts import OpsOverride, principal_from_actor
from match_domain.trust_summary import build_trust_summary
from profile_service import get_profile

from .http_helpers import _json_safe, _query_dict
from .identity import ROLE_OPS_OPERATOR, ROLE_PLATFORM_ADMIN, ROLE_RISK_REVIEWER, GatewayPermissionError
from .profile_source_defaults import default_profile_source


class SupportGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(self, actor: Any, roles: set[str]) -> None: ...

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
    return int(match.group(1))


def rest_profile_trust(
    gateway: SupportGateway,
    environ: dict[str, Any],
    *,
    path: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    actor = gateway._current_actor(environ)
    profile_id = _profile_id_from_trust_path(path)
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


def rest_ops_override(
    gateway: SupportGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "authentication required"}}
    try:
        gateway._require_roles(
            actor,
            {ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN},
        )
    except GatewayPermissionError as exc:
        return 403, {"error": {"code": "forbidden", "message": str(exc)}}

    override = OpsOverride(
        target_owner=str(body.get("target_owner") or "").strip(),
        target_id=str(body.get("target_id") or "").strip(),
        action=str(body.get("action") or "").strip(),
        operator_id=str(actor.actor_id),
        reason=(str(body.get("reason")).strip() if body.get("reason") is not None else None),
    )
    if not override.target_owner or not override.target_id or not override.action:
        return 400, {"error": {"code": "invalid_request", "message": "target_owner, target_id, action are required"}}

    if override.target_owner == "recommendation":
        from recommendation_system.service import get_recommendation_by_id, record_user_review  # type: ignore[import-untyped]

        review_type = override.action
        if review_type not in {"skip", "save", "direct_greet"}:
            return 400, {
                "error": {
                    "code": "unsupported_action",
                    "message": "recommendation owner supports skip|save|direct_greet",
                }
            }
        try:
            recommendation_id = int(override.target_id)
        except ValueError:
            return 400, {"error": {"code": "invalid_request", "message": "target_id must be recommendation_id int"}}

        def _apply(conn: Any) -> dict[str, Any]:
            recommendation = get_recommendation_by_id(conn, recommendation_id)
            if not recommendation:
                raise ValueError(f"Unknown recommendation_id={recommendation_id}")
            return record_user_review(
                conn,
                subscription_id=str(recommendation["subscription_id"]),
                candidate_id=int(recommendation["candidate_id"]),
                review_type=review_type,
                actor_id=override.operator_id,
                review_payload={"ops_override": True, "reason": override.reason},
            )

        try:
            result = gateway._with_rec(_apply)
        except ValueError as exc:
            return 404, {"error": {"code": "not_found", "message": str(exc)}}
        return 200, _json_safe({"ok": True, "override": override.to_dict(), "result": result})

    return 400, {
        "error": {
            "code": "unsupported_target_owner",
            "message": f"target_owner {override.target_owner!r} is not supported yet",
        }
    }


def rest_ops_workbench_summary(
    gateway: SupportGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "authentication required"}}
    try:
        gateway._require_roles(
            actor,
            {ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN},
        )
    except GatewayPermissionError as exc:
        return 403, {"error": {"code": "forbidden", "message": str(exc)}}

    q = _query_dict(environ)
    try:
        limit = max(int(q.get("limit", 5)), 1)
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
]
