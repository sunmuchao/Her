from __future__ import annotations

from pathlib import Path

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_partner_system_on_path(system_dir_name: str) -> Path:
    ensure_partner_system_roots_on_sys_path(REPO_ROOT)
    return REPO_ROOT / "external-systems" / system_dir_name


def ensure_recommendation_system_on_path() -> Path:
    return _ensure_partner_system_on_path("partner-recommendation-system")


def ensure_matchmaking_system_on_path() -> Path:
    return _ensure_partner_system_on_path("partner-matchmaking-system")


def ensure_chat_system_on_path() -> Path:
    return _ensure_partner_system_on_path("partner-chat-system")
