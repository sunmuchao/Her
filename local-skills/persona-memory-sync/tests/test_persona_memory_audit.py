import pathlib
import sys
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_persona_memory_audit as audit_script


class PersonaMemoryAuditTests(unittest.TestCase):
    def test_build_user_key(self):
        self.assertEqual(
            audit_script.build_user_key("20260429_180000", "lin"),
            "pma_20260429_180000_lin",
        )

    def test_filter_strong_inference_patch(self):
        patch = {
            "preferred_traits": ["稳重"],
            "persona_summary_internal": "总结",
            "self_age": 30,
        }
        filtered = audit_script.filter_strong_inference_patch(patch)
        self.assertEqual(filtered["preferred_traits"], ["稳重"])
        self.assertEqual(filtered["persona_summary_internal"], "总结")
        self.assertNotIn("self_age", filtered)

    def test_summarize_reviews(self):
        summary = audit_script.summarize_reviews(
            [
                {
                    "review": {
                        "drift": ["收入写得太实"],
                        "do_not_public": ["收入范围不要公开"],
                        "risk_level": "high",
                    }
                },
                {
                    "review": {
                        "drift": [],
                        "do_not_public": ["具体单位不要公开", "婚史细节不要公开"],
                        "risk_level": "medium",
                    }
                },
            ]
        )
        self.assertEqual(summary["persona_count"], 2)
        self.assertEqual(summary["drift_count"], 1)
        self.assertEqual(summary["privacy_count"], 3)
        self.assertEqual(summary["high_risk_count"], 1)

    def test_mask_snapshot_for_review_replaces_exact_income_with_range(self):
        snapshot = {
            "user_persona": {
                "display_name": "测试",
                "self_income_wan": 38,
            },
            "profile_internal": {
                "income_range": "31-40万/年",
            },
            "public_profile_view": {},
        }
        masked = audit_script.mask_snapshot_for_review(snapshot, ["准确收入", "具体公司名"])
        self.assertNotIn("self_income_wan", masked["user_persona"])
        self.assertEqual(masked["user_persona"]["self_income_range"], "31-40万/年")

    def test_mask_snapshot_for_review_leaves_snapshot_untouched_without_income_boundary(self):
        snapshot = {
            "user_persona": {
                "self_income_wan": 38,
            },
            "profile_internal": {},
            "public_profile_view": {},
        }
        masked = audit_script.mask_snapshot_for_review(snapshot, ["具体公司名"])
        self.assertEqual(masked["user_persona"]["self_income_wan"], 38)


if __name__ == "__main__":
    unittest.main()
