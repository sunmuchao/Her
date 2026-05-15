"""Compatibility wrapper around the shared Her repo bootstrap helper."""

from __future__ import annotations

import sys
from pathlib import Path

def ensure_her_repo_on_sys_path(anchor_file: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    from her_repo_path_bootstrap import ensure_her_repo_on_sys_path as shared_ensure

    return shared_ensure(anchor_file)


__all__ = ["ensure_her_repo_on_sys_path"]
