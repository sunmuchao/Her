#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SKILL_ROOT}/../.." && pwd)"

find "${SKILL_ROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${SKILL_ROOT}" -type f -name '*.pyc' -delete

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" python3 -B -m unittest discover -s "${SKILL_ROOT}/tests" -v

find "${SKILL_ROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${SKILL_ROOT}" -type f -name '*.pyc' -delete
