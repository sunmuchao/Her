"""Shared sys.path bootstrap for partner external-system packages."""

from __future__ import annotations

import sys
from pathlib import Path

_EXTERNAL_SYSTEMS_ROOT = Path(__file__).resolve().parent
_EXTERNAL_SYSTEMS_ROOT_STR = str(_EXTERNAL_SYSTEMS_ROOT)
if _EXTERNAL_SYSTEMS_ROOT_STR not in sys.path:
    sys.path.insert(0, _EXTERNAL_SYSTEMS_ROOT_STR)

from her_external_bootstrap import load_ensure_her_repo_on_sys_path  # noqa: E402

ensure_her_repo_on_sys_path = load_ensure_her_repo_on_sys_path()

__all__ = ["ensure_her_repo_on_sys_path"]
