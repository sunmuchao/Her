"""端到端测试：被动推荐'已查看'状态的完整用户流程"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"

for root in (GATEWAY_ROOT, CHAT_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
)
from gateway.app import PartnerGateway  # noqa: E402
from gateway_tests.helpers import (  # noqa: E402
    auth_headers,
    call_gateway_json,
    ensure_search_schema,
    reset_search_rows,
    search_test_config,
)
from matchmaking_system.proxy_intro import (  # noqa: E402
    get_match_case,
    mark_case_as_viewed,
    record_match_case_reply,
)
from matchmaking_system.storage import (  # noqa: E402
    DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
    connect_db as connect_matchmaking_db,
    initialize_database as initialize_matchmaking_db,
    reset_all_tables as reset_matchmaking_tables,
)
from recommendation_system import (  # noqa: E402
    create_subscription,
    deliver_in_app_recommendations,
    record_user_review,
    refresh_subscription,
)
from recommendation_system.storage import (  # noqa: E402
    DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
    connect_db as connect_recommendation_db,
    initialize_database as initialize_recommendation_db,
    reset_all_tables as reset_recommendation_tables,
)
from relationship_ledger.storage import (  # noqa: E402
    DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN,
    connect_db as connect_relation_ledger_db,
    initialize_database as initialize_relation_ledger_db,
    reset_all_tables as reset_relation_ledger_tables,
)


DEFAULT_PROFILE_TEST_DSN = os.environ.get(
    "PARTNER_SEARCH_E2E_TEST_DB",
    os.environ.get(
        "PARTNER_SEARCH_REALISTIC_TEST_DB",
        "mysql://root@127.0.0.1:3307/her_partner_search_realistic_test?table=profiles&photos_table=profile_photos",
    ),
)


class ProxyIntroViewedStatusEndToEndTests(unittest.TestCase):
    """端到端测试：被动推荐'已查看'状态的完整流程"""

    def setUp(self) -> None:
        self.profile_search_config = search_test_config(DEFAULT_PROFILE_TEST_DSN)
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        self._old_proxy_intro_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        self._old_profile_source_dsn = os.environ.get("HER_PROFILE_SOURCE_DSN")
        os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"
        os.environ["HER_PROFILE_SOURCE_DSN"] = DEFAULT_PROFILE_TEST_DSN
        ensure_search_schema(self.profile_search_config)
        reset_search_rows(self.profile_search_config)

        rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_db(rec_conn)
        reset_recommendation_tables(rec_conn)
        rec_conn.close()

        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_db(mm_conn)
        reset_matchmaking_tables(mm_conn)
        mm_conn.close()

        chat_conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_chat_db(chat_conn)
        reset_chat_tables(chat_conn)
        chat_conn.close()

        ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        initialize_relation_ledger_db(ledger_conn)
        reset_relation_ledger_tables(ledger_conn)
        ledger_conn.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            relation_ledger_dsn=DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN,
            profile_source_dsn=DEFAULT_PROFILE_TEST_DSN,
            sms_provider=_FakeSmsProvider(),
            db_pool_max=0,
        )

        self.requester_id = 1001
        self.candidate_id = 2001

    def tearDown(self) -> None:
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db

        if self._old_proxy_intro_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_proxy_intro_storage

        if self._old_profile_source_dsn is None:
            os.environ.pop("HER_PROFILE_SOURCE_DSN", None)
        else:
            os.environ["HER_PROFILE_SOURCE_DSN"] = self._old_profile_source_dsn

    def _seed_passive_recommendation(self) -> str:
        """创建一个被动推荐case（模拟有人想认识用户）"""
        rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)

        try:
            # 创建订阅
            sub = create_subscription(
                rec_conn,
                requester_id=self.requester_id,
                title="被动推荐测试",
                source=DEFAULT_PROFILE_TEST_DSN,
                criteria={"gender": "女", "cities": ["北京"]},
                self_profile={"age": 30, "city": "北京"},
                now=datetime(2026, 6, 20, 10, 0, 0),
            )

            # 刷新订阅（生成推荐）
            refresh_subscription(
                rec_conn,
                sub["subscription_id"],
                now=datetime(2026, 6, 20, 10, 5, 0),
                search_runner=lambda **_: {
                    "results": [
                        {
                            "id": self.candidate_id,
                            "name": "测试候选人",
                            "score": 60,
                            "profile": {"age": 27, "city": "北京"},
                        }
                    ]
                },
            )

            # 记录用户评价（直接打招呼）
            record_user_review(
                rec_conn,
                subscription_id=sub["subscription_id"],
                candidate_id=self.candidate_id,
                review_type="direct_greet",
                now=datetime(2026, 6, 20, 10, 10, 0),
            )

            # 投递推荐
            deliver_in_app_recommendations(rec_conn, now=datetime(2026, 6, 20, 10, 20, 0))

            # 创建match case
            from matchmaking_system.proxy_intro import create_match_case
            case = create_match_case(
                mm_conn,
                recommendation_conn=rec_conn,
                subscription_id=sub["subscription_id"],
                candidate_id=self.candidate_id,
                now=datetime(2026, 6, 20, 11, 0, 0),
            )

            mm_conn.commit()
            return str(case["case_id"])
        finally:
            rec_conn.close()
            mm_conn.close()

    def test_full_user_flow_awaiting_reply_to_viewed(self) -> None:
        """完整流程：用户点击被动推荐卡片，状态从awaiting_reply变为viewed"""

        # 1. 创建被动推荐case
        case_id = self._seed_passive_recommendation()

        # 2. 验证初始状态：awaiting_reply
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_before = get_match_case(mm_conn, case_id)
        mm_conn.close()

        self.assertIsNotNone(case_before)
        self.assertEqual(case_before["case_status"], "awaiting_reply")

        # 3. 用户点击卡片进入详情页（调用API标记为viewed）
        headers = auth_headers(self.candidate_id)
        response = call_gateway_json(
            self.gw,
            method="POST",
            path=f"/v1/proxy-intro/cases/{case_id}/view",
            headers=headers,
            body={"source": "detail_page"},
        )

        # 4. 验证API返回：状态变为viewed
        self.assertEqual(response.status_code, 200)
        case_view = response.json_data.get("case")
        self.assertIsNotNone(case_view)
        self.assertEqual(case_view["case_status"], "viewed")

        # 5. 验证数据库状态：viewed
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_after = get_match_case(mm_conn, case_id)
        mm_conn.close()

        self.assertEqual(case_after["case_status"], "viewed")
        self.assertIsNotNone(case_after.get("replied_at"))

        # 6. 验证badge count：viewed状态不计入
        # 模拟前端计算badge count的逻辑
        headers = auth_headers(self.candidate_id)
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        # 验证：badge count为0（因为case已经变为viewed）
        self.assertEqual(interest_unread, 0)

    def test_full_user_flow_viewed_to_accepted(self) -> None:
        """完整流程：用户接受被动推荐，状态从viewed变为accepted"""

        # 1. 创建case并标记为viewed
        case_id = self._seed_passive_recommendation()
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        mark_case_as_viewed(
            mm_conn,
            case_id=case_id,
            now=datetime(2026, 6, 20, 12, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm_conn.commit()
        mm_conn.close()

        # 2. 用户点击"愿意认识"（调用reply API）
        headers = auth_headers(self.candidate_id)
        response = call_gateway_json(
            self.gw,
            method="POST",
            path=f"/v1/proxy-intro/cases/{case_id}/reply",
            headers=headers,
            body={"reply_type": "accepted", "source": "detail_page"},
        )

        # 3. 验证API返回：状态变为accepted
        self.assertEqual(response.status_code, 200)
        case_accepted = response.json_data.get("case")
        self.assertIsNotNone(case_accepted)
        self.assertEqual(case_accepted["case_status"], "accepted")

        # 4. 验证数据库状态：accepted
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        case_final = get_match_case(mm_conn, case_id)
        mm_conn.close()

        self.assertEqual(case_final["case_status"], "accepted")

        # 5. 验证badge count：仍然为0（accepted状态也不计入）
        headers = auth_headers(self.candidate_id)
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        self.assertEqual(interest_unread, 0)

    def test_full_user_flow_multiple_cases_badge_count(self) -> None:
        """完整流程：多个被动推荐case，badge count计算正确"""

        # 1. 创建3个被动推荐case
        case_ids = []
        for i in range(3):
            self.candidate_id = 2001 + i
            case_id = self._seed_passive_recommendation()
            case_ids.append(case_id)

        # 2. 验证初始badge count：3（全部awaiting_reply）
        headers = auth_headers(2001)  # 使用第一个candidate
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        self.assertEqual(interest_unread, 3)

        # 3. 用户点击第一个case（标记为viewed）
        headers = auth_headers(2001)
        response = call_gateway_json(
            self.gw,
            method="POST",
            path=f"/v1/proxy-intro/cases/{case_ids[0]}/view",
            headers=headers,
            body={"source": "detail_page"},
        )

        # 4. 验证badge count减少：2（1个viewed，2个awaiting_reply）
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        self.assertEqual(interest_unread, 2)

        # 5. 用户接受第一个case（状态变为accepted）
        response = call_gateway_json(
            self.gw,
            method="POST",
            path=f"/v1/proxy-intro/cases/{case_ids[0]}/reply",
            headers=headers,
            body={"reply_type": "accepted"},
        )

        # 6. 验证badge count仍然为2（accepted状态不影响badge count）
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        self.assertEqual(interest_unread, 2)

    def test_persistence_after_browser_cache_clear(self) -> None:
        """持久化验证：清空浏览器缓存不影响badge count（根本解决）"""

        # 1. 创建case并标记为viewed
        case_id = self._seed_passive_recommendation()
        mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        mark_case_as_viewed(
            mm_conn,
            case_id=case_id,
            now=datetime(2026, 6, 20, 12, 0, 0),
            view_payload={"source": "detail_page"},
        )
        mm_conn.commit()
        mm_conn.close()

        # 2. 模拟清空浏览器缓存（前端sessionStorage清空）
        # 在根本解决方案中，前端不依赖sessionStorage，状态在后端持久化

        # 3. 刷新badge count（从后端获取真实数据）
        headers = auth_headers(self.candidate_id)
        response = call_gateway_json(
            self.gw,
            method="GET",
            path="/v1/proxy-intro/cases/mine",
            headers=headers,
        )

        cases = response.json_data.get("cases", [])
        interest_unread = len([
            c for c in cases
            if c.get("role") == "candidate" and c.get("case_status") == "awaiting_reply"
        ])

        # 4. 验证：badge count仍然为0（viewed状态在后端持久化）
        self.assertEqual(interest_unread, 0)


class _FakeSmsProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_code(self, phone: str, code: str) -> dict[str, str]:
        self.calls.append((phone, code))
        return {"provider": "fake"}


if __name__ == "__main__":
    unittest.main()