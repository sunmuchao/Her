"""Process-local and env-backed actor context for audit and authorization flows."""

from __future__ import annotations

import contextvars
import os
from dataclasses import dataclass
from typing import Iterable

_ACTOR_ID_ENV = "HER_ACTOR_ID"
_ACTOR_ROLES_ENV = "HER_ACTOR_ROLES"
_ACTOR_SOURCE_ENV = "HER_ACTOR_SOURCE"
_ACTOR_TOKEN_ID_ENV = "HER_ACTOR_TOKEN_ID"
_ACTOR_REASON_ENV = "HER_ACTOR_REASON"


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    actor_roles: tuple[str, ...] = ()
    auth_source: str | None = None
    token_id: str | None = None
    reason: str | None = None


_actor_ctx: contextvars.ContextVar[ActorContext | None] = contextvars.ContextVar(
    "her_actor_context",
    default=None,
)


def normalize_actor_roles(raw: str | Iterable[str] | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = list(raw)
    return tuple(str(part).strip() for part in parts if str(part).strip())


def get_actor_context() -> ActorContext | None:
    """Active actor context: context var first, then ``HER_ACTOR_*`` env."""

    ctx = _actor_ctx.get()
    if ctx is not None:
        return ctx
    actor_id = str(os.environ.get(_ACTOR_ID_ENV) or "").strip()
    if not actor_id:
        return None
    return ActorContext(
        actor_id=actor_id,
        actor_roles=normalize_actor_roles(os.environ.get(_ACTOR_ROLES_ENV)),
        auth_source=str(os.environ.get(_ACTOR_SOURCE_ENV) or "").strip() or None,
        token_id=str(os.environ.get(_ACTOR_TOKEN_ID_ENV) or "").strip() or None,
        reason=str(os.environ.get(_ACTOR_REASON_ENV) or "").strip() or None,
    )


def set_actor_context(
    actor_id: str | None,
    *,
    actor_roles: str | Iterable[str] | None = None,
    auth_source: str | None = None,
    token_id: str | None = None,
    reason: str | None = None,
) -> contextvars.Token[ActorContext | None]:
    actor_text = str(actor_id or "").strip()
    if not actor_text:
        return _actor_ctx.set(None)
    return _actor_ctx.set(
        ActorContext(
            actor_id=actor_text,
            actor_roles=normalize_actor_roles(actor_roles),
            auth_source=str(auth_source or "").strip() or None,
            token_id=str(token_id or "").strip() or None,
            reason=str(reason or "").strip() or None,
        )
    )


def reset_actor_context(token: contextvars.Token[ActorContext | None]) -> None:
    _actor_ctx.reset(token)


__all__ = [
    "ActorContext",
    "get_actor_context",
    "normalize_actor_roles",
    "reset_actor_context",
    "set_actor_context",
]
