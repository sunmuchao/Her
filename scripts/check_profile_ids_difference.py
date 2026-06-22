#!/usr/bin/env python3
"""检查搜索返回的候选人profile_id"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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

from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection
from outer_system_mysql_schema import quote_mysql_ident

source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or ""
if not source:
    print("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE 或 HER_PERSONA_DB")
    sys.exit(1)

conn = mysql_connect(source, use_pool=True, timeout=10.0)

try:
    with conn.cursor() as cursor:
        # 检查搜索返回的候选人（6092, 2379, 6566, 1045, 8867）
        profile_ids = [6092, 2379, 6566, 1045, 8867]
        placeholders = ", ".join(["%s"] * len(profile_ids))

        cursor.execute(
            f"""
            SELECT id, name, age, city, gender, job, relationship_goal, profile_status
            FROM {quote_mysql_ident("profiles")}
            WHERE id IN ({placeholders})
            """,
            tuple(profile_ids),
        )
        profiles = cursor.fetchall() or []

        print("=" * 80)
        print("【搜索返回的候选人】")
        print("=" * 80)
        for p in profiles:
            print(f"  id={p.get('id')}, name={p.get('name')}, age={p.get('age')}, "
                  f"gender={p.get('gender')}, city={p.get('city')}, status={p.get('profile_status')}")

        # 检查生成向量数据的候选人（10002, 10005等）
        my_profile_ids = [10002, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10016]
        placeholders2 = ", ".join(["%s"] * len(my_profile_ids))

        cursor.execute(
            f"""
            SELECT id, name, age, city, gender, job, relationship_goal, profile_status
            FROM {quote_mysql_ident("profiles")}
            WHERE id IN ({placeholders2})
            """,
            tuple(my_profile_ids),
        )
        my_profiles = cursor.fetchall() or []

        print("\n" + "=" * 80)
        print("【生成向量数据的候选人】")
        print("=" * 80)
        for p in my_profiles:
            print(f"  id={p.get('id')}, name={p.get('name')}, age={p.get('age')}, "
                  f"gender={p.get('gender')}, city={p.get('city')}, status={p.get('profile_status')}")

        print("\n" + "=" * 80)
        print("【分析】")
        print("=" * 80)
        print("两组profile_id完全不匹配，这就是向量筛选失效的根本原因！")

finally:
    release_persona_connection(source, conn)