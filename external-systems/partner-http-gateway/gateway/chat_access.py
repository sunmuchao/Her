"""Shared access checks for chat-facing gateway transports."""

from __future__ import annotations

from typing import Any, Protocol

from .role_sets import STAFF_OVERRIDE_ROLES


class ChatAccessGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...


def thread_visible_to_requester(
    gateway: ChatAccessGateway,
    environ: dict[str, Any],
    thread: dict[str, Any] | None,
    requester_id: str,
) -> bool:
    if not thread:
        return False
    actor = gateway._current_actor(environ)
    if requester_id in (thread["participant_a_id"], thread["participant_b_id"]):
        return True
    return bool(actor and actor.has_any_role(STAFF_OVERRIDE_ROLES))


__all__ = ["thread_visible_to_requester"]
