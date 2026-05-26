"""Production-mode guards for auth, ledger, and agent configuration."""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_production_mode() -> bool:
    raw = str(os.environ.get("HER_PRODUCTION_MODE") or "").strip().lower()
    return raw in _TRUTHY


def require_secret(name: str, *, label: str | None = None) -> str:
    """Return env value or raise if missing in production mode."""
    value = str(os.environ.get(name) or "").strip()
    if value:
        return value
    if is_production_mode():
        raise RuntimeError(
            f"Missing required secret {name}"
            + (f" ({label})" if label else "")
            + "; inject via your secret manager in production."
        )
    return ""


def production_forbids_auth_stubs() -> bool:
    return is_production_mode()


def assert_production_auth_providers(
    *,
    sms_provider_name: str,
    wechat_is_stub: bool,
    one_tap_is_stub: bool,
) -> None:
    if not production_forbids_auth_stubs():
        return
    sms = str(sms_provider_name or "").strip().lower()
    if sms in {"", "disabled", "mac_messages", "shell"}:
        raise RuntimeError(
            "HER_PRODUCTION_MODE=1 requires HER_SMS_PROVIDER=aliyun with valid Aliyun credentials."
        )
    if wechat_is_stub:
        raise RuntimeError(
            "HER_PRODUCTION_MODE=1 forbids HER_AUTH_WECHAT_PROVIDER=stub and stub JSON maps."
        )
    if one_tap_is_stub:
        raise RuntimeError(
            "HER_PRODUCTION_MODE=1 forbids HER_AUTH_ONE_TAP_PROVIDER=stub."
        )


def assert_production_ledger_config() -> None:
    if not is_production_mode():
        return
    from relationship_ledger.runtime import ledger_allow_legacy_fallback, ledger_read_mode  # noqa: PLC0415

    if ledger_read_mode() != "ledger_primary":
        raise RuntimeError("HER_PRODUCTION_MODE=1 requires HER_RELATION_LEDGER_READ_MODE=ledger_primary.")
    if ledger_allow_legacy_fallback():
        raise RuntimeError(
            "HER_PRODUCTION_MODE=1 forbids HER_ALLOW_LEGACY_TIMELINE_FALLBACK."
        )


def assert_production_discovery_agent_isolation() -> None:
    if not is_production_mode():
        return
    discovery_key = str(os.environ.get("HER_DISCOVERY_AGENT_API_KEY") or "").strip()
    discovery_base = str(os.environ.get("HER_DISCOVERY_AGENT_BASE_URL") or "").strip()
    if not discovery_key or not discovery_base:
        raise RuntimeError(
            "HER_PRODUCTION_MODE=1 requires HER_DISCOVERY_AGENT_API_KEY and "
            "HER_DISCOVERY_AGENT_BASE_URL (do not rely on chat agent env fallback)."
        )


__all__ = [
    "assert_production_auth_providers",
    "assert_production_discovery_agent_isolation",
    "assert_production_ledger_config",
    "is_production_mode",
    "production_forbids_auth_stubs",
    "require_secret",
]
