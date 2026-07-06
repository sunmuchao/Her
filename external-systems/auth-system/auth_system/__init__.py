"""Auth system package (re-export from chat_system for compatibility)."""
# 🔧 Migration Phase 1: auth_system 作为命名空间，底层仍使用 chat_system
# Phase 2（未来）：将 auth 函数完全迁移到 auth_system

from __future__ import annotations

# 直接从 chat_system 导入所有 auth 函数（保持 API 兼容）
# 注意：这里不需要 auth_system.auth_accounts 模块，直接导入 chat_system
try:
    from chat_system import *  # type: ignore[import-untyped,misc]
    from chat_system.auth_accounts import __all__ as _auth_all  # type: ignore[import-untyped,misc]
except ImportError:
    # Fallback: 直接导入关键函数
    from chat_system.auth_accounts import (  # type: ignore[import-untyped]
        get_auth_session_roles,
        get_session_by_access_token,
        get_onboarding_profile,
        login_with_wechat_profile,
        submit_onboarding_profile,
        get_current_auth_payload,
        issue_sms_code,
        verify_sms_code,
        bind_phone_with_sms,
        create_one_tap_attempt,
        verify_one_tap_login,
        refresh_session,
        revoke_session_by_access_token,
        find_user_id_by_profile_id,
        find_profile_id_by_user_id,
        upsert_phone_role_binding,
        classify_phone_scenario,
        AuthDomainError,
    )
    _auth_all = [
        "get_auth_session_roles",
        "get_session_by_access_token",
        "get_onboarding_profile",
        "login_with_wechat_profile",
        "submit_onboarding_profile",
        "get_current_auth_payload",
        "issue_sms_code",
        "verify_sms_code",
        "bind_phone_with_sms",
        "create_one_tap_attempt",
        "verify_one_tap_login",
        "refresh_session",
        "revoke_session_by_access_token",
        "find_user_id_by_profile_id",
        "find_profile_id_by_user_id",
        "upsert_phone_role_binding",
        "classify_phone_scenario",
        "AuthDomainError",
    ]

# 导出数据库连接工具（auth_system 自己的）
from .storage import (
    DEFAULT_AUTH_MYSQL_DSN,
    connect_db,
    initialize_database,
    reset_all_tables,
)

# 合并导出列表
__all__ = list(_auth_all) + [
    "DEFAULT_AUTH_MYSQL_DSN",
    "connect_db",
    "initialize_database",
    "reset_all_tables",
]
