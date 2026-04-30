import unittest
from pathlib import Path

from local_skills_persona_eval_import import build_audit_summary


class BuildAuditSummaryTests(unittest.TestCase):
    def test_builds_nested_audit_summary_with_optional_artifacts(self):
        feedback = [
            {
                "persona_id": "shanghai_exec_f",
                "display_name": "用户A01",
                "memory_accuracy": {
                    "accurate": ["32岁", "上海"],
                    "drift": [
                        "target_cities 只写上海，漏掉稳定留沪",
                        "target_accept_long_distance 写成可协商过宽",
                    ],
                    "do_not_public": ["准确收入 85 万", "具体公司"],
                    "summary": "核心信息正确，但有约束偏差",
                },
                "matching_feedback": {
                    "overall_satisfaction": "高",
                    "candidate_reviews": [
                        {"rank": 1, "name": "季沉川", "verdict": "愿意聊"},
                        {"rank": 2, "name": "顾闻舟", "verdict": "愿意聊"},
                    ],
                    "systemic_issues": ["表达自然度区分不够强"],
                    "summary": "整体满意",
                },
                "overall_score": 88,
                "final_summary": "整体靠谱",
            },
            {
                "persona_id": "shenzhen_divorce_mom_f",
                "display_name": "用户A05",
                "memory_accuracy": {
                    "accurate": ["35岁", "深圳"],
                    "drift": [
                        "target_accept_partner_children 语义错位",
                        "孩子信息记录不完整",
                    ],
                    "do_not_public": ["孩子具体情况", "离婚原因"],
                    "summary": "婚育语义有偏差",
                },
                "matching_feedback": {
                    "overall_satisfaction": "低",
                    "candidate_reviews": [],
                    "no_match_reasonable": True,
                    "systemic_issues": ["数据池为空", "原因解释太粗"],
                    "summary": "无结果可理解但不满意",
                },
                "overall_score": 56,
                "final_summary": "匹配受限于数据池",
            },
        ]
        memory_snapshots = [
            {
                "persona_id": "shanghai_exec_f",
                "display_name": "用户A01",
                "profile_id": 30082,
                "private_boundaries": ["准确收入", "具体公司"],
            },
            {
                "persona_id": "shenzhen_divorce_mom_f",
                "display_name": "用户A05",
                "profile_id": 30086,
                "private_boundaries": ["孩子具体情况", "离婚原因"],
            },
        ]
        search_results = [
            {
                "persona_id": "shanghai_exec_f",
                "output": "1. 季沉川 | score=236 | 34岁 | 上海 | 战略咨询经理",
            },
            {
                "persona_id": "shenzhen_divorce_mom_f",
                "output": (
                    "No matches found.\n"
                    "pool_summary: scanned=1 | passed=0\n"
                    "why_no_match: exclude_record_ref x1"
                ),
            },
        ]
        dataset_diagnostics = {
            "note": "深圳画像无结果主要是样本覆盖问题。"
        }

        summary = build_audit_summary.build_audit_summary(
            feedback,
            Path("/tmp/feedback.json"),
            run_id="persona_eval_many_20260430_1",
            memory_snapshots=memory_snapshots,
            search_results=search_results,
            dataset_diagnostics=dataset_diagnostics,
        )

        self.assertEqual(summary["run_id"], "persona_eval_many_20260430_1")
        self.assertEqual(summary["overall"]["agent_count"], 2)
        self.assertEqual(summary["overall"]["overall_score_avg"], 72.0)
        self.assertEqual(
            summary["overall"]["matching_satisfaction_distribution"],
            {"high": 1, "low": 1},
        )
        self.assertIn("婚育语义映射不准", summary["overall"]["common_memory_issues"])
        self.assertIn("收入信息不宜公开", summary["overall"]["common_public_risks"])
        self.assertIn("数据池覆盖不足", summary["overall"]["common_matching_issues"])
        self.assertEqual(summary["personas"][0]["profile_id"], 30082)
        self.assertEqual(
            summary["personas"][0]["matching_verdict"],
            ["季沉川：愿意聊", "顾闻舟：愿意聊"],
        )
        self.assertEqual(summary["personas"][1]["matching_verdict"][0], "无候选")
        self.assertIn("exclude_record_ref", summary["personas"][1]["matching_verdict"][1])
        self.assertEqual(summary["dataset_diagnostics"]["tiny_pool_personas"][0]["scanned"], 1)
        self.assertEqual(summary["dataset_diagnostics"]["note"], "深圳画像无结果主要是样本覆盖问题。")

    def test_dataset_diagnostics_can_be_empty(self):
        summary = build_audit_summary.build_audit_summary(
            feedback=[],
            feedback_input=Path("/tmp/empty.json"),
            run_id="empty_run",
            memory_snapshots=[],
            search_results=[],
            dataset_diagnostics=None,
        )

        self.assertEqual(summary["run_id"], "empty_run")
        self.assertEqual(summary["overall"]["agent_count"], 0)
        self.assertNotIn("dataset_diagnostics", summary)


if __name__ == "__main__":
    unittest.main()
