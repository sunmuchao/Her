"""Shared bootstrap loader for partner systems under ``external-systems/``."""

from __future__ import annotations

import sys
from typing import Callable


def load_ensure_her_repo_on_sys_path() -> Callable[..., object]:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    from her_repo_path_bootstrap import ensure_her_repo_on_sys_path

    return ensure_her_repo_on_sys_path


__all__ = ["load_ensure_her_repo_on_sys_path"]
