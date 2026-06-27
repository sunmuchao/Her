#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GPT_SOVITS_DIR="${REPO_ROOT}/external-systems/GPT-SoVITS"
GPT_SOVITS_START_SCRIPT="${GPT_SOVITS_DIR}/start-api-ultra-minimal.sh"
RUN_DIR="${REPO_ROOT}/.run"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"

WITH_GPT_SOVITS=1
WITH_SCHEDULER=1

usage() {
  cat <<'EOF'
Usage: scripts/start_everything.sh [--without-gpt-sovits] [--without-scheduler]

One-click startup for the full local Her environment:
  1. docker compose services (mysql/minio/signaling-server, etc.)
  2. business stack (local MySQL, SSE server, gateway, frontend)
  3. optional scheduler
  4. optional GPT-SoVITS API service

Examples:
  scripts/start_everything.sh
  scripts/start_everything.sh --without-gpt-sovits
  scripts/start_everything.sh --without-scheduler
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --without-gpt-sovits)
      WITH_GPT_SOVITS=0
      shift
      ;;
    --without-scheduler)
      WITH_SCHEDULER=0
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

pid_is_running() {
  local pidfile="$1"
  if [[ ! -f "${pidfile}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${pidfile}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

start_background_service() {
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

require_cmd docker

echo "=== Starting docker compose services ==="
(cd "${REPO_ROOT}" && docker compose up -d mysql minio signaling-server)

echo ""
echo "=== Starting Her business stack ==="
START_STACK_ARGS=()
if [[ "${WITH_SCHEDULER}" == "1" ]]; then
  START_STACK_ARGS+=(--with-scheduler)
fi
(cd "${REPO_ROOT}" && bash ./scripts/start_local_stack.sh "${START_STACK_ARGS[@]+"${START_STACK_ARGS[@]}"}")

if [[ "${WITH_GPT_SOVITS}" == "1" ]]; then
  echo ""
  echo "=== Starting GPT-SoVITS ==="
  if [[ ! -x "${GPT_SOVITS_START_SCRIPT}" ]]; then
    echo "GPT-SoVITS start script not found: ${GPT_SOVITS_START_SCRIPT}" >&2
    echo "Run ./scripts/quick-deploy-gpt-sovits.sh first if needed." >&2
    exit 1
  fi

  start_background_service \
    "gpt-sovits" \
    "${GPT_SOVITS_DIR}" \
    "${PID_DIR}/gpt-sovits.pid" \
    "${LOG_DIR}/gpt-sovits.log" \
    bash "${GPT_SOVITS_START_SCRIPT}"
fi

cat <<EOF

Everything is starting.

Core services:
  Frontend:   http://127.0.0.1:3000
  Gateway:    http://127.0.0.1:8765
  SSE:        http://127.0.0.1:8081
  MinIO:      http://127.0.0.1:9000
  MinIO Web:  http://127.0.0.1:9001
$( [[ "${WITH_GPT_SOVITS}" == "1" ]] && printf '  GPT-SoVITS: http://127.0.0.1:9880\n' )

Logs:
  ${LOG_DIR}/frontend.log
  ${LOG_DIR}/gateway.log
  ${LOG_DIR}/sse-server.log
$( [[ "${WITH_SCHEDULER}" == "1" ]] && printf '  %s\n' "${LOG_DIR}/scheduler.log" )
$( [[ "${WITH_GPT_SOVITS}" == "1" ]] && printf '  %s\n' "${LOG_DIR}/gpt-sovits.log" )
EOF
