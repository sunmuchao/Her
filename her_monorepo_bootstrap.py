"""Single source of truth for putting the Her monorepo root on ``sys.path`` (stdlib only).

Outer packages load ``her_activate_repo`` (via ``importlib``) which loads this file from
``recommendation_system._path_bootstrap`` / ``matchmaking_system._path_bootstrap`` (and the
HTTP gateway) before any ``match_domain`` import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_her_repo_on_sys_path(anchor_file: Path, *, repo_root_hint: Path | None = None) -> Path:
    """
    Ensure the repository root (contains ``match_domain/``) is first on ``sys.path``.

    Precedence: ``HER_REPO_ROOT`` → ``repo_root_hint`` (directory of this file when loaded) →
    walk ``anchor_file`` parents for ``local-skills/partner-search`` + ``match_domain`` →
    infer from ``.../<root>/external-systems/...`` layout.
    """

    env = os.environ.get("HER_REPO_ROOT")
    if env and str(env).strip():
        root = Path(env).expanduser().resolve()
    elif repo_root_hint is not None:
        root = repo_root_hint.resolve()
    else:
        here = anchor_file.resolve()
        root = None
        for p in (here.parent, *here.parents):
            if (p / "local-skills" / "partner-search").is_dir() and (p / "match_domain").is_dir():
                root = p
                break
        if root is None and "external-systems" in here.parts:
            idx = here.parts.index("external-systems")
            if idx > 0:
                root = Path(*here.parts[:idx])
        if root is None:
            raise RuntimeError(
                "Cannot locate Her monorepo root. Set HER_REPO_ROOT to the directory that "
                "contains match_domain/ and local-skills/partner-search/, or run from a full checkout."
            )

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def activate_for_anchor(anchor_file: Path) -> Path:
    """Called after this module was loaded from ``<repo>/her_monorepo_bootstrap.py``."""

    return ensure_her_repo_on_sys_path(anchor_file, repo_root_hint=Path(__file__).resolve().parent)


__all__ = ["activate_for_anchor", "ensure_her_repo_on_sys_path"]
