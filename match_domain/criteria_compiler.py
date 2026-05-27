"""Unified effective-criteria compiler (§13.1.2) — collected inputs only."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from her_time_utils import clean_text as _clean_text

from .collected_profile import extract_profile_facts, merge_collected_for_compile
from .onboarding_search import build_profile_search_defaults, normalize_compiled_criteria

LIST_FIELD_KEYS = frozenset(
    {
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
)

SCENE_DISCOVERY_SEARCH = "discovery_search"
SCENE_RECOMMENDATION_REFRESH = "recommendation_refresh"
SCENE_SAVED_SEARCH = "saved_search"


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
        return _unique_ordered([item for item in _as_list(value) if item not in {None, ""}])
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


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def _build_relationship_goals(collected: Mapping[str, Any] | None, fallback: Any) -> list[Any]:
    if not collected:
        return _unique_ordered(_as_list(fallback))
    self_goal = _clean_text(collected.get("self_relationship_goal"))
    if self_goal == "结婚导向":
        return ["结婚导向"]
    if self_goal in {"认真恋爱", "认真相处"}:
        return ["认真恋爱", "结婚导向"]
    if self_goal:
        return [self_goal]
    return _unique_ordered(_as_list(fallback))


def _build_collected_criteria_patch(collected: Mapping[str, Any] | None) -> dict[str, Any]:
    if not collected:
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
        if source_key not in collected:
            continue
        value = collected.get(source_key)
        if target_key in LIST_FIELD_KEYS:
            patch[target_key] = _coerce_criteria_value(value, as_list_value=True)
        else:
            patch[target_key] = _coerce_criteria_value(value)

    relationship_goals = _build_relationship_goals(collected, patch.get("relationship_goals"))
    if relationship_goals:
        patch["relationship_goals"] = relationship_goals
    return patch


def _build_source_map(
    *,
    profile_facts: Mapping[str, Any],
    collected: Mapping[str, Any],
    criteria: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    source_map: dict[str, dict[str, Any]] = {}
    reverse_map = {
        "gender": "target_gender",
        "age_min": "target_age_min",
        "age_max": "target_age_max",
        "cities": "target_cities",
        "height_min": "target_height_min",
        "height_max": "target_height_max",
        "marital_statuses": "target_marital_statuses",
        "accept_partner_children": "target_accept_partner_children",
        "long_distance": "target_accept_long_distance",
        "must_have": "must_have_tags",
        "must_not_have": "must_not_have_tags",
        "prefer": "preferred_traits",
        "relationship_goals": "self_relationship_goal",
    }
    for criteria_key in criteria:
        persona_key = reverse_map.get(criteria_key)
        if persona_key and persona_key in collected:
            source_map[criteria_key] = {
                "source": "explicit_statement",
                "field": persona_key,
            }
        elif criteria_key == "relationship_goals" and collected.get("self_relationship_goal"):
            source_map[criteria_key] = {
                "source": "explicit_statement",
                "field": "self_relationship_goal",
            }
        elif overrides and criteria_key in overrides:
            source_map[criteria_key] = {"source": "explicit_override", "field": criteria_key}
        elif criteria_key == "gender" and profile_facts.get("sexual_orientation"):
            source_map[criteria_key] = {"source": "profile_form", "field": "sexual_orientation"}
        elif criteria_key in build_profile_search_defaults(profile_facts):
            source_map[criteria_key] = {"source": "profile_form", "field": criteria_key}
    return source_map


def _criteria_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _split_criteria(criteria: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    hard_keys = {
        "gender",
        "age_min",
        "age_max",
        "cities",
        "height_min",
        "height_max",
        "marital_statuses",
        "accept_partner_children",
        "long_distance",
        "must_not_have",
        "must_have",
    }
    hard_filters: dict[str, Any] = {}
    soft_preferences: dict[str, Any] = {}
    for key, value in criteria.items():
        if key in hard_keys:
            hard_filters[key] = value
        else:
            soft_preferences[key] = value
    return hard_filters, soft_preferences


def _build_self_profile(
    profile_facts: Mapping[str, Any],
    collected: Mapping[str, Any],
    *,
    fallback_self_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    self_profile = dict(fallback_self_profile or {})
    if profile_facts:
        self_profile.update(profile_facts)
    persona_self = {
        f"self_{key[len('self_'):]}": value
        for key, value in collected.items()
        if key.startswith("self_")
    }
    self_profile.update({k: v for k, v in persona_self.items() if v not in (None, "", [], {})})
    return self_profile


@dataclass
class CompiledCriteria:
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    criteria: dict[str, Any] = field(default_factory=dict)
    self_profile: dict[str, Any] = field(default_factory=dict)
    source_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    criteria_hash: str = ""
    scene: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_initial_request(subscription: Mapping[str, Any]) -> dict[str, Any]:
    initial_request = _json_loads(subscription.get("initial_request_json"), {})
    if initial_request:
        return dict(initial_request)
    return {
        "source": subscription.get("source"),
        "criteria": _json_loads(subscription.get("search_criteria_json"), {}),
        "self_profile": _json_loads(subscription.get("self_profile_json"), None),
        "self_id": subscription.get("self_id"),
        "table_name": subscription.get("table_name"),
        "photos_table_name": subscription.get("photos_table_name"),
        "limit": int(subscription.get("limit_count") or 10),
        "photo_preview_count": 0,
        "include_source": True,
        "include_text": False,
    }


def build_subscription_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = _json_loads(subscription.get("subscription_overrides_json"), {})
    if not isinstance(overrides, Mapping):
        return {}
    filtered = dict(overrides or {})
    filtered.pop("review_policy", None)
    return filtered


def compile_effective_criteria(
    *,
    scene: str,
    profile_row: Mapping[str, Any] | None = None,
    persona_row: Mapping[str, Any] | None = None,
    base_criteria: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
    subscription: Mapping[str, Any] | None = None,
    fallback_self_profile: Mapping[str, Any] | None = None,
) -> CompiledCriteria:
    profile_facts = extract_profile_facts(profile_row or {})
    collected = merge_collected_for_compile(profile_row=profile_row, persona_row=persona_row)

    if subscription is not None:
        initial = build_initial_request(subscription)
        criteria_base = dict(initial.get("criteria") or {})
        subscription_overrides = build_subscription_overrides(subscription)
        fallback_self_profile = fallback_self_profile or initial.get("self_profile")
    else:
        criteria_base = dict(base_criteria or {})
        subscription_overrides = {}

    criteria = _apply_patch(criteria_base, build_profile_search_defaults(profile_row or {}))
    criteria = _apply_patch(criteria, _build_collected_criteria_patch(collected))
    explicit_overrides = dict(overrides or {})
    explicit_overrides.update(subscription_overrides)
    criteria = _apply_patch(criteria, explicit_overrides)
    criteria = normalize_compiled_criteria(criteria)

    hard_filters, soft_preferences = _split_criteria(criteria)
    source_map = _build_source_map(
        profile_facts=profile_facts,
        collected=collected,
        criteria=criteria,
        overrides=explicit_overrides,
    )
    self_profile = _build_self_profile(
        profile_facts,
        collected,
        fallback_self_profile=fallback_self_profile,
    )
    criteria_hash = _criteria_hash(
        {
            "scene": scene,
            "criteria": criteria,
            "self_profile_keys": sorted(self_profile.keys()),
        }
    )
    return CompiledCriteria(
        hard_filters=hard_filters,
        soft_preferences=soft_preferences,
        criteria=criteria,
        self_profile=self_profile,
        source_map=source_map,
        criteria_hash=criteria_hash,
        scene=scene,
    )


def build_effective_search_request(
    subscription: Mapping[str, Any],
    *,
    persona_profile: Mapping[str, Any] | None = None,
    profile_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    initial_request = build_initial_request(subscription)
    compiled = compile_effective_criteria(
        scene=SCENE_RECOMMENDATION_REFRESH,
        profile_row=profile_row,
        persona_row=persona_profile,
        subscription=subscription,
        fallback_self_profile=persona_profile or initial_request.get("self_profile"),
    )
    return {
        "source": initial_request.get("source") or subscription.get("source"),
        "table_name": initial_request.get("table_name") or subscription.get("table_name"),
        "photos_table_name": initial_request.get("photos_table_name") or subscription.get("photos_table_name"),
        "criteria": compiled.criteria,
        "self_profile": compiled.self_profile,
        "compiled": compiled.to_dict(),
        "self_id": initial_request.get("self_id", subscription.get("self_id")),
        "limit": int(initial_request.get("limit") or subscription.get("limit_count") or 10),
        "photo_preview_count": int(initial_request.get("photo_preview_count") or 0),
        "include_source": bool(initial_request.get("include_source", True)),
        "include_text": bool(initial_request.get("include_text", False)),
    }


def build_discovery_search_request(
    *,
    source: str,
    profile_row: Mapping[str, Any] | None,
    persona_row: Mapping[str, Any] | None,
    criteria_overrides: Mapping[str, Any] | None,
    self_id: int | None,
    limit: int,
    table_name: str | None = None,
    photos_table_name: str | None = None,
) -> dict[str, Any]:
    compiled = compile_effective_criteria(
        scene=SCENE_DISCOVERY_SEARCH,
        profile_row=profile_row,
        persona_row=persona_row,
        base_criteria={},
        overrides=criteria_overrides,
        fallback_self_profile=profile_row,
    )
    return {
        "source": source,
        "table_name": table_name,
        "photos_table_name": photos_table_name,
        "criteria": compiled.criteria,
        "self_profile": compiled.self_profile,
        "compiled": compiled.to_dict(),
        "self_id": self_id,
        "limit": limit,
        "photo_preview_count": 3,
        "include_source": False,
    }
