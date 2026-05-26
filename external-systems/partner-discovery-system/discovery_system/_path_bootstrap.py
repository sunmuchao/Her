"""Compatibility wrapper around the shared Her repo bootstrap helper."""

from __future__ import annotations

import sys
from pathlib import Path

_EXTERNAL_SYSTEMS_ROOT = Path(__file__).resolve().parents[2]
_EXTERNAL_SYSTEMS_ROOT_STR = str(_EXTERNAL_SYSTEMS_ROOT)
if _EXTERNAL_SYSTEMS_ROOT_STR not in sys.path:
    sys.path.insert(0, _EXTERNAL_SYSTEMS_ROOT_STR)

from partner_system_path_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402

__all__ = ["ensure_her_repo_on_sys_path"]
