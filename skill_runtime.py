"""Shared helpers for importing local skill packages through their public APIs."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def _ensure_skill_on_path(skill_dir_name: str) -> Path:
    skill_root = REPO_ROOT / "local-skills" / skill_dir_name
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    return skill_root


def ensure_partner_search_skill_on_path() -> Path:
    return _ensure_skill_on_path("partner-search")


def ensure_persona_memory_skill_on_path() -> Path:
    return _ensure_skill_on_path("persona-memory-sync")


__all__ = [
    "ensure_partner_search_skill_on_path",
    "ensure_persona_memory_skill_on_path",
]
