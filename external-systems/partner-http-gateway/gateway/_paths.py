"""Put monorepo root and partner-system package dirs on ``sys.path`` before other imports."""

from __future__ import annotations

import sys
from pathlib import Path

_GATEWAY_PATH = Path(__file__).resolve()


def _bootstrap_gateway_paths() -> Path:
    repo_root = _GATEWAY_PATH.parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    from her_repo_path_bootstrap import (
        ensure_her_repo_on_sys_path,
        ensure_partner_system_roots_on_sys_path,
    )

    resolved_repo_root = ensure_her_repo_on_sys_path(_GATEWAY_PATH)
    ensure_partner_system_roots_on_sys_path(resolved_repo_root)
    return resolved_repo_root


_REPO_ROOT = _bootstrap_gateway_paths()
