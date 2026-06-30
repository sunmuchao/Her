#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${1:-}" == "--check-only" ]]; then
  cd "${REPO_ROOT}"
  exec docker compose ps
fi

cat <<'EOF'
[deprecated] scripts/start_local_dev.sh 已废弃。
本地环境唯一推荐入口：

  docker compose up -d
EOF

cd "${REPO_ROOT}"
exec docker compose up -d
