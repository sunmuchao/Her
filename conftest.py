"""Pytest bootstrap for repository-local imports."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
repo_text = str(REPO_ROOT)
if repo_text in sys.path:
    sys.path.remove(repo_text)
sys.path.insert(0, repo_text)
