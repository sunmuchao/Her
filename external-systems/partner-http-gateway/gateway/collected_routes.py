"""Profile facts and collected-statement read APIs (§13.1.2)."""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

from match_domain.collected_profile import extract_collected_statements, extract_profile_facts
from match_domain.collected_metadata import build_collected_items
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

    # 暂时禁用 profile API，避免数据库连接数爆炸
    # TODO: 修复 profile_service 使用连接池
    return 503, {"error": {"code": "service_temporarily_disabled", "message": "profile API 暂时禁用，等待修复"}}


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

    # 暂时禁用 persona API，避免数据库连接数爆炸
    # TODO: 修复 persona_service 使用连接池
    return 503, {"error": {"code": "service_temporarily_disabled", "message": "persona API 暂时禁用，等待修复"}}


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
    return None


__all__ = [
    "dispatch_collected_rest",
    "rest_persona_collected",
    "rest_profile_me",
]
