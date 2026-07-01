"""Feature flags for match-chat assistant behavior."""

from __future__ import annotations

import os


def is_match_chat_ai_assistant_enabled() -> bool:
    value = os.environ.get("HER_MATCH_CHAT_AI_ASSISTANT_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


__all__ = ["is_match_chat_ai_assistant_enabled"]
