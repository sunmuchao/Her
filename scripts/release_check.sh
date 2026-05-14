#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_DIR="${REPO_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-}"
RUN_TESTS=1
RUN_SCHEMA_CHECK=0
RUN_E2E=0

usage() {
  cat <<'EOF'
Usage: scripts/release_check.sh [--python <python-bin>] [--venv-dir <path>] [--skip-tests] [--with-schema] [--with-e2e]

Checks that the local skills are packaged correctly in the current environment.
When --with-schema is set, also runs schema release-check with HER_SCHEMA_INIT_MODE=validate.
When --with-e2e is set, also runs the serial end-to-end regression suite.
EOF
}

version_supported() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

resolve_python() {
  if [[ -n "${PYTHON_BIN}" ]]; then
    if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      echo "Configured python not found: ${PYTHON_BIN}" >&2
      exit 1
    fi
    if ! version_supported "${PYTHON_BIN}"; then
      echo "Configured python must be >= 3.10: ${PYTHON_BIN}" >&2
      exit 1
    fi
    printf '%s\n' "${PYTHON_BIN}"
    return
  fi

  if [[ -x "${VENV_DIR}/bin/python" ]] && version_supported "${VENV_DIR}/bin/python"; then
    printf '%s\n' "${VENV_DIR}/bin/python"
    return
  fi

  local candidate
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if ! command -v "${candidate}" >/dev/null 2>&1; then
      continue
    fi
    if version_supported "${candidate}"; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  echo "No Python >= 3.10 interpreter found. Set --python or run scripts/dev_setup.sh first." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --venv-dir)
      VENV_DIR="${2:-}"
      shift 2
      ;;
    --skip-tests)
      RUN_TESTS=0
      shift
      ;;
    --with-schema)
      RUN_SCHEMA_CHECK=1
      shift
      ;;
    --with-e2e)
      RUN_E2E=1
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

PYTHON_BIN="$(resolve_python)"
PARTNER_SEARCH_BIN="$(cd "$(dirname "${PYTHON_BIN}")" && pwd)/partner-search"
PERSONA_MEMORY_BIN="$(cd "$(dirname "${PYTHON_BIN}")" && pwd)/persona-memory-sync"

echo "[release-check] using ${PYTHON_BIN}"
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/check_skill_packaging.py" --require-console-scripts
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/check_installed_runtime.py"

if [[ ! -x "${PARTNER_SEARCH_BIN}" || ! -x "${PERSONA_MEMORY_BIN}" ]]; then
  echo "Console scripts not found next to ${PYTHON_BIN}. Run scripts/dev_setup.sh first." >&2
  exit 1
fi

"${PARTNER_SEARCH_BIN}" --help >/dev/null
"${PERSONA_MEMORY_BIN}" --help >/dev/null

if [[ "${RUN_TESTS}" == "1" ]]; then
  "${PYTHON_BIN}" -m pytest \
    tests/test_db_migrations.py \
    tests/test_skill_packaging.py \
    local-skills/partner-search/tests/test_partner_search_api.py \
    local-skills/partner-search/tests/test_search_candidates.py \
    local-skills/persona-memory-sync/tests/test_persona_memory_api.py \
    local-skills/persona-memory-sync/tests/test_persona_memory_engine.py \
    local-skills/persona-memory-sync/tests/test_persona_memory.py \
    local-skills/persona-memory-sync/tests/test_persona_memory_audit.py \
    local-skills/persona-memory-sync/tests/test_persona_memory_scripts.py \
    local-skills/persona-eval/tests/local_skills_persona_eval_import.py \
    external-systems/partner-discovery-system/tests/test_discovery_system.py \
    -q
fi

if [[ "${RUN_SCHEMA_CHECK}" == "1" ]]; then
  HER_SCHEMA_INIT_MODE=validate "${PYTHON_BIN}" "${REPO_ROOT}/scripts/schema_workflow.py" release-check
fi

if [[ "${RUN_E2E}" == "1" ]]; then
  "${REPO_ROOT}/scripts/run_e2e_tests.sh" --python "${PYTHON_BIN}"
fi

echo "[release-check] ok"
