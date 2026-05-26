"""Shared bootstrap helpers for external systems living under ``external-systems/``."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_PARTNER_SYSTEM_DIRS = (
    Path("external-systems/partner-recommendation-system"),
    Path("external-systems/partner-matchmaking-system"),
    Path("external-systems/partner-chat-system"),
    Path("external-systems/partner-discovery-system"),
    Path("external-systems/partner-http-gateway"),
)


def _repo_root_for_external_system_anchor(anchor_file: Path, *, levels_up: int = 3) -> Path:
    anchor = anchor_file.resolve()
    try:
        repo_root = anchor.parents[levels_up]
    except IndexError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(f"cannot resolve Her repo root from {anchor}") from exc
    if not (repo_root / "match_domain").is_dir():
        raise RuntimeError(f"match_domain not found under inferred repo root {repo_root}")
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    return repo_root


def ensure_her_repo_on_sys_path(anchor_file: Path, *, levels_up: int = 3) -> Path:
    _repo_root_for_external_system_anchor(anchor_file, levels_up=levels_up)
    mod = importlib.import_module("her_activate_repo")
    ensure = getattr(mod, "ensure_her_repo_on_sys_path", None)
    if ensure is None:
        raise RuntimeError("her_activate_repo.ensure_her_repo_on_sys_path is unavailable")
    return ensure(anchor_file)


def ensure_partner_system_roots_on_sys_path(repo_root: Path) -> None:
    for relative_dir in _PARTNER_SYSTEM_DIRS:
        package_root = repo_root / relative_dir
        package_root_str = str(package_root)
        if package_root_str not in sys.path:
            sys.path.insert(0, package_root_str)


__all__ = [
    "ensure_her_repo_on_sys_path",
    "ensure_partner_system_roots_on_sys_path",
]
