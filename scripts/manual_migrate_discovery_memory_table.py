#!/usr/bin/env python3
"""手动执行 discovery 数据库迁移，创建缺失的 discovery_agent_session_memory_items 表。

修复错误：
    Table 'her.discovery_agent_session_memory_items' doesn't exist

执行方式：
    python scripts/manual_migrate_discovery_memory_table.py
"""

from __future__ import annotations

import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from outer_system_mysql_schema import (
    mysql_database_connect,
    parse_mysql_dsn,
    ensure_table,
    discovery_tables,
)


def main():
    """执行迁移，创建 discovery_agent_session_memory_items 表"""

    # 从环境变量获取数据库连接信息
    discovery_db_dsn = os.environ.get("PARTNER_DISCOVERY_DB")

    if not discovery_db_dsn:
        print("错误：缺少环境变量 PARTNER_DISCOVERY_DB")
        print("请设置数据库连接字符串，例如：")
        print("export PARTNER_DISCOVERY_DB='mysql+pymysql://root:password@localhost:3306/her'")
        sys.exit(1)

    print(f"正在连接数据库...")

    # 解析 DSN
    config = parse_mysql_dsn(discovery_db_dsn)
    print(f"数据库: {config['database']}")
    print(f"主机: {config['host']}:{config['port']}")

    # 连接数据库
    conn = mysql_database_connect(config)

    try:
        # 查找 discovery_agent_session_memory_items 表定义
        memory_table = None
        for table in discovery_tables():
            if table.name == "discovery_agent_session_memory_items":
                memory_table = table
                break

        if not memory_table:
            print("错误：未找到 discovery_agent_session_memory_items 表定义")
            sys.exit(1)

        print(f"\n表结构:")
        print(f"  表名: {memory_table.name}")
        print(f"  列: {', '.join(memory_table.column_names)}")
        print(f"  主键: {', '.join(memory_table.primary_key)}")

        # 创建表
        print(f"\n正在创建表...")
        ensure_table(conn, memory_table, config=config)
        conn.commit()

        print(f"\n✓ 表创建成功！")

        # 验证表已创建
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'discovery_agent_session_memory_items'")
            result = cursor.fetchone()

            if result:
                print(f"✓ 验证成功：表 discovery_agent_session_memory_items 已存在")

                # 显示表结构
                cursor.execute("DESCRIBE discovery_agent_session_memory_items")
                columns = cursor.fetchall()

                print(f"\n表结构详情:")
                for col in columns:
                    print(f"  - {col['Field']}: {col['Type']} ({'NULL' if col['Null'] == 'YES' else 'NOT NULL'})")
            else:
                print(f"✗ 验证失败：表未创建")
                sys.exit(1)

    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()