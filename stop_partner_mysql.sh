#!/bin/zsh
set -euo pipefail

CONF="/Users/sunmuchao/Downloads/Her/.partner-search-mysql/my.cnf"
MYSQL="/usr/local/mysql/bin/mysql"

if "$MYSQL" --defaults-file="$CONF" -e 'SELECT 1' >/dev/null 2>&1; then
  "$MYSQL" --defaults-file="$CONF" -e 'SHUTDOWN;'
  echo "partner-search mysql stopped"
else
  echo "partner-search mysql is not running"
fi
