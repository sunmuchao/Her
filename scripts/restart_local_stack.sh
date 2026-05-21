#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/restart_local_stack.sh [--with-scheduler] [--with-mysql]

One-click restart for the local Her stack:
  1. stop frontend, gateway, scheduler (and MySQL if --with-mysql)
  2. start everything via scripts/start_local_stack.sh

Examples:
  scripts/restart_local_stack.sh
  scripts/restart_local_stack.sh --with-scheduler
  scripts/restart_local_stack.sh --with-mysql
EOF
}

WITH_SCHEDULER=0
WITH_MYSQL=0
START_ARGS=()
STOP_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-scheduler)
      WITH_SCHEDULER=1
      START_ARGS+=(--with-scheduler)
      shift
      ;;
    --with-mysql)
      WITH_MYSQL=1
      STOP_ARGS+=(--with-mysql)
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo "=== Restarting Her local stack ==="

bash "${SCRIPT_DIR}/stop_local_stack.sh" "${STOP_ARGS[@]+"${STOP_ARGS[@]}"}"

if [[ "${WITH_MYSQL}" == "1" ]]; then
  sleep 1
fi

bash "${SCRIPT_DIR}/start_local_stack.sh" "${START_ARGS[@]+"${START_ARGS[@]}"}"
