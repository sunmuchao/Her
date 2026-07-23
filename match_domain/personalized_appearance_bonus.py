"""Personalized appearance bonus calculator based on user preferences."""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def compute_style_preference_bonus(
    *,
    candidate_photo_features: dict[str, Any],
    user_appearance_preference: dict[str, Any],
) -> float:
    """
    计算风格偏好匹配加分

    【逻辑】
    1. 提取候选人的风格标签
    2. 提取用户的偏好风格标签和权重
    3. 匹配计算：
       - 候选人风格符合用户偏好 → 加分（权重×3.0）
       - 候选人风格不符合用户偏好 → 减分（-3.0）

    Args:
        candidate_photo_features: 候选人照片特征（包含appearance_keywords_json）
        user_appearance_preference: 用户外貌偏好（包含preferred_style_tags_json等）

    Returns:
        float: 风格匹配加分（范围：-15到+20）
    """
    # 1. 提取候选人的风格标签
    candidate_keywords_raw = candidate_photo_features.get("appearance_keywords_json") or []

    # 解析风格标签（支持两种格式：["温柔"] 或 [{"label": "温柔"}]）
    candidate_keywords: list[str] = []
    for keyword_item in candidate_keywords_raw:
        if isinstance(keyword_item, str):
            keyword_str = keyword_item.strip()
            if keyword_str:
                candidate_keywords.append(keyword_str)
        elif isinstance(keyword_item, dict):
            keyword_str = str(keyword_item.get("label") or "").strip()
            if keyword_str:
                candidate_keywords.append(keyword_str)

    if not candidate_keywords:
        return 0.0

    # 2. 提取用户的偏好风格标签和权重
    preferred_tags = list(user_appearance_preference.get("preferred_style_tags_json") or [])
    preferred_weights = dict(user_appearance_preference.get("preferred_style_weights_json") or {})
    disliked_tags = list(user_appearance_preference.get("disliked_style_tags_json") or [])

    # 3. 计算加分
    bonus = 0.0

    # 正向匹配：候选人风格符合用户偏好
    for keyword in candidate_keywords:
        if keyword in preferred_weights:
            weight = float(preferred_weights.get(keyword, 1.0))
            bonus += weight * 3.0  # 每个匹配标签加分（权重×3）

    # 负向匹配：候选人风格不符合用户偏好
    for keyword in candidate_keywords:
        if keyword in disliked_tags:
            bonus -= 3.0  # 每个不匹配标签减分

    # 4. 限制加分范围（-15到+20）
    bonus = max(-15.0, min(20.0, bonus))

    return round(bonus, 2)


