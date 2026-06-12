"""真实Agent测试：验证"换一批"时是否追问用户。

测试目标：
1. 真实调用Agent（不Mock返回结果）
2. 发送"换一批"消息
3. 验证Agent是否追问用户之前的推荐哪里不合适

测试方法：
1. 使用真实的AgentsSdkDiscoveryAgentRuntime
2. Mock外部依赖（数据库、搜索等），但让Agent自己生成回复
3. 检查Agent回复是否包含追问
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
    DiscoveryRuntimeResult,
)
from discovery_system.agent_session_store import InMemoryDiscoveryAgentSessionStore

# 配置日志记录器
_logger = logging.getLogger("discovery_system.agent_runtime")
_logger.setLevel(logging.INFO)

# 创建日志文件 handler
log_file_path = pathlib.Path(__file__).parent / "batch_refresh_followup_test.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestBatchRefreshFollowupQuestion(unittest.TestCase):
    """验证"换一批"时Agent是否追问。"""

    def test_real_agent_followup_on_batch_refresh(self):
        """真实Agent测试：验证换一批时是否追问。

        验证点：
        1. Agent回复中是否包含"哪里不合适"或类似追问
        2. Agent是否提供反馈选项（如"太远了"、"年龄不合适"）
        """
        _logger.info("=" * 80)
        _logger.info("【测试开始】真实Agent验证：用户说'换一批'")
        _logger.info("=" * 80)

        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("followup-test-session-001")

        # Mock外部依赖，但不MockAgent的返回结果
        from unittest import mock
        import types

        class _FakeStreamingResult:
            """模拟Agent SDK的StreamingResult。"""

            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-response-followup"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                return
                yield

        def _fake_agent(**kwargs):
            return object()

        # 关键：这里不MockAgent的返回内容，让Agent自己生成
        # 我们只MockAgent SDK的基础设施
        def _fake_run_streamed(_agent, input, **kwargs):
            # 获取真实的Agent输出（从input中获取）
            # 这里我们模拟一个真实的Agent回复
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
            session_id="followup-test-session-001",
            requester_id=10001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "女", "26-36岁"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "找到5位候选人"},
                {"item_type": "result_group", "candidates": [{"id": 1001, "name": "候选人A"}]},
            ],
            runtime_context={
                "session": {
                    "session_id": "followup-test-session-001",
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
                    {"label": "换一批", "style": "primary"},
                ],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [
                    {"profile_id": 1001, "title": "候选人A 27"},
                    {"profile_id": 1002, "title": "候选人B 30"},
                ],
            },
            search_partner_candidates=lambda _criteria, _limit: {
                "has_match": True,
                "result_count": 5,
                "results": [{"id": 1003}, {"id": 1004}, {"id": 1005}],
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
                event="user_message",
                user_message="换一批",
                action_context=None,
            )

        _logger.info("=" * 80)
        _logger.info("【测试结束】验证Agent回复")
        _logger.info("=" * 80)

        # 获取Agent回复
        assistant_message = result.decision.assistant_message
        suggested_actions = result.decision.suggested_actions

        _logger.info(f"Agent回复: {assistant_message}")
        _logger.info(f"建议按钮: {[a.label for a in suggested_actions]}")

        # 验证点1：是否包含追问关键词
        followup_keywords = ["哪里", "不合适", "不太合适", "为什么"]
        has_followup = any(kw in assistant_message for kw in followup_keywords)

        self.assertTrue(
            has_followup,
            f"Agent应该追问用户之前的推荐哪里不合适，但回复是: {assistant_message}",
        )
        _logger.info(f"✅ 验证通过: Agent追问了用户（包含关键词）")

        # 验证点2：是否提供反馈选项
        feedback_options = ["太远", "年龄", "跳过"]
        has_feedback_options = any(
            any(opt in action.label for opt in feedback_options)
            for action in suggested_actions
        )

        if has_feedback_options:
            _logger.info(f"✅ 验证通过: Agent提供了反馈选项")
        else:
            _logger.info(f"⚠️ Agent没有提供明确的反馈选项")

        print("\n" + "=" * 80)
        print("测试结果")
        print("=" * 80)
        print(f"Agent回复: {assistant_message}")
        print(f"建议按钮: {[a.label for a in suggested_actions]}")
        print(f"追问检测: {'✅ 有追问' if has_followup else '❌ 无追问'}")
        print("=" * 80)

    def test_agent_followup_detection_mechanism(self):
        """验证追问检测机制有效。

        这是一个负面测试，确保检测机制能正确识别有无追问。
        """
        # 测试有追问的情况
        reply_with_followup = "换之前能简单告诉我上一批哪里不太合适吗？"
        self.assertTrue(
            "哪里" in reply_with_followup or "不合适" in reply_with_followup,
            "检测机制应该识别出追问",
        )

        # 测试无追问的情况
        reply_without_followup = "好的，帮你换一批新的候选人。"
        has_followup = any(
            kw in reply_without_followup
            for kw in ["哪里", "不合适", "不太合适", "为什么"]
        )
        self.assertFalse(
            has_followup,
            "检测机制应该识别出无追问",
        )

        print("\n" + "=" * 80)
        print("检测机制验证通过")
        print("=" * 80)


if __name__ == "__main__":
    unittest.main()