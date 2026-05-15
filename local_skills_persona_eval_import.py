"""Compatibility bridge for persona-eval tests under pytest importlib mode."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent / "local-skills" / "persona-eval" / "scripts"
script_text = str(SCRIPT_DIR)
if script_text not in sys.path:
    sys.path.insert(0, script_text)

import build_audit_summary  # noqa: E402, F401
import build_review_packets  # noqa: E402, F401
import normalize_agent_feedback  # noqa: E402, F401
import summarize_agent_feedback  # noqa: E402, F401


__all__ = [
    "build_audit_summary",
    "build_review_packets",
    "normalize_agent_feedback",
    "summarize_agent_feedback",
]
