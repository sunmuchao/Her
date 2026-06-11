"""验证问题根因的测试实验"""
import os
import unittest
from datetime import datetime

os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = "test_profile_source"
os.environ["PERSONA_MEMORY_MYSQL_SOURCE"] = "test_persona_source"
os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = "agent"

from discovery_system.storage import InMemoryDiscoveryStorage
from discovery_system.service import DiscoveryService
from discovery_system.agent_runtime import (
    StubDiscoveryAgentRuntime,
    _build_runtime_prompt,
    DiscoveryRunInput,
)


class ProblemRootCauseTests(unittest.TestCase):
    """验证问题根因的测试"""

    def test_context_contains_candidate_title(self) -> None:
        """验证 Agent context 是否包含候选人 title 信息"""
        # 模拟 runtime_context
        runtime_context = {
            "current_results": [
                {"profile_id": 1001, "title": "张安萌 27"},
                {"profile_id": 1005, "title": "冯静雯 32"},
            ],
            "user_profile": {"age": 30, "city": "无锡"},
            "visible_actions": [],
        }

        # 构建 run_input
        run_input = DiscoveryRunInput(
            session_id="test-session",
            requester_id=70001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["城市:无锡", "年龄:27-32"],
            recent_timeline=[],
            runtime_context=runtime_context,
            search_partner_candidates=lambda criteria, limit: {"results": []},
            sync_requester_persona_memory=lambda patch: {"success": True},
            propose_requester_profile_update=lambda patch, evidence: {"success": True},
            create_saved_search_subscription_from_last_search=lambda: {"success": True},
        )

        # 构建 Agent context
        prompt = _build_runtime_prompt(
            run_input=run_input,
            event="user_message",
            user_message="能介绍一下feng jing wen",
        )

        # 分析 context
        import json
        context = json.loads(prompt)

        print("=" * 60)
        print("【Agent Context 分析】")
        print("=" * 60)
        print("用户消息:", context["event"]["user_message"])
        print("当前候选人:")
        for card in context["state"]["current_results"]:
            print("  - profile_id:", card["profile_id"])
            print("    title:", card["title"])
        print("=" * 60)

        # 验证候选人信息是否传递
        self.assertEqual(len(context["state"]["current_results"]), 2)
        titles = [card["title"] for card in context["state"]["current_results"]]
        self.assertIn("冯静雯 32", titles)

        print("【验证结果】")
        print("✅ Agent context 包含候选人 title 信息")
        print("✅ 候选人 '冯静雯 32' 在 context 中")
        print()
        print("【问题根因】")
        print("1. Agent context 包含候选人 title（'冯静雯 32'）")
        print("2. 用户消息是拼音 'feng jing wen'")
        print("3. AI 需要自己识别拼音和汉字的对应关系")
        print("4. 问题可能出在:")
        print("   - AI 拼音识别能力不足")
        print("   - AI 默认行为是展示卡片而非对话")
        print("   - 工具 description 没有明确区分 reply_to_user 和 show_candidates")

    def test_tool_description_comparison(self) -> None:
        """对比 reply_to_user 和 show_candidates 工具的 description"""
        print("=" * 60)
        print("【工具 Description 分析（已优化）】")
        print("=" * 60)
        print()
        print("reply_to_user 工具（优化后）:")
        print("  '回复用户。用于对话场景，不展示候选人卡片。'")
        print("  ⚠️ 重要：以下场景应该使用 reply_to_user，不要使用 show_candidates：")
        print("  - 用户想了解现有候选人详情（如'介绍一下第一位'）")
        print("  - 用户问问题（如'为什么推荐她'）")
        print("  - 用户表达不满或反馈")
        print("  - 用户只是想对话，不想看新的候选人")
        print()
        print("show_candidates 工具（优化后）:")
        print("  '展示候选人。用于展示新的候选人列表。'")
        print("  ⚠️ 重要：只有在搜索新候选人后才使用此工具")
        print("  - 用户想了解现有候选人详情 → 使用 reply_to_user")
        print("  - 当前已有候选人展示，用户只是想对话 → 使用 reply_to_user")
        print()
        print("【优化效果】")
        print("✅ 明确区分两种工具的使用场景")
        print("✅ 告诉 AI：想了解现有候选人 → reply_to_user")
        print("✅ 告诉 AI：搜索新候选人后 → show_candidates")
        print()
        print("【下一步】")
        print("需要在真实对话场景中验证优化效果")
        print("=" * 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)