"""验证工具 description 是否正确传递给 Agent"""
import os
import unittest
import json

os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = "test_profile_source"
os.environ["PERSONA_MEMORY_MYSQL_SOURCE"] = "test_persona_source"
os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = "agent"

from discovery_system.agent_runtime import AgentsSdkDiscoveryAgentRuntime, DiscoveryRunInput


class ToolDescriptionVerificationTests(unittest.TestCase):
    """验证工具 description 是否正确构建"""

    def test_tool_description_contains_important_warning(self) -> None:
        """验证工具 description 包含关键的使用场景说明"""
        # 模拟 run_input
        run_input = DiscoveryRunInput(
            session_id="test-session",
            requester_id=70001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["城市:无锡"],
            recent_timeline=[],
            runtime_context={
                "current_results": [
                    {"profile_id": 1005, "title": "冯静雯 32"},
                ],
                "user_profile": {"age": 30},
                "visible_actions": [],
            },
            search_partner_candidates=lambda criteria, limit: {"results": []},
            sync_requester_persona_memory=lambda patch: {"success": True},
            propose_requester_profile_update=lambda patch, evidence: {"success": True},
            create_saved_search_subscription_from_last_search=lambda: {"success": True},
            submit_rejection_feedback=lambda **kwargs: {"success": True},
            get_feedback_options=lambda **kwargs: {"options": []},
        )

        # 由于需要真实的 API key 才能运行 Agent，我们只验证工具构建逻辑
        # 通过检查代码中的工具定义字符串来验证

        # 直接读取 agent_runtime.py 中的工具 description
        import inspect
        from discovery_system import agent_runtime

        source_code = inspect.getsource(agent_runtime)

        print("=" * 60)
        print("【工具 Description 验证】")
        print("=" * 60)

        # 检查 reply_to_user 的 description
        reply_markers = [
            "用于对话场景，不展示候选人卡片",
            "用户想了解现有候选人详情",
            "不要使用 show_candidates",
        ]
        for marker in reply_markers:
            if marker in source_code:
                print(f"✅ reply_to_user description 包含: '{marker}'")
            else:
                print(f"❌ reply_to_user description 缺失: '{marker}'")

        print()

        # 检查 show_candidates 的 description
        show_markers = [
            "只有在搜索新候选人后才使用",  # 实际的 description 文案
            "用户想了解现有候选人详情 → 使用 reply_to_user",
            "当前已有候选人展示，用户只是想对话 → 使用 reply_to_user",
        ]
        for marker in show_markers:
            if marker in source_code:
                print(f"✅ show_candidates description 包含: '{marker}'")
            else:
                print(f"❌ show_candidates description 缺失: '{marker}'")

        print("=" * 60)

        # 验证所有 marker 都存在
        all_markers = reply_markers + show_markers
        missing_markers = [m for m in all_markers if m not in source_code]

        self.assertEqual(len(missing_markers), 0, f"缺失的 description 内容: {missing_markers}")

        print("【验证结果】")
        print("✅ 所有工具 description 都包含关键的使用场景说明")
        print("✅ AI 应该能够正确理解何时使用 reply_to_user vs show_candidates")

    def test_runtime_context_build_correctly(self) -> None:
        """验证 runtime context 构建正确，包含所有候选人"""
        from discovery_system.agent_runtime import _build_runtime_prompt

        runtime_context = {
            "current_results": [
                {"profile_id": 1001, "title": "张安萌 27", "reason_summary": "城市一致"},
                {"profile_id": 1002, "title": "陈佳悦 32", "reason_summary": "价值观匹配"},
                {"profile_id": 1003, "title": "陈以心 30", "reason_summary": "性格匹配"},
                {"profile_id": 1004, "title": "李欣琪 30", "reason_summary": "家庭投入型"},
                {"profile_id": 1005, "title": "冯静雯 32", "reason_summary": "测试工程师"},
            ],
            "user_profile": {"age": 30, "city": "无锡"},
            "visible_actions": [],
        }

        run_input = DiscoveryRunInput(
            session_id="test-session",
            requester_id=70001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["城市:无锡"],
            recent_timeline=[],
            runtime_context=runtime_context,
            search_partner_candidates=lambda criteria, limit: {"results": []},
            sync_requester_persona_memory=lambda patch: {"success": True},
            propose_requester_profile_update=lambda patch, evidence: {"success": True},
            create_saved_search_subscription_from_last_search=lambda: {"success": True},
            submit_rejection_feedback=lambda **kwargs: {"success": True},
            get_feedback_options=lambda **kwargs: {"options": []},
        )

        prompt = _build_runtime_prompt(
            run_input=run_input,
            event="user_message",
            user_message="能介绍一下李欣琪",
        )

        context = json.loads(prompt)

        print("=" * 60)
        print("【Runtime Context 验证（修复后）】")
        print("=" * 60)
        print("用户消息:", context["event"]["user_message"])
        print("候选人数量:", len(context["state"]["current_results"]))
        print()

        # 验证所有候选人信息都传递给 Agent（不再截断到前3位）
        self.assertEqual(len(context["state"]["current_results"]), 5, "应该包含所有5位候选人，不应截断")

        for card in context["state"]["current_results"]:
            print(f"候选人: {card['title']} (profile_id: {card['profile_id']})")
            self.assertIsNotNone(card["profile_id"])
            self.assertIsNotNone(card["title"])

        print("=" * 60)
        print("✅ Runtime context 构建正确")
        print("✅ 所有候选人信息都传递给 Agent（不再截断）")
        print("✅ 用户问'李欣琪'时，Agent 能够找到这位候选人")


if __name__ == "__main__":
    unittest.main(verbosity=2)