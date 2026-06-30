#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat <<'EOF'
[deprecated] scripts/stop_local_stack.sh 已废弃。
请改用 Docker Compose：

  docker compose down
EOF

cd "${REPO_ROOT}"
exec docker compose down
