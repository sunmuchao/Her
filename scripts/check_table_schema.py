#!/usr/bin/env python3
"""检查数据库表结构"""

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
        # 查询 profiles 表结构
        cursor.execute(f"DESCRIBE {quote_mysql_ident('profiles')}")
        profiles_schema = cursor.fetchall()

        print("=" * 80)
        print("profiles 表结构:")
        print("=" * 80)
        for row in profiles_schema:
            print(f"  {row.get('Field')}: {row.get('Type')} ({row.get('Null')}, {row.get('Key')})")

        # 查询 user_personas 表结构
        cursor.execute(f"DESCRIBE {quote_mysql_ident('user_personas')}")
        personas_schema = cursor.fetchall()

        print("\n" + "=" * 80)
        print("user_personas 表结构:")
        print("=" * 80)
        for row in personas_schema:
            print(f"  {row.get('Field')}: {row.get('Type')} ({row.get('Null')}, {row.get('Key')})")

        # 查询 conversation_summaries 表结构
        cursor.execute(f"DESCRIBE {quote_mysql_ident('conversation_summaries')}")
        summaries_schema = cursor.fetchall()

        print("\n" + "=" * 80)
        print("conversation_summaries 表结构:")
        print("=" * 80)
        for row in summaries_schema:
            print(f"  {row.get('Field')}: {row.get('Type')} ({row.get('Null')}, {row.get('Key')})")

        # 查询 profiles 表的前几条数据（看看主键是什么）
        cursor.execute(f"SELECT * FROM {quote_mysql_ident('profiles')} LIMIT 1")
        sample_profile = cursor.fetchone()

        print("\n" + "=" * 80)
        print("profiles 表样本数据:")
        print("=" * 80)
        if sample_profile:
            for key, value in sample_profile.items():
                print(f"  {key}: {value}")

finally:
    release_persona_connection(source, conn)