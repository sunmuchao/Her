import pathlib
import sys
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_multi_agent_matchmaking_audit as journey_script


class MatchmakingJourneyTests(unittest.TestCase):
    def test_build_search_command_includes_core_filters(self):
        command = journey_script.build_search_command(
            persona_row={
                "target_gender": "男",
                "target_age_min": 30,
                "target_age_max": 36,
                "target_cities": "上海,苏州",
                "target_marital_statuses": "未婚,离异未育",
                "self_relationship_goal": "结婚导向",
                "must_have_tags": "情绪稳定,愿意沟通",
                "must_not_have_tags": "抽烟",
                "preferred_traits": "消费观正常,有耐心",
                "target_marriage_timeline": "1年内",
                "target_want_children": "想要",
                "target_marital_status_strength": "谨慎接受",
                "target_accept_partner_children_strength": "明确接受",
            },
            profile_id=90001,
            search_source="mysql://root@127.0.0.1:3307/her?table=profiles",
            candidate_limit=2,
            photo_preview_count=1,
            active_within_days=30,
            verified_level_min="basic",
        )
        self.assertIn("--self-id", command)
        self.assertIn("90001", command)
        self.assertIn("--gender", command)
        self.assertIn("男", command)
        self.assertIn("--city", command)
        self.assertIn("上海", command)
        self.assertIn("苏州", command)
        self.assertIn("--must-have", command)
        self.assertIn("情绪稳定", command)
        self.assertIn("--must-not-have", command)
        self.assertIn("抽烟", command)
        self.assertIn("--accept-partner-children-strength", command)
        self.assertIn("明确接受", command)

    def test_mask_observation_rows_for_review_masks_income(self):
        masked = journey_script.mask_observation_rows_for_review(
            [
                {"field_name": "self_income_wan", "field_value": "38"},
                {"field_name": "self_city", "field_value": "上海"},
            ],
            ["准确收入"],
        )
        self.assertEqual(masked[0]["field_value"], "31-40万/年")
        self.assertEqual(masked[1]["field_value"], "上海")

    def test_summarize_journey_results_counts_satisfaction_and_privacy(self):
        summary = journey_script.summarize_journey_results(
            [
                {
                    "review": {"drift": ["年龄写重"], "do_not_public": ["收入"], "risk_level": "high"},
                    "search": {"has_match": True},
                    "satisfaction": {"satisfied": True, "overall_verdict": "满意"},
                },
                {
                    "review": {"drift": [], "do_not_public": [], "risk_level": "medium"},
                    "search": {"has_match": False},
                    "satisfaction": {"satisfied": False, "overall_verdict": "部分满意"},
                },
                {
                    "error": "boom",
                },
            ]
        )
        self.assertEqual(summary["persona_count"], 3)
        self.assertEqual(summary["completed_count"], 2)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["drift_count"], 1)
        self.assertEqual(summary["privacy_count"], 1)
        self.assertEqual(summary["high_risk_count"], 1)
        self.assertEqual(summary["satisfied_count"], 1)
        self.assertEqual(summary["partial_satisfaction_count"], 1)
        self.assertEqual(summary["no_match_count"], 1)


if __name__ == "__main__":
    unittest.main()
