#!/usr/bin/env python3
"""检查数据分布情况"""

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

source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
if not source:
    print("请设置环境变量 PERSONA_MEMORY_MYSQL_SOURCE")
    sys.exit(1)

conn = mysql_connect(source, use_pool=True, timeout=10.0)

try:
    with conn.cursor() as cursor:
        # 查询无锡女性的总数
        cursor.execute(
            f"""
            SELECT COUNT(*) as total_count
            FROM {quote_mysql_ident("profiles")}
            WHERE city = '无锡'
              AND gender = 'female'
              AND age BETWEEN 26 AND 36
              AND profile_status = 'active'
            """
        )
        total_result = cursor.fetchone()
        total_count = total_result.get("total_count", 0) if total_result else 0

        print(f"【无锡女性（26-36岁，活跃）】总数: {total_count}")

        # 查询 relationship_goal 的分布
        cursor.execute(
            f"""
            SELECT relationship_goal, COUNT(*) as count
            FROM {quote_mysql_ident("profiles")}
            WHERE city = '无锡'
              AND gender = 'female'
              AND age BETWEEN 26 AND 36
              AND profile_status = 'active'
            GROUP BY relationship_goal
            """
        )
        goal_distribution = cursor.fetchall() or []

        print("\n【relationship_goal 分布】:")
        for row in goal_distribution:
            print(f"  - {row.get('relationship_goal')}: {row.get('count')}")

        # 查询符合条件的前10个profile_id
        cursor.execute(
            f"""
            SELECT id, name, age, city, relationship_goal
            FROM {quote_mysql_ident("profiles")}
            WHERE city = '无锡'
              AND gender = 'female'
              AND age BETWEEN 26 AND 36
              AND profile_status = 'active'
            ORDER BY id ASC
            LIMIT 10
            """
        )
        sample_profiles = cursor.fetchall() or []

        print("\n【前10个候选人】:")
        for row in sample_profiles:
            print(f"  - id={row.get('id')}, name={row.get('name')}, age={row.get('age')}, goal={row.get('relationship_goal')}")

finally:
    release_persona_connection(source, conn)