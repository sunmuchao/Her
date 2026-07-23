"""User appearance preference learner from behavior data."""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)

# 默认表名
DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE = "user_appearance_preferences"


def learn_style_preference(
    *,
    source_dsn: str,
    user_key: str,
    behavior_table_name: str = "user_appearance_behavior_log",
) -> dict[str, Any]:
    """
    学习用户风格偏好

    【数据来源】
    - user_appearance_behavior_log 表
    - action_type = 'like' 的候选人 → 提取风格标签 → 统计高频关键词
    - action_type = 'skip' 的候选人 → 提取风格标签 → 作为不喜欢风格

    【返回】
    - preferred_style_tags: 偏好风格标签列表
    - preferred_style_weights: 偏好风格权重字典
    - disliked_style_tags: 不喜欢风格标签列表
    - total_like_count: 点赞总数
    - total_skip_count: 跳过总数
    """
    from match_domain.user_appearance_behavior_logger import list_user_appearance_behavior_logs

    # 1. 查询点赞候选人
    like_logs = list_user_appearance_behavior_logs(
        source_dsn=source_dsn,
        user_key=user_key,
        action_types=["like"],
        limit=100,
    )

    # 2. 统计风格标签频率
    keyword_counter: Counter[str] = Counter()

    for log in like_logs:
        keywords_raw = log.get("candidate_appearance_keywords_json")
        if not keywords_raw:
            continue

        # 解析风格标签
        keywords_list = []
        if isinstance(keywords_raw, str):
            try:
                keywords_list = json.loads(keywords_raw)
            except json.JSONDecodeError:
                continue
        elif isinstance(keywords_raw, list):
            keywords_list = keywords_raw

        for keyword_item in keywords_list:
            # 支持两种格式：["温柔"] 或 [{"label": "温柔"}]
            keyword_str = ""
            if isinstance(keyword_item, str):
                keyword_str = keyword_item.strip()
            elif isinstance(keyword_item, dict):
                keyword_str = str(keyword_item.get("label") or "").strip()

            if keyword_str:
                keyword_counter[keyword_str] += 1

    # 3. 计算权重（出现次数 / 总点赞数）
    total_like_count = len(like_logs)
    preferred_style_weights: dict[str, float] = {}

    if total_like_count > 0:
        for keyword, count in keyword_counter.items():
            if count >= 2:  # 至少出现2次才纳入偏好
                weight = round(count / total_like_count, 2)
                preferred_style_weights[keyword] = weight

    # 4. 提取偏好风格标签列表（权重排序）
    preferred_style_tags = sorted(
        preferred_style_weights.keys(),
        key=lambda k: preferred_style_weights[k],
        reverse=True,
    )[:10]  # 只保留前10个偏好风格

    # 5. 查询跳过候选人 → 学习不喜欢风格
    skip_logs = list_user_appearance_behavior_logs(
        source_dsn=source_dsn,
        user_key=user_key,
        action_types=["skip"],
        limit=50,
    )

    # 6. 统计不喜欢风格标签
    disliked_counter: Counter[str] = Counter()

    for log in skip_logs:
        keywords_raw = log.get("candidate_appearance_keywords_json")
        if not keywords_raw:
            continue

        keywords_list = []
        if isinstance(keywords_raw, str):
            try:
                keywords_list = json.loads(keywords_raw)
            except json.JSONDecodeError:
                continue
        elif isinstance(keywords_raw, list):
            keywords_list = keywords_raw

        for keyword_item in keywords_list:
            keyword_str = ""
            if isinstance(keyword_item, str):
                keyword_str = keyword_item.strip()
            elif isinstance(keyword_item, dict):
                keyword_str = str(keyword_item.get("label") or "").strip()

            if keyword_str:
                disliked_counter[keyword_str] += 1

    # 7. 提取不喜欢风格标签列表（出现次数排序）
    disliked_style_tags = sorted(
        disliked_counter.keys(),
        key=lambda k: disliked_counter[k],
        reverse=True,
    )[:5]  # 只保留前5个不喜欢风格

    return {
        "preferred_style_tags": preferred_style_tags,
        "preferred_style_weights": preferred_style_weights,
        "disliked_style_tags": disliked_style_tags,
        "total_like_count": total_like_count,
        "total_skip_count": len(skip_logs),
    }


