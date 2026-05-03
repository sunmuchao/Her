"""Compile effective search criteria from persona-driven subscription state."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .storage import json_loads


LIST_FIELD_KEYS = {
    "cities",
    "districts",
    "settlement_cities",
    "relationship_goals",
    "must_have",
    "must_not_have",
    "prefer",
    "housing_statuses",
    "car_statuses",
    "marital_statuses",
    "marriage_timelines",
    "profile_statuses",
    "verified_levels",
    "required_known_fields",
    "exclude_source_channels",
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, tuple):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, set):
        return [item for item in value if item not in {None, ""}]
    if isinstance(value, str):
        parts = re.split(r"[，,、/|]+", value)
        return [part.strip() for part in parts if part.strip()]
    return [value]


def _unique_ordered(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    ordered: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _coerce_criteria_value(value: Any, *, as_list_value: bool = False) -> Any:
    if as_list_value:
        coerced = _unique_ordered([item for item in _as_list(value) if item not in {None, ""}])
        return coerced
    if value is None or value == "":
        return None
    return value


def _apply_patch(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    updated = dict(base)
    for key, value in patch.items():
        if value is None or value == "" or value == [] or value == {}:
            updated.pop(key, None)
            continue
        if key in LIST_FIELD_KEYS:
            updated[key] = _coerce_criteria_value(value, as_list_value=True)
        else:
            updated[key] = value
    return updated


def _build_relationship_goals(persona_profile: Mapping[str, Any] | None, fallback: Any) -> list[Any]:
    if not persona_profile:
        return _unique_ordered(_as_list(fallback))

    self_goal = _clean_text(persona_profile.get("self_relationship_goal"))
    if self_goal == "结婚导向":
        return ["结婚导向"]
    if self_goal in {"认真恋爱", "认真相处"}:
        return ["认真恋爱", "结婚导向"]
    if self_goal:
        return [self_goal]
    return _unique_ordered(_as_list(fallback))


def _build_persona_criteria_patch(persona_profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not persona_profile:
        return {}

    patch: dict[str, Any] = {}
    field_map = {
        "gender": "target_gender",
        "age_min": "target_age_min",
        "age_max": "target_age_max",
        "cities": "target_cities",
        "height_min": "target_height_min",
        "height_max": "target_height_max",
        "marital_statuses": "target_marital_statuses",
        "accept_marital_status_strength": "target_marital_status_strength",
        "accept_partner_children": "target_accept_partner_children",
        "accept_partner_children_strength": "target_accept_partner_children_strength",
        "long_distance": "target_accept_long_distance",
        "want_children": "target_want_children",
        "marriage_timelines": "target_marriage_timeline",
        "must_have": "must_have_tags",
        "must_not_have": "must_not_have_tags",
        "prefer": "preferred_traits",
    }

    for target_key, source_key in field_map.items():
        if source_key not in persona_profile:
            continue
        value = persona_profile.get(source_key)
        if target_key in LIST_FIELD_KEYS:
            coerced = _coerce_criteria_value(value, as_list_value=True)
            patch[target_key] = coerced
        else:
            coerced = _coerce_criteria_value(value)
            patch[target_key] = coerced

    relationship_goals = _build_relationship_goals(persona_profile, patch.get("relationship_goals"))
    if relationship_goals:
        patch["relationship_goals"] = relationship_goals

    return patch


def build_initial_request(subscription: Mapping[str, Any]) -> dict[str, Any]:
    initial_request = json_loads(subscription.get("initial_request_json"), {})
    if initial_request:
        return dict(initial_request)
    return {
        "source": subscription.get("source"),
        "criteria": json_loads(subscription.get("search_criteria_json"), {}),
        "self_profile": json_loads(subscription.get("self_profile_json"), None),
        "self_id": subscription.get("self_id"),
        "table_name": subscription.get("table_name"),
        "photos_table_name": subscription.get("photos_table_name"),
        "limit": int(subscription.get("limit_count") or 10),
        "photo_preview_count": 0,
        "include_source": True,
        "include_text": False,
    }


def build_subscription_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = json_loads(subscription.get("subscription_overrides_json"), {})
    return dict(overrides or {})


def compile_effective_criteria(
    subscription: Mapping[str, Any],
    persona_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    initial_request = build_initial_request(subscription)
    base_criteria = dict(initial_request.get("criteria") or {})
    criteria = _apply_patch(base_criteria, _build_persona_criteria_patch(persona_profile))
    return _apply_patch(criteria, build_subscription_overrides(subscription))


def build_effective_search_request(
    subscription: Mapping[str, Any],
    *,
    persona_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    initial_request = build_initial_request(subscription)
    effective_criteria = compile_effective_criteria(subscription, persona_profile=persona_profile)
    request = {
        "source": initial_request.get("source") or subscription.get("source"),
        "table_name": initial_request.get("table_name") or subscription.get("table_name"),
        "photos_table_name": initial_request.get("photos_table_name") or subscription.get("photos_table_name"),
        "criteria": effective_criteria,
        "self_profile": dict(persona_profile or {}) or initial_request.get("self_profile") or json_loads(subscription.get("self_profile_json"), None),
        "self_id": initial_request.get("self_id", subscription.get("self_id")),
        "limit": int(initial_request.get("limit") or subscription.get("limit_count") or 10),
        "photo_preview_count": int(initial_request.get("photo_preview_count") or 0),
        "include_source": bool(initial_request.get("include_source", True)),
        "include_text": bool(initial_request.get("include_text", False)),
    }
    return request
