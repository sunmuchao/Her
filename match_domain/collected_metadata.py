"""Collected statement metadata from persona observations (§13.1.2)."""

from __future__ import annotations

from typing import Any, Mapping

from .collected_profile import (
    COLLECTED_PERSONA_FIELDS,
    INFERENCE_ONLY_PERSONA_FIELDS,
    PERSISTABLE_SOURCE_TYPES,
    extract_collected_statements,
)

TAG_FIELDS_REQUIRING_EXPLICIT_OBS = frozenset(
    {
        "must_have_tags",
        "must_not_have_tags",
        "preferred_traits",
        "disliked_traits",
    }
)

_BASIS_TO_SOURCE_CHANNEL = {
    "discovery_agent": "matchmaker_chat",
    "profile_form": "profile_form",
    "explicit_confirmation": "profile_form",
    "candidate_chat": "candidate_chat",
    "matchmaker_chat": "matchmaker_chat",
}


def infer_source_channel(
    *,
    conversation_ref: str | None = None,
    basis: str | None = None,
    explicit_source_channel: str | None = None,
) -> str:
    if explicit_source_channel:
        return explicit_source_channel
    if basis:
        normalized = str(basis).strip().lower()
        if normalized in _BASIS_TO_SOURCE_CHANNEL:
            return _BASIS_TO_SOURCE_CHANNEL[normalized]
        if normalized:
            return normalized
    ref = str(conversation_ref or "").strip().lower()
    if ref.startswith("discovery/"):
        return "matchmaker_chat"
    if ref.startswith("profile/"):
        return "profile_form"
    return "matchmaker_chat"


def latest_explicit_observations(
    observations: list[Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    if not observations:
        return grouped
    for row in observations:
        field_name = str(row.get("field_name") or "").strip()
        if not field_name:
            continue
        source_type = str(row.get("source_type") or "").strip()
        if source_type not in PERSISTABLE_SOURCE_TYPES:
            continue
        current = grouped.get(field_name)
        created_at = str(row.get("created_at") or "")
        if current is None or created_at >= str(current.get("created_at") or ""):
            grouped[field_name] = dict(row)
    return grouped


def build_collected_items(
    persona: Mapping[str, Any] | None,
    observations: list[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    raw = extract_collected_statements(persona or {})
    obs_map = latest_explicit_observations(observations)
    items: dict[str, dict[str, Any]] = {}
    for field_name in COLLECTED_PERSONA_FIELDS:
        if field_name in INFERENCE_ONLY_PERSONA_FIELDS:
            continue
        value = raw.get(field_name)
        if value is None:
            continue
        if field_name in TAG_FIELDS_REQUIRING_EXPLICIT_OBS and field_name not in obs_map:
            continue
        meta = obs_map.get(field_name) or {}
        items[field_name] = {
            "value": value,
            "source_channel": infer_source_channel(
                conversation_ref=meta.get("conversation_ref"),
                explicit_source_channel=meta.get("source_channel"),
            ),
            "collected_at": meta.get("created_at"),
            "evidence": meta.get("evidence_text"),
            "source_type": meta.get("source_type") or "explicit",
        }
    return items


__all__ = [
    "TAG_FIELDS_REQUIRING_EXPLICIT_OBS",
    "build_collected_items",
    "infer_source_channel",
    "latest_explicit_observations",
]
