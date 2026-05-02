"""Bridge from the matchmaking outer system to the partner-search API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def ensure_partner_search_skill_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    skill_root = repo_root / "local-skills" / "partner-search"
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    return skill_root


ensure_partner_search_skill_on_path()

from partner_search import search_profiles  # noqa: E402


def run_partner_search(**kwargs: Any) -> dict[str, Any]:
    return search_profiles(**kwargs)
