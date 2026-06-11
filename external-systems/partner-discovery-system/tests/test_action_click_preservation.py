#!/usr/bin/env python3
"""
端到端测试：验证按钮点击后保留在历史对话中

测试场景：
1. AI推荐候选人，显示"换一批"按钮
2. 用户点击"换一批"
3. Timeline显示：AI消息 → "[换一批]"（用户点击） → AI追问

验证：用户能看到自己点击了什么按钮
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest import mock

DISCOVERY_ROOT = Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)
from discovery_system.service import DiscoveryService
from discovery_system.storage import InMemoryDiscoveryStorage, StoredSession


def test_action_click_preserved_in_timeline():
    """
    测试：用户点击按钮后，按钮文本作为历史消息保留在timeline中
    """
    storage = InMemoryDiscoveryStorage()
    service = DiscoveryService(storage=storage, runtime=None)

    # 手动创建session和按钮（模拟真实场景）
    session = StoredSession(
        session_id="test-session-001",
        requester_id=10001,
        profile_id=10001,
        status="active",
        phase="results_shown",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        view={
            "timeline": [
                {
                    "item_type": "assistant_message",
                    "item_id": "msg-001",
                    "body": "为你推荐两位候选人：胡书瑶、胡欣雅",
                }
            ]
        },
        state={},
    )
    storage.save_session(session)

    # 创建按钮
    action = storage.create_action(
        session_id="test-session-001",
        label="换一批",
        style="secondary",
        semantic_payload={"kind": "show_more_candidates"},
        now=datetime.now(),
    )

    # 设置按钮为可见
    session.visible_action_ids = [action.action_id]
    session.view["suggested_actions"] = [
        {
            "action_id": action.action_id,
            "label": action.label,
            "style": action.style,
            "semantic_payload": action.semantic_payload,
        }
    ]
    storage.save_session(session)

    # 定义runtime（返回追问消息）
    class _TestRuntime:
        def initial_decision(self, _run_input):
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="collecting_preferences",
                    assistant_message="开始吧",
                )
            )

        def run_turn(self, _run_input, *, user_message=None, action_context=None):
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="collecting_preferences",
                    assistant_message="上一批哪里不合适？",
                    suggested_actions=[
                        DiscoveryActionSuggestion(
                            label="太远了",
                            semantic_payload={"kind": "rejection_feedback", "feedback_type": "location_distance"},
                            style="secondary",
                        ),
                        DiscoveryActionSuggestion(
                            label="职业不匹配",
                            semantic_payload={"kind": "rejection_feedback", "feedback_type": "occupation_mismatch"},
                            style="secondary",
                        ),
                    ],
                )
            )

    service.runtime = _TestRuntime()

    # ========== 用户点击按钮 ==========
    result = service.process_turn(
        session_id="test-session-001",
        action_id=action.action_id,
    )

    # ========== 验证Timeline ==========
    timeline = result["view"]["timeline"]

    print("\n========== Timeline历史记录 ========== ")
    for i, item in enumerate(timeline):
        item_type = item.get("item_type")
        body = item.get("body", "")

        if item_type == "assistant_message":
            print(f"{i}. AI消息: {body}")
        elif item_type == "user_message":
            print(f"{i}. 用户消息: {body} ✅")
        else:
            print(f"{i}. {item_type}")

    # ========== 验证点 ==========
    # 1. Timeline应该有3条记录：AI推荐 → 用户点击 → AI追问
    assert len(timeline) == 3, f"Timeline应该有3条记录，实际有{len(timeline)}条"

    # 2. 第二条应该是用户点击按钮的记录
    click_item = timeline[1]
    assert click_item["item_type"] == "user_message", "点击记录应该是user_message类型"

    # 3. 点击记录的内容应该是按钮文本
    assert click_item["body"] == "[换一批]", f"点击记录内容应该是'[换一批]', 实际是'{click_item['body']}'"

    # 4. 用户能看到自己点击了什么
    print(f"\n✅ 用户可以看到自己点击了: {click_item['body']}")

    return True


def test_multiple_action_clicks():
    """
    测试：多次点击按钮，每次都保留历史记录
    """
    storage = InMemoryDiscoveryStorage()
    service = DiscoveryService(storage=storage, runtime=None)

    # 创建session
    session = StoredSession(
        session_id="test-session-002",
        requester_id=10001,
        profile_id=10001,
        status="active",
        phase="collecting_preferences",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        view={"timeline": []},
        state={},
    )
    storage.save_session(session)

    # 创建多个按钮
    actions = []
    for label in ["换一批", "调整条件", "跳过"]:
        action = storage.create_action(
            session_id="test-session-002",
            label=label,
            style="secondary",
            semantic_payload={"kind": "show_more_candidates"},
            now=datetime.now(),
        )
        actions.append(action)

    session.visible_action_ids = [a.action_id for a in actions]
    session.view["suggested_actions"] = [
        {
            "action_id": a.action_id,
            "label": a.label,
            "style": a.style,
            "semantic_payload": a.semantic_payload,
        }
        for a in actions
    ]
    storage.save_session(session)

    # 定义runtime
    class _TestRuntime:
        def initial_decision(self, _run_input):
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(phase="collecting_preferences", assistant_message="开始")
            )

        def run_turn(self, _run_input, *, user_message=None, action_context=None):
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="collecting_preferences",
                    assistant_message=f"收到你的反馈",
                    suggested_actions=[],
                )
            )

    service.runtime = _TestRuntime()

    # 模拟AI先发送一条消息
    session.view["timeline"].append(
        {
            "item_type": "assistant_message",
            "item_id": "msg-001",
            "body": "为你推荐候选人",
        }
    )
    storage.save_session(session)

    # 点击第一个按钮
    result1 = service.process_turn(session_id="test-session-002", action_id=actions[0].action_id)

    print("\n========== 第一次点击 ========== ")
    timeline1 = result1["view"]["timeline"]
    for item in timeline1:
        if item["item_type"] == "user_message":
            print(f"用户点击: {item['body']} ✅")

    assert timeline1[-2]["body"] == "[换一批]", "第一次点击应该记录'[换一批]'"

    # 添加新的按钮（模拟第二轮）
    new_action = storage.create_action(
        session_id="test-session-002",
        label="职业不匹配",
        style="secondary",
        semantic_payload={"kind": "rejection_feedback", "feedback_type": "occupation_mismatch"},
        now=datetime.now(),
    )

    session = storage.get_session("test-session-002")
    session.visible_action_ids = [new_action.action_id]
    session.view["suggested_actions"] = [
        {
            "action_id": new_action.action_id,
            "label": new_action.label,
            "style": new_action.style,
            "semantic_payload": new_action.semantic_payload,
        }
    ]
    storage.save_session(session)

    # 点击第二个按钮
    result2 = service.process_turn(session_id="test-session-002", action_id=new_action.action_id)

    print("\n========== 第二次点击 ========== ")
    timeline2 = result2["view"]["timeline"]
    for item in timeline2:
        if item["item_type"] == "user_message":
            print(f"用户点击: {item['body']} ✅")

    # 验证：两次点击都保留在timeline中
    user_clicks = [item for item in timeline2 if item["item_type"] == "user_message"]
    assert len(user_clicks) >= 2, "应该有至少2条点击记录"

    click_labels = [item["body"] for item in user_clicks]
    assert "[换一批]" in click_labels, "第一次点击'[换一批]'应该保留"
    assert "[职业不匹配]" in click_labels, "第二次点击'[职业不匹配]'应该保留"

    print("\n✅ 多次点击都正确保留在历史对话中")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("端到端测试：按钮点击保留在历史对话中")
    print("=" * 60)

    try:
        test_action_click_preserved_in_timeline()
        print("\n✅ 测试1通过：单次点击保留")

        test_multiple_action_clicks()
        print("\n✅ 测试2通过：多次点击保留")

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)