#!/usr/bin/env python3
"""手动处理 pending 状态的摘要记录（向量化）

使用方式：
  # 处理所有 pending 记录
  python scripts/process_pending_vectors.py --all

  # 处理特定用户的 pending 记录
  python scripts/process_pending_vectors.py --user-id 501

  # 查看所有 pending 记录（不处理）
  python scripts/process_pending_vectors.py --list

  # 处理指定数量的记录（批量处理）
  python scripts/process_pending_vectors.py --batch 10
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pymysql

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger(__name__)


async def list_pending_records(limit: int = 100) -> None:
    """列出所有 pending 状态的摘要记录"""

    _logger.info("查询 pending 状态的摘要记录...")

    try:
        conn = pymysql.connect(
            host='127.0.0.1',
            port=3307,
            user='root',
            password='',
            charset='utf8mb4',
            database='her'
        )

        cursor = conn.cursor()

        # 查询总数
        count_sql = "SELECT COUNT(*) FROM conversation_summaries WHERE vector_status = 'pending'"
        cursor.execute(count_sql)
        total_count = cursor.fetchone()[0]

        _logger.info(f"Pending 记录总数: {total_count}")

        # 查询记录
        data_sql = """
        SELECT
            requester_id,
            summary_key,
            summary_text,
            conversation_id,
            created_at
        FROM conversation_summaries
        WHERE vector_status = 'pending'
        ORDER BY created_at DESC
        LIMIT %s
        """

        cursor.execute(data_sql, (limit,))
        rows = cursor.fetchall()

        if rows:
            _logger.info(f"查询到 {len(rows)} 条 pending 记录:")
            for i, row in enumerate(rows, 1):
                _logger.info(
                    f"  [{i}] user_id={row[0]}, key={row[1]}, "
                    f"text={row[2][:30]}..., conversation_id={row[3]}"
                )
        else:
            _logger.info("没有 pending 状态的记录")

        conn.close()

    except Exception as exc:
        _logger.error(f"查询失败: error={exc}", exc_info=True)


async def process_pending_records(
    user_id: int | None = None,
    batch_size: int | None = None,
    limit: int = 100,
) -> None:
    """处理 pending 状态的摘要记录（生成向量并更新状态）"""

    _logger.info(
        f"开始处理 pending 记录: user_id={user_id}, "
        f"batch_size={batch_size}, limit={limit}"
    )

    try:
        # 1. 查询 pending 记录
        conn = pymysql.connect(
            host='127.0.0.1',
            port=3307,
            user='root',
            password='',
            charset='utf8mb4',
            database='her'
        )

        cursor = conn.cursor()

        # 构建查询条件
        where_clause = "vector_status = 'pending'"
        params = []

        if user_id:
            where_clause += " AND requester_id = %s"
            params.append(user_id)

        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM conversation_summaries WHERE {where_clause}"
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()[0]

        _logger.info(f"发现 {total_count} 条 pending 记录")

        if total_count == 0:
            _logger.info("没有需要处理的 pending 记录")
            conn.close()
            return

        # 查询记录（限制数量）
        limit_value = batch_size if batch_size else limit
        data_sql = f"""
        SELECT
            requester_id,
            summary_key,
            summary_text,
            conversation_id
        FROM conversation_summaries
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        """

        params.append(limit_value)
        cursor.execute(data_sql, params)
        rows = cursor.fetchall()

        conn.close()

        _logger.info(f"准备处理 {len(rows)} 条记录")

        # 2. 批量处理：生成向量并存储
        from match_domain.embedding_service import EmbeddingService
        from match_domain.vector_store_lite import VectorStoreLite

        embedding_service = EmbeddingService(model_name="text-embedding-v3")
        vector_store = VectorStoreLite()

        success_count = 0
        failed_count = 0

        for i, row in enumerate(rows, 1):
            requester_id, summary_key, summary_text, conversation_id = row

            _logger.info(
                f"[{i}/{len(rows)}] 处理: user_id={requester_id}, "
                f"key={summary_key}, text={summary_text[:30]}..."
            )

            try:
                # 生成向量
                embedding = await embedding_service.generate_embedding(summary_text)

                if not embedding or len(embedding) == 0:
                    raise ValueError("向量生成失败：返回空向量")

                # 存储向量
                result = vector_store.save_vector_with_version(
                    user_id=requester_id,
                    vector_type=summary_key,
                    embedding=embedding,
                    raw_text=summary_text,
                    conversation_id=conversation_id,
                )

                # 更新状态
                new_status = 'done' if result.get("success") else 'failed'

                conn = pymysql.connect(
                    host='127.0.0.1',
                    port=3307,
                    user='root',
                    password='',
                    charset='utf8mb4',
                    database='her'
                )

                update_cursor = conn.cursor()
                update_sql = """
                UPDATE conversation_summaries
                SET vector_status = %s, updated_at = NOW()
                WHERE requester_id = %s AND summary_key = %s AND conversation_id = %s
                """
                update_cursor.execute(
                    update_sql,
                    (new_status, requester_id, summary_key, conversation_id)
                )
                conn.commit()
                conn.close()

                if result.get("success"):
                    success_count += 1
                    _logger.info(f"✅ 成功: user_id={requester_id}, key={summary_key}")
                else:
                    failed_count += 1
                    _logger.error(
                        f"❌ 失败: user_id={requester_id}, key={summary_key}, "
                        f"error={result.get('error')}"
                    )

            except Exception as exc:
                failed_count += 1
                _logger.error(
                    f"❌ 异常: user_id={requester_id}, key={summary_key}, "
                    f"error={exc}", exc_info=True
                )

                # 更新状态为 failed
                try:
                    conn = pymysql.connect(
                        host='127.0.0.1',
                        port=3307,
                        user='root',
                        password='',
                        charset='utf8mb4',
                        database='her'
                    )

                    update_cursor = conn.cursor()
                    update_sql = """
                    UPDATE conversation_summaries
                    SET vector_status = 'failed', updated_at = NOW()
                    WHERE requester_id = %s AND summary_key = %s AND conversation_id = %s
                    """
                    update_cursor.execute(
                        update_sql,
                        (requester_id, summary_key, conversation_id)
                    )
                    conn.commit()
                    conn.close()
                except Exception as update_exc:
                    _logger.error(f"更新状态失败: {update_exc}")

        # 3. 输出处理结果
        _logger.info(
            f"处理完成: "
            f"total={len(rows)}, success={success_count}, failed={failed_count}"
        )

        if total_count > len(rows):
            remaining = total_count - len(rows)
            _logger.info(f"还有 {remaining} 条 pending 记录未处理")

    except Exception as exc:
        _logger.error(f"处理失败: error={exc}", exc_info=True)


async def main(args: argparse.Namespace) -> None:
    """主函数"""

    _logger.info(f"开始执行: time={datetime.now().isoformat()}")

    if args.list:
        await list_pending_records(limit=args.limit)
    elif args.all:
        await process_pending_records(limit=args.limit)
    elif args.user_id:
        await process_pending_records(user_id=args.user_id, limit=args.limit)
    elif args.batch:
        await process_pending_records(batch_size=args.batch, limit=args.limit)
    else:
        _logger.error("错误：请指定操作参数（--list, --all, --user-id, 或 --batch）")
        sys.exit(1)

    _logger.info("执行完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="手动处理 pending 状态的摘要记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有 pending 状态的记录（不处理）",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="处理所有 pending 状态的记录",
    )

    parser.add_argument(
        "--user-id",
        type=int,
        help="处理指定用户的 pending 记录",
    )

    parser.add_argument(
        "--batch",
        type=int,
        help="批量处理指定数量的记录",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="查询数量限制（默认100）",
    )

    args = parser.parse_args()
    asyncio.run(main(args))
