"""Gateway resolved principal tests (§13.3)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

from gateway.identity import ROLE_END_USER, ActorPrincipal
from gateway.resolved_principal import ENV_RESOLVED_PRINCIPAL, resolve_end_user_principal
from match_domain.support_contracts import Principal

_CHAT_SYSTEM_ROOT = Path(__file__).resolve().parents[2] / "partner-chat-system"
if str(_CHAT_SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHAT_SYSTEM_ROOT))


class _PrincipalGatewayStub:
    def __init__(self, *, profile_id: int | None = 42) -> None:
        self._profile_id = profile_id

    def _current_actor(self, environ: dict[str, Any]) -> ActorPrincipal | None:
        return environ.get("_actor")

    def _is_auth_session_end_user(self, actor: ActorPrincipal | None) -> bool:
        return (
            actor is not None
            and actor.auth_source == "auth_session"
            and actor.has_any_role(frozenset({ROLE_END_USER}))
        )

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return {"profile_id": self._profile_id, "requester_id": self._profile_id}


class ResolvedPrincipalTests(unittest.TestCase):
    def test_resolve_end_user_principal_caches_on_environ(self) -> None:
        gateway = _PrincipalGatewayStub(profile_id=99)
        environ: dict[str, Any] = {
            "_actor": ActorPrincipal(
                actor_id="user-1",
                roles=frozenset({ROLE_END_USER}),
                token_id="tok",
                auth_source="auth_session",
            )
        }
        first = resolve_end_user_principal(gateway, environ)
        second = resolve_end_user_principal(gateway, environ)
        self.assertIs(first, second)
        self.assertIsInstance(first, Principal)
        self.assertEqual(first.profile_id, 99)
        self.assertEqual(first.to_dict()["user_key"], "99")
        self.assertIs(environ.get(ENV_RESOLVED_PRINCIPAL), first)

    def test_staff_actor_returns_principal_without_profile(self) -> None:
        gateway = _PrincipalGatewayStub(profile_id=99)
        environ: dict[str, Any] = {
            "_actor": ActorPrincipal(
                actor_id="ops-1",
                roles=frozenset({"ops_operator"}),
                token_id="tok",
                auth_source="static_token",
            )
        }
        principal = resolve_end_user_principal(gateway, environ)
        self.assertIsNotNone(principal)
        self.assertIsNone(principal.profile_id)


if __name__ == "__main__":
    unittest.main()
