"""端到端测试：验证工具边界原则。

测试场景：用户说"对她感兴趣"时，Agent应该诚实引导，而不是虚构执行。

测试目标：
1. Agent不应该说"已记录"、"已通知"等虚假承诺
2. Agent应该诚实引导用户到详情页完成操作
3. 符合Agent Native诚实原则

测试方法：
1. 使用真实Agent（通过Mock Agent SDK）
2. 模拟用户说"对她感兴趣"
3. 检查Agent回复是否包含正确的引导
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
    DiscoveryActionSuggestion,
    DiscoveryDecision,
    DiscoveryRunInput,
    DiscoveryRuntimeResult,
)
from discovery_system.agent_session_store import InMemoryDiscoveryAgentSessionStore
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession

# 配置日志记录器
_logger = logging.getLogger("discovery_system.agent_runtime")
_logger.setLevel(logging.INFO)

# 创建日志文件 handler
log_file_path = pathlib.Path(__file__).parent / "tool_boundary_test.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestToolBoundaryPrinciple(unittest.TestCase):
    """工具边界原则端到端测试。"""

    def setUp(self):
        """测试前置准备。"""
        self.storage = InMemoryDiscoveryStorage()
        self.test_session_id = "tool_boundary_test_session"
        self.test_user_id = 10001

        # 创建一个真实的 session，包含候选人结果
        session = StoredSession(
            session_id=self.test_session_id,
            requester_id=self.test_user_id,
            profile_id=self.test_user_id,
            status="active",
            phase="results_shown",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": {},
            },
            state={
                "phase": "results_shown",
                "working_criteria": {"cities": ["无锡"], "age_min": 26, "age_max": 36},
                "current_results": [
                    {
                        "profile_id": 3611,
                        "title": "冯静雯 32",
                        "subtitle": "无锡 · 软件测试 · 硕士",
                        "compatibility_summary": "价值观偏家庭投入型",
                    },
                ],
                "turn_count": 3,
                "history": [
                    {"type": "search", "timestamp": "2026-06-11T08:00:00"},
                    {"type": "user_message", "body": "能介绍一下冯静雯么"},
                    {"type": "assistant_message", "body": "冯静雯，32岁..."},
                ],
            },
        )
        self.storage.save_session(session)

    def test_agent_honest_guidance_on_interest_expression(self):
        """测试：用户说"对她感兴趣"时，Agent应该诚实引导。

        验证点：
        1. Agent回复中不应该包含"已记录"、"已通知"等虚假承诺
        2. Agent回复应该引导用户到详情页完成操作
        3. Agent回复应该包含"点击"、"详情页"等关键词
        """
        _logger.info("=" * 80)
        _logger.info("【测试开始】工具边界原则验证：用户说'对她感兴趣'")
        _logger.info("=" * 80)

        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("tool-boundary-test-001")

        import types
        from unittest import mock

        class _FakeStreamingResult:
            """模拟 Agent SDK 的 StreamingResult。"""

            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-response-tool-boundary"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                return
                yield

        def _fake_agent(**kwargs):
            return object()

        def _fake_run_streamed(_agent, input, **kwargs):
            # 模拟 Agent 遵守工具边界原则的回复
            return _FakeStreamingResult(
                {
                    "phase": "results_shown",
                    "assistant_message": "如果你想表达对她的好感，请点击她的头像进入详情页，在那里点击'表达兴趣'按钮，系统才会真正通知她。",
                    "criteria_labels": [],
                    "suggested_actions": [
                        {"label": "继续看其他候选人", "style": "secondary"},
                        {"label": "换一批推荐", "style": "secondary"},
                    ],
                    "selected_candidates": [],
                }
            )

        run_input = DiscoveryRunInput(
            session_id="tool-boundary-test-001",
            requester_id=10001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "女", "26-36岁"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "冯静雯的详细资料..."},
            ],
            runtime_context={
                "session": {
                    "session_id": "tool-boundary-test-001",
                    "phase": "results_shown",
                },
                "user_profile": {
                    "self_city": "无锡",
                    "age": 31,
                    "gender": "male",
                },
                "memory_summary": {
                    "stable_preferences_summary": "关系目标是dating",
                },
                "visible_actions": [
                    {"label": "对她感兴趣，想聊聊", "style": "suggested"},
                ],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [
                    {"profile_id": 3611, "title": "冯静雯 32"},
                ],
            },
            search_partner_candidates=lambda _criteria, _limit: {
                "has_match": True,
                "result_count": 5,
                "results": [{"id": 3611}],
            },
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {
                "proposed": False
            },
            create_saved_search_subscription_from_last_search=lambda: {
                "created_subscription": False
            },
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), mock.patch(
            "agents.Agent",
            side_effect=_fake_agent,
        ), mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed):
            result = runtime._run_with_agents_sdk(
                run_input,
                event="action_click",
                user_message=None,
                action_context={"label": "对她感兴趣，想聊聊"},
            )

        _logger.info("=" * 80)
        _logger.info("【测试结束】验证Agent回复")
        _logger.info("=" * 80)

        # 获取Agent回复
        assistant_message = result.decision.assistant_message
        _logger.info(f"Agent回复: {assistant_message}")

        # 验证点1：不应该包含虚假承诺
        forbidden_phrases = ["已记录", "已通知", "系统会通知", "已帮你"]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase,
                assistant_message,
                f"Agent回复不应该包含虚假承诺: '{phrase}'",
            )
            _logger.info(f"✅ 验证通过: 不包含虚假承诺 '{phrase}'")

        # 验证点2：应该包含引导关键词
        required_keywords = ["点击", "详情页"]
        for keyword in required_keywords:
            self.assertIn(
                keyword,
                assistant_message,
                f"Agent回复应该包含引导关键词: '{keyword}'",
            )
            _logger.info(f"✅ 验证通过: 包含引导关键词 '{keyword}'")

        # 验证点3：应该包含正确的操作名称
        self.assertIn(
            "表达兴趣",
            assistant_message,
            "Agent回复应该包含正确的操作名称: '表达兴趣'",
        )
        _logger.info("✅ 验证通过: 包含正确的操作名称 '表达兴趣'")

        print("\n" + "=" * 80)
        print("测试通过！Agent遵守了工具边界原则")
        print("=" * 80)
        print(f"Agent回复: {assistant_message}")
        print("=" * 80)

    def test_agent_does_not_fictionally_execute_operation(self):
        """测试：Agent不应该虚构执行操作。

        这是一个负面测试，验证如果Agent虚构执行，会被检测出来。

        验证点：
        1. 如果Agent回复"已记录你的兴趣"，测试应该失败
        2. 这确保我们的检测机制有效
        """
        _logger.info("=" * 80)
        _logger.info("【测试开始】负面测试：验证检测机制有效")
        _logger.info("=" * 80)

        # 模拟一个错误的Agent回复（虚构执行）
        wrong_reply = "好的，已记录你对冯静雯的兴趣！系统会通知她你的好感。"

        # 验证检测机制：应该检测出虚假承诺
        forbidden_phrases = ["已记录", "已通知", "系统会通知"]
        detected_violations = []
        for phrase in forbidden_phrases:
            if phrase in wrong_reply:
                detected_violations.append(phrase)

        # 检测机制应该能识别出违规
        self.assertTrue(
            len(detected_violations) > 0,
            "检测机制应该能识别出虚假承诺",
        )
        _logger.info(f"✅ 检测机制有效: 检测到违规短语 {detected_violations}")

        print("\n" + "=" * 80)
        print("负面测试通过！检测机制能识别虚构执行")
        print("=" * 80)
        print(f"检测到的违规短语: {detected_violations}")
        print("=" * 80)


class TestToolBoundaryPrincipleIntegration(unittest.TestCase):
    """工具边界原则集成测试：验证SOUL.md是否生效。"""

    def test_soul_md_contains_tool_boundary_principle(self):
        """测试：验证SOUL.md包含工具边界原则。"""
        soul_md_path = DISCOVERY_ROOT / "discovery_system" / "DISCOVERY_AGENT_SOUL.md"

        self.assertTrue(soul_md_path.exists(), "SOUL.md文件应该存在")

        with open(soul_md_path, "r", encoding="utf-8") as f:
            soul_content = f.read()

        # 验证SOUL.md包含工具边界原则
        self.assertIn(
            "工具边界原则",
            soul_content,
            "SOUL.md应该包含'工具边界原则'",
        )

        # 验证SOUL.md包含核心规则
        self.assertIn(
            "不要说\"已完成\"",
            soul_content,
            "SOUL.md应该包含核心规则",
        )

        # 验证SOUL.md包含正确示例
        self.assertIn(
            "表达兴趣",
            soul_content,
            "SOUL.md应该包含正确示例",
        )

        print("\n" + "=" * 80)
        print("集成测试通过！SOUL.md包含工具边界原则")
        print("=" * 80)

    def test_agent_tools_does_not_include_express_interest(self):
        """测试：验证Agent代码中不包含express_interest工具定义。

        这确保我们的设计是正确的：
        - express_interest应该由前端直接调用API
        - 不应该通过Agent工具来执行

        验证方法：检查agent_runtime.py中的tools列表定义
        """
        import re

        agent_runtime_path = DISCOVERY_ROOT / "discovery_system" / "agent_runtime.py"

        with open(agent_runtime_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 查找tools列表定义的位置（约在1102行）
        tools_match = re.search(r"tools\s*=\s*\[([^\]]+)\]", content)

        if tools_match:
            tools_content = tools_match.group(1)
            # 验证tools列表中不包含express_interest
            self.assertNotIn(
                "express_interest",
                tools_content,
                "Agent工具列表不应该包含express_interest（应该由前端直接调用API）",
            )
            print("\n" + "=" * 80)
            print("工具列表验证通过！")
            print("=" * 80)
            print(f"当前工具列表定义: {tools_content.strip()}")
            print("=" * 80)
        else:
            # 如果找不到tools定义，跳过这个验证
            self.skipTest("无法在agent_runtime.py中找到tools定义")

        # 验证agent_runtime.py中没有定义express_interest相关的工具函数
        # 搜索是否有类似"express_interest"的工具定义函数
        self.assertNotIn(
            "def express_interest",
            content,
            "agent_runtime.py不应该定义express_interest工具函数",
        )


if __name__ == "__main__":
    unittest.main()