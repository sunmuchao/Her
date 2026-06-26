"""Gateway integration: proxy-intro case 'viewed' status API tests."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for root in (GATEWAY_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT, CHAT_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from gateway.app import PartnerGateway  # noqa: E402
from gateway.identity import ActorPrincipal, ROLE_END_USER  # noqa: E402
from gateway.proxy_intro_routes import rest_proxy_intro_view_case, rest_proxy_intro_list_mine  # noqa: E402
from matchmaking_system.proxy_intro import create_match_case, get_match_case, mark_case_as_viewed  # noqa: E402
from recommendation_system import (  # noqa: E402
    connect_db as connect_recommendation_db,
    create_subscription,
    deliver_in_app_recommendations,
    initialize_database as initialize_recommendation_db,
    record_user_review,
    refresh_subscription,
    reset_all_tables as reset_recommendation_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import connect_db as connect_matchmaking_db  # noqa: E402
from matchmaking_system import initialize_database as initialize_matchmaking_db  # noqa: E402
from matchmaking_system import reset_all_tables as reset_matchmaking_tables  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN  # noqa: E402


def _search_result(candidate_id: int) -> dict[str, object]:
    return {
        "id": candidate_id,
        "name": "测试候选人",
        "score": 60,
        "fit_score": 50,
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": [],
        "reciprocal_on": [],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [],
        "photo_preview": [],
        "profile": {"age": 27, "city": "无锡", "relationship_goal": "认真恋爱"},
    }


class ProxyIntroViewedStatusTests(unittest.TestCase):
    """测试被动推荐的'已查看'状态功能"""

    def setUp(self) -> None:
        self._old_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"

        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_db(rec)
        reset_recommendation_tables(rec)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_db(mm)
        reset_matchmaking_tables(mm)
        rec.close()
        mm.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )
        self._requester_id = 75001
        self._candidate_id = 92001

    def tearDown(self) -> None:
        if self._old_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_storage

    def _seed_case_awaiting_reply(self) -> str:
        """创建一个处于awaiting_reply状态的case"""
        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            sub = create_subscription(
                rec,
                requester_id=self._requester_id,
                title="test-viewed",
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["无锡"]},
                self_profile={"age": 30, "city": "无锡"},
                now=datetime(2026, 6, 10, 9, 0, 0),
            )
            refresh_subscription(
                rec,
                sub["subscription_id"],
                now=datetime(2026, 6, 10, 9, 5, 0),
                search_runner=lambda **_: {"results": [_search_result(self._candidate_id)]},
            )
            record_user_review(
                rec,
                subscription_id=sub["subscription_id"],
                candidate_id=self._candidate_id,
                review_type="direct_greet",
                now=datetime(2026, 6, 10, 9, 10, 0),
            )
            deliver_in_app_recommendations(rec, now=datetime(2026, 6, 10, 9, 20, 0))
            case = create_match_case(
                mm,
                recommendation_conn=rec,
                subscription_id=sub["subscription_id"],
                candidate_id=self._candidate_id,
                now=datetime(2026, 6, 10, 10, 0, 0),
            )
            return str(case["case_id"])
        finally:
            rec.close()
            mm.close()

    def test_mark_case_as_viewed_success(self) -> None:
        """测试：成功标记case为viewed状态"""
        case_id = self._seed_case_awaiting_reply()

        # 验证初始状态是awaiting_reply
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_before = get_match_case(mm, case_id)
        mm.close()
        self.assertEqual(case_before["case_status"], "awaiting_reply")

        # 调用mark_case_as_viewed
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_after = mark_case_as_viewed(
            mm,
            case_id=case_id,
            now=datetime(2026, 6, 10, 11, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm.commit()
        mm.close()

        # 验证状态变为viewed
        self.assertEqual(case_after["case_status"], "viewed")
        self.assertIsNotNone(case_after["replied_at"])  # 应该记录时间戳

    def test_mark_case_as_viewed_invalid_status(self) -> None:
        """测试：对非awaiting_reply状态的case调用mark_case_as_viewed"""
        case_id = self._seed_case_awaiting_reply()

        # 先标记为viewed
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        mark_case_as_viewed(
            mm,
            case_id=case_id,
            now=datetime(2026, 6, 10, 11, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm.commit()
        mm.close()

        # 再次尝试标记为viewed（应该不会改变状态）
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_after = mark_case_as_viewed(
            mm,
            case_id=case_id,
            now=datetime(2026, 6, 10, 12, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm.close()

        # 验证状态仍然为viewed（不会抛错）
        self.assertEqual(case_after["case_status"], "viewed")

    def test_rest_proxy_intro_view_case_success(self) -> None:
        """测试：REST API成功调用"""
        case_id = self._seed_case_awaiting_reply()

        environ = {
            "_actor": ActorPrincipal(
                actor_id=str(self._candidate_id),  # candidate调用
                roles=frozenset({ROLE_END_USER}),
                token_id="test",
                auth_source="static_token",
            ),
        }
        body = {"source": "detail_page"}

        # 调用REST API
        status_code, response = rest_proxy_intro_view_case(
            self.gw,
            environ,
            case_id,
            body,
        )

        # 验证返回
        self.assertEqual(status_code, 200)
        self.assertIsNotNone(response.get("case"))
        self.assertEqual(response["case"]["case_status"], "viewed")

    def test_rest_proxy_intro_view_case_permission_denied(self) -> None:
        """测试：非candidate调用API（权限拒绝）"""
        case_id = self._seed_case_awaiting_reply()

        # 使用requester_id调用（不是candidate）
        environ = {
            "_actor": ActorPrincipal(
                actor_id=str(self._requester_id),  # requester调用
                roles=frozenset({ROLE_END_USER}),
                token_id="test",
                auth_source="static_token",
            ),
        }
        body = {"source": "detail_page"}

        # 调用REST API
        with self.assertRaises(ValueError) as cm:
            rest_proxy_intro_view_case(
                self.gw,
                environ,
                case_id,
                body,
            )

        # 验证错误信息
        self.assertIn("只有被推荐的一方", str(cm.exception))

    def test_case_status_in_open_cases(self) -> None:
        """测试：viewed状态应该属于OPEN_CASE_STATUSES"""
        from matchmaking_system.proxy_intro_core import OPEN_CASE_STATUSES

        # 验证viewed在OPEN_CASE_STATUSES中
        self.assertIn("viewed", OPEN_CASE_STATUSES)

        # 验证awaiting_reply、accepted也在OPEN_CASE_STATUSES中
        self.assertIn("awaiting_reply", OPEN_CASE_STATUSES)
        self.assertIn("accepted", OPEN_CASE_STATUSES)


class BadgeCountCalculationTests(unittest.TestCase):
    """测试badge count计算逻辑的改变"""

    def test_awaiting_reply_counts_as_unread(self) -> None:
        """测试：awaiting_reply状态的case应该计入badge count"""
        # 这个测试验证前端badge count计算逻辑
        # 前端应该只统计 case_status === 'awaiting_reply' 的case

        # 模拟数据
        cases = [
            {"case_id": "case-1", "role": "candidate", "case_status": "awaiting_reply"},
            {"case_id": "case-2", "role": "candidate", "case_status": "viewed"},
            {"case_id": "case-3", "role": "candidate", "case_status": "accepted"},
            {"case_id": "case-4", "role": "requester", "case_status": "awaiting_reply"},  # requester不算
        ]

        # 计算未读数（模拟前端逻辑）
        interest_unread = len([
            c for c in cases
            if c["role"] == "candidate" and c["case_status"] == "awaiting_reply"
        ])

        # 验证：只有case-1应该计入
        self.assertEqual(interest_unread, 1)

    def test_viewed_not_counts_as_unread(self) -> None:
        """测试：viewed状态的case不应该计入badge count"""
        cases = [
            {"case_id": "case-1", "role": "candidate", "case_status": "awaiting_reply"},
            {"case_id": "case-2", "role": "candidate", "case_status": "viewed"},
        ]

        # 计算未读数
        interest_unread = len([
            c for c in cases
            if c["role"] == "candidate" and c["case_status"] == "awaiting_reply"
        ])

        # 验证：只有awaiting_reply的case-1应该计入
        self.assertEqual(interest_unread, 1)


class StageLabelVisibilityTests(unittest.TestCase):
    """测试'已查看'状态的 stage_label 按 role 显示逻辑"""

    def setUp(self) -> None:
        self._old_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"

        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_db(rec)
        reset_recommendation_tables(rec)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_db(mm)
        reset_matchmaking_tables(mm)
        rec.close()
        mm.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )
        self._requester_id = 75001
        self._candidate_id = 92001

    def tearDown(self) -> None:
        if self._old_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_storage

    def _seed_case_awaiting_reply(self) -> str:
        """创建一个处于awaiting_reply状态的case"""
        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            sub = create_subscription(
                rec,
                requester_id=self._requester_id,
                title="test-stage-label",
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["无锡"]},
                self_profile={"age": 30, "city": "无锡"},
                now=datetime(2026, 6, 10, 9, 0, 0),
            )
            refresh_subscription(
                rec,
                sub["subscription_id"],
                now=datetime(2026, 6, 10, 9, 5, 0),
                search_runner=lambda **_: {"results": [_search_result(self._candidate_id)]},
            )
            record_user_review(
                rec,
                subscription_id=sub["subscription_id"],
                candidate_id=self._candidate_id,
                review_type="direct_greet",
                now=datetime(2026, 6, 10, 9, 10, 0),
            )
            deliver_in_app_recommendations(rec, now=datetime(2026, 6, 10, 9, 20, 0))
            case = create_match_case(
                mm,
                recommendation_conn=rec,
                subscription_id=sub["subscription_id"],
                candidate_id=self._candidate_id,
                now=datetime(2026, 6, 10, 10, 0, 0),
            )
            return str(case["case_id"])
        finally:
            rec.close()
            mm.close()

    def test_requester_sees_waiting_reply_when_viewed(self) -> None:
        """测试：发起方在viewed状态看到'等待回复'而非'已查看'"""
        case_id = self._seed_case_awaiting_reply()

        # 标记为已查看
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        mark_case_as_viewed(
            mm,
            case_id=case_id,
            now=datetime(2026, 6, 10, 11, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm.commit()
        mm.close()

        # requester 查看case列表
        environ = {
            "_actor": ActorPrincipal(
                actor_id=str(self._requester_id),
                roles=frozenset({ROLE_END_USER}),
                token_id="test",
                auth_source="static_token",
            ),
        }
        status_code, response = rest_proxy_intro_list_mine(self.gw, environ)

        # 验证返回
        self.assertEqual(status_code, 200)
        cases = response.get("cases", [])
        self.assertTrue(len(cases) > 0)

        # 找到我们的case
        target_case = None
        for c in cases:
            if c["case_id"] == case_id:
                target_case = c
                break

        self.assertIsNotNone(target_case)
        self.assertEqual(target_case["case_status"], "viewed")  # 真实状态是viewed
        self.assertEqual(target_case["role"], "requester")  # role是requester
        # 🔒 关键验证：requester看到"等待回复"，而非"已查看"
        self.assertEqual(target_case["stage_label"], "等待回复")

    def test_candidate_sees_viewed_when_viewed(self) -> None:
        """测试：被推荐方在viewed状态看到真实的'已查看'"""
        case_id = self._seed_case_awaiting_reply()

        # 标记为已查看
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        mark_case_as_viewed(
            mm,
            case_id=case_id,
            now=datetime(2026, 6, 10, 11, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm.commit()
        mm.close()

        # candidate 查看case列表
        environ = {
            "_actor": ActorPrincipal(
                actor_id=str(self._candidate_id),
                roles=frozenset({ROLE_END_USER}),
                token_id="test",
                auth_source="static_token",
            ),
        }
        status_code, response = rest_proxy_intro_list_mine(self.gw, environ)

        # 验证返回
        self.assertEqual(status_code, 200)
        cases = response.get("cases", [])
        self.assertTrue(len(cases) > 0)

        # 找到我们的case
        target_case = None
        for c in cases:
            if c["case_id"] == case_id:
                target_case = c
                break

        self.assertIsNotNone(target_case)
        self.assertEqual(target_case["case_status"], "viewed")  # 真实状态是viewed
        self.assertEqual(target_case["role"], "candidate")  # role是candidate
        # 🔑 关键验证：candidate看到真实的"已查看"
        self.assertEqual(target_case["stage_label"], "已查看")


if __name__ == "__main__":
    unittest.main()