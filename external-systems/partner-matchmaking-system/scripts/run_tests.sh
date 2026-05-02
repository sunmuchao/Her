#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

find "${SYSTEM_ROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${SYSTEM_ROOT}" -type f -name '*.pyc' -delete

PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s "${SYSTEM_ROOT}/tests" -v

find "${SYSTEM_ROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${SYSTEM_ROOT}" -type f -name '*.pyc' -delete
