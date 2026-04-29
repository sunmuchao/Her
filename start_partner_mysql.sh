#!/bin/zsh
set -euo pipefail

BASE_DIR="/Users/sunmuchao/Downloads/Her/.partner-search-mysql"
CONF="$BASE_DIR/my.cnf"
DATA_DIR="$BASE_DIR/data"
MYSQLD="/usr/local/mysql/bin/mysqld"
MYSQL="/usr/local/mysql/bin/mysql"

mkdir -p "$DATA_DIR"

if [[ ! -f "$DATA_DIR/auto.cnf" ]]; then
  "$MYSQLD" --defaults-file="$CONF" --initialize-insecure
fi

if "$MYSQL" --defaults-file="$CONF" -e 'SELECT 1' >/dev/null 2>&1; then
  echo "partner-search mysql is already running"
  exit 0
fi

"$MYSQLD" --defaults-file="$CONF" --daemonize
echo "partner-search mysql started on 127.0.0.1:3307"
