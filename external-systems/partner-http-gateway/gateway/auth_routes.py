"""Public auth/SMS HTTP handlers for the gateway."""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime
from typing import Any, Protocol
from chat_system import (  # type: ignore[import-untyped]
    AuthDomainError,
    bind_phone_with_sms,
    create_one_tap_attempt,
    get_current_auth_payload,
    get_onboarding_profile,
    issue_sms_code as persist_sms_code,
    login_with_wechat_profile,
    refresh_session as persist_refresh_session,
    revoke_session_by_access_token,
    submit_onboarding_profile,
    verify_one_tap_login,
    verify_sms_code as persist_verify_sms_code,
)
from chat_system.storage import row_to_dict  # type: ignore[import-untyped]
from match_domain import get_trace_id
from match_domain.principal import principal_identity_table, sync_user_block_from_principal

from .auth_common import (
    AuthRouteError,
    OtpRecord,
    SmsProvider,
    WechatLoginProvider,
    OneTapLoginProvider,
    _CODE_TTL,
    _MAX_VERIFY_ATTEMPTS,
    _RESEND_COOLDOWN,
    mask_phone,
    require_cn_phone,
    require_code,
    utcnow,
)
from . import auth_providers as _auth_providers
from .auth_providers import (
    build_one_tap_login_provider,
    build_sms_provider,
    build_wechat_login_provider,
    fixed_auth_code,
)
from .http_helpers import _json_safe, _parse_json_body, _read_body
from .request_policy import client_ip
from .resolved_principal import principal_payload_for_actor

# Backward-compatible re-exports for gateway tests and app wiring.
AliyunSmsProvider = _auth_providers.AliyunSmsProvider
DisabledOneTapLoginProvider = _auth_providers.DisabledOneTapLoginProvider
DisabledSmsProvider = _auth_providers.DisabledSmsProvider
DisabledWechatLoginProvider = _auth_providers.DisabledWechatLoginProvider
MacMessagesSmsProvider = _auth_providers.MacMessagesSmsProvider
ShellCommandSmsProvider = _auth_providers.ShellCommandSmsProvider
StubOneTapLoginProvider = _auth_providers.StubOneTapLoginProvider
StubWechatLoginProvider = _auth_providers.StubWechatLoginProvider
WechatOpenPlatformProvider = _auth_providers.WechatOpenPlatformProvider
urllib_request = _auth_providers.urllib_request

# Backward-compatible private aliases for gateway app imports.
_build_sms_provider = build_sms_provider
_build_wechat_login_provider = build_wechat_login_provider
_build_one_tap_login_provider = build_one_tap_login_provider

