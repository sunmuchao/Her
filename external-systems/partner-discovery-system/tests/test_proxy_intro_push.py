"""测试被动推荐推送逻辑（有人想认识你）

测试场景：
1. 模拟创建被动推荐案件
2. 模拟马沐瑶打开发现页（create_session）
3. 检查timeline中是否有"有人想认识你"卡片
4. 验证案件是否被标记为已推送

运行方式：
cd external-systems/partner-discovery-system
python -m pytest tests/test_proxy_intro_push.py -v

或者直接运行：
python tests/test_proxy_intro_push.py
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

# 添加discovery_system到sys.path
DISCOVERY_ROOT = Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.service import DiscoveryService, StoredSession
from discovery_system.storage import InMemoryDiscoveryStorage
from discovery_system.view_models import assistant_message, result_group, composer


class ProxyIntroPushTests(unittest.TestCase):
    """测试被动推荐推送逻辑"""

    def setUp(self) -> None:
        """设置测试环境"""
        # 创建mock storage
        self.storage = InMemoryDiscoveryStorage()

        # 创建mock runtime（不需要真实的Agent）
        self.runtime = Mock()

        # 创建DiscoveryService实例
        self.service = DiscoveryService(
            storage=self.storage,
            runtime=self.runtime,
        )

        # 测试数据
        self.requester_profile_id = 123  # 发起方（你）
        self.candidate_profile_id = 456  # 被推荐方（马沐瑶）
        self.case_id = "match-case-test123"

    def test_check_and_push_proxy_intro_cases_basic_logic(self) -> None:
        """测试基础推送逻辑：检查待推送案件并推送到timeline"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-1",
            requester_id=1001,
            profile_id=self.candidate_profile_id,  # 马沐瑶的profile_id
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. 创建mock案件数据
        mock_cases = [
            {
                "case_id": self.case_id,
                "requester_id": self.requester_profile_id,  # 发起方（你）
                "candidate_id": self.candidate_profile_id,  # 被推荐方（马沐瑶）
                "case_status": "awaiting_reply",
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "张三",
                        "age": 28,
                        "city": "北京",
                        "occupation": "程序员",
                    }
                },
                "outreach_payload": {},  # 未推送
            },
        ]

        # 3. Mock数据库连接和查询
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None  # execute成功
        mock_conn.commit.return_value = None  # commit成功
        mock_conn.close.return_value = None  # close成功

        # 4. Mock open_proxy_intro_conn
        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn

            # 5. Mock list_match_cases_for_participant
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 6. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 7. 验证timeline中有推送的消息和候选人卡片
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 2, "应该有2个timeline item：消息+候选人卡片")

        # 8. 验证第一个是assistant_message
        first_item = timeline[0]
        self.assertEqual(first_item.get("item_type"), "assistant_message")
        self.assertIn("有人想认识你", first_item.get("body", ""))
        self.assertIn("张三", first_item.get("body", ""))
        self.assertIn("28", first_item.get("body", ""))
        self.assertIn("北京", first_item.get("body", ""))

        # 9. 验证第二个是result_group
        second_item = timeline[1]
        self.assertEqual(second_item.get("item_type"), "result_group")
        self.assertEqual(second_item.get("title"), "有人想认识你")
        cards = second_item.get("cards", [])
        self.assertEqual(len(cards), 1, "应该有1个候选人卡片")

        # 10. 验证候选人卡片的数据
        card = cards[0]
        self.assertEqual(card.get("profile_id"), self.requester_profile_id)
        self.assertIn("张三", card.get("title", ""))

        # 11. 验证数据库更新（标记为已推送）
        self.assertTrue(mock_conn.execute.called, "应该调用了execute更新数据库")

    def test_no_pending_cases_no_push(self) -> None:
        """测试没有待推送案件时不推送"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-2",
            requester_id=1002,
            profile_id=self.candidate_profile_id,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. Mock数据库连接和查询（返回空列表）
        mock_conn = MagicMock()
        mock_cases = []  # 没有待推送案件

        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 3. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 4. 验证timeline没有变化
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 0, "没有待推送案件，timeline应该为空")

        # 5. 验证没有调用数据库更新
        self.assertFalse(mock_conn.execute.called, "没有待推送案件，不应该调用execute")

    def test_already_pushed_no_duplicate(self) -> None:
        """测试已推送的案件不会重复推送"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-3",
            requester_id=1003,
            profile_id=self.candidate_profile_id,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. 创建已推送的案件数据（discovery_pushed=True）
        mock_cases = [
            {
                "case_id": self.case_id,
                "requester_id": self.requester_profile_id,
                "candidate_id": self.candidate_profile_id,
                "case_status": "awaiting_reply",
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "张三",
                        "age": 28,
                        "city": "北京",
                        "occupation": "程序员",
                    }
                },
                "outreach_payload": {
                    "discovery_pushed": True,  # 已推送
                },
            },
        ]

        # 3. Mock数据库连接和查询
        mock_conn = MagicMock()

        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 4. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 5. 验证timeline没有变化（已推送的案件不会再次推送）
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 0, "已推送的案件，不应该重复推送")

        # 6. 验证没有调用数据库更新
        self.assertFalse(mock_conn.execute.called, "已推送的案件，不应该调用execute")

    def test_wrong_candidate_id_no_push(self) -> None:
        """测试candidate_id不匹配的案件不会推送"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-4",
            requester_id=1004,
            profile_id=self.candidate_profile_id,  # 马沐瑶的profile_id
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. 创建案件数据（candidate_id不匹配）
        mock_cases = [
            {
                "case_id": self.case_id,
                "requester_id": self.requester_profile_id,
                "candidate_id": 999,  # 不匹配马沐瑶的profile_id
                "case_status": "awaiting_reply",
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "张三",
                        "age": 28,
                        "city": "北京",
                        "occupation": "程序员",
                    }
                },
                "outreach_payload": {},
            },
        ]

        # 3. Mock数据库连接和查询
        mock_conn = MagicMock()

        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 4. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 5. 验证timeline没有变化（candidate_id不匹配）
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 0, "candidate_id不匹配，不应该推送")

    def test_wrong_case_status_no_push(self) -> None:
        """测试case_status不是awaiting_reply的案件不会推送"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-5",
            requester_id=1005,
            profile_id=self.candidate_profile_id,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. 创建案件数据（case_status不是awaiting_reply）
        mock_cases = [
            {
                "case_id": self.case_id,
                "requester_id": self.requester_profile_id,
                "candidate_id": self.candidate_profile_id,
                "case_status": "accepted",  # 不是awaiting_reply
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "张三",
                        "age": 28,
                        "city": "北京",
                        "occupation": "程序员",
                    }
                },
                "outreach_payload": {},
            },
        ]

        # 3. Mock数据库连接和查询
        mock_conn = MagicMock()

        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 4. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 5. 验证timeline没有变化（case_status不匹配）
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 0, "case_status不是awaiting_reply，不应该推送")

    def test_multiple_cases_push_all(self) -> None:
        """测试多个待推送案件都推送"""

        # 1. 创建mock session
        session = StoredSession(
            session_id="test-session-6",
            requester_id=1006,
            profile_id=self.candidate_profile_id,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("测试placeholder"),
            },
            state={},
        )

        # 2. 创建多个案件数据
        mock_cases = [
            {
                "case_id": "match-case-test1",
                "requester_id": 123,
                "candidate_id": self.candidate_profile_id,
                "case_status": "awaiting_reply",
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "张三",
                        "age": 28,
                        "city": "北京",
                        "occupation": "程序员",
                    }
                },
                "outreach_payload": {},
            },
            {
                "case_id": "match-case-test2",
                "requester_id": 789,
                "candidate_id": self.candidate_profile_id,
                "case_status": "awaiting_reply",
                "requester_profile_snapshot": {
                    "self_profile": {
                        "display_name": "李四",
                        "age": 30,
                        "city": "上海",
                        "occupation": "工程师",
                    }
                },
                "outreach_payload": {},
            },
        ]

        # 3. Mock数据库连接和查询
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None
        mock_conn.commit.return_value = None
        mock_conn.close.return_value = None

        with patch("discovery_system.service.open_proxy_intro_conn") as mock_open_conn:
            mock_open_conn.return_value = mock_conn
            with patch("discovery_system.service.list_match_cases_for_participant") as mock_list_cases:
                mock_list_cases.return_value = mock_cases

                # 4. 调用推送方法
                self.service._check_and_push_proxy_intro_cases(
                    session=session,
                    profile_id=self.candidate_profile_id,
                    now=datetime.now(),
                )

        # 5. 验证timeline有4个item（2个案件 × 2个item）
        timeline = session.view.get("timeline", [])
        self.assertEqual(len(timeline), 4, "应该有4个timeline item：2个案件 × (消息+卡片)")

        # 6. 验证第一个案件的消息
        first_msg = timeline[0]
        self.assertIn("张三", first_msg.get("body", ""))

        # 7. 验证第二个案件的消息
        second_msg = timeline[2]
        self.assertIn("李四", second_msg.get("body", ""))


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)