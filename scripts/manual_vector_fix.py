#!/usr/bin/env python3
"""手动修复向量库写入失败的记录

使用方式：
# 修复单个用户的某个向量类型
python scripts/manual_vector_fix.py --user_id 123 --vector_type personality_traits

# 修复单个用户的所有向量类型
python scripts/manual_vector_fix.py --user_id 123 --all_types

# 修复所有失败记录
python scripts/manual_vector_fix.py --all

# 查看失败记录（不修复）
python scripts/manual_vector_fix.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger(__name__)


async def list_failed_records(max_retry_count: int = 3) -> None:
    """列出所有失败的向量记录"""

    _logger.info("查询失败的向量记录...")

    try:
        from match_domain.ai_merge_handler import query_failed_vector_records

        persona_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not persona_dsn:
            _logger.error("错误：缺少 PERSONA_MEMORY_MYSQL_SOURCE 环境变量")
            return

        failed_records = await query_failed_vector_records(
            dsn=persona_dsn,
            max_retry_count=max_retry_count,
        )

        if not failed_records:
            _logger.info("没有失败的向量记录")
            return

        _logger.info(f"发现 {len(failed_records)} 条失败记录:")
        for idx, record in enumerate(failed_records, 1):
            _logger.info(
                f"  [{idx}] user_id={record.get('requester_id')}, "
                f"key={record.get('summary_key')}, "
                f"text={record.get('summary_text')[:30]}..., "
                f"retry_count={record.get('retry_count')}, "
                f"error={record.get('error_message')[:50]}"
            )

    except Exception as exc:
        _logger.error(f"查询失败: error={exc}", exc_info=True)


async def fix_single_user(user_id: int, vector_type: str | None = None) -> None:
    """修复单个用户的向量"""

    _logger.info(
        f"修复单个用户的向量: user_id={user_id}, "
        f"vector_type={vector_type or '所有类型'}"
    )

    try:
        from match_domain.ai_merge_handler import (
            query_failed_vector_records,
            retry_vector_write,
        )

        persona_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not persona_dsn:
            _logger.error("错误：缺少 PERSONA_MEMORY_MYSQL_SOURCE 环境变量")
            return

        # 查询该用户的失败记录
        all_failed = await query_failed_vector_records(dsn=persona_dsn, max_retry_count=3)
        user_failed = [r for r in all_failed if r.get('requester_id') == user_id]

        if vector_type:
            user_failed = [r for r in user_failed if r.get('summary_key') == vector_type]

        if not user_failed:
            _logger.info(f"用户 {user_id} 没有失败的向量记录")
            return

        _logger.info(f"发现 {len(user_failed)} 条失败记录")

        # 尝试修复
        success_count = 0
        for record in user_failed:
            try:
                success = await retry_vector_write(record)
                if success:
                    success_count += 1
                    _logger.info(
                        f"修复成功: user_id={record.get('requester_id')}, "
                        f"key={record.get('summary_key')}"
                    )
                else:
                    _logger.error(
                        f"修复失败: user_id={record.get('requester_id')}, "
                        f"key={record.get('summary_key')}"
                    )
            except Exception as exc:
                _logger.error(
                    f"修复异常: user_id={record.get('requester_id')}, "
                    f"key={record.get('summary_key')}, error={exc}"
                )

        _logger.info(
            f"修复完成: "
            f"total={len(user_failed)}, success={success_count}, "
            f"failed={len(user_failed) - success_count}"
        )

    except Exception as exc:
        _logger.error(f"修复失败: error={exc}", exc_info=True)


async def fix_all_failed(max_retry_count: int = 3) -> None:
    """修复所有失败的向量"""

    _logger.info("修复所有失败的向量...")

    try:
        from match_domain.ai_merge_handler import (
            query_failed_vector_records,
            retry_vector_write,
        )

        persona_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
        if not persona_dsn:
            _logger.error("错误：缺少 PERSONA_MEMORY_MYSQL_SOURCE 环境变量")
            return

        failed_records = await query_failed_vector_records(
            dsn=persona_dsn,
            max_retry_count=max_retry_count,
        )

        if not failed_records:
            _logger.info("没有失败的向量记录")
            return

        _logger.info(f"发现 {len(failed_records)} 条失败记录")

        # 尝试修复
        success_count = 0
        for record in failed_records:
            try:
                success = await retry_vector_write(record)
                if success:
                    success_count += 1
                    _logger.info(
                        f"修复成功: user_id={record.get('requester_id')}, "
                        f"key={record.get('summary_key')}"
                    )
                else:
                    _logger.error(
                        f"修复失败: user_id={record.get('requester_id')}, "
                        f"key={record.get('summary_key')}"
                    )
            except Exception as exc:
                _logger.error(
                    f"修复异常: user_id={record.get('requester_id')}, "
                    f"key={record.get('summary_key')}, error={exc}"
                )

        _logger.info(
            f"修复完成: "
            f"total={len(failed_records)}, success={success_count}, "
            f"failed={len(failed_records) - success_count}"
        )

    except Exception as exc:
        _logger.error(f"修复失败: error={exc}", exc_info=True)


async def main(args: argparse.Namespace) -> None:
    """主函数"""

    _logger.info(f"开始执行: time={datetime.now().isoformat()}")

    if args.list:
        await list_failed_records(max_retry_count=args.max_retry)
    elif args.user_id:
        await fix_single_user(user_id=args.user_id, vector_type=args.vector_type)
    elif args.all:
        await fix_all_failed(max_retry_count=args.max_retry)
    else:
        _logger.error("错误：请指定操作参数（--list, --user_id, 或 --all）")
        sys.exit(1)

    _logger.info("执行完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="手动修复向量库写入失败的记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有失败的向量记录（不修复）",
    )

    parser.add_argument(
        "--user_id",
        type=int,
        help="修复单个用户的向量",
    )

    parser.add_argument(
        "--vector_type",
        type=str,
        help="指定向量类型（如 personality_traits）",
    )

    parser.add_argument(
        "--all_types",
        action="store_true",
        help="修复用户的所有向量类型",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="修复所有失败的向量记录",
    )

    parser.add_argument(
        "--max_retry",
        type=int,
        default=3,
        help="最大重试次数（默认3次）",
    )

    args = parser.parse_args()
    asyncio.run(main(args))