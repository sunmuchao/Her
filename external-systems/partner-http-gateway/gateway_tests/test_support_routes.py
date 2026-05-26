"""Gateway tests for §13.1.3 support routes."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from gateway.support_routes import rest_profile_trust


class _SupportGatewayStub:
    def _current_actor(self, environ: dict[str, Any]) -> Any:
        return environ.get("_actor")

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any:
        from match_domain.support_contracts import Principal

        return Principal(
            user_id="user-1",
            profile_id=42,
            roles=frozenset({"end_user"}),
            auth_source="auth_session",
            user_key="42",
        )


class SupportRoutesTests(unittest.TestCase):
    @patch("gateway.support_routes.get_profile")
    @patch("gateway.support_routes.default_profile_source")
    def test_profile_trust_returns_trust_summary(
        self,
        default_source_mock: MagicMock,
        get_profile_mock: MagicMock,
    ) -> None:
        default_source_mock.return_value = ("mysql://test", "profiles")
        get_profile_mock.return_value = {
            "id": 42,
            "verified_level": "photo",
            "live_video_verified": True,
        }
        status, payload = rest_profile_trust(
            _SupportGatewayStub(),
            {},
            path="/v1/profiles/42/trust",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["profile_id"], 42)
        self.assertIn("trust_summary", payload)
        self.assertTrue(payload["trust_summary"].get("labels"))


if __name__ == "__main__":
    unittest.main()
