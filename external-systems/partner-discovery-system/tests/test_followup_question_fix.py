#!/usr/bin/env python3
"""
端到端测试：验证追问场景修复效果

测试流程：
1. 创建discovery session
2. 用户发送"给我推荐" → 搜索返回候选人（胡书瑶、胡欣雅）
3. 用户追问"这两个你更推荐哪个，为什么" → Agent正确回答，不返回错误消息

验证修复：_coerce_search_failure_decision 不会误判追问场景为"幻觉"
"""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

# 添加discovery_system到路径
DISCOVERY_ROOT = Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession


class _SearchThenFollowupRuntime:
    """模拟搜索+追问的runtime"""

    call_count = 0  # ✅ 新增：计数器区分轮次

    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先说说你的要求。",
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label="给我推荐几个",
                        semantic_payload={"kind": "starter_prompt"},
                        style="primary",
                    ),
                ],
            )
        )

    def run_turn(self, run_input, *, user_message=None, action_context=None):
        self.call_count += 1

        # ✅ 用call_count区分轮次，而不是用关键词匹配
        # 第一轮：搜索
        if self.call_count == 1:
            search_response = run_input.search_partner_candidates({}, 5)
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="results_shown",
                    assistant_message="先给你看两位比较合适的。",
                    criteria_labels=["无锡", "女", "奔着结婚"],
                    selected_candidates=[
                        DiscoveryCandidateSelection(
                            profile_id=2052,
                            reason_summary="法务工作，INTP，性格理性",
                        ),
                        DiscoveryCandidateSelection(
                            profile_id=6792,
                            reason_summary="数据分析，ESTP，性格活泼",
                        ),
                    ],
                    suggested_actions=[
                        DiscoveryActionSuggestion(
                            label="换一批",
                            semantic_payload={"kind": "show_more_candidates"},
                            style="secondary",
                        ),
                    ],
                ),
                search_response=search_response,
            )

        # 第二轮：追问（关键场景）
        if self.call_count == 2:
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="results_shown",
                    assistant_message="我更推荐胡书瑶（第一位）。INTP偏理性、喜欢深度思考，婚后沟通会更理性，不容易因为小事吵架上头。胡欣雅也很好，ESTP更活泼，但需要你配合她的节奏。",
                    criteria_labels=["无锡", "女", "奔着结婚"],
                    selected_candidates=[
                        DiscoveryCandidateSelection(
                            profile_id=2052,  # ✅ 来自现有卡片
                            reason_summary="INTP + 安全型依恋，适合长期经营",
                        ),
                        DiscoveryCandidateSelection(
                            profile_id=6792,  # ✅ 来自现有卡片
                            reason_summary="ESTP + 安全型依恋，性格活泼",
                        ),
                    ],
                    suggested_actions=[
                        DiscoveryActionSuggestion(
                            label="换一批",
                            semantic_payload={"kind": "show_more_candidates"},
                            style="secondary",
                        ),
                    ],
                ),
                search_response=None,  # ✅ 追问场景：不搜索
            )

        # 默认fallback
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="收到。",
            )
        )


