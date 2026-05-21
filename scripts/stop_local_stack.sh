#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_DIR="${REPO_ROOT}/.run"
PID_DIR="${RUN_DIR}/pids"

WITH_MYSQL=0

usage() {
  cat <<'EOF'
Usage: scripts/stop_local_stack.sh [--with-mysql]

Stops the local Her stack started by scripts/start_local_stack.sh:
  - frontend (port 3000 fallback)
  - HTTP gateway (port 8765 fallback)
  - task scheduler (if pid file exists)
  - optional local MySQL (--with-mysql)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-mysql)
      WITH_MYSQL=1
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

stop_pidfile() {
  local name="$1"
  local pidfile="$2"

  if [[ ! -f "${pidfile}" ]]; then
    echo "${name}: not running (no pid file)"
    return 0
  fi

  local pid
  pid="$(cat "${pidfile}" 2>/dev/null || true)"
  rm -f "${pidfile}"

  if [[ -z "${pid}" ]]; then
    echo "${name}: stale pid file removed"
    return 0
  fi

  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    echo "${name}: not running (stale pid ${pid})"
    return 0
  fi

  echo "Stopping ${name} (pid ${pid})..."
  kill -TERM "${pid}" >/dev/null 2>&1 || true
  for _ in $(seq 1 10); do
    kill -0 "${pid}" >/dev/null 2>&1 || break
    sleep 0.5
  done
  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill -KILL "${pid}" >/dev/null 2>&1 || true
  fi
  echo "Stopped ${name}"
}

stop_port() {
  local name="$1"
  local port="$2"

  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi

  local pids
  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "Stopping ${name} listeners on port ${port}..."
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill -TERM "${pid}" >/dev/null 2>&1 || true
  done <<<"${pids}"

  sleep 1

  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    while IFS= read -r pid; do
      [[ -n "${pid}" ]] || continue
      kill -KILL "${pid}" >/dev/null 2>&1 || true
    done <<<"${pids}"
  fi
}

echo "Stopping Her local stack..."

stop_pidfile "scheduler" "${PID_DIR}/scheduler.pid"
stop_pidfile "frontend" "${PID_DIR}/frontend.pid"
stop_pidfile "gateway" "${PID_DIR}/gateway.pid"

stop_port "frontend" 3000
stop_port "gateway" 8765

if [[ "${WITH_MYSQL}" == "1" ]]; then
  if [[ -x "${REPO_ROOT}/stop_partner_mysql.sh" ]]; then
    (cd "${REPO_ROOT}" && ./stop_partner_mysql.sh) || true
  else
    echo "stop_partner_mysql.sh not found; skipped MySQL shutdown" >&2
  fi
fi

echo "Her local stack stopped."
