"""SSE Server configuration."""

from __future__ import annotations

import os


class Config:
    """SSE Server configuration."""

    # Server settings
    HOST: str = os.environ.get("SSE_SERVER_HOST", "127.0.0.1")
    PORT: int = int(os.environ.get("SSE_SERVER_PORT", "8081"))

    # Connection settings
    HEARTBEAT_INTERVAL: int = 30  # seconds
    MAX_CONNECTIONS: int = 1000  # maximum concurrent connections

    # Push settings
    PUSH_TIMEOUT: float = 2.0  # seconds timeout for HTTP callback

    # Database settings (for future outbox polling)
    DATABASE_URL: str = os.environ.get("PARTNER_CHAT_DB", "")

    # Logging
    LOG_LEVEL: str = os.environ.get("SSE_SERVER_LOG_LEVEL", "INFO")


config = Config()