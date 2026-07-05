"""Photo-driven discovery search services."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .appearance_features import compute_photo_bonus_breakdown, load_candidate_photo_features
from .appearance_search import (
    AppearanceStyleSearcher,
    AttributeFilterSearcher,
    CelebrityReferenceGallery,
    FaceSimilaritySearcher,
    UploadedReferenceFaceProcessor,
    search_profiles_by_reference_image,
)
from observability.photo_search_metrics import emit_photo_search_event


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


def _merge_ranked_candidate_groups(
    *,
    groups: Iterable[tuple[str, Iterable[Mapping[str, Any]]]],
    top_k: int,
) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for source_name, rows in groups:
        for row in list(rows or []):
            payload = dict(row)
            profile_id = int(payload.get("profile_id") or 0)
            if profile_id <= 0:
                continue
            score = float(
                payload.get("final_score")
                or payload.get("similarity")
                or payload.get("base_score")
                or 0.0
            )
            current = merged.get(profile_id)
            if current is None:
                merged[profile_id] = {
                    **payload,
                    "profile_id": profile_id,
                    "final_score": round(score, 4),
                    "search_sources": [source_name],
                }
                continue
            current_score = float(current.get("final_score") or 0.0)
            averaged = round((current_score + score) / 2.0, 4)
            current["final_score"] = max(current_score, averaged, round(score, 4))
            current["base_score"] = round(
                max(float(current.get("base_score") or 0.0), float(payload.get("base_score") or 0.0)),
                4,
            )
            current["photo_bonus"] = round(
                max(float(current.get("photo_bonus") or 0.0), float(payload.get("photo_bonus") or 0.0)),
                2,
            )
            current["appearance_summary"] = current.get("appearance_summary") or payload.get("appearance_summary")
            sources = [str(item).strip() for item in list(current.get("search_sources") or []) if str(item).strip()]
            if source_name not in sources:
                sources.append(source_name)
            current["search_sources"] = sources
    ranked = sorted(
        merged.values(),
        key=lambda item: float(item.get("final_score") or 0.0),
        reverse=True,
    )
    return ranked[: max(1, int(top_k or 20))]


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
        emit_photo_search_event(
            user_key=requester_user_key,
            search_type="face_similarity",
            stage="search_failed",
            result_count=0,
            success=False,
        )
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
    out = {
        "saved": True,
        "search_type": "face_similarity",
        "result_count": len(reranked),
        "results": reranked,
    }
    emit_photo_search_event(
        user_key=requester_user_key,
        search_type="face_similarity",
        stage="search_completed",
        result_count=len(reranked),
        success=True,
    )
    return out


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
    query_text: str | None = None,
) -> dict[str, Any]:
    _ = UploadedReferenceFaceProcessor.process(
        image_source=image_source,
        requester_profile_id=requester_profile_id,
    )
    resolved_query_text = str(query_text or "").strip() or _style_query_from_image_source(image_source)
    base_results = AppearanceStyleSearcher.search_by_text(
        source_dsn=source_dsn,
        query_text=resolved_query_text,
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
    out = {
        "saved": True,
        "search_type": "style_similarity",
        "query_text": resolved_query_text,
        "result_count": len(reranked),
        "results": reranked,
    }
    emit_photo_search_event(
        user_key=str(requester_profile_id or "anonymous"),
        search_type="style_similarity",
        stage="search_completed",
        result_count=len(reranked),
        success=True,
    )
    return out


def search_hybrid_photo_candidates(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    image_source: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    attribute_filters: dict[str, Any] | None = None,
    query_text: str | None = None,
) -> dict[str, Any]:
    face_result = search_similar_face_candidates(
        source_dsn=source_dsn,
        requester_user_key=requester_user_key,
        image_source=image_source,
        requester_profile_id=requester_profile_id,
        top_k=max(top_k, 12),
        attribute_filters=attribute_filters,
    )
    style_result = search_style_candidates(
        source_dsn=source_dsn,
        image_source=image_source,
        requester_profile_id=requester_profile_id,
        top_k=max(top_k, 12),
        attribute_filters=attribute_filters,
        query_text=query_text,
    )
    merged_results = _merge_ranked_candidate_groups(
        groups=[
            ("face_similarity", face_result.get("results") or []),
            ("style_similarity", style_result.get("results") or []),
        ],
        top_k=top_k,
    )
    saved = bool(face_result.get("saved")) or bool(style_result.get("saved"))
    emit_photo_search_event(
        user_key=requester_user_key,
        search_type="hybrid_photo_similarity",
        stage="search_completed" if saved else "search_failed",
        result_count=len(merged_results),
        success=saved,
    )
    return {
        "saved": saved,
        "search_type": "hybrid_photo_similarity",
        "result_count": len(merged_results),
        "query_text": str(query_text or "").strip() or style_result.get("query_text") or "自动理解",
        "results": merged_results,
        "subsearches": {
            "face": {
                "saved": bool(face_result.get("saved")),
                "result_count": int(face_result.get("result_count") or 0),
            },
            "style": {
                "saved": bool(style_result.get("saved")),
                "result_count": int(style_result.get("result_count") or 0),
            },
        },
    }


def search_celebrity_face_candidates(
    *,
    source_dsn: str | None,
    celebrity_name: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    attribute_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    references = CelebrityReferenceGallery.search_by_name(celebrity_name, top_k=1)
    reference_embedding = CelebrityReferenceGallery.reference_embedding_for_name(celebrity_name)
    face_results = FaceSimilaritySearcher.search(
        source_dsn=source_dsn,
        reference_embedding=reference_embedding,
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
    base_scores = {
        item.profile_id: item.similarity
        for item in face_results
        if allowed_ids is None or item.profile_id in allowed_ids
    }
    reranked = _rerank_with_photo_bonus(
        source_dsn=source_dsn,
        profile_ids=list(base_scores.keys()),
        base_scores=base_scores,
    )[: max(1, int(top_k or 20))]
    out = {
        "saved": True,
        "search_type": "celebrity_face_similarity",
        "celebrity_reference": references[0] if references else {"name": celebrity_name},
        "result_count": len(reranked),
        "results": reranked,
    }
    emit_photo_search_event(
        user_key=str(requester_profile_id or celebrity_name),
        search_type="celebrity_face_similarity",
        stage="search_completed",
        result_count=len(reranked),
        success=True,
    )
    return out


__all__ = [
    "search_hybrid_photo_candidates",
    "search_celebrity_face_candidates",
    "search_similar_face_candidates",
    "search_style_candidates",
]
