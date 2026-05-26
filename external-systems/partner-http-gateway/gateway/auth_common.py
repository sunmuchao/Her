"""Shared auth route constants and helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


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


_CN_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_CODE_RE = re.compile(r"^\d{6}$")
_CODE_TTL = timedelta(minutes=5)
_RESEND_COOLDOWN = timedelta(seconds=60)
_MAX_VERIFY_ATTEMPTS = 5
_DEFAULT_SMS_TEXT = "【遇见】验证码 {code}，5 分钟内有效。"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_cn_phone(raw: Any) -> str:
    phone = re.sub(r"\D+", "", str(raw or ""))
    if not _CN_PHONE_RE.fullmatch(phone):
        raise AuthRouteError(400, "invalid_phone", "请输入正确的中国大陆手机号")
    return phone


def require_code(raw: Any) -> str:
    code = re.sub(r"\D+", "", str(raw or ""))
    if not _CODE_RE.fullmatch(code):
        raise AuthRouteError(400, "invalid_code", "请输入 6 位数字验证码")
    return code


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


__all__ = [
    "AuthRouteError",
    "OneTapLoginProvider",
    "OtpRecord",
    "SmsProvider",
    "WechatLoginProvider",
    "_CODE_RE",
    "_CODE_TTL",
    "_DEFAULT_SMS_TEXT",
    "_MAX_VERIFY_ATTEMPTS",
    "_RESEND_COOLDOWN",
    "mask_phone",
    "require_cn_phone",
    "require_code",
    "utcnow",
]
