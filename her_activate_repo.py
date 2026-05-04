"""Load ``her_monorepo_bootstrap`` from the checkout and apply ``sys.path`` (stdlib only).

Partner packages and the HTTP gateway load this module via ``importlib`` (see
``recommendation_system._path_bootstrap``) before importing ``match_domain`` or
other repo-root modules.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def ensure_her_repo_on_sys_path(anchor_file: Path) -> Path:
    cached = sys.modules.get("her_monorepo_bootstrap")
    if cached is not None and hasattr(cached, "activate_for_anchor"):
        return cached.activate_for_anchor(anchor_file)

    here = anchor_file.resolve()
    bootstrap_py: Path | None = None
    repo_root: Path | None = None
    for p in (here.parent, *here.parents):
        cand = p / "her_monorepo_bootstrap.py"
        if cand.is_file() and (p / "match_domain").is_dir():
            bootstrap_py = cand
            repo_root = p
            break
    if bootstrap_py is None or repo_root is None:
        raise RuntimeError(
            "her_monorepo_bootstrap.py not found; set HER_REPO_ROOT or use a full Her monorepo checkout."
        )
    spec = importlib.util.spec_from_file_location("her_monorepo_bootstrap", bootstrap_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load her_monorepo_bootstrap from {bootstrap_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("her_monorepo_bootstrap", mod)
    spec.loader.exec_module(mod)
    return mod.activate_for_anchor(anchor_file)


__all__ = ["ensure_her_repo_on_sys_path"]
