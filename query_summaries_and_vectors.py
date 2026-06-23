#!/usr/bin/env python3
"""查看摘要内容和向量库内容的查询工具。

执行方式：
  python query_summaries_and_vectors.py [--user-id 10015] [--conversation-id xxx]
"""

import argparse
import pymysql
import sys
from pathlib import Path
from typing import Optional

repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pymilvus import MilvusClient
from match_domain.vector_store_lite import MILVUS_LITE_DB, COLLECTION_NAME

# ============================================================================
# 查询摘要内容
# ============================================================================

def query_summaries(user_id: Optional[int] = None, conversation_id: Optional[str] = None, limit: int = 20):
    """查询 conversation_summaries 表中的摘要数据。"""

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
    where_clauses = []
    params = []

    if user_id:
        where_clauses.append("requester_id = ?")
        params.append(user_id)

    if conversation_id:
        where_clauses.append("conversation_id = ?")
        params.append(conversation_id)

    where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

    # 查询总数
    count_sql = f"SELECT COUNT(*) FROM conversation_summaries{where_sql}"
    cursor.execute(count_sql, params)
    total_count = cursor.fetchone()[0]

    print(f"\n{'='*60}")
    print(f"摘要数据查询结果")
    print(f"{'='*60}")
    print(f"摘要总数: {total_count}")
    print(f"查询条件: user_id={user_id}, conversation_id={conversation_id}")
    print(f"{'='*60}\n")

    # 查询数据
    data_sql = f"""
    SELECT
        conversation_id,
        requester_id,
        profile_id,
        summary_key,
        summary_text,
        vector_status,
        created_at,
        updated_at
    FROM conversation_summaries
    {where_sql}
    ORDER BY created_at DESC
    LIMIT {limit}
    """

    cursor.execute(data_sql, params)

    rows = cursor.fetchall()
    if rows:
        print(f"查询到 {len(rows)} 条摘要记录:\n")
        for i, row in enumerate(rows, 1):
            print(f"[{i}] conversation_id: {row[0]}")
            print(f"    requester_id: {row[1]}")
            print(f"    profile_id: {row[2]}")
            print(f"    summary_key: {row[3]}")
            print(f"    summary_text: {row[4]}")
            print(f"    vector_status: {row[5]}")
            print(f"    created_at: {row[6]}")
            print(f"    updated_at: {row[7]}")
            print("-" * 60)
    else:
        print("未查询到摘要数据")

    conn.close()

    # 按向量类型统计
    print(f"\n按向量类型统计:")
    cursor = pymysql.connect(
        host='127.0.0.1',
        port=3307,
        user='root',
        password='',
        charset='utf8mb4',
        database='her'
    ).cursor()

    stats_sql = """
    SELECT
        summary_key,
        COUNT(*) as count,
        SUM(CASE WHEN vector_status = 'pending' THEN 1 ELSE 0 END) as pending_count,
        SUM(CASE WHEN vector_status = 'done' THEN 1 ELSE 0 END) as done_count,
        SUM(CASE WHEN vector_status = 'failed' THEN 1 ELSE 0 END) as failed_count
    FROM conversation_summaries
    GROUP BY summary_key
    ORDER BY count DESC
    """

    cursor.execute(stats_sql)
    stats_rows = cursor.fetchall()

    for row in stats_rows:
        print(f"  {row[0]}: 总数={row[1]}, pending={row[2]}, done={row[3]}, failed={row[4]}")

    cursor.close()


# ============================================================================
# 查询向量库内容
# ============================================================================

