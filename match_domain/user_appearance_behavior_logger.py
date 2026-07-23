"""User appearance behavior logger for learning preferences."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)

# 默认表名
DEFAULT_USER_APPEARANCE_BEHAVIOR_LOG_TABLE = "user_appearance_behavior_log"


def record_user_appearance_behavior(
    *,
    source_dsn: str,
    user_key: str,
    candidate_profile_id: int,
    action_type: str,  # 'like', 'skip', 'dislike', 'view'
    session_id: str | None = None,
    table_name: str = DEFAULT_USER_APPEARANCE_BEHAVIOR_LOG_TABLE,
) -> dict[str, Any]:
    """
    记录用户对候选人的外貌行为

    【记录内容】
    1. 行为类型（点赞、跳过、不喜欢）
    2. 候选人风格特征快照（用于学习风格偏好）
    3. 候选人五官特征快照（用于学习五官偏好）
    4. ❌ 不记录颜值评分（beauty_score）

    【设计原则】
    - beauty_score 是全局基础分，不参与个性化学习
    - 只记录风格和五官特征，用于个性化加分

    Args:
        source_dsn: 数据库连接字符串
        user_key: 用户标识
        candidate_profile_id: 候选人ID
        action_type: 行为类型（'like', 'skip', 'dislike', 'view'）
        session_id: 会话ID（可选）
        table_name: 表名（默认：user_appearance_behavior_log）

    Returns:
        dict: 记录结果（saved: bool, error: str | None）
    """
    # 1. 参数校验
    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return {"saved": False, "error": "user_key_missing"}

    normalized_candidate_id = int(candidate_profile_id or 0)
    if normalized_candidate_id <= 0:
        return {"saved": False, "error": "candidate_profile_id_invalid"}

    normalized_action = str(action_type or "").strip().lower()
    if normalized_action not in {"like", "skip", "dislike", "view"}:
        return {"saved": False, "error": f"invalid_action_type:{action_type}"}

    # 2. 获取候选人外貌特征
    try:
        candidate_features = _get_candidate_appearance_features(
            source_dsn=source_dsn,
            candidate_profile_id=normalized_candidate_id,
        )
    except Exception as e:
        _logger.warning(
            "failed_to_get_candidate_appearance_features",
            extra={
                "user_key": normalized_user_key,
                "candidate_profile_id": normalized_candidate_id,
                "error": str(e),
            },
        )
        return {"saved": False, "error": f"get_features_failed:{e}"}

    if not candidate_features:
        _logger.info(
            "candidate_appearance_features_not_found",
            extra={
                "user_key": normalized_user_key,
                "candidate_profile_id": normalized_candidate_id,
            },
        )
        # 候选人外貌特征不存在，仍然记录行为（但外貌特征为空）
        candidate_features = {}

    # 3. 写入行为日志
    try:
        _insert_behavior_log(
            source_dsn=source_dsn,
            table_name=table_name,
            user_key=normalized_user_key,
            candidate_profile_id=normalized_candidate_id,
            action_type=normalized_action,
            action_timestamp=datetime.now(),
            session_id=session_id,
            candidate_appearance_keywords_json=candidate_features.get("appearance_keywords_json"),
            candidate_appearance_summary=candidate_features.get("appearance_summary"),
            candidate_eye_size_score=candidate_features.get("eye_size_score"),
            candidate_face_roundness_score=candidate_features.get("face_roundness_score"),
            candidate_jaw_definition_score=candidate_features.get("jaw_definition_score"),
            candidate_youthfulness_score=candidate_features.get("youthfulness_score"),
        )
    except Exception as e:
        _logger.error(
            "failed_to_insert_behavior_log",
            extra={
                "user_key": normalized_user_key,
                "candidate_profile_id": normalized_candidate_id,
                "action_type": normalized_action,
                "error": str(e),
            },
        )
        return {"saved": False, "error": f"insert_failed:{e}"}

    _logger.info(
        "user_appearance_behavior_recorded",
        extra={
            "user_key": normalized_user_key,
            "candidate_profile_id": normalized_candidate_id,
            "action_type": normalized_action,
        },
    )

    return {
        "saved": True,
        "user_key": normalized_user_key,
        "candidate_profile_id": normalized_candidate_id,
        "action_type": normalized_action,
    }


def _get_candidate_appearance_features(
    *,
    source_dsn: str,
    candidate_profile_id: int,
) -> dict[str, Any] | None:
    """
    获取候选人外貌特征

    【获取内容】
    1. 风格特征：appearance_keywords_json、appearance_summary
    2. 五官特征：eye_size_score、face_roundness_score等
    3. ❌ 不获取beauty_score（颜值评分只做基础分）

    Returns:
        dict: 候选人外貌特征字典（如果不存在返回None）
    """
    from profile_service import (
        list_profile_face_attributes,
        list_profile_photo_feature_rows,
    )

    # 1. 获取候选人照片特征（风格特征）
    feature_rows = list_profile_photo_feature_rows(
        source_dsn=source_dsn,
        profile_ids=[candidate_profile_id],
        analysis_statuses=["done"],
        limit=1,
    )

    if not feature_rows:
        return None

    feature_row = dict(feature_rows[0])

    # 2. 获取候选人五官属性（五官特征）
    attribute_rows = list_profile_face_attributes(
        source_dsn=source_dsn,
        profile_ids=[candidate_profile_id],
    )

    attribute_row = dict(attribute_rows[0]) if attribute_rows else {}

    # 3. 合并外貌特征
    result = {
        # 风格特征
        "appearance_keywords_json": feature_row.get("appearance_keywords_json"),
        "appearance_summary": feature_row.get("appearance_summary"),
        # 五官特征
        "eye_size_score": attribute_row.get("eye_size_score"),
        "face_roundness_score": attribute_row.get("face_roundness_score"),
        "jaw_definition_score": attribute_row.get("jaw_definition_score"),
        "youthfulness_score": attribute_row.get("youthfulness_score"),
        # ❌ 不获取beauty_score（颜值评分只做基础分，不参与个性化学习）
    }

    return result


def _insert_behavior_log(
    *,
    source_dsn: str,
    table_name: str,
    user_key: str,
    candidate_profile_id: int,
    action_type: str,
    action_timestamp: datetime,
    session_id: str | None = None,
    candidate_appearance_keywords_json: Any | None = None,
    candidate_appearance_summary: str | None = None,
    candidate_eye_size_score: float | None = None,
    candidate_face_roundness_score: float | None = None,
    candidate_jaw_definition_score: float | None = None,
    candidate_youthfulness_score: float | None = None,
) -> None:
    """
    插入行为日志到数据库
    """
    from profile_service import schema
    from profile_service.api import _connect_profile_db, _table_exists, release_profile_connection

    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        # 1. 检查表是否存在
        if not _table_exists(profile_conn, table_name):
            _logger.warning(f"table {table_name} not found, skipping behavior log")
            raise ValueError(f"table {table_name} was not found")

        # 2. 序列化JSON字段
        keywords_json_str = None
        if candidate_appearance_keywords_json is not None:
            if isinstance(candidate_appearance_keywords_json, str):
                keywords_json_str = candidate_appearance_keywords_json
            else:
                keywords_json_str = json.dumps(
                    candidate_appearance_keywords_json,
                    ensure_ascii=False,
                )

        # 3. 插入数据
        profile_conn.execute(
            f"""
            INSERT INTO {schema.quote_mysql_ident(table_name)}
            (
              {schema.quote_mysql_ident('user_key')},
              {schema.quote_mysql_ident('candidate_profile_id')},
              {schema.quote_mysql_ident('action_type')},
              {schema.quote_mysql_ident('action_timestamp')},
              {schema.quote_mysql_ident('session_id')},
              {schema.quote_mysql_ident('candidate_appearance_keywords_json')},
              {schema.quote_mysql_ident('candidate_appearance_summary')},
              {schema.quote_mysql_ident('candidate_eye_size_score')},
              {schema.quote_mysql_ident('candidate_face_roundness_score')},
              {schema.quote_mysql_ident('candidate_jaw_definition_score')},
              {schema.quote_mysql_ident('candidate_youthfulness_score')}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_key,
                candidate_profile_id,
                action_type,
                action_timestamp,
                session_id,
                keywords_json_str,
                candidate_appearance_summary,
                candidate_eye_size_score,
                candidate_face_roundness_score,
                candidate_jaw_definition_score,
                candidate_youthfulness_score,
            ),
        )
        profile_conn.commit()
    finally:
        release_profile_connection(source_dsn, profile_conn)


