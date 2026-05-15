"""HTTP + JSON-RPC gateway for partner recommendation and matchmaking systems."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["application", "make_application"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(".app", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