def compute_feature_preference_bonus(
    *,
    candidate_photo_features: dict[str, Any],
    candidate_face_attributes: dict[str, Any],
    user_appearance_preference: dict[str, Any],
) -> float:
    """
    计算五官偏好匹配加分

    【逻辑】
    1. 提取候选人的五官评分
    2. 提取用户的偏好五官评分平均值和标准差
    3. 匹配计算：
       - 候选人五官评分接近用户偏好平均值 → 加分
       - 接近程度 = 差距 / 标准差

    【关键设计】
    - 不是"眼睛大就加分"，而是"眼睛大小接近用户偏好就加分"
    - 使用标准差判断接近程度（统计学方法）

    Args:
        candidate_photo_features: 候选人照片特征
        candidate_face_attributes: 候选人五官属性（包含eye_size_score等）
        user_appearance_preference: 用户外貌偏好（包含preferred_eye_size_score_avg等）

    Returns:
        float: 五官匹配加分（范围：0到+8）
    """
    # 1. 提取用户五官偏好
    user_eye_size_avg = float(user_appearance_preference.get("preferred_eye_size_score_avg") or 0)
    user_eye_size_std = float(user_appearance_preference.get("preferred_eye_size_score_std") or 0)

    user_face_roundness_avg = float(user_appearance_preference.get("preferred_face_roundness_score_avg") or 0)
    user_face_roundness_std = float(user_appearance_preference.get("preferred_face_roundness_score_std") or 0)

    user_jaw_definition_avg = float(user_appearance_preference.get("preferred_jaw_definition_score_avg") or 0)
    user_youthfulness_avg = float(user_appearance_preference.get("preferred_youthfulness_score_avg") or 0)

    # 2. 提取候选人五官评分
    candidate_eye_size = float(candidate_face_attributes.get("eye_size_score") or 0)
    candidate_face_roundness = float(candidate_face_attributes.get("face_roundness_score") or 0)
    candidate_jaw_definition = float(candidate_face_attributes.get("jaw_definition_score") or 0)
    candidate_youthfulness = float(candidate_face_attributes.get("youthfulness_score") or 0)

    # 3. 计算加分（每个五官维度独立计算）
    bonus = 0.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 眼睛大小匹配
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if user_eye_size_avg > 0 and candidate_eye_size > 0:
        diff = abs(candidate_eye_size - user_eye_size_avg)

        # 用户偏好明确（标准差 > 0）
        if user_eye_size_std > 0:
            ratio = diff / user_eye_size_std

            if ratio <= 1.0:  # 差距 ≤ 标准差 → 非常接近
                bonus += 2.0
            elif ratio <= 2.0:  # 差距 ≤ 2倍标准差 → 比较接近
                bonus += 1.0
            # 差距 > 2倍标准差 → 不加分

        # 用户偏好不明确（标准差 = 0，只点赞过1个候选人）
        else:
            if diff <= 10:  # 差距 ≤ 10分
                bonus += 1.5

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 脸型圆润度匹配
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if user_face_roundness_avg > 0 and candidate_face_roundness > 0:
        diff = abs(candidate_face_roundness - user_face_roundness_avg)

        if user_face_roundness_std > 0:
            ratio = diff / user_face_roundness_std

            if ratio <= 1.0:
                bonus += 1.5
            elif ratio <= 2.0:
                bonus += 0.8
        else:
            if diff <= 15:
                bonus += 1.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 下颌线清晰度匹配
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if user_jaw_definition_avg > 0 and candidate_jaw_definition > 0:
        diff = abs(candidate_jaw_definition - user_jaw_definition_avg)

        if diff <= 15:
            bonus += 1.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 幼态感匹配
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if user_youthfulness_avg > 0 and candidate_youthfulness > 0:
        diff = abs(candidate_youthfulness - user_youthfulness_avg)

        if diff <= 12:
            bonus += 1.0

    # 4. 限制加分范围（0到+8）
    bonus = max(0.0, min(8.0, bonus))

    return round(bonus, 2)


def compute_personalized_appearance_bonus(
    *,
    source_dsn: str,
    candidate_profile_id: int,
    user_key: str,
) -> dict[str, Any]:
    """
    计算个性化外貌加分（综合风格偏好 + 五官偏好）

    【不包括】
    - ❌ 颜值评分匹配加分（beauty_score只做基础分）

    【返回】
    - style_match_bonus: 风格偏好匹配加分
    - feature_match_bonus: 五官偏好匹配加分
    - total_bonus: 总加分
    """
    from match_domain.user_appearance_preference_learner import load_user_appearance_preferences
    from profile_service import list_profile_face_attributes, list_profile_photo_feature_rows

    # 1. 获取候选人外貌特征
    feature_rows = list_profile_photo_feature_rows(
        source_dsn=source_dsn,
        profile_ids=[candidate_profile_id],
        analysis_statuses=["done"],
        limit=1,
    )

    if not feature_rows:
        return {
            "style_match_bonus": 0.0,
            "feature_match_bonus": 0.0,
            "total_bonus": 0.0,
            "error": "candidate_features_missing",
        }

    candidate_photo_features = dict(feature_rows[0])

    # 2. 获取候选人五官属性
    attribute_rows = list_profile_face_attributes(
        source_dsn=source_dsn,
        profile_ids=[candidate_profile_id],
    )

    candidate_face_attributes = dict(attribute_rows[0]) if attribute_rows else {}

    # 3. 获取用户外貌偏好
    user_appearance_preference = load_user_appearance_preferences(
        source_dsn=source_dsn,
        user_key=user_key,
    )

    if not user_appearance_preference:
        # 用户偏好不存在（新用户）→ 不加分
        return {
            "style_match_bonus": 0.0,
            "feature_match_bonus": 0.0,
            "total_bonus": 0.0,
            "reason": "user_preference_not_found",
        }

    # 4. 计算风格偏好匹配加分
    style_match_bonus = compute_style_preference_bonus(
        candidate_photo_features=candidate_photo_features,
        user_appearance_preference=user_appearance_preference,
    )

    # 5. 计算五官偏好匹配加分
    feature_match_bonus = compute_feature_preference_bonus(
        candidate_photo_features=candidate_photo_features,
        candidate_face_attributes=candidate_face_attributes,
        user_appearance_preference=user_appearance_preference,
    )

    # 6. 总加分
    total_bonus = style_match_bonus + feature_match_bonus

    return {
        "style_match_bonus": style_match_bonus,
        "feature_match_bonus": feature_match_bonus,
        "total_bonus": round(total_bonus, 2),
    }


