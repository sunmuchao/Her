import json
import unittest

from persona_memory_sync import audit as audit_script


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

    def test_mask_snapshot_for_review_hides_income_fields_when_income_is_private(self):
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
        self.assertNotIn("self_income_range", masked["user_persona"])
        self.assertNotIn("income_range", masked["profile_internal"])

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

    def test_mask_snapshot_for_review_redacts_family_housing_and_history_boundaries(self):
        snapshot = {
            "user_persona": {
                "persona_summary_internal": "家里老人身体负担不轻，离婚原因不想展开。",
                "self_job": "某事业单位人力行政岗",
            },
            "profile_internal": {
                "job": "某事业单位人力行政岗",
                "public_job": "事业单位人力行政岗",
                "notes": "房贷金额目前不想公开；前任细节不方便展开。",
            },
            "public_profile_view": {
                "job": "事业单位人力行政岗",
                "notes": "房贷金额目前不想公开",
            },
        }
        masked = audit_script.mask_snapshot_for_review(
            snapshot,
            ["家里老人身体负担", "房贷金额", "离婚原因", "具体单位"],
        )
        flattened = json.dumps(masked, ensure_ascii=False)
        self.assertNotIn("老人身体负担", flattened)
        self.assertNotIn("房贷金额", flattened)
        self.assertNotIn("离婚原因", flattened)
        self.assertNotIn("前任细节", flattened)
        self.assertNotIn("某事业单位", flattened)
        self.assertNotIn("job", masked["profile_internal"])
        self.assertEqual(masked["public_profile_view"]["job"], "事业单位人力行政岗")


if __name__ == "__main__":
    unittest.main()
