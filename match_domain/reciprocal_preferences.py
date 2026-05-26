"""Map collected persona preferences onto legacy reciprocal profile keys."""

from __future__ import annotations

from typing import Any, Mapping

from .deprecated_profile_columns import (
    COLLECTED_TO_RECIPROCAL_PROFILE_ALIASES,
    PROFILE_PREFERENCE_TO_PERSONA,
)


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def enrich_record_for_reciprocal(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fill legacy `preferred_*` / `accept_*` keys from `target_*` when profile columns are dropped."""
    if not record:
        return {}
    enriched = dict(record)
    for legacy_key, collected_key in COLLECTED_TO_RECIPROCAL_PROFILE_ALIASES.items():
        if _has_value(enriched.get(legacy_key)):
            continue
        collected_value = enriched.get(collected_key)
        if _has_value(collected_value):
            enriched[legacy_key] = collected_value

    for legacy_key, collected_key in PROFILE_PREFERENCE_TO_PERSONA.items():
        if _has_value(enriched.get(collected_key)):
            continue
        legacy_value = enriched.get(legacy_key)
        if _has_value(legacy_value):
            enriched[collected_key] = legacy_value

    for legacy_key, collected_key in COLLECTED_TO_RECIPROCAL_PROFILE_ALIASES.items():
        if legacy_key in PROFILE_PREFERENCE_TO_PERSONA:
            continue
        if _has_value(enriched.get(collected_key)):
            continue
        legacy_value = enriched.get(legacy_key)
        if _has_value(legacy_value):
            enriched[collected_key] = legacy_value

    if not _has_value(enriched.get("matcher_preferences")) and not _has_value(
        enriched.get("matcher_preferences_json")
    ):
        tags: dict[str, Any] = {}
        if _has_value(enriched.get("must_have_tags")):
            tags["must_have_tags"] = enriched.get("must_have_tags")
        if _has_value(enriched.get("preferred_traits")):
            tags["preferred_traits"] = enriched.get("preferred_traits")
        if _has_value(enriched.get("target_gender")):
            tags["target_gender"] = enriched.get("target_gender")
        if tags:
            enriched["matcher_preferences"] = tags

    if not _has_value(enriched.get("matcher_risks")) and not _has_value(enriched.get("matcher_risks_json")):
        risks: dict[str, Any] = {}
        if _has_value(enriched.get("must_not_have_tags")):
            risks["must_not_have_tags"] = enriched.get("must_not_have_tags")
        if _has_value(enriched.get("disliked_traits")):
            risks["disliked_traits"] = enriched.get("disliked_traits")
        if risks:
            enriched["matcher_risks"] = risks

    return enriched


def merge_persona_into_profile_record(
    profile_row: Mapping[str, Any],
    persona_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(profile_row)
    if persona_row:
        for key, value in persona_row.items():
            if key in {"id", "profile_id", "user_key", "created_at", "updated_at"}:
                continue
            if _has_value(value):
                merged[key] = value
    return enrich_record_for_reciprocal(merged)


__all__ = [
    "enrich_record_for_reciprocal",
    "merge_persona_into_profile_record",
]
