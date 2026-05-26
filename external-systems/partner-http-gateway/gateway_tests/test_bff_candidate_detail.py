"""Tests for GET /v1/candidates/{id} BFF aggregate read."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from gateway.bff.candidate_detail import rest_candidate_detail


class _CandidateGatewayStub:
    _discovery: Any


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
        status, body = rest_candidate_detail(gateway, {"QUERY_STRING": ""}, "42")
        self.assertEqual(status, 200)
        self.assertEqual(body["candidate_id"], 42)
        self.assertEqual(body["trust_summary"]["labels"], ["human_verified"])
        self.assertIn("profile_facts", body)


if __name__ == "__main__":
    unittest.main()
