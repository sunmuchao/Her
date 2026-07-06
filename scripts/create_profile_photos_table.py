"""创建 profile_photos 表的脚本。

用途：
    当外部数据库（partner-matchmaking/partner-search）中缺少 profile_photos 表时，
    可以使用此脚本创建表结构。

执行方式：
    python scripts/create_profile_photos_table.py --dsn mysql://root@127.0.0.1:3307/her_matchmaking

注意：
    profile_photos 表应该和 profiles 表在同一个数据库中，
    通常是在 partner-matchmaking 或 partner-search 数据库中。
"""

from __future__ import annotations

import argparse
import sys

import outer_system_mysql_schema as schema


PROFILE_PHOTOS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `profile_photos` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `profile_id` BIGINT NOT NULL,
  `photo_url` VARCHAR(512) NOT NULL,
  `is_primary` TINYINT(1) DEFAULT 0,
  `sort_order` INT DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_profile_photos_profile_id` (`profile_id`),
  INDEX `idx_profile_photos_sort_order` (`profile_id`, `sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create profile_photos table in the specified database"
    )
    parser.add_argument(
        "--dsn",
        required=True,
        help="MySQL DSN for the target database (e.g., mysql://root@127.0.0.1:3307/her_matchmaking)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL without executing",
    )
    args = parser.parse_args()

    # 解析 DSN
    config = schema.parse_mysql_dsn(args.dsn)

    if args.dry_run:
        print("SQL to execute:")
        print(PROFILE_PHOTOS_TABLE_SQL)
        print(f"\nTarget database: {config['database']}")
        return 0

    # 连接数据库
    print(f"Connecting to database: {config['database']}")
    conn = schema.mysql_database_connect(config)

    try:
        with conn.cursor() as cursor:
            # 检查表是否已存在
            cursor.execute("SHOW TABLES LIKE 'profile_photos'")
            if cursor.fetchone():
                print("✓ Table 'profile_photos' already exists")
                return 0

            # 创建表
            cursor.execute(PROFILE_PHOTOS_TABLE_SQL)
            conn.commit()
            print("✓ Table 'profile_photos' created successfully")

            # 验证表结构
            cursor.execute("DESCRIBE profile_photos")
            columns = cursor.fetchall()
            print("\nTable structure:")
            for col in columns:
                print(f"  - {col['Field']}: {col['Type']}")

            return 0
    except Exception as e:
        print(f"✗ Error creating table: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())