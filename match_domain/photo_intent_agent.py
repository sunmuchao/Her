"""Photo preference intent parsing and explanation services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .appearance_features import build_match_explanation_payload
from .appearance_search import CelebrityReferenceGallery
from .photo_discovery_search import (
    search_celebrity_face_candidates,
    search_similar_face_candidates,
    search_style_candidates,
)


@dataclass(frozen=True)
class PhotoPreferenceIntent:
    intent_type: str
    mode: str
    query_text: str
    attribute_filters: dict[str, Any]
    celebrity_name: str | None = None
    raw_text: str = ""


def detect_photo_preference_intent(text: str) -> PhotoPreferenceIntent:
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    attribute_filters: dict[str, Any] = {}
    query_parts: list[str] = []

    if "阳光" in normalized or "sunny" in lowered:
        attribute_filters["sunny_score"] = {"min": 65}
        query_parts.append("阳光")
    if "清爽" in normalized or "clean" in lowered:
        attribute_filters["clean_score"] = {"min": 68}
        query_parts.append("清爽")
    if "成熟" in normalized or "mature" in lowered:
        attribute_filters["mature_score"] = {"min": 65}
        query_parts.append("成熟")
    if "温柔" in normalized or "gentle" in lowered:
        attribute_filters["gentle_score"] = {"min": 62}
        query_parts.append("温柔")
    if "幼态" in normalized or "可爱" in normalized:
        attribute_filters["youthfulness_score"] = {"min": 62}
        query_parts.append("幼态")
    if "眼睛大" in normalized:
        attribute_filters["eye_size_score"] = {"min": 68}
        query_parts.append("眼睛大")

    celebrity_name = None
    for candidate in CelebrityReferenceGallery.DEFAULT_REFERENCES:
        if candidate in normalized:
            celebrity_name = candidate
            break

    if celebrity_name:
        return PhotoPreferenceIntent(
            intent_type="celebrity_face_search",
            mode="celebrity",
            query_text=celebrity_name,
            celebrity_name=celebrity_name,
            attribute_filters=attribute_filters,
            raw_text=normalized,
        )
    if any(token in normalized for token in ("像这张脸", "像这个人", "找像", "同款脸")):
        return PhotoPreferenceIntent(
            intent_type="face_similarity_search",
            mode="face",
            query_text=normalized,
            attribute_filters=attribute_filters,
            raw_text=normalized,
        )
    return PhotoPreferenceIntent(
        intent_type="style_similarity_search",
        mode="style",
        query_text=" ".join(query_parts) or normalized or "自然 顺眼",
        attribute_filters=attribute_filters,
        raw_text=normalized,
    )


def translate_intent_to_search_plan(intent: PhotoPreferenceIntent) -> dict[str, Any]:
    payload = {
        "intent_type": intent.intent_type,
        "mode": intent.mode,
        "query_text": intent.query_text,
        "attribute_filters": dict(intent.attribute_filters),
    }
    if intent.celebrity_name:
        payload["celebrity_name"] = intent.celebrity_name
    if intent.mode == "style":
        payload["search_strategy"] = "appearance_vector_plus_tags"
    elif intent.mode == "celebrity":
        payload["search_strategy"] = "celebrity_reference_face"
    else:
        payload["search_strategy"] = "reference_face_similarity"
    return payload


def execute_photo_preference_search(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    intent: PhotoPreferenceIntent,
    image_source: str | None = None,
    requester_profile_id: int | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    if intent.mode == "celebrity":
        return search_celebrity_face_candidates(
            source_dsn=source_dsn,
            celebrity_name=str(intent.celebrity_name or intent.query_text),
            requester_profile_id=requester_profile_id,
            top_k=top_k,
        )
    if intent.mode == "face":
        return search_similar_face_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=str(image_source or "").strip() or intent.query_text,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
        )
    return search_style_candidates(
        source_dsn=source_dsn,
        image_source=str(image_source or "").strip() or intent.query_text,
        requester_profile_id=requester_profile_id,
        top_k=top_k,
        attribute_filters=intent.attribute_filters,
    )


def build_photo_recommendation_explanation(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidate = dict(candidate_row or {})
    appearance_summary = str(candidate.get("appearance_summary") or "").strip()
    highlights: list[str] = []
    if intent.celebrity_name:
        highlights.append(f"整体神态会让人联想到{intent.celebrity_name}")
    if appearance_summary:
        highlights.append(appearance_summary)
    for field_name in intent.attribute_filters:
        label = field_name.replace("_score", "")
        highlights.append(f"{label}方向更贴近你的描述")
    payload = build_match_explanation_payload(
        matched_on=list(matched_reasons or []),
        appearance_reasoning={
            "summary": (
                f"这位的长相风格更贴近你说的“{intent.query_text}”"
                if intent.mode != "celebrity"
                else f"这位的整体观感更接近你提到的{intent.celebrity_name}"
            ),
            "highlights": highlights,
        },
    )
    payload["intent_type"] = intent.intent_type
    payload["mode"] = intent.mode
    return payload


__all__ = [
    "PhotoPreferenceIntent",
    "build_photo_recommendation_explanation",
    "detect_photo_preference_intent",
    "execute_photo_preference_search",
    "translate_intent_to_search_plan",
]
