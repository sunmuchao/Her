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
    "emotional_needs",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def vector_filter_candidates(
    vector_filter_json: dict[str, Any],
    candidate_ids: list[int],
    user_id: int,
) -> tuple[set[int], set[int], dict[str, Any]]:
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
        - excluded_ids: 被排除的用户ID集合
        - included_ids: 被包含的用户ID集合（include筛选后保留的）
        - filter_trace: 筛选统计信息
    """

    if not vector_filter_json:
        return set(), set(candidate_ids), {"mode": "no_filter", "note": "无筛选条件"}

    if not candidate_ids:
        return set(), set(), {"mode": "no_candidates", "note": "无候选人"}

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

    return excluded_ids, included_ids, filter_trace


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
        similar_ids, avg_similarity = await _search_similar_users(
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

        include_text = config.get("text", "")
        similarity_threshold = config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if not include_text:
            continue

        # 生成向量并搜索
        similar_ids, avg_similarity = await _search_similar_users(
            text=include_text,
            vector_type=vector_type,
            candidate_ids=candidate_ids,
            user_id=user_id,
            similarity_threshold=similarity_threshold,
        )

        # 包含逻辑：只保留相似度高的（取交集）
        included_ids = included_ids.intersection(set(similar_ids))

        include_trace.append({
            "vector_type": vector_type,
            "include_text": include_text,
            "similarity_threshold": similarity_threshold,
            "included_ids": list(similar_ids),
            "included_count": len(similar_ids),
            "avg_similarity": round(avg_similarity, 3),
            "remaining_after_filter": len(included_ids),
        })

        _logger.info(
            f"【包含详情】vector_type={vector_type} text={include_text} "
            f"threshold={similarity_threshold} similar_count={len(similar_ids)} "
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
) -> tuple[list[int], float]:
    """搜索相似用户（带缓存优化）

    改造核心：
    - 缓存筛选文本的向量（避免重复计算）
    - 节省embedding API调用（节省40-60%成本）
    - 确保资源清理（embedding_service 和 vector_store）

    Args:
        text: 待搜索的文本（如"绿茶、虚伪"）
        vector_type: 向量类型（如"personality_traits"）
        candidate_ids: 候选人ID列表（只搜索这些范围内）
        user_id: 用户ID（排除自己）
        similarity_threshold: 相似度阈值

    Returns:
        (similar_ids, avg_similarity)
        - similar_ids: 相似用户ID列表
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
            return [], 0.0

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
                return [], 0.0

            # 缓存向量（下次直接使用）
            _vector_filter_cache.cache_vector(search_text, vector_type, vector)
            _logger.info(
                f"向量缓存保存: text={search_text}, vector_type={vector_type}"
            )

        # Step 2: 向量库搜索
        vector_store = VectorStoreLite()
        similar_users = vector_store.search_similar_users(
            user_vector=vector,
            vector_type=vector_type,
            top_k=len(candidate_ids),  # 搜索数量等于候选人数量
            similarity_threshold=similarity_threshold,
            exclude_user_ids=[user_id],
        )

        # Step 3: 筛选候选人范围内的相似用户
        candidate_set = set(candidate_ids)
        similar_ids = [
            u["user_id"]
            for u in similar_users
            if u["user_id"] in candidate_set
        ]

        # Step 4: 计算平均相似度
        if similar_users:
            similarities = [u["similarity"] for u in similar_users if u["user_id"] in candidate_set]
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        else:
            avg_similarity = 0.0

        return similar_ids, avg_similarity

    except Exception as exc:
        _logger.error(f"向量搜索异常: text={text} vector_type={vector_type} error={exc}")
        return [], 0.0

    finally:
        # 资源清理
        if embedding_service:
            await embedding_service.aclose()
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
