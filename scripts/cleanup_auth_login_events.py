"""定期清理认证事件日志的任务。

功能：
1. 归档90天前的认证事件日志到归档表
2. 删除已归档的数据
3. 优化表空间

执行频率：每天凌晨3点执行一次
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import outer_system_mysql_schema as _schema

logger = logging.getLogger(__name__)

# 配置项
RETENTION_DAYS = int(os.environ.get("AUTH_EVENT_RETENTION_DAYS", "90"))
BATCH_SIZE = int(os.environ.get("AUTH_EVENT_CLEANUP_BATCH_SIZE", "100000"))
MAX_DELETE_ROUNDS = int(os.environ.get("AUTH_EVENT_CLEANUP_MAX_ROUNDS", "10"))


def ensure_archive_table(mysql_conn) -> None:
    """确保归档表存在"""
    archive_table_sql = """
    CREATE TABLE IF NOT EXISTS auth_login_events_archive (
        event_id VARCHAR(64) NOT NULL,
        user_id VARCHAR(64),
        phone VARCHAR(255),
        event_type VARCHAR(64) NOT NULL,
        result VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64),
        client_ip VARCHAR(64),
        device_id VARCHAR(128),
        metadata_json LONGTEXT NOT NULL,
        created_at DATETIME NOT NULL,
        archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (event_id),
        INDEX idx_archived_at (archived_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(archive_table_sql)
    logger.info("Ensured auth_login_events_archive table exists")


def archive_old_events(mysql_conn, cutoff_date: datetime) -> int:
    """归档旧数据到归档表

    Args:
        mysql_conn: 数据库连接
        cutoff_date: 截止日期，早于此日期的数据将被归档

    Returns:
        归档的记录数
    """
    archive_sql = """
    INSERT INTO auth_login_events_archive
    SELECT *, NOW() as archived_at
    FROM auth_login_events
    WHERE created_at < %s
    LIMIT %s
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(archive_sql, (cutoff_date, BATCH_SIZE))
        archived_count = cursor.rowcount
    logger.info(f"Archived {archived_count} events before {cutoff_date}")
    return archived_count


def delete_archived_events(mysql_conn, cutoff_date: datetime) -> int:
    """删除已归档的数据

    Args:
        mysql_conn: 数据库连接
        cutoff_date: 截止日期

    Returns:
        删除的记录数
    """
    delete_sql = """
    DELETE FROM auth_login_events
    WHERE created_at < %s
    LIMIT %s
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(delete_sql, (cutoff_date, BATCH_SIZE))
        deleted_count = cursor.rowcount
    logger.info(f"Deleted {deleted_count} archived events")
    return deleted_count


def optimize_table(mysql_conn) -> None:
    """优化表空间，释放磁盘空间"""
    with mysql_conn.cursor() as cursor:
        cursor.execute("OPTIMIZE TABLE auth_login_events")
    logger.info("Optimized auth_login_events table space")


def get_table_stats(mysql_conn) -> dict[str, Any]:
    """获取表统计信息"""
    stats_sql = """
    SELECT
        COUNT(*) as total_rows,
        MIN(created_at) as oldest_record,
        MAX(created_at) as newest_record,
        COUNT(CASE WHEN created_at < %s THEN 1 END) as old_records
    FROM auth_login_events
    """
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    with mysql_conn.cursor() as cursor:
        cursor.execute(stats_sql, (cutoff_date,))
        result = cursor.fetchone()
    return {
        "total_rows": result["total_rows"],
        "oldest_record": result["oldest_record"],
        "newest_record": result["newest_record"],
        "old_records": result["old_records"],
        "retention_days": RETENTION_DAYS,
    }


def cleanup_auth_events(mysql_conn) -> dict[str, Any]:
    """执行清理任务

    Args:
        mysql_conn: 数据库连接

    Returns:
        清理结果统计
    """
    logger.info("Starting auth_login_events cleanup task")

    # 1. 确保归档表存在
    ensure_archive_table(mysql_conn)

    # 2. 计算截止日期
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    logger.info(f"Cutoff date: {cutoff_date} (retention: {RETENTION_DAYS} days)")

    # 3. 分批归档和删除
    total_archived = 0
    total_deleted = 0

    for round_num in range(MAX_DELETE_ROUNDS):
        # 归档
        archived = archive_old_events(mysql_conn, cutoff_date)
        total_archived += archived

        # 删除
        deleted = delete_archived_events(mysql_conn, cutoff_date)
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
        optimize_table(mysql_conn)
        mysql_conn.commit()

    # 5. 获取最终统计
    stats = get_table_stats(mysql_conn)
    stats["total_archived"] = total_archived
    stats["total_deleted"] = total_deleted

    logger.info(f"Cleanup completed: {stats}")
    return stats


def main() -> None:
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Cleanup auth_login_events table")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats, don't delete")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS, help="Retention days")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Batch size")
    args = parser.parse_args()

    # 获取数据库连接
    config = _schema.parse_mysql_dsn(os.environ.get("CHAT_DATABASE_URL", ""))
    mysql_conn = _schema.mysql_database_connect(config)

    try:
        if args.dry_run:
            stats = get_table_stats(mysql_conn)
            print(json.dumps(stats, indent=2, default=str))
        else:
            global RETENTION_DAYS, BATCH_SIZE
            RETENTION_DAYS = args.retention_days
            BATCH_SIZE = args.batch_size
            stats = cleanup_auth_events(mysql_conn)
            print(json.dumps(stats, indent=2, default=str))
    finally:
        mysql_conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()