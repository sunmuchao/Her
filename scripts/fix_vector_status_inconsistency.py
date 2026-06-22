#!/usr/bin/env python3
"""修复数据不一致问题：MySQL显示done但向量库无数据

用途：
  修复MySQL中vector_status='done'但向量库没有对应数据的问题

执行方式：
  python scripts/fix_vector_status_inconsistency.py [--profile-ids 6092,2379,6566]

参数说明：
  --profile-ids: 指定要修复的profile_id列表（可选，默认修复所有不一致数据）

修复逻辑：
  1. 查询MySQL中vector_status='done'的记录
  2. 检查向量库是否有对应数据
  3. 如果没有，重新生成向量并写入
  4. 更新状态为'done'（如果成功）或'failed'（如果失败）
"""

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: 查询不一致数据
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def find_inconsistent_data(
    profile_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """查找MySQL显示done但向量库无数据的记录"""

    from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
    from outer_system_mysql_schema import quote_mysql_ident
    from match_domain.vector_store_lite import VectorStoreLite

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
    if not source:
        _logger.error("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE 或 HER_PERSONA_DB")
        return []

    conn = mysql_connect(source, use_pool=True, timeout=10.0)
    vector_store = VectorStoreLite()

    inconsistent_records: list[dict[str, Any]] = []

    try:
        with conn.cursor() as cursor:
            # 查询vector_status='done'的记录
            if profile_ids:
                placeholders = ", ".join(["%s"] * len(profile_ids))
                sql = f"""
                    SELECT requester_id, summary_key, summary_text, conversation_id
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE requester_id IN ({placeholders})
                    AND vector_status = 'done'
                """
                cursor.execute(sql, tuple(profile_ids))
            else:
                sql = f"""
                    SELECT requester_id, summary_key, summary_text, conversation_id
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE vector_status = 'done'
                """
                cursor.execute(sql)

            records = cursor.fetchall() or []

            _logger.info(f"【查询完成】找到 {len(records)} 条 vector_status='done' 的记录")

            # 检查向量库是否有对应数据
            for record in records:
                user_id = record.get("requester_id")
                vector_type = record.get("summary_key")
                summary_text = record.get("summary_text")
                conversation_id = record.get("conversation_id")

                # 查询向量库
                vectors = vector_store.get_user_vectors(user_id, vector_type)

                if not vectors:
                    # 向量库无数据，记录为不一致
                    inconsistent_records.append({
                        "user_id": user_id,
                        "vector_type": vector_type,
                        "summary_text": summary_text,
                        "conversation_id": conversation_id,
                    })
                    _logger.warning(
                        f"【不一致】user_id={user_id} vector_type={vector_type} "
                        f"MySQL显示done但向量库无数据"
                    )

        _logger.info(f"【检查完成】找到 {len(inconsistent_records)} 条不一致记录")

    finally:
        release_persona_connection(source, conn)
        vector_store.close()

    return inconsistent_records


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: 修复不一致数据（重新生成向量）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fix_single_record(
    user_id: int,
    vector_type: str,
    summary_text: str,
    conversation_id: str,
) -> bool:
    """修复单条记录：重新生成向量并写入"""

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite
    from match_domain.ai_merge_handler import update_vector_status

    try:
        # 先标记为pending（避免状态不一致）
        await update_vector_status(
            user_id=user_id,
            vector_type=vector_type,
            status='pending',
        )

        # 初始化服务
        embedding_service = EmbeddingService()
        vector_store = VectorStoreLite()

        # 生成向量
        embedding = await embedding_service.generate_embedding(summary_text)

        # 写入向量库
        result = vector_store.save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=embedding,
            raw_text=summary_text,
            conversation_id=conversation_id,
        )

        # 关闭连接
        await embedding_service.aclose()
        vector_store.close()

        # 更新状态
        if result.get("success"):
            # 成功：更新为done
            await update_vector_status(
                user_id=user_id,
                vector_type=vector_type,
                status='done',
            )
            _logger.info(
                f"【修复成功】user_id={user_id} vector_type={vector_type} status=done"
            )
            return True
        else:
            # 失败：更新为failed
            await update_vector_status(
                user_id=user_id,
                vector_type=vector_type,
                status='failed',
                error_message=result.get('error', '向量写入失败'),
            )
            _logger.error(
                f"【修复失败】user_id={user_id} vector_type={vector_type} "
                f"status=failed error={result.get('error')}"
            )
            return False

    except Exception as exc:
        _logger.error(
            f"【修复异常】user_id={user_id} vector_type={vector_type} error={exc}"
        )

        # 异常时也要标记为failed
        try:
            await update_vector_status(
                user_id=user_id,
                vector_type=vector_type,
                status='failed',
                error_message=str(exc)[:200],
            )
        except:
            pass  # 状态更新失败不影响主流程

        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: 批量修复
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fix_batch(
    inconsistent_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """批量修复不一致数据"""

    success_count = 0
    failed_count = 0

    for record in inconsistent_records:
        user_id = record.get("user_id")
        vector_type = record.get("vector_type")
        summary_text = record.get("summary_text")
        conversation_id = record.get("conversation_id")

        success = await fix_single_record(
            user_id=user_id,
            vector_type=vector_type,
            summary_text=summary_text,
            conversation_id=conversation_id,
        )

        if success:
            success_count += 1
        else:
            failed_count += 1

    _logger.info(f"【修复完成】成功 {success_count}，失败 {failed_count}")

    return {
        "total": len(inconsistent_records),
        "success_count": success_count,
        "failed_count": failed_count,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主流程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def main():
    """主流程"""

    # 解析参数
    parser = argparse.ArgumentParser(description="修复数据不一致问题")
    parser.add_argument(
        "--profile-ids",
        type=str,
        help="指定要修复的profile_id列表（逗号分隔）",
    )
    args = parser.parse_args()

    # 解析profile_ids参数
    profile_ids = None
    if args.profile_ids:
        profile_ids = [int(pid.strip()) for pid in args.profile_ids.split(",")]
        _logger.info(f"【指定修复】profile_ids={profile_ids}")

    _logger.info("=" * 80)
    _logger.info("【开始】修复数据不一致问题")
    _logger.info("=" * 80)

    # Step 1: 查找不一致数据
    inconsistent_records = await find_inconsistent_data(profile_ids)

    if not inconsistent_records:
        _logger.info("【结束】没有不一致数据")
        return

    # Step 2: 批量修复
    result = await fix_batch(inconsistent_records)

    # Step 3: 总结
    _logger.info("=" * 80)
    _logger.info("【完成】")
    _logger.info(f"  - 检查记录数: {result.get('total')}")
    _logger.info(f"  - 修复成功: {result.get('success_count')}")
    _logger.info(f"  - 修复失败: {result.get('failed_count')}")
    _logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())