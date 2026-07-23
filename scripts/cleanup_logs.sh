#!/bin/bash
# 日志表清理脚本执行器
# 用法：./cleanup_logs.sh [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_SCRIPT="$SCRIPT_DIR/cleanup_log_tables.sql"
LOG_FILE="$SCRIPT_DIR/../logs/log_cleanup.log"
MYSQL_HOST="${MYSQL_HOST:-her-mysql-1}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"

# 创建日志目录
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 检查是否是 dry-run 模式
if [[ "$1" == "--dry-run" ]]; then
    log "DRY RUN MODE - Showing statistics only"

    docker exec "$MYSQL_HOST" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "
    SELECT 'auth_login_events' as table_name,
           COUNT(*) as total_rows,
           MIN(created_at) as oldest,
           MAX(created_at) as newest
    FROM her_auth.auth_login_events;

    SELECT 'match_relation_events' as table_name,
           COUNT(*) as total_rows,
           MIN(occurred_at) as oldest,
           MAX(occurred_at) as newest
    FROM her_relationship_ledger.match_relation_events;

    SELECT 'recommendation_actions' as table_name,
           COUNT(*) as total_rows,
           MIN(occurred_at) as oldest,
           MAX(occurred_at) as newest
    FROM her_recommendation.recommendation_actions;
    "
    exit 0
fi

# 执行清理
log "Starting log tables cleanup..."

if docker exec "$MYSQL_HOST" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < "$SQL_SCRIPT" >> "$LOG_FILE" 2>&1; then
    log "Cleanup completed successfully"
    exit 0
else
    log "ERROR: Cleanup failed"
    exit 1
fi