"""Ops rule-config API routes (§13.5)."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain.experiment_bucket import (
    delete_experiment_bucket_member,
    list_experiment_bucket_members,
    upsert_experiment_bucket_member,
)
from match_domain.rule_config_store import (
    STATUS_DRAFT,
    activate_version,
    create_assignment,
    create_version,
    list_active_global_configs,
    list_versions,
)
from match_domain.rule_decision_trace import build_recommendation_decision_trace

from .http_helpers import _json_safe, _query_dict
from .identity import ROLE_OPS_OPERATOR, ROLE_PLATFORM_ADMIN, ROLE_RISK_REVIEWER, GatewayPermissionError


class RuleConfigGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(self, environ: dict[str, Any], roles: set[str]) -> None: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _require_ops_actor(gateway: RuleConfigGateway, environ: dict[str, Any]) -> tuple[Any | None, tuple[int, dict[str, Any]] | None]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return None, (401, {"error": {"code": "unauthorized", "message": "authentication required"}})
    try:
        gateway._require_roles(
            environ,
            {ROLE_OPS_OPERATOR, ROLE_RISK_REVIEWER, ROLE_PLATFORM_ADMIN},
        )
    except GatewayPermissionError as exc:
        return None, (403, {"error": {"code": "forbidden", "message": str(exc)}})
    return actor, None


def rest_ops_rule_config_active(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    _, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err

    def _load(conn: Any) -> dict[str, Any]:
        return {"active": list_active_global_configs(conn)}

    return 200, _json_safe(gateway._with_rec(_load))


def rest_ops_rule_config_versions(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    _, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    q = _query_dict(environ)
    slice_id = str(q.get("slice_id") or "").strip() or None
    try:
        limit = max(int(q.get("limit", 50)), 1)
    except ValueError:
        limit = 50

    def _load(conn: Any) -> dict[str, Any]:
        return {"versions": list_versions(conn, slice_id=slice_id, limit=limit)}

    return 200, _json_safe(gateway._with_rec(_load))


def rest_ops_rule_config_create_version(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    slice_id = str(body.get("slice_id") or "").strip()
    version_id = str(body.get("version_id") or "").strip()
    params = body.get("params")
    if not slice_id or not version_id or not isinstance(params, dict):
        return 400, {
            "error": {
                "code": "invalid_request",
                "message": "slice_id, version_id, params object are required",
            }
        }

    def _create(conn: Any) -> dict[str, Any]:
        version = create_version(
            conn,
            version_id=version_id,
            slice_id=slice_id,
            params=params,
            schema_version=str(body.get("schema_version") or "1"),
            status=STATUS_DRAFT,
            created_by=str(actor.actor_id),
        )
        conn.commit()
        return {"version": version}

    return 201, _json_safe(gateway._with_rec(_create))


def rest_ops_rule_config_activate_version(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    *,
    version_id: str,
) -> tuple[int, dict[str, Any]]:
    actor, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err

    def _activate(conn: Any) -> dict[str, Any]:
        version = activate_version(conn, version_id, operator_id=str(actor.actor_id))
        return {"version": version}

    try:
        return 200, _json_safe(gateway._with_rec(_activate))
    except ValueError as exc:
        return 404, {"error": {"code": "not_found", "message": str(exc)}}


def rest_ops_rule_config_create_assignment(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    assignment_id = str(body.get("assignment_id") or "").strip()
    version_id = str(body.get("version_id") or "").strip()
    slice_id = str(body.get("slice_id") or "").strip()
    scope_type = str(body.get("scope_type") or "").strip()
    scope_key = str(body.get("scope_key") or "").strip()
    if not all([assignment_id, version_id, slice_id, scope_type, scope_key]):
        return 400, {
            "error": {
                "code": "invalid_request",
                "message": "assignment_id, version_id, slice_id, scope_type, scope_key are required",
            }
        }

    def _create(conn: Any) -> dict[str, Any]:
        assignment = create_assignment(
            conn,
            assignment_id=assignment_id,
            version_id=version_id,
            slice_id=slice_id,
            scope_type=scope_type,
            scope_key=scope_key,
            priority=int(body.get("priority") or 0),
            created_by=str(actor.actor_id),
        )
        conn.commit()
        return {"assignment": assignment}

    return 201, _json_safe(gateway._with_rec(_create))


def rest_ops_rule_config_experiment_members(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    _, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    q = _query_dict(environ)
    try:
        limit = max(int(q.get("limit", 100)), 1)
    except ValueError:
        limit = 100

    def _load(conn: Any) -> dict[str, Any]:
        return {"members": list_experiment_bucket_members(conn, limit=limit)}

    return 200, _json_safe(gateway._with_rec(_load))


def rest_ops_rule_config_upsert_experiment_member(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    try:
        profile_id = int(body.get("profile_id"))
    except (TypeError, ValueError):
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}
    bucket_key = str(body.get("bucket_key") or "").strip()
    if not bucket_key:
        return 400, {"error": {"code": "invalid_request", "message": "bucket_key is required"}}

    def _upsert(conn: Any) -> dict[str, Any]:
        member = upsert_experiment_bucket_member(
            conn,
            profile_id=profile_id,
            bucket_key=bucket_key,
            updated_by=str(actor.actor_id),
        )
        conn.commit()
        return {"member": member}

    return 200, _json_safe(gateway._with_rec(_upsert))


def rest_ops_rule_config_delete_experiment_member(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    *,
    profile_id: int,
) -> tuple[int, dict[str, Any]]:
    _, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err

    def _delete(conn: Any) -> dict[str, Any]:
        removed = delete_experiment_bucket_member(conn, profile_id)
        conn.commit()
        return {"removed": removed, "profile_id": profile_id}

    return 200, _json_safe(gateway._with_rec(_delete))


def rest_ops_recommendation_decision_trace(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    *,
    recommendation_id: int,
) -> tuple[int, dict[str, Any]]:
    _, err = _require_ops_actor(gateway, environ)
    if err is not None:
        return err
    from recommendation_system.service import get_recommendation_by_id  # type: ignore[import-untyped]

    def _load(conn: Any) -> dict[str, Any]:
        recommendation = get_recommendation_by_id(conn, recommendation_id)
        if not recommendation:
            raise ValueError(f"Unknown recommendation_id={recommendation_id}")
        return {"decision_trace": build_recommendation_decision_trace(recommendation)}

    try:
        return 200, _json_safe(gateway._with_rec(_load))
    except ValueError as exc:
        return 404, {"error": {"code": "not_found", "message": str(exc)}}


def dispatch_rule_config_rest(
    gateway: RuleConfigGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    normalized = path.rstrip("/") or "/"
    if normalized == "/v1/ops/rule-config/active" and method == "GET":
        return rest_ops_rule_config_active(gateway, environ)
    if normalized == "/v1/ops/rule-config/versions" and method == "GET":
        return rest_ops_rule_config_versions(gateway, environ)
    if normalized == "/v1/ops/rule-config/versions" and method == "POST":
        from .http_helpers import _parse_json_body, _read_body

        return rest_ops_rule_config_create_version(gateway, environ, _parse_json_body(_read_body(environ)))
    activate_match = re.fullmatch(r"/v1/ops/rule-config/versions/([^/]+)/activate", normalized)
    if activate_match and method == "POST":
        return rest_ops_rule_config_activate_version(
            gateway,
            environ,
            version_id=activate_match.group(1),
        )
    if normalized == "/v1/ops/rule-config/assignments" and method == "POST":
        from .http_helpers import _parse_json_body, _read_body

        return rest_ops_rule_config_create_assignment(gateway, environ, _parse_json_body(_read_body(environ)))
    if normalized == "/v1/ops/rule-config/experiment-members" and method == "GET":
        return rest_ops_rule_config_experiment_members(gateway, environ)
    if normalized == "/v1/ops/rule-config/experiment-members" and method == "POST":
        from .http_helpers import _parse_json_body, _read_body

        return rest_ops_rule_config_upsert_experiment_member(
            gateway, environ, _parse_json_body(_read_body(environ))
        )
    delete_member_match = re.fullmatch(r"/v1/ops/rule-config/experiment-members/(\d+)", normalized)
    if delete_member_match and method == "DELETE":
        return rest_ops_rule_config_delete_experiment_member(
            gateway,
            environ,
            profile_id=int(delete_member_match.group(1)),
        )
    trace_match = re.fullmatch(r"/v1/ops/recommendations/(\d+)/decision-trace", normalized)
    if trace_match and method == "GET":
        return rest_ops_recommendation_decision_trace(
            gateway,
            environ,
            recommendation_id=int(trace_match.group(1)),
        )
    return None


__all__ = [
    "dispatch_rule_config_rest",
    "rest_ops_recommendation_decision_trace",
    "rest_ops_rule_config_active",
    "rest_ops_rule_config_activate_version",
    "rest_ops_rule_config_create_assignment",
    "rest_ops_rule_config_create_version",
    "rest_ops_rule_config_delete_experiment_member",
    "rest_ops_rule_config_experiment_members",
    "rest_ops_rule_config_upsert_experiment_member",
    "rest_ops_rule_config_versions",
]
