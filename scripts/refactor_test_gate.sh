#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "[refactor-gate] ruff"
ruff check "${REPO_ROOT}"

echo "[refactor-gate] python packaging"
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/check_skill_packaging.py"

echo "[refactor-gate] python tests (core + gateway + local-skills)"
"${PYTHON_BIN}" -m pytest \
  "${REPO_ROOT}/tests" \
  "${REPO_ROOT}/external-systems/partner-http-gateway/gateway_tests" \
  "${REPO_ROOT}/local-skills/partner-search/tests" \
  "${REPO_ROOT}/local-skills/persona-memory-sync/tests" \
  "${REPO_ROOT}/local-skills/persona-eval/tests" \
  "${REPO_ROOT}/external-systems/partner-recommendation-system/tests" \
  "${REPO_ROOT}/external-systems/partner-matchmaking-system/tests" \
  "${REPO_ROOT}/external-systems/partner-discovery-system/tests" \
  "${REPO_ROOT}/external-systems/partner-chat-system/tests/test_chat_conversations.py" \
  -q

echo "[refactor-gate] frontend unit + build"
(
  cd "${REPO_ROOT}/frontend/her-app"
  pnpm run lint
  pnpm run test:unit
  pnpm run build
)

echo "[refactor-gate] ok"
