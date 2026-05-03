"""Bridge from the external recommendation system to the partner-search API."""

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

from scripts import search_candidates as engine  # noqa: E402
from partner_search import search_profiles  # noqa: E402


def run_partner_search(**kwargs: Any) -> dict[str, Any]:
    """Execute partner-search through its stable Python API."""

    return search_profiles(**kwargs)


def load_requester_profile(
    *,
    source: str,
    self_id: int | None,
    table_name: str | None = None,
    self_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the latest requester profile row for persona-driven refreshes."""

    if self_id is None:
        return self_profile

    try:
        records = engine.collect_source_records_for_request(
            [source],
            table_name=table_name,
            criteria={},
            self_id=self_id,
        )
        return engine.build_self_profile(
            records,
            self_id=self_id,
            profile_input=self_profile,
        )
    except Exception:
        return self_profile
