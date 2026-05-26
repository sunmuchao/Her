"""Tests for §13.5 rule config, reason codes, and provenance v2."""

from __future__ import annotations

import unittest
from datetime import datetime

from match_domain.reason_codes import (
    normalize_reason_code,
    reason_codes_from_final_review,
)
from match_domain.rule_config import resolve_effective_rules, resolve_subscription_rule_bundles
from match_domain.chat_cooldown import resolve_assistant_cooldown_seconds
from match_domain.experiment_bucket import (
    resolve_experiment_bucket_for_subscription,
    upsert_experiment_bucket_member,
)
from match_domain.rule_config_schema import (
    SLICE_CHAT_ASSISTANT_COOLDOWN,
    SLICE_PARTNER_SEARCH_SCORING,
    SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
)
from match_domain.rule_config_store import (
    SCOPE_EXPERIMENT_BUCKET,
    SCOPE_GLOBAL,
    create_assignment,
    create_version,
    get_active_assignment,
    seed_global_defaults_from_code,
)
from match_domain.search_scoring_config import build_effective_risk_flag_penalties
from match_domain.verification_triage import auto_triage_enabled
from partner_search.search_candidates import RISK_FLAG_PENALTIES, SOFT_CONCESSION_RISK_FLAGS
from match_domain.rule_decision_trace import build_recommendation_decision_trace
from match_domain.rulesets import (
    RULE_PROVENANCE_SCHEMA,
    build_subscription_refresh_provenance,
    provenance_has_effective_params,
)


