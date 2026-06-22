#!/usr/bin/env python3
"""只生成向量数据（摘要已经生成好了）"""

from __future__ import annotations

import argparse
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


async def generate_vectors_for_profiles(profile_ids: list[int], vector_types: list[str]):
    """为已有摘要的profile生成向量"""

    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident
    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE 或 HER_PERSONA_DB")
        return

    conn = mysql_connect(source, use_pool=True, timeout=10.0)

    success_count = 0
    error_count = 0

    try:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(profile_ids))
            vt_placeholders = ", ".join(["%s"] * len(vector_types))

            # 查询已有摘要
            cursor.execute(
                f"""
                SELECT profile_id, summary_key, summary_text
                FROM {quote_mysql_ident("conversation_summaries")}
                WHERE profile_id IN ({placeholders})
                  AND summary_key IN ({vt_placeholders})
                  AND vector_status = 'done'
                """,
                tuple(profile_ids) + tuple(vector_types),
            )
            summaries = cursor.fetchall() or []

            _logger.info(f"【查询摘要】找到 {len(summaries)} 条记录")

            # 初始化服务
            embedding_service = EmbeddingService()
            vector_store = VectorStoreLite()

            try:
                # 为每条摘要生成向量
                for summary in summaries:
                    profile_id = summary.get("profile_id")
                    vector_type = summary.get("summary_key")
                    summary_text = summary.get("summary_text")

                    try:
                        # 转向量
                        embedding = await embedding_service.generate_embedding(summary_text)

                        # 写入向量库
                        result = vector_store.save_vector_with_version(
                            user_id=profile_id,
                            vector_type=vector_type,
                            embedding=embedding,
                            raw_text=summary_text,
                            conversation_id=f"synthetic_{profile_id}",
                        )

                        if result.get("success"):
                            _logger.info(f"【写入向量库成功】profile_id={profile_id} vector_type={vector_type}")
                            success_count += 1
                        else:
                            _logger.error(f"【写入向量库失败】profile_id={profile_id} error={result.get('error')}")
                            error_count += 1

                    except Exception as exc:
                        _logger.error(f"【处理失败】profile_id={profile_id} vector_type={vector_type} error={exc}")
                        error_count += 1

            finally:
                await embedding_service.aclose()
                vector_store.close()

    finally:
        release_persona_connection(source, conn)

    _logger.info(f"【完成】成功 {success_count}，失败 {error_count}")
    return {"success_count": success_count, "error_count": error_count}


async def main():
    """主流程"""

    parser = argparse.ArgumentParser(description="为已有摘要生成向量数据")
    parser.add_argument("--batch-size", type=int, default=10, help="每批处理的数量")
    args = parser.parse_args()

    _logger.info("=" * 80)
    _logger.info("【开始】为已有摘要生成向量数据")
    _logger.info("=" * 80)

    profile_ids = [10002, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10016]
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

    result = await generate_vectors_for_profiles(profile_ids, vector_types)

    _logger.info("=" * 80)
    _logger.info("【完成】")
    _logger.info(f"  - 成功: {result.get('success_count', 0)}")
    _logger.info(f"  - 失败: {result.get('error_count', 0)}")
    _logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())