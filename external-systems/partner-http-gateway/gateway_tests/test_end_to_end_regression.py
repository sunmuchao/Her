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
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"

for root in (GATEWAY_ROOT, CHAT_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

import outer_system_mysql_schema as mysql_schema  # noqa: E402

from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
)
from chat_system.async_tasks import run_chat_async_job_worker  # noqa: E402
from gateway.app import PartnerGateway  # noqa: E402
from matchmaking_system.async_tasks import run_matchmaking_async_job_worker  # noqa: E402
from recommendation_system.async_tasks import run_recommendation_async_job_worker  # noqa: E402
from matchmaking_system.storage import (  # noqa: E402
    DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
    connect_db as connect_matchmaking_db,
    initialize_database as initialize_matchmaking_db,
    reset_all_tables as reset_matchmaking_tables,
)
from recommendation_system import create_match_case  # noqa: E402
from recommendation_system.storage import (  # noqa: E402
    DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
    connect_db as connect_recommendation_db,
    initialize_database as initialize_recommendation_db,
    reset_all_tables as reset_recommendation_tables,
)


DEFAULT_E2E_SEARCH_TEST_DSN = os.environ.get(
    "PARTNER_SEARCH_E2E_TEST_DB",
    os.environ.get(
        "PARTNER_SEARCH_REALISTIC_TEST_DB",
        "mysql://root@127.0.0.1:3307/her_partner_search_realistic_test?table=profiles&photos_table=profile_photos",
    ),
)

