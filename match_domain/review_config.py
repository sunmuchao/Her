"""Review policy configuration loaded from environment."""

from __future__ import annotations

import os
from typing import Any


def review_policy_from_env() -> dict[str, Any]:
    return {
        "require_user_review": os.environ.get("HER_REQUIRE_USER_REVIEW", "true").lower()
        in {"1", "true", "yes"},
        "auto_deliver_on_system_pass": os.environ.get("HER_AUTO_DELIVER_ON_SYSTEM_PASS", "true").lower()
        in {"1", "true", "yes"},
        "direct_greet_requires_review": os.environ.get("HER_DIRECT_GREET_REQUIRES_REVIEW", "false").lower()
        in {"1", "true", "yes"},
    }


__all__ = ["review_policy_from_env"]
