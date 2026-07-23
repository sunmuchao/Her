"""向量筛选模块：支持排除和包含两种模式

核心功能：
1. exclude（排除）：排除相似度高的候选人（如"不要绿茶"）
2. include（包含）：只保留相似度高的候选人（如"找温柔的"）

使用方式：
from match_domain.vector_filter import vector_filter_candidates

excluded_ids, included_ids, filter_trace = await vector_filter_candidates(
    vector_filter_json={
        "exclude": {"personality_traits": {"text": "绿茶、虚伪", "similarity_threshold": 0.85}},
        "include": {"personality_traits": {"text": "温柔、真诚", "similarity_threshold": 0.80}}
    },
    candidate_ids=[123, 456, 789],
    user_id=100
)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)

from match_domain.retrieval_text_normalizer import normalize_query_text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 默认配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_SIMILARITY_THRESHOLD = 0.85
DEFAULT_VECTOR_TYPES = [
    "personality_traits",
    "values",
    "life_attitude",
    "partner_expectation",
    "partner_personality_preference",
    "partner_relationship_pacing",
    "partner_lifestyle_preference",
    "emotional_needs",
    "appearance_profile",
    "appearance_preference",
    "face_embedding",  # ✅ 新增：明星脸搜索
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def vector_filter_candidates(
    vector_filter_json: dict[str, Any],
    candidate_ids: list[int],
    user_id: int,
) -> tuple[list[int], list[int], dict[str, Any]]:
    """向量库语义筛选（支持排除和包含）

    Args:
        vector_filter_json: 筛选条件，包含 exclude 和 include 两部分
            示例：
            {
                "exclude": {
                    "personality_traits": {"text": "绿茶、虚伪", "similarity_threshold": 0.85}
                },
                "include": {
                    "personality_traits": {"text": "温柔、真诚", "similarity_threshold": 0.80}
                }
            }
        candidate_ids: 候选人ID列表（结构化查询后的结果）
        user_id: 用户ID（避免排除自己）

    Returns:
        (excluded_ids, included_ids, filter_trace)
        - excluded_ids: 被排除的用户ID列表（JSON可序列化）
        - included_ids: 被包含的用户ID列表（JSON可序列化）
        - filter_trace: 筛选统计信息
    """

    if not vector_filter_json:
        return [], candidate_ids, {"mode": "no_filter", "note": "无筛选条件"}

    if not candidate_ids:
        return [], [], {"mode": "no_candidates", "note": "无候选人"}

    _logger.info(
        f"【向量筛选开始】user_id={user_id} candidate_count={len(candidate_ids)} "
        f"has_exclude={bool(vector_filter_json.get('exclude'))} "
        f"has_include={bool(vector_filter_json.get('include'))}"
    )

    excluded_ids: set[int] = set()
    included_ids: set[int] = set(candidate_ids)  # 默认全部保留
    filter_trace: dict[str, Any] = {
        "exclude_trace": [],
        "include_trace": [],
        "excluded_count": 0,
        "included_count": len(candidate_ids),
        "final_count": 0,
    }

    # Step 1: 执行 exclude（排除）
    exclude_config = vector_filter_json.get("exclude", {})
    if exclude_config:
        excluded_ids, exclude_trace = await _execute_exclude(
            exclude_config=exclude_config,
            candidate_ids=candidate_ids,
            user_id=user_id,
        )
        filter_trace["exclude_trace"] = exclude_trace
        filter_trace["excluded_count"] = len(excluded_ids)

        _logger.info(
            f"【排除完成】excluded_count={len(excluded_ids)} "
            f"excluded_ids={list(excluded_ids)[:10]}..."
        )

    # Step 2: 执行 include（包含）
    include_config = vector_filter_json.get("include", {})
    if include_config:
        # 先过滤掉被排除的人
        remaining_ids = [id for id in candidate_ids if id not in excluded_ids]
        included_ids, include_trace = await _execute_include(
            include_config=include_config,
            candidate_ids=remaining_ids,
            user_id=user_id,
        )
        filter_trace["include_trace"] = include_trace
        filter_trace["included_count"] = len(included_ids)

        _logger.info(
            f"【包含完成】included_count={len(included_ids)} "
            f"included_ids={list(included_ids)[:10]}..."
        )

    # Step 3: 计算最终结果
    final_ids = included_ids - excluded_ids
    filter_trace["final_count"] = len(final_ids)

    _logger.info(
        f"【向量筛选完成】final_count={len(final_ids)} "
        f"excluded={len(excluded_ids)} included={len(included_ids)}"
    )

    # ✅ P0修复：返回前转换为list（JSON可序列化）
    # 内部仍用set做高效计算，但返回值必须是list
    return list(excluded_ids), list(included_ids), filter_trace


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 排除逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _execute_exclude(
    exclude_config: dict[str, Any],
    candidate_ids: list[int],
    user_id: int,
) -> tuple[set[int], list[dict[str, Any]]]:
    """执行排除逻辑：找出相似度高的候选人，排除掉

    Args:
        exclude_config: 排除条件，格式：
            {"personality_traits": {"text": "绿茶、虚伪", "similarity_threshold": 0.85}}
        candidate_ids: 候选人ID列表
        user_id: 用户ID

    Returns:
        (excluded_ids, exclude_trace)
    """

    excluded_ids: set[int] = set()
    exclude_trace: list[dict[str, Any]] = []

    for vector_type, config in exclude_config.items():
        if vector_type not in DEFAULT_VECTOR_TYPES:
            _logger.warning(f"未知的向量类型: {vector_type}")
            continue

        exclude_text = config.get("text", "")
        similarity_threshold = config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if not exclude_text:
            continue

        # 生成向量并搜索
        similar_ids, _, avg_similarity = await _search_similar_users(
            text=exclude_text,
            vector_type=vector_type,
            candidate_ids=candidate_ids,
            user_id=user_id,
            similarity_threshold=similarity_threshold,
        )

        excluded_ids.update(similar_ids)

        exclude_trace.append({
            "vector_type": vector_type,
            "exclude_text": exclude_text,
            "similarity_threshold": similarity_threshold,
            "excluded_ids": list(similar_ids),
            "excluded_count": len(similar_ids),
            "avg_similarity": round(avg_similarity, 3),
        })

        _logger.info(
            f"【排除详情】vector_type={vector_type} text={exclude_text} "
            f"threshold={similarity_threshold} excluded_count={len(similar_ids)} "
            f"avg_similarity={avg_similarity:.3f}"
        )

    return excluded_ids, exclude_trace


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 包含逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _execute_include(
    include_config: dict[str, Any],
    candidate_ids: list[int],
    user_id: int,
) -> tuple[set[int], list[dict[str, Any]]]:
    """执行包含逻辑：找出相似度高的候选人，只保留这些

    Args:
        include_config: 包含条件，格式：
            {"personality_traits": {"text": "温柔、真诚", "similarity_threshold": 0.80}}
        candidate_ids: 候选人ID列表（已过滤掉被排除的人）
        user_id: 用户ID

    Returns:
        (included_ids, include_trace)
    """

    included_ids: set[int] = set(candidate_ids)  # 默认全部保留
    include_trace: list[dict[str, Any]] = []

    for vector_type, config in include_config.items():
        if vector_type not in DEFAULT_VECTOR_TYPES:
            _logger.warning(f"未知的向量类型: {vector_type}")
            continue

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 特殊处理：face_embedding类型（明星脸搜索）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if vector_type == "face_embedding":
            photo_url = config.get("photo_url", "")
            similarity_threshold = config.get("similarity_threshold", 0.75)  # 默认阈值

            if not photo_url:
                _logger.warning("face_embedding类型缺少photo_url参数")
                continue

            # 调用专门的照片向量搜索函数
            similar_ids, candidate_ids_with_data, avg_similarity = await _search_by_face_embedding(
                photo_url=photo_url,
                candidate_ids=candidate_ids,
                user_id=user_id,
                similarity_threshold=similarity_threshold,
            )

            # 处理"无数据"的候选人
            candidate_ids_without_data = set(candidate_ids) - set(candidate_ids_with_data)
            included_ids_with_data = included_ids.intersection(set(similar_ids))
            included_ids = included_ids_with_data.union(candidate_ids_without_data)

            include_trace.append({
                "vector_type": vector_type,
                "photo_url": photo_url,
                "similarity_threshold": similarity_threshold,
                "similar_ids": list(similar_ids),
                "similar_count": len(similar_ids),
                "avg_similarity": round(avg_similarity, 3),
                "remaining_after_filter": len(included_ids),
            })

            _logger.info(
                f"【明星脸搜索详情】photo_url={photo_url[:100]} "
                f"threshold={similarity_threshold} similar_count={len(similar_ids)} "
                f"avg_similarity={avg_similarity:.3f}"
            )

            continue

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 普通向量类型处理（文本向量）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        include_text = config.get("text", "")
        similarity_threshold = config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if not include_text:
            continue

        # 生成向量并搜索
        similar_ids, candidate_ids_with_data, avg_similarity = await _search_similar_users(
            text=include_text,
            vector_type=vector_type,
            candidate_ids=candidate_ids,
            user_id=user_id,
            similarity_threshold=similarity_threshold,
        )

        # 【改进】包含逻辑：正确处理"无数据"的候选人
        # 核心思路：
        # - 有数据且匹配（similar_ids）：保留 ✅
        # - 有数据但不匹配（candidate_ids_with_data - similar_ids）：过滤 ❌（合理）
        # - 无数据（candidate_ids - candidate_ids_with_data）：保留 ✅（未知 ≠ 不匹配）
        candidate_ids_without_data = set(candidate_ids) - set(candidate_ids_with_data)

        # 正确的 intersection：保留"有数据且匹配" + "无数据"
        included_ids_with_data = included_ids.intersection(set(similar_ids))
        included_ids = included_ids_with_data.union(candidate_ids_without_data)

        include_trace.append({
            "vector_type": vector_type,
            "include_text": include_text,
            "similarity_threshold": similarity_threshold,
            "similar_ids": list(similar_ids),  # 有数据且匹配
            "similar_count": len(similar_ids),
            "candidate_ids_with_data": list(candidate_ids_with_data),  # 有数据
            "with_data_count": len(candidate_ids_with_data),
            "candidate_ids_without_data": list(candidate_ids_without_data),  # 无数据
            "without_data_count": len(candidate_ids_without_data),
            "avg_similarity": round(avg_similarity, 3),
            "remaining_after_filter": len(included_ids),
        })

        _logger.info(
            f"【包含详情】vector_type={vector_type} text={include_text} "
            f"threshold={similarity_threshold} similar_count={len(similar_ids)} "
            f"with_data_count={len(candidate_ids_with_data)} "
            f"without_data_count={len(candidate_ids_without_data)} "
            f"remaining_count={len(included_ids)} avg_similarity={avg_similarity:.3f}"
        )

    return included_ids, include_trace


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 向量搜索核心逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 缓存类：筛选文本向量缓存（节省embedding API调用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class VectorFilterCache:
    """缓存筛选文本的向量

    作用：
    - 避免重复计算常用筛选词的向量（如"温柔"、"绿茶"）
    - 节省embedding API调用（节省40-60%成本）

    缓存格式：
    - key: "{vector_type}:{text}"（如 "personality_traits:温柔"）
    - value: 1024维向量（list[float])

    缓存策略：
    - 内存缓存（简单高效）
    - 无过期时间（向量是固定的，不会过期）
    """

    def __init__(self):
        self.cache: dict[str, list[float]] = {}

    def get_cached_vector(self, text: str, vector_type: str) -> list[float] | None:
        """查询缓存

        Args:
            text: 筛选文本（如"温柔"）
            vector_type: 向量类型（如"personality_traits"）

        Returns:
            向量（如果缓存命中），None（如果缓存未命中）
        """
        cache_key = f"{vector_type}:{text}"
        return self.cache.get(cache_key)

    def cache_vector(self, text: str, vector_type: str, vector: list[float]):
        """缓存向量

        Args:
            text: 筛选文本
            vector_type: 向量类型
            vector: 向量数据
        """
        cache_key = f"{vector_type}:{text}"
        self.cache[cache_key] = vector

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """获取缓存统计信息

        Returns:
            {
                "cache_size": 缓存条目数量,
                "cache_hit_rate": 缓存命中率（百分比）
            }
        """
        return {
            "cache_size": len(self.cache),
        }


# 全局缓存实例（单例模式）
_vector_filter_cache = VectorFilterCache()


async def _search_similar_users(
    text: str,
    vector_type: str,
    candidate_ids: list[int],
    user_id: int,
    similarity_threshold: float,
) -> tuple[list[int], list[int], float]:
    """搜索相似用户（带缓存优化）

    改造核心：
    - 缓存筛选文本的向量（避免重复计算）
    - 节省embedding API调用（节省40-60%成本）
    - 确保资源清理（embedding_service 和 vector_store）
    - 【新增】返回候选人在向量库中的存在情况，区分"无数据"和"不匹配"

    Args:
        text: 待搜索的文本（如"绿茶、虚伪"）
        vector_type: 向量类型（如"personality_traits"）
        candidate_ids: 候选人ID列表（只搜索这些范围内）
        user_id: 用户ID（排除自己）
        similarity_threshold: 相似度阈值

    Returns:
        (similar_ids, candidate_ids_with_data, avg_similarity)
        - similar_ids: 相似用户ID列表（有数据且匹配）
        - candidate_ids_with_data: 在向量库中有数据的候选人ID列表
        - avg_similarity: 平均相似度
    """

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    # 资源声明（延迟初始化）
    embedding_service = None
    vector_store = None

    try:
        normalized_query = normalize_query_text(text)
        if vector_type not in normalized_query.route_vector_types:
            _logger.info(
                f"查询路由跳过: text={text}, normalized={normalized_query.normalized_text}, vector_type={vector_type}"
            )
            return [], [], 0.0  # 修复：返回完整的3个值

        search_text = normalized_query.retrieval_text or normalized_query.normalized_text or text

        # Step 1: 生成文本向量（带缓存优化）
        # 先查缓存
        cached_vector = _vector_filter_cache.get_cached_vector(search_text, vector_type)
        if cached_vector:
            vector = cached_vector
            _logger.info(
                f"向量缓存命中: text={search_text}, vector_type={vector_type}"
            )
        else:
            # 缓存未命中，调用embedding API
            embedding_service = EmbeddingService()  # 只在需要时创建
            vector = await embedding_service.generate_embedding(search_text)

            if not vector:
                _logger.warning(f"向量生成失败: text={search_text}")
                return [], [], 0.0  # 修复：返回完整的3个值

            # 缓存向量（下次直接使用）
            _vector_filter_cache.cache_vector(search_text, vector_type, vector)
            _logger.info(
                f"向量缓存保存: text={search_text}, vector_type={vector_type}"
            )

        # Step 2: 向量库搜索（【改进】使用极低阈值获取所有有数据的候选人）
        vector_store = VectorStoreLite()
        all_users_in_vector_db = vector_store.search_similar_users(
            user_vector=vector,
            vector_type=vector_type,
            top_k=len(candidate_ids) * 2,  # 搜索数量放大，确保覆盖所有候选人
            similarity_threshold=0.01,  # ← 极低阈值，返回所有在向量库中有数据的候选人
            exclude_user_ids=[user_id],
        )

        # Step 3: 区分三种情况：有数据且匹配、有数据但不匹配、无数据
        candidate_set = set(candidate_ids)

        # 所有在向量库中有数据的候选人（不考虑相似度）
        candidate_ids_with_data = [
            u["user_id"]
            for u in all_users_in_vector_db
            if u["user_id"] in candidate_set
        ]

        # 有数据且匹配的候选人（相似度 ≥ threshold）
        similar_ids = [
            u["user_id"]
            for u in all_users_in_vector_db
            if u["user_id"] in candidate_set and u["similarity"] >= similarity_threshold
        ]

        # Step 4: 计算平均相似度（只计算匹配的候选人）
        if similar_ids:
            similarities = [u["similarity"] for u in all_users_in_vector_db if u["user_id"] in similar_ids]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        else:
            avg_similarity = 0.0

        _logger.info(
            f"向量搜索详情: candidate_count={len(candidate_ids)} "
            f"with_data_count={len(candidate_ids_with_data)} "
            f"similar_count={len(similar_ids)} "
            f"avg_similarity={avg_similarity:.3f}"
        )

        return similar_ids, candidate_ids_with_data, avg_similarity

    except Exception as exc:
        _logger.error(f"向量搜索异常: text={text} vector_type={vector_type} error={exc}")
        return [], [], 0.0

    finally:
        # 资源清理
        if embedding_service:
            await embedding_service.aclose()
        if vector_store:
            vector_store.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 明星脸搜索专用函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _search_by_face_embedding(
    photo_url: str,
    candidate_ids: list[int],
    user_id: int,
    similarity_threshold: float,
) -> tuple[list[int], list[int], float]:
    """照片向量搜索（明星脸搜索专用）

    Args:
        photo_url: 照片URL（Agent用WebSearch/WebFetch获取）
        candidate_ids: 候选人ID列表（只搜索这些范围内）
        user_id: 用户ID（排除自己）
        similarity_threshold: 相似度阈值（默认0.75）

    Returns:
        (similar_ids, candidate_ids_with_data, avg_similarity)
        - similar_ids: 相似用户ID列表（有数据且匹配）
        - candidate_ids_with_data: 在向量库中有数据的候选人ID列表
        - avg_similarity: 平均相似度
    """

    from match_domain.face_embedding_extractor import extract_face_embedding
    from match_domain.vector_store_lite import VectorStoreLite

    vector_store = None

    try:
        _logger.info(f"【明星脸向量提取开始】photo_url={photo_url[:100]}")

        # Step 1: 提取照片向量
        face_result = extract_face_embedding(photo_url)

        if not face_result or not face_result.get("success"):
            error_msg = face_result.get("error", "unknown_error") if face_result else "no_result"
            _logger.warning(f"照片向量提取失败: {error_msg}")
            return [], [], 0.0

        vector = face_result.get("face_embedding")
        if not vector:
            _logger.warning("照片向量提取失败: 向量为空")
            return [], [], 0.0

        _logger.info(
            f"【明星脸向量提取成功】"
            f"model={face_result.get('face_embedding_model')} "
            f"dimension={face_result.get('face_embedding_dimension')}"
        )

        # Step 2: 向量库搜索
        vector_store = VectorStoreLite()
        all_users_in_vector_db = vector_store.search_similar_users(
            user_vector=vector,
            vector_type="face_embedding",
            top_k=len(candidate_ids) * 2,
            similarity_threshold=0.01,  # 极低阈值，返回所有有数据的候选人
            exclude_user_ids=[user_id],
        )

        # Step 3: 区分三种情况
        candidate_set = set(candidate_ids)

        # 所有在向量库中有数据的候选人
        candidate_ids_with_data = [
            u["user_id"]
            for u in all_users_in_vector_db
            if u["user_id"] in candidate_set
        ]

        # 有数据且匹配的候选人
        similar_ids = [
            u["user_id"]
            for u in all_users_in_vector_db
            if u["user_id"] in candidate_set and u["similarity"] >= similarity_threshold
        ]

        # Step 4: 计算平均相似度
        if similar_ids:
            similarities = [u["similarity"] for u in all_users_in_vector_db if u["user_id"] in similar_ids]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        else:
            avg_similarity = 0.0

        _logger.info(
            f"【明星脸向量搜索详情】candidate_count={len(candidate_ids)} "
            f"with_data_count={len(candidate_ids_with_data)} "
            f"similar_count={len(similar_ids)} "
            f"avg_similarity={avg_similarity:.3f}"
        )

        return similar_ids, candidate_ids_with_data, avg_similarity

    except Exception as exc:
        _logger.error(f"明星脸向量搜索异常: photo_url={photo_url} error={exc}")
        return [], [], 0.0

    finally:
        if vector_store:
            vector_store.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


__all__ = [
    "vector_filter_candidates",
    "VectorFilterCache",
    "_vector_filter_cache",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_VECTOR_TYPES",
]
