"""Partner-search runner for matchmaking refresh workflows."""

from __future__ import annotations

from typing import Any

from match_domain.search_visibility import run_partner_search as _run_partner_search
from partner_search import search_profiles


def run_partner_search(**kwargs: Any) -> dict[str, Any]:
    return _run_partner_search(search_profiles, **kwargs)
