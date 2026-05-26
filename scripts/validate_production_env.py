#!/usr/bin/env python3
"""Validate production-oriented environment before deploy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()

from her_production import (  # noqa: E402
    assert_production_discovery_agent_isolation,
    assert_production_ledger_config,
    is_production_mode,
)


def main() -> int:
    os.environ.setdefault("HER_PRODUCTION_MODE", "1")
    errors: list[str] = []

    if not is_production_mode():
        print("HER_PRODUCTION_MODE is not enabled; set HER_PRODUCTION_MODE=1 to validate production.")
        return 1

    try:
        assert_production_ledger_config()
    except RuntimeError as exc:
        errors.append(str(exc))

    try:
        assert_production_discovery_agent_isolation()
    except RuntimeError as exc:
        errors.append(str(exc))

    surface = str(os.environ.get("PARTNER_GATEWAY_SURFACE") or "").strip().lower()
    if surface in {"", "all"}:
        errors.append("Set PARTNER_GATEWAY_SURFACE to public|ops|internal per deployment unit.")

    if str(os.environ.get("HER_ALLOW_LEGACY_TIMELINE_FALLBACK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        errors.append("HER_ALLOW_LEGACY_TIMELINE_FALLBACK must be unset in production.")

    storage = str(os.environ.get("HER_PROXY_INTRO_STORAGE") or "matchmaking").strip().lower()
    if storage != "matchmaking":
        errors.append("HER_PROXY_INTRO_STORAGE must be matchmaking in production.")

    pool = int(str(os.environ.get("PARTNER_GATEWAY_DB_POOL_MAX") or "0").strip() or "0")
    if pool <= 0:
        errors.append("PARTNER_GATEWAY_DB_POOL_MAX must be > 0 in production.")

    if errors:
        print("Production environment validation failed:")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("Production environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
