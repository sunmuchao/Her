"""Backward-compatible re-exports; canonical code is matchmaking_system.proxy_intro_core."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    from matchmaking_system import proxy_intro_core as _core  # noqa: PLC0415

    return getattr(_core, name)


def __dir__() -> list[str]:
    from matchmaking_system import proxy_intro_core as _core  # noqa: PLC0415

    return sorted({*globals().keys(), *(n for n in dir(_core) if not n.startswith("_"))})
