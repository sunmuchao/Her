"""Photo-driven discovery search services."""

from __future__ import annotations

from typing import Any, Iterable

from .appearance_features import compute_photo_bonus_breakdown, load_candidate_photo_features
from .appearance_search import (
    AppearanceStyleSearcher,
    AttributeFilterSearcher,
    CelebrityReferenceGallery,
    FaceSimilaritySearcher,
    UploadedReferenceFaceProcessor,
    search_profiles_by_reference_image,
)


def _rerank_with_photo_bonus(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int],
    base_scores: dict[int, float],
) -> list[dict[str, Any]]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    feature_map = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=normalized_ids,
    )
    reranked: list[dict[str, Any]] = []
    for profile_id in normalized_ids:
        feature_row = feature_map.get(profile_id) or {}
        bonus = compute_photo_bonus_breakdown(feature_row, None)
        final_score = round(float(base_scores.get(profile_id) or 0.0) + (bonus.total / 100.0), 4)
        reranked.append(
            {
                "profile_id": profile_id,
                "base_score": round(float(base_scores.get(profile_id) or 0.0), 4),
                "photo_bonus": round(bonus.total, 2),
                "final_score": final_score,
                "appearance_summary": feature_row.get("appearance_summary"),
            }
        )
    reranked.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    return reranked


def search_similar_face_candidates(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    image_source: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    attribute_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = search_profiles_by_reference_image(
        source_dsn=source_dsn,
        requester_user_key=requester_user_key,
        requester_profile_id=requester_profile_id,
        image_source=image_source,
        top_k=max(top_k * 2, 20),
    )
    if not base.get("saved"):
        return base
    result_rows = list(base.get("results") or [])
    allowed_ids: set[int] | None = None
    if attribute_filters:
        filtered = AttributeFilterSearcher.search(
            source_dsn=source_dsn,
            filters=attribute_filters,
            top_k=max(top_k * 3, 50),
        )
        allowed_ids = {int(item.get("profile_id") or 0) for item in filtered if int(item.get("profile_id") or 0) > 0}
    base_scores: dict[int, float] = {}
    ordered_ids: list[int] = []
    for item in result_rows:
        profile_id = int(item.get("profile_id") or 0)
        if profile_id <= 0:
            continue
        if allowed_ids is not None and profile_id not in allowed_ids:
            continue
        ordered_ids.append(profile_id)
        base_scores[profile_id] = float(item.get("similarity") or 0.0)
    reranked = _rerank_with_photo_bonus(
        source_dsn=source_dsn,
        profile_ids=ordered_ids,
        base_scores=base_scores,
    )[: max(1, int(top_k or 20))]
    return {
        "saved": True,
        "search_type": "face_similarity",
        "result_count": len(reranked),
        "results": reranked,
    }


def _style_query_from_image_source(image_source: str) -> str:
    normalized = str(image_source or "").strip().lower()
    if not normalized:
        return ""
    parts: list[str] = []
    if "sun" in normalized or "outdoor" in normalized:
        parts.append("阳光")
    if "clean" in normalized or "white" in normalized:
        parts.append("清爽")
    if "mature" in normalized:
        parts.append("成熟")
    if "gentle" in normalized:
        parts.append("温柔")
    if "style" in normalized or "fashion" in normalized:
        parts.append("精致")
    return " ".join(parts) or "自然 顺眼"


def search_style_candidates(
    *,
    source_dsn: str | None,
    image_source: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    attribute_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = UploadedReferenceFaceProcessor.process(
        image_source=image_source,
        requester_profile_id=requester_profile_id,
    )
    query_text = _style_query_from_image_source(image_source)
    base_results = AppearanceStyleSearcher.search_by_text(
        source_dsn=source_dsn,
        query_text=query_text,
        top_k=max(top_k * 2, 20),
        exclude_profile_ids=[int(requester_profile_id or 0)] if int(requester_profile_id or 0) > 0 else [],
    )
    allowed_ids: set[int] | None = None
    if attribute_filters:
        filtered = AttributeFilterSearcher.search(
            source_dsn=source_dsn,
            filters=attribute_filters,
            top_k=max(top_k * 3, 50),
        )
        allowed_ids = {int(item.get("profile_id") or 0) for item in filtered if int(item.get("profile_id") or 0) > 0}
    base_scores: dict[int, float] = {}
    ordered_ids: list[int] = []
    for item in base_results:
        profile_id = int(item.get("profile_id") or item.get("user_id") or 0)
        if profile_id <= 0:
            continue
        if allowed_ids is not None and profile_id not in allowed_ids:
            continue
        ordered_ids.append(profile_id)
        base_scores[profile_id] = float(item.get("similarity") or 0.0)
    reranked = _rerank_with_photo_bonus(
        source_dsn=source_dsn,
        profile_ids=ordered_ids,
        base_scores=base_scores,
    )[: max(1, int(top_k or 20))]
    return {
        "saved": True,
        "search_type": "style_similarity",
        "query_text": query_text,
        "result_count": len(reranked),
        "results": reranked,
    }


def search_celebrity_face_candidates(
    *,
    source_dsn: str | None,
    celebrity_name: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    references = CelebrityReferenceGallery.search_by_name(celebrity_name, top_k=1)
    reference_embedding = CelebrityReferenceGallery.reference_embedding_for_name(celebrity_name)
    face_results = FaceSimilaritySearcher.search(
        source_dsn=source_dsn,
        reference_embedding=reference_embedding,
        top_k=max(top_k * 2, 20),
        exclude_profile_ids=[int(requester_profile_id or 0)] if int(requester_profile_id or 0) > 0 else [],
    )
    base_scores = {item.profile_id: item.similarity for item in face_results}
    reranked = _rerank_with_photo_bonus(
        source_dsn=source_dsn,
        profile_ids=[item.profile_id for item in face_results],
        base_scores=base_scores,
    )[: max(1, int(top_k or 20))]
    return {
        "saved": True,
        "search_type": "celebrity_face_similarity",
        "celebrity_reference": references[0] if references else {"name": celebrity_name},
        "result_count": len(reranked),
        "results": reranked,
    }


__all__ = [
    "search_celebrity_face_candidates",
    "search_similar_face_candidates",
    "search_style_candidates",
]
