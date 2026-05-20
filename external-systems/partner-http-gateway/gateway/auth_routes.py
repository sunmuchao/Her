"""Public auth/SMS HTTP handlers for the gateway."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from chat_system import (  # type: ignore[import-untyped]
    AuthDomainError,
    bind_phone_with_sms,
    create_one_tap_attempt,
    get_current_auth_payload,
    issue_sms_code as persist_sms_code,
    login_with_wechat_profile,
    refresh_session as persist_refresh_session,
    revoke_session_by_access_token,
    verify_one_tap_login,
    verify_sms_code as persist_verify_sms_code,
)
from chat_system.storage import row_to_dict  # type: ignore[import-untyped]
from match_domain import get_trace_id

from .http_helpers import _json_safe, _parse_json_body, _read_body
from .request_policy import client_ip

_CN_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_CODE_RE = re.compile(r"^\d{6}$")
_CODE_TTL = timedelta(minutes=5)
_RESEND_COOLDOWN = timedelta(seconds=60)
_MAX_VERIFY_ATTEMPTS = 5
_DEFAULT_SMS_TEXT = "【遇见】验证码 {code}，5 分钟内有效。"


class AuthRouteError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.code = str(code)
        self.message = str(message)


class SmsProvider(Protocol):
    def send_code(self, phone: str, code: str) -> dict[str, Any]: ...


class WechatLoginProvider(Protocol):
    def exchange_code(self, code: str) -> dict[str, Any]: ...


class OneTapLoginProvider(Protocol):
    def create_attempt(self, *, device_id: str | None, client_type: str | None) -> dict[str, Any]: ...
    def verify(self, *, operator_token: str, attempt_context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class OtpRecord:
    phone: str
    code: str
    expires_at: datetime
    resend_at: datetime
    failed_attempts: int
    scenario: str
    next_path: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_cn_phone(raw: Any) -> str:
    phone = re.sub(r"\D+", "", str(raw or ""))
    if not _CN_PHONE_RE.fullmatch(phone):
        raise AuthRouteError(400, "invalid_phone", "请输入正确的中国大陆手机号")
    return phone


def _require_code(raw: Any) -> str:
    code = re.sub(r"\D+", "", str(raw or ""))
    if not _CODE_RE.fullmatch(code):
        raise AuthRouteError(400, "invalid_code", "请输入 6 位数字验证码")
    return code


def _mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


class DisabledSmsProvider:
    def send_code(self, phone: str, code: str) -> dict[str, Any]:
        raise AuthRouteError(
            503,
            "sms_provider_unavailable",
            "短信通道未配置，请接入正式短信供应商后再发送验证码",
        )


class DisabledWechatLoginProvider:
    def exchange_code(self, code: str) -> dict[str, Any]:
        del code
        raise AuthRouteError(503, "wechat_login_unavailable", "微信登录未配置，请接入正式微信开放平台后再使用")


class StubWechatLoginProvider:
    def __init__(self, code_map: dict[str, dict[str, Any]]) -> None:
        self._code_map = code_map

    def exchange_code(self, code: str) -> dict[str, Any]:
        payload = self._code_map.get(code)
        if payload is None:
            raise AuthRouteError(400, "wechat_code_invalid", "微信授权 code 无效或已过期")
        out = dict(payload)
        out.setdefault("openid", f"wx-openid-{code}")
        out.setdefault("unionid", out.get("openid"))
        out.setdefault("nickname", "微信用户")
        out.setdefault("avatar_url", "")
        return out


class WechatOpenPlatformProvider:
    _ACCESS_TOKEN_ENDPOINT = "https://api.weixin.qq.com/sns/oauth2/access_token"
    _USERINFO_ENDPOINT = "https://api.weixin.qq.com/sns/userinfo"

    def __init__(self, *, app_id: str, app_secret: str) -> None:
        self._app_id = str(app_id or "").strip()
        self._app_secret = str(app_secret or "").strip()
        if not self._app_id or not self._app_secret:
            raise ValueError("WeChat app id and app secret are required")

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib_request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise AuthRouteError(504, "wechat_timeout", "微信登录服务响应超时，请稍后重试") from exc
        if str(payload.get("errcode") or "").strip() not in {"", "0"}:
            message = str(payload.get("errmsg") or "wechat error").strip()
            raise AuthRouteError(502, "wechat_provider_error", f"微信登录失败：{message}"[:300])
        return payload

    def exchange_code(self, code: str) -> dict[str, Any]:
        qs = urllib_parse.urlencode(
            {
                "appid": self._app_id,
                "secret": self._app_secret,
                "code": code,
                "grant_type": "authorization_code",
            }
        )
        access_payload = self._get_json(f"{self._ACCESS_TOKEN_ENDPOINT}?{qs}")
        access_token = str(access_payload.get("access_token") or "").strip()
        openid = str(access_payload.get("openid") or "").strip()
        unionid = str(access_payload.get("unionid") or "").strip() or None
        if not access_token or not openid:
            raise AuthRouteError(502, "wechat_provider_error", "微信登录返回数据不完整")
        user_qs = urllib_parse.urlencode(
            {"access_token": access_token, "openid": openid, "lang": "zh_CN"}
        )
        profile_payload = self._get_json(f"{self._USERINFO_ENDPOINT}?{user_qs}")
        return {
            "openid": openid,
            "unionid": unionid or str(profile_payload.get("unionid") or "").strip() or None,
            "nickname": profile_payload.get("nickname"),
            "avatar_url": profile_payload.get("headimgurl"),
            "raw_profile": profile_payload,
        }


class DisabledOneTapLoginProvider:
    def create_attempt(self, *, device_id: str | None, client_type: str | None) -> dict[str, Any]:
        del device_id, client_type
        raise AuthRouteError(503, "one_tap_unavailable", "一键登录未配置，请接入正式运营商认证服务后再使用")

    def verify(self, *, operator_token: str, attempt_context: dict[str, Any]) -> dict[str, Any]:
        del operator_token, attempt_context
        raise AuthRouteError(503, "one_tap_unavailable", "一键登录未配置，请接入正式运营商认证服务后再使用")


class StubOneTapLoginProvider:
    def __init__(self, *, phone: str, operator_token: str) -> None:
        self._phone = phone
        self._operator_token = operator_token

    def create_attempt(self, *, device_id: str | None, client_type: str | None) -> dict[str, Any]:
        del device_id, client_type
        return {
            "provider": "stub_carrier",
            "masked_phone": _mask_phone(self._phone),
            "operator_request_id": f"stub-{secrets.token_hex(8)}",
            "provider_payload": {
                "mode": "stub",
                "hint": "use configured operator token",
            },
        }

    def verify(self, *, operator_token: str, attempt_context: dict[str, Any]) -> dict[str, Any]:
        del attempt_context
        if operator_token != self._operator_token:
            raise AuthRouteError(400, "one_tap_token_invalid", "一键登录凭证无效或已过期")
        return {
            "provider": "stub_carrier",
            "phone": self._phone,
            "masked_phone": _mask_phone(self._phone),
        }


def _first_env(*names: str) -> str:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _fixed_auth_code() -> str | None:
    raw = str(os.environ.get("HER_AUTH_FIXED_CODE") or "").strip()
    return raw if _CODE_RE.fullmatch(raw) else None


class AliyunSmsProvider:
    _DEFAULT_ENDPOINT = "https://dysmsapi.aliyuncs.com/"
    _DEFAULT_REGION_ID = "cn-hangzhou"
    _DEFAULT_TEMPLATE_PARAM_KEY = "code"

    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        sign_name: str,
        template_code: str,
        region_id: str = _DEFAULT_REGION_ID,
        endpoint: str = _DEFAULT_ENDPOINT,
        template_param_key: str = _DEFAULT_TEMPLATE_PARAM_KEY,
    ) -> None:
        self._access_key_id = str(access_key_id or "").strip()
        self._access_key_secret = str(access_key_secret or "").strip()
        self._sign_name = str(sign_name or "").strip()
        self._template_code = str(template_code or "").strip()
        self._region_id = str(region_id or self._DEFAULT_REGION_ID).strip()
        self._endpoint = str(endpoint or self._DEFAULT_ENDPOINT).strip().rstrip("/") + "/"
        self._template_param_key = str(template_param_key or self._DEFAULT_TEMPLATE_PARAM_KEY).strip()
        if not self._access_key_id:
            raise ValueError("Aliyun SMS access key id is required")
        if not self._access_key_secret:
            raise ValueError("Aliyun SMS access key secret is required")
        if not self._sign_name:
            raise ValueError("Aliyun SMS sign name is required")
        if not self._template_code:
            raise ValueError("Aliyun SMS template code is required")
        if not self._template_param_key:
            raise ValueError("Aliyun SMS template param key is required")

    @classmethod
    def is_configured_from_env(cls) -> bool:
        return bool(
            _first_env("HER_SMS_ALIYUN_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_ID")
            and _first_env(
                "HER_SMS_ALIYUN_ACCESS_KEY_SECRET",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                "ALICLOUD_ACCESS_KEY_SECRET",
            )
            and _first_env("HER_SMS_ALIYUN_SIGN_NAME", "HER_SMS_SIGN_NAME")
            and _first_env("HER_SMS_ALIYUN_TEMPLATE_CODE", "HER_SMS_TEMPLATE_CODE")
        )

    @classmethod
    def from_env(cls) -> AliyunSmsProvider:
        return cls(
            access_key_id=_first_env("HER_SMS_ALIYUN_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_ID"),
            access_key_secret=_first_env(
                "HER_SMS_ALIYUN_ACCESS_KEY_SECRET",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                "ALICLOUD_ACCESS_KEY_SECRET",
            ),
            sign_name=_first_env("HER_SMS_ALIYUN_SIGN_NAME", "HER_SMS_SIGN_NAME"),
            template_code=_first_env("HER_SMS_ALIYUN_TEMPLATE_CODE", "HER_SMS_TEMPLATE_CODE"),
            region_id=_first_env("HER_SMS_ALIYUN_REGION_ID") or cls._DEFAULT_REGION_ID,
            endpoint=_first_env("HER_SMS_ALIYUN_ENDPOINT") or cls._DEFAULT_ENDPOINT,
            template_param_key=_first_env("HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY") or cls._DEFAULT_TEMPLATE_PARAM_KEY,
        )

    def _percent_encode(self, value: Any) -> str:
        return urllib_parse.quote(str(value), safe="~-_.")

    def _canonical_query(self, params: dict[str, Any]) -> str:
        items = sorted((str(key), str(value)) for key, value in params.items())
        return "&".join(
            f"{self._percent_encode(key)}={self._percent_encode(value)}"
            for key, value in items
        )

    def _signature_for(self, params: dict[str, Any]) -> str:
        canonical = self._canonical_query(params)
        string_to_sign = f"GET&%2F&{self._percent_encode(canonical)}"
        digest = hmac.new(
            f"{self._access_key_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _provider_error(self, message: str, *, status_code: int = 502, code: str = "sms_provider_error") -> AuthRouteError:
        return AuthRouteError(status_code, code, f"阿里云短信发送失败：{message}"[:300])

    def send_code(self, phone: str, code: str) -> dict[str, Any]:
        params = {
            "AccessKeyId": self._access_key_id,
            "Action": "SendSms",
            "Format": "JSON",
            "PhoneNumbers": phone,
            "RegionId": self._region_id,
            "SignName": self._sign_name,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": secrets.token_hex(16),
            "SignatureVersion": "1.0",
            "TemplateCode": self._template_code,
            "TemplateParam": json.dumps(
                {self._template_param_key: code},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "Timestamp": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2017-05-25",
        }
        signed_params = dict(params)
        signed_params["Signature"] = self._signature_for(params)
        request_url = f"{self._endpoint}?{self._canonical_query(signed_params)}"
        request = urllib_request.Request(request_url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {}
            message = str(payload.get("Message") or payload.get("Code") or body or f"HTTP {exc.code}").strip()
            raise self._provider_error(message) from exc
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise AuthRouteError(504, "sms_timeout", "阿里云短信通道响应超时，请稍后重试") from exc

        response_code = str(payload.get("Code") or "").strip()
        if response_code != "OK":
            message = str(payload.get("Message") or response_code or "unknown_error").strip()
            if response_code == "isv.BUSINESS_LIMIT_CONTROL":
                raise AuthRouteError(429, "sms_cooldown", "短信发送过于频繁，请稍后再试")
            raise self._provider_error(message)
        return {
            "provider": "aliyun",
            "request_id": str(payload.get("RequestId") or "").strip(),
            "biz_id": str(payload.get("BizId") or "").strip(),
        }


class ShellCommandSmsProvider:
    def __init__(self, command: str) -> None:
        self._command = str(command or "").strip()
        if not self._command:
            raise ValueError("HER_SMS_SHELL_COMMAND is required for shell SMS provider")

    def send_code(self, phone: str, code: str) -> dict[str, Any]:
        env = os.environ.copy()
        env["HER_SMS_PHONE"] = phone
        env["HER_SMS_CODE"] = code
        env["HER_SMS_BODY"] = _DEFAULT_SMS_TEXT.format(code=code)
        try:
            completed = subprocess.run(
                self._command,
                shell=True,
                check=True,
                text=True,
                capture_output=True,
                env=env,
                timeout=20,
            )
        except subprocess.TimeoutExpired as exc:
            raise AuthRouteError(504, "sms_timeout", "短信通道响应超时，请稍后重试") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            message = stderr or "短信通道执行失败"
            raise AuthRouteError(502, "sms_provider_error", message[:300]) from exc
        return {"provider": "shell", "output": (completed.stdout or "").strip()[:300]}


class MacMessagesSmsProvider:
    _SCRIPT = """
