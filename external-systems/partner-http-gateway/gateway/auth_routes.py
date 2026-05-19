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

from match_domain import get_trace_id

from .http_helpers import _parse_json_body, _read_body

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


def _scenario_from_phone(phone: str) -> str:
    last = int(phone[-1])
    return "existing" if last % 2 == 0 else "new"


def _next_path_for_scenario(scenario: str) -> str:
    del scenario
    return ""


class DisabledSmsProvider:
    def send_code(self, phone: str, code: str) -> dict[str, Any]:
        raise AuthRouteError(
            503,
            "sms_provider_unavailable",
            "短信通道未配置，请接入正式短信供应商后再发送验证码",
        )


def _first_env(*names: str) -> str:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


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


class AuthOtpService:
    def __init__(self, provider: SmsProvider | None = None) -> None:
        self._provider = provider or _build_sms_provider()
        self._records: dict[str, OtpRecord] = {}
        self._lock = threading.Lock()

    def _prune(self, now: datetime) -> None:
        expired = [phone for phone, record in self._records.items() if record.expires_at <= now]
        for phone in expired:
            self._records.pop(phone, None)

    def send_code(self, phone: str) -> dict[str, Any]:
        now = _utcnow()
        scenario = _scenario_from_phone(phone)
        next_path = _next_path_for_scenario(scenario)
        with self._lock:
            self._prune(now)
            existing = self._records.get(phone)
            if existing is not None and now < existing.resend_at:
                seconds = max(1, int((existing.resend_at - now).total_seconds()))
                raise AuthRouteError(429, "sms_cooldown", f"发送过于频繁，请在 {seconds} 秒后重试")

        code = f"{secrets.randbelow(1000000):06d}"
        provider_meta = self._provider.send_code(phone, code)
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
            "delivery": {
                "channel": "sms",
                "masked_phone": _mask_phone(phone),
                "expires_in_seconds": int(_CODE_TTL.total_seconds()),
                "resend_in_seconds": int(_RESEND_COOLDOWN.total_seconds()),
                "provider": provider_meta.get("provider") or "unknown",
            },
            "flow": {"scenario": scenario, "next_path": next_path},
        }

    def verify_code(self, phone: str, code: str) -> dict[str, Any]:
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
            return {
                "verified": True,
                "flow": {"scenario": record.scenario, "next_path": record.next_path},
            }


class AuthGateway(Protocol):
    _auth_otp: AuthOtpService


def _error_payload(exc: AuthRouteError) -> tuple[int, dict[str, Any]]:
    return exc.status_code, {
        "error": {"code": exc.code, "message": exc.message},
        "trace_id": get_trace_id(),
    }


def rest_auth_send_sms_code(
    gateway: AuthGateway,
    _environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        out = gateway._auth_otp.send_code(_require_cn_phone(body.get("phone") or body.get("mobile")))
    except AuthRouteError as exc:
        return _error_payload(exc)
    return 201, {**out, "trace_id": get_trace_id()}


def rest_auth_verify_sms_code(
    gateway: AuthGateway,
    _environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        out = gateway._auth_otp.verify_code(
            _require_cn_phone(body.get("phone") or body.get("mobile")),
            _require_code(body.get("code") or body.get("otp")),
        )
    except AuthRouteError as exc:
        return _error_payload(exc)
    return 200, {**out, "trace_id": get_trace_id()}


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
    return None
