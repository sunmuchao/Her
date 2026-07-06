"""Face similarity search functionality."""

from __future__ import annotations

import json
from typing import Any

from outer_mysql_compat import MySQLCompatConnection
from outer_system_mysql_schema import mysql_database_connect, parse_mysql_dsn

from .face_embedding_extractor import compute_face_similarity


def list_profile_face_embeddings(
    source_dsn: str,
    *,
    profile_id: int | None = None,
    exclude_profile_id: int | None = None,
    photo_verification_level: str | None = None,
    is_primary_face: bool | None = None,
    cache_status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    查询人脸向量记录

    Args:
        source_dsn: 数据源DSN
        profile_id: 指定用户ID
        exclude_profile_id: 排除的用户ID
        photo_verification_level: 认证级别过滤
        is_primary_face: 是否只查询主人脸向量
        cache_status: 缓存状态过滤
        limit: 返回记录数量限制

    Returns:
        list: 人脸向量记录列表
    """
    config = parse_mysql_dsn(source_dsn)
    raw_conn = mysql_database_connect(config)
    conn = MySQLCompatConnection(raw_conn, config)

    try:
        query = "SELECT * FROM profile_face_embeddings WHERE 1=1"
        params: list[Any] = []

        if profile_id is not None:
            query += " AND profile_id = ?"
            params.append(int(profile_id))

        if exclude_profile_id is not None:
            query += " AND profile_id != ?"
            params.append(int(exclude_profile_id))

        if photo_verification_level:
            query += " AND photo_verification_level = ?"
            params.append(str(photo_verification_level))

        if is_primary_face is not None:
            query += " AND is_primary_face = ?"
            params.append(int(is_primary_face))

        if cache_status:
            query += " AND cache_status = ?"
            params.append(str(cache_status))

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(int(limit))

        rows = conn.execute(query, tuple(params)).fetchall()

        return [dict(row) for row in rows]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def upsert_profile_face_embedding(
    source_dsn: str,
    profile_id: int,
    *,
    face_embedding_json: str,
    face_embedding_model: str = "Facenet512",
    face_embedding_version: int = 1,
    face_embedding_dimension: int = 512,
    face_detection_confidence: float | None = None,
    face_bbox_json: str | None = None,
    photo_id: int | None = None,
    photo_url: str | None = None,
    photo_verification_level: str | None = None,
    is_primary_face: bool = True,
    cache_status: str = "computed",
    extraction_error: str | None = None,
) -> dict[str, Any]:
    """
    插入或更新人脸向量记录

    Args:
        source_dsn: 数据源DSN
        profile_id: 用户ID
        face_embedding_json: 人脸向量（JSON格式）
        face_embedding_model: 向量模型名称
        face_embedding_version: 向量版本号
        face_embedding_dimension: 向量维度
        face_detection_confidence: 人脸检测置信度
        face_bbox_json: 人脸位置边界框（JSON）
        photo_id: 来源照片ID
        photo_url: 来源照片URL
        photo_verification_level: 认证级别
        is_primary_face: 是否为主人脸向量
        cache_status: 缓存状态
        extraction_error: 提取错误信息

    Returns:
        dict: 插入或更新后的记录
    """
    config = parse_mysql_dsn(source_dsn)
    raw_conn = mysql_database_connect(config)
    conn = MySQLCompatConnection(raw_conn, config)

    try:
        # 检查是否已存在记录
        existing = conn.execute(
            "SELECT id FROM profile_face_embeddings WHERE profile_id = ? AND is_primary_face = ?",
            (int(profile_id), int(is_primary_face))
        ).fetchone()

        if existing:
            # 更新现有记录
            conn.execute(
                """
                UPDATE profile_face_embeddings
                SET face_embedding_json = ?,
                    face_embedding_model = ?,
                    face_embedding_version = ?,
                    face_embedding_dimension = ?,
                    face_detection_confidence = ?,
                    face_bbox_json = ?,
                    photo_id = ?,
                    photo_url = ?,
                    photo_verification_level = ?,
                    cache_status = ?,
                    extraction_error = ?,
                    updated_at = NOW()
                WHERE id = ?
                """,
                (
                    face_embedding_json,
                    face_embedding_model,
                    face_embedding_version,
                    face_embedding_dimension,
                    face_detection_confidence,
                    face_bbox_json,
                    photo_id,
                    photo_url,
                    photo_verification_level,
                    cache_status,
                    extraction_error,
                    existing["id"]
                )
            )
            result = conn.execute(
                "SELECT * FROM profile_face_embeddings WHERE id = ?",
                (existing["id"],)
            ).fetchone()
        else:
            # 插入新记录
            conn.execute(
                """
                INSERT INTO profile_face_embeddings (
                    profile_id,
                    face_embedding_json,
                    face_embedding_model,
                    face_embedding_version,
                    face_embedding_dimension,
                    face_detection_confidence,
                    face_bbox_json,
                    photo_id,
                    photo_url,
                    photo_verification_level,
                    is_primary_face,
                    cache_status,
                    extraction_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(profile_id),
                    face_embedding_json,
                    face_embedding_model,
                    face_embedding_version,
                    face_embedding_dimension,
                    face_detection_confidence,
                    face_bbox_json,
                    photo_id,
                    photo_url,
                    photo_verification_level,
                    int(is_primary_face),
                    cache_status,
                    extraction_error
                )
            )
            result = conn.execute(
                "SELECT * FROM profile_face_embeddings WHERE profile_id = ? AND is_primary_face = ? ORDER BY id DESC LIMIT 1",
                (int(profile_id), int(is_primary_face))
            ).fetchone()

        conn.commit()
        return dict(result) if result else {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def find_similar_faces(
    source_dsn: str,
    reference_profile_id: int,
    *,
    top_k: int = 10,
    similarity_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """
    查找与指定用户相似的其他用户

    Args:
        source_dsn: 数据源DSN
        reference_profile_id: 参考用户ID（要找跟谁相似的）
        top_k: 返回结果数量（默认10个）
        similarity_threshold: 相似度阈值（默认0.75 = 75%相似）

    Returns:
        list: 相似用户列表，包含profile_id、相似度评分等
    """
    # 1. 获取参考用户的人脸向量
    reference_embeddings = list_profile_face_embeddings(
        source_dsn=source_dsn,
        profile_id=reference_profile_id,
        is_primary_face=True
    )

    if not reference_embeddings:
        return []

    reference_embedding_json = reference_embeddings[0].get("face_embedding_json")
    if not reference_embedding_json:
        return []

    reference_embedding = json.loads(reference_embedding_json)

    # 2. 获取所有其他用户的人脸向量（批量）
    # 注意：这里可能需要分批处理，避免一次加载太多
    all_embeddings = list_profile_face_embeddings(
        source_dsn=source_dsn,
        exclude_profile_id=reference_profile_id,
        is_primary_face=True,
        cache_status="computed"
    )

    # 3. 计算相似度并排序
    similarity_scores = []
    for embedding_row in all_embeddings:
        candidate_profile_id = embedding_row["profile_id"]
        candidate_embedding_json = embedding_row.get("face_embedding_json")

        if not candidate_embedding_json:
            continue

        candidate_embedding = json.loads(candidate_embedding_json)

        # 计算相似度
        similarity = compute_face_similarity(reference_embedding, candidate_embedding)

        # 过滤低相似度结果
        if similarity >= similarity_threshold:
            similarity_scores.append({
                "profile_id": candidate_profile_id,
                "similarity_score": round(similarity, 4),  # 保留4位小数
                "photo_verification_level": embedding_row.get("photo_verification_level"),
                "face_detection_confidence": embedding_row.get("face_detection_confidence")
            })

    # 4. 视频认证用户优先（相似度额外提升10%）
    for score in similarity_scores:
        if score["photo_verification_level"] == "live_video_verified":
            # 视频认证用户优先
            score["similarity_score"] = min(1.0, score["similarity_score"] * 1.1)

    # 5. 按相似度排序
    similarity_scores.sort(key=lambda x: x["similarity_score"], reverse=True)

    # 6. 返回top_k结果
    return similarity_scores[:top_k]


__all__ = [
    "list_profile_face_embeddings",
    "upsert_profile_face_embedding",
    "find_similar_faces",
]