on run argv
  set targetPhone to item 1 of argv
  set targetBody to item 2 of argv
  tell application "Messages"
    set targetService to missing value
    try
      set targetService to 1st service whose service type = SMS
    end try
    if targetService is missing value then
      try
        set targetService to 1st service whose service type = iMessage
      end try
    end if
    if targetService is missing value then error "No Messages service available"
    set targetBuddy to buddy targetPhone of targetService
    send targetBody to targetBuddy
  end tell
end run
""".strip()

    def __init__(self) -> None:
        if shutil.which("osascript") is None:
            raise ValueError("osascript is not available")

    def send_code(self, phone: str, code: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["osascript", "-e", self._SCRIPT, phone, _DEFAULT_SMS_TEXT.format(code=code)],
                check=True,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired as exc:
            raise AuthRouteError(
                504,
                "sms_timeout",
                "Messages 发送超时，请先打开 Messages 完成登录，并检查短信转发和自动化权限",
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            if "-1712" in stderr:
                message = "Messages 响应超时，请先打开 Messages 完成登录，并检查短信转发和自动化权限"
            elif "-1743" in stderr:
                message = "Messages 自动化权限未开启，请在系统设置里允许 Python 或终端控制 Messages"
            elif "-2700" in stderr or "No Messages service available" in stderr:
                message = "Messages 没有可用短信服务，请先登录 iMessage 并开启 iPhone 短信转发，或改用阿里云短信"
            else:
                message = stderr or "Messages 无法发送验证码，请检查短信转发和自动化权限"
            raise AuthRouteError(502, "sms_provider_error", message[:300]) from exc
        return {"provider": "mac_messages", "output": (completed.stdout or "").strip()[:300]}


def _build_sms_provider() -> SmsProvider:
    configured = str(os.environ.get("HER_SMS_PROVIDER") or "").strip().lower()
    if configured == "aliyun":
        return AliyunSmsProvider.from_env()
    if configured == "shell":
        return ShellCommandSmsProvider(os.environ.get("HER_SMS_SHELL_COMMAND") or "")
    if configured == "mac_messages":
        return MacMessagesSmsProvider()
    if configured in {"disabled", "none", "off"}:
        return DisabledSmsProvider()
    if not configured and AliyunSmsProvider.is_configured_from_env():
        return AliyunSmsProvider.from_env()
    if not configured and os.uname().sysname.lower() == "darwin":
        try:
            return MacMessagesSmsProvider()
        except ValueError:
            return DisabledSmsProvider()
    return DisabledSmsProvider()


def _build_wechat_login_provider() -> WechatLoginProvider:
    configured = str(os.environ.get("HER_AUTH_WECHAT_PROVIDER") or "").strip().lower()
    stub_json = str(os.environ.get("HER_AUTH_WECHAT_STUB_CODES_JSON") or "").strip()
    if configured == "stub" or stub_json:
        try:
            parsed = json.loads(stub_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("HER_AUTH_WECHAT_STUB_CODES_JSON must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("HER_AUTH_WECHAT_STUB_CODES_JSON must be a JSON object")
        code_map = {
            str(code): value
            for code, value in parsed.items()
            if isinstance(value, dict)
        }
        return StubWechatLoginProvider(code_map)
    if configured in {"open_platform", "wechat"}:
        return WechatOpenPlatformProvider(
            app_id=_first_env("HER_WECHAT_APP_ID"),
            app_secret=_first_env("HER_WECHAT_APP_SECRET"),
        )
    if configured in {"disabled", "none", "off"}:
        return DisabledWechatLoginProvider()
    app_id = _first_env("HER_WECHAT_APP_ID")
    app_secret = _first_env("HER_WECHAT_APP_SECRET")
    if app_id and app_secret:
        return WechatOpenPlatformProvider(app_id=app_id, app_secret=app_secret)
    return DisabledWechatLoginProvider()


def _build_one_tap_login_provider() -> OneTapLoginProvider:
    configured = str(os.environ.get("HER_AUTH_ONE_TAP_PROVIDER") or "").strip().lower()
    stub_phone = str(os.environ.get("HER_AUTH_ONE_TAP_STUB_PHONE") or "").strip()
    stub_token = str(os.environ.get("HER_AUTH_ONE_TAP_STUB_TOKEN") or "").strip()
    if configured == "stub" or (stub_phone and stub_token):
        return StubOneTapLoginProvider(phone=_require_cn_phone(stub_phone), operator_token=stub_token)
    if configured in {"disabled", "none", "off", ""}:
        return DisabledOneTapLoginProvider()
    return DisabledOneTapLoginProvider()


class AuthOtpService:
    def __init__(
        self,
        provider: SmsProvider | None = None,
        *,
        chat_executor: Any | None = None,
    ) -> None:
        self._provider = provider or _build_sms_provider()
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
        now = _utcnow()
        code = _fixed_auth_code() or f"{secrets.randbelow(1000000):06d}"
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
                "masked_phone": _mask_phone(phone),
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

        now = _utcnow()
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
            _require_cn_phone(body.get("phone") or body.get("mobile")),
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
            _require_cn_phone(body.get("phone") or body.get("mobile")),
            _require_code(body.get("code") or body.get("otp")),
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
            phone=_require_cn_phone(verified.get("phone")),
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
    return 200, _json_safe({**out, "trace_id": get_trace_id()})


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
            phone=_require_cn_phone(body.get("phone") or body.get("mobile")),
            code=_require_code(body.get("code") or body.get("otp")),
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
    if path == "/v1/auth/logout" and method == "POST":
        return rest_auth_logout(gateway, environ)
    if path == "/v1/auth/wechat/bind-phone" and method == "POST":
        return rest_auth_wechat_bind_phone(gateway, environ, _parse_json_body(_read_body(environ)))
    return None
