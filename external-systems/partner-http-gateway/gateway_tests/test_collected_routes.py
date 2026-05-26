"""Gateway tests for §13.1.2 collected read APIs."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from gateway.collected_routes import (
    rest_persona_collected,
    rest_profile_me,
)


class _CollectedGatewayStub:
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

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int:
        return int(raw_value)

    def _get_recommendation_for_actor(
        self,
        environ: dict[str, Any],
        recommendation_id: int,
    ) -> dict[str, Any]:
        return {"recommendation_id": recommendation_id, "rule_provenance": {}}


class CollectedRoutesTests(unittest.TestCase):
    @patch("gateway.collected_routes.get_profile")
    @patch.dict("os.environ", {"PARTNER_SEARCH_MYSQL_SOURCE": "mysql://root@127.0.0.1/test"})
    def test_profile_me_returns_profile_facts(self, get_profile_mock: MagicMock) -> None:
        get_profile_mock.return_value = {
            "id": 42,
            "name": "Demo",
            "age": 28,
            "city": "上海",
            "preferred_age_min": 25,
            "matcher_traits_json": '{"ignored": true}',
        }
        gateway = _CollectedGatewayStub()
        actor = MagicMock(actor_id="user-1", auth_source="auth_session")
        status, body = rest_profile_me(gateway, {"_actor": actor, "QUERY_STRING": ""})
        self.assertEqual(status, 200)
        self.assertEqual(body["profile_id"], 42)
        facts = body["profile_facts"]
        self.assertEqual(facts["city"], "上海")
        self.assertNotIn("preferred_age_min", facts)
        self.assertNotIn("matcher_traits_json", facts)

    @patch("gateway.collected_routes.load_collected_bundle")
    @patch.dict("os.environ", {"PARTNER_SEARCH_MYSQL_SOURCE": "mysql://root@127.0.0.1/test"})
    def test_persona_collected_returns_explicit_fields(self, bundle_mock: MagicMock) -> None:
        bundle_mock.return_value = {
            "user_key": "42",
            "persona": {
                "target_age_min": 25,
                "target_age_max": 32,
                "target_cities": "上海",
                "persona_summary_internal": "should not appear",
            },
            "observations": [],
            "collected_items": {
                "target_age_min": {"value": 25, "source_channel": "matchmaker_chat"},
                "target_age_max": {"value": 32, "source_channel": "matchmaker_chat"},
                "target_cities": {"value": "上海", "source_channel": "matchmaker_chat"},
            },
        }
        gateway = _CollectedGatewayStub()
        status, body = rest_persona_collected(
            gateway,
            {"QUERY_STRING": "profile_id=42"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["profile_id"], 42)
        collected = body["collected_statements"]
        self.assertEqual(collected["target_age_min"], 25)
        self.assertNotIn("persona_summary_internal", collected)
        self.assertIn("target_cities", body["collected_items"])


if __name__ == "__main__":
    unittest.main()