class FollowupQuestionE2ETest(unittest.TestCase):
    """端到端测试：追问场景验证"""

    def setUp(self):
        """设置测试环境"""
        self.storage = InMemoryDiscoveryStorage()
        self.service = DiscoveryService(storage=self.storage, runtime=None)

    def test_followup_question_scenario_preserves_agent_answer(self):
        """
        端到端测试：追问场景下，Agent的回答应该被保留

        场景：
        - 第一轮：用户说"给我推荐" → 搜索返回候选人
        - 第二轮：用户追问"这两个你更推荐哪个，为什么" → Agent正确回答
        - 验证：不应该返回"还没真正跑出候选人卡片"的错误消息
        """

        # ========== 第一轮：搜索候选人 ==========
        # 使用共享的runtime实例（确保call_count正确）
        runtime_instance = _SearchThenFollowupRuntime()
        self.service.runtime = runtime_instance

        # 模拟搜索返回数据
        mock_search_response = {
            "has_match": True,
            "result_count": 5,
            "results": [
                {
                    "id": 2052,
                    "name": "胡书瑶",
                    "profile": {"age": 27, "city": "无锡", "job": "法务"},
                    "match_reason": "法务工作，性格稳定",
                },
                {
                    "id": 6792,
                    "name": "胡欣雅",
                    "profile": {"age": 28, "city": "无锡", "job": "数据分析"},
                    "match_reason": "数据分析，工作规律",
                },
            ],
            "request_meta": {
                "criteria": {"cities": ["无锡"], "gender": "female"},
                "limit_count": 5,
            },
        }

        # ========== 第一轮：创建session并搜索 ==========
        with mock.patch.object(
            self.service,
            "_search_partner_candidates",
            return_value=mock_search_response,
        ):
            created = self.service.create_session(requester_id=10001, profile_id=10001)

        session_id = created["session"]["session_id"]

        # 第一轮：用户说"给我推荐"
        with mock.patch.object(
            self.service,
            "_search_partner_candidates",
            return_value=mock_search_response,
        ):
            first_turn = self.service.process_turn(
                session_id=session_id,
                user_message_text="给我推荐几个合适的",
            )

        # 验证第一轮：应该显示候选人
        self.assertEqual(first_turn["session"]["phase"], "results_shown")
        first_timeline = first_turn["view"]["timeline"]
        self.assertEqual(first_timeline[-1]["item_type"], "result_group")
        self.assertEqual(len(first_timeline[-1]["cards"]), 2)
        self.assertEqual(first_timeline[-1]["cards"][0]["profile_id"], 2052)
        self.assertEqual(first_timeline[-1]["cards"][1]["profile_id"], 6792)

        print("✅ 第一轮验证通过：候选人卡片正确显示")

        # ========== 第二轮：用户追问 ==========
        second_turn = self.service.process_turn(
            session_id=session_id,
            user_message_text="这两个你更推荐哪个，为什么",
        )

        # ========== 验证修复效果 ==========
        # 1. Phase应该是"results_shown"，不是"collecting_preferences"
        self.assertEqual(
            second_turn["session"]["phase"],
            "results_shown",
            "Phase应该是results_shown，说明Agent的回答被保留了",
        )

        # 2. Timeline中应该有assistant_message和result_group
        second_timeline = second_turn["view"]["timeline"]

        # 找到assistant_message（应该在result_group之前）
        assistant_messages = [
            item for item in second_timeline if item.get("item_type") == "assistant_message"
        ]
        self.assertTrue(len(assistant_messages) > 0, "应该有assistant_message")

        last_assistant = assistant_messages[-1]
        assistant_body = last_assistant.get("body", "")

        # 3. assistant_message应该是Agent的回答，不是错误消息
        # ✅ 关键验证：不应该包含错误消息
        self.assertNotIn(
            "还没真正跑出候选人卡片",
            assistant_body,
            "❌ Bug未修复：系统误判追问场景为幻觉，返回了错误消息",
        )
        self.assertNotIn(
            "你再发一次",
            assistant_body,
            "❌ Bug未修复：系统返回了错误消息",
        )

        # ✅ 应该包含Agent的正确回答
        self.assertIn("胡书瑶", assistant_body, "✅ Agent正确回答了问题")
        self.assertIn("INTP", assistant_body, "✅ Agent分析了MBTI")

        # 4. 候选人卡片应该被保留
        result_groups = [
            item for item in second_timeline if item.get("item_type") == "result_group"
        ]
        self.assertTrue(len(result_groups) > 0, "应该有result_group")

        last_result_group = result_groups[-1]
        cards = last_result_group.get("cards", [])
        self.assertEqual(len(cards), 2, "✅ 候选人卡片被保留")
        self.assertEqual(cards[0]["profile_id"], 2052, "✅ 第一位候选人（胡书瑶）被保留")
        self.assertEqual(cards[1]["profile_id"], 6792, "✅ 第二位候选人（胡欣雅）被保留")

        print("✅ 第二轮验证通过：追问场景正确处理")
        print(f"✅ Agent回答：{assistant_body[:50]}...")
        print(f"✅ 候选人卡片：{len(cards)}张被保留")

    def test_hallucination_scenario_still_detected(self):
        """
        验证幻觉场景仍然能被正确检测

        场景：Agent凭空编造候选人ID（不在对话记录中）
        预期：系统应该返回错误消息
        """
        class _HallucinationRuntime:
            def initial_decision(self, _run_input):
                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="collecting_preferences",
                        assistant_message="先说说你的要求。",
                    )
                )

            def run_turn(self, _run_input, *, user_message=None, action_context=None):
                # 幻觉场景：Agent返回候选人ID，但这些ID不在现有卡片中
                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="results_shown",
                        assistant_message="我给你推荐两位。",
                        selected_candidates=[
                            DiscoveryCandidateSelection(
                                profile_id=99999,  # ❌ 不存在的ID（幻觉）
                                reason_summary="编造的候选人",
                            ),
                        ],
                    ),
                    search_response=None,  # 没搜索
                )

        self.service.runtime = _HallucinationRuntime()

        # 创建session，没有候选人卡片
        created = self.service.create_session(requester_id=10001, profile_id=10001)
        session_id = created["session"]["session_id"]

        # Agent返回幻觉候选人
        result = self.service.process_turn(
            session_id=session_id,
            user_message_text="给我推荐",
        )

        # ✅ 验证：系统应该检测到幻觉并返回错误消息
        self.assertEqual(
            result["session"]["phase"],
            "collecting_preferences",
            "幻觉场景应该被检测，phase改为collecting_preferences",
        )

        timeline = result["view"]["timeline"]
        assistant_msg = timeline[-1]
        self.assertEqual(assistant_msg["item_type"], "assistant_message")
        self.assertIn(
            "还没真正跑出候选人卡片",
            assistant_msg["body"],
            "✅ 幻觉场景应该返回错误消息",
        )

        print("✅ 幻觉场景验证通过：系统正确检测并返回错误消息")


