"""手动执行 discovery 数据库迁移，在 her 数据库中创建缺失的 discovery 表。

修复错误：
    Table 'her.discovery_agent_session_memory_items' doesn't exist
    Table 'her.discovery_agent_sessions' doesn't exist

原因：
    session_end_processor 代码优先使用 HER_PERSONA_DB（her数据库），
    导致查询 discovery 相关表时找不到。

解决方案：
    在 her 数据库中创建必要的 discovery 表。

执行方式：
    python scripts/manual_migrate_discovery_tables_to_her.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from pymysql.cursors import DictCursor


DISCOVERY_TABLES_SQL = """
-- 1. discovery_agent_sessions 表
CREATE TABLE IF NOT EXISTS discovery_agent_sessions (
    session_id VARCHAR(191) NOT NULL,
    requester_id BIGINT NOT NULL,
    profile_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    phase VARCHAR(64) NOT NULL,
    state_json LONGTEXT NOT NULL,
    latest_view_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (session_id),
    INDEX idx_discovery_sessions_requester_updated (requester_id, updated_at),
    INDEX idx_discovery_sessions_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. discovery_agent_session_memory_items 表
CREATE TABLE IF NOT EXISTS discovery_agent_session_memory_items (
    item_id BIGINT NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(191) NOT NULL,
    item_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (item_id),
    INDEX idx_discovery_agent_memory_session_item (session_id, item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def main():
    """执行迁移"""

    # 连接 her 数据库
    password = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user="root",
        password=password,
        database="her",
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )

    try:
        print("正在连接 her 数据库...")

        with conn.cursor() as cursor:
            # 执行建表SQL
            for sql in DISCOVERY_TABLES_SQL.strip().split(";"):
                if sql.strip():
                    cursor.execute(sql)

        conn.commit()
        print("\n✓ 迁移成功！")

        # 验证表已创建
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'discovery_%'")
            tables = cursor.fetchall()

            print(f"\n已创建的 discovery 表:")
            for table in tables:
                table_name = list(table.values())[0]
                print(f"  - {table_name}")

                # 显示表结构
                cursor.execute(f"DESC {table_name}")
                columns = cursor.fetchall()
                print(f"    列数: {len(columns)}")

    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()