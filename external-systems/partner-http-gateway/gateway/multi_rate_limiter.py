"""Multi-dimensional rate limiting for the partner gateway.

This module extends the basic IP-level rate limiting with:
1. Phone-level SMS rate limiting (prevent SMS bombing)
2. Verification attempt tracking (prevent brute force)
3. Resource-level rate limiting (prevent enumeration attacks)
4. Distributed attack detection (coordinate across IPs)

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    MultiRateLimiter                          │
│                                                              │
│  Dimensions:                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ IP Rate Limiter (基础)                               │    │
│  │ - 每分钟全局请求上限                                  │    │
│  │ - 防止单机资源耗尽                                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ SMS Rate Limiter (SMS防护)                           │    │
│  │ - 同一手机号: 1次/分钟                               │    │
│  │ - 同一IP: 5次/分钟 (不同号码)                        │    │
│  │ - 验证尝试: 5次上限后锁定30分钟                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Resource Rate Limiter (防枚举)                       │    │
│  │ - 同一IP 404/403 错误累计                            │    │
│  │ - 超过阈值触发封禁                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Distributed Detection (分布式检测)                   │    │
│  │ - 跨IP协同攻击检测                                   │    │
│  │ - 同一资源多IP访问告警                               │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    # IP-level limits
    ip_requests_per_minute: int = 600
    ip_sms_per_minute: int = 5  # Different phone numbers per IP

    # Phone-level limits
    phone_sms_per_minute: int = 1
    phone_verify_attempts_max: int = 5
    phone_verify_lockout_minutes: int = 30

    # Resource enumeration limits
    ip_404_threshold: int = 20
    ip_403_threshold: int = 15
    ip_enum_lockout_minutes: int = 10

    # Distributed attack detection
    resource_multi_ip_threshold: int = 10  # Same resource accessed by N different IPs
    distributed_alert_window_minutes: int = 5

    @classmethod
    def from_env(cls) -> RateLimitConfig:
        """Load configuration from environment variables."""
        return cls(
            ip_requests_per_minute=int(os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE", "600") or "600"),
            ip_sms_per_minute=int(os.environ.get("PARTNER_RATE_LIMIT_SMS_IP_PER_MINUTE", "5") or "5"),
            phone_sms_per_minute=int(os.environ.get("PARTNER_RATE_LIMIT_SMS_PHONE_PER_MINUTE", "1") or "1"),
            phone_verify_attempts_max=int(os.environ.get("PARTNER_RATE_LIMIT_VERIFY_MAX_ATTEMPTS", "5") or "5"),
            phone_verify_lockout_minutes=int(os.environ.get("PARTNER_RATE_LIMIT_VERIFY_LOCKOUT_MINUTES", "30") or "30"),
            ip_404_threshold=int(os.environ.get("PARTNER_RATE_LIMIT_404_THRESHOLD", "20") or "20"),
            ip_403_threshold=int(os.environ.get("PARTNER_RATE_LIMIT_403_THRESHOLD", "15") or "15"),
            ip_enum_lockout_minutes=int(os.environ.get("PARTNER_RATE_LIMIT_ENUM_LOCKOUT_MINUTES", "10") or "10"),
            resource_multi_ip_threshold=int(os.environ.get("PARTNER_RATE_LIMIT_RESOURCE_MULTI_IP_THRESHOLD", "10") or "10"),
            distributed_alert_window_minutes=int(os.environ.get("PARTNER_RATE_LIMIT_DISTRIBUTED_WINDOW_MINUTES", "5") or "5"),
        )


@dataclass
class RateLimitDecision:
    """Result of a rate limit check."""

    allowed: bool
    reason: str | None = None
    retry_after_seconds: int | None = None
    limit_type: str | None = None


class RateLimitRecord:
    """Thread-safe record for tracking rate limit hits."""

    __slots__ = ("_hits", "_lock", "_failures", "_lockout_until")

    def __init__(self) -> None:
        self._hits: deque[datetime] = deque()
        self._failures: int = 0
        self._lockout_until: datetime | None = None
        self._lock = threading.Lock()

    def add_hit(self, now: datetime) -> None:
        """Record a hit."""
        with self._lock:
            self._hits.append(now)

    def add_failure(self, now: datetime, max_failures: int, lockout_minutes: int) -> bool:
        """Record a failure and check if lockout should be triggered.

        Returns:
            True if lockout triggered
        """
        with self._lock:
            self._failures += 1
            if self._failures >= max_failures:
                self._lockout_until = now + timedelta(minutes=lockout_minutes)
                return True
            return False

    def is_locked_out(self, now: datetime) -> tuple[bool, int | None]:
        """Check if currently locked out.

        Returns:
            (is_locked_out, remaining_seconds)
        """
        with self._lock:
            if self._lockout_until is None:
                return False, None
            if now >= self._lockout_until:
                self._lockout_until = None
                self._failures = 0
                return False, None
            remaining = int((self._lockout_until - now).total_seconds())
            return True, remaining

    def count_recent(self, now: datetime, window: timedelta) -> int:
        """Count hits within the time window."""
        with self._lock:
            cutoff = now - window
            # Prune old hits
            while self._hits and self._hits[0] < cutoff:
                self._hits.popleft()
            return len(self._hits)

    def reset(self) -> None:
        """Reset the record."""
        with self._lock:
            self._hits.clear()
            self._failures = 0
            self._lockout_until = None


class SmsRateLimiter:
    """Rate limiter specifically for SMS operations.

    Prevents:
    1. SMS bombing: Same phone number targeted repeatedly
    2. Distributed SMS bombing: Multiple IPs targeting same phone
    3. Brute force verification: Repeated verification attempts
    """

    __slots__ = ("_config", "_phone_records", "_ip_records", "_phone_lockouts", "_lock")

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig.from_env()
        self._phone_records: dict[str, RateLimitRecord] = {}
        self._ip_records: dict[str, RateLimitRecord] = {}
        self._phone_lockouts: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def _prune_expired(self, now: datetime) -> None:
        """Remove expired records."""
        with self._lock:
            # Prune phone records
            expired_phones = [
                phone for phone, record in self._phone_records.items()
                if record.count_recent(now, timedelta(minutes=5)) == 0
            ]
            for phone in expired_phones:
                self._phone_records.pop(phone, None)

            # Prune IP records
            expired_ips = [
                ip for ip, record in self._ip_records.items()
                if record.count_recent(now, timedelta(minutes=1)) == 0
            ]
            for ip in expired_ips:
                self._ip_records.pop(ip, None)

            # Prune lockouts
            expired_lockouts = [
                phone for phone, until in self._phone_lockouts.items()
                if now >= until
            ]
            for phone in expired_lockouts:
                self._phone_lockouts.pop(phone, None)

    def can_send_sms(self, phone: str, ip: str) -> RateLimitDecision:
        """Check if SMS can be sent to this phone from this IP.

        Rules:
        1. Same phone: max 1 per minute
        2. Same IP: max 5 different phones per minute
        3. Locked out phones: blocked
        """
        now = datetime.now(timezone.utc)
        minute_window = timedelta(minutes=1)

        self._prune_expired(now)

        # Check phone-level lockout
        with self._lock:
            lockout_until = self._phone_lockouts.get(phone)
            if lockout_until and now < lockout_until:
                remaining = int((lockout_until - now).total_seconds())
                return RateLimitDecision(
                    allowed=False,
                    reason="Phone number locked out due to too many verification failures",
                    retry_after_seconds=remaining,
                    limit_type="phone_lockout",
                )

        # Check phone-level rate limit
        phone_record = self._phone_records.setdefault(phone, RateLimitRecord())
        phone_count = phone_record.count_recent(now, minute_window)
        if phone_count >= self._config.phone_sms_per_minute:
            return RateLimitDecision(
                allowed=False,
                reason="SMS sent too frequently to this phone number",
                retry_after_seconds=60,
                limit_type="phone_rate",
            )

        # Check IP-level rate limit (different phones)
        ip_record = self._ip_records.setdefault(ip, RateLimitRecord())
        ip_count = ip_record.count_recent(now, minute_window)
        if ip_count >= self._config.ip_sms_per_minute:
            return RateLimitDecision(
                allowed=False,
                reason="SMS sent too frequently from this IP",
                retry_after_seconds=60,
                limit_type="ip_sms_rate",
            )

        return RateLimitDecision(allowed=True)

    def record_sms_sent(self, phone: str, ip: str) -> None:
        """Record that SMS was sent."""
        now = datetime.now(timezone.utc)
        phone_record = self._phone_records.setdefault(phone, RateLimitRecord())
        phone_record.add_hit(now)
        ip_record = self._ip_records.setdefault(ip, RateLimitRecord())
        ip_record.add_hit(now)

    def can_verify_code(self, phone: str) -> RateLimitDecision:
        """Check if verification attempt is allowed.

        Rules:
        1. Max 5 failed attempts per verification session
        2. Lockout 30 minutes after 5 failures
        """
        now = datetime.now(timezone.utc)

        # Check existing lockout
        phone_record = self._phone_records.get(phone)
        if phone_record:
            is_locked, remaining = phone_record.is_locked_out(now)
            if is_locked:
                return RateLimitDecision(
                    allowed=False,
                    reason="Phone locked out due to too many failed verification attempts",
                    retry_after_seconds=remaining or 1800,
                    limit_type="verify_lockout",
                )

        return RateLimitDecision(allowed=True)

    def record_verify_failure(self, phone: str) -> RateLimitDecision:
        """Record a verification failure and check if lockout triggered.

        Returns:
            Decision indicating if further attempts allowed
        """
        now = datetime.now(timezone.utc)
        phone_record = self._phone_records.setdefault(phone, RateLimitRecord())
        locked_out = phone_record.add_failure(
            now,
            self._config.phone_verify_attempts_max,
            self._config.phone_verify_lockout_minutes,
        )

        if locked_out:
            with self._lock:
                self._phone_lockouts[phone] = now + timedelta(minutes=self._config.phone_verify_lockout_minutes)
            return RateLimitDecision(
                allowed=False,
                reason="Too many failed verification attempts, phone locked out",
                retry_after_seconds=self._config.phone_verify_lockout_minutes * 60,
                limit_type="verify_lockout",
            )

        remaining_attempts = self._config.phone_verify_attempts_max - phone_record._failures
        return RateLimitDecision(
            allowed=True,
            reason=f"Verification failed, {remaining_attempts} attempts remaining",
            limit_type="verify_failure",
        )

    def record_verify_success(self, phone: str) -> None:
        """Record successful verification, reset failures."""
        phone_record = self._phone_records.get(phone)
        if phone_record:
            phone_record.reset()


class EnumerationRateLimiter:
    """Rate limiter to prevent resource enumeration attacks.

    Tracks 404/403 responses to detect enumeration attempts.
    """

    __slots__ = ("_config", "_ip_records", "_lock")

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig.from_env()
        self._ip_records: dict[str, RateLimitRecord] = defaultdict(RateLimitRecord)
        self._lock = threading.Lock()

    def check_enum_limit(self, ip: str, status_code: int) -> RateLimitDecision:
        """Check if IP is hitting too many error responses.

        Args:
            ip: Client IP address
            status_code: HTTP status code (404 or 403)

        Returns:
            Decision with block status
        """
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=self._config.ip_enum_lockout_minutes)

        record = self._ip_records[ip]

        # Check if already locked out
        is_locked, remaining = record.is_locked_out(now)
        if is_locked:
            return RateLimitDecision(
                allowed=False,
                reason="IP blocked due to resource enumeration",
                retry_after_seconds=remaining,
                limit_type="enum_lockout",
            )

        # Track the error
        if status_code == 404:
            record.add_failure(now, self._config.ip_404_threshold, self._config.ip_enum_lockout_minutes)
        elif status_code == 403:
            record.add_failure(now, self._config.ip_403_threshold, self._config.ip_enum_lockout_minutes)

        return RateLimitDecision(allowed=True)

    def is_ip_blocked(self, ip: str) -> tuple[bool, int | None]:
        """Check if IP is currently blocked."""
        now = datetime.now(timezone.utc)
        record = self._ip_records.get(ip)
        if not record:
            return False, None
        return record.is_locked_out(now)


class DistributedAttackDetector:
    """Detector for distributed/coordinated attacks.

    Tracks:
    1. Same resource accessed by multiple IPs
    2. Suspicious patterns across IPs
    """

    __slots__ = ("_config", "_resource_access", "_alerts", "_lock")

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig.from_env()
        self._resource_access: dict[str, set[str]] = defaultdict(set)  # resource_id -> set of IPs
        self._alerts: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record_resource_access(self, resource_type: str, resource_id: str, ip: str) -> bool:
        """Record resource access and check for distributed attack.

        Returns:
            True if alert triggered
        """
        now = datetime.now(timezone.utc)
        key = f"{resource_type}:{resource_id}"

        with self._lock:
            self._resource_access[key].add(ip)
            ip_count = len(self._resource_access[key])

            if ip_count >= self._config.resource_multi_ip_threshold:
                # Trigger alert
                alert = {
                    "timestamp": now.isoformat(),
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ip_count": ip_count,
                    "ips": list(self._resource_access[key]),
                }
                self._alerts.append(alert)
                # Emit observability event
                from observability import emit_pipeline_record
                emit_pipeline_record(
                    her_kind="security.distributed_attack_alert",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_count=ip_count,
                    alert_data=alert,
                )
                return True

        return False

    def get_recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent distributed attack alerts."""
        with self._lock:
            return self._alerts[-limit:]