class AuthOtpService:
    def __init__(
        self,
        provider: SmsProvider | None = None,
        *,
        chat_executor: Any | None = None,
    ) -> None:
        self._provider = provider or build_sms_provider()
        self._chat_executor = chat_executor
        self._records: dict[str, OtpRecord] = {}
        self._users: dict[str, str] = {}
        self._lock = threading.Lock()

    def _prune(self, now: datetime) -> None:
        expired = [phone for phone, record in self._records.items() if record.expires_at <= now]
        for phone in expired:
            self._records.pop(phone, None)

    def send_code(
        self,
        phone: str,
        *,
        scene: str = "login",
        client_ip_text: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        now = utcnow()
        code = fixed_auth_code() or f"{secrets.randbelow(1000000):06d}"
        provider_meta = self._provider.send_code(phone, code)
        if self._chat_executor is not None:
            try:
                return self._chat_executor(
                    persist_sms_code,
                    phone=phone,
                    code=code,
                    scene=scene,
                    provider_name=str(provider_meta.get("provider") or "unknown"),
                    client_ip=client_ip_text,
                    device_id=device_id,
                )
            except AuthDomainError as exc:
                raise AuthRouteError(exc.status_code, exc.code, exc.message) from exc

        scenario = "existing" if phone in self._users else "new"
        next_path = "" if scenario == "existing" else "/onboarding"
        with self._lock:
            self._prune(now)
            existing = self._records.get(phone)
            if existing is not None and now < existing.resend_at:
                seconds = max(1, int((existing.resend_at - now).total_seconds()))
                raise AuthRouteError(429, "sms_cooldown", f"发送过于频繁，请在 {seconds} 秒后重试")
        record = OtpRecord(
            phone=phone,
            code=code,
            expires_at=now + _CODE_TTL,
            resend_at=now + _RESEND_COOLDOWN,
            failed_attempts=0,
            scenario=scenario,
            next_path=next_path,
        )
        with self._lock:
            self._records[phone] = record
        return {
            "challenge_id": f"otp-mem-{phone[-4:]}",
            "delivery": {
                "channel": "sms",
                "masked_phone": mask_phone(phone),
                "expires_in_seconds": int(_CODE_TTL.total_seconds()),
                "resend_in_seconds": int(_RESEND_COOLDOWN.total_seconds()),
                "provider": provider_meta.get("provider") or "unknown",
            },
            "flow": {"scenario": scenario, "next_path": next_path},
        }

    def verify_code(
        self,
        phone: str,
        code: str,
        *,
        challenge_id: str | None = None,
        client_ip_text: str | None = None,
        device_id: str | None = None,
        client_type: str | None = None,
    ) -> dict[str, Any]:
        if self._chat_executor is not None:
            try:
                return self._chat_executor(
                    persist_verify_sms_code,
                    phone=phone,
                    code=code,
                    challenge_id=challenge_id,
                    client_ip=client_ip_text,
                    device_id=device_id,
                    client_type=client_type,
                )
            except AuthDomainError as exc:
                raise AuthRouteError(exc.status_code, exc.code, exc.message) from exc

        now = utcnow()
        with self._lock:
            self._prune(now)
            record = self._records.get(phone)
            if record is None:
                raise AuthRouteError(400, "code_not_requested", "请先获取验证码")
            if record.expires_at <= now:
                self._records.pop(phone, None)
                raise AuthRouteError(400, "code_expired", "验证码已过期，请重新获取")
            if record.failed_attempts >= _MAX_VERIFY_ATTEMPTS:
                self._records.pop(phone, None)
                raise AuthRouteError(429, "code_locked", "输入错误次数过多，请重新获取验证码")
            if record.code != code:
                record.failed_attempts += 1
                self._records[phone] = record
                remaining = max(0, _MAX_VERIFY_ATTEMPTS - record.failed_attempts)
                raise AuthRouteError(
                    400,
                    "code_mismatch",
                    "验证码错误，请重新输入" if remaining else "输入错误次数过多，请重新获取验证码",
                )
            self._records.pop(phone, None)
            is_new_user = phone not in self._users
            user_id = self._users.get(phone) or f"usr-mem-{phone[-6:]}"
            self._users[phone] = user_id
            return {
                "verified": True,
                "user": {
                    "user_id": user_id,
                    "is_new_user": is_new_user,
                    "account_status": "active",
                    "onboarding_status": "not_started" if is_new_user else "completed",
                },
                "session": {
                    "session_id": f"sess-mem-{phone[-6:]}",
                    "access_token": f"atk_mem_{phone[-6:]}",
                    "refresh_token": f"rtk_mem_{phone[-6:]}",
                    "token_type": "Bearer",
                    "expires_in_seconds": 7200,
                    "refresh_expires_in_seconds": 2592000,
                },
                "flow": {"scenario": record.scenario, "next_path": record.next_path},
            }


class AuthGateway(Protocol):
    _auth_otp: AuthOtpService
    _wechat_login_provider: WechatLoginProvider
    _one_tap_login_provider: OneTapLoginProvider
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...
    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...
    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...


def _error_payload(exc: AuthRouteError) -> tuple[int, dict[str, Any]]:
    return exc.status_code, {
        "error": {"code": exc.code, "message": exc.message},
        "trace_id": get_trace_id(),
    }


def rest_auth_send_sms_code(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        out = gateway._auth_otp.send_code(
            require_cn_phone(body.get("phone") or body.get("mobile")),
            scene=str(body.get("scene") or "login"),
            client_ip_text=client_ip(environ),
            device_id=str(body.get("device_id") or "").strip() or None,
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    return 201, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_verify_sms_code(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        out = gateway._auth_otp.verify_code(
            require_cn_phone(body.get("phone") or body.get("mobile")),
            require_code(body.get("code") or body.get("otp")),
            challenge_id=str(body.get("challenge_id") or "").strip() or None,
            client_ip_text=client_ip(environ),
            device_id=str(body.get("device_id") or "").strip() or None,
            client_type=str(body.get("client_type") or "").strip() or None,
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_refresh_token(
    gateway: AuthGateway,
    _environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    refresh_token = str(body.get("refresh_token") or "").strip()
    if not refresh_token:
        return _error_payload(AuthRouteError(400, "refresh_token_required", "refresh_token is required"))
    try:
        out = gateway._with_chat(persist_refresh_session, refresh_token)
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_wechat_login(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    code = str(body.get("code") or "").strip()
    if not code:
        return _error_payload(AuthRouteError(400, "wechat_code_required", "微信授权 code 不能为空"))
    try:
        profile = gateway._wechat_login_provider.exchange_code(code)
        out = gateway._with_chat(
            login_with_wechat_profile,
            openid=str(profile.get("openid") or "").strip(),
            unionid=str(profile.get("unionid") or "").strip() or None,
            nickname=str(profile.get("nickname") or "").strip() or None,
            avatar_url=str(profile.get("avatar_url") or "").strip() or None,
            raw_profile=profile.get("raw_profile") if isinstance(profile.get("raw_profile"), dict) else profile,
            client_ip=client_ip(environ),
            device_id=str(body.get("device_id") or "").strip() or None,
            client_type=str(body.get("client_type") or "").strip() or None,
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_one_tap_create(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    device_id = str(body.get("device_id") or "").strip() or None
    client_type = str(body.get("client_type") or "").strip() or None
    try:
        created = gateway._one_tap_login_provider.create_attempt(
            device_id=device_id,
            client_type=client_type,
        )
        out = gateway._with_chat(
            create_one_tap_attempt,
            provider=str(created.get("provider") or "unknown"),
            masked_phone=str(created.get("masked_phone") or "").strip(),
            provider_payload=created.get("provider_payload") if isinstance(created.get("provider_payload"), dict) else {},
            operator_request_id=str(created.get("operator_request_id") or "").strip() or None,
            device_id=device_id,
            client_ip=client_ip(environ),
            client_type=client_type,
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 201, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_one_tap_verify(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    attempt_id = str(body.get("attempt_id") or "").strip()
    operator_token = str(body.get("operator_token") or "").strip()
    if not attempt_id:
        return _error_payload(AuthRouteError(400, "one_tap_attempt_required", "attempt_id is required"))
    if not operator_token:
        return _error_payload(AuthRouteError(400, "one_tap_token_required", "operator_token is required"))
    device_id = str(body.get("device_id") or "").strip() or None
    client_type = str(body.get("client_type") or "").strip() or None
    try:
        provider_result = gateway._with_chat(_load_one_tap_attempt_context, attempt_id)
        if not provider_result:
            raise AuthRouteError(404, "one_tap_attempt_not_found", "一键登录尝试不存在")
        verified = gateway._one_tap_login_provider.verify(
            operator_token=operator_token,
            attempt_context=provider_result,
        )
        out = gateway._with_chat(
            verify_one_tap_login,
            attempt_id=attempt_id,
            phone=require_cn_phone(verified.get("phone")),
            provider=str(verified.get("provider") or provider_result.get("provider") or "unknown"),
            operator_token=operator_token,
            client_ip=client_ip(environ),
            device_id=device_id,
            client_type=client_type,
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def _extract_bearer_token(environ: dict[str, Any]) -> str:
    auth = str(environ.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""


def _load_one_tap_attempt_context(conn: Any, attempt_id: str) -> dict[str, Any] | None:
    row = row_to_dict(
        conn.execute(
            """
            SELECT attempt_id, provider, masked_phone, provider_payload_json, client_type, device_id
            FROM auth_one_tap_attempts
            WHERE attempt_id = ?
            LIMIT 1
            """,
            (attempt_id,),
        ).fetchone()
    )
    if not row:
        return None
    payload = row.get("provider_payload_json")
    if isinstance(payload, str):
        try:
            row["provider_payload_json"] = json.loads(payload)
        except json.JSONDecodeError:
            row["provider_payload_json"] = {}
    return row


def rest_auth_get_onboarding(
    gateway: AuthGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    try:
        out = gateway._with_chat(get_onboarding_profile, str(actor.actor_id))
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_patch_onboarding(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    try:
        out = gateway._with_chat(
            submit_onboarding_profile,
            str(actor.actor_id),
            basic_info=body.get("basic_info"),
            preference=body.get("preference"),
            mark_completed=bool(body.get("mark_completed", True)),
        )
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_me(
    gateway: AuthGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    token = _extract_bearer_token(environ)
    try:
        out = gateway._with_chat(get_current_auth_payload, actor.actor_id, token)
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe(
        {
            **out,
            "user": sync_user_block_from_principal(out.get("user"), principal_payload_for_actor(gateway, environ)),
            "principal": principal_payload_for_actor(gateway, environ),
            "trace_id": get_trace_id(),
            "read_apis": {
                "profile_facts": "/v1/profile/me",
                "collected_statements": "/v1/persona/collected",
                "principal": "/v1/auth/principal",
            },
            "identity_vocabulary": principal_identity_table(),
        }
    )


def rest_auth_principal(
    gateway: AuthGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    principal = principal_payload_for_actor(gateway, environ)
    return 200, _json_safe(
        {
            "principal": principal,
            "identity_vocabulary": principal_identity_table(),
            "trace_id": get_trace_id(),
        }
    )


def rest_auth_logout(
    gateway: AuthGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    token = _extract_bearer_token(environ)
    if not token:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    out = gateway._with_chat(revoke_session_by_access_token, token)
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def rest_auth_wechat_bind_phone(
    gateway: AuthGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    actor = gateway._current_actor(environ)
    if actor is None:
        return _error_payload(AuthRouteError(401, "unauthorized", "登录状态已失效，请重新登录"))
    try:
        out = gateway._with_chat(
            bind_phone_with_sms,
            user_id=str(actor.actor_id),
            phone=require_cn_phone(body.get("phone") or body.get("mobile")),
            code=require_code(body.get("code") or body.get("otp")),
            challenge_id=str(body.get("challenge_id") or "").strip() or None,
            client_ip=client_ip(environ),
            device_id=str(body.get("device_id") or "").strip() or None,
        )
    except AuthDomainError as exc:
        return _error_payload(AuthRouteError(exc.status_code, exc.code, exc.message))
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


def dispatch_public_auth_rest(
    gateway: AuthGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/auth/sms/send-code" and method == "POST":
        return rest_auth_send_sms_code(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/sms/verify-code" and method == "POST":
        return rest_auth_verify_sms_code(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/wechat/login" and method == "POST":
        return rest_auth_wechat_login(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/one-tap/create" and method == "POST":
        return rest_auth_one_tap_create(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/one-tap/verify" and method == "POST":
        return rest_auth_one_tap_verify(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/token/refresh" and method == "POST":
        return rest_auth_refresh_token(gateway, environ, _parse_json_body(_read_body(environ)))
    return None


def dispatch_private_auth_rest(
    gateway: AuthGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/auth/me" and method == "GET":
        return rest_auth_me(gateway, environ)
    if path == "/v1/auth/principal" and method == "GET":
        return rest_auth_principal(gateway, environ)
    if path == "/v1/auth/onboarding" and method == "GET":
        return rest_auth_get_onboarding(gateway, environ)
    if path == "/v1/auth/onboarding" and method in {"PATCH", "POST"}:
        return rest_auth_patch_onboarding(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/auth/logout" and method == "POST":
        return rest_auth_logout(gateway, environ)
    if path == "/v1/auth/wechat/bind-phone" and method == "POST":
        return rest_auth_wechat_bind_phone(gateway, environ, _parse_json_body(_read_body(environ)))
    return None