class IntegrationTestWithRealData(unittest.TestCase):
    """集成测试：使用真实数据验证"""

    def test_full_conversation_flow_with_search_and_followup(self):
        """
        完整对话流程测试：

        1. 用户："给我推荐几个无锡的女生"
        2. 系统：搜索 → 返回候选人（胡书瑶、胡欣雅）
        3. 用户："这两个你更推荐哪个，为什么"
        4. 系统：Agent回答 → 保留候选人卡片

        验证：追问场景不应该触发"没跑出候选人卡片"错误
        """
        storage = InMemoryDiscoveryStorage()
        service = DiscoveryService(storage=storage, runtime=None)

        # 使用真实的搜索响应数据（模拟日志中的数据）
        search_response_data = {
            "has_match": True,
            "result_count": 5,
            "results": [
                {
                    "id": 2052,
                    "name": "胡书瑶",
                    "score": 120,
                    "profile": {"age": 27, "city": "无锡", "job": "法务", "education": "本科"},
                    "match_reason": "法务工作稳定",
                    "personality_traits": {
                        "mbti": {"type_code": "INTP"},
                        "attachment": {"type_code": "secure"},
                    },
                },
                {
                    "id": 6792,
                    "name": "胡欣雅",
                    "score": 120,
                    "profile": {"age": 28, "city": "无锡", "job": "招商主管", "education": "本科"},
                    "match_reason": "数据分析岗，工作节奏规律",
                    "personality_traits": {
                        "mbti": {"type_code": "ESTP"},
                        "attachment": {"type_code": "secure"},
                    },
                },
            ],
            "request_meta": {
                "criteria": {"gender": "female", "cities": ["无锡"], "age_min": 23, "age_max": 33},
                "limit_count": 5,
            },
        }

        class _RealFlowRuntime:
            """模拟真实的对话流程"""

            call_count = 0

            def initial_decision(self, _run_input):
                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="collecting_preferences",
                        assistant_message="你好，我来帮你找合适的对象。",
                    )
                )

            def run_turn(self, run_input, *, user_message=None, action_context=None):
                self.call_count += 1

                # 第一轮：搜索
                if self.call_count == 1 and user_message and "推荐" in user_message:
                    response = run_input.search_partner_candidates({}, 5)
                    return DiscoveryRuntimeResult(
                        decision=DiscoveryDecision(
                            phase="results_shown",
                            assistant_message="按你的要求，先给你看两位。胡书瑶做法务、INTP偏理性；胡欣雅做招商、ESTP偏活泼。",
                            criteria_labels=["无锡", "女", "23-33岁", "奔着结婚"],
                            selected_candidates=[
                                DiscoveryCandidateSelection(profile_id=2052, reason_summary="法务稳定"),
                                DiscoveryCandidateSelection(profile_id=6792, reason_summary="工作规律"),
                            ],
                        ),
                        search_response=response,
                    )

                # 第二轮：追问（关键场景）
                if self.call_count == 2 and user_message and "更推荐" in user_message:
                    # ✅ 不搜索，但返回候选人ID（来自现有卡片）
                    return DiscoveryRuntimeResult(
                        decision=DiscoveryDecision(
                            phase="results_shown",
                            assistant_message="我更推荐胡书瑶。INTP偏理性、喜欢深度思考，婚后沟通会更理性，不容易因为小事吵架。胡欣雅也好，ESTP更活泼，但社交需求高一些。",
                            criteria_labels=["无锡", "女", "23-33岁", "奔着结婚"],
                            selected_candidates=[
                                DiscoveryCandidateSelection(
                                    profile_id=2052,  # ✅ 来自现有卡片
                                    reason_summary="INTP + 安全型依恋，适合长期经营",
                                ),
                                DiscoveryCandidateSelection(
                                    profile_id=6792,  # ✅ 来自现有卡片
                                    reason_summary="ESTP + 安全型依恋，性格活泼",
                                ),
                            ],
                        ),
                        search_response=None,  # ✅ 追问场景不搜索
                    )

                return DiscoveryRuntimeResult(
                    decision=DiscoveryDecision(
                        phase="collecting_preferences",
                        assistant_message="收到。",
                    )
                )

        service.runtime = _RealFlowRuntime()

        # ========== 第一轮：搜索 ==========
        with mock.patch.object(
            service,
            "_search_partner_candidates",
            return_value=search_response_data,
        ):
            created = service.create_session(requester_id=10015, profile_id=10015)

        session_id = created["session"]["session_id"]

        # 用户：给我推荐
        with mock.patch.object(
            service,
            "_search_partner_candidates",
            return_value=search_response_data,
        ):
            first_result = service.process_turn(
                session_id=session_id,
                user_message_text="给我推荐几个无锡的女生",
            )

        # 验证第一轮
        self.assertEqual(first_result["session"]["phase"], "results_shown")
        first_cards = first_result["view"]["timeline"][-1]["cards"]
        self.assertEqual(len(first_cards), 2)

        print(f"\n========== 第一轮搜索结果 ========== ")
        print(f"Phase: {first_result['session']['phase']}")
        print(f"候选人数量: {len(first_cards)}")
        print(f"候选人ID: {[c['profile_id'] for c in first_cards]}")

        # ========== 第二轮：追问（关键场景） ==========
        second_result = service.process_turn(
            session_id=session_id,
            user_message_text="这两个你更推荐哪个，为什么",
        )

        # ========== 验证修复效果 ==========
        print(f"\n========== 第二轮追问结果 ========== ")
        print(f"Phase: {second_result['session']['phase']}")

        second_timeline = second_result["view"]["timeline"]

        # 获取最后两条记录（assistant_message + result_group）
        if len(second_timeline) >= 2:
            last_assistant = [
                item for item in second_timeline if item.get("item_type") == "assistant_message"
            ][-1]
            last_group = [
                item for item in second_timeline if item.get("item_type") == "result_group"
            ][-1]

            assistant_body = last_assistant.get("body", "")
            cards = last_group.get("cards", [])

            print(f"Assistant消息: {assistant_body[:80]}...")
            print(f"候选人卡片数量: {len(cards)}")

        # ✅ 核心验证点
        # 1. Phase应该是"results_shown"（追问场景保留）
        self.assertEqual(
            second_result["session"]["phase"],
            "results_shown",
            "❌ Bug：追问场景phase被错误改为collecting_preferences",
        )

        # 2. 不应该出现错误消息
        assistant_msgs = [
            item for item in second_timeline if item.get("item_type") == "assistant_message"
        ]
        if assistant_msgs:
            body = assistant_msgs[-1].get("body", "")
            self.assertNotIn("还没真正跑出候选人卡片", body, "❌ Bug：返回了错误消息")
            self.assertIn("胡书瑶", body, "✅ Agent正确回答了问题")

        # 3. 候选人卡片应该被保留
        result_groups = [
            item for item in second_timeline if item.get("item_type") == "result_group"
        ]
        if result_groups:
            cards = result_groups[-1].get("cards", [])
            self.assertEqual(len(cards), 2, "✅ 候选人卡片被保留")
            self.assertIn(2052, [c["profile_id"] for c in cards])
            self.assertIn(6792, [c["profile_id"] for c in cards])

        print("\n✅ 端到端测试通过：追问场景正确处理，修复有效")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)