def list_user_appearance_behavior_logs(
    *,
    source_dsn: str,
    user_key: str,
    action_types: list[str] | None = None,
    limit: int = 100,
    table_name: str = DEFAULT_USER_APPEARANCE_BEHAVIOR_LOG_TABLE,
) -> list[dict[str, Any]]:
    """
    查询用户外貌行为日志

    Args:
        source_dsn: 数据库连接字符串
        user_key: 用户标识
        action_types: 行为类型列表（如 ['like', 'skip']）
        limit: 查询数量限制
        table_name: 表名

    Returns:
        list: 行为日志列表
    """
    from profile_service import schema
    from profile_service.api import _connect_profile_db, _table_exists, release_profile_connection

    normalized_user_key = str(user_key or "").strip()
    if not normalized_user_key:
        return []

    normalized_limit = max(1, min(int(limit or 100), 1000))

    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, table_name):
            return []

        where_clauses = [f"{schema.quote_mysql_ident('user_key')} = ?"]
        params: list[Any] = [normalized_user_key]

        if action_types:
            normalized_types = [str(t).strip().lower() for t in action_types if str(t).strip()]
            if normalized_types:
                placeholders = ", ".join(["?"] * len(normalized_types))
                where_clauses.append(f"{schema.quote_mysql_ident('action_type')} IN ({placeholders})")
                params.extend(normalized_types)

        rows = profile_conn.execute(
            f"""
            SELECT *
            FROM {schema.quote_mysql_ident(table_name)}
            WHERE {" AND ".join(where_clauses)}
            ORDER BY {schema.quote_mysql_ident('action_timestamp')} DESC,
                     {schema.quote_mysql_ident('id')} DESC
            LIMIT ?
            """,
            tuple(params + [normalized_limit]),
        ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            # 解析JSON字段
            keywords_raw = payload.get("candidate_appearance_keywords_json")
            if isinstance(keywords_raw, str) and keywords_raw.strip():
                try:
                    payload["candidate_appearance_keywords_json"] = json.loads(keywords_raw)
                except json.JSONDecodeError:
                    pass
            result.append(payload)

        return result
    finally:
        release_profile_connection(source_dsn, profile_conn)


__all__ = [
    "DEFAULT_USER_APPEARANCE_BEHAVIOR_LOG_TABLE",
    "record_user_appearance_behavior",
    "list_user_appearance_behavior_logs",
]