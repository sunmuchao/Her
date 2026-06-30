#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat <<'EOF'
[deprecated] scripts/restart_local_stack.sh 已废弃。
请改用 Docker Compose：

  docker compose down
  docker compose up -d
EOF

cd "${REPO_ROOT}"
docker compose down
exec docker compose up -d
