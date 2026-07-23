"""Unified retrieval entrypoint for visual candidate search.

This module is the方案 B compatibility bridge:
- upper layers call a single retrieval API
- lower layers can still reuse legacy face/style/hybrid searchers during migration
"""

from __future__ import annotations

from typing import Any, Mapping

from .photo_discovery_search import (
    search_hybrid_photo_candidates,
    search_similar_face_candidates,
    search_style_candidates,
)
from .photo_intent_agent import PhotoPreferenceIntent, visual_plan_to_photo_intent


def _resolve_intent(
    *,
    intent: PhotoPreferenceIntent | None,
    visual_plan: Mapping[str, Any] | None,
) -> PhotoPreferenceIntent:
    if intent is not None:
        return intent
    if visual_plan is None:
        raise ValueError("either intent or visual_plan is required")
    return visual_plan_to_photo_intent(dict(visual_plan or {}))


def execute_visual_candidate_retrieval(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    image_source: str | None = None,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    intent: PhotoPreferenceIntent | None = None,
    visual_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_intent = _resolve_intent(intent=intent, visual_plan=visual_plan)
    normalized_image = str(image_source or "").strip() or resolved_intent.query_text

    # During migration we keep the legacy retrievers here, but upper layers no longer
    # route directly by face/style/hybrid names.
    if resolved_intent.intent_type == "style_similarity_search":
        return search_style_candidates(
            source_dsn=source_dsn,
            image_source=normalized_image,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=resolved_intent.attribute_filters,
        )
    if resolved_intent.intent_type == "face_similarity_search":
        return search_similar_face_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=normalized_image,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=resolved_intent.attribute_filters,
        )
    if resolved_intent.intent_type == "celebrity_face_search":
        return search_similar_face_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=normalized_image,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=resolved_intent.attribute_filters,
        )
    return search_hybrid_photo_candidates(
        source_dsn=source_dsn,
        requester_user_key=requester_user_key,
        image_source=normalized_image,
        requester_profile_id=requester_profile_id,
        top_k=top_k,
        attribute_filters=resolved_intent.attribute_filters,
        query_text=resolved_intent.query_text,
    )


__all__ = ["execute_visual_candidate_retrieval"]
