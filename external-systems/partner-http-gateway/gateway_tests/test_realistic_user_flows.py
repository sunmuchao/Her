from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"

for root in (GATEWAY_ROOT, CHAT_ROOT, RECOMMENDATION_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

import outer_system_mysql_schema as mysql_schema  # noqa: E402

from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
)
from gateway.app import PartnerGateway  # noqa: E402
from recommendation_system.storage import (  # noqa: E402
    DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
    connect_db as connect_recommendation_db,
    initialize_database as initialize_recommendation_db,
    reset_all_tables as reset_recommendation_tables,
)


DEFAULT_REALISTIC_SEARCH_TEST_DSN = os.environ.get(
    "PARTNER_SEARCH_REALISTIC_TEST_DB",
    "mysql://root@127.0.0.1:3307/her_partner_search_realistic_test?table=profiles&photos_table=profile_photos",
)


class GatewayRealisticUserFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.search_dsn = DEFAULT_REALISTIC_SEARCH_TEST_DSN
        cls.search_config = mysql_schema.parse_mysql_dsn(cls.search_dsn)
        mysql_schema.ensure_database(cls.search_config)
        cls._ensure_search_schema()

    @classmethod
    def _search_conn(cls):
        return mysql_schema.mysql_database_connect(cls.search_config)

    @classmethod
    def _ensure_search_schema(cls) -> None:
        conn = cls._search_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
                cursor.execute("DROP TABLE IF EXISTS `profiles`")
                cursor.execute(
                    """
                    CREATE TABLE `profiles` (
                      `id` BIGINT PRIMARY KEY,
                      `name` VARCHAR(255),
                      `gender` VARCHAR(32),
                      `age` INT,
                      `city` VARCHAR(64),
                      `education` VARCHAR(64),
                      `job` VARCHAR(255),
                      `income_range` VARCHAR(64),
                      `marital_status` VARCHAR(64),
                      `has_children` TINYINT(1),
                      `relationship_goal` VARCHAR(64),
                      `profile_status` VARCHAR(32),
                      `verified_level` VARCHAR(32),
                      `photo_verification_level` VARCHAR(32),
                      `education_verification_status` VARCHAR(32),
                      `job_verification_status` VARCHAR(32),
                      `income_verification_status` VARCHAR(32),
                      `profile_review_status` VARCHAR(32),
                      `job_change_count_30d` INT,
                      `photo_count` INT,
                      `life_routine` VARCHAR(64),
                      `communication_style` VARCHAR(64),
                      `values` TEXT,
                      `notes` TEXT,
                      `last_active_at` DATETIME
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE `profile_photos` (
                      `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                      `profile_id` BIGINT NOT NULL,
                      `photo_url` VARCHAR(512) NOT NULL,
                      `is_primary` TINYINT(1) DEFAULT 0,
                      `sort_order` INT DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def setUp(self) -> None:
        self._reset_search_rows()

        rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_db(rec_conn)
        reset_recommendation_tables(rec_conn)
        rec_conn.close()

        chat_conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_chat_db(chat_conn)
        reset_chat_tables(chat_conn)
        chat_conn.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn="mysql://noop",
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )

    def _reset_search_rows(self) -> None:
        conn = self._search_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM `profile_photos`")
                cursor.execute("DELETE FROM `profiles`")
            conn.commit()
        finally:
            conn.close()

    def _seed_search_profiles(self) -> None:
        conn = self._search_conn()
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        try:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO `profiles` (
                      `id`,
                      `name`,
                      `gender`,
                      `age`,
                      `city`,
                      `education`,
                      `job`,
                      `income_range`,
                      `marital_status`,
                      `has_children`,
                      `relationship_goal`,
                      `profile_status`,
                      `verified_level`,
                      `photo_verification_level`,
                      `education_verification_status`,
                      `job_verification_status`,
                      `income_verification_status`,
                      `profile_review_status`,
                      `job_change_count_30d`,
                      `photo_count`,
                      `life_routine`,
                      `communication_style`,
                      `values`,
                      `notes`,
                      `last_active_at`
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            1001,
                            "林知夏",
                            "女",
                            29,
                            "无锡",
                            "硕士",
                            "中学老师",
                            "20-30万/年",
                            "未婚",
                            0,
                            "结婚导向",
                            "active",
                            "offline",
                            "offline_verified",
                            "verified",
                            "verified",
                            "verified",
                            "approved",
                            0,
                            5,
                            "生活规律",
                            "主动沟通",
                            "消费观务实，愿意经营关系",
                            "情绪稳定，愿意沟通，认真长期关系",
                            active_at,
                        ),
                        (
                            1002,
                            "苏曼",
                            "女",
                            28,
                            "无锡",
                            "本科",
                            "创业顾问",
                            "80-120万/年",
                            "未婚",
                            0,
                            "认真恋爱",
                            "active",
                            "basic",
                            "uploaded",
                            "self_reported",
                            "needs_review",
                            "self_reported",
                            "needs_review",
                            2,
                            8,
                            "生活规律",
                            "主动沟通",
                            "很会包装自己，收入和职业都靠自述",
                            "情绪稳定，愿意沟通，也想认真恋爱",
                            active_at,
                        ),
                    ],
                )
                cursor.executemany(
                    """
                    INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (1001, "https://img.example.com/1001-main.jpg", 1, 0),
                        (1001, "https://img.example.com/1001-2.jpg", 0, 1),
                        (1002, "https://img.example.com/1002-main.jpg", 1, 0),
                    ],
                )
            conn.commit()
        finally:
            conn.close()

    def _call(self, method: str, path: str, body: dict | None = None, query: str = "") -> tuple[str, dict]:
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
            "REMOTE_ADDR": "127.0.0.1",
        }
        state: dict[str, object] = {"status": "", "headers": []}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            state["status"] = status
            state["headers"] = headers

        out = b"".join(self.gw(env, start_response))
        data = json.loads(out.decode("utf-8")) if out else {}
        return str(state["status"]), data

    def test_realistic_search_and_recommendation_surface_trust_differences(self) -> None:
        self._seed_search_profiles()

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                    "must_have": ["情绪稳定", "愿意沟通"],
                },
                "self_profile": {
                    "age": 30,
                    "city": "无锡",
                    "education": "本科",
                },
                "limit": 5,
                "photo_preview_count": 2,
            },
        )

        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 2)

        by_name = {item["name"]: item for item in payload["results"]}
        serious = by_name["林知夏"]
        packaged = by_name["苏曼"]

        serious_items = {item["key"]: item for item in serious["verification_items"]}
        packaged_items = {item["key"]: item for item in packaged["verification_items"]}

        self.assertGreater(serious["score"], packaged["score"])
        self.assertEqual(serious["verified_level"], "offline")
        self.assertEqual(serious["verified_label"], "线下核验")
        self.assertEqual(serious["photo_verification_level"], "offline_verified")
        self.assertEqual(serious["photo_verification_label"], "线下核验照片")
        self.assertEqual(serious_items["offline_check"]["status"], "verified")
        self.assertEqual(serious_items["photo"]["status"], "verified")
        self.assertEqual(len(serious["photo_preview"]), 2)
        self.assertIn("已线下核验", serious["trust_summary"]["headline"])
        self.assertEqual(serious["caution_items"], [])

        self.assertEqual(packaged["verified_level"], "basic")
        self.assertEqual(packaged["verified_label"], "基础认证")
        self.assertEqual(packaged["photo_verification_level"], "uploaded")
        self.assertEqual(packaged_items["identity"]["status"], "verified")
        self.assertEqual(packaged_items["photo"]["status"], "self_reported")
        self.assertEqual(packaged_items["job"]["status"], "needs_review")
        self.assertIn("资料填写为主", packaged["trust_summary"]["headline"])
        self.assertNotIn("已线下核验", packaged["trust_summary"]["headline"])
        self.assertGreaterEqual(len(packaged["caution_items"]), 1)
        self.assertGreaterEqual(len(packaged["trust_actions"]), 1)

        status, payload = self._call(
            "POST",
            "/v1/recommendation/subscriptions",
            {
                "requester_id": 70001,
                "title": "无锡认真恋爱验证",
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                    "must_have": ["情绪稳定", "愿意沟通"],
                },
                "self_profile": {"age": 30, "city": "无锡", "education": "本科"},
                "limit_count": 5,
                "top_k": 5,
                "min_notify_score": 40,
                "daily_notification_cap": 5,
                "quiet_hours_start": 23,
                "quiet_hours_end": 8,
                "refresh_interval_hours": 24,
                "recommendation_mode": "match_based",
                "now": "2026-05-05 10:00:00",
            },
        )

        self.assertTrue(status.startswith("201"), status)
        subscription_id = payload["subscription"]["subscription_id"]

        status, payload = self._call(
            "POST",
            f"/v1/recommendation/subscriptions/{subscription_id}/refresh",
            {"now": "2026-05-05 10:05:00"},
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 2)
        self.assertEqual(payload["status_counts"]["pending_delivery"], 2)
        self.assertEqual(payload["review_counts"]["match_ready"], 2)

        status, payload = self._call(
            "POST",
            "/v1/recommendation/deliver",
            {"now": "2026-05-05 10:10:00"},
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["delivered_count"], 2)

        status, payload = self._call(
            "GET",
            "/v1/recommendation/cards",
            query="requester_id=70001",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["cards"]), 2)

        serious_card = next(card for card in payload["cards"] if "林知夏" in card["title"])
        packaged_card = next(card for card in payload["cards"] if "苏曼" in card["title"])

        self.assertIn("线下核验", serious_card["subtitle"])
        self.assertIn("可信度：", serious_card["body"])
        self.assertIn("已线下核验", serious_card["body"])

        self.assertIn("普通上传照片", packaged_card["subtitle"])
        self.assertIn("可信度：", packaged_card["body"])
        self.assertIn("谨慎点：", packaged_card["body"])
        self.assertIn("资料填写为主", packaged_card["body"])
        self.assertNotIn("已线下核验", packaged_card["body"])

    def test_realistic_scam_flow_can_be_reported_reviewed_and_blocked(self) -> None:
        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-risk-realistic",
                "relation_key": "real-user-risk",
                "participant_a_id": "victim-1",
                "participant_b_id": "suspect-1",
                "now": "2026-05-05 10:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "suspect-1",
                "body": "先加微信，我带你投资，收益稳，转账后马上进群",
                "visibility": "dyadic",
                "now": "2026-05-05 10:01:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        message_id = payload["message"]["message_id"]

        status, payload = self._call(
            "GET",
            "/v1/chat/reports",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["reports"]), 1)
        self.assertEqual(payload["reports"][0]["report_source"], "system_rule")
        self.assertIn("investment", payload["reports"][0]["signal_codes"])
        self.assertIn("money_transfer", payload["reports"][0]["signal_codes"])
        self.assertIn("off_platform", payload["reports"][0]["signal_codes"])

        status, payload = self._call(
            "GET",
            "/v1/chat/risk-cases",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["risk_cases"]), 1)
        risk_case = payload["risk_cases"][0]
        self.assertEqual(risk_case["severity"], "high")
        self.assertEqual(risk_case["recommended_action"], "limit_chat")

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/reports",
            {
                "reporter_id": "victim-1",
                "report_type": "fraud",
                "reason_text": "对方让我转账进投资群",
                "message_id": message_id,
                "now": "2026-05-05 10:02:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        self.assertEqual(payload["report"]["report_source"], "user_report")
        self.assertEqual(payload["risk_case"]["report_count"], 2)
        self.assertEqual(payload["risk_case"]["recommended_action"], "limit_chat")

        status, payload = self._call(
            "GET",
            "/v1/chat/risk-signals",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        signal_codes = {item["signal_code"] for item in payload["risk_signals"]}
        self.assertIn("investment", signal_codes)
        self.assertIn("money_transfer", signal_codes)

        status, payload = self._call(
            "GET",
            f"/v1/chat/threads/{thread_id}/risk-overview",
            query="requester_id=victim-1",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_overview"]["counterpart_user_id"], "suspect-1")
        self.assertIn("请勿转账", "".join(payload["risk_overview"]["caution_messages"]))

        status, payload = self._call(
            "GET",
            f"/v1/chat/risk-cases/{risk_case['risk_case_id']}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["reports"]), 2)

        status, payload = self._call(
            "POST",
            f"/v1/chat/risk-cases/{risk_case['risk_case_id']}/review",
            {
                "resolver_id": "moderator-1",
                "status": "action_applied",
                "applied_action": "limit_chat",
                "resolution_note": "高风险诈骗话术，限制继续发言",
                "now": "2026-05-05 10:03:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_case"]["status"], "action_applied")
        self.assertEqual(payload["risk_case"]["applied_action"], "limit_chat")

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "suspect-1",
                "body": "我再给你发开户链接",
                "visibility": "dyadic",
                "now": "2026-05-05 10:04:00",
            },
        )
        self.assertTrue(status.startswith("400"), status)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertIn("restricted by risk action", payload["error"]["message"])

    def test_realistic_benign_boundary_messages_do_not_trigger_false_positive(self) -> None:
        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-benign-realistic",
                "relation_key": "real-user-benign",
                "participant_a_id": "user-a",
                "participant_b_id": "user-b",
                "now": "2026-05-05 11:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        for body in (
            "我在券商做投资研究，平时也看宏观",
            "这顿饭AA就行，车费我自己来",
        ):
            status, payload = self._call(
                "POST",
                f"/v1/chat/threads/{thread_id}/messages",
                {
                    "author_id": "user-b",
                    "body": body,
                    "visibility": "dyadic",
                    "now": "2026-05-05 11:01:00",
                },
            )
            self.assertTrue(status.startswith("201"), status)
            self.assertEqual(payload["message"]["body"], body)

        status, payload = self._call(
            "GET",
            "/v1/chat/reports",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["reports"], [])

        status, payload = self._call(
            "GET",
            "/v1/chat/risk-cases",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_cases"], [])


if __name__ == "__main__":
    unittest.main()
