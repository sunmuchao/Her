"""Tests for rejection feedback collection feature."""

from __future__ import annotations

import unittest

from discovery_system.feedback_service import infer_feedback_type, generate_feedback_options


class TestFeedbackTypeInference(unittest.TestCase):
    """测试反馈类型推断。"""

    def test_infer_location_distance(self):
        """测试地理位置反馈推断。"""
        feedback_text = "太远了（都是异地）"
        feedback_type = infer_feedback_type(feedback_text)
        self.assertEqual(feedback_type, "location_distance")

    def test_infer_age_gap(self):
        """测试年龄差距反馈推断。"""
        feedback_text = "年龄差距有点大（候选人 28-35，你 26）"
        feedback_type = infer_feedback_type(feedback_text)
        self.assertEqual(feedback_type, "age_gap")

    def test_infer_work_life_balance(self):
        """测试生活节奏反馈推断。"""
        feedback_text = "太忙太卷（工作压力大的感觉）"
        feedback_type = infer_feedback_type(feedback_text)
        self.assertEqual(feedback_type, "work_life_balance")

    def test_infer_secondary_criteria_age(self):
        """测试二级追问结果推断。"""
        feedback_text = "年龄差距有点大"
        feedback_type = infer_feedback_type(feedback_text)
        # 注意："年龄差距有点大"在二级追问选项中出现（见SECONDARY_OPTIONS_MAP）
        # 简短的文本（无括号补充）应被识别为二级追问结果
        self.assertEqual(feedback_type, "criteria_age")

    def test_infer_criteria_education(self):
        """测试学历反馈推断。"""
        feedback_text = "学历不太匹配"
        feedback_type = infer_feedback_type(feedback_text)
        self.assertEqual(feedback_type, "criteria_education")

    def test_infer_criteria_generic(self):
        """测试通用外在条件反馈推断。"""
        feedback_text = "外在条件不合适（年龄/学历/收入）"
        feedback_type = infer_feedback_type(feedback_text)
        self.assertEqual(feedback_type, "criteria_generic")


class TestFeedbackOptionsGeneration(unittest.TestCase):
    """测试反馈选项生成。"""

    def test_generate_primary_options(self):
        """测试一级选项生成。"""
        last_batch_candidates = [
            {"age": 30, "city": "北京"},
            {"age": 32, "city": "上海"},
        ]
        user_profile = {"age": 26, "city": "杭州"}

        result = generate_feedback_options(last_batch_candidates, user_profile)

        self.assertIn("options", result)
        self.assertIn("追问文案", result)
        self.assertIsInstance(result["options"], list)
        self.assertGreater(len(result["options"]), 0)
        self.assertIn("跳过，直接换", result["options"])

    def test_generate_secondary_options(self):
        """测试二级选项生成。"""
        result = generate_feedback_options(
            [],
            {},
            include_secondary=True,
            primary_option="外在条件不合适（年龄/学历/收入）"
        )

        self.assertIn("options", result)
        self.assertIn("追问文案", result)
        self.assertIn("年龄差距有点大", result["options"])
        self.assertIn("学历不太匹配", result["options"])


class TestFeedbackToCriteriaAdjustment(unittest.TestCase):
    """测试反馈到调整策略映射。"""

    def test_location_distance_adjustment(self):
        """测试地理位置调整策略。"""
        from discovery_system.feedback_service import FEEDBACK_TO_CRITERIA_ADJUSTMENT

        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get("location_distance")
        self.assertIsNotNone(strategy)
        self.assertEqual(strategy["affected_field"], "target_cities")
        self.assertEqual(strategy["adjustment_type"], "tighten")
        self.assertIn("preferred_traits", strategy["persona_write"])

    def test_work_life_balance_adjustment(self):
        """测试生活节奏调整策略。"""
        from discovery_system.feedback_service import FEEDBACK_TO_CRITERIA_ADJUSTMENT

        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get("work_life_balance")
        self.assertIsNotNone(strategy)
        self.assertEqual(strategy["affected_field"], "life_rhythm_weight")
        self.assertIn("生活感强", strategy["persona_write"]["preferred_traits"])

    def test_criteria_generic_needs_secondary(self):
        """测试通用外在条件需要二级追问。"""
        from discovery_system.feedback_service import FEEDBACK_TO_CRITERIA_ADJUSTMENT

        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get("criteria_generic")
        self.assertIsNotNone(strategy)
        self.assertTrue(strategy.get("need_secondary", False))


if __name__ == "__main__":
    unittest.main()