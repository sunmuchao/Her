"""Bridge from the matchmaking outer system to the persona-memory-sync API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping


def ensure_persona_memory_skill_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    skill_root = repo_root / "local-skills" / "persona-memory-sync"
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    return skill_root


ensure_persona_memory_skill_on_path()

from persona_memory_sync import upsert_persona_memory  # noqa: E402


def sync_persona_memory(request: Mapping[str, Any]) -> dict[str, Any]:
    return upsert_persona_memory(dict(request))
