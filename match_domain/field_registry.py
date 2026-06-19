"""Formal field registry for §13.1.2 profile / persona / criteria layering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .collected_profile import (
    COLLECTED_PERSONA_FIELDS,
    INFERENCE_ONLY_PERSONA_FIELDS,
    PROFILE_FACT_PROFILE_COLUMNS,
)

FieldLayer = Literal["P0", "P0-P1", "P1", "P2", "P3"]
WriteSource = Literal[
    "profile_form",
    "explicit_statement",
    "explicit_confirmation",
    "runtime_inference",
    "compile_output",
    "none",
]
DisplaySurface = Literal[
    "profile_page",
    "collected_page",
    "recommendation_explain",
    "internal_only",
    "none",
]
CriteriaUsage = Literal["hard_filter", "soft_preference", "self_feature", "none", "runtime_only"]


@dataclass(frozen=True)
class FieldRegistryEntry:
    field_name: str
    current_source: str
    target_layer: FieldLayer
    allowed_write_sources: tuple[WriteSource, ...]
    display_surface: DisplaySurface
    criteria_usage: CriteriaUsage
    notes: str = ""


def _entries_for_fields(
    fields: frozenset[str],
    *,
    layer: FieldLayer,
    current_source: str,
    write_sources: tuple[WriteSource, ...],
    display: DisplaySurface,
    criteria: CriteriaUsage,
    notes: str = "",
) -> tuple[FieldRegistryEntry, ...]:
    return tuple(
        FieldRegistryEntry(
            field_name=name,
            current_source=current_source,
            target_layer=layer,
            allowed_write_sources=write_sources,
            display_surface=display,
            criteria_usage=criteria,
            notes=notes,
        )
        for name in sorted(fields)
    )


P0_PROFILE_FACTS = _entries_for_fields(
    frozenset(
        (PROFILE_FACT_PROFILE_COLUMNS)
        - {
            "id",
            "avatar_url",
            "public_display_name",
            "public_education",
            "public_job",
            "public_personality",
            "public_values",
            "public_notes",
        }
    ),
    layer="P0",
    current_source="profiles",
    write_sources=("profile_form", "explicit_confirmation"),
    display="profile_page",
    criteria="self_feature",
    notes="Formal profile facts; persona auto-sync blocked.",
)

P0_P1_TRANSITION = _entries_for_fields(
    frozenset({"smoking", "drinking", "relationship_goal"}),
    layer="P0-P1",
    current_source="profiles",
    write_sources=("profile_form", "explicit_statement", "explicit_confirmation"),
    display="profile_page",
    criteria="self_feature",
)

P1_COLLECTED = _entries_for_fields(
    COLLECTED_PERSONA_FIELDS
    - frozenset({"display_name"}),
    # self_smoking, self_drinking, self_relationship_goal 已在 COLLECTED_PERSONA_FIELDS 中删除
    # 这些硬条件字段应该在 profiles 表中
    layer="P1",
    current_source="user_personas",
    write_sources=("profile_form", "explicit_statement", "explicit_confirmation"),
    display="collected_page",
    criteria="hard_filter",
    notes="Collected preferences; not mirrored to profiles.preferred_*.",
)

P2_INFERENCE = _entries_for_fields(
    INFERENCE_ONLY_PERSONA_FIELDS,
    layer="P2",
    current_source="deprecated",
    write_sources=("none",),
    display="none",
    criteria="runtime_only",
    notes="Must not persist; optional runtime snapshot only.",
)

P3_RUNTIME = (
    FieldRegistryEntry(
        field_name="effective_criteria",
        current_source="compile_effective_criteria",
        target_layer="P3",
        allowed_write_sources=("compile_output",),
        display_surface="internal_only",
        criteria_usage="hard_filter",
        notes="Compiled search/recommendation working set.",
    ),
    FieldRegistryEntry(
        field_name="criteria_snapshot",
        current_source="criteria_snapshots",
        target_layer="P3",
        allowed_write_sources=("compile_output",),
        display_surface="recommendation_explain",
        criteria_usage="none",
        notes="Optional runtime_explanation_json; not user profile.",
    ),
)

FIELD_REGISTRY: tuple[FieldRegistryEntry, ...] = (
    *P0_PROFILE_FACTS,
    *P0_P1_TRANSITION,
    *P1_COLLECTED,
    *P2_INFERENCE,
    *P3_RUNTIME,
)

FIELD_REGISTRY_BY_NAME: dict[str, FieldRegistryEntry] = {entry.field_name: entry for entry in FIELD_REGISTRY}


def registry_entry(field_name: str) -> FieldRegistryEntry | None:
    return FIELD_REGISTRY_BY_NAME.get(field_name)


__all__ = [
    "CriteriaUsage",
    "DisplaySurface",
    "FIELD_REGISTRY",
    "FIELD_REGISTRY_BY_NAME",
    "FieldLayer",
    "FieldRegistryEntry",
    "WriteSource",
    "registry_entry",
]
