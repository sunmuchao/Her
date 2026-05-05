"""API key auth, per-IP rate limiting, client IP extraction for the partner gateway."""

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


def rate_limiter_from_environ() -> MinuteRateLimiter:
    raw = (os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE") or "600").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 600
    return MinuteRateLimiter(n)


__all__ = ["ApiKeyGuard", "MinuteRateLimiter", "client_ip", "rate_limiter_from_environ"]
