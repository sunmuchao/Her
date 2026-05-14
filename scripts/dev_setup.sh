#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_DIR="${REPO_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-}"

usage() {
  cat <<'EOF'
Usage: scripts/dev_setup.sh [--python <python-bin>] [--venv-dir <path>]

Creates a local virtualenv, installs the repo in editable mode, and runs
skill-packaging smoke checks.
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

  echo "No Python >= 3.10 interpreter found. Set --python or PYTHON_BIN." >&2
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
echo "[dev-setup] using ${PYTHON_BIN}"
echo "[dev-setup] venv: ${VENV_DIR}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
VENV_PY="${VENV_DIR}/bin/python"
PARTNER_SEARCH_BIN="${VENV_DIR}/bin/partner-search"
PERSONA_MEMORY_BIN="${VENV_DIR}/bin/persona-memory-sync"

"${VENV_PY}" -m pip install -U pip setuptools wheel
"${VENV_PY}" -m pip install -e "${REPO_ROOT}[dev]"

"${VENV_PY}" "${REPO_ROOT}/scripts/check_skill_packaging.py" --require-console-scripts
"${VENV_PY}" "${REPO_ROOT}/scripts/check_installed_runtime.py"
"${PARTNER_SEARCH_BIN}" --help >/dev/null
"${PERSONA_MEMORY_BIN}" --help >/dev/null

cat <<EOF
[dev-setup] done
activate with:
  source "${VENV_DIR}/bin/activate"
EOF
