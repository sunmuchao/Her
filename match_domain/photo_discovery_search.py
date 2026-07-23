"""Photo-driven discovery search services.

底层 face/style/hybrid/reference 检索能力继续保留在这里，方便独立测试和复用。
但从 A5 开始，这些函数不再作为 discovery 顶层协议边界暴露，而是作为内部能力供
service / agent capability tools 组合调用。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from .appearance_features import compute_photo_bonus_breakdown, load_candidate_photo_features
from .appearance_search import (
    AppearanceStyleSearcher,
    AttributeFilterSearcher,
    FaceSimilaritySearcher,
    UploadedReferenceFaceProcessor,
    search_profiles_by_reference_image,
)
from observability.photo_search_metrics import emit_photo_search_event

_logger = logging.getLogger(__name__)


def _prepare_candidate_appearance_data(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int],
    base_scores: dict[int, float],
    user_key: str | None = None,
) -> dict[str, Any]:
    """
    准备候选人外貌数据（只返回原始数据）

    【Agent Native设计】
    - 只返回原始数据，不计算加分、不排序
    - Agent根据原始数据自己判断匹配度并排序
    - 不包含"final_score"、"photo_bonus"等业务判断

    Args:
        source_dsn: 数据源
        profile_ids: 候选人ID列表
        base_scores: 基础相似度评分
        user_key: 用户标识（用于查询用户偏好）

    Returns:
        dict: 包含candidates（候选人数据）和user_preference（用户偏好）
    """
    from .appearance_features import get_candidate_appearance_features

    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]

    # 查询候选人外貌特征（原始数据）
    appearance_features = get_candidate_appearance_features(
        source_dsn=source_dsn,
        profile_ids=normalized_ids,
    )

    # 查询用户偏好（原始数据）
    user_preference = None
    if user_key and source_dsn:
        from .appearance_features import load_requester_appearance_preference

        user_preference = load_requester_appearance_preference(
            source_dsn=source_dsn,
            user_key=user_key,
        )

    # 构建返回数据（原始数据）
    candidates = []
    for feature in appearance_features:
        profile_id = feature["profile_id"]

        candidates.append({
            "profile_id": profile_id,
            "base_similarity": base_scores.get(profile_id, 0.0),  # 基础相似度
            "appearance_keywords": feature["appearance_keywords"],  # 风格标签
            "style_scores": feature["style_scores"],  # 风格评分
            "photo_quality_score": feature["photo_quality_score"],  # 照片质量
            "beauty_score": feature["beauty_score"],  # 颜值评分
            "appearance_summary": feature["appearance_summary"],  # 外貌描述
            # 不包含"final_score"、"photo_bonus"等业务判断
        })

    return {
        "candidates": candidates,
        "user_preference": user_preference,  # 用户偏好（原始数据）
    }


def _rerank_with_photo_bonus(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int],
    base_scores: dict[int, float],
    user_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    对候选人进行重排序（旧版本，向后兼容）

    【已废弃】请使用 _prepare_candidate_appearance_data 代替

    【Agent Native设计】
    - 此函数保留用于向后兼容
    - 新代码应使用 _prepare_candidate_appearance_data，只返回原始数据
    - Agent根据原始数据自己判断匹配度并排序
    """
    _logger.warning(
        "【已废弃】_rerank_with_photo_bonus 已被废弃，请使用 _prepare_candidate_appearance_data",
        extra={"user_key": user_key},
    )

    # 调用新函数获取原始数据
    result = _prepare_candidate_appearance_data(
        source_dsn=source_dsn,
        profile_ids=profile_ids,
        base_scores=base_scores,
        user_key=user_key,
    )

    # 为了向后兼容，添加默认的排序逻辑（但这是硬编码的，不推荐）
    candidates = result["candidates"]
    for candidate in candidates:
        # 简单的评分公式（硬编码，不推荐）
        base_sim = candidate["base_similarity"]
        beauty = candidate["beauty_score"]
        quality = candidate["photo_quality_score"]
        # 简单的加权平均（Agent应该自己决定权重）
        candidate["final_score"] = round((base_sim * 0.5 + beauty / 100.0 * 0.3 + quality / 100.0 * 0.2), 4)

    # 按final_score排序（硬编码排序，Agent应该自己排序）
    candidates.sort(key=lambda x: x["final_score"], reverse=True)

    return candidates


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
        user_key=requester_user_key,  # 传入user_key，启用个性化加分
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
    requester_user_key: str | None = None,  # 新增：用户标识，用于个性化加分
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
        user_key=requester_user_key,  # 传入user_key，启用个性化加分
    )[: max(1, int(top_k or 20))]
    out = {
        "saved": True,
        "search_type": "style_similarity",
        "query_text": resolved_query_text,
        "result_count": len(reranked),
        "results": reranked,
    }
    emit_photo_search_event(
        user_key=requester_user_key or str(requester_profile_id or "anonymous"),
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
    photo_url: str,  # ✅ 新增：必需参数，明星照片URL
    celebrity_name: str | None = None,  # ✅ 改为可选，用于日志和显示
    requester_profile_id: int | None = None,
    requester_user_key: str | None = None,
    top_k: int = 20,
    attribute_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """明星脸搜索（AI Native版本）

    核心改动：
    - 新增photo_url参数（必需）：Agent或前端需要自己获取明星照片URL
    - celebrity_name改为可选：仅用于日志和显示，不参与搜索逻辑
    - 移除硬编码的CelebrityReferenceGallery，改用真实的人脸向量

    Args:
        source_dsn: 数据库DSN
        photo_url: 明星照片URL（Agent用WebSearch获取或前端上传）
        celebrity_name: 明星名字（可选，用于日志）
        requester_profile_id: 用户画像ID
        requester_user_key: 用户标识（用于个性化加分）
        top_k: 返回数量
        attribute_filters: 属性筛选条件

    Returns:
        搜索结果，包含候选人列表
    """
    _logger.info(
        "【明星脸搜索】stage=request_received celebrity_name=%s photo_url=%s requester_profile_id=%s top_k=%s has_attribute_filters=%s",
        celebrity_name,
        photo_url[:200],
        requester_profile_id,
        top_k,
        bool(attribute_filters),
    )

    # Step 1: 提取明星照片的人脸向量
    from .face_embedding_extractor import extract_face_embedding

    _logger.info(
        "【明星脸搜索】stage=reference_fetch_start celebrity_name=%s photo_url=%s",
        celebrity_name,
        photo_url[:200],
    )

    embedding_result = extract_face_embedding(photo_url)

    if not embedding_result or not embedding_result.get("success"):
        error_msg = embedding_result.get("error", "人脸向量提取失败") if embedding_result else "人脸向量提取失败"
        _logger.error(
            "【明星脸搜索失败】stage=embedding_compute_failed celebrity_name=%s photo_url=%s error=%s",
            celebrity_name,
            photo_url[:200],
            error_msg,
        )

        return {
            "saved": False,
            "search_type": "celebrity_face_similarity",
            "error": error_msg,
            "result_count": 0,
            "results": [],
        }

    # Step 2: 获取人脸向量
    reference_embedding = embedding_result.get("face_embedding")

    if not reference_embedding:
        _logger.error(
            "【明星脸搜索失败】stage=embedding_missing celebrity_name=%s photo_url=%s",
            celebrity_name,
            photo_url[:200],
        )
        return {
            "saved": False,
            "search_type": "celebrity_face_similarity",
            "error": "照片中未检测到人脸",
            "result_count": 0,
            "results": [],
        }

    _logger.info(
        "【明星脸搜索】stage=embedding_compute_done celebrity_name=%s photo_url=%s dimension=%s confidence=%s",
        celebrity_name,
        photo_url[:200],
        len(reference_embedding),
        embedding_result.get("face_detection_confidence"),
    )

    # Step 3: 用真实向量搜索相似候选人
    _logger.info(
        "【明星脸搜索】stage=search_candidates_start celebrity_name=%s query_embedding_dimension=%s",
        celebrity_name,
        len(reference_embedding),
    )
    face_results = FaceSimilaritySearcher.search(
        source_dsn=source_dsn,
        reference_embedding=reference_embedding,  # ✅ 使用真实向量
        top_k=max(top_k * 2, 20),
        exclude_profile_ids=[int(requester_profile_id or 0)] if int(requester_profile_id or 0) > 0 else [],
    )

    # Step 4: 属性筛选（可选）
    allowed_ids: set[int] | None = None
    if attribute_filters:
        filtered = AttributeFilterSearcher.search(
            source_dsn=source_dsn,
            filters=attribute_filters,
            top_k=max(top_k * 3, 50),
        )
        allowed_ids = {int(item.get("profile_id") or 0) for item in filtered if int(item.get("profile_id") or 0) > 0}
        _logger.info(
            "【明星脸搜索】stage=attribute_filter_done celebrity_name=%s allowed_count=%s",
            celebrity_name,
            len(allowed_ids),
        )

    # Step 5: 计算基础分
    base_scores = {
        item.profile_id: item.similarity
        for item in face_results
        if allowed_ids is None or item.profile_id in allowed_ids
    }
    _logger.info(
        "【明星脸搜索】stage=search_candidates_done celebrity_name=%s raw_candidate_count=%s filtered_candidate_count=%s",
        celebrity_name,
        len(face_results),
        len(base_scores),
    )

    # Step 6: 重排序（个性化加分）
    _logger.info(
        "【明星脸搜索】stage=rerank_start celebrity_name=%s candidate_count=%s",
        celebrity_name,
        len(base_scores),
    )
    reranked = _rerank_with_photo_bonus(
        source_dsn=source_dsn,
        profile_ids=list(base_scores.keys()),
        base_scores=base_scores,
        user_key=requester_user_key,
    )[: max(1, int(top_k or 20))]
    _logger.info(
        "【明星脸搜索】stage=rerank_done celebrity_name=%s result_count=%s",
        celebrity_name,
        len(reranked),
    )

    # Step 7: 返回结果
    out = {
        "saved": True,
        "search_type": "celebrity_face_similarity",
        "celebrity_reference": {
            "name": celebrity_name or "unknown",
            "photo_url": photo_url,
            "face_detection_confidence": embedding_result.get("face_detection_confidence"),
        },
        "result_count": len(reranked),
        "results": reranked,
    }

    emit_photo_search_event(
        user_key=requester_user_key or str(requester_profile_id or celebrity_name or "unknown"),
        search_type="celebrity_face_similarity",
        stage="search_completed",
        result_count=len(reranked),
        success=True,
    )
    _logger.info(
        "【明星脸搜索】stage=response_ready celebrity_name=%s result_count=%s",
        celebrity_name,
        len(reranked),
    )

    return out


__all__ = [
    "search_hybrid_photo_candidates",
    "search_celebrity_face_candidates",
    "search_similar_face_candidates",
    "search_style_candidates",
]
