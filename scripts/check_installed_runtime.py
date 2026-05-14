#!/usr/bin/env python3

"""Verify installed-runtime imports without checkout-specific ``sys.path`` fallbacks."""

from __future__ import annotations

import importlib
import json
from typing import Any

TARGET_MODULES = (
    "partner_search",
    "persona_memory_sync",
    "recommendation_system.service",
    "matchmaking_system.service",
    "chat_system.persona_jobs",
    "gateway.app",
    "discovery_system.service",
)


def _module_summary(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - report import failures in the payload
        return {
            "module": module_name,
            "file": None,
            "import_error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "module": module_name,
        "file": getattr(module, "__file__", None),
        "import_error": None,
    }


def main() -> int:
    payload = {
        "modules": [_module_summary(module_name) for module_name in TARGET_MODULES],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if any(item["import_error"] for item in payload["modules"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
