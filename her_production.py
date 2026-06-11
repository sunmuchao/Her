"""Production-mode guards for auth, ledger, and agent configuration."""

from __future__ import annotations

import os
from urllib.parse import urlparse

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


def assert_production_database_security() -> None:
    """
    生产环境数据库安全检查。

    检查项：
    1. 禁止使用 localhost/127.0.0.1 数据库地址
    2. 禁止 root 用户无密码连接
    3. 确保所有数据库配置已设置
    """
    if not is_production_mode():
        return

    # 检查数据库连接字符串
    db_envs = [
        "PARTNER_RECOMMENDATION_DB",
        "PARTNER_MATCHMAKING_DB",
        "PARTNER_CHAT_DB",
        "PARTNER_DISCOVERY_DB",
        "HER_RELATION_LEDGER_DB",
    ]

    for env_name in db_envs:
        dsn = os.environ.get(env_name, "")
        if not dsn:
            raise RuntimeError(f"HER_PRODUCTION_MODE=1 requires {env_name} to be set.")

        # 解析数据库连接字符串
        try:
            parsed = urlparse(dsn)

            # 检查是否使用本地地址
            hostname = parsed.hostname or ""
            if hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
                raise RuntimeError(
                    f"HER_PRODUCTION_MODE=1 forbids localhost database in {env_name}. "
                    f"Use production database server instead of '{hostname}'."
                )

            # 检查是否使用 root 用户无密码
            username = parsed.username or ""
            password = parsed.password or ""
            if username == "root" and not password:
                raise RuntimeError(
                    f"HER_PRODUCTION_MODE=1 forbids root without password in {env_name}. "
                    f"Use strong password for database authentication."
                )

            # 检查是否使用弱密码（长度过短）
            if password and len(password) < 12:
                raise RuntimeError(
                    f"HER_PRODUCTION_MODE=1 requires database password >= 12 chars in {env_name}. "
                    f"Current password length: {len(password)}."
                )
        except Exception as e:
            # 如果解析失败，仍然要求配置
            raise RuntimeError(
                f"HER_PRODUCTION_MODE=1 requires valid database DSN in {env_name}. "
                f"Parse error: {str(e)}"
            )


def assert_production_api_key_security() -> None:
    """
    生产环境API密钥安全检查。

    检查项：
    1. API密钥长度必须 >= 32 chars
    2. 禁止使用占位符（如 "replace-with", "test", "demo"）
    """
    if not is_production_mode():
        return

    # 检查API密钥配置
    api_keys = [
        ("OPENAI_API_KEY", "OpenAI API key"),
        ("HER_DISCOVERY_AGENT_API_KEY", "Discovery agent API key"),
        ("HER_VERIFICATION_CHALLENGE_SECRET", "Live verification HMAC secret"),
        ("MINIO_ACCESS_KEY", "MinIO access key"),
        ("MINIO_SECRET_KEY", "MinIO secret key"),
    ]

    for key_name, key_label in api_keys:
        key_value = os.environ.get(key_name, "")

        # MinIO密钥可选，但如果配置则必须强密码
        if key_name.startswith("MINIO_") and not key_value:
            continue

        # 其他密钥必须配置
        if not key_value:
            raise RuntimeError(
                f"HER_PRODUCTION_MODE=1 requires {key_name} ({key_label}) to be set."
            )

        # 检查密钥长度
        min_length = 32 if key_name == "OPENAI_API_KEY" else 20
        if key_name == "MINIO_SECRET_KEY":
            min_length = 40

        if len(key_value) < min_length:
            raise RuntimeError(
                f"HER_PRODUCTION_MODE=1 requires {key_name} ({key_label}) to be >= {min_length} chars. "
                f"Current length: {len(key_value)}."
            )

        # 检查是否使用占位符
        placeholders = ["replace-with", "test", "demo", "example", "placeholder", "your-", "change-"]
        for placeholder in placeholders:
            if placeholder in key_value.lower():
                raise RuntimeError(
                    f"HER_PRODUCTION_MODE=1 forbids placeholder values in {key_name} ({key_label}). "
                    f"Detected placeholder: '{placeholder}'. Use real production credentials."
                )


def assert_production_all() -> None:
    """
    执行所有生产环境安全检查。

    建议在应用启动时调用此函数，确保生产环境配置安全。
    """
    if not is_production_mode():
        return

    # 执行所有检查
    assert_production_database_security()
    assert_production_api_key_security()
    assert_production_ledger_config()
    assert_production_discovery_agent_isolation()


__all__ = [
    "assert_production_all",
    "assert_production_api_key_security",
    "assert_production_auth_providers",
    "assert_production_database_security",
    "assert_production_discovery_agent_isolation",
    "assert_production_ledger_config",
    "is_production_mode",
    "production_forbids_auth_stubs",
    "require_secret",
]
