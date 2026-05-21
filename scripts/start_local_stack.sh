#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
FRONTEND_DIR="${REPO_ROOT}/frontend/her-app"
GATEWAY_DIR="${REPO_ROOT}/external-systems/partner-http-gateway"
RUN_DIR="${REPO_ROOT}/.run"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"

WITH_SCHEDULER=0

usage() {
  cat <<'EOF'
Usage: scripts/start_local_stack.sh [--with-scheduler]

Starts the local Her stack in the background:
  1. local MySQL
  2. HTTP gateway
  3. frontend app
  4. optional task scheduler

Logs are written to .run/logs/
PID files are written to .run/pids/
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-scheduler)
      WITH_SCHEDULER=1
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

mkdir -p "${LOG_DIR}" "${PID_DIR}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_env_file() {
  local target="$1"
  local example="$2"
  if [[ ! -f "${target}" && -f "${example}" ]]; then
    cp "${example}" "${target}"
    echo "Created ${target} from ${example}"
  fi
}

ensure_python_env() {
  if [[ ! -x "${VENV_PY}" ]]; then
    echo "Python virtualenv missing; running scripts/dev_setup.sh"
    bash "${REPO_ROOT}/scripts/dev_setup.sh"
  fi
}

ensure_frontend_deps() {
  require_cmd pnpm
  if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "Installing frontend dependencies with pnpm"
    (cd "${FRONTEND_DIR}" && pnpm install)
  fi
}

pid_is_running() {
  local pidfile="$1"
  if [[ ! -f "${pidfile}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${pidfile}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

start_service() {
  local name="$1"
  local workdir="$2"
  local pidfile="$3"
  local logfile="$4"
  shift 4

  if pid_is_running "${pidfile}"; then
    echo "${name} already running (pid $(cat "${pidfile}"))"
    return 0
  fi

  rm -f "${pidfile}"
  (
    cd "${workdir}"
    nohup "$@" >"${logfile}" 2>&1 &
    echo $! >"${pidfile}"
  )

  sleep 2
  if pid_is_running "${pidfile}"; then
    echo "Started ${name} (pid $(cat "${pidfile}"))"
  else
    echo "Failed to start ${name}. Check ${logfile}" >&2
    exit 1
  fi
}

ensure_env_file "${REPO_ROOT}/.env" "${REPO_ROOT}/.env.example"
ensure_env_file "${FRONTEND_DIR}/.env.local" "${FRONTEND_DIR}/.env.example"
ensure_python_env
ensure_frontend_deps

echo "Starting local MySQL"
(cd "${REPO_ROOT}" && ./start_partner_mysql.sh)

start_service \
  "gateway" \
  "${GATEWAY_DIR}" \
  "${PID_DIR}/gateway.pid" \
  "${LOG_DIR}/gateway.log" \
  "${VENV_PY}" -m gateway

start_service \
  "frontend" \
  "${FRONTEND_DIR}" \
  "${PID_DIR}/frontend.pid" \
  "${LOG_DIR}/frontend.log" \
  pnpm dev --hostname 127.0.0.1 --port 3000

if [[ "${WITH_SCHEDULER}" == "1" ]]; then
  start_service \
    "scheduler" \
    "${REPO_ROOT}" \
    "${PID_DIR}/scheduler.pid" \
    "${LOG_DIR}/scheduler.log" \
    "${VENV_PY}" -m task_scheduler run
fi

cat <<EOF

Her local stack is up.

Frontend: http://127.0.0.1:3000
Gateway:  http://127.0.0.1:8765

Logs:
  ${LOG_DIR}/frontend.log
  ${LOG_DIR}/gateway.log
$( [[ "${WITH_SCHEDULER}" == "1" ]] && printf '  %s\n' "${LOG_DIR}/scheduler.log" )
EOF
