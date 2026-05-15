#!/usr/bin/env python3

"""Compatibility wrapper for the packaged partner-search engine."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from partner_search.search_candidates import main  # noqa: E402


if __name__ == "__main__":
    main()
