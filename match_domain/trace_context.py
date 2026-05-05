"""Process-local and env-backed trace id for canonical match-domain events."""

from __future__ import annotations

import contextvars
import os
import uuid

TRACE_ID_HEX_LEN = 32

_trace_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("her_trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str | None:
    """Active trace id: context var first, then ``HER_TRACE_ID`` env."""

    ctx = _trace_ctx.get()
    if ctx:
        return ctx
    env = os.environ.get("HER_TRACE_ID")
    return env.strip() if env and str(env).strip() else None


def set_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    return _trace_ctx.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    _trace_ctx.reset(token)


__all__ = [
    "TRACE_ID_HEX_LEN",
    "get_trace_id",
    "new_trace_id",
    "reset_trace_id",
    "set_trace_id",
]
