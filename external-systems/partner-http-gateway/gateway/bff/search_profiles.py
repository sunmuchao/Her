"""POST /v1/search/profiles — search with external visibility gate."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain.search_self_profile import prepare_gateway_search_body
from match_domain.search_visibility import search_profiles_with_visibility_gate
from partner_search import search_profiles as partner_search_profiles
from profile_source_refs import resolve_profile_source

from ..http_helpers import _json_safe, _normalize_boolish
from ..profile_source_defaults import default_profile_source


class SearchProfilesGateway(Protocol):
    @property
    def _chat_dsn(self) -> str: ...


def rest_search_profiles(
    gateway: SearchProfilesGateway,
    _environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    source = body.get("source") or body.get("sources")
    if not source:
        raise ValueError("source or sources is required")
    if isinstance(source, list):
        source = source[0] if source else None
    try:
        profile_dsn, profile_table = resolve_profile_source(str(source))
    except ValueError:
        profile_dsn, profile_table = default_profile_source()
    prepared = prepare_gateway_search_body(
        body,
        profile_source_dsn=profile_dsn,
        profile_table_name=profile_table,
    )
    kwargs = prepared["search_kwargs"]
    response = search_profiles_with_visibility_gate(
        partner_search_profiles,
        source=kwargs["source"],
        criteria=kwargs["criteria"],
        self_profile=kwargs["self_profile"],
        self_id=kwargs["self_id"],
        table_name=kwargs["table_name"],
        photos_table_name=kwargs["photos_table_name"],
        limit=int(kwargs["limit"]),
        photo_preview_count=int(kwargs["photo_preview_count"]),
        include_source=_normalize_boolish(kwargs.get("include_source"), False),
        include_text=_normalize_boolish(kwargs.get("include_text"), False),
        moderation_dsn=gateway._chat_dsn,
        include_moderation_blocked=_normalize_boolish(kwargs.get("include_moderation_blocked"), False),
    )
    payload = _json_safe(response)
    if prepared.get("deprecation"):
        payload["_deprecation"] = prepared["deprecation"]
    return 200, payload


__all__ = ["rest_search_profiles"]
