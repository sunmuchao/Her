"""监控认证事件表的容量和增长趋势。

功能：
1. 监控表数据量
2. 监控磁盘空间使用
3. 预测增长趋势
4. 发送告警

执行频率：每5分钟执行一次
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import outer_system_mysql_schema as _schema

logger = logging.getLogger(__name__)

# 告警阈值
TABLE_ROWS_WARNING = int(os.environ.get("AUTH_EVENTS_ROWS_WARNING", "1000000"))  # 100万行
TABLE_ROWS_CRITICAL = int(os.environ.get("AUTH_EVENTS_ROWS_CRITICAL", "5000000"))  # 500万行
TABLE_AGE_WARNING_DAYS = int(os.environ.get("AUTH_EVENTS_AGE_WARNING_DAYS", "180"))  # 180天
TABLE_AGE_CRITICAL_DAYS = int(os.environ.get("AUTH_EVENTS_AGE_CRITICAL_DAYS", "365"))  # 365天


def get_table_status(mysql_conn) -> dict[str, Any]:
    """获取表状态信息"""
    status_sql = """
    SELECT
        TABLE_ROWS as row_count,
        DATA_LENGTH as data_size,
        INDEX_LENGTH as index_size,
        DATA_FREE as data_free,
        (DATA_LENGTH + INDEX_LENGTH) as total_size
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'auth_login_events'
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(status_sql)
        result = cursor.fetchone()

    if not result:
        return {"error": "Table not found"}

    return {
        "row_count": result["row_count"],
        "data_size_mb": round(result["data_size"] / 1024 / 1024, 2),
        "index_size_mb": round(result["index_size"] / 1024 / 1024, 2),
        "total_size_mb": round(result["total_size"] / 1024 / 1024, 2),
        "data_free_mb": round(result["data_free"] / 1024 / 1024, 2),
    }


def get_record_stats(mysql_conn) -> dict[str, Any]:
    """获取记录统计信息"""
    stats_sql = """
    SELECT
        COUNT(*) as total_rows,
        MIN(created_at) as oldest_record,
        MAX(created_at) as newest_record,
        COUNT(CASE WHEN created_at < DATE_SUB(NOW(), INTERVAL %s DAY) THEN 1 END) as records_older_than_warning,
        COUNT(CASE WHEN created_at < DATE_SUB(NOW(), INTERVAL %s DAY) THEN 1 END) as records_older_than_critical
    FROM auth_login_events
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(stats_sql, (TABLE_AGE_WARNING_DAYS, TABLE_AGE_CRITICAL_DAYS))
        result = cursor.fetchone()

    return {
        "total_rows": result["total_rows"],
        "oldest_record": result["oldest_record"],
        "newest_record": result["newest_record"],
        "records_older_than_warning": result["records_older_than_warning"],
        "records_older_than_critical": result["records_older_than_critical"],
        "oldest_record_age_days": (datetime.utcnow() - result["oldest_record"]).days if result["oldest_record"] else 0,
    }


def get_growth_rate(mysql_conn) -> dict[str, Any]:
    """获取增长速率（基于最近7天的数据）"""
    growth_sql = """
    SELECT
        COUNT(*) as recent_rows,
        COUNT(*) / 7 as daily_avg
    FROM auth_login_events
    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(growth_sql)
        result = cursor.fetchone()

    return {
        "recent_rows": result["recent_rows"],
        "daily_avg": round(result["daily_avg"], 2),
    }


def check_health(mysql_conn) -> dict[str, Any]:
    """检查表健康状态"""
    status = get_table_status(mysql_conn)
    stats = get_record_stats(mysql_conn)
    growth = get_growth_rate(mysql_conn)

    # 判断健康状态
    health_status = "healthy"
    alerts = []

    # 检查行数
    if stats["total_rows"] >= TABLE_ROWS_CRITICAL:
        health_status = "critical"
        alerts.append({
            "level": "critical",
            "message": f"auth_login_events table has {stats['total_rows']} rows (critical threshold: {TABLE_ROWS_CRITICAL})",
        })
    elif stats["total_rows"] >= TABLE_ROWS_WARNING:
        health_status = "warning"
        alerts.append({
            "level": "warning",
            "message": f"auth_login_events table has {stats['total_rows']} rows (warning threshold: {TABLE_ROWS_WARNING})",
        })

    # 检查数据年龄
    if stats["oldest_record_age_days"] >= TABLE_AGE_CRITICAL_DAYS:
        if health_status != "critical":
            health_status = "warning"
        alerts.append({
            "level": "warning",
            "message": f"Oldest record is {stats['oldest_record_age_days']} days old (critical threshold: {TABLE_AGE_CRITICAL_DAYS} days)",
        })
    elif stats["oldest_record_age_days"] >= TABLE_AGE_WARNING_DAYS:
        if health_status == "healthy":
            health_status = "warning"
        alerts.append({
            "level": "warning",
            "message": f"Oldest record is {stats['oldest_record_age_days']} days old (warning threshold: {TABLE_AGE_WARNING_DAYS} days)",
        })

    # 预测容量耗尽时间（基于当前增长速率）
    if growth["daily_avg"] > 0:
        days_until_full = (TABLE_ROWS_CRITICAL - stats["total_rows"]) / growth["daily_avg"]
        if days_until_full < 30:  # 30天内将达到容量上限
            alerts.append({
                "level": "warning",
                "message": f"Table will reach critical capacity in {round(days_until_full)} days (daily avg: {growth['daily_avg']} rows)",
            })

    return {
        "status": health_status,
        "alerts": alerts,
        "table_status": status,
        "record_stats": stats,
        "growth_rate": growth,
        "thresholds": {
            "rows_warning": TABLE_ROWS_WARNING,
            "rows_critical": TABLE_ROWS_CRITICAL,
            "age_warning_days": TABLE_AGE_WARNING_DAYS,
            "age_critical_days": TABLE_AGE_CRITICAL_DAYS,
        },
    }


def send_alert(alert: dict[str, Any]) -> None:
    """发送告警（可扩展为发送到钉钉、企业微信、邮件等）"""
    # TODO: 接入告警系统（钉钉、企业微信、邮件等）
    # 目前只记录日志
    logger.warning(f"ALERT [{alert['level'].upper()}]: {alert['message']}")

    # 示例：发送到标准输出（可被 Prometheus Node Exporter 抓取）
    print(f"auth_events_alert{{level=\"{alert['level']}\"}} 1")


def main() -> None:
    """命令行入口"""
    # 获取数据库连接
    config = _schema.parse_mysql_dsn(os.environ.get("CHAT_DATABASE_URL", ""))
    mysql_conn = _schema.mysql_database_connect(config)

    try:
        health = check_health(mysql_conn)

        # 输出 Prometheus 格式的指标
        print(f"auth_events_rows{{status=\"total\"}} {health['record_stats']['total_rows']}")
        print(f"auth_events_size_mb{{type=\"data\"}} {health['table_status']['data_size_mb']}")
        print(f"auth_events_size_mb{{type=\"index\"}} {health['table_status']['index_size_mb']}")
        print(f"auth_events_size_mb{{type=\"total\"}} {health['table_status']['total_size_mb']}")
        print(f"auth_events_daily_avg{{}} {health['growth_rate']['daily_avg']}")
        print(f"auth_events_oldest_age_days{{}} {health['record_stats']['oldest_record_age_days']}")

        # 发送告警
        for alert in health["alerts"]:
            send_alert(alert)

        # 输出 JSON 格式的完整状态
        print(f"\n# Health Status: {health['status']}")
        print(f"# {json.dumps(health, indent=2, default=str)}")

    finally:
        mysql_conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()