def compute_candidate_total_score(
    *,
    source_dsn: str,
    candidate_profile_id: int,
    user_key: str,
) -> dict[str, Any]:
    """
    计算候选人综合评分（三层评分机制）

    【评分结构】
    1. 基础分（beauty_score）- 全局评分
    2. 全局加分（照片质量）- 全局评分
    3. 个性化加分（风格偏好 + 五官偏好）- 个性化评分

    【返回】
    - base_score: 基础分（颜值评分）
    - quality_bonus: 全局加分（照片质量）
    - style_match_bonus: 风格匹配加分
    - feature_match_bonus: 五官匹配加分
    - total_bonus: 总加分（全局 + 个性化）
    - total_score: 综合评分
    """
    from profile_service import list_profile_photo_feature_rows

    # 1. 获取候选人外貌特征
    feature_rows = list_profile_photo_feature_rows(
        source_dsn=source_dsn,
        profile_ids=[candidate_profile_id],
        analysis_statuses=["done"],
        limit=1,
    )

    if not feature_rows:
        return {
            "total_score": 0.0,
            "error": "candidate_features_missing",
        }

    candidate_photo_features = dict(feature_rows[0])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 第一层：基础分（beauty_score）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    base_score = float(candidate_photo_features.get("beauty_score") or 0)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 第二层：全局加分（照片质量）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    quality_bonus = 0.0
    quality_score = float(candidate_photo_features.get("quality_score") or 0)
    authenticity_score = float(candidate_photo_features.get("authenticity_score") or 0)

    if quality_score >= 75:
        quality_bonus += 2.0

    if authenticity_score >= 80:
        quality_bonus += 3.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 第三层：个性化加分（风格偏好 + 五官偏好）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    personalized_bonus_result = compute_personalized_appearance_bonus(
        source_dsn=source_dsn,
        candidate_profile_id=candidate_profile_id,
        user_key=user_key,
    )

    style_match_bonus = personalized_bonus_result.get("style_match_bonus", 0)
    feature_match_bonus = personalized_bonus_result.get("feature_match_bonus", 0)
    personalized_bonus = personalized_bonus_result.get("total_bonus", 0)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 综合评分
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    total_bonus = quality_bonus + personalized_bonus
    total_score = base_score + total_bonus

    return {
        "base_score": base_score,
        "quality_bonus": round(quality_bonus, 2),
        "style_match_bonus": style_match_bonus,
        "feature_match_bonus": feature_match_bonus,
        "personalized_bonus": round(personalized_bonus, 2),
        "total_bonus": round(total_bonus, 2),
        "total_score": round(total_score, 2),
    }


def batch_compute_candidate_scores(
    *,
    source_dsn: str,
    candidate_profile_ids: list[int],
    user_key: str,
) -> list[dict[str, Any]]:
    """
    批量计算候选人综合评分

    Args:
        source_dsn: 数据库连接字符串
        candidate_profile_ids: 候选人ID列表
        user_key: 用户标识

    Returns:
        list: 候选人评分列表（按total_score降序排序）
    """
    results: list[dict[str, Any]] = []

    for candidate_id in candidate_profile_ids:
        score_result = compute_candidate_total_score(
            source_dsn=source_dsn,
            candidate_profile_id=candidate_id,
            user_key=user_key,
        )

        results.append({
            "profile_id": candidate_id,
            **score_result,
        })

    # 按total_score降序排序
    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    return results


