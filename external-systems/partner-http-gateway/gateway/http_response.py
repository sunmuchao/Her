from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GatewayHttpResponse:
    status_code: int
    body: bytes = b""
    headers: list[tuple[str, str]] = field(default_factory=list)
    reason: str | None = None
