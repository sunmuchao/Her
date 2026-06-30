#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat <<'EOF'
[deprecated] scripts/start_local_stack.sh 已废弃。
请只使用 Docker Compose 启动本地环境：

  docker compose up -d

查看状态：

  docker compose ps

查看关键日志：

  docker compose logs -f bootstrap gateway-public frontend
EOF

cd "${REPO_ROOT}"
exec docker compose up -d
