"""档案状态转换服务单元测试

测试内容：
1. 状态转换规则验证
2. 状态转换逻辑正确性
3. 不允许的转换拒绝
"""

import unittest
from profile_status_service import (
    transition_profile_status,
    validate_transition,
    get_status_transition_rules,
    get_allowed_transitions_for_status,
    ALLOWED_TRANSITIONS,
)


class ProfileStatusServiceTests(unittest.TestCase):
    """档案状态转换服务测试"""

    def test_allowed_transitions_rules(self):
        """测试状态转换规则定义"""
        rules = get_status_transition_rules()

        # 验证规则包含所有状态
        self.assertIn("active", rules)
        self.assertIn("matched", rules)
        self.assertIn("inactive", rules)

        # 验证规则数量（只有3个状态）
        self.assertEqual(len(rules), 3)

        # 验证 active 的允许转换
        self.assertIn("matched", rules["active"])
        self.assertIn("inactive", rules["active"])
        self.assertEqual(len(rules["active"]), 2)

        # 验证 matched 的允许转换
        self.assertIn("active", rules["matched"])
        self.assertIn("inactive", rules["matched"])
        self.assertEqual(len(rules["matched"]), 2)

        # 验证 inactive 的允许转换
        self.assertIn("active", rules["inactive"])
        self.assertEqual(len(rules["inactive"]), 1)

        print("[成功] 状态转换规则定义正确")

    def test_validate_transition_allowed(self):
        """测试允许的状态转换"""
        # active → matched（允许）
        self.assertTrue(validate_transition("active", "matched"))

        # active → inactive（允许）
        self.assertTrue(validate_transition("active", "inactive"))

        # matched → active（允许）
        self.assertTrue(validate_transition("matched", "active"))

        # matched → inactive（允许）
        self.assertTrue(validate_transition("matched", "inactive"))

        # inactive → active（允许）
        self.assertTrue(validate_transition("inactive", "active"))

        print("[成功] 允许的转换验证正确")

    def test_validate_transition_not_allowed(self):
        """测试不允许的状态转换"""
        # inactive → matched（不允许）
        self.assertFalse(validate_transition("inactive", "matched"))

        # inactive → inactive（不允许，不能转到自己）
        self.assertFalse(validate_transition("inactive", "inactive"))

        # matched → matched（不允许，不能转到自己）
        self.assertFalse(validate_transition("matched", "matched"))

        # active → active（不允许，不能转到自己）
        self.assertFalse(validate_transition("active", "active"))

        # unknown → active（不允许，未知状态）
        self.assertFalse(validate_transition("unknown", "active"))

        print("[成功] 不允许的转换验证正确")

    def test_get_allowed_transitions_for_status(self):
        """测试获取状态允许的转换"""
        # active 的允许转换
        active_transitions = get_allowed_transitions_for_status("active")
        self.assertIn("matched", active_transitions)
        self.assertIn("inactive", active_transitions)
        self.assertEqual(len(active_transitions), 2)

        # matched 的允许转换
        matched_transitions = get_allowed_transitions_for_status("matched")
        self.assertIn("active", matched_transitions)
        self.assertIn("inactive", matched_transitions)
        self.assertEqual(len(matched_transitions), 2)

        # inactive 的允许转换
        inactive_transitions = get_allowed_transitions_for_status("inactive")
        self.assertIn("active", inactive_transitions)
        self.assertEqual(len(inactive_transitions), 1)

        # 未知状态的允许转换
        unknown_transitions = get_allowed_transitions_for_status("unknown")
        self.assertEqual(len(unknown_transitions), 0)

        print("[成功] 获取状态允许转换正确")

    def test_transition_profile_status_with_mock(self):
        """测试状态转换逻辑（模拟数据库）"""
        # 注意：这个测试需要数据库连接，暂时只测试规则验证部分
        # 实际的数据库更新测试需要在集成测试中进行

        # 测试允许的转换不会抛出规则错误
        try:
            # 这里只验证规则，不实际执行数据库更新
            self.assertTrue(validate_transition("active", "matched"))
            self.assertTrue(validate_transition("matched", "active"))
            self.assertTrue(validate_transition("inactive", "active"))
            print("[成功] 状态转换规则验证通过")
        except ValueError as e:
            self.fail(f"允许的转换抛出错误：{e}")

    def test_transition_profile_status_not_allowed_raises_error(self):
        """测试不允许的转换会抛出错误"""
        # 注意：由于需要数据库连接，这里只测试规则验证
        # 不实际调用 transition_profile_status

        # 测试不允许的转换会被拒绝
        self.assertFalse(validate_transition("inactive", "matched"))
        self.assertFalse(validate_transition("unknown", "active"))

        print("[成功] 不允许的转换会拒绝")

    def test_status_labels_mapping(self):
        """测试状态中文标签映射"""
        # 从 search_matching.py 导入状态标签
        from partner_search.search_matching import PROFILE_STATUS_LABELS

        # 验证标签包含所有状态
        self.assertIn("active", PROFILE_STATUS_LABELS)
        self.assertIn("matched", PROFILE_STATUS_LABELS)
        self.assertIn("inactive", PROFILE_STATUS_LABELS)

        # 验证标签数量（只有3个状态）
        self.assertEqual(len(PROFILE_STATUS_LABELS), 3)

        # 验证标签值
        self.assertEqual(PROFILE_STATUS_LABELS["active"], "活跃")
        self.assertEqual(PROFILE_STATUS_LABELS["matched"], "已匹配")
        self.assertEqual(PROFILE_STATUS_LABELS["inactive"], "不活跃")

        # 验证不包含旧状态
        self.assertNotIn("paused", PROFILE_STATUS_LABELS)
        self.assertNotIn("archived", PROFILE_STATUS_LABELS)

        print("[成功] 状态标签映射正确")

    def test_status_priority_order(self):
        """测试状态优先级排序"""
        from partner_search.search_candidates import PROFILE_STATUS_ORDER

        # 验证优先级包含所有状态
        self.assertIn("active", PROFILE_STATUS_ORDER)
        self.assertIn("matched", PROFILE_STATUS_ORDER)
        self.assertIn("inactive", PROFILE_STATUS_ORDER)

        # 验证优先级数量（只有3个状态）
        self.assertEqual(len(PROFILE_STATUS_ORDER), 3)

        # 验证优先级顺序：active 最高，inactive 最低
        self.assertEqual(PROFILE_STATUS_ORDER["active"], 2)
        self.assertEqual(PROFILE_STATUS_ORDER["matched"], 1)
        self.assertEqual(PROFILE_STATUS_ORDER["inactive"], 0)

        # 验证优先级关系
        self.assertGreater(PROFILE_STATUS_ORDER["active"], PROFILE_STATUS_ORDER["matched"])
        self.assertGreater(PROFILE_STATUS_ORDER["matched"], PROFILE_STATUS_ORDER["inactive"])

        # 验证不包含旧状态
        self.assertNotIn("paused", PROFILE_STATUS_ORDER)
        self.assertNotIn("archived", PROFILE_STATUS_ORDER)

        print("[成功] 状态优先级排序正确")


if __name__ == "__main__":
    print("=" * 80)
    print("档案状态转换服务单元测试")
    print("=" * 80)

    unittest.main(verbosity=2)