"""Shared helpers for recommendation-system maintenance scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PARTNER_REC_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def bootstrap_script_paths() -> None:
    for root in (_PARTNER_REC_ROOT, _REPO_ROOT):
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)


def load_json_arg(value: str | None, default: dict | list | None = None):
    if not value:
        return {} if default is None else default
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)
