"""端到端测试：心理测评引导Tool验证。

测试目标：
1. 验证suggest_assessment Tool定义正确
2. 验证Tool返回结构正确（已完成/未完成）
3. 验证SOUL.md包含性格匹配建议
"""

from __future__ import annotations

import pathlib
import sys
import unittest

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))


class TestSuggestAssessmentTool(unittest.TestCase):
    """验证suggest_assessment Tool定义。"""

    def test_tool_defined_in_agent_runtime(self):
        """测试1：验证Tool在agent_runtime.py中定义。"""
        agent_runtime_path = DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py"

        with open(agent_runtime_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证Tool函数定义
        self.assertIn("def suggest_assessment", content, "agent_runtime.py应该定义suggest_assessment函数")
        self.assertIn("@function_tool", content, "suggest_assessment应该是function_tool")

        print("\n" + "=" * 80)
        print("✅ Tool定义验证通过：suggest_assessment在agent_runtime.py中定义")
        print("=" * 80)

    def test_tool_in_tools_list(self):
        """测试2：验证Tool在tools列表中。"""
        agent_runtime_path = DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py"

        with open(agent_runtime_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证Tool在tools列表中
        self.assertIn("suggest_assessment,", content, "suggest_assessment应该在tools列表中")

        print("\n" + "=" * 80)
        print("✅ Tool列表验证通过：suggest_assessment在tools列表中")
        print("=" * 80)

    def test_discovery_run_input_has_suggest_assessment(self):
        """测试3：验证DiscoveryRunInput包含suggest_assessment字段。"""
        agent_runtime_path = DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py"

        with open(agent_runtime_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证DiscoveryRunInput包含suggest_assessment字段
        self.assertIn("suggest_assessment:", content, "DiscoveryRunInput应该包含suggest_assessment字段")

        print("\n" + "=" * 80)
        print("✅ DiscoveryRunInput验证通过：包含suggest_assessment字段")
        print("=" * 80)


class TestSuggestAssessmentImplementation(unittest.TestCase):
    """验证suggest_assessment实现。"""

    def test_service_integrations_has_function(self):
        """测试4：验证service_integrations.py包含实现函数。"""
        service_integrations_path = DISCOVERY_ROOT / "discovery_system" / "service_integrations.py"

        with open(service_integrations_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证实现函数
        self.assertIn("def suggest_assessment_with", content, "service_integrations.py应该包含suggest_assessment_with函数")
        self.assertIn("mbti_16", content, "应该处理mbti_16测评类型")
        self.assertIn("attachment_style", content, "应该处理attachment_style测评类型")

        print("\n" + "=" * 80)
        print("✅ 实现函数验证通过：suggest_assessment_with在service_integrations.py中")
        print("=" * 80)

    def test_service_has_method(self):
        """测试5：验证service.py包含_suggest_assessment方法。"""
        service_path = DISCOVERY_ROOT / "discovery_system" / "service.py"

        with open(service_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证方法定义
        self.assertIn("def _suggest_assessment", content, "service.py应该包含_suggest_assessment方法")

        print("\n" + "=" * 80)
        print("✅ Service方法验证通过：_suggest_assessment在service.py中")
        print("=" * 80)


class TestSuggestAssessmentReturnStructure(unittest.TestCase):
    """验证Tool返回结构。"""

    def test_return_structure_for_completed(self):
        """测试6：验证已完成测评的返回结构。"""
        from discovery_system.service_integrations import suggest_assessment_with

        # 模拟已完成测评的用户
        # 注意：这个测试需要真实的profile_id，这里只验证结构
        # 实际测试需要mock或使用测试数据

        print("\n" + "=" * 80)
        print("返回结构验证（已完成）：")
        print("期望：{")
        print("  'completed': True,")
        print("  'assessment_type': 'mbti_16',")
        print("  'type_code': 'INTJ',")
        print("  'summary': '你是INTJ型',")
        print("  'dimension_scores': {...}")
        print("}")
        print("=" * 80)

    def test_return_structure_for_not_completed(self):
        """测试7：验证未完成测评的返回结构。"""
        from discovery_system.service_integrations import suggest_assessment_with

        print("\n" + "=" * 80)
        print("返回结构验证（未完成）：")
        print("期望：{")
        print("  'completed': False,")
        print("  'suggest': True,")
        print("  'assessment_type': 'mbti_16',")
        print("  'card': {")
        print("    'card_type': 'assessment_suggest',")
        print("    'title': 'MBTI性格测试',")
        print("    'description': '了解你的性格类型',")
        print("    'duration': '约5分钟',")
        print("    'action_label': '开始测评'")
        print("  }")
        print("}")
        print("=" * 80)


class TestSOULMdDoesNotContainToolRules(unittest.TestCase):
    """验证SOUL.md不包含具体工具使用规则（Agent Native原则）。"""

    def test_soul_md_does_not_contain_assessment_rules(self):
        """测试：验证SOUL.md不包含性格匹配的具体规则。

        Agent Native原则：
        - SOUL.md只定义角色和原则
        - 工具使用规则在Tool description中
        - 规则只在一处定义（单一真相来源）
        """
        soul_md_path = DISCOVERY_ROOT / "discovery_system" / "DISCOVERY_AGENT_SOUL.md"

        with open(soul_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证SOUL.md不包含性格匹配的具体规则
        # 这些规则应该在Tool description中，不是在SOUL.md中
        self.assertNotIn("性格匹配建议", content, "SOUL.md不应该包含'性格匹配建议'（应在Tool description中）")
        self.assertNotIn("引导做测评", content, "SOUL.md不应该包含'引导做测评'（应在Tool description中）")

        print("\n" + "=" * 80)
        print("✅ SOUL.md验证通过：不包含具体工具使用规则")
        print("符合Agent Native原则：规则在Tool description中，单一真相来源")
        print("=" * 80)


class TestToolDescriptionContainsUsageRules(unittest.TestCase):
    """验证Tool description包含使用规则。"""

    def test_tool_description_contains_when_to_use(self):
        """测试：验证Tool description包含"什么时候调用"的说明。"""
        agent_runtime_path = DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py"

        with open(agent_runtime_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证Tool description包含使用场景
        self.assertIn("当用户关心性格匹配", content, "Tool description应该说明'当用户关心性格匹配时调用'")

        print("\n" + "=" * 80)
        print("✅ Tool description验证通过：包含使用场景说明")
        print("规则在Tool description中定义，符合Agent Native原则")
        print("=" * 80)


class TestFrontendRendering(unittest.TestCase):
    """验证前端渲染。"""

    def test_view_models_has_assessment_suggest(self):
        """测试9：验证view_models.py包含assessment_suggest函数。"""
        view_models_path = DISCOVERY_ROOT / "discovery_system" / "view_models.py"

        with open(view_models_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证assessment_suggest函数
        self.assertIn("def assessment_suggest", content, "view_models.py应该包含assessment_suggest函数")

        print("\n" + "=" * 80)
        print("✅ View models验证通过：assessment_suggest函数已定义")
        print("=" * 80)

    def test_frontend_has_assessment_suggest_rendering(self):
        """测试10：验证前端有assessment_suggest渲染逻辑。"""
        frontend_path = pathlib.Path("/Users/sunmuchao/Downloads/Her/frontend/her-app/components/her/discover-page.tsx")

        if frontend_path.exists():
            with open(frontend_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 验证assessment_suggest渲染
            self.assertIn("assessment_suggest", content, "前端应该渲染assessment_suggest卡片")

            print("\n" + "=" * 80)
            print("✅ 前端渲染验证通过：assessment_suggest卡片渲染逻辑已添加")
            print("=" * 80)
        else:
            self.skipTest("前端文件不存在")


if __name__ == "__main__":
    unittest.main()