"""Auth SMS / WeChat / one-tap provider implementations."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from .auth_common import (
    AuthRouteError,
    OneTapLoginProvider,
    SmsProvider,
    WechatLoginProvider,
    _CODE_RE,
    _DEFAULT_SMS_TEXT,
    mask_phone,
    require_cn_phone,
    utcnow,
)


def first_env(*names: str) -> str:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def fixed_auth_code() -> str | None:
    raw = str(os.environ.get("HER_AUTH_FIXED_CODE") or "").strip()
    return raw if _CODE_RE.fullmatch(raw) else None

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
            "masked_phone": mask_phone(self._phone),
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
            "masked_phone": mask_phone(self._phone),
        }


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
            first_env("HER_SMS_ALIYUN_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_ID")
            and first_env(
                "HER_SMS_ALIYUN_ACCESS_KEY_SECRET",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                "ALICLOUD_ACCESS_KEY_SECRET",
            )
            and first_env("HER_SMS_ALIYUN_SIGN_NAME", "HER_SMS_SIGN_NAME")
            and first_env("HER_SMS_ALIYUN_TEMPLATE_CODE", "HER_SMS_TEMPLATE_CODE")
        )

    @classmethod
    def from_env(cls) -> AliyunSmsProvider:
        return cls(
            access_key_id=first_env("HER_SMS_ALIYUN_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_ID"),
            access_key_secret=first_env(
                "HER_SMS_ALIYUN_ACCESS_KEY_SECRET",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                "ALICLOUD_ACCESS_KEY_SECRET",
            ),
            sign_name=first_env("HER_SMS_ALIYUN_SIGN_NAME", "HER_SMS_SIGN_NAME"),
            template_code=first_env("HER_SMS_ALIYUN_TEMPLATE_CODE", "HER_SMS_TEMPLATE_CODE"),
            region_id=first_env("HER_SMS_ALIYUN_REGION_ID") or cls._DEFAULT_REGION_ID,
            endpoint=first_env("HER_SMS_ALIYUN_ENDPOINT") or cls._DEFAULT_ENDPOINT,
            template_param_key=first_env("HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY") or cls._DEFAULT_TEMPLATE_PARAM_KEY,
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
            "Timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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


def build_sms_provider() -> SmsProvider:
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


def build_wechat_login_provider() -> WechatLoginProvider:
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
            app_id=first_env("HER_WECHAT_APP_ID"),
            app_secret=first_env("HER_WECHAT_APP_SECRET"),
        )
    if configured in {"disabled", "none", "off"}:
        return DisabledWechatLoginProvider()
    app_id = first_env("HER_WECHAT_APP_ID")
    app_secret = first_env("HER_WECHAT_APP_SECRET")
    if app_id and app_secret:
        return WechatOpenPlatformProvider(app_id=app_id, app_secret=app_secret)
    return DisabledWechatLoginProvider()


def build_one_tap_login_provider() -> OneTapLoginProvider:
    configured = str(os.environ.get("HER_AUTH_ONE_TAP_PROVIDER") or "").strip().lower()
    stub_phone = str(os.environ.get("HER_AUTH_ONE_TAP_STUB_PHONE") or "").strip()
    stub_token = str(os.environ.get("HER_AUTH_ONE_TAP_STUB_TOKEN") or "").strip()
    if configured == "stub" or (stub_phone and stub_token):
        return StubOneTapLoginProvider(phone=require_cn_phone(stub_phone), operator_token=stub_token)
    if configured in {"disabled", "none", "off", ""}:
        return DisabledOneTapLoginProvider()
    return DisabledOneTapLoginProvider()



__all__ = [
    "urllib_request",
    "AliyunSmsProvider",
    "DisabledOneTapLoginProvider",
    "DisabledSmsProvider",
    "DisabledWechatLoginProvider",
    "MacMessagesSmsProvider",
    "ShellCommandSmsProvider",
    "StubOneTapLoginProvider",
    "StubWechatLoginProvider",
    "WechatOpenPlatformProvider",
    "build_one_tap_login_provider",
    "build_sms_provider",
    "build_wechat_login_provider",
]
