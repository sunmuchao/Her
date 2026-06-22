#!/usr/bin/env python3
"""探索数据现状脚本

目标：
1. 查询数据库：这50个人有没有性格原始数据（MBTI、依恋等）
2. 查向量库：确认哪些vector_type需要补数据（personality_traits、values等）
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass  # dotenv 不是必需的

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)


async def explore_data_status():
    """探索数据现状"""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1: 查询数据库，获取这50个人的profile_id
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【Step 1】查询数据库：获取50个候选人的profile_id")
    _logger.info("=" * 80)

    # 从日志看，搜索条件是：无锡、女性、26-36岁、dating目标
    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE")
        return

    conn = mysql_connect(source, use_pool=True, timeout=10.0)

    try:
        with conn.cursor() as cursor:
            # 执行同样的搜索查询
            cursor.execute(
                f"""
                SELECT id
                FROM {quote_mysql_ident("profiles")}
                WHERE city = '无锡'
                  AND gender = 'female'
                  AND age BETWEEN 26 AND 36
                  AND relationship_goal IN ('dating', '认真恋爱', '结婚导向')
                  AND profile_status = 'active'
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall() or []
            profile_ids = [row.get("id") for row in rows if row.get("id")]

            _logger.info(f"【查询结果】找到 {len(profile_ids)} 个候选人")
            _logger.info(f"【前10个profile_id】{profile_ids[:10]}")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Step 2: 查询这些人的性格原始数据（persona表）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            _logger.info("=" * 80)
            _logger.info("【Step 2】查询persona表：检查性格原始数据")
            _logger.info("=" * 80)

            # 查询 persona 表
            placeholders = ", ".join(["%s"] * len(profile_ids))
            cursor.execute(
                f"""
                SELECT profile_id, self_personality_traits_json
                FROM {quote_mysql_ident("user_personas")}
                WHERE profile_id IN ({placeholders})
                """,
                tuple(profile_ids),
            )
            persona_rows = cursor.fetchall() or []

            # 统计有数据的人数
            has_personality_traits = 0
            has_any_data = 0

            persona_data_map: dict[int, dict[str, Any]] = {}
            for row in persona_rows:
                profile_id = row.get("profile_id")
                if profile_id:
                    persona_data_map[profile_id] = dict(row)
                    if row.get("self_personality_traits_json"):
                        has_personality_traits += 1
                        has_any_data += 1

            _logger.info(f"【persona表统计】总人数: {len(profile_ids)}")
            _logger.info(f"  - 有性格特质数据: {has_personality_traits} ({has_personality_traits/len(profile_ids)*100:.1f}%)")
            _logger.info(f"  - 有任何数据: {has_any_data} ({has_any_data/len(profile_ids)*100:.1f}%)")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Step 3: 查询conversation_summaries表（摘要数据）
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            _logger.info("=" * 80)
            _logger.info("【Step 3】查询conversation_summaries表：检查摘要数据")
            _logger.info("=" * 80)

            vector_types = [
                "personality_traits",
                "values",
                "life_attitude",
                "partner_expectation",
                "partner_personality_preference",
                "partner_relationship_pacing",
                "partner_lifestyle_preference",
                "emotional_needs",
            ]

            # 查询摘要表（conversation_summaries）
            cursor.execute(
                f"""
                SELECT profile_id, summary_key, summary_text
                FROM {quote_mysql_ident("conversation_summaries")}
                WHERE profile_id IN ({placeholders})
                """,
                tuple(profile_ids),
            )
            summary_rows = cursor.fetchall() or []

            # 统计每种summary_key的数据覆盖情况
            summary_count_by_type: dict[str, int] = {}
            for vt in vector_types:
                summary_count_by_type[vt] = 0

            for row in summary_rows:
                vt = row.get("summary_key")
                if vt in summary_count_by_type:
                    summary_count_by_type[vt] += 1

            _logger.info(f"【摘要表统计】总人数: {len(profile_ids)}")
            for vt, count in summary_count_by_type.items():
                _logger.info(f"  - {vt}: {count} ({count/len(profile_ids)*100:.1f}%)")

    finally:
        release_persona_connection(source, conn)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4: 查向量库（检查向量数据）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【Step 4】查向量库：检查向量数据")
    _logger.info("=" * 80)

    from match_domain.vector_store_lite import VectorStoreLite

    vector_store = VectorStoreLite()

    try:
        # 查询每个用户的向量数据
        vector_count_by_type: dict[str, int] = {}
        for vt in vector_types:
            vector_count_by_type[vt] = 0

        for profile_id in profile_ids[:10]:  # 先查前10个用户（避免太慢）
            vectors = vector_store.get_user_vectors(profile_id)
            for v in vectors:
                vt = v.get("vector_type")
                if vt in vector_count_by_type:
                    vector_count_by_type[vt] += 1

        _logger.info(f"【向量库统计】前10个用户:")
        for vt, count in vector_count_by_type.items():
            _logger.info(f"  - {vt}: {count} ({count/10*100:.1f}%)")

    finally:
        vector_store.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 总结：数据缺失情况
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【总结】数据缺失情况")
    _logger.info("=" * 80)

    _logger.info("【性格原始数据（persona表）】")
    if has_any_data < len(profile_ids):
        missing_count = len(profile_ids) - has_any_data
        _logger.info(f"  ❌ 缺失: {missing_count} 人 ({missing_count/len(profile_ids)*100:.1f}%)")
    else:
        _logger.info(f"  ✅ 完整: {has_any_data} 人")

    _logger.info("【摘要数据（conversation_summaries表）】")
    missing_types = []
    for vt, count in summary_count_by_type.items():
        if count < len(profile_ids):
            missing_types.append(vt)
            _logger.info(f"  ❌ {vt}: 缺失 {len(profile_ids) - count} 条")
        else:
            _logger.info(f"  ✅ {vt}: 完整 {count} 条")

    if missing_types:
        _logger.info(f"  🔧 需要补数据的vector_type: {missing_types}")

    _logger.info("【向量数据（向量库）】")
    _logger.info(f"  ⚠️  向量库数据缺失严重（日志显示50个人都没有向量数据）")

    return {
        "profile_ids": profile_ids,
        "persona_data_map": persona_data_map,
        "has_any_data": has_any_data,
        "missing_types": missing_types,
    }


if __name__ == "__main__":
    asyncio.run(explore_data_status())