def query_vectors(user_id: Optional[int] = None, conversation_id: Optional[str] = None, limit: int = 20):
    """查询 Milvus 向量库中的向量数据。"""

    # 配置 gRPC keepalive 参数，避免 too_many_pings 错误
    grpc_options = {
        "grpc.keepalive_time_ms": 60000,  # 每 60 秒发送一次 ping
        "grpc.keepalive_timeout_ms": 20000,  # 20 秒超时
        "grpc.keepalive_permit_without_calls": True,
        "grpc.http2.max_pings_without_data": 0,  # 无限制
    }

    client = MilvusClient(uri=MILVUS_LITE_DB, grpc_options=grpc_options)

    if not client.has_collection(COLLECTION_NAME):
        print(f"\n向量库 Collection '{COLLECTION_NAME}' 不存在")
        return

    # 加载 Collection
    try:
        client.load_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"加载 Collection 失败（可能已加载）: {e}")

    # 获取总数
    stats = client.get_collection_stats(COLLECTION_NAME)
    total_count = stats.get('row_count', 0)

    print(f"\n{'='*60}")
    print(f"向量库查询结果")
    print(f"{'='*60}")
    print(f"向量总数: {total_count}")
    print(f"查询条件: user_id={user_id}, conversation_id={conversation_id}")
    print(f"{'='*60}\n")

    # 构建查询条件
    filter_expr = ""
    if user_id:
        filter_expr = f"user_id == {user_id}"
    if conversation_id:
        if filter_expr:
            filter_expr += f" and conversation_id == '{conversation_id}'"
        else:
            filter_expr = f"conversation_id == '{conversation_id}'"

    # 查询数据
    try:
        results = client.query(
            collection_name=COLLECTION_NAME,
            filter=filter_expr,
            output_fields=["user_id", "conversation_id", "vector_type", "vector_version", "raw_text", "create_time", "is_active"],
            limit=limit
        )

        if results:
            print(f"查询到 {len(results)} 条向量记录:\n")
            for i, result in enumerate(results, 1):
                print(f"[{i}] user_id: {result.get('user_id')}")
                print(f"    conversation_id: {result.get('conversation_id')}")
                print(f"    vector_type: {result.get('vector_type')}")
                print(f"    vector_version: {result.get('vector_version')}")
                print(f"    raw_text: {result.get('raw_text')}")
                print(f"    create_time: {result.get('create_time')}")
                print(f"    is_active: {result.get('is_active')}")
                print("-" * 60)
        else:
            print("未查询到向量数据")

    except Exception as e:
        print(f"查询向量失败: {e}")

    # 按向量类型统计
    print(f"\n按向量类型统计:")
    try:
        # 查询所有数据（用于统计）
        all_results = client.query(
            collection_name=COLLECTION_NAME,
            filter="",
            output_fields=["vector_type", "is_active"],
            limit=1000
        )

        # 统计各类型数量
        type_stats = {}
        for result in all_results:
            vector_type = result.get('vector_type')
            is_active = result.get('is_active')
            if vector_type not in type_stats:
                type_stats[vector_type] = {"total": 0, "active": 0}
            type_stats[vector_type]["total"] += 1
            if is_active:
                type_stats[vector_type]["active"] += 1

        for vector_type, stats in sorted(type_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            print(f"  {vector_type}: 总数={stats['total']}, 活跃={stats['active']}")

    except Exception as e:
        print(f"统计失败: {e}")


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="查看摘要内容和向量库内容")
    parser.add_argument("--user-id", type=int, help="按用户ID查询")
    parser.add_argument("--conversation-id", type=str, help="按会话ID查询")
    parser.add_argument("--limit", type=int, default=20, help="查询数量限制")
    parser.add_argument("--summaries", action="store_true", help="只查询摘要")
    parser.add_argument("--vectors", action="store_true", help="只查询向量")

    args = parser.parse_args()

    # 默认查询两者
    if not args.summaries and not args.vectors:
        args.summaries = True
        args.vectors = True

    # 查询摘要
    if args.summaries:
        query_summaries(user_id=args.user_id, conversation_id=args.conversation_id, limit=args.limit)

    # 查询向量
    if args.vectors:
        query_vectors(user_id=args.user_id, conversation_id=args.conversation_id, limit=args.limit)


if __name__ == "__main__":
    main()