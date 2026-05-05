from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def ensure_recommendation_system_on_path() -> Path:
    root = REPO_ROOT / "external-systems" / "partner-recommendation-system"
    path = str(root)
    if path not in sys.path:
        sys.path.insert(0, path)
    return root


def ensure_matchmaking_system_on_path() -> Path:
    root = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
    path = str(root)
    if path not in sys.path:
        sys.path.insert(0, path)
    return root


def ensure_chat_system_on_path() -> Path:
    root = REPO_ROOT / "external-systems" / "partner-chat-system"
    path = str(root)
    if path not in sys.path:
        sys.path.insert(0, path)
    return root
