"""Load ``her_activate_repo`` from the checkout and apply ``sys.path`` (stdlib only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SEARCH_ANCHOR = Path(__file__).resolve()


def _load_her_activate_repo():
    mod = sys.modules.get("her_activate_repo")
    if mod is not None:
        return mod
    try:
        import her_activate_repo as mod
    except ImportError:
        mod = None
    if mod is not None and hasattr(mod, "ensure_her_repo_on_sys_path"):
        return mod
    activate_py: Path | None = None
    for p in (_SEARCH_ANCHOR.parent, *_SEARCH_ANCHOR.parents):
        cand = p / "her_activate_repo.py"
        if cand.is_file() and (p / "match_domain").is_dir():
            activate_py = cand
            break
    if activate_py is None:
        raise RuntimeError(
            "her_activate_repo.py not found; set HER_REPO_ROOT or use a full Her monorepo checkout."
        )
    spec = importlib.util.spec_from_file_location("her_activate_repo", activate_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load her_activate_repo from {activate_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("her_activate_repo", mod)
    spec.loader.exec_module(mod)
    return mod


def ensure_her_repo_on_sys_path(anchor_file: Path) -> Path:
    return _load_her_activate_repo().ensure_her_repo_on_sys_path(anchor_file)


__all__ = ["ensure_her_repo_on_sys_path"]