def learn_feature_preference(
    *,
    source_dsn: str,
    user_key: str,
    behavior_table_name: str = "user_appearance_behavior_log",
) -> dict[str, Any]:
    """
    学习用户五官偏好

    【数据来源】
    - user_appearance_behavior_log 表
    - action_type = 'like' 的候选人 → 提取五官评分 → 计算平均值和标准差

    【计算逻辑】
    - preferred_eye_size_score_avg：点赞候选人眼睛大小评分的平均值
    - preferred_eye_size_score_std：点赞候选人眼睛大小评分的标准差
    - 用于匹配：候选人eye_size_score接近平均值 → 加分

    【返回】
    - preferred_eye_size_score_avg: 偏好眼睛大小平均分
    - preferred_eye_size_score_std: 偏好眼睛大小标准差
    - preferred_face_roundness_score_avg: 偏好脸型圆润度平均分
    - preferred_face_roundness_score_std: 偏好脸型圆润度标准差
    - preferred_jaw_definition_score_avg: 偏好下颌线清晰度平均分
    - preferred_youthfulness_score_avg: 偏好幼态感平均分
    """
    from match_domain.user_appearance_behavior_logger import list_user_appearance_behavior_logs

    # 1. 查询点赞候选人
    like_logs = list_user_appearance_behavior_logs(
        source_dsn=source_dsn,
        user_key=user_key,
        action_types=["like"],
        limit=100,
    )

    # 2. 提取五官评分列表
    eye_size_scores = []
    face_roundness_scores = []
    jaw_definition_scores = []
    youthfulness_scores = []

    for log in like_logs:
        eye_size = log.get("candidate_eye_size_score")
        if eye_size is not None and float(eye_size) > 0:
            eye_size_scores.append(float(eye_size))

        face_roundness = log.get("candidate_face_roundness_score")
        if face_roundness is not None and float(face_roundness) > 0:
            face_roundness_scores.append(float(face_roundness))

        jaw_definition = log.get("candidate_jaw_definition_score")
        if jaw_definition is not None and float(jaw_definition) > 0:
            jaw_definition_scores.append(float(jaw_definition))

        youthfulness = log.get("candidate_youthfulness_score")
        if youthfulness is not None and float(youthfulness) > 0:
            youthfulness_scores.append(float(youthfulness))

    # 3. 计算平均值和标准差
    def calc_avg_std(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        avg = sum(values) / len(values)
        if len(values) < 2:
            return round(avg, 2), 0.0
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        return round(avg, 2), round(std, 2)

    eye_size_avg, eye_size_std = calc_avg_std(eye_size_scores)
    face_roundness_avg, face_roundness_std = calc_avg_std(face_roundness_scores)
    jaw_definition_avg, jaw_definition_std = calc_avg_std(jaw_definition_scores)
    youthfulness_avg, youthfulness_std = calc_avg_std(youthfulness_scores)

    return {
        "preferred_eye_size_score_avg": eye_size_avg,
        "preferred_eye_size_score_std": eye_size_std,
        "preferred_face_roundness_score_avg": face_roundness_avg,
        "preferred_face_roundness_score_std": face_roundness_std,
        "preferred_jaw_definition_score_avg": jaw_definition_avg,
        "preferred_jaw_definition_score_std": jaw_definition_std,
        "preferred_youthfulness_score_avg": youthfulness_avg,
        "preferred_youthfulness_score_std": youthfulness_std,
    }


def update_user_appearance_preference(
    *,
    source_dsn: str,
    user_key: str,
    behavior_table_name: str = "user_appearance_behavior_log",
    preference_table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any]:
    """
    更新用户外貌偏好（综合风格偏好 + 五官偏好）

    【调用时机】
    - 用户点赞/跳过候选人后，实时更新偏好
    - 或定时批量更新偏好（每天一次）

    【返回】
    - saved: bool - 是否保存成功
    - user_key: str - 用户标识
    - preference_data: dict - 偏好数据
    """
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return {"saved": False, "error": "user_key_missing"}

    # 1. 学习风格偏好
    try:
        style_preference = learn_style_preference(
            source_dsn=source_dsn,
            user_key=normalized_user_key,
            behavior_table_name=behavior_table_name,
        )
    except Exception as e:
        _logger.error(
            "failed_to_learn_style_preference",
            extra={
                "user_key": normalized_user_key,
                "error": str(e),
            },
        )
        return {"saved": False, "error": f"learn_style_failed:{e}"}

    # 2. 学习五官偏好
    try:
        feature_preference = learn_feature_preference(
            source_dsn=source_dsn,
            user_key=normalized_user_key,
            behavior_table_name=behavior_table_name,
        )
    except Exception as e:
        _logger.error(
            "failed_to_learn_feature_preference",
            extra={
                "user_key": normalized_user_key,
                "error": str(e),
            },
        )
        return {"saved": False, "error": f"learn_feature_failed:{e}"}

    # 3. 合并偏好数据
    preference_data = {
        "user_key": normalized_user_key,
        "last_updated": datetime.now(),
        # 风格偏好
        "preferred_style_tags_json": style_preference.get("preferred_style_tags"),
        "preferred_style_weights_json": style_preference.get("preferred_style_weights"),
        "disliked_style_tags_json": style_preference.get("disliked_style_tags"),
        # 五官偏好
        "preferred_eye_size_score_avg": feature_preference.get("preferred_eye_size_score_avg"),
        "preferred_eye_size_score_std": feature_preference.get("preferred_eye_size_score_std"),
        "preferred_face_roundness_score_avg": feature_preference.get("preferred_face_roundness_score_avg"),
        "preferred_face_roundness_score_std": feature_preference.get("preferred_face_roundness_score_std"),
        "preferred_jaw_definition_score_avg": feature_preference.get("preferred_jaw_definition_score_avg"),
        "preferred_jaw_definition_score_std": feature_preference.get("preferred_jaw_definition_score_std"),
        "preferred_youthfulness_score_avg": feature_preference.get("preferred_youthfulness_score_avg"),
        "preferred_youthfulness_score_std": feature_preference.get("preferred_youthfulness_score_std"),
        # 统计信息
        "total_like_count": style_preference.get("total_like_count"),
        "total_skip_count": style_preference.get("total_skip_count"),
    }

    # 4. 写入用户偏好表
    try:
        _upsert_user_appearance_preferences(
            source_dsn=source_dsn,
            table_name=preference_table_name,
            preference_data=preference_data,
        )
    except Exception as e:
        _logger.error(
            "failed_to_upsert_preference",
            extra={
                "user_key": normalized_user_key,
                "error": str(e),
            },
        )
        return {"saved": False, "error": f"upsert_failed:{e}"}

    _logger.info(
        "user_appearance_preference_updated",
        extra={
            "user_key": normalized_user_key,
            "preferred_style_count": len(style_preference.get("preferred_style_tags", [])),
            "disliked_style_count": len(style_preference.get("disliked_style_tags", [])),
        },
    )

    return {
        "saved": True,
        "user_key": normalized_user_key,
        "preference_data": preference_data,
    }


def _upsert_user_appearance_preferences(
    *,
    source_dsn: str,
    table_name: str,
    preference_data: dict[str, Any],
) -> None:
    """
    写入用户偏好表（insert or update）
    """
    from profile_service import schema
    from profile_service.api import _connect_profile_db, _table_exists, _column_exists, release_profile_connection

    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        # 1. 检查表是否存在
        if not _table_exists(profile_conn, table_name):
            raise ValueError(f"table {table_name} was not found")

        user_key = preference_data.get("user_key")

        # 2. 检查是否存在
        existing_row = profile_conn.execute(
            f"""
            SELECT *
            FROM {schema.quote_mysql_ident(table_name)}
            WHERE {schema.quote_mysql_ident('user_key')} = ?
            LIMIT 1
            """,
            (user_key,),
        ).fetchone()

        # 3. 序列化JSON字段
        preferred_style_tags_json = preference_data.get("preferred_style_tags_json")
        if isinstance(preferred_style_tags_json, list):
            preferred_style_tags_json = json.dumps(preferred_style_tags_json, ensure_ascii=False)

        preferred_style_weights_json = preference_data.get("preferred_style_weights_json")
        if isinstance(preferred_style_weights_json, dict):
            preferred_style_weights_json = json.dumps(preferred_style_weights_json, ensure_ascii=False)

        disliked_style_tags_json = preference_data.get("disliked_style_tags_json")
        if isinstance(disliked_style_tags_json, list):
            disliked_style_tags_json = json.dumps(disliked_style_tags_json, ensure_ascii=False)

        # 4. 插入或更新
        if existing_row:
            # 更新
            profile_conn.execute(
                f"""
                UPDATE {schema.quote_mysql_ident(table_name)}
                SET
                    {schema.quote_mysql_ident('last_updated')} = ?,
                    {schema.quote_mysql_ident('preferred_style_tags_json')} = ?,
                    {schema.quote_mysql_ident('preferred_style_weights_json')} = ?,
                    {schema.quote_mysql_ident('disliked_style_tags_json')} = ?,
                    {schema.quote_mysql_ident('preferred_eye_size_score_avg')} = ?,
                    {schema.quote_mysql_ident('preferred_eye_size_score_std')} = ?,
                    {schema.quote_mysql_ident('preferred_face_roundness_score_avg')} = ?,
                    {schema.quote_mysql_ident('preferred_face_roundness_score_std')} = ?,
                    {schema.quote_mysql_ident('preferred_jaw_definition_score_avg')} = ?,
                    {schema.quote_mysql_ident('preferred_youthfulness_score_avg')} = ?,
                    {schema.quote_mysql_ident('total_like_count')} = ?,
                    {schema.quote_mysql_ident('total_skip_count')} = ?
                WHERE {schema.quote_mysql_ident('user_key')} = ?
                """,
                (
                    preference_data.get("last_updated"),
                    preferred_style_tags_json,
                    preferred_style_weights_json,
                    disliked_style_tags_json,
                    preference_data.get("preferred_eye_size_score_avg"),
                    preference_data.get("preferred_eye_size_score_std"),
                    preference_data.get("preferred_face_roundness_score_avg"),
                    preference_data.get("preferred_face_roundness_score_std"),
                    preference_data.get("preferred_jaw_definition_score_avg"),
                    preference_data.get("preferred_youthfulness_score_avg"),
                    preference_data.get("total_like_count"),
                    preference_data.get("total_skip_count"),
                    user_key,
                ),
            )
        else:
            # 插入
            profile_conn.execute(
                f"""
                INSERT INTO {schema.quote_mysql_ident(table_name)}
                (
                    {schema.quote_mysql_ident('user_key')},
                    {schema.quote_mysql_ident('last_updated')},
                    {schema.quote_mysql_ident('preferred_style_tags_json')},
                    {schema.quote_mysql_ident('preferred_style_weights_json')},
                    {schema.quote_mysql_ident('disliked_style_tags_json')},
                    {schema.quote_mysql_ident('preferred_eye_size_score_avg')},
                    {schema.quote_mysql_ident('preferred_eye_size_score_std')},
                    {schema.quote_mysql_ident('preferred_face_roundness_score_avg')},
                    {schema.quote_mysql_ident('preferred_face_roundness_score_std')},
                    {schema.quote_mysql_ident('preferred_jaw_definition_score_avg')},
                    {schema.quote_mysql_ident('preferred_youthfulness_score_avg')},
                    {schema.quote_mysql_ident('total_like_count')},
                    {schema.quote_mysql_ident('total_skip_count')}
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_key,
                    preference_data.get("last_updated"),
                    preferred_style_tags_json,
                    preferred_style_weights_json,
                    disliked_style_tags_json,
                    preference_data.get("preferred_eye_size_score_avg"),
                    preference_data.get("preferred_eye_size_score_std"),
                    preference_data.get("preferred_face_roundness_score_avg"),
                    preference_data.get("preferred_face_roundness_score_std"),
                    preference_data.get("preferred_jaw_definition_score_avg"),
                    preference_data.get("preferred_youthfulness_score_avg"),
                    preference_data.get("total_like_count"),
                    preference_data.get("total_skip_count"),
                ),
            )

        profile_conn.commit()
    finally:
        release_profile_connection(source_dsn, profile_conn)


def load_user_appearance_preferences(
    *,
    source_dsn: str,
    user_key: str,
    table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any] | None:
    """
    加载用户外貌偏好

    Args:
        source_dsn: 数据库连接字符串
        user_key: 用户标识
        table_name: 表名

    Returns:
        dict: 用户偏好数据（如果不存在返回None）
    """
    from profile_service import schema
    from profile_service.api import _connect_profile_db, _table_exists, release_profile_connection

    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return None

    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, table_name):
            return None

        row = profile_conn.execute(
            f"""
            SELECT *
            FROM {schema.quote_mysql_ident(table_name)}
            WHERE {schema.quote_mysql_ident('user_key')} = ?
            LIMIT 1
            """,
            (normalized_user_key,),
        ).fetchone()

        if not row:
            return None

        result = dict(row)

        # 解析JSON字段
        for json_field in [
            "preferred_style_tags_json",
            "preferred_style_weights_json",
            "disliked_style_tags_json",
        ]:
            raw_value = result.get(json_field)
            if isinstance(raw_value, str) and raw_value.strip():
                try:
                    result[json_field] = json.loads(raw_value)
                except json.JSONDecodeError:
                    pass

        return result
    finally:
        release_profile_connection(source_dsn, profile_conn)


__all__ = [
    "DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE",
    "learn_style_preference",
    "learn_feature_preference",
    "update_user_appearance_preference",
    "load_user_appearance_preferences",
]