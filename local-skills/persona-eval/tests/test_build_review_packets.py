import unittest

from local_skills_persona_eval_import import build_review_packets


class BuildReviewPacketsTests(unittest.TestCase):
    def test_re_masks_income_sensitive_snapshot_fields(self):
        packets = build_review_packets.build_packets(
            [
                {
                    "persona_id": "c01",
                    "display_name": "用户C01",
                    "private_boundaries": ["准确收入"],
                }
            ],
            [
                {
                    "persona_id": "c01",
                    "display_name": "用户C01",
                    "private_boundaries": ["准确收入"],
                    "user_persona": {
                        "self_income_wan": 82,
                        "self_income_range": "76-85万/年",
                        "persona_summary_internal": "年收入约82万，认真找长期关系。",
                    },
                    "profile_internal": {
                        "income_range": "76-85万/年",
                        "personality": "年收入约82万，认真找长期关系。",
                    },
                    "public_profile_view": {
                        "job": "外企战略岗位",
                    },
                }
            ],
            [{"id": "c01", "output": "1. 候选A"}],
        )

        self.assertEqual(len(packets), 1)
        packet = packets[0]
        self.assertNotIn("self_income_wan", packet["user_persona"])
        self.assertNotIn("self_income_range", packet["user_persona"])
        self.assertNotIn("income_range", packet["profile_internal_focus"])
        self.assertIn("收入信息已隐藏", packet["user_persona"]["persona_summary_internal"])
        self.assertIn("收入信息已隐藏", packet["profile_internal_focus"]["personality"])


if __name__ == "__main__":
    unittest.main()
