"""Unified profile service entrypoints."""

from .api import (
    apply_profile_updates,
    create_profile_row,
    detect_profile_table,
    get_profile,
    get_public_profile,
    list_comparison_profile_photo_sources,
    list_profile_columns,
    list_profile_photo_sources,
    list_comparison_profile_photos,
    list_profile_photo_previews,
    list_profile_photos,
    list_profiles,
    iter_profile_batches,
    resolve_profile_source,
    upsert_profile_for_onboarding,
)
from .persona_bridge import apply_persona_patch, render_public_profile

__all__ = [
    "apply_persona_patch",
    "apply_profile_updates",
    "create_profile_row",
    "detect_profile_table",
    "get_profile",
    "get_public_profile",
    "list_comparison_profile_photo_sources",
    "list_profile_columns",
    "list_profile_photo_sources",
    "list_comparison_profile_photos",
    "list_profile_photo_previews",
    "list_profile_photos",
    "list_profiles",
    "iter_profile_batches",
    "render_public_profile",
    "resolve_profile_source",
    "upsert_profile_for_onboarding",
]
