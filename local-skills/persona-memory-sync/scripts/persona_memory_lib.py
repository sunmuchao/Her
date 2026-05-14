#!/usr/bin/env python3

"""Compatibility wrapper for the packaged persona-memory library."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.persona_memory_lib import *  # noqa: E402,F401,F403
