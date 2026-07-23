"""统一清理所有日志表的定时任务。

功能：
1. 清理 auth_login_events（认证日志）
2. 清理 match_relation_events（关系事件日志）
3. 清理 recommendation_actions（推荐操作日志）

执行频率：每天凌晨3点执行一次
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

# 配置项
RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "90"))
BATCH_SIZE = int(os.environ.get("LOG_CLEANUP_BATCH_SIZE", "100000"))
MAX_DELETE_ROUNDS = int(os.environ.get("LOG_CLEANUP_MAX_ROUNDS", "10"))

# 日志表配置
LOG_TABLES = [
    {
        "database": "her_auth",
        "table": "auth_login_events",
        "archive_table": "auth_login_events_archive",
        "date_column": "created_at",
    },
    {
        "database": "her_relationship_ledger",
        "table": "match_relation_events",
        "archive_table": "match_relation_events_archive",
        "date_column": "occurred_at",
    },
    {
        "database": "her_recommendation",
        "table": "recommendation_actions",
        "archive_table": "recommendation_actions_archive",
        "date_column": "occurred_at",
    },
]


def get_mysql_connection():
    """获取MySQL连接"""
    password = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user="root",
        password=password,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def ensure_archive_table(mysql_conn, db_name: str, table_name: str, archive_table: str) -> None:
    """确保归档表存在"""
    # 获取原表结构
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {db_name}.{archive_table} LIKE {db_name}.{table_name}
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"USE {db_name}")
        cursor.execute(create_table_sql)
        # 添加归档时间列
        try:
            cursor.execute(f"""
                ALTER TABLE {archive_table}
                ADD COLUMN archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" not in str(e):
                raise
    logger.info(f"Ensured {db_name}.{archive_table} exists")


def archive_old_data(
    mysql_conn, db_name: str, table_name: str, archive_table: str, date_column: str, cutoff_date: datetime
) -> int:
    """归档旧数据"""
    archive_sql = f"""
    INSERT INTO {db_name}.{archive_table}
    SELECT *, NOW() as archived_at
    FROM {db_name}.{table_name}
    WHERE {date_column} < %s
    LIMIT %s
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"USE {db_name}")
        cursor.execute(archive_sql, (cutoff_date, BATCH_SIZE))
        archived_count = cursor.rowcount
    logger.info(f"Archived {archived_count} rows from {db_name}.{table_name}")
    return archived_count


def delete_archived_data(
    mysql_conn, db_name: str, table_name: str, date_column: str, cutoff_date: datetime
) -> int:
    """删除已归档的数据"""
    delete_sql = f"""
    DELETE FROM {db_name}.{table_name}
    WHERE {date_column} < %s
    LIMIT %s
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"USE {db_name}")
        cursor.execute(delete_sql, (cutoff_date, BATCH_SIZE))
        deleted_count = cursor.rowcount
    logger.info(f"Deleted {deleted_count} rows from {db_name}.{table_name}")
    return deleted_count


def optimize_table(mysql_conn, db_name: str, table_name: str) -> None:
    """优化表空间"""
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"OPTIMIZE TABLE {db_name}.{table_name}")
    logger.info(f"Optimized {db_name}.{table_name}")


def get_table_stats(mysql_conn, db_name: str, table_name: str, date_column: str) -> dict[str, Any]:
    """获取表统计信息"""
    stats_sql = f"""
    SELECT
        COUNT(*) as total_rows,
        MIN({date_column}) as oldest_record,
        MAX({date_column}) as newest_record,
        COUNT(CASE WHEN {date_column} < %s THEN 1 END) as old_records
    FROM {db_name}.{table_name}
    """
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"USE {db_name}")
        cursor.execute(stats_sql, (cutoff_date,))
        result = cursor.fetchone()
    return {
        "total_rows": result["total_rows"],
        "oldest_record": result["oldest_record"],
        "newest_record": result["newest_record"],
        "old_records": result["old_records"],
    }


def cleanup_table(
    mysql_conn, db_name: str, table_name: str, archive_table: str, date_column: str
) -> dict[str, Any]:
    """清理单个表"""
    logger.info(f"Starting cleanup for {db_name}.{table_name}")

    # 1. 确保归档表存在
    ensure_archive_table(mysql_conn, db_name, table_name, archive_table)

    # 2. 计算截止日期
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    logger.info(f"Cutoff date: {cutoff_date} (retention: {RETENTION_DAYS} days)")

    # 3. 分批归档和删除
    total_archived = 0
    total_deleted = 0

    for round_num in range(MAX_DELETE_ROUNDS):
        # 归档
        archived = archive_old_data(mysql_conn, db_name, table_name, archive_table, date_column, cutoff_date)
        total_archived += archived

        # 删除
        deleted = delete_archived_data(mysql_conn, db_name, table_name, date_column, cutoff_date)
        total_deleted += deleted

        # 提交事务
        mysql_conn.commit()

        # 如果本轮没有数据需要处理，退出循环
        if archived == 0 and deleted == 0:
            logger.info(f"No more data to archive/delete after {round_num} rounds")
            break

        logger.info(
            f"Round {round_num + 1}: archived={archived}, deleted={deleted}, "
            f"total_archived={total_archived}, total_deleted={total_deleted}"
        )

    # 4. 优化表空间
    if total_deleted > 0:
        optimize_table(mysql_conn, db_name, table_name)
        mysql_conn.commit()

    # 5. 获取最终统计
    stats = get_table_stats(mysql_conn, db_name, table_name, date_column)
    stats["total_archived"] = total_archived
    stats["total_deleted"] = total_deleted

    logger.info(f"Cleanup completed for {db_name}.{table_name}: {stats}")
    return stats


def cleanup_all_tables() -> dict[str, Any]:
    """清理所有日志表"""
    logger.info("Starting cleanup for all log tables")

    mysql_conn = get_mysql_connection()
    results = {}

    try:
        for table_config in LOG_TABLES:
            try:
                stats = cleanup_table(
                    mysql_conn,
                    table_config["database"],
                    table_config["table"],
                    table_config["archive_table"],
                    table_config["date_column"],
                )
                results[table_config["table"]] = stats
            except Exception as e:
                logger.error(f"Failed to cleanup {table_config['table']}: {e}")
                results[table_config["table"]] = {"error": str(e)}
    finally:
        mysql_conn.close()

    logger.info(f"All cleanup completed: {results}")
    return results


def show_stats() -> None:
    """显示所有表的统计信息"""
    mysql_conn = get_mysql_connection()

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        print(f"\n{'='*80}")
        print(f"Log Tables Statistics (Retention: {RETENTION_DAYS} days, Cutoff: {cutoff_date})")
        print(f"{'='*80}\n")

        for table_config in LOG_TABLES:
            stats = get_table_stats(
                mysql_conn,
                table_config["database"],
                table_config["table"],
                table_config["date_column"],
            )

            print(f"Table: {table_config['database']}.{table_config['table']}")
            print(f"  Total rows: {stats['total_rows']:,}")
            print(f"  Oldest record: {stats['oldest_record']}")
            print(f"  Newest record: {stats['newest_record']}")
            print(f"  Records older than {RETENTION_DAYS} days: {stats['old_records']:,}")
            print()

    finally:
        mysql_conn.close()


def main() -> None:
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Cleanup log tables")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats, don't delete")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS, help="Retention days")
    args = parser.parse_args()

    if args.dry_run or args.stats:
        show_stats()
    else:
        results = cleanup_all_tables()
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    main()