def compute_celebrity_type_bonus(
    *,
    candidate_photo_features: dict[str, Any],
    user_appearance_preference: dict[str, Any],
) -> float:
    """计算明星类型偏好加分

    【逻辑】
    1. 提取候选人的外貌标签
    2. 提取用户偏好的明星类型
    3. 检查候选人是否符合明星类型的特征
    4. 符合 → 加分（权重×3.0）

    Args:
        candidate_photo_features: 候选人照片特征（包含appearance_keywords_json）
        user_appearance_preference: 用户外貌偏好（包含preferred_celebrity_types_json等）

    Returns:
        float: 明星类型偏好加分（范围：-10到+15）
    """

    # 1. 提取候选人的外貌标签
    candidate_keywords_raw = candidate_photo_features.get("appearance_keywords_json") or []

    # 解析风格标签
    candidate_keywords: list[str] = []
    for keyword_item in candidate_keywords_raw:
        if isinstance(keyword_item, str):
            keyword_str = keyword_item.strip()
            if keyword_str:
                candidate_keywords.append(keyword_str)
        elif isinstance(keyword_item, dict):
            keyword_str = str(keyword_item.get("label") or keyword_item.get("keyword") or "").strip()
            if keyword_str:
                candidate_keywords.append(keyword_str)

    if not candidate_keywords:
        return 0.0

    # 2. 提取用户偏好的明星类型
    preferred_celebrity_types = list(user_appearance_preference.get("preferred_celebrity_types_json") or [])
    preferred_celebrity_weights = dict(user_appearance_preference.get("preferred_celebrity_weights_json") or {})

    if not preferred_celebrity_types:
        return 0.0

    # 3. 检查候选人是否符合明星类型的特征
    bonus = 0.0

    for celebrity_type in preferred_celebrity_types:
        weight = float(preferred_celebrity_weights.get(celebrity_type, 0.5))

        # 检查候选人是否符合这个明星类型的特征
        if _matches_celebrity_type(candidate_keywords, celebrity_type):
            bonus += weight * 3.0

    # 4. 限制加分范围（-10到+15）
    bonus = max(-10.0, min(15.0, bonus))

    return round(bonus, 2)


def _matches_celebrity_type(candidate_keywords: list[str], celebrity_type: str) -> bool:
    """判断候选人是否符合明星类型

    Args:
        candidate_keywords: 候选人外貌标签
        celebrity_type: 明星类型（如"田曦薇类型"）

    Returns:
        bool: 是否匹配
    """

    # 明星类型特征映射（简化版，实际应该从数据库查询）
    celebrity_features_map = {
        "田曦薇类型": ["甜美", "圆眼", "元气", "鹅蛋脸", "温柔"],
        "刘亦菲类型": ["清秀", "仙气", "古典", "鹅蛋脸", "神仙姐姐"],
        "范冰冰类型": ["精致", "瓜子脸", "大气", "美艳", "成熟"],
        "赵丽颖类型": ["可爱", "圆脸", "甜美", "元气", "邻家"],
        "杨幂类型": ["精致", "大眼睛", "少女感", "甜美"],
    }

    features = celebrity_features_map.get(celebrity_type, [])

    if not features:
        # 如果没有预定义特征，返回False
        return False

    # 检查候选人是否包含该明星类型的特征
    match_count = sum(1 for keyword in candidate_keywords if keyword in features)

    # 至少匹配2个特征才算符合
    return match_count >= 2


__all__ = [
    "compute_style_preference_bonus",
    "compute_feature_preference_bonus",
    "compute_celebrity_type_bonus",  # 新增
    "compute_personalized_appearance_bonus",
    "compute_candidate_total_score",
    "batch_compute_candidate_scores",
]