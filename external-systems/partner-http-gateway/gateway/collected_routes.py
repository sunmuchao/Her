"""Profile facts and collected-statement read APIs (§13.1.2)."""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

from match_domain.collected_profile import extract_collected_statements, extract_profile_facts
from match_domain.collected_metadata import build_collected_items
from match_domain.criteria_snapshots import get_criteria_snapshot_store, snapshot_to_dict
from match_domain.persona_loader import load_collected_bundle
from profile_service import get_profile

from .http_helpers import _json_safe, _query_dict
from .recommendation_access import resolve_optional_profile_id


class CollectedGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _is_auth_session_end_user(self, actor: Any) -> bool: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _get_recommendation_for_actor(
        self,
        environ: dict[str, Any],
        recommendation_id: int,
    ) -> dict[str, Any]: ...


def _default_profile_source() -> str:
    for name in (
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _parse_profile_source(source: str) -> tuple[str, str | None]:
    from profile_service import resolve_profile_source

    normalized_source, table_name = resolve_profile_source(source, None)
    return normalized_source or source, table_name


def rest_profile_me(gateway: CollectedGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    actor = gateway._current_actor(environ)
    profile_id: int | None = None
    if actor is not None and getattr(gateway, "_is_auth_session_end_user", lambda _a: False)(actor):
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        profile_id = int(resolved.profile_id) if resolved is not None and resolved.profile_id is not None else None
    elif q.get("profile_id") not in (None, ""):
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            q.get("profile_id"),
            field_name="profile_id",
        )
    if profile_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}
    source = (q.get("source") or _default_profile_source()).strip()
    if not source:
        return 503, {"error": {"code": "profile_source_not_configured", "message": "profile source is not configured"}}
    normalized_source, table_name = _parse_profile_source(source)
    row = get_profile(
        source_dsn=normalized_source,
        source_table_name=table_name or "profiles",
        profile_id=int(profile_id),
    )
    if not row:
        return 404, {"error": {"code": "not_found", "message": "profile not found"}}
    return 200, {"profile_id": int(profile_id), "profile_facts": _json_safe(extract_profile_facts(row))}


def rest_persona_collected(gateway: CollectedGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    profile_id = resolve_optional_profile_id(
        gateway,
        environ,
        q.get("profile_id"),
        raw_requester_id=q.get("requester_id"),
        raw_user_key=q.get("user_key"),
        treat_empty_as_missing=True,
    )
    if profile_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}
    source = (q.get("source") or _default_profile_source()).strip()
    if not source:
        return 503, {"error": {"code": "persona_source_not_configured", "message": "persona source is not configured"}}
    bundle = load_collected_bundle(source=source, user_key=str(profile_id))
    persona = bundle.get("persona") or {}
    collected_items = bundle.get("collected_items") or build_collected_items(
        persona,
        bundle.get("observations") or [],
    )
    flat_statements = extract_collected_statements(persona)
    return 200, {
        "profile_id": int(profile_id),
        "user_key": str(profile_id),
        "collected_statements": _json_safe(flat_statements),
        "collected_items": _json_safe(collected_items),
    }


def rest_recommendation_explain(
    gateway: CollectedGateway,
    environ: dict[str, Any],
    recommendation_id: int,
) -> tuple[int, dict[str, Any]]:
    recommendation = gateway._get_recommendation_for_actor(environ, int(recommendation_id))
    store = get_criteria_snapshot_store()
    snapshot = store.get_latest_for_recommendation(int(recommendation_id))
    if snapshot is None:
        provenance = dict(recommendation.get("rule_provenance") or {})
        source_map = provenance.get("source_map") or {}
        if not source_map:
            return 404, {
                "error": {
                    "code": "explain_unavailable",
                    "message": "no criteria snapshot or source_map for this recommendation",
                }
            }
        return 200, {
            "recommendation_id": int(recommendation_id),
            "source_map": _json_safe(source_map),
            "runtime_explanation": provenance.get("runtime_explanation"),
        }
    payload = snapshot_to_dict(snapshot)
    return 200, {
        "recommendation_id": int(recommendation_id),
        "source_map": _json_safe(payload.get("source_map") or {}),
        "compiled": _json_safe(payload.get("compiled") or {}),
        "runtime_explanation": _json_safe(payload.get("runtime_explanation")),
        "snapshot_id": payload.get("snapshot_id"),
        "created_at": payload.get("created_at"),
    }


def dispatch_collected_rest(
    gateway: CollectedGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/profile/me" and method == "GET":
        return rest_profile_me(gateway, environ)
    if path == "/v1/persona/collected" and method == "GET":
        return rest_persona_collected(gateway, environ)
    match = re.fullmatch(r"/v1/recommendations/([^/]+)/explain", path)
    if match and method == "GET":
        return rest_recommendation_explain(gateway, environ, int(match.group(1)))
    return None


__all__ = [
    "dispatch_collected_rest",
    "rest_persona_collected",
    "rest_profile_me",
    "rest_recommendation_explain",
]
