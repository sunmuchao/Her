"""Tests for GET /v1/candidates/{id} BFF aggregate read."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from gateway.bff.candidate_detail import _check_candidate_access_via_session, rest_candidate_detail


class _CandidateGatewayStub:
    _discovery: Any

    def _current_actor(self, environ: dict[str, Any]) -> Any:
        return None

    def _is_auth_session_end_user(self, actor: Any) -> bool:
        return False


class CandidateDetailBffTests(unittest.TestCase):
    @patch.dict("os.environ", {"HER_PROFILE_SOURCE_DSN": "mysql://root@127.0.0.1/test?table=profiles"})
    @patch("gateway.bff.candidate_detail.get_profile")
    @patch("gateway.bff.candidate_detail.build_trust_summary")
    def test_candidate_detail_returns_trust_and_facts(
        self,
        trust_mock: MagicMock,
        profile_mock: MagicMock,
    ) -> None:
        profile_mock.return_value = {"id": 42, "name": "Demo", "verified_level": "basic"}
        trust_mock.return_value = MagicMock(to_dict=lambda: {"labels": ["human_verified"]})
        gateway = _CandidateGatewayStub()
        gateway._discovery = MagicMock()
        gateway._current_actor = MagicMock(  # type: ignore[method-assign]
            return_value=MagicMock(
                actor_id="ops-1",
                has_any_role=MagicMock(return_value=True),
            )
        )
        status, body = rest_candidate_detail(gateway, {"QUERY_STRING": ""}, "42")
        self.assertEqual(status, 200)
        self.assertEqual(body["candidate_id"], 42)
        self.assertEqual(body["trust_summary"]["labels"], ["human_verified"])
        self.assertIn("profile_facts", body)

    def test_candidate_access_via_session_allows_timeline_cards(self) -> None:
        gateway = _CandidateGatewayStub()
        gateway._discovery = MagicMock()
        gateway._discovery.get_session_owner_id.return_value = 10001
        gateway._discovery.get_session_view.return_value = {
            "view": {
                "timeline": [
                    {
                        "item_type": "assistant_message",
                        "body": "先看看这几位",
                    },
                    {
                        "item_type": "result_group",
                        "cards": [
                            {"profile_id": 2701},
                            {"profile_id": 5054},
                        ],
                    },
                ]
            }
        }

        allowed = _check_candidate_access_via_session(
            gateway,
            {},
            5054,
            "discovery-session-26aa5c988392",
        )

        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
