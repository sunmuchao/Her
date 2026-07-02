"""Rate limiting utilities for verification API endpoints.

This module provides rate limiting functionality to prevent abuse of
verification-related API endpoints, including:
- Live video challenge creation
- Video submission
- Photo review requests

Rate limits are enforced using a simple in-memory counter with time-based expiration.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any


class RateLimitExceeded(Exception):
    """Rate limit exceeded error"""

    def __init__(self, limit: str, retry_after: int):
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded: {limit}. Retry after {retry_after} seconds.")


class RateLimiter:
    """Simple in-memory rate limiter with sliding window"""

    def __init__(self):
        # Store request counts per key
        # Structure: {key: [(timestamp, count), ...]}
        self._requests: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._lock = Lock()

    def _cleanup_old_requests(self, key: str, window_seconds: int) -> None:
        """Remove requests older than the window"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds

        with self._lock:
            self._requests[key] = [
                (ts, count) for ts, count in self._requests[key]
                if ts > cutoff_time
            ]

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        """
        Check if rate limit is exceeded

        Args:
            key: The rate limit key (e.g., "user_id:endpoint")
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        self._cleanup_old_requests(key, window_seconds)

        with self._lock:
            current_count = sum(count for _, count in self._requests[key])

            if current_count >= max_requests:
                # Calculate retry_after time
                oldest_request = min(self._requests[key], key=lambda x: x[0])
                retry_after = int(window_seconds - (time.time() - oldest_request[0]))
                raise RateLimitExceeded(
                    limit=f"{max_requests} requests per {window_seconds} seconds",
                    retry_after=max(1, retry_after)
                )

            # Record this request
            self._requests[key].append((time.time(), 1))

    def get_remaining_requests(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """
        Get remaining requests allowed in the current window

        Args:
            key: The rate limit key
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            Number of remaining requests
        """
        self._cleanup_old_requests(key, window_seconds)

        with self._lock:
            current_count = sum(count for _, count in self._requests[key])
            return max(0, max_requests - current_count)


# Global rate limiter instance
_rate_limiter = RateLimiter()


# Rate limit configurations for verification endpoints
RATE_LIMITS = {
    # Live video challenge creation: 10 requests per minute
    "create_challenge": {
        "max_requests": 10,
        "window_seconds": 60,
    },
    # Video submission: 5 requests per minute
    "submit_video": {
        "max_requests": 5,
        "window_seconds": 60,
    },
    # Photo review request: 20 requests per minute
    "photo_review": {
        "max_requests": 20,
        "window_seconds": 60,
    },
}


def check_verification_rate_limit(
    endpoint: str,
    user_id: str,
) -> None:
    """
    Check rate limit for verification endpoint

    Args:
        endpoint: The endpoint name (e.g., "create_challenge", "submit_video")
        user_id: The user ID

    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    if endpoint not in RATE_LIMITS:
        return

    config = RATE_LIMITS[endpoint]
    key = f"{user_id}:{endpoint}"

    _rate_limiter.check_rate_limit(
        key=key,
        max_requests=config["max_requests"],
        window_seconds=config["window_seconds"],
    )


def get_remaining_verification_requests(
    endpoint: str,
    user_id: str,
) -> int:
    """
    Get remaining requests for verification endpoint

    Args:
        endpoint: The endpoint name
        user_id: The user ID

    Returns:
        Number of remaining requests
    """
    if endpoint not in RATE_LIMITS:
        return -1  # No limit configured

    config = RATE_LIMITS[endpoint]
    key = f"{user_id}:{endpoint}"

    return _rate_limiter.get_remaining_requests(
        key=key,
        max_requests=config["max_requests"],
        window_seconds=config["window_seconds"],
    )


def extract_user_id_from_environ(environ: dict[str, Any]) -> str:
    """
    Extract user ID from WSGI environ

    Args:
        environ: WSGI environ dict

    Returns:
        User ID string
    """
    # Try to get from actor principal
    actor = environ.get("her.actor")
    if actor and hasattr(actor, "user_id"):
        return str(actor.user_id)

    # Fallback to remote address (for unauthenticated requests)
    remote_addr = environ.get("REMOTE_ADDR", "unknown")
    return f"ip:{remote_addr}"


if __name__ == "__main__":
    # Test rate limiting
    print("Testing rate limiting...")

    user_id = "test-user-001"

    # Test create_challenge rate limit (10 per minute)
    for i in range(12):
        try:
            check_verification_rate_limit("create_challenge", user_id)
            print(f"Request {i+1}: Allowed")
        except RateLimitExceeded as e:
            print(f"Request {i+1}: Blocked - {e}")

    remaining = get_remaining_verification_requests("create_challenge", user_id)
    print(f"Remaining requests: {remaining}")

    print("✓ Rate limiting test passed")