"""Gateway tests for relationship ledger REST routes."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

from gateway.ledger_routes import rest_get_relation_by_case, rest_list_relations_mine


class _LedgerGatewayStub:
    def _with_ledger(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    def _current_actor(self, environ: dict[str, Any]) -> Any:
        return environ.get("_actor")

    def _is_auth_session_end_user(self, actor: Any) -> bool:
        return bool(getattr(actor, "auth_source", None) == "auth_session")

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any:
        from match_domain.support_contracts import Principal

        return Principal(
            user_id="user-1",
            profile_id=42,
            roles=frozenset({"end_user"}),
            auth_source="auth_session",
            user_key="42",
        )

    def _bound_profile_id(self) -> int:
        return 42

    def _assert_actor_can_access_ledger_relation(self, environ: dict[str, Any], relation: dict[str, Any]) -> None:
        actor = self._current_actor(environ)
        if actor is None:
            return
        allowed = {f"profile:{self._bound_profile_id()}", actor.actor_id}
        owner = str(relation.get("owner_profile_ref") or "")
        target = str(relation.get("target_profile_ref") or "")
        if owner not in allowed and target not in allowed:
            from gateway.identity import GatewayPermissionError

            raise GatewayPermissionError("denied")


class LedgerRoutesTests(unittest.TestCase):
    def test_get_relation_by_case_allows_participant(self) -> None:
        gateway = _LedgerGatewayStub()
        relation = {
            "relation_key": "rel-test",
            "owner_profile_ref": "profile:42",
            "target_profile_ref": "profile:99",
            "events": [{"event_type": "request_proxy_intro", "occurred_at": "2026-01-01"}],
            "cases": [],
        }
        gateway._with_ledger = MagicMock(return_value=relation)  # type: ignore[method-assign]
        actor = MagicMock(actor_id="profile:42", auth_source="auth_session")
        status, body = rest_get_relation_by_case(
            gateway,
            {"_actor": actor},
            "case-1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["relation"]["relation_key"], "rel-test")

    def test_list_relations_mine(self) -> None:
        gateway = _LedgerGatewayStub()
        gateway._with_ledger = MagicMock(  # type: ignore[method-assign]
            return_value=[{"relation_key": "rel-mine", "events": []}],
        )
        actor = MagicMock(actor_id="user-1", auth_source="auth_session")
        status, body = rest_list_relations_mine(gateway, {"_actor": actor})
        self.assertEqual(status, 200)
        self.assertEqual(body["profile_ref"], "profile:42")
        self.assertEqual(body["count"], 1)


if __name__ == "__main__":
    unittest.main()