class MultiRateLimiter:
    """Unified multi-dimensional rate limiter.

    Combines all rate limiting dimensions into a single interface.
    """

    __slots__ = ("_config", "_ip_limiter", "_sms_limiter", "_enum_limiter", "_distributed_detector", "_lock")

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig.from_env()
        self._ip_limiter = MinuteRateLimiter(self._config.ip_requests_per_minute)
        self._sms_limiter = SmsRateLimiter(self._config)
        self._enum_limiter = EnumerationRateLimiter(self._config)
        self._distributed_detector = DistributedAttackDetector(self._config)
        self._lock = threading.Lock()

    def allow_request(self, ip: str) -> RateLimitDecision:
        """Check if general request is allowed (IP-level)."""
        # First check enumeration block
        blocked, remaining = self._enum_limiter.is_ip_blocked(ip)
        if blocked:
            return RateLimitDecision(
                allowed=False,
                reason="IP blocked due to suspicious activity",
                retry_after_seconds=remaining,
                limit_type="enum_block",
            )

        # Then check general rate limit
        if not self._ip_limiter.allow(ip):
            return RateLimitDecision(
                allowed=False,
                reason="Rate limit exceeded",
                retry_after_seconds=60,
                limit_type="ip_rate",
            )

        return RateLimitDecision(allowed=True)

    def allow_sms(self, phone: str, ip: str) -> RateLimitDecision:
        """Check if SMS can be sent."""
        decision = self._sms_limiter.can_send_sms(phone, ip)
        if decision.allowed:
            self._sms_limiter.record_sms_sent(phone, ip)
        return decision

    def allow_verify(self, phone: str) -> RateLimitDecision:
        """Check if verification attempt is allowed."""
        return self._sms_limiter.can_verify_code(phone)

    def record_verify_failure(self, phone: str) -> RateLimitDecision:
        """Record verification failure."""
        return self._sms_limiter.record_verify_failure(phone)

    def record_verify_success(self, phone: str) -> None:
        """Record verification success."""
        self._sms_limiter.record_verify_success(phone)

    def record_error_response(self, ip: str, status_code: int) -> RateLimitDecision:
        """Record error response for enumeration detection."""
        return self._enum_limiter.check_enum_limit(ip, status_code)

    def record_resource_access(self, resource_type: str, resource_id: str, ip: str) -> bool:
        """Record resource access for distributed attack detection."""
        return self._distributed_detector.record_resource_access(resource_type, resource_id, ip)


class MinuteRateLimiter:
    """Legacy IP rate limiter (kept for backward compatibility)."""

    __slots__ = ("_hits", "_limit", "_lock")

    def __init__(self, per_minute: int) -> None:
        self._limit = int(per_minute)
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        """Check if request from IP is allowed."""
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


def multi_rate_limiter_from_environ() -> MultiRateLimiter:
    """Create MultiRateLimiter from environment configuration."""
    return MultiRateLimiter(RateLimitConfig.from_env())


__all__ = [
    "MultiRateLimiter",
    "SmsRateLimiter",
    "EnumerationRateLimiter",
    "DistributedAttackDetector",
    "MinuteRateLimiter",
    "RateLimitConfig",
    "RateLimitDecision",
    "multi_rate_limiter_from_environ",
]