"""明星脸搜索偏好学习模块

核心功能：
1. 从明星脸搜索中学习用户偏好（风格、五官、明星类型）
2. 写入用户偏好档案（user_appearance_preferences表）
3. 用于下次个性化推荐

使用方式：
from match_domain.celebrity_preference_learner import learn_from_celebrity_search

result = learn_from_celebrity_search(
    user_key="user123",
    photo_url="https://example.com/tianxiwei.jpg",
    celebrity_name="田曦薇"
)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


def learn_from_celebrity_search(
    user_key: str,
    photo_url: str,
    celebrity_name: str = "",
    source_dsn: str | None = None,
) -> dict[str, Any]:
    """从明星脸搜索中学习用户偏好

    Args:
        user_key: 用户标识
        photo_url: 明星照片URL
        celebrity_name: 明星名称（可选）
        source_dsn: 数据源DSN

    Returns:
        dict: 学习结果
    """

    _logger.info(
        f"【偏好学习开始】user_key={user_key} photo_url={photo_url[:100]} celebrity_name={celebrity_name}"
    )

    # Step 1: 提取照片特征
    from .face_embedding_extractor import extract_face_embedding
    from .appearance_description_generator import generate_appearance_description

    # 提取人脸向量（用于后续搜索）
    face_result = extract_face_embedding(photo_url)
    if not face_result or not face_result.get("success"):
        error_msg = face_result.get("error") if face_result else "no_result"
        _logger.warning(f"照片特征提取失败: {error_msg}")
        return {"success": False, "error": f"照片特征提取失败: {error_msg}"}

    # 提取外貌描述和标签（用于偏好学习）
    try:
        appearance_result = generate_appearance_description(photo_url)
        if not appearance_result or not appearance_result.get("success"):
            _logger.warning("外貌描述生成失败")
            # 不阻塞流程，继续用空特征
            style_keywords = []
            feature_keywords = []
        else:
            style_keywords = appearance_result.get("appearance_keywords", [])
            feature_keywords = appearance_result.get("dominant_features", [])
    except Exception as exc:
        _logger.warning(f"外貌描述生成异常: {exc}")
        style_keywords = []
        feature_keywords = []

    # 如果有明星名称，构造"明星类型"标签
    celebrity_type = f"{celebrity_name}类型" if celebrity_name else None

    _logger.info(
        f"【特征提取完成】style_keywords={style_keywords} "
        f"feature_keywords={feature_keywords} celebrity_type={celebrity_type}"
    )

    # Step 2: 查询现有偏好数据
    from profile_service.api import load_user_appearance_preference

    existing_preference = load_user_appearance_preference(
        source_dsn=source_dsn,
        user_key=user_key,
    )

    # Step 3: 合并偏好数据（增量学习）
    merged_preference = _merge_preference_data(
        existing_preference=existing_preference,
        style_keywords=style_keywords,
        feature_keywords=feature_keywords,
        celebrity_type=celebrity_type,
    )

    # Step 4: 写入用户偏好档案
    from profile_service.api import upsert_user_appearance_preference

    result = upsert_user_appearance_preference(
        source_dsn=source_dsn,
        preference_data={
            "user_key": user_key,
            "last_updated": datetime.now(),
            "preferred_style_tags_json": merged_preference.get("preferred_style_tags"),
            "preferred_style_weights_json": merged_preference.get("preferred_style_weights"),
            "preferred_feature_tags_json": merged_preference.get("preferred_feature_tags"),
            "preferred_feature_weights_json": merged_preference.get("preferred_feature_weights"),
            "preferred_celebrity_types_json": merged_preference.get("preferred_celebrity_types"),
            "preferred_celebrity_weights_json": merged_preference.get("preferred_celebrity_weights"),
            "positive_sample_count": merged_preference.get("positive_sample_count", 0),
        },
    )

    _logger.info(
        f"【偏好学习完成】user_key={user_key} "
        f"style_tags={merged_preference.get('preferred_style_tags')} "
        f"celebrity_types={merged_preference.get('preferred_celebrity_types')}"
    )

    return {
        "success": True,
        "learned_preference": merged_preference,
        "database_result": result,
    }


def _merge_preference_data(
    existing_preference: dict[str, Any] | None,
    style_keywords: list[str],
    feature_keywords: list[str],
    celebrity_type: str | None,
) -> dict[str, Any]:
    """合并偏好数据（增量学习）

    Args:
        existing_preference: 现有偏好数据
        style_keywords: 新提取的风格标签
        feature_keywords: 新提取的五官标签
        celebrity_type: 新提取的明星类型

    Returns:
        dict: 合并后的偏好数据
    """

    existing = dict(existing_preference or {})

    # 合并风格偏好
    existing_style_tags = list(existing.get("preferred_style_tags_json") or [])
    existing_style_weights = dict(existing.get("preferred_style_weights_json") or {})

    for keyword in style_keywords:
        if keyword not in existing_style_tags:
            existing_style_tags.append(keyword)
            existing_style_weights[keyword] = 0.5  # 新标签初始权重
        else:
            # 已存在的标签，权重增加
            existing_style_weights[keyword] = min(1.0, existing_style_weights.get(keyword, 0.5) + 0.1)

    # 合并五官偏好
    existing_feature_tags = list(existing.get("preferred_feature_tags_json") or [])
    existing_feature_weights = dict(existing.get("preferred_feature_weights_json") or {})

    for keyword in feature_keywords:
        if keyword not in existing_feature_tags:
            existing_feature_tags.append(keyword)
            existing_feature_weights[keyword] = 0.5
        else:
            existing_feature_weights[keyword] = min(1.0, existing_feature_weights.get(keyword, 0.5) + 0.1)

    # 合并明星类型偏好
    existing_celebrity_types = list(existing.get("preferred_celebrity_types_json") or [])
    existing_celebrity_weights = dict(existing.get("preferred_celebrity_weights_json") or {})

    if celebrity_type:
        if celebrity_type not in existing_celebrity_types:
            existing_celebrity_types.append(celebrity_type)
            existing_celebrity_weights[celebrity_type] = 0.5
        else:
            existing_celebrity_weights[celebrity_type] = min(1.0, existing_celebrity_weights.get(celebrity_type, 0.5) + 0.1)

    # 更新样本计数
    positive_sample_count = int(existing.get("positive_sample_count") or 0) + 1

    return {
        "preferred_style_tags": existing_style_tags,
        "preferred_style_weights": existing_style_weights,
        "preferred_feature_tags": existing_feature_tags,
        "preferred_feature_weights": existing_feature_weights,
        "preferred_celebrity_types": existing_celebrity_types,
        "preferred_celebrity_weights": existing_celebrity_weights,
        "positive_sample_count": positive_sample_count,
    }


__all__ = [
    "learn_from_celebrity_search",
]