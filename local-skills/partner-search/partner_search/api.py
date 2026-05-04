"""Importable API for the partner-search matching engine."""

from __future__ import annotations

import json
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from scripts import search_candidates as engine


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


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return value


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _first_defined(*values: Any) -> Any:
    for value in values:
        if _has_value(value):
            return value
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


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
        )

    return SearchResponse(
        search_run=engine.execute_search_request(search_request.to_engine_request()),
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
        )
    )
    return response.to_dict(include_text=include_text)


def load_self_profile(
    *,
    source: str,
    self_id: int,
    table_name: str | None = None,
) -> dict[str, Any] | None:
    records = engine.collect_source_records_for_request(
        [source],
        table_name=table_name,
        criteria={},
        self_id=self_id,
    )
    profile = engine.build_self_profile(
        records,
        self_id=self_id,
        profile_input=None,
    )
    return _json_safe_value(profile)


def normalize_persona_profile(
    profile: Mapping[str, Any] | None,
    *,
    fallback_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not profile and not fallback_profile:
        return None

    raw_profile = dict(profile or {})
    normalized = dict(fallback_profile or {})
    normalized.update(raw_profile)

    matcher_preferences = _as_mapping(raw_profile.get("matcher_preferences"))
    matcher_risks = _as_mapping(raw_profile.get("matcher_risks"))

    persona_fields = {
        "self_gender": raw_profile.get("gender"),
        "self_age": raw_profile.get("age"),
        "self_city": raw_profile.get("city"),
        "self_district": raw_profile.get("district"),
        "self_height": raw_profile.get("height"),
        "self_education": raw_profile.get("education"),
        "self_job": raw_profile.get("job"),
        "self_marital_status": raw_profile.get("marital_status"),
        "self_has_children": raw_profile.get("has_children"),
        "self_children_count": raw_profile.get("children_count"),
        "self_children_living_with_self": raw_profile.get("children_living_with_self"),
        "self_smoking": raw_profile.get("smoking"),
        "self_drinking": raw_profile.get("drinking"),
        "self_relationship_goal": raw_profile.get("relationship_goal"),
        "target_gender": _first_defined(
            matcher_preferences.get("target_gender"),
            raw_profile.get("target_gender"),
        ),
        "target_age_min": _first_defined(
            raw_profile.get("preferred_age_min"),
            matcher_preferences.get("target_age_min"),
            raw_profile.get("target_age_min"),
        ),
        "target_age_max": _first_defined(
            raw_profile.get("preferred_age_max"),
            matcher_preferences.get("target_age_max"),
            raw_profile.get("target_age_max"),
        ),
        "target_cities": _first_defined(
            matcher_preferences.get("target_cities"),
            raw_profile.get("preferred_cities"),
            raw_profile.get("target_cities"),
        ),
        "target_height_min": _first_defined(
            raw_profile.get("preferred_height_min"),
            matcher_preferences.get("target_height_min"),
            raw_profile.get("target_height_min"),
        ),
        "target_height_max": _first_defined(
            raw_profile.get("preferred_height_max"),
            matcher_preferences.get("target_height_max"),
            raw_profile.get("target_height_max"),
        ),
        "target_education_min": _first_defined(
            raw_profile.get("preferred_education_min"),
            matcher_preferences.get("target_education_min"),
            raw_profile.get("target_education_min"),
        ),
        "target_income_min_wan": _first_defined(
            raw_profile.get("preferred_income_min_wan"),
            matcher_preferences.get("target_income_min_wan"),
            raw_profile.get("target_income_min_wan"),
        ),
        "target_income_max_wan": _first_defined(
            raw_profile.get("preferred_income_max_wan"),
            matcher_preferences.get("target_income_max_wan"),
            raw_profile.get("target_income_max_wan"),
        ),
        "target_marital_statuses": _first_defined(
            matcher_preferences.get("target_marital_statuses"),
            raw_profile.get("accept_marital_status"),
            raw_profile.get("target_marital_statuses"),
        ),
        "target_marital_status_strength": _first_defined(
            matcher_preferences.get("target_marital_status_strength"),
            raw_profile.get("accept_marital_status_strength"),
            raw_profile.get("target_marital_status_strength"),
        ),
        "target_accept_partner_children": _first_defined(
            matcher_preferences.get("target_accept_partner_children"),
            raw_profile.get("accept_partner_children"),
            raw_profile.get("target_accept_partner_children"),
        ),
        "target_accept_partner_children_strength": _first_defined(
            matcher_preferences.get("target_accept_partner_children_strength"),
            raw_profile.get("accept_partner_children_strength"),
            raw_profile.get("target_accept_partner_children_strength"),
        ),
        "target_accept_long_distance": _first_defined(
            matcher_preferences.get("target_accept_long_distance"),
            raw_profile.get("accept_long_distance"),
            raw_profile.get("long_distance"),
            raw_profile.get("target_accept_long_distance"),
        ),
        "target_location_semantics": _first_defined(
            matcher_preferences.get("target_location_semantics"),
            raw_profile.get("location_preference_semantics"),
            raw_profile.get("target_location_semantics"),
        ),
        "target_requires_partner_accept_my_children": _first_defined(
            matcher_preferences.get("target_requires_partner_accept_my_children"),
            raw_profile.get("requires_partner_accept_my_children"),
            raw_profile.get("target_requires_partner_accept_my_children"),
        ),
        "target_want_children": _first_defined(
            matcher_preferences.get("target_want_children"),
            raw_profile.get("target_want_children"),
        ),
        "target_marriage_timeline": _first_defined(
            matcher_preferences.get("target_marriage_timeline"),
            raw_profile.get("target_marriage_timeline"),
        ),
        "must_have_tags": _first_defined(
            matcher_preferences.get("must_have_tags"),
            raw_profile.get("must_have_tags"),
        ),
        "must_not_have_tags": _first_defined(
            matcher_risks.get("must_not_have_tags"),
            raw_profile.get("must_not_have_tags"),
        ),
        "preferred_traits": _first_defined(
            matcher_preferences.get("preferred_traits"),
            raw_profile.get("preferred_traits"),
        ),
        "disliked_traits": _first_defined(
            matcher_risks.get("disliked_traits"),
            raw_profile.get("disliked_traits"),
        ),
    }
    for key, value in persona_fields.items():
        if _has_value(value):
            normalized[key] = value

    return _json_safe_value(normalized)
