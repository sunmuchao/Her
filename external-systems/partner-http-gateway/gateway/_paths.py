"""Put monorepo root and partner-system package dirs on ``sys.path`` before other imports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_GATEWAY_DIR = Path(__file__).resolve().parent
_SEARCH_ANCHOR = _GATEWAY_DIR


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
            "gateway: her_activate_repo.py not found; set HER_REPO_ROOT or run from a full Her checkout."
        )
    spec = importlib.util.spec_from_file_location("her_activate_repo", activate_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"gateway: cannot load {activate_py}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("her_activate_repo", mod)
    spec.loader.exec_module(mod)
    return mod


def _bootstrap_monorepo_root() -> Path:
    mod = _load_her_activate_repo()
    return mod.ensure_her_repo_on_sys_path(_GATEWAY_DIR / "_paths.py")


_REPO_ROOT = _bootstrap_monorepo_root()
_REC_ROOT = _REPO_ROOT / "external-systems" / "partner-recommendation-system"
_MM_ROOT = _REPO_ROOT / "external-systems" / "partner-matchmaking-system"
_CHAT_ROOT = _REPO_ROOT / "external-systems" / "partner-chat-system"
_DISCOVERY_ROOT = _REPO_ROOT / "external-systems" / "partner-discovery-system"

for _p in (_REC_ROOT, _MM_ROOT, _CHAT_ROOT, _DISCOVERY_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)
