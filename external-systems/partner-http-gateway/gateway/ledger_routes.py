"""Relationship ledger read APIs for the gateway."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from relationship_ledger import (  # type: ignore[import-untyped]
    build_cross_system_funnel_dashboard,
    build_relation_dashboard,
    build_unified_timeline_from_ledger,
    get_relation_by_key,
    list_relations,
    list_relations_for_profile_refs,
    summarize_ledger_relation_for_timeline,
)
from relationship_ledger.runtime import ledger_read_mode  # type: ignore[import-untyped]

from .http_helpers import _json_safe, _query_dict
from .role_sets import INTERNAL_WRITE_ROLES


class LedgerGateway(Protocol):
    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _assert_actor_can_access_ledger_relation(
        self,
        environ: dict[str, Any],
        relation: dict[str, Any],
    ) -> None: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _is_auth_session_end_user(self, actor: Any) -> bool: ...

    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _with_ledger(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def rest_get_relation(
    gateway: LedgerGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    relation_key = unquote(str(q.get("relation_key") or "").strip())
    if not relation_key:
        raise ValueError("relation_key query parameter is required")
    relation = gateway._with_ledger(get_relation_by_key, relation_key)
    if not relation:
        return 404, {"error": {"code": "not_found", "message": "relation not found"}}
    gateway._assert_actor_can_access_ledger_relation(environ, relation)
    return 200, {
        "relation": _json_safe(relation),
        "summary": _json_safe(summarize_ledger_relation_for_timeline(relation)),
        "unified_timeline": _json_safe(build_unified_timeline_from_ledger(relation)),
        "trace_id": get_trace_id(),
    }


def rest_list_relations_mine(
    gateway: LedgerGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None or not gateway._is_auth_session_end_user(actor):
        raise ValueError("authenticated end-user session is required")
    profile_id = gateway._resolve_end_user_principal(environ, require_profile=True).profile_id
    profile_ref = f"profile:{profile_id}"
    relations = gateway._with_ledger(list_relations_for_profile_refs, [profile_ref])
    return 200, {
        "profile_ref": profile_ref,
        "relations": _json_safe(relations),
        "count": len(relations),
        "read_mode": ledger_read_mode(),
        "trace_id": get_trace_id(),
    }


def rest_list_relations(
    gateway: LedgerGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot list ledger relations",
    )
    relations = gateway._with_ledger(list_relations)
    return 200, {
        "relations": _json_safe(relations),
        "count": len(relations),
        "trace_id": get_trace_id(),
    }


def rest_ledger_dashboard(
    gateway: LedgerGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect ledger dashboard",
    )
    dashboard = gateway._with_ledger(build_relation_dashboard)
    funnel = gateway._with_ledger(build_cross_system_funnel_dashboard)
    return 200, {
        "ledger": _json_safe(dashboard),
        "funnel": _json_safe(funnel),
        "trace_id": get_trace_id(),
    }


def dispatch_ledger_rest(
    gateway: LedgerGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/relations" and method == "GET":
        return rest_get_relation(gateway, environ)
    if path == "/v1/relations/mine" and method == "GET":
        return rest_list_relations_mine(gateway, environ)
    if path == "/v1/relations/list" and method == "GET":
        return rest_list_relations(gateway, environ)
    if path == "/v1/relations/dashboard" and method == "GET":
        return rest_ledger_dashboard(gateway, environ)
    return None
