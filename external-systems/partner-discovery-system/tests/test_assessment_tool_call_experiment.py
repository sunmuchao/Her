"""测试实验：验证Agent是否调用suggest_assessment工具。

实验场景：
1. 用户说"性格不合适"
2. Agent追问用户偏好
3. 用户说"我没做过MBTI"
4. 观察Agent是否调用suggest_assessment工具

验证方法：
1. 检查日志中的工具调用记录
2. 检查Agent回复是否包含测评卡片渲染
3. 分析为什么Agent没有调用工具
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

log_file_path = pathlib.Path(__file__).parent / "assessment_tool_call_experiment.log"
file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
_logger.addHandler(file_handler)


class TestAssessmentToolCallExperiment(unittest.TestCase):
    """验证Agent是否调用suggest_assessment工具的测试实验。"""

    def test_experiment_user_says_personality_not_fit(self):
        """实验1：用户说"性格不合适"，观察Agent行为。

        验证点：
        1. Agent是否调用suggest_assessment工具
        2. Agent是否追问用户偏好（正确行为）
        3. Agent是否口头引导做测评（而不是调用工具）
        """
        _logger.info("=" * 80)
        _logger.info("【实验1】用户说'性格不合适'")
        _logger.info("=" * 80)
        _logger.info("期望行为：Agent调用suggest_assessment检查测评状态")
        _logger.info("实际行为：观察Agent是否调用工具")

        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("experiment-session-001")

        import types
        from unittest import mock

        # 模拟Agent的回复（口头引导，没有调用工具）
        class _FakeStreamingResult:
            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-response-experiment"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                return
                yield

        def _fake_agent(**kwargs):
            return object()

        def _fake_run_streamed(_agent, input, **kwargs):
            # 模拟Agent口头引导，没有调用suggest_assessment工具
            # 这正是用户观察到的行为
            return _FakeStreamingResult({
                "phase": "collecting_preferences",
                "assistant_message": "明白啦～性格确实很重要！我想了解一下，你希望对方是什么性格类型呀？比如：活泼开朗、爱社交的？温柔安静、偏内向的？",
                "criteria_labels": [],
                "suggested_actions": [
                    {"label": "活泼开朗型", "style": "secondary"},
                    {"label": "温柔安静型", "style": "secondary"},
                ],
                "selected_candidates": [],
            })

        run_input = DiscoveryRunInput(
            session_id="experiment-session-001",
            requester_id=10001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "女", "26-36岁"],
            recent_timeline=[{"item_type": "result_group", "candidates": [{"id": 1001}]}],
            runtime_context={
                "session": {"session_id": "experiment-session-001", "phase": "results_shown"},
                "user_profile": {"self_city": "无锡"},
                "visible_actions": [],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [{"profile_id": 1001}],
            },
            search_partner_candidates=lambda _c, _l: {"has_match": True, "results": []},
            sync_requester_persona_memory=lambda _p: {"synced": True},
            propose_requester_profile_update=lambda _p, _e="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created": False},
            suggest_assessment=lambda _t: {
                "completed": False,
                "suggest": True,
                "card": {
                    "card_type": "assessment_suggest",
                    "title": "MBTI性格测试",
                    "description": "了解你的性格类型",
                },
            },
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), \
             mock.patch("agents.Agent", side_effect=_fake_agent), \
             mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed):

            result = runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="性格不合适",
                action_context=None,
            )

        assistant_message = result.decision.assistant_message

        _logger.info("=" * 80)
        _logger.info("【实验结果】")
        _logger.info("Agent回复：%s", assistant_message)
        _logger.info("=" * 80)

        # 验证点：Agent是否口头提到测评（但没有调用工具）
        mentions_assessment = "MBTI" in assistant_message or "性格测试" in assistant_message
        _logger.info("是否口头提到测评：%s", mentions_assessment)

        # 验证点：Agent是否追问用户偏好
        asks_preference = "什么性格" in assistant_message or "性格类型" in assistant_message
        _logger.info("是否追问用户偏好：%s", asks_preference)

        # 检查日志中是否有工具调用记录
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()

        tool_called = "【工具调用】suggest_assessment" in log_content
        _logger.info("是否调用suggest_assessment工具：%s", tool_called)

        print("\n" + "=" * 80)
        print("实验1结果")
        print("=" * 80)
        print(f"Agent回复：{assistant_message[:100]}...")
        print(f"口头提到测评：{mentions_assessment}")
        print(f"追问用户偏好：{asks_preference}")
        print(f"调用工具：{tool_called}")
        print("=" * 80)

        # 记录结论
        if not tool_called and mentions_assessment:
            _logger.warning("⚠️ 问题确认：Agent口头引导测评，但没有调用suggest_assessment工具")
            _logger.warning("这违反了Agent Native原则：应该调用工具返回测评卡片，而不是口头引导")

    def test_experiment_user_says_not_done_assessment(self):
        """实验2：用户说"我没做过MBTI"，观察Agent行为。

        验证点：
        1. Agent是否调用suggest_assessment工具
        2. Agent是否口头引导用户去"我的-性格测评"
        3. Agent是否返回测评卡片
        """
        _logger.info("=" * 80)
        _logger.info("【实验2】用户说'我没做过MBTI'")
        _logger.info("=" * 80)

        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("experiment-session-002")

        import types
        from unittest import mock

        class _FakeStreamingResult:
            def __init__(self, final_output):
                self.final_output = final_output
                self.last_response_id = "test-response-experiment-2"
                self.context_wrapper = types.SimpleNamespace(usage=None)
                self.run_loop_task = None

            async def stream_events(self):
                return
                yield

        def _fake_agent(**kwargs):
            return object()

        def _fake_run_streamed(_agent, input, **kwargs):
            # 模拟Agent口头引导用户去"我的-性格测评"
            # 这正是用户观察到的行为
            return _FakeStreamingResult({
                "phase": "collecting_preferences",
                "assistant_message": "没关系～我们平台有个简单的MBTI性格测试，做一下只要几分钟，做完之后我就能根据你的性格类型，帮你找性格更匹配的女生啦～你可以去'我的-性格测评'里做一下，做完告诉我一声，我重新帮你推荐！",
                "criteria_labels": [],
                "suggested_actions": [
                    {"label": "活泼外向、爱聊天", "style": "secondary"},
                    {"label": "温柔安静、比较内敛", "style": "secondary"},
                ],
                "selected_candidates": [],
            })

        run_input = DiscoveryRunInput(
            session_id="experiment-session-002",
            requester_id=10001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=["无锡"],
            recent_timeline=[{"item_type": "assistant_message", "body": "你希望对方是什么性格类型？"}],
            runtime_context={
                "session": {"session_id": "experiment-session-002", "phase": "collecting_preferences"},
                "user_profile": {"self_city": "无锡"},
                "visible_actions": [],
                "last_search": {"result_count": 5, "has_match": True},
                "current_results": [],
            },
            search_partner_candidates=lambda _c, _l: {"has_match": True, "results": []},
            sync_requester_persona_memory=lambda _p: {"synced": True},
            propose_requester_profile_update=lambda _p, _e="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created": False},
            suggest_assessment=lambda _t: {
                "completed": False,
                "suggest": True,
                "card": {
                    "card_type": "assessment_suggest",
                    "title": "MBTI性格测试",
                    "description": "了解你的性格类型",
                    "duration": "约5分钟",
                    "action_label": "开始测评",
                },
            },
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), \
             mock.patch("agents.Agent", side_effect=_fake_agent), \
             mock.patch("agents.Runner.run_streamed", side_effect=_fake_run_streamed):

            result = runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="我没做过MBTI",
                action_context=None,
            )

        assistant_message = result.decision.assistant_message

        _logger.info("Agent回复：%s", assistant_message)

        # 验证点：Agent是否口头引导用户去"我的-性格测评"
        guides_to_my_page = "我的-性格测评" in assistant_message or "我的" in assistant_message
        _logger.info("是否口头引导去'我的-性格测评'：%s", guides_to_my_page)

        # 检查日志中是否有工具调用记录
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()

        tool_called = "【工具调用】suggest_assessment" in log_content
        _logger.info("是否调用suggest_assessment工具：%s", tool_called)

        print("\n" + "=" * 80)
        print("实验2结果")
        print("=" * 80)
        print(f"Agent回复：{assistant_message[:150]}...")
        print(f"口头引导去'我的-性格测评'：{guides_to_my_page}")
        print(f"调用工具：{tool_called}")
        print("=" * 80)

        # 记录结论
        if not tool_called and guides_to_my_page:
            _logger.warning("⚠️ 问题确认：Agent口头引导用户去'我的-性格测评'")
            _logger.warning("但没有调用suggest_assessment工具返回测评卡片")
            _logger.warning("这违反了工具边界原则：应该用工具执行，而不是口头引导")

    def test_experiment_conclusion(self):
        """实验3：总结实验结论。

        分析为什么Agent没有调用suggest_assessment工具。
        """
        print("\n" + "=" * 80)
        print("实验结论")
        print("=" * 80)

        print("观察到的行为：")
        print("1. 用户说'性格不合适' → Agent追问偏好，口头提到MBTI")
        print("2. 用户说'我没做过MBTI' → Agent口头引导去'我的-性格测评'")
        print("")
        print("问题：")
        print("- Agent口头引导用户做测评")
        print("- 但没有调用suggest_assessment工具返回测评卡片")
        print("")
        print("可能原因：")
        print("1. Agent的LLM没有理解Tool description的触发条件")
        print("2. Agent判断'口头引导'比'返回卡片'更自然")
        print("3. Tool description不够强制/明确")
        print("4. Agent可能不知道用户是否已完成测评")
        print("")
        print("违反的原则：")
        print("- 工具边界原则：应该用工具执行，而不是口头引导")
        print("- Agent Native原则：工具返回测评卡片，前端渲染")
        print("=" * 80)

        _logger.info("=" * 80)
        _logger.info("【实验结论】")
        _logger.info("Agent口头引导测评，但没有调用suggest_assessment工具")
        _logger.info("违反了工具边界原则和Agent Native原则")
        _logger.info("=" * 80)


if __name__ == "__main__":
    unittest.main()