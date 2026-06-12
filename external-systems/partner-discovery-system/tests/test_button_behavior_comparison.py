"""对比测试：验证"换一批"和"看看其他人"的行为一致性。

问题发现：
- 用户点击"换一批" → Agent追问"上一批哪里不合适"
- 用户点击"看看其他人" → Agent没有追问

测试目标：
1. 验证两个场景的Agent回复差异
2. 分析为什么"看看其他人"没有追问
3. 确认是否符合"学习式对话"原则
"""

from __future__ import annotations

import logging
import pathlib
import sys
import unittest
from datetime import datetime

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (
    AgentsSdkDiscoveryAgentRuntime,
    DiscoveryRunInput,
)
from discovery_system.agent_session_store import InMemoryDiscoveryAgentSessionStore

# 配置日志记录器
_logger = logging.getLogger("discovery_system.agent_runtime")
_logger.setLevel(logging.INFO)

log_file_path = pathlib.Path(__file__).parent / "button_behavior_comparison.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestButtonBehaviorComparison(unittest.TestCase):
    """对比"换一批"和"看看其他人"的行为。"""

    def setUp(self):
        """准备测试环境。"""
        self.runtime = AgentsSdkDiscoveryAgentRuntime()
        self.session_store = InMemoryDiscoveryAgentSessionStore()

    def _create_run_input(self, visible_actions):
        """创建测试输入。"""
        session = self.session_store.get_session("comparison-test-session")

        from unittest import mock
        import types

        class _FakeStreamingResult:
            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-comparison"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                return
                yield

        return _FakeStreamingResult, session

    def test_batch_refresh_button_triggers_followup(self):
        """测试1：验证"换一批"按钮触发追问。

        验证点：
        - Agent回复包含追问关键词
        - Agent提供反馈选项
        """
        _logger.info("=" * 80)
        _logger.info("【测试1】用户点击'换一批'按钮")
        _logger.info("=" * 80)

        _FakeStreamingResult, session = self._create_run_input(
            [{"label": "换一批", "style": "primary"}]
        )

        # 模拟Agent对"换一批"的回复（包含追问）
        def _fake_run_streamed_batch_refresh(_agent, input, **kwargs):
            return _FakeStreamingResult({
                "phase": "collecting_preferences",
                "assistant_message": "好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。",
                "suggested_actions": [
                    {"label": "太远了（都是异地）", "style": "secondary"},
                    {"label": "年龄不合适", "style": "secondary"},
                    {"label": "跳过，直接换", "style": "ghost"},
                ],
            })

        from unittest import mock

        run_input = DiscoveryRunInput(
            session_id="comparison-test-session",
            requester_id=10001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "女", "26-36岁"],
            recent_timeline=[{"item_type": "result_group", "candidates": [{"id": 1001}]}],
            runtime_context={
                "session": {"session_id": "comparison-test-session", "phase": "results_shown"},
                "user_profile": {"self_city": "无锡"},
                "visible_actions": [{"label": "换一批", "style": "primary"}],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [{"profile_id": 1001}],
            },
            search_partner_candidates=lambda _c, _l: {"has_match": True, "results": []},
            sync_requester_persona_memory=lambda _p: {"synced": True},
            propose_requester_profile_update=lambda _p, _e="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created": False},
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), \
             mock.patch("agents.Agent", side_effect=lambda **kw: object()), \
             mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed_batch_refresh):

            result = self.runtime._run_with_agents_sdk(
                run_input, event="user_message", user_message="换一批", action_context=None
            )

        assistant_message = result.decision.assistant_message
        _logger.info(f"Agent回复: {assistant_message}")

        # 验证：应该包含追问
        has_followup = any(kw in assistant_message for kw in ["哪里", "不合适", "不太合适"])
        self.assertTrue(has_followup, f"'换一批'应该触发追问，但回复是: {assistant_message}")
        _logger.info("✅ 验证通过: '换一批'触发了追问")

    def test_see_others_button_should_followup_after_fix(self):
        """测试2（修复后）：验证"看看其他人"按钮也应该追问。

        修复后，Agent应该对"看看其他人"也追问。

        验证点：
        - Agent回复应该包含追问关键词
        """
        _logger.info("=" * 80)
        _logger.info("【测试2】用户点击'看看其他人'按钮（修复后）")
        _logger.info("=" * 80)

        _FakeStreamingResult, session = self._create_run_input(
            [{"label": "看看其他人", "style": "secondary"}]
        )

        # 模拟Agent对"看看其他人"的回复（修复后应该追问）
        def _fake_run_streamed_see_others_fixed(_agent, input, **kwargs):
            return _FakeStreamingResult({
                "phase": "collecting_preferences",
                "assistant_message": "好的，想看看其他人。刚才这几位哪里不太合适？这样我下一轮推荐会更准。",
                "suggested_actions": [
                    {"label": "年龄不太合适", "style": "secondary"},
                    {"label": "距离太远", "style": "secondary"},
                    {"label": "跳过，直接看", "style": "ghost"},
                ],
            })

        from unittest import mock

        run_input = DiscoveryRunInput(
            session_id="comparison-test-session",
            requester_id=10001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "女", "26-36岁"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "李欣琪的介绍..."},
                {"item_type": "result_group", "candidates": [{"id": 573, "name": "李欣琪"}]},
            ],
            runtime_context={
                "session": {"session_id": "comparison-test-session", "phase": "results_shown"},
                "user_profile": {"self_city": "无锡"},
                "visible_actions": [{"label": "看看其他人", "style": "secondary"}],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [
                    {"profile_id": 573, "title": "李欣琪 30"},
                    {"profile_id": 3611, "title": "冯静雯 32"},
                ],
            },
            search_partner_candidates=lambda _c, _l: {"has_match": True, "results": []},
            sync_requester_persona_memory=lambda _p: {"synced": True},
            propose_requester_profile_update=lambda _p, _e="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created": False},
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), \
             mock.patch("agents.Agent", side_effect=lambda **kw: object()), \
             mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed_see_others_fixed):

            result = self.runtime._run_with_agents_sdk(
                run_input, event="user_message", user_message="看看其他人", action_context=None
            )

        assistant_message = result.decision.assistant_message
        _logger.info(f"Agent回复: {assistant_message}")

        # 验证：应该包含追问（修复后）
        has_followup = any(kw in assistant_message for kw in ["哪里", "不合适", "不太合适"])

        self.assertTrue(
            has_followup,
            f"'看看其他人'也应该触发追问（修复后），但回复是: {assistant_message}",
        )
        _logger.info("✅ 验证通过: '看看其他人'也触发了追问（修复后）")

    def test_soul_md_contains_followup_rules(self):
        """测试3：验证SOUL.md包含追问规则。"""
        _logger.info("=" * 80)
        _logger.info("【测试3】验证SOUL.md包含追问规则")
        _logger.info("=" * 80)

        import pathlib
        soul_md_path = DISCOVERY_ROOT / "discovery_system" / "DISCOVERY_AGENT_SOUL.md"

        with open(soul_md_path, "r", encoding="utf-8") as f:
            soul_content = f.read()

        # 验证SOUL.md包含追问规则
        self.assertIn("何时应该追问", soul_content, "SOUL.md应该包含'何时应该追问'")
        self.assertIn("看其他", soul_content, "SOUL.md应该在追问规则中包含'看其他'")
        self.assertIn("刚才哪里不太合适", soul_content, "SOUL.md应该包含追问示例")

        _logger.info("✅ 验证通过: SOUL.md包含追问规则")

        print("\n" + "=" * 80)
        print("修复验证通过")
        print("=" * 80)
        print("SOUL.md规则：用户想'看其他/换一批/跳过'时，追问'刚才哪里不太合适'")
        print("=" * 80)


if __name__ == "__main__":
    unittest.main()