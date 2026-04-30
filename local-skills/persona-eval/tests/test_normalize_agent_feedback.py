import unittest

from local_skills_persona_eval_import import normalize_agent_feedback


class NormalizeAgentFeedbackTests(unittest.TestCase):
    def test_normalizes_wait_agent_status_payload(self):
        payload = {
            "status": {
                "agent-1": {
                    "completed": """```json
{
  "memory_accuracy": {
    "accurate": ["32岁", "上海"],
    "drift": ["target_cities 漏掉稳定留沪"],
    "do_not_public": ["准确收入"],
    "summary": "整体准确"
  },
  "matching_feedback": {
    "overall_satisfaction": "高",
    "candidate_reviews": [
      {"rank": 1, "name": "季沉川", "verdict": "愿意聊"}
    ],
    "systemic_issues": ["表达自然度区分不够强"],
    "summary": "整体满意"
  },
  "overall_score": 88,
  "final_summary": "整体不错"
}
```"""
                }
            },
            "timed_out": False,
        }
        persona_index = {
            "ordered": ["shanghai_exec_f"],
            "by_persona_id": {
                "shanghai_exec_f": {
                    "persona_id": "shanghai_exec_f",
                    "display_name": "用户A01",
                    "agent_id": "agent-1",
                    "profile_id": 30082,
                    "user_key": "uk-1",
                }
            },
            "by_agent_id": {
                "agent-1": {
                    "persona_id": "shanghai_exec_f",
                    "display_name": "用户A01",
                    "agent_id": "agent-1",
                    "profile_id": 30082,
                    "user_key": "uk-1",
                }
            },
        }

        normalized, errors = normalize_agent_feedback.normalize_feedback_payload(
            payload,
            persona_index=persona_index,
        )

        self.assertEqual(errors, [])
        self.assertEqual(len(normalized), 1)
        entry = normalized[0]
        self.assertEqual(entry["persona_id"], "shanghai_exec_f")
        self.assertEqual(entry["display_name"], "用户A01")
        self.assertEqual(entry["profile_id"], 30082)
        self.assertEqual(entry["overall_score"], 88.0)
        self.assertEqual(entry["memory_accuracy"]["drift"], ["target_cities 漏掉稳定留沪"])
        self.assertEqual(
            entry["matching_feedback"]["candidate_reviews"][0]["name"],
            "季沉川",
        )

    def test_normalizes_results_report_memory_shape(self):
        payload = {
            "run_label": "subagent_rerun",
            "results": [
                {
                    "persona_id": "lin",
                    "display_name": "林知夏",
                    "accurate": ["基础信息准确"],
                    "drift": ["公开名字像系统代号"],
                    "do_not_public": ["准确收入"],
                    "summary": "整体比较稳",
                }
            ],
        }

        normalized, errors = normalize_agent_feedback.normalize_feedback_payload(payload)

        self.assertEqual(errors, [])
        self.assertEqual(normalized[0]["persona_id"], "lin")
        self.assertEqual(normalized[0]["memory_accuracy"]["summary"], "整体比较稳")
        self.assertNotIn("matching_feedback", normalized[0])

    def test_normalizes_legacy_matching_feedback_list(self):
        payload = [
            {
                "persona_id": "zhou",
                "display_name": "周予安",
                "candidate_reviews": [
                    {"rank": 1, "name": "候选A", "score": 80, "verdict": "满意"}
                ],
                "systemic_issue": ["硬筛过死"],
                "summary": "整体方向不算错",
                "overall_verdict": "基本合理",
            }
        ]

        normalized, errors = normalize_agent_feedback.normalize_feedback_payload(payload)

        self.assertEqual(errors, [])
        entry = normalized[0]
        self.assertEqual(entry["persona_id"], "zhou")
        self.assertEqual(entry["overall_verdict"], "基本合理")
        self.assertEqual(entry["matching_feedback"]["summary"], "整体方向不算错")
        self.assertEqual(entry["matching_feedback"]["systemic_issues"], ["硬筛过死"])
        self.assertEqual(entry["matching_feedback"]["candidate_reviews"][0]["name"], "候选A")


if __name__ == "__main__":
    unittest.main()
