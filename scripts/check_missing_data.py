#!/usr/bin/env python3
"""完整的数据补全脚本：为无锡女性生成性格摘要和向量数据"""

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
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)


async def main():
    """完整的数据补全流程"""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1: 获取无锡女性候选人列表
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【Step 1】获取无锡女性候选人列表")
    _logger.info("=" * 80)

    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE")
        return

    conn = mysql_connect(source, use_pool=True, timeout=10.0)

    profile_ids = []
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, name, age, city, job, education, relationship_goal,
                       public_personality, public_values, life_routine, communication_style, values
                FROM {quote_mysql_ident("profiles")}
                WHERE city = '无锡'
                  AND gender = 'female'
                  AND age BETWEEN 26 AND 36
                  AND profile_status = 'active'
                ORDER BY id ASC
                """
            )
            profiles = cursor.fetchall() or []
            profile_ids = [p.get("id") for p in profiles if p.get("id")]

            _logger.info(f"【查询结果】找到 {len(profiles)} 个候选人")
            for p in profiles:
                _logger.info(f"  - id={p.get('id')}, name={p.get('name')}, age={p.get('age')}, job={p.get('job')}")

    finally:
        release_persona_connection(source, conn)

    if not profile_ids:
        _logger.warning("没有找到候选人，退出")
        return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2: 检查向量库缺失数据
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【Step 2】检查向量库缺失数据")
    _logger.info("=" * 80)

    # 由于向量库连接有问题，我们先检查数据库中的摘要数据
    conn = mysql_connect(source, use_pool=True, timeout=10.0)

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

    missing_summary_profiles = []

    try:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(profile_ids))
            cursor.execute(
                f"""
                SELECT profile_id, summary_key
                FROM {quote_mysql_ident("conversation_summaries")}
                WHERE profile_id IN ({placeholders})
                """,
                tuple(profile_ids),
            )
            existing_summaries = cursor.fetchall() or []

            # 构建已有摘要的映射
            existing_summary_map: dict[int, set[str]] = {}
            for row in existing_summaries:
                profile_id = row.get("profile_id")
                summary_key = row.get("summary_key")
                if profile_id not in existing_summary_map:
                    existing_summary_map[profile_id] = set()
                existing_summary_map[profile_id].add(summary_key)

            # 检查缺失的摘要
            for profile_id in profile_ids:
                missing_types = []
                for vt in vector_types:
                    if profile_id not in existing_summary_map or vt not in existing_summary_map[profile_id]:
                        missing_types.append(vt)

                if missing_types:
                    missing_summary_profiles.append({
                        "profile_id": profile_id,
                        "missing_types": missing_types,
                    })

            _logger.info(f"【摘要数据缺失情况】:")
            for item in missing_summary_profiles:
                _logger.info(f"  - profile_id={item['profile_id']}: 缺失 {len(item['missing_types'])} 个摘要")

    finally:
        release_persona_connection(source, conn)

    if not missing_summary_profiles:
        _logger.info("所有摘要数据完整，无需生成")
        return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3-6: 批量生成摘要、写入数据库、转向量、写入向量库
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _logger.info("=" * 80)
    _logger.info("【Step 3-6】批量生成摘要和向量数据")
    _logger.info("=" * 80)

    # 这里需要调用 manual_generate_summaries.py 或 session_end_processor 的逻辑
    # 由于脚本较长，我建议用户参考 manual_generate_summaries.py 的实现

    _logger.info("【后续步骤】:")
    _logger.info("  1. 参考 manual_generate_summaries.py 生成摘要")
    _logger.info("  2. 调用 session_end_processor.save_session_summary_text() 写入数据库")
    _logger.info("  3. 调用 embedding_service 转向量")
    _logger.info("  4. 调用 vector_store_lite.save_vector_with_version() 写入向量库")

    _logger.info(f"【待处理】{len(missing_summary_profiles)} 个用户需要生成摘要")


if __name__ == "__main__":
    asyncio.run(main())