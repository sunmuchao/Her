#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
APP_DIR="$ROOT_DIR/frontend/her-app"
GATEWAY_DIR="$ROOT_DIR/external-systems/partner-http-gateway"
VENV_PY="${ROOT_DIR}/.venv/bin/python"
HOST="${PARTNER_GATEWAY_HOST:-127.0.0.1}"
PORT="${PARTNER_GATEWAY_PORT:-8765}"
BASE_URL="${PARTNER_GATEWAY_BASE_URL:-http://${HOST}:${PORT}}"
LOG_FILE="${HER_GATEWAY_LOG_FILE:-/tmp/her-partner-gateway-dev.log}"

usage() {
  cat <<'EOF'
Usage:
  bash ./scripts/gateway-dev.sh health
  bash ./scripts/gateway-dev.sh start

Commands:
  health  Check whether PARTNER_GATEWAY_BASE_URL points to the real partner gateway
  start   Start the repo's partner gateway on the configured host/port and wait for /health
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

print_health_hint() {
  cat <<EOF
Expected a partner gateway JSON payload from ${BASE_URL}/health.
If you see another service format or /v1/... returns {"detail":"Not Found"}, then PARTNER_GATEWAY_BASE_URL is pointing to the wrong upstream.
EOF
}

print_mysql_hint() {
  cat <<EOF
Gateway startup usually needs local MySQL first.
Start it from the repo root with:
  ./start_partner_mysql.sh
Then retry:
  pnpm gateway:start
EOF
}

check_health() {
  require_cmd curl
  local body
  if ! body="$(curl -fsS "${BASE_URL}/health")"; then
    echo "Gateway health check failed: ${BASE_URL}/health" >&2
    print_health_hint >&2
    exit 1
  fi

  if [[ "${body}" == *'"services"'* && "${body}" == *'"surface"'* && "${body}" == *'"jsonrpc_enabled"'* ]]; then
    echo "partner gateway is healthy: ${BASE_URL}"
    echo "${body}"
    return 0
  fi

  echo "Gateway responded, but it does not look like partner-http-gateway:" >&2
  echo "${body}" >&2
  print_health_hint >&2
  exit 1
}

start_gateway() {
  require_cmd curl

  if [[ ! -x "${VENV_PY}" ]]; then
    echo "Missing virtualenv python: ${VENV_PY}" >&2
    echo "Run: bash ${ROOT_DIR}/scripts/dev_setup.sh" >&2
    exit 1
  fi

  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    echo "A service is already listening at ${BASE_URL}"
    check_health
    return 0
  fi

  echo "Starting partner gateway at ${BASE_URL}"
  (
    cd "${GATEWAY_DIR}"
    nohup "${VENV_PY}" -m gateway --host "${HOST}" --port "${PORT}" >"${LOG_FILE}" 2>&1 &
    echo $! > /tmp/her-partner-gateway-dev.pid
  )

  for _ in $(seq 1 20); do
    if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
      check_health
      echo "gateway log: ${LOG_FILE}"
      return 0
    fi
    sleep 1
  done

  echo "Gateway failed readiness check. See ${LOG_FILE}" >&2
  if grep -q "Can't connect to MySQL server" "${LOG_FILE}" 2>/dev/null; then
    print_mysql_hint >&2
  fi
  exit 1
}

main() {
  cd "${APP_DIR}"

  case "${1:-}" in
    health)
      check_health
      ;;
    start)
      start_gateway
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
}

main "${@:-}"
