"""API key auth, per-IP rate limiting, client IP extraction for the partner gateway.

SECURITY FIX: Added multi-dimensional rate limiting for sensitive endpoints.

Changes:
1. SmsRateLimiter - Phone + IP dual-dimension limiting (prevent SMS bombing)
2. VerifyCodeRateLimiter - Prevent brute-force verification attempts
3. TieredRateLimiter - Path-based tiered rate limits
"""

from __future__ import annotations

import os
import threading
from collections import deque
from datetime import datetime, timedelta, timezone


def client_ip(environ: dict) -> str:
    if os.environ.get("PARTNER_GATEWAY_TRUST_X_FORWARDED_FOR", "").lower() in ("1", "true", "yes"):
        xff = (environ.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            return xff.split(",")[0].strip()
    return (environ.get("REMOTE_ADDR") or "").strip() or "0.0.0.0"


class ApiKeyGuard:
    __slots__ = ("_key",)

    def __init__(self) -> None:
        self._key = (os.environ.get("PARTNER_GATEWAY_API_KEY") or "").strip()

    @property
    def required(self) -> bool:
        return bool(self._key)

    def allows(self, environ: dict) -> bool:
        if not self._key:
            return True
        path = (environ.get("PATH_INFO") or "/").rstrip("/") or "/"
        if path == "/health":
            return True
        auth = (environ.get("HTTP_AUTHORIZATION") or "").strip()
        if auth.startswith("Bearer ") and auth[7:].strip() == self._key:
            return True
        if (environ.get("HTTP_X_API_KEY") or "").strip() == self._key:
            return True
        return False


class MinuteRateLimiter:
    """Fixed window: at most ``n`` requests per distinct IP per rolling minute."""

    __slots__ = ("_hits", "_limit", "_lock")

    def __init__(self, per_minute: int) -> None:
        self._limit = int(per_minute)
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        if self._limit <= 0:
            return True
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        with self._lock:
            dq = self._hits.setdefault(ip, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._limit:
                return False
            dq.append(now)
            return True


class SmsRateLimiter:
    """短信发送独立限流器：多维度限制防止轰炸

    维度：
    1. 手机号维度：同一号码每分钟最多 N 次（默认 1 次）
    2. IP 维度：同一 IP 每分钟最多 M 次不同号码（默认 5 次）

    这样可以：
    - 防止对单一手机号的轰炸攻击
    - 防止分布式攻击（多 IP 协同轰炸同一号码）
    - 防止滥用（同一 IP 发送大量不同号码）
    """
    __slots__ = ("_phone_hits", "_ip_hits", "_phone_limit", "_ip_limit", "_lock")

    def __init__(self, phone_limit: int = 1, ip_limit: int = 5) -> None:
        self._phone_limit = phone_limit  # 每手机号每分钟限制
        self._ip_limit = ip_limit        # 每 IP 每分钟限制
        self._phone_hits: dict[str, deque[datetime]] = {}
        self._ip_hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow_sms(self, phone: str, ip: str) -> tuple[bool, str | None]:
        """检查是否允许发送短信

        Args:
            phone: 目标手机号
            ip: 客户端 IP

        Returns:
            (allowed, reason) - allowed=True 表示允许发送
            reason 在拒绝时说明原因
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)

        with self._lock:
            # 手机号维度检查（防单号码轰炸）
            phone_dq = self._phone_hits.setdefault(phone, deque())
            while phone_dq and phone_dq[0] < cutoff:
                phone_dq.popleft()
            if len(phone_dq) >= self._phone_limit:
                seconds = max(1, int((phone_dq[0] - cutoff).total_seconds()))
                return False, f"该手机号发送过于频繁，请等待 {seconds} 秒后再试"

            # IP 维度检查（防分布式攻击）
            ip_dq = self._ip_hits.setdefault(ip, deque())
            while ip_dq and ip_dq[0] < cutoff:
                ip_dq.popleft()
            if len(ip_dq) >= self._ip_limit:
                return False, "当前网络发送次数已达上限，请稍后再试"

            # 记录本次请求（两个维度都记录）
            phone_dq.append(now)
            ip_dq.append(now)
            return True, None

    def reset(self, phone: str | None = None, ip: str | None = None) -> None:
        """重置指定手机号或 IP 的记录（用于调试或特殊情况）"""
        with self._lock:
            if phone is not None:
                self._phone_hits.pop(phone, None)
            if ip is not None:
                self._ip_hits.pop(ip, None)


class VerifyCodeRateLimiter:
    """验证码验证独立限流器：防暴力破解

    同一手机号每分钟最多 N 次验证尝试（默认 10 次）
    配合 auth_common.py 的 _MAX_VERIFY_ATTEMPTS（单次验证码最多 5 次错误）
    """
    __slots__ = ("_hits", "_limit", "_lock")

    def __init__(self, per_minute: int = 10) -> None:
        self._limit = per_minute
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow_verify(self, phone: str) -> bool:
        """检查是否允许验证

        Args:
            phone: 目标手机号

        Returns:
            True 表示允许验证尝试
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        with self._lock:
            dq = self._hits.setdefault(phone, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._limit:
                return False
            dq.append(now)
            return True


class TieredRateLimiter:
    """分级限流：不同路径使用不同限制

    配置示例：
    - 短信发送：10/IP/min
    - 验证码验证：10/IP/min
    - 文件上传：20/IP/min
    - 创建会话：30/IP/min
    - 其他认证：30/IP/min
    - 默认：600/IP/min
    """

    TIER_LIMITS = {
        "/v1/auth/sms/send-code": 10,
        "/v1/auth/sms/verify-code": 10,
        "/v1/auth/": 30,
        "/v2/media/upload": 20,
        "/v1/discovery/sessions": 30,  # POST 创建
        "/v1/verifications/": 20,
        "default": 600,
    }

    def __init__(self) -> None:
        self._limiters: dict[str, MinuteRateLimiter] = {}
        for key, limit in self.TIER_LIMITS.items():
            self._limiters[key] = MinuteRateLimiter(limit)

    def get_limit_for_path(self, path: str) -> MinuteRateLimiter:
        """根据路径获取对应的限流器"""
        # 精确匹配优先
        if path in self._limiters:
            return self._limiters[path]

        # 前缀匹配（只匹配以 / 结尾的配置）
        for prefix, limiter in self._limiters.items():
            if prefix.endswith("/") and path.startswith(prefix):
                return limiter

        # 默认
        return self._limiters["default"]

    def allow(self, ip: str, path: str) -> bool:
        limiter = self.get_limit_for_path(path)
        return limiter.allow(ip)


def rate_limiter_from_environ() -> MinuteRateLimiter:
    raw = (os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE") or "600").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 600
    return MinuteRateLimiter(n)


def sms_rate_limiter_from_environ() -> SmsRateLimiter:
    """从环境变量创建短信限流器

    环境变量：
    - SMS_RATE_LIMIT_PHONE_PER_MINUTE: 每手机号每分钟限制（默认 1）
    - SMS_RATE_LIMIT_IP_PER_MINUTE: 每 IP 每分钟限制（默认 5）
    """
    phone_limit = int(os.environ.get("SMS_RATE_LIMIT_PHONE_PER_MINUTE", "1") or "1")
    ip_limit = int(os.environ.get("SMS_RATE_LIMIT_IP_PER_MINUTE", "5") or "5")
    return SmsRateLimiter(phone_limit=phone_limit, ip_limit=ip_limit)


def verify_rate_limiter_from_environ() -> VerifyCodeRateLimiter:
    """从环境变量创建验证码限流器

    环境变量：
    - VERIFY_RATE_LIMIT_PER_MINUTE: 每手机号每分钟验证限制（默认 10）
    """
    limit = int(os.environ.get("VERIFY_RATE_LIMIT_PER_MINUTE", "10") or "10")
    return VerifyCodeRateLimiter(per_minute=limit)


__all__ = [
    "ApiKeyGuard",
    "MinuteRateLimiter",
    "SmsRateLimiter",
    "VerifyCodeRateLimiter",
    "TieredRateLimiter",
    "client_ip",
    "rate_limiter_from_environ",
    "sms_rate_limiter_from_environ",
    "verify_rate_limiter_from_environ",
]
