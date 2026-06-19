"""摘要加载模块：加载完整摘要信息

核心功能：
- 从 conversation_summaries 表加载用户的完整摘要
- 支持 5 种向量类型：personality_traits, values, life_attitude, partner_expectation, emotional_needs
- 返回结构化摘要字典，供 Agent 判断

使用方式：
from match_domain.summary_loader import load_complete_summary

summary_dict = await load_complete_summary(user_id=123)
# 返回：{"personality_traits": "性格温柔、内向", "values": "重视家庭", ...}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 默认配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


async def load_complete_summary(
    user_id: int,
    vector_types: list[str] | None = None,
) -> dict[str, str]:
    """加载完整摘要信息

    Args:
        user_id: 用户ID
        vector_types: 向量类型列表（可选，默认使用 DEFAULT_VECTOR_TYPES）

    Returns:
        摘要字典，格式：
        {
            "personality_traits": "性格温柔、内向",
            "values": "重视家庭、重视事业",
            "partner_expectation": "希望找个能理解工作忙碌的人",
            "life_attitude": "追求稳定、重视生活质量",
            "emotional_needs": "需要理解和支持"
        }

    注意：
        - 如果某个字段没有数据，不会出现在返回字典中
        - 返回的是最新摘要（按 created_at DESC 排序）
    """

    if vector_types is None:
        vector_types = DEFAULT_VECTOR_TYPES

    _logger.info(
        f"【摘要加载开始】user_id={user_id} vector_types={vector_types}"
    )

    summary_dict: dict[str, str] = {}

    # 并行加载多个摘要字段
    async def _load_single_summary(vector_type: str) -> tuple[str, str | None]:
        """加载单个摘要字段"""
        from match_domain.ai_merge_handler import load_historical_summary

        try:
            text = await load_historical_summary(user_id, vector_type)
            return vector_type, text
        except Exception as exc:
            _logger.warning(
                f"【摘要加载失败】user_id={user_id} vector_type={vector_type} error={exc}"
            )
            return vector_type, None

    # 使用 asyncio.gather 并行加载
    tasks = [_load_single_summary(vt) for vt in vector_types]
    results = await asyncio.gather(*tasks)

    # 构建摘要字典
    for vector_type, summary_text in results:
        if summary_text:
            summary_dict[vector_type] = summary_text

    _logger.info(
        f"【摘要加载完成】user_id={user_id} loaded_fields={list(summary_dict.keys())} "
        f"missing_fields={[vt for vt in vector_types if vt not in summary_dict]}"
    )

    return summary_dict


async def load_complete_summaries_batch(
    user_ids: list[int],
    vector_types: list[str] | None = None,
) -> dict[int, dict[str, str]]:
    """批量加载摘要信息

    Args:
        user_ids: 用户ID列表
        vector_types: 向量类型列表（可选）

    Returns:
        摘要字典，格式：
        {
            123: {"personality_traits": "性格温柔", "values": "重视家庭"},
            456: {"personality_traits": "性格内向", "values": "重视事业"},
            ...
        }

    注意：
        - 使用并行加载提高效率
        - 每个用户最多加载 5 个摘要字段
    """

    if vector_types is None:
        vector_types = DEFAULT_VECTOR_TYPES

    _logger.info(
        f"【批量摘要加载开始】user_count={len(user_ids)} vector_types={vector_types}"
    )

    summary_map: dict[int, dict[str, str]] = {}

    # 并行加载所有用户的摘要
    async def _load_user_summaries(user_id: int) -> tuple[int, dict[str, str]]:
        summary_dict = await load_complete_summary(user_id, vector_types)
        return user_id, summary_dict

    tasks = [_load_user_summaries(uid) for uid in user_ids]
    results = await asyncio.gather(*tasks)

    for user_id, summary_dict in results:
        summary_map[user_id] = summary_dict

    _logger.info(
        f"【批量摘要加载完成】user_count={len(summary_map)} "
        f"avg_fields_per_user={sum(len(s) for s in summary_map.values()) / len(summary_map) if summary_map else 0:.1f}"
    )

    return summary_map


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def build_summary_meta(summary_dict: dict[str, str]) -> dict[str, Any]:
    """构建摘要元数据

    Args:
        summary_dict: 摘要字典

    Returns:
        元数据字典，包含：
        - field_count: 字段数量
        - completeness: 完整度（有多少字段有数据）
        - has_data: 是否有数据
    """

    total_fields = len(DEFAULT_VECTOR_TYPES)
    loaded_fields = len(summary_dict)

    return {
        "field_count": loaded_fields,
        "total_fields": total_fields,
        "completeness": round(loaded_fields / total_fields, 2) if total_fields > 0 else 0,
        "has_data": bool(summary_dict),
        "loaded_fields": list(summary_dict.keys()),
        "missing_fields": [vt for vt in DEFAULT_VECTOR_TYPES if vt not in summary_dict],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


__all__ = [
    "load_complete_summary",
    "load_complete_summaries_batch",
    "build_summary_meta",
    "DEFAULT_VECTOR_TYPES",
]