class RuleConfigTests(unittest.TestCase):
    def test_normalize_reason_code_maps_legacy_gate_reason(self):
        self.assertEqual(
            normalize_reason_code("not_compelling_enough_for_direct_greet"),
            "gate:score_below_threshold",
        )

    def test_reason_codes_from_final_review_includes_blocked_by(self):
        codes = reason_codes_from_final_review(
            {
                "reason": "not_compelling_enough_for_direct_greet",
                "payload": {"blocked_by": "score_threshold"},
            }
        )
        self.assertIn("gate:score_below_threshold", codes)
        self.assertIn("blocked_by:score_threshold", codes)

    def test_resolve_effective_rules_uses_subscription_columns(self):
        subscription = {
            "subscription_id": "saved-search-test",
            "min_direct_greet_score": 55,
            "max_review_candidates_per_refresh": 2,
            "recommendation_mode": "direct_greet_only",
            "auto_reject_on_follow_up_questions": True,
            "auto_reject_on_risk_flags": True,
            "direct_greet_profile_json": "{}",
            "subscription_overrides_json": "{}",
            "quiet_hours_start": 23,
            "quiet_hours_end": 8,
        }
        bundle = resolve_effective_rules(
            SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            context=__import__("match_domain.rule_config", fromlist=["RuleResolutionContext"]).RuleResolutionContext(
                subscription=subscription
            ),
        )
        self.assertEqual(bundle.params["min_direct_greet_score"], 55)
        self.assertIn("subscription_columns", bundle.resolution_chain)

    def test_build_subscription_refresh_provenance_v2(self):
        subscription = {
            "subscription_id": "saved-search-test",
            "min_direct_greet_score": 60,
            "max_review_candidates_per_refresh": 3,
            "recommendation_mode": "direct_greet_only",
            "auto_reject_on_follow_up_questions": True,
            "auto_reject_on_risk_flags": True,
            "direct_greet_profile_json": "{}",
            "subscription_overrides_json": "{}",
            "quiet_hours_start": 22,
            "quiet_hours_end": 9,
            "daily_notification_cap": 2,
            "skip_cooldown_days": 30,
            "min_notify_score": 40,
        }
        prov = build_subscription_refresh_provenance(
            subscription_id="saved-search-test",
            persona_profile={"target_age_min": 27},
            search_request={"criteria": {"cities": ["无锡"]}},
            subscription=subscription,
        )
        self.assertEqual(prov["schema"], RULE_PROVENANCE_SCHEMA)
        self.assertTrue(provenance_has_effective_params(prov))
        gate_params = prov["effective_params"]["recommendation.direct_greet_gate"]
        self.assertEqual(gate_params["min_direct_greet_score"], 60)
        self.assertIn("resolution_chain", gate_params)

    def test_build_recommendation_decision_trace(self):
        trace = build_recommendation_decision_trace(
            {
                "recommendation_id": 1,
                "subscription_id": "saved-search-test",
                "candidate_id": 42,
                "delivery_status": "review_pending",
                "final_review_status": "save_only",
                "final_review_reason": "not_compelling_enough_for_direct_greet",
                "gate_outcome": "hold",
                "gate_reason_codes": ["gate:score_below_threshold", "blocked_by:score_threshold"],
                "rule_provenance": {
                    "schema": RULE_PROVENANCE_SCHEMA,
                    "effective_params": {
                        "recommendation.direct_greet_gate": {
                            "min_direct_greet_score": 60,
                            "resolution_chain": ["code_defaults", "subscription_columns"],
                        }
                    },
                },
            }
        )
        self.assertTrue(trace["has_effective_params"])
        self.assertEqual(trace["effective_params"]["recommendation.direct_greet_gate"]["min_direct_greet_score"], 60)
        self.assertEqual(trace["reason_code_labels"][0]["code"], "gate:score_below_threshold")

    def test_rule_config_store_seed_and_activate(self):
        try:
            from recommendation_system.storage import connect_db, initialize_database, reset_all_tables
        except ImportError:
            self.skipTest("recommendation_system not importable")
        conn = connect_db()
        reset_all_tables(conn)
        initialize_database(conn)
        created = seed_global_defaults_from_code(conn)
        self.assertTrue(created)
        active = get_active_assignment(
            conn,
            slice_id=SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            scope_type=SCOPE_GLOBAL,
            scope_key="*",
        )
        self.assertIsNotNone(active)
        create_version(
            conn,
            version_id="rcfg_gate_test_v2",
            slice_id=SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            params={"min_direct_greet_score": 58},
            created_by="test",
        )
        create_assignment(
            conn,
            assignment_id="assign_gate_test_v2",
            version_id="rcfg_gate_test_v2",
            slice_id=SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            scope_type=SCOPE_GLOBAL,
            scope_key="*",
            priority=1,
            created_by="test",
        )
        conn.commit()
        bundles = resolve_subscription_rule_bundles(
            {
                "subscription_id": "saved-search-test",
                "subscription_overrides_json": "{}",
            },
            conn=conn,
        )
        self.assertEqual(
            bundles[SLICE_RECOMMENDATION_DIRECT_GREET_GATE].params["min_direct_greet_score"],
            58,
        )

    def test_experiment_bucket_overrides_gate_threshold(self):
        try:
            from recommendation_system.storage import connect_db, initialize_database, reset_all_tables
        except ImportError:
            self.skipTest("recommendation_system not importable")
        conn = connect_db()
        reset_all_tables(conn)
        initialize_database(conn)
        seed_global_defaults_from_code(conn)
        create_version(
            conn,
            version_id="rcfg_gate_exp_55",
            slice_id=SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            params={"min_direct_greet_score": 55},
            created_by="test",
        )
        create_assignment(
            conn,
            assignment_id="assign_exp_bucket_55",
            version_id="rcfg_gate_exp_55",
            slice_id=SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
            scope_type=SCOPE_EXPERIMENT_BUCKET,
            scope_key="exp_gate_score_55",
            priority=10,
            created_by="test",
        )
        upsert_experiment_bucket_member(
            conn,
            profile_id=42,
            bucket_key="exp_gate_score_55",
            updated_by="test",
        )
        conn.commit()
        subscription = {
            "subscription_id": "saved-search-test",
            "self_id": 42,
            "subscription_overrides_json": "{}",
        }
        bucket = resolve_experiment_bucket_for_subscription(subscription, conn=conn)
        self.assertEqual(bucket, "exp_gate_score_55")
        bundles = resolve_subscription_rule_bundles(subscription, conn=conn)
        self.assertEqual(
            bundles[SLICE_RECOMMENDATION_DIRECT_GREET_GATE].params["min_direct_greet_score"],
            55,
        )

    def test_search_scoring_applies_negotiable_tier(self):
        penalties = build_effective_risk_flag_penalties(RISK_FLAG_PENALTIES)
        sample_flag = next(iter(SOFT_CONCESSION_RISK_FLAGS))
        self.assertEqual(penalties[sample_flag], 7)

    def test_chat_cooldown_defaults(self):
        seconds = resolve_assistant_cooldown_seconds(["pace_mismatch"])
        self.assertEqual(seconds, 60)

    def test_verification_auto_triage_enabled_default(self):
        self.assertTrue(auto_triage_enabled())

    def test_resolve_subscription_includes_new_slices(self):
        subscription = {
            "subscription_id": "saved-search-test",
            "subscription_overrides_json": "{}",
        }
        bundles = resolve_subscription_rule_bundles(subscription)
        self.assertIn(SLICE_CHAT_ASSISTANT_COOLDOWN, bundles)
        self.assertIn(SLICE_PARTNER_SEARCH_SCORING, bundles)


if __name__ == "__main__":
    unittest.main()
