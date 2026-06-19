#!/usr/bin/env python3
"""手动生成所有 Discovery 会话的摘要并写入向量库。

用途：
  因为所有用户都是虚拟用户，聊天记录也是模拟的，
  所以需要手动根据 discovery_agent_session_memory_items 表中的聊天记录
  生成摘要信息并写到向量库中。

执行方式：
  python manual_generate_summaries.py [--batch-size 10] [--limit 50] [--skip-vector]

参数说明：
  --batch-size: 每批处理的会话数量（默认10）
  --limit: 总共处理多少个会话（默认50，不指定则处理全部）
  --skip-vector: 跳过向量化步骤（仅生成摘要文本）

注意事项：
  1. 需要配置 HER_DISCOVERY_AGENT_API_KEY（LLM API Key）
  2. 需要配置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY（Embedding API Key）
  3. 需要数据库连接配置（PARTNER_DISCOVERY_DB）
  4. LLM 和 Embedding API 调用会产生费用
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass  # dotenv 不是必需的

# 导入核心模块
from match_domain.session_end_processor import (
    process_session_end,
    load_session_messages_from_db,
)
from external_systems.partner_discovery_system.discovery_system.storage import connect_db

# ============================================================================
# 配置常量
# ============================================================================

DISCOVERY_DSN = os.environ.get("PARTNER_DISCOVERY_DB") or ""
PERSONA_DSN = os.environ.get("HER_PERSONA_DB") or os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or ""

# conversation_summaries 表在 her 数据库中（PERSONA_MEMORY_MYSQL_SOURCE）
SUMMARY_DSN = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""

# ============================================================================
# 辅助函数
# ============================================================================

def get_all_sessions(dsn: str, limit: int | None = None) -> list[dict[str, Any]]:
    """查询所有 discovery 会话及其元信息。"""
    conn = connect_db(dsn)
    try:
        sql = """
        SELECT
            s.session_id,
            s.requester_id,
            s.profile_id,
            s.status,
            s.phase,
            s.created_at
        FROM discovery_agent_sessions s
        WHERE s.status = 'active' OR s.status = 'completed'
        ORDER BY s.created_at DESC
        """
        if limit is not None:
            sql += f" LIMIT {limit}"

        rows = conn.execute(sql).fetchall()
        sessions = []
        for row in rows:
            sessions.append({
                "session_id": str(row["session_id"]),
                "requester_id": int(row["requester_id"]),
                "profile_id": int(row["profile_id"]),
                "status": str(row["status"]),
                "phase": str(row["phase"]),
                "created_at": str(row["created_at"]),
            })
        return sessions
    finally:
        conn.close()


def count_session_messages(dsn: str, session_id: str) -> int:
    """统计会话的聊天记录数量。"""
    conn = connect_db(dsn)
    try:
        sql = """
        SELECT COUNT(*) as count
        FROM discovery_agent_session_memory_items
        WHERE session_id = ?
        """
        row = conn.execute(sql, (session_id,)).fetchone()
        return int(row["count"]) if row else 0
    finally:
        conn.close()


def check_summary_exists(dsn: str, conversation_id: str) -> bool:
    """检查摘要是否已存在（在 her 数据库中）。"""
    conn = connect_db(dsn)
    try:
        conn.execute("USE her")  # 确保连接到 her 数据库
        sql = """
        SELECT COUNT(*) as count
        FROM conversation_summaries
        WHERE conversation_id = ?
        """
        row = conn.execute(sql, (conversation_id,)).fetchone()
        return int(row["count"]) > 0 if row else False
    finally:
        conn.close()


def print_progress(current: int, total: int, session_id: str, message_count: int, skipped: bool = False):
    """打印进度信息。"""
    if skipped:
        status = "跳过（已有摘要）"
    else:
        status = "处理中"
    print(f"[{current}/{total}] {status} | session_id={session_id} | 消息数={message_count}")


# ============================================================================
# 主处理函数
# ============================================================================

async def process_single_session(
    session: dict[str, Any],
    discovery_dsn: str,
    skip_vector: bool = False,
) -> dict[str, Any]:
    """处理单个会话：生成摘要并写入向量库。"""

    session_id = session["session_id"]
    requester_id = session["requester_id"]
    profile_id = session["profile_id"]

    # 1. 加载聊天记录（检查数量）
    message_count = count_session_messages(discovery_dsn, session_id)
    if message_count < 2:
        return {"status": "skipped", "reason": "no_messages"}

    # 2. 直接调用 process_session_end()（完整流程）
    # 注意：不传递 dsn 参数，让函数使用默认值
    # load_session_messages_from_db() 会使用 PARTNER_DISCOVERY_DB
    # save_session_summary_text() 会使用 HER_PERSONA_DB 或 PERSONA_MEMORY_MYSQL_SOURCE
    result = await process_session_end(
        session_id=session_id,
        requester_id=requester_id,
        profile_id=profile_id,
        conversation_type="discovery",
        # dsn 参数不传递，让函数使用各自的默认值
    )

    if result.get("success"):
        return {
            "status": "success",
            "message_count": message_count,
            "summary_data": result.get("summary_data"),
            "quantifiable_fields": list(result.get("quantifiable_data", {}).keys()),
            "non_quantifiable_fields": list(result.get("non_quantifiable_data", {}).keys()),
            "saved_keys": result.get("saved_keys"),
            "vectorized_keys": result.get("vectorized_keys"),
        }
    else:
        return {
            "status": "failed",
            "reason": result.get("error"),
            "message": result.get("message"),
        }


async def process_all_sessions(
    batch_size: int = 10,
    limit: int | None = None,
    skip_vector: bool = False,
) -> dict[str, Any]:
    """批量处理所有会话。"""

    discovery_dsn = DISCOVERY_DSN
    summary_dsn = SUMMARY_DSN  # 使用 her 数据库

    if not discovery_dsn:
        raise ValueError("缺少 PARTNER_DISCOVERY_DB 环境变量")

    # 1. 查询所有会话
    all_sessions = get_all_sessions(discovery_dsn, limit)
    total_count = len(all_sessions)

    print(f"\n{'='*60}")
    print(f"开始处理 Discovery 会话摘要生成")
    print(f"{'='*60}")
    print(f"总会话数: {total_count}")
    print(f"批量大小: {batch_size}")
    print(f"处理限制: {limit if limit else '无限制（处理全部）'}")
    print(f"向量化: {'跳过' if skip_vector else '执行'}")
    print(f"{'='*60}\n")

    # 2. 批量处理
    results = {
        "total": total_count,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    for i, session in enumerate(all_sessions, 1):
        session_id = session["session_id"]
        message_count = count_session_messages(discovery_dsn, session_id)

        # 检查是否已有摘要（使用 her 数据库）
        exists = check_summary_exists(summary_dsn, session_id)
        print_progress(i, total_count, session_id, message_count, skipped=exists)

        if exists:
            results["skipped"] += 1
            results["details"].append({
                "session_id": session_id,
                "status": "skipped",
                "reason": "summary_exists",
            })
            continue

        # 处理单个会话
        try:
            result = await process_single_session(
                session=session,
                discovery_dsn=discovery_dsn,
                skip_vector=skip_vector,
            )

            if result["status"] == "success":
                results["success"] += 1
                print(f"  ✓ 成功 | 消息数={result['message_count']} | "
                      f"可量化={len(result.get('quantifiable_fields', []))} | "
                      f"不可量化={len(result.get('non_quantifiable_fields', []))} | "
                      f"向量={len(result.get('vectorized_keys', []))}")
            elif result["status"] == "skipped":
                results["skipped"] += 1
                print(f"  - 跳过 | 原因={result['reason']}")
            else:
                results["failed"] += 1
                print(f"  ✗ 失败 | 原因={result['reason']} | {result.get('message', '')}")

            results["details"].append({
                "session_id": session_id,
                **result,
            })

        except Exception as e:
            results["failed"] += 1
            print(f"  ✗ 异常 | {str(e)}")
            results["details"].append({
                "session_id": session_id,
                "status": "failed",
                "reason": "exception",
                "message": str(e),
            })

        # 每 batch_size 个会话暂停一下（避免 API 限流）
        if i % batch_size == 0:
            print(f"\n已处理 {i} 个会话，暂停 3 秒...")
            await asyncio.sleep(3)

    # 3. 打印总结
    print(f"\n{'='*60}")
    print(f"处理完成")
    print(f"{'='*60}")
    print(f"总数: {results['total']}")
    print(f"成功: {results['success']}")
    print(f"跳过: {results['skipped']}")
    print(f"失败: {results['failed']}")
    print(f"{'='*60}\n")

    return results


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="手动生成 Discovery 会话摘要")
    parser.add_argument("--batch-size", type=int, default=10, help="批量大小")
    parser.add_argument("--limit", type=int, default=None, help="处理限制")
    parser.add_argument("--skip-vector", action="store_true", help="跳过向量化")

    args = parser.parse_args()

    # 检查环境变量
    if not DISCOVERY_DSN:
        print("错误：缺少 PARTNER_DISCOVERY_DB 环境变量")
        sys.exit(1)

    api_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("警告：缺少 HER_DISCOVERY_AGENT_API_KEY 环境变量，LLM 调用可能失败")

    embedding_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not embedding_key and not args.skip_vector:
        print("警告：缺少 OPENAI_API_KEY 环境变量，向量化可能失败")

    # 执行处理
    results = asyncio.run(process_all_sessions(
        batch_size=args.batch_size,
        limit=args.limit,
        skip_vector=args.skip_vector,
    ))

    # 返回状态码
    if results["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()