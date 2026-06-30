#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat <<'EOF'
[deprecated] scripts/start_everything.sh 已废弃。
本地环境唯一推荐入口：

  docker compose up -d

如果你保留旧 MySQL 数据卷且 root 有密码，先执行：

  export MYSQL_ROOT_PASSWORD="$(cat secrets/mysql_root_password.txt)"

然后再启动：

  docker compose up -d
EOF

cd "${REPO_ROOT}"
exec docker compose up -d
