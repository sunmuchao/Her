#!/bin/bash
# 日志表监控脚本
# 输出 Prometheus 格式的指标
# 执行频率：每5分钟

set -e

MYSQL_HOST="${MYSQL_HOST:-her-mysql-1}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/../logs/log_tables.prom"

# 创建输出目录
mkdir -p "$(dirname "$OUTPUT_FILE")"

# 临时文件
TEMP_FILE="${OUTPUT_FILE}.tmp"

# 获取当前时间戳
TIMESTAMP=$(date +%s%3N)

# 查询所有日志表的统计信息
docker exec "$MYSQL_HOST" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "
SELECT 'auth_login_events', COUNT(*), MIN(created_at), MAX(created_at)
FROM her_auth.auth_login_events;
SELECT 'match_relation_events', COUNT(*), MIN(occurred_at), MAX(occurred_at)
FROM her_relationship_ledger.match_relation_events;
SELECT 'recommendation_actions', COUNT(*), MIN(occurred_at), MAX(occurred_at)
FROM her_recommendation.recommendation_actions;
" 2>/dev/null | while read table_name row_count oldest newest; do
    # 计算最老记录的年龄（天）
    # 使用MySQL计算年龄，避免shell日期解析问题
    oldest_age_days=$(docker exec "$MYSQL_HOST" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "
        SELECT DATEDIFF(NOW(), '$oldest');
    " 2>/dev/null)

    # 输出 Prometheus 格式的指标
    echo "log_table_rows{table=\"$table_name\"} $row_count" >> "$TEMP_FILE"
    echo "log_table_oldest_age_days{table=\"$table_name\"} $oldest_age_days" >> "$TEMP_FILE"
done

# 获取磁盘使用率
disk_usage=$(docker exec "$MYSQL_HOST" df -h / | awk 'NR==2 {gsub(/%/,""); print $5}')
echo "mysql_disk_usage_percent $disk_usage" >> "$TEMP_FILE"

# 获取表大小
docker exec "$MYSQL_HOST" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "
SELECT 'auth_login_events', ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2)
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'her_auth' AND TABLE_NAME = 'auth_login_events';
SELECT 'match_relation_events', ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2)
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'her_relationship_ledger' AND TABLE_NAME = 'match_relation_events';
SELECT 'recommendation_actions', ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2)
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'her_recommendation' AND TABLE_NAME = 'recommendation_actions';
" 2>/dev/null | while read table_name size_mb; do
    echo "log_table_size_mb{table=\"$table_name\"} $size_mb" >> "$TEMP_FILE"
done

# 原子性更新文件
mv "$TEMP_FILE" "$OUTPUT_FILE"

echo "Metrics updated at $(date)"