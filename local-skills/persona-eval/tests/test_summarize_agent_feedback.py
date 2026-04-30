import tempfile
import unittest
from pathlib import Path

from local_skills_persona_eval_import import summarize_agent_feedback


class SummarizeAgentFeedbackTests(unittest.TestCase):
    def test_legacy_feedback_shape_still_works(self):
        feedback = [
            {
                "persona_id": "lin",
                "display_name": "林知夏",
                "overall_verdict": "基本合理",
                "systemic_issue": ["排序更像条件合适，不够像会心动"],
                "candidate_reviews": [
                    {"rank": 1, "name": "沈既白", "score": 88, "verdict": "满意"},
                    {"rank": 2, "name": "胡睿城", "score": 80, "verdict": "能聊聊"},
                ],
            },
            {
                "persona_id": "zhou",
                "display_name": "周予安",
                "overall_verdict": "不满意",
                "systemic_issue": ["硬筛过死"],
                "candidate_reviews": [],
            },
        ]

        summary = summarize_agent_feedback.summarize_feedback(
            feedback,
            Path("/tmp/legacy_feedback.json"),
            label="legacy",
        )

        self.assertEqual(summary["persona_count"], 2)
        self.assertEqual(summary["candidate_review_count"], 2)
        self.assertEqual(summary["average_score"], 84.0)
        self.assertEqual(summary["top1_average_score"], 88.0)
        self.assertEqual(summary["verdict_counts"], {"满意": 1, "能聊聊": 1})
        self.assertEqual(
            summary["overall_verdict_counts"],
            {"不满意": 1, "基本合理": 1},
        )
        self.assertEqual(summary["no_match_persona_count"], 1)
        self.assertEqual(summary["systemic_issue_persona_count"], 2)
        self.assertEqual(summary["memory_reviewed_persona_count"], 0)
        self.assertEqual(summary["personas"][0]["top_candidate"]["name"], "沈既白")

    def test_nested_feedback_shape_is_summarized(self):
        feedback = [
            {
                "persona_id": "shanghai_exec_f",
                "display_name": "用户A01",
                "memory_accuracy": {
                    "accurate": ["32岁", "上海"],
                    "drift": ["target_cities 漏掉稳定留沪", "异地接受度过宽"],
                    "do_not_public": ["准确收入", "具体公司"],
                    "summary": "整体准，但有偏差",
                },
                "matching_feedback": {
                    "overall_satisfaction": "高",
                    "candidate_reviews": [
                        {"rank": 1, "name": "季沉川", "verdict": "愿意聊"},
                        {"rank": 2, "name": "顾闻舟", "verdict": "愿意聊"},
                    ],
                    "no_match_reasonable": None,
                    "systemic_issues": ["表达自然度区分不够强"],
                    "summary": "整体满意",
                },
                "overall_score": 88,
                "final_summary": "整体不错",
            },
            {
                "persona_id": "shenzhen_divorce_mom_f",
                "display_name": "用户A05",
                "memory_accuracy": {
                    "accurate": ["35岁", "深圳"],
                    "drift": ["孩子语义错位"],
                    "do_not_public": ["孩子具体情况"],
                    "summary": "孩子语义有问题",
                },
                "matching_feedback": {
                    "overall_satisfaction": "低",
                    "candidate_reviews": [],
                    "no_match_reasonable": True,
                    "systemic_issues": ["数据池为空", "原因解释太粗"],
                    "summary": "无结果可理解但不满意",
                },
                "overall_score": 56,
                "final_summary": "主要是数据池问题",
            },
        ]

        summary = summarize_agent_feedback.summarize_feedback(
            feedback,
            Path("/tmp/nested_feedback.json"),
            label="nested",
        )

        self.assertEqual(summary["persona_count"], 2)
        self.assertEqual(summary["candidate_review_count"], 2)
        self.assertEqual(summary["average_score"], 0.0)
        self.assertEqual(summary["top1_average_score"], 0.0)
        self.assertEqual(summary["overall_score_average"], 72.0)
        self.assertEqual(summary["overall_score_count"], 2)
        self.assertEqual(summary["matching_satisfaction_counts"], {"低": 1, "高": 1})
        self.assertEqual(summary["no_match_persona_count"], 1)
        self.assertEqual(summary["memory_reviewed_persona_count"], 2)
        self.assertEqual(summary["memory_drift_persona_count"], 2)
        self.assertEqual(summary["privacy_flag_persona_count"], 2)
        self.assertEqual(summary["systemic_issue_persona_count"], 2)
        self.assertEqual(summary["average_memory_drift_count"], 1.5)
        self.assertEqual(summary["average_privacy_flag_count"], 1.5)
        self.assertEqual(summary["average_systemic_issue_count"], 1.5)
        self.assertEqual(summary["personas"][0]["candidate_review_count"], 2)
        self.assertFalse(summary["personas"][0]["no_match"])
        self.assertTrue(summary["personas"][1]["no_match"])
        self.assertEqual(summary["personas"][0]["top_candidate"]["verdict"], "愿意聊")

    def test_load_feedback_rejects_non_list_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text("{\"bad\": true}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                summarize_agent_feedback.load_feedback(path)


if __name__ == "__main__":
    unittest.main()
