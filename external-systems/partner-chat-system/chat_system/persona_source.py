"""Chat-specific helpers for resolving persona/profile data sources."""

from __future__ import annotations

import os
from typing import Any

from profile_service import get_public_profile


def persona_mysql_source() -> str | None:
    raw = (os.environ.get("HER_CHAT_PERSONA_MYSQL_SOURCE") or "").strip()
    return raw or None


def load_public_profile_from_persona_source(profile_id: Any) -> dict[str, Any] | None:
    source = persona_mysql_source()
    if not source:
        return None
    try:
        return get_public_profile(source_dsn=source, profile_id=int(profile_id))
    except (TypeError, ValueError):
        return None
    except Exception:
        return None


__all__ = [
    "load_public_profile_from_persona_source",
    "persona_mysql_source",
]