STATIC_TOKENS = json.dumps(
    {
        "token-ops": {
            "actor_id": "ops-1",
            "roles": ["ops_operator", "service_worker"],
        },
        "token-user-a": {"actor_id": "user-a", "roles": ["end_user"]},
        "token-user-b": {"actor_id": "user-b", "roles": ["end_user"]},
        "token-requester-70001": {"actor_id": "70001", "roles": ["end_user"]},
    }
)


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class GatewayEndToEndRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.search_dsn = DEFAULT_E2E_SEARCH_TEST_DSN
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
        self._old_static_tokens = os.environ.get("PARTNER_GATEWAY_STATIC_TOKENS_JSON")
        os.environ["PARTNER_GATEWAY_STATIC_TOKENS_JSON"] = STATIC_TOKENS

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

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )

    def tearDown(self) -> None:
        if self._old_static_tokens is None:
            os.environ.pop("PARTNER_GATEWAY_STATIC_TOKENS_JSON", None)
        else:
            os.environ["PARTNER_GATEWAY_STATIC_TOKENS_JSON"] = self._old_static_tokens

    def _reset_search_rows(self) -> None:
        conn = self._search_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM `profile_photos`")
                cursor.execute("DELETE FROM `profiles`")
            conn.commit()
        finally:
            conn.close()

    def _insert_search_profile(self, row: tuple) -> None:
        conn = self._search_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
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
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    row,
                )
            conn.commit()
        finally:
            conn.close()

    def _seed_matchmaking_profiles(self) -> None:
        active_at = datetime(2026, 5, 6, 9, 0, 0)
        self._insert_search_profile(
            (
                2001,
                "周明",
                "男",
                30,
                "无锡",
                "本科",
                "产品经理",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
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
                "愿意长期关系",
                "靠谱稳定",
                active_at,
            )
        )
        self._insert_search_profile(
            (
                2002,
                "许宁",
                "女",
                28,
                "无锡",
                "本科",
                "设计师",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
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
                "愿意长期关系",
                "同城稳定",
                active_at,
            )
        )

    def _seed_recommendation_profiles(self) -> None:
        active_at = datetime(2026, 5, 7, 10, 0, 0)
        self._insert_search_profile(
            (
                3002,
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
                "情绪稳定，认真长期关系",
                active_at,
            )
        )

    def _call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        query: str = "",
        token: str | None = None,
    ) -> tuple[str, dict]:
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
            "REMOTE_ADDR": "127.0.0.1",
            **_auth_headers(token),
        }
        state: dict[str, object] = {"status": "", "headers": []}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            state["status"] = status
            state["headers"] = headers

        out = b"".join(self.gw(env, start_response))
        data = json.loads(out.decode("utf-8")) if out else {}
        return str(state["status"]), data

    def _run_matchmaking_async_jobs(self) -> dict:
        conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            return run_matchmaking_async_job_worker(conn, limit=10)
        finally:
            conn.close()

    def _run_recommendation_async_jobs(self) -> dict:
        conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            return run_recommendation_async_job_worker(conn, limit=10)
        finally:
            conn.close()

    def _run_chat_async_jobs(self) -> dict:
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return run_chat_async_job_worker(conn, limit=10)
        finally:
            conn.close()

    def test_end_to_end_matchmaking_case_can_flow_into_chat_timeline(self) -> None:
        self._seed_matchmaking_profiles()

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/members",
            {
                "user_key": "user-a",
                "source": self.search_dsn,
                "self_id": 2001,
                "search_criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 30, "city": "无锡", "education": "本科"},
                "min_pair_score": 1,
                "limit_count": 5,
                "refresh_interval_hours": 24,
                "now": "2026-05-06 09:00:00",
            },
            token="token-user-a",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/members",
            {
                "user_key": "user-b",
                "source": self.search_dsn,
                "self_id": 2002,
                "search_criteria": {
                    "gender": "男",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 28, "city": "无锡", "education": "本科"},
                "min_pair_score": 1,
                "limit_count": 5,
                "refresh_interval_hours": 24,
                "now": "2026-05-06 09:00:00",
            },
            token="token-user-b",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/pool/refresh",
            {"now": "2026-05-06 09:05:00"},
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        refresh_job_id = payload["job"]["job_id"]
        worker_out = self._run_matchmaking_async_jobs()
        self.assertEqual(worker_out["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/matchmaking/jobs/{refresh_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(len(payload["job"]["result"]), 2)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/pairs/build",
            {"now": "2026-05-06 09:06:00"},
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        pairs_job_id = payload["job"]["job_id"]
        worker_out = self._run_matchmaking_async_jobs()
        self.assertEqual(worker_out["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/matchmaking/jobs/{pairs_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(len(payload["job"]["result"]), 1)
        pair_key = payload["job"]["result"][0]["pair_key"]

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/cases/open",
            {"now": "2026-05-06 09:07:00"},
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        open_job_id = payload["job"]["job_id"]
        worker_out = self._run_matchmaking_async_jobs()
        self.assertEqual(worker_out["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/matchmaking/jobs/{open_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(len(payload["job"]["result"]), 1)
        case_id = payload["job"]["result"][0]["case_id"]

        status, payload = self._call(
            "GET",
            "/v1/ops/async-jobs/dashboard",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        matchmaking_types = payload["systems"]["matchmaking"]["job_types"]
        self.assertEqual(
            {item["job_type"] for item in matchmaking_types},
            {
                "matchmaking.refresh_active_pool",
                "matchmaking.build_mutual_pairs",
                "matchmaking.open_match_cases",
            },
        )
        self.assertTrue(all(item["by_status"]["succeeded"] == 1 for item in matchmaking_types))

        status, payload = self._call(
            "POST",
            f"/v1/matchmaking/cases/{case_id}/dispatch",
            {"now": "2026-05-06 09:08:00"},
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["case"]["status"], "awaiting_first_reply")

        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": case_id,
                "relation_key": pair_key,
                "participant_a_id": "user-a",
                "participant_b_id": "user-b",
                "now": "2026-05-06 09:09:00",
            },
            token="token-ops",
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "user-a",
                "body": "你好，我看了案例卡片，想先了解一下你的工作节奏。",
                "now": "2026-05-06 09:10:00",
            },
            token="token-user-a",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "user-b",
                "body": "我一般工作日忙一点，周末时间比较固定，也愿意见面。",
                "now": "2026-05-06 09:11:00",
            },
            token="token-user-b",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "GET",
            f"/v1/matchmaking/cases/{case_id}",
            token="token-user-a",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["case"]["case_id"], case_id)

        status, payload = self._call(
            "GET",
            "/v1/timeline",
            query=f"case_id={case_id}&viewer_id=user-a&message_limit=20",
            token="token-user-a",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["chat"]["thread"]["thread_id"], thread_id)
        self.assertEqual(len(payload["chat"]["messages"]), 2)
        self.assertEqual(payload["matchmaking"]["case"]["case_id"], case_id)
        self.assertGreaterEqual(len(payload["matchmaking"]["events"]), 2)
        self.assertIsNone(payload["recommendation"]["case"])

    def test_end_to_end_recommendation_proxy_case_can_flow_into_timeline(self) -> None:
        self._seed_recommendation_profiles()

        status, payload = self._call(
            "POST",
            "/v1/recommendation/subscriptions",
            {
                "requester_id": 70001,
                "title": "无锡认真恋爱候选池",
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 30, "city": "无锡", "education": "本科"},
                "limit_count": 5,
                "top_k": 5,
                "min_notify_score": 1,
                "daily_notification_cap": 5,
                "quiet_hours_start": 23,
                "quiet_hours_end": 8,
                "refresh_interval_hours": 24,
                "recommendation_mode": "match_based",
                "now": "2026-05-07 10:00:00",
            },
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("201"), status)
        subscription_id = payload["subscription"]["subscription_id"]

        status, payload = self._call(
            "POST",
            f"/v1/recommendation/subscriptions/{subscription_id}/refresh",
            {"now": "2026-05-07 10:05:00"},
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/recommendation/subscriptions/{subscription_id}/recommendations",
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["recommendations"]), 1)
        candidate_id = payload["recommendations"][0]["candidate_id"]

        rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            recommendation_case = create_match_case(
                rec_conn,
                subscription_id=subscription_id,
                candidate_id=candidate_id,
                now=datetime(2026, 5, 7, 10, 10, 0),
            )
        finally:
            rec_conn.close()
        case_id = recommendation_case["case_id"]

        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": case_id,
                "relation_key": f"proxy-intro:{subscription_id}:{candidate_id}",
                "participant_a_id": "70001",
                "participant_b_id": f"candidate-{candidate_id}",
                "now": "2026-05-07 10:11:00",
            },
            token="token-ops",
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "70001",
                "body": "如果方便的话，我愿意先从平台内了解一下她的节奏。",
                "now": "2026-05-07 10:12:00",
            },
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "GET",
            "/v1/timeline",
            query=f"case_id={case_id}&viewer_id=70001&message_limit=20",
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["chat"]["thread"]["thread_id"], thread_id)
        self.assertEqual(len(payload["chat"]["messages"]), 1)
        self.assertIsNone(payload["matchmaking"]["case"])
        self.assertEqual(payload["recommendation"]["case"]["case_id"], case_id)
        self.assertGreaterEqual(len(payload["recommendation"]["events"]), 1)

    def test_end_to_end_async_jobs_are_observable_across_three_systems(self) -> None:
        self._seed_recommendation_profiles()
        self._seed_matchmaking_profiles()

        status, payload = self._call(
            "POST",
            "/v1/recommendation/subscriptions",
            {
                "requester_id": 70001,
                "title": "无锡认真恋爱候选池",
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 30, "city": "无锡", "education": "本科"},
                "limit_count": 5,
                "top_k": 5,
                "min_notify_score": 1,
                "daily_notification_cap": 5,
                "quiet_hours_start": 23,
                "quiet_hours_end": 8,
                "refresh_interval_hours": 24,
                "recommendation_mode": "match_based",
                "now": "2026-05-08 10:00:00",
            },
            token="token-requester-70001",
        )
        self.assertTrue(status.startswith("201"), status)
        subscription_id = payload["subscription"]["subscription_id"]

        status, payload = self._call(
            "POST",
            "/v1/recommendation/subscriptions/refresh-due",
            {
                "subscription_ids": [subscription_id],
                "now": "2026-05-08 10:05:00",
            },
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        recommendation_job_id = payload["job"]["job_id"]
        recommendation_worker = self._run_recommendation_async_jobs()
        self.assertEqual(recommendation_worker["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/recommendation/jobs/{recommendation_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(len(payload["job"]["result"]["summaries"]), 1)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/members",
            {
                "user_key": "user-a",
                "source": self.search_dsn,
                "self_id": 2001,
                "search_criteria": {
                    "gender": "女",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 30, "city": "无锡", "education": "本科"},
                "min_pair_score": 1,
                "limit_count": 5,
                "refresh_interval_hours": 24,
                "now": "2026-05-08 10:06:00",
            },
            token="token-user-a",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/members",
            {
                "user_key": "user-b",
                "source": self.search_dsn,
                "self_id": 2002,
                "search_criteria": {
                    "gender": "男",
                    "cities": ["无锡"],
                    "relationship_goals": ["认真恋爱", "结婚导向"],
                },
                "self_profile": {"age": 28, "city": "无锡", "education": "本科"},
                "min_pair_score": 1,
                "limit_count": 5,
                "refresh_interval_hours": 24,
                "now": "2026-05-08 10:06:00",
            },
            token="token-user-b",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/matchmaking/pool/refresh",
            {"now": "2026-05-08 10:07:00"},
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        matchmaking_job_id = payload["job"]["job_id"]
        matchmaking_worker = self._run_matchmaking_async_jobs()
        self.assertEqual(matchmaking_worker["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/matchmaking/jobs/{matchmaking_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(len(payload["job"]["result"]), 2)

        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-async-dashboard-1",
                "relation_key": "async-dashboard:1",
                "participant_a_id": "user-a",
                "participant_b_id": "user-b",
                "now": "2026-05-08 10:08:00",
            },
            token="token-ops",
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "user-a",
                "body": "先打个招呼，看看 maintenance 和摘要链路。",
                "now": "2026-05-08 10:09:00",
            },
            token="token-user-a",
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/chat/maintenance/run",
            {
                "persona_limit": 5,
                "summary_max_threads": 10,
            },
            token="token-ops",
        )
        self.assertTrue(status.startswith("202"), status)
        chat_job_id = payload["job"]["job_id"]
        chat_worker = self._run_chat_async_jobs()
        self.assertEqual(chat_worker["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/chat/jobs/{chat_job_id}",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")

        status, payload = self._call(
            "GET",
            "/v1/ops/async-jobs/dashboard",
            token="token-ops",
        )
        self.assertTrue(status.startswith("200"), status)
        dashboard = payload
        self.assertGreaterEqual(dashboard["totals"]["succeeded"], 3)
        self.assertEqual(dashboard["totals"]["backlog_open"], 0)

        recommendation_types = {
            item["job_type"]: item for item in dashboard["systems"]["recommendation"]["job_types"]
        }
        self.assertEqual(
            recommendation_types["recommendation.refresh_due_subscriptions"]["by_status"]["succeeded"],
            1,
        )

        matchmaking_types = {
            item["job_type"]: item for item in dashboard["systems"]["matchmaking"]["job_types"]
        }
        self.assertEqual(
            matchmaking_types["matchmaking.refresh_active_pool"]["by_status"]["succeeded"],
            1,
        )

        chat_types = {
            item["job_type"]: item for item in dashboard["systems"]["chat"]["job_types"]
        }
        self.assertEqual(chat_types["chat.run_maintenance"]["by_status"]["succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
