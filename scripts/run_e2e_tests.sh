#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_SMOKE=1

usage() {
  cat <<'EOF'
Usage: scripts/run_e2e_tests.sh [--python <python-bin>] [--skip-smoke]

Runs the serial end-to-end regression suite for the HTTP gateway and cross-system flows.

Notes:
- These tests share MySQL test databases and must run serially.
- They cover cross-system gateway flows, realistic user journeys, and v2 chat conversation visibility.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --skip-smoke)
      RUN_SMOKE=0
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

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python not found: ${PYTHON_BIN}" >&2
  exit 1
fi

run_unittest() {
  local target="$1"
  echo "[e2e] ${target}"
  PYTHONDONTWRITEBYTECODE=1 "${PYTHON_BIN}" -B -m unittest "${target}" -v
}

cd "${REPO_ROOT}"

run_unittest "external-systems/partner-http-gateway/gateway_tests/test_end_to_end_regression.py"
run_unittest "external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py"
run_unittest "external-systems/partner-http-gateway/gateway_tests/test_chat_conversations_v2.py"

if [[ "${RUN_SMOKE}" == "1" ]]; then
  echo "[e2e] external-systems/partner-chat-system/scripts/run_matchmaker_c_smoke.py --reset"
  "${PYTHON_BIN}" "${REPO_ROOT}/external-systems/partner-chat-system/scripts/run_matchmaker_c_smoke.py" --reset >/dev/null
fi

echo "[e2e] ok"
