#!/usr/bin/env python3
"""检查正确的候选人（6092, 2379等）是否有摘要和向量数据"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path(repo_root) / ".env")
except ImportError:
    pass

from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
from outer_system_mysql_schema import quote_mysql_ident

source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
conn = mysql_connect(source, use_pool=True, timeout=10.0)

try:
    with conn.cursor() as cursor:
        profile_ids = [6092, 2379, 6566, 1045, 8867]
        placeholders = ", ".join(["%s"] * len(profile_ids))

        cursor.execute(
            f"""
            SELECT profile_id, summary_key, summary_text
            FROM {quote_mysql_ident("conversation_summaries")}
            WHERE profile_id IN ({placeholders})
            ORDER BY profile_id, summary_key
            """,
            tuple(profile_ids),
        )
        summaries = cursor.fetchall() or []

        print("=" * 80)
        print(f"【摘要数据】找到 {len(summaries)} 条记录")
        print("=" * 80)

        # 统计每个用户的摘要数量
        summary_count_by_user = {}
        for row in summaries:
            profile_id = row.get("profile_id")
            if profile_id not in summary_count_by_user:
                summary_count_by_user[profile_id] = 0
            summary_count_by_user[profile_id] += 1

        for profile_id, count in sorted(summary_count_by_user.items()):
            print(f"  profile_id={profile_id}: {count} 条摘要")

        if len(summary_count_by_user) == len(profile_ids):
            print("\n✅ 所有候选人都有摘要数据！")
        else:
            missing = [pid for pid in profile_ids if pid not in summary_count_by_user]
            print(f"\n❌ 缺失摘要的候选人: {missing}")

finally:
    release_persona_connection(source, conn)