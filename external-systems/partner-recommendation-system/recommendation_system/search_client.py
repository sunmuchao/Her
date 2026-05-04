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

from partner_search import load_self_profile, normalize_persona_profile, search_profiles  # noqa: E402


def normalize_requester_profile_for_subscription(
    profile: dict[str, Any] | None,
    *,
    fallback_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Convert a synced profile row back into the persona-style keys used by refresh."""

    return normalize_persona_profile(
        profile,
        fallback_profile=fallback_profile,
    )


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
        profile = load_self_profile(
            source=source,
            self_id=self_id,
            table_name=table_name,
        )
        return normalize_requester_profile_for_subscription(
            profile,
            fallback_profile=self_profile,
        )
    except Exception:
        return normalize_requester_profile_for_subscription(
            self_profile,
            fallback_profile=self_profile,
        )
