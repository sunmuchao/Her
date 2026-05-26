"""Shared sys.path bootstrap for repository scripts."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPTS_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from her_monorepo_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402
from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path  # noqa: E402


def bootstrap_repo() -> Path:
    root = ensure_her_repo_on_sys_path(_SCRIPTS_DIR)
    ensure_partner_system_roots_on_sys_path(root)
    return root


__all__ = ["REPO_ROOT", "bootstrap_repo"]
