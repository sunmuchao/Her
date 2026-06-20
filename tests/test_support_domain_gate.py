"""Tests for §13.1.3 support-domain gate and trust contracts."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from match_domain.boundary import assert_gate_mirror_fields, assert_recommendation_status_only
from match_domain.gate_runner import (
    apply_gate_decision,
    evaluate_recommendation_gate,
    recommendation_row_gate_fields,
)
from match_domain.support_contracts import GATE_OUTCOME_HOLD, GATE_OUTCOME_PASS
from match_domain.trust_summary import build_trust_summary


class SupportContractsTests(unittest.TestCase):
    def test_evaluate_recommendation_gate_maps_final_review(self) -> None:
        decision = evaluate_recommendation_gate(
            candidate_id=42,
            final_review={
                "status": "direct_greet_ready",
                "reason": "ok",
                "payload": {},
            },
            risk_flags=[],
        )
        self.assertEqual(decision.outcome, GATE_OUTCOME_PASS)
        self.assertIn("ok", decision.reason_codes)

    def test_apply_gate_decision_keeps_recommendation_owned_status(self) -> None:
        from match_domain.support_contracts import GateDecision

        mirror = apply_gate_decision(
            GateDecision(
                subject_type="recommendation",
                subject_id="42",
                outcome=GATE_OUTCOME_HOLD,
                reason_codes=["risk:foo"],
            ),
            delivery_status="review_pending",
            delivery_reason="gate_hold",
        )
        self.assertEqual(mirror["gate_outcome"], GATE_OUTCOME_HOLD)
        assert_recommendation_status_only("review_pending")
        assert_gate_mirror_fields({"delivery_status": "review_pending", "gate_outcome": "hold"})

    def test_recommendation_row_gate_fields_json(self) -> None:
        from match_domain.support_contracts import GateDecision

        fields = recommendation_row_gate_fields(
            GateDecision(
                subject_type="recommendation",
                subject_id="1",
                outcome=GATE_OUTCOME_PASS,
                reason_codes=["direct_greet_ready"],
                details_ref="recommendation_gate:final_review:direct_greet_ready",
            )
        )
        self.assertEqual(fields["gate_outcome"], GATE_OUTCOME_PASS)
        self.assertIn("direct_greet_ready", fields["gate_reason_codes_json"])

    def test_build_trust_summary_from_profile(self) -> None:
        trust = build_trust_summary(
            {"id": 7, "verified_level": "photo", "live_video_verified": True},
        )
        self.assertEqual(trust.profile_id, 7)
        self.assertTrue(trust.labels)


class SearchVisibilityTests(unittest.TestCase):
    @patch("match_domain.search_visibility.overlay_records_with_moderation")
    def test_apply_search_visibility_gate(self, overlay_mock: MagicMock) -> None:
        from match_domain.search_visibility import apply_search_visibility_gate

        overlay_mock.return_value = [{"id": 1, "account_moderation_action": "warn"}]
        out = apply_search_visibility_gate(
            {
                "results": [{"id": 1, "match_tier": "strict", "compatibility_flags": []}],
                "fallback_results": [],
            },
            moderation_dsn="mysql://test",
        )
        self.assertTrue(out["search_gate"]["moderation_applied_externally"])
        self.assertEqual(len(out["results"]), 1)


if __name__ == "__main__":
    unittest.main()
