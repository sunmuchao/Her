"""Importable API for the partner-search matching engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from her_json_utils import json_safe
from profile_service import get_profile, resolve_profile_source

from . import search_candidates as engine
from .search_cache import get_cached_search_run, store_cached_search_run


@dataclass
class SearchRequest:
    source: str | Sequence[str] | None = None
    criteria: Mapping[str, Any] = field(default_factory=dict)
    self_profile: Mapping[str, Any] | None = None
    self_id: int | None = None
    table_name: str | None = None
    photos_table_name: str | None = None
    limit: int = 10
    photo_preview_count: int = 0
    include_source: bool = False
    moderation_dsn: str | None = None
    include_moderation_blocked: bool = False

    def to_engine_request(self) -> dict[str, Any]:
        return engine.build_search_request(
            source=self.source,
            table_name=self.table_name,
            photos_table_name=self.photos_table_name,
            criteria=dict(self.criteria or {}),
            self_profile=dict(self.self_profile or {}) or None,
            self_id=self.self_id,
            limit=self.limit,
            photo_preview_count=self.photo_preview_count,
            moderation_dsn=self.moderation_dsn,
            include_moderation_blocked=self.include_moderation_blocked,
        )


@dataclass
class SearchResponse:
    search_run: Mapping[str, Any]
    include_source: bool = False

    @property
    def text(self) -> str:
        return engine.render_search_output(
            dict(self.search_run),
            include_source=self.include_source,
        )

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        return engine.build_structured_search_response(
            dict(self.search_run),
            include_source=self.include_source,
            include_text=include_text,
        )

    def to_json(self, include_text: bool = False, ensure_ascii: bool = False, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(include_text=include_text),
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=False,
        )


def search(request: SearchRequest | Mapping[str, Any]) -> SearchResponse:
    if isinstance(request, SearchRequest):
        search_request = request
    else:
        search_request = SearchRequest(
            source=request.get("source") or request.get("sources"),
            criteria=request.get("criteria") or {},
            self_profile=request.get("self_profile"),
            self_id=request.get("self_id"),
            table_name=request.get("table_name"),
            photos_table_name=request.get("photos_table_name"),
            limit=request.get("limit", 10),
            photo_preview_count=request.get("photo_preview_count", 0),
            include_source=bool(request.get("include_source", False)),
            moderation_dsn=request.get("moderation_dsn"),
            include_moderation_blocked=bool(request.get("include_moderation_blocked", False)),
        )

    engine_request = search_request.to_engine_request()
    cached = get_cached_search_run(
        criteria=dict(search_request.criteria or {}),
        self_id=search_request.self_id,
        limit=int(search_request.limit),
        source=str(search_request.source) if search_request.source is not None else None,
    )
    if cached is not None:
        search_run = cached
    else:
        search_run = engine.execute_search_request(engine_request)
        store_cached_search_run(
            criteria=dict(search_request.criteria or {}),
            self_id=search_request.self_id,
            limit=int(search_request.limit),
            source=str(search_request.source) if search_request.source is not None else None,
            search_run=search_run,
        )
    return SearchResponse(
        search_run=search_run,
        include_source=search_request.include_source,
    )


def search_profiles(
    *,
    source: str | Sequence[str] | None,
    criteria: Mapping[str, Any] | None = None,
    self_profile: Mapping[str, Any] | None = None,
    self_id: int | None = None,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    limit: int = 10,
    photo_preview_count: int = 0,
    include_source: bool = False,
    include_text: bool = False,
    moderation_dsn: str | None = None,
    include_moderation_blocked: bool = False,
) -> dict[str, Any]:
    response = search(
        SearchRequest(
            source=source,
            criteria=criteria or {},
            self_profile=self_profile,
            self_id=self_id,
            table_name=table_name,
            photos_table_name=photos_table_name,
            limit=limit,
            photo_preview_count=photo_preview_count,
            include_source=include_source,
            moderation_dsn=moderation_dsn,
            include_moderation_blocked=include_moderation_blocked,
        )
    )
    return response.to_dict(include_text=include_text)


def load_source_profile_record(
    *,
    source: str,
    profile_id: int,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    normalized_source, normalized_table = resolve_profile_source(source, table_name)
    if not normalized_source or not normalized_table:
        return None
    raw_profile = get_profile(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=profile_id,
    )
    return engine.normalize_record(
        {
            **dict(raw_profile),
            "source_file": engine.build_source_file_ref(normalized_source, normalized_table),
        }
    )


def load_self_profile(
    *,
    source: str,
    self_id: int,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    record = load_source_profile_record(
        source=source,
        profile_id=self_id,
        table_name=table_name,
    )
    if record is None:
        records = engine.collect_source_records_for_request(
            [source],
            table_name=table_name,
            criteria={},
            self_id=self_id,
        )
    else:
        records = [record]
    profile = engine.build_self_profile(
        records,
        self_id=self_id,
        profile_input=None,
    )
    return json_safe(profile)


__all__ = [
    "SearchRequest",
    "SearchResponse",
    "load_self_profile",
    "load_source_profile_record",
    "search",
    "search_profiles",
]
