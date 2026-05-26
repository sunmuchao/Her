#!/usr/bin/env python3
"""Validate §10.3 tech-optimization environment conventions (dev + production)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()

REQUIRED_ENV_DEFAULTS = {
    "HER_RELATION_LEDGER_READ_MODE": "ledger_primary",
    "HER_PROXY_INTRO_STORAGE": "matchmaking",
}

PRODUCTION_REQUIRED = {
    "PARTNER_GATEWAY_DB_POOL_MAX": lambda v: int(v) > 0,
    "PARTNER_SEARCH_CACHE_TTL_SECONDS": lambda v: int(v) > 0,
}

FORBIDDEN_IN_PRODUCTION = {
    "HER_ALLOW_LEGACY_TIMELINE_FALLBACK": {"1", "true", "yes", "on"},
}

COMPOSE_REQUIRED_SNIPPETS = (
    "HER_PROXY_INTRO_STORAGE: matchmaking",
    "HER_RELATION_LEDGER_READ_MODE: ledger_primary",
    "PARTNER_GATEWAY_DB_POOL_MAX",
)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _check_process_env(*, production: bool) -> list[str]:
    errors: list[str] = []
    for key, expected in REQUIRED_ENV_DEFAULTS.items():
        actual = str(os.environ.get(key) or "").strip().lower()
        if actual != expected:
            errors.append(f"{key} must be {expected!r} (got {actual!r})")

    if _truthy(os.environ.get("HER_ALLOW_LEGACY_TIMELINE_FALLBACK")):
        errors.append("HER_ALLOW_LEGACY_TIMELINE_FALLBACK must be unset")

    if production:
        for key, predicate in PRODUCTION_REQUIRED.items():
            raw = str(os.environ.get(key) or "").strip()
            try:
                ok = bool(raw) and predicate(raw)
            except ValueError:
                ok = False
            if not ok:
                errors.append(f"{key} must be set to a positive integer in production")

        surface = str(os.environ.get("PARTNER_GATEWAY_SURFACE") or "").strip().lower()
        if surface in {"", "all"}:
            errors.append("PARTNER_GATEWAY_SURFACE must be public|ops|internal in production")

        if _truthy(os.environ.get("PARTNER_GATEWAY_ENABLE_JSONRPC")) and surface != "internal":
            errors.append("JSON-RPC must only be enabled on internal gateway surface")

    return errors


def _check_repo_templates() -> list[str]:
    errors: list[str] = []
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for snippet in COMPOSE_REQUIRED_SNIPPETS:
        if snippet not in compose:
            errors.append(f"docker-compose.yml missing {snippet!r}")

    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("HER_PROXY_INTRO_STORAGE=matchmaking", "HER_RELATION_LEDGER_READ_MODE=ledger_primary"):
        if key not in example:
            errors.append(f".env.example missing {key}")

    e2e = (REPO_ROOT / "frontend" / "her-app" / "scripts" / "run-her-e2e-ci.sh").read_text(encoding="utf-8")
    if "HER_PROXY_INTRO_STORAGE=matchmaking" not in e2e:
        errors.append("run-her-e2e-ci.sh must export HER_PROXY_INTRO_STORAGE=matchmaking")

    ci = (REPO_ROOT / ".github" / "workflows" / "tech-optimization-ci.yml").read_text(encoding="utf-8")
    if "HER_PROXY_INTRO_STORAGE=matchmaking" not in ci:
        errors.append("tech-optimization-ci.yml must set HER_PROXY_INTRO_STORAGE=matchmaking")

    return errors


def _check_frontend_a11y_artifacts() -> list[str]:
    errors: list[str] = []
    layout = (REPO_ROOT / "frontend" / "her-app" / "app" / "layout.tsx").read_text(encoding="utf-8")
    if 'id="main-content"' not in layout:
        errors.append("layout.tsx must expose #main-content landmark")
    if "skip-link" not in layout:
        errors.append("layout.tsx must include skip-link")

    error_state = REPO_ROOT / "frontend" / "her-app" / "components" / "her" / "ui" / "error-state.tsx"
    if not error_state.is_file():
        errors.append("missing components/her/ui/error-state.tsx")
    elif 'role="alert"' not in error_state.read_text(encoding="utf-8"):
        errors.append("error-state.tsx must use role=alert")

    connectivity = REPO_ROOT / "frontend" / "her-app" / "components" / "her" / "ui" / "app-connectivity.tsx"
    if connectivity.is_file():
        text = connectivity.read_text(encoding="utf-8")
        if "aria-live" not in text:
            errors.append("app-connectivity.tsx must announce offline state with aria-live")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--production",
        action="store_true",
        help="Also enforce production-only constraints on current environment",
    )
    parser.add_argument(
        "--skip-repo",
        action="store_true",
        help="Skip static repo template checks",
    )
    args = parser.parse_args()

    _load_dotenv()
    if args.production:
        os.environ.setdefault("HER_PRODUCTION_MODE", "1")

    errors = _check_process_env(production=args.production or _truthy(os.environ.get("HER_PRODUCTION_MODE")))
    if not args.skip_repo:
        errors.extend(_check_repo_templates())
        errors.extend(_check_frontend_a11y_artifacts())

    if errors:
        print("Tech optimization environment validation failed:")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("Tech optimization environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
