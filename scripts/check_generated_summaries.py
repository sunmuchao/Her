#!/usr/bin/env python3
"""检查生成的摘要数据"""

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
        cursor.execute(
            f"""
            SELECT profile_id, summary_key, summary_text, vector_status
            FROM {quote_mysql_ident("conversation_summaries")}
            WHERE profile_id IN (10002, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10016)
            ORDER BY profile_id, summary_key
            """
        )
        summaries = cursor.fetchall() or []

        print("=" * 80)
        print(f"【摘要数据】找到 {len(summaries)} 条记录")
        print("=" * 80)

        for row in summaries:
            print(f"profile_id={row.get('profile_id')}, key={row.get('summary_key')}")
            print(f"  text={row.get('summary_text')}")
            print(f"  status={row.get('vector_status')}")
            print()

finally:
    release_persona_connection(source, conn)