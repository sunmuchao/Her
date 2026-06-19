"""测试方案C：支持多条消息（reply_to_user + show_candidates）"""

import unittest
from datetime import datetime
from unittest import mock

from discovery_system.agent_runtime import (
    DiscoveryDecision,
    DiscoveryRuntimeResult,
    DiscoveryCandidateSelection,
)
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession


class MultiplePayloadsRuntime:
    """模拟一个会调用 reply_to_user + show_candidates 的 Runtime"""

    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先说说你的基本要求。",
            )
        )

    def run_turn(self, _run_input, *, user_message=None, action_context=None):
        # 模拟 Agent 连续调用 reply_to_user + show_candidates
        reply_payload = {
            "kind": "reply",
            "phase": "results_shown",
            "assistant_message": "明白啦！你说自己性格比较闷，想找个外向活泼的女生来带动你～",
            "suggested_actions": [],
        }

        show_payload = {
            "kind": "show",
            "phase": "results_shown",
            "assistant_message": "根据你'性格外向'的偏好，我帮你筛选了这几位...",
            "result_group_title": "外向开朗的女生推荐",
            "selected_candidates": [
                {"profile_id": 1001, "reason_summary": ""},
                {"profile_id": 1002, "reason_summary": ""},
            ],
        }

        # 创建 decision，模拟方案C的处理（传入 _all_payloads）
        decision = DiscoveryDecision(
            phase="results_shown",
            assistant_message=show_payload["assistant_message"],
            result_group_title=show_payload["result_group_title"],
            selected_candidates=[
                DiscoveryCandidateSelection(profile_id=1001, reason_summary=""),
                DiscoveryCandidateSelection(profile_id=1002, reason_summary=""),
            ],
            _all_payloads=[reply_payload, show_payload],  # 方案C：直接传入
        )

        return DiscoveryRuntimeResult(
            decision=decision,
            search_response={
                "has_match": True,
                "result_count": 2,
                "results": [
                    {"id": 1001, "name": "张安萌", "profile": {"age": 27}},
                    {"id": 1002, "name": "陈以心", "profile": {"age": 30}},
                ],
            },
        )


class TestMultiplePayloadsSupport(unittest.TestCase):
    """测试方案C：支持多条消息"""

    def setUp(self):
        """每个测试前的准备工作"""
        self.storage = InMemoryDiscoveryStorage()
        self.session = StoredSession(
            session_id="test-multi-payloads",
            requester_id=10015,
            profile_id=10015,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={"timeline": [], "criteria_chips": [], "suggested_actions": []},
            state={},
        )
        self.storage.save_session(self.session)

    def test_service_handles_multiple_payloads_correctly(self):
        """测试：Service 层正确处理多个 payload"""
        service = DiscoveryService(
            storage=self.storage,
            runtime=MultiplePayloadsRuntime(),
        )

        # 用户发送消息
        result = service.process_turn(
            session_id=self.session.session_id,
            user_message_text="我想找性格外向的",
        )

        # 刷新 session
        updated_session = self.storage.get_session(self.session.session_id)
        assert updated_session is not None

        # 验证 timeline
        timeline = updated_session.view.get("timeline") or []
        assistant_messages = [
            item for item in timeline if item.get("item_type") == "assistant_message"
        ]

        # ✅ 应该有 2 条 assistant_message（reply + show）
        self.assertEqual(len(assistant_messages), 2)

        # ✅ 第一条消息应该是 reply_to_user 的内容
        first_message = assistant_messages[0].get("body") or ""
        self.assertIn("明白啦", first_message)
        self.assertIn("性格比较闷", first_message)

        # ✅ 第二条消息应该是 show_candidates 的内容
        second_message = assistant_messages[1].get("body") or ""
        self.assertIn("根据你", second_message)
        self.assertIn("性格外向", second_message)

        # ✅ 应该有候选人卡片
        result_groups = [
            item for item in timeline if item.get("item_type") == "result_group"
        ]
        self.assertEqual(len(result_groups), 1)
        self.assertEqual(
            result_groups[0].get("title"), "外向开朗的女生推荐"
        )

    def test_service_handles_single_payload_correctly(self):
        """测试：Service 层仍然正确处理单个 payload（确保向后兼容）"""
        # 复制 _FakeRuntime 的定义（避免导入问题）
        class _SinglePayloadRuntime:
            def initial_decision(self, _run_input):
                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="collecting_preferences",
                        assistant_message="先说说你的基本要求。",
                    )
                )

            def run_turn(self, _run_input, *, user_message=None, action_context=None):
                # 单个 payload：只有 show_candidates
                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="results_shown",
                        assistant_message="我先给你看一位比较贴近的。",
                        criteria_labels=["无锡", "认真恋爱"],
                        result_group_title="这一轮先给你看 1 位",
                        selected_candidates=[
                            DiscoveryCandidateSelection(
                                profile_id=1001,
                                reason_summary="城市一致、关系目标一致",
                            )
                        ],
                        _all_payloads=None,  # 单个 payload，不传 _all_payloads
                    ),
                    search_response={
                        "has_match": True,
                        "result_count": 1,
                        "results": [
                            {
                                "id": 1001,
                                "name": "林知夏",
                                "profile": {"age": 29, "city": "无锡"},
                            }
                        ],
                    },
                )

        service = DiscoveryService(
            storage=self.storage,
            runtime=_SinglePayloadRuntime(),
        )

        # 用户发送消息
        result = service.process_turn(
            session_id=self.session.session_id,
            user_message_text="我想找对象",
        )

        # 刷新 session
        updated_session = self.storage.get_session(self.session.session_id)
        assert updated_session is not None

        # 验证 timeline
        timeline = updated_session.view.get("timeline") or []
        assistant_messages = [
            item for item in timeline if item.get("item_type") == "assistant_message"
        ]

        # ✅ 单个 payload：应该只有 1 条 assistant_message
        self.assertEqual(len(assistant_messages), 1)

        # ✅ 消息内容应该是 decision.assistant_message
        message = assistant_messages[0].get("body") or ""
        self.assertIn("先给你看一位", message)

    def test_multiple_payloads_preserve_order(self):
        """测试：多条消息的顺序正确（reply → show → 候选人卡片）"""
        service = DiscoveryService(
            storage=self.storage,
            runtime=MultiplePayloadsRuntime(),
        )

        # 用户发送消息
        result = service.process_turn(
            session_id=self.session.session_id,
            user_message_text="我想找性格外向的",
        )

        # 刷新 session
        updated_session = self.storage.get_session(self.session.session_id)
        assert updated_session is not None

        # 验证 timeline 顺序
        timeline = updated_session.view.get("timeline") or []

        # 找到各类型 item 的索引
        item_types = [item.get("item_type") for item in timeline]

        # ✅ 顺序应该是：user_message → assistant_message(reply) → assistant_message(show) → result_group
        expected_sequence = [
            "user_message",
            "assistant_message",  # reply_to_user
            "assistant_message",  # show_candidates
            "result_group",       # 候选人卡片
        ]

        # 提取关键类型的序列
        actual_sequence = [
            t for t in item_types if t in ["user_message", "assistant_message", "result_group"]
        ]

        self.assertEqual(actual_sequence, expected_sequence)


if __name__ == "__main__":
    unittest.main()