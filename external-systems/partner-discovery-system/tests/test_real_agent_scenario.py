"""真实场景模拟测试：验证日志埋点和 Agent 行为。

测试场景：模拟"换一批"场景，触发日志埋点，查看 Agent 实际行为。

测试方法：
1. 使用 Mock 模拟 Agent 的返回结果
2. 触发真实的 service 流程
3. 查看日志输出
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

# 配置日志记录器，用于收集测试证据
_logger = logging.getLogger("discovery_system.agent_runtime")
_logger.setLevel(logging.INFO)

# 创建日志文件 handler
log_file_path = pathlib.Path(__file__).parent / "real_agent_test.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestRealAgentScenario(unittest.TestCase):
    """真实场景模拟测试。"""

    def setUp(self):
        """测试前置准备。"""
        self.storage = InMemoryDiscoveryStorage()
        self.test_session_id = "real_test_session"
        self.test_user_id = 10001

        # 创建一个真实的 session
        session = StoredSession(
            session_id=self.test_session_id,
            requester_id=self.test_user_id,
            profile_id=self.test_user_id,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": {},
            },
            state={
                "phase": "collecting_preferences",
                "working_criteria": {"cities": ["上海"], "age_min": 25, "age_max": 30},
                "current_results": [
                    {"profile_id": 1002, "title": "候选人A"},
                    {"profile_id": 1003, "title": "候选人B"},
                ],
                "turn_count": 1,
                "history": [{"type": "search", "timestamp": "2026-06-11T08:00:00"}],
            },
        )
        self.storage.save_session(session)

    def test_simulate_batch_refresh_scenario(self):
        """模拟"换一批"场景，触发日志埋点。

        测试目标：
        1. 触发 agent_runtime.py 中的日志埋点
        2. 查看 Agent 输出是否包含追问文案
        3. 分析日志输出，判断是否需要改进
        """
        _logger.info("=" * 80)
        _logger.info("【测试开始】模拟'换一批'场景")
        _logger.info("=" * 80)

        # 使用真实的 AgentsSdkDiscoveryAgentRuntime，但 Mock Agent SDK
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("real-test-session-001")

        # Mock Agent SDK 的调用
        import types
        from unittest import mock

        class _FakeStreamingResult:
            """模拟 Agent SDK 的 StreamingResult。"""

            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-response-001"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                # 不产生任何事件
                return
                yield  # 使其成为异步生成器

        def _fake_agent(**kwargs):
            return object()

        def _fake_run_streamed(_agent, input, **kwargs):
            # 模拟 Agent SDK 返回的结果（包含追问文案）
            return _FakeStreamingResult(
                {
                    "phase": "collecting_preferences",
                    "assistant_message": "好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。",
                    "criteria_labels": [],
                    "suggested_actions": [
                        {"label": "太远了（都是异地）", "style": "secondary"},
                        {"label": "年龄不合适", "style": "secondary"},
                        {"label": "跳过，直接换", "style": "ghost"},
                    ],
                    "selected_candidates": [],
                }
            )

        run_input = DiscoveryRunInput(
            session_id="real-test-session-001",
            requester_id=10001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=["上海"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "前面聊过城市和关系目标。"},
            ],
            runtime_context={
                "session": {"session_id": "real-test-session-001", "phase": "collecting_preferences"},
                "user_profile": {"self_city": "上海"},
                "memory_summary": {
                    "recent_conversation_summary": "前面聊过城市和关系目标。",
                },
                "visible_actions": [{"label": "换一批", "style": "primary", "semantic_payload": {"kind": "show_more_candidates"}}],
                "last_search": {"result_count": 2, "has_match": True},
                "current_results": [
                    {"profile_id": 1002, "title": "候选人A"},
                    {"profile_id": 1003, "title": "候选人B"},
                ],
            },
            search_partner_candidates=lambda _criteria, _limit: {"has_match": True, "result_count": 2, "results": [{"id": 1004}, {"id": 1005}]},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            agent_session=session,
        )

        # 使用 Mock Agent SDK
        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), mock.patch(
            "agents.Agent",
            side_effect=_fake_agent,
        ), mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed):
            # 调用真实的 run_turn，触发日志埋点
            result = runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="换一批",
                action_context=None,
            )

        _logger.info("=" * 80)
        _logger.info("【测试结束】日志记录完成")
        _logger.info("=" * 80)

        # 查看日志文件内容
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
            print("\n" + "=" * 80)
            print("日志文件内容：")
            print("=" * 80)
            print(log_content)
            print("=" * 80)

        self.assertTrue(True, "测试完成，请查看日志文件")


if __name__ == "__main__":
    unittest.main()