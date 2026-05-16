from __future__ import annotations

import base64
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"

for root in (GATEWAY_ROOT, CHAT_ROOT, RECOMMENDATION_ROOT, REPO_ROOT):
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
    call_gateway_json,
    ensure_search_schema,
    insert_search_profile,
    insert_search_profiles,
    open_search_conn,
    reset_search_rows,
    search_test_config,
)
from recommendation_system.async_tasks import run_recommendation_async_job_worker  # noqa: E402
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
        cls.search_config = search_test_config(cls.search_dsn)
        cls._ensure_search_schema()

    @classmethod
    def _search_conn(cls):
        return open_search_conn(cls.search_config)

    @classmethod
    def _ensure_search_schema(cls) -> None:
        ensure_search_schema(cls.search_config)

    def setUp(self) -> None:
        self._reset_search_rows()
        self._verification_tempdir = tempfile.TemporaryDirectory()
        self._old_verification_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
        self._old_verification_provider = os.environ.get("HER_VERIFICATION_PROVIDER")
        self._old_verification_auto_triage = os.environ.get("HER_VERIFICATION_AUTO_TRIAGE")
        os.environ["HER_VERIFICATION_STORAGE_DIR"] = self._verification_tempdir.name
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        os.environ["HER_VERIFICATION_AUTO_TRIAGE"] = "1"

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

    def tearDown(self) -> None:
        if self._old_verification_storage_dir is None:
            os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
        else:
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = self._old_verification_storage_dir
        if self._old_verification_provider is None:
            os.environ.pop("HER_VERIFICATION_PROVIDER", None)
        else:
            os.environ["HER_VERIFICATION_PROVIDER"] = self._old_verification_provider
        if self._old_verification_auto_triage is None:
            os.environ.pop("HER_VERIFICATION_AUTO_TRIAGE", None)
        else:
            os.environ["HER_VERIFICATION_AUTO_TRIAGE"] = self._old_verification_auto_triage
        self._verification_tempdir.cleanup()

    def _reset_search_rows(self) -> None:
        reset_search_rows(self.search_config)

    def _seed_search_profiles(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        insert_search_profiles(
            self.search_config,
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
        conn = self._search_conn()
        try:
            with conn.cursor() as cursor:
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

    def _insert_search_profile(self, row: tuple) -> None:
        insert_search_profile(self.search_config, row)

    def _call(self, method: str, path: str, body: dict | None = None, query: str = "") -> tuple[str, dict]:
        return call_gateway_json(self.gw, method, path, body=body, query=query)

    def _run_recommendation_async_jobs(self) -> dict:
        conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            return run_recommendation_async_job_worker(conn, limit=10)
        finally:
            conn.close()

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
        self.assertIn("资料存在待复核或不一致信号", packaged["risk_flags"])
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
        self.assertTrue(status.startswith("202"), status)
        deliver_job_id = payload["job"]["job_id"]
        worker_out = self._run_recommendation_async_jobs()
        self.assertEqual(worker_out["success_count"], 1)

        status, payload = self._call(
            "GET",
            f"/v1/recommendation/jobs/{deliver_job_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(payload["job"]["result"]["delivered_count"], 2)

        status, payload = self._call(
            "GET",
            "/v1/ops/async-jobs/dashboard",
        )
        self.assertTrue(status.startswith("200"), status)
        recommendation_types = payload["systems"]["recommendation"]["job_types"]
        deliver_summary = next(item for item in recommendation_types if item["job_type"] == "recommendation.deliver_in_app_recommendations")
        self.assertEqual(deliver_summary["by_status"]["succeeded"], 1)
        self.assertEqual(deliver_summary["backlog_open"], 0)

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

    def test_realistic_search_can_raise_trust_thresholds_to_filter_packaged_profiles(self) -> None:
        self._seed_search_profiles()

        for extra_criteria in (
            {"verified_level_min": "photo"},
            {"photo_verification_level_min": "live_video_verified"},
        ):
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
                        **extra_criteria,
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
            self.assertEqual(payload["result_count"], 1)
            self.assertEqual([item["name"] for item in payload["results"]], ["林知夏"])
            kept = payload["results"][0]
            self.assertEqual(kept["verified_level"], "offline")
            self.assertEqual(kept["photo_verification_level"], "offline_verified")
            self.assertIn("已线下核验", kept["trust_summary"]["headline"])

    def test_realistic_photo_review_request_flow_can_link_report_resubmission_and_notifications(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        self._insert_search_profile(
            (
                2010,
                "陆清筠",
                "女",
                30,
                "上海",
                "本科",
                "品牌运营",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "id",
                "uploaded",
                "verified",
                "verified",
                "self_reported",
                "approved",
                0,
                4,
                "生活规律",
                "沟通温和",
                "希望认真沟通",
                "照片等待复核",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
                "limit": 5,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 0)

        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-photo-review-realistic",
                "relation_key": "photo-review-realistic",
                "participant_a_id": "reviewer-10",
                "participant_b_id": "candidate-2010",
                "metadata": {
                    "participant_profiles": {
                        "candidate-2010": {
                            "profile_id": 2010,
                            "source_dsn": self.search_dsn,
                            "source_table_name": "profiles",
                        }
                    }
                },
                "now": "2026-05-05 10:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/reports",
            {
                "reporter_id": "reviewer-10",
                "report_type": "suspected_fake_photo",
                "reason_text": "感觉照片和真人差异较大",
                "reported_profile_id": 2010,
                "reported_source_dsn": self.search_dsn,
                "reported_source_table_name": "profiles",
                "now": "2026-05-05 10:03:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        risk_case_id = payload["risk_case"]["risk_case_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/risk-cases/{risk_case_id}/review",
            {
                "resolver_id": "moderator-10",
                "status": "action_applied",
                "applied_action": "require_verification",
                "resolution_note": "请补录真人活体视频完成复核",
                "now": "2026-05-05 10:05:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_case"]["applied_action"], "require_verification")

        status, payload = self._call(
            "GET",
            "/v1/verifications/live-video-requests",
            query="user_id=candidate-2010",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["requests"]), 1)
        request = payload["requests"][0]
        submission_id = request["submission_id"]
        self.assertEqual(request["status"], "awaiting_submission")
        self.assertEqual(request["photo_review_task"]["linked_risk_case_ids"], [risk_case_id])

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-submissions",
            {
                "submission_id": submission_id,
                "user_id": "candidate-2010",
                "profile_id": 2010,
                "source_dsn": self.search_dsn,
                "video_base64": base64.b64encode(b"photo-review-first").decode("ascii"),
                "file_name": "photo-review-first.mp4",
                "content_type": "video/mp4",
                "metadata": {
                    "machine_review_inputs": {
                        "liveness_score": 42,
                        "face_match_score": 88,
                        "challenge_score": 35,
                    }
                },
                "now": "2026-05-05 10:10:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        first = payload["submission"]
        self.assertEqual(first["submission_id"], submission_id)
        self.assertEqual(first["status"], "resubmission_required")

        status, payload = self._call(
            "GET",
            "/v1/verifications/notifications",
            query=f"submission_id={submission_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        first_notification_types = {item["notification_type"] for item in payload["notifications"]}
        self.assertIn("photo_review_requested", first_notification_types)
        self.assertIn("photo_review_resubmission_required", first_notification_types)

        status, payload = self._call(
            "POST",
            f"/v1/verifications/live-video-submissions/{submission_id}/resubmit",
            {
                "user_id": "candidate-2010",
                "video_base64": base64.b64encode(b"photo-review-second").decode("ascii"),
                "file_name": "photo-review-second.mp4",
                "content_type": "video/mp4",
                "metadata": {
                    "machine_review_inputs": {
                        "liveness_score": 96,
                        "face_match_score": 94,
                        "challenge_score": 91,
                    }
                },
                "now": "2026-05-05 10:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        approved = payload["submission"]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["profile_sync"]["status"], "synced")

        status, payload = self._call(
            "GET",
            f"/v1/verifications/live-video-requests/{submission_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        request_detail = payload["request"]
        self.assertEqual(request_detail["status"], "approved")

        status, payload = self._call(
            "GET",
            "/v1/verifications/notifications",
            query=f"submission_id={submission_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        notification_types = {item["notification_type"] for item in payload["notifications"]}
        self.assertIn("photo_review_requested", notification_types)
        self.assertIn("photo_review_resubmission_required", notification_types)
        self.assertIn("photo_review_approved", notification_types)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
                "limit": 5,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["name"], "陆清筠")
        self.assertEqual(payload["results"][0]["photo_verification_level"], "live_video_verified")

    def test_realistic_live_video_verification_submission_review_and_resubmission_flow(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        self._insert_search_profile(
            (
                2001,
                "陈南栀",
                "女",
                30,
                "上海",
                "本科",
                "品牌策划",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "id",
                "uploaded",
                "verified",
                "verified",
                "self_reported",
                "approved",
                0,
                4,
                "生活规律",
                "主动沟通",
                "认真恋爱，愿意沟通",
                "资料完整，照片未做真人核验",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
                "limit": 5,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 0)

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-submissions",
            {
                "user_id": "candidate-2001",
                "profile_id": 2001,
                "source_dsn": self.search_dsn,
                "video_base64": base64.b64encode(b"first-video").decode("ascii"),
                "file_name": "first-selfie.mp4",
                "content_type": "video/mp4",
                "challenge_phrase": "第一次补真人视频",
                "metadata": {
                    "device": "ios",
                    "machine_review_inputs": {
                        "liveness_score": 45,
                        "face_match_score": 86,
                        "challenge_score": 38,
                    },
                },
                "now": "2026-05-05 10:10:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        submission = payload["submission"]
        submission_id = submission["submission_id"]
        self.assertEqual(submission["status"], "resubmission_required")
        self.assertEqual(submission["review_decision"], "request_resubmission")
        self.assertEqual(submission["recommended_next_step"], "retry_live_video")
        self.assertEqual(submission["assets"][0]["upload_attempt"], 1)
        stored_path = pathlib.Path(self._verification_tempdir.name) / submission["assets"][0]["storage_key"]
        self.assertTrue(stored_path.exists())

        status, payload = self._call(
            "POST",
            f"/v1/verifications/live-video-submissions/{submission_id}/resubmit",
            {
                "user_id": "candidate-2001",
                "video_base64": base64.b64encode(b"second-video").decode("ascii"),
                "file_name": "second-selfie.mp4",
                "content_type": "video/mp4",
                "challenge_phrase": "第二次补真人视频",
                "metadata": {
                    "device": "ios",
                    "retry": 1,
                    "machine_review_inputs": {
                        "liveness_score": 95,
                        "face_match_score": 92,
                        "challenge_score": 90,
                    },
                },
                "now": "2026-05-05 10:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        approved = payload["submission"]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["review_decision"], "approve")
        self.assertEqual(approved["latest_sync_status"], "synced")
        self.assertEqual(approved["profile_sync"]["status"], "synced")
        self.assertEqual(approved["resubmission_count"], 1)
        self.assertEqual(len(approved["assets"]), 2)
        self.assertEqual(len(approved["reviews"]), 2)

        status, payload = self._call(
            "GET",
            f"/v1/verifications/live-video-submissions/{submission_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["submission"]["status"], "approved")
        self.assertEqual(len(payload["submission"]["reviews"]), 2)
        self.assertEqual(payload["submission"]["machine_review"]["attempt"], 2)

        status, payload = self._call(
            "GET",
            "/v1/verifications/live-video-submissions",
            query="user_id=candidate-2001&status=approved",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["submissions"]), 1)
        self.assertEqual(payload["submissions"][0]["submission_id"], submission_id)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
                "limit": 5,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["name"], "陈南栀")
        self.assertEqual(payload["results"][0]["photo_verification_level"], "live_video_verified")

    def test_realistic_live_video_verification_can_auto_approve_first_shot(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        self._insert_search_profile(
            (
                2002,
                "沈清和",
                "女",
                29,
                "上海",
                "硕士",
                "用户研究",
                "30-50万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "id",
                "uploaded",
                "verified",
                "verified",
                "verified",
                "approved",
                0,
                5,
                "作息规律",
                "直接坦诚",
                "愿意慢慢了解",
                "资料完整，等待真人核验",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-submissions",
            {
                "user_id": "candidate-2002",
                "profile_id": 2002,
                "source_dsn": self.search_dsn,
                "video_base64": base64.b64encode(b"auto-approve-video").decode("ascii"),
                "file_name": "first-shot.mp4",
                "content_type": "video/mp4",
                "challenge_phrase": "请眨眼并读出今天日期",
                "metadata": {
                    "device": "ios",
                    "machine_review_inputs": {
                        "liveness_score": 97,
                        "face_match_score": 95,
                        "challenge_score": 93,
                        "risk_flags": [],
                    },
                },
                "now": "2026-05-05 10:12:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        submission = payload["submission"]
        self.assertEqual(submission["status"], "approved")
        self.assertEqual(submission["review_decision"], "approve")
        self.assertEqual(submission["reviewer_id"], "system:auto_verification")
        self.assertEqual(submission["recommended_next_step"], "complete")
        self.assertEqual(submission["profile_sync"]["status"], "synced")

    def test_realistic_live_video_verification_can_escalate_to_strong_identity(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        self._insert_search_profile(
            (
                2003,
                "许雾",
                "女",
                31,
                "上海",
                "本科",
                "产品运营",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "id",
                "uploaded",
                "verified",
                "verified",
                "self_reported",
                "approved",
                0,
                4,
                "生活规律",
                "愿意沟通",
                "希望高质量沟通",
                "资料等待真人核验",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-submissions",
            {
                "user_id": "candidate-2003",
                "profile_id": 2003,
                "source_dsn": self.search_dsn,
                "video_base64": base64.b64encode(b"risk-video").decode("ascii"),
                "file_name": "risk-selfie.mp4",
                "content_type": "video/mp4",
                "challenge_phrase": "请抬头眨眼",
                "metadata": {
                    "device": "android",
                    "machine_review_inputs": {
                        "liveness_score": 93,
                        "face_match_score": 22,
                        "challenge_score": 91,
                        "risk_flags": ["deepfake_risk"],
                    },
                },
                "now": "2026-05-05 10:18:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        submission = payload["submission"]
        self.assertEqual(submission["status"], "under_review")
        self.assertEqual(submission["recommended_decision"], "manual_review")
        self.assertEqual(submission["recommended_next_step"], "strong_identity")
        self.assertEqual(submission["review_decision"], None)
        self.assertEqual(len(submission["reviews"]), 0)

    def test_realistic_live_video_realtime_challenge_can_issue_and_complete(self) -> None:
        active_at = datetime(2026, 5, 5, 10, 0, 0)
        self._insert_search_profile(
            (
                2004,
                "周既白",
                "女",
                28,
                "上海",
                "本科",
                "内容策划",
                "20-30万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "id",
                "uploaded",
                "verified",
                "verified",
                "verified",
                "approved",
                0,
                4,
                "生活规律",
                "沟通直接",
                "认真沟通",
                "资料完整，等待实时活体验证",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-challenges",
            {
                "user_id": "candidate-2004",
                "profile_id": 2004,
                "challenge_actions": ["blink", "open_mouth", "turn_left"],
                "now": "2026-05-05 10:10:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        challenge = payload["challenge"]
        self.assertEqual(challenge["required_actions"], ["blink", "open_mouth", "turn_left"])
        self.assertRegex(
            challenge["challenge_phrase"],
            r"^请依次完成：眨眼、张嘴、向左转头；并大声读出数字 \d{2}$",
        )
        self.assertRegex(challenge["spoken_code"], r"^\d{2}$")
        self.assertEqual(len(challenge["prompt_steps"]), 4)

        status, payload = self._call(
            "POST",
            "/v1/verifications/live-video-submissions",
            {
                "user_id": "candidate-2004",
                "profile_id": 2004,
                "source_dsn": self.search_dsn,
                "video_base64": base64.b64encode(b"realtime-proof-video").decode("ascii"),
                "file_name": "realtime-proof.mp4",
                "content_type": "video/mp4",
                "challenge_token": challenge["challenge_token"],
                "metadata": {
                    "action_result": {
                        "capture_mode": "realtime_challenge",
                        "completed_actions": ["blink", "open_mouth", "turn_left"],
                        "action_events": [
                            {"action": "blink", "step_index": 1, "detected_at_ms": 680, "score": 96},
                            {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1460, "score": 94},
                            {"action": "turn_left", "step_index": 3, "detected_at_ms": 2190, "score": 92},
                        ],
                        "action_scores": {
                            "blink": 96,
                            "open_mouth": 94,
                            "turn_left": 92,
                        },
                        "face_count_max": 1,
                        "challenge_phrase_rendered": True,
                        "spoken_prompt_rendered": True,
                        "spoken_prompt_display_ms": 1850,
                        "audio_recorded": True,
                        "recording_duration_ms": 4300,
                        "video_recorded": True,
                    },
                    "machine_review_inputs": {
                        "face_match_score": 95,
                    },
                    "speech_challenge_result": {
                        "provider": "unit_test_asr",
                        "transcript_text": challenge["spoken_code"],
                        "transcript_confidence": 95,
                        "speech_started_at_ms": 2480,
                        "speech_ended_at_ms": 3260,
                        "audio_video_sync_score": 82,
                    },
                },
                "now": "2026-05-05 10:11:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        submission = payload["submission"]
        self.assertEqual(submission["status"], "approved")
        self.assertEqual(submission["reviewer_id"], "system:auto_verification")
        self.assertRegex(
            submission["challenge_phrase"],
            r"^请依次完成：眨眼、张嘴、向左转头；并大声读出数字 \d{2}$",
        )
        self.assertEqual(submission["machine_review"]["capture_mode"], "realtime_challenge")
        self.assertEqual(submission["machine_review"]["speech_result"], "pass")
        self.assertEqual(submission["recommended_next_step"], "complete")
        self.assertEqual(
            submission["metadata"]["action_challenge"]["spoken_code"],
            challenge["spoken_code"],
        )

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
                "limit": 5,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 1)
        self.assertEqual(payload["results"][0]["name"], "周既白")

    def test_realistic_meeting_feedback_turns_mismatch_into_verification_followup(self) -> None:
        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-meeting-realistic",
                "relation_key": "real-user-meeting-feedback",
                "participant_a_id": "reviewer-1",
                "participant_b_id": "candidate-1",
                "now": "2026-05-05 12:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/meeting-feedback",
            {
                "reviewer_id": "reviewer-1",
                "photo_match_status": "heavily_edited",
                "profile_consistency_status": "hidden_info",
                "income_job_consistency_status": "exaggerated",
                "willing_video_status": "refused",
                "notes": "照片修得很重，职业和收入都比资料里夸张，也一直回避视频。",
                "now": "2026-05-05 12:30:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        self.assertEqual(payload["feedback"]["counterpart_user_id"], "candidate-1")
        report_types = {item["report_type"] for item in payload["generated_reports"]}
        self.assertEqual(
            report_types,
            {"photo_mismatch", "profile_mismatch", "income_mismatch", "video_refusal"},
        )
        self.assertEqual(len(payload["risk_cases"]), 1)
        self.assertEqual(payload["risk_cases"][0]["recommended_action"], "require_verification")

        status, payload = self._call(
            "GET",
            "/v1/chat/meeting-feedback",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["meeting_feedback"]), 1)
        feedback = payload["meeting_feedback"][0]
        self.assertEqual(feedback["willing_video_status"], "refused")
        self.assertEqual(len(feedback["derived_report_ids"]), 4)

        status, payload = self._call(
            "GET",
            "/v1/chat/reports",
            query=f"thread_id={thread_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["reports"]), 4)
        self.assertTrue(all(item["report_source"] == "user_report" for item in payload["reports"]))

        status, payload = self._call(
            "GET",
            f"/v1/chat/threads/{thread_id}/risk-overview",
            query="requester_id=reviewer-1",
        )
        self.assertTrue(status.startswith("200"), status)
        caution = "".join(payload["risk_overview"]["caution_messages"])
        self.assertIn("资料一致性风险", caution)
        self.assertIn("回避视频", caution)

    def test_profile_review_and_field_verification_can_limit_and_restore_exposure(self) -> None:
        active_at = datetime(2026, 5, 5, 14, 0, 0)
        self._insert_search_profile(
            (
                3001,
                "赵清禾",
                "女",
                31,
                "无锡",
                "本科",
                "行政助理",
                "120-150万/年",
                "未婚",
                0,
                "结婚导向",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                3,
                3,
                "生活规律",
                "主动沟通",
                "认真找对象，但资料最近改动比较多",
                "收入写得很高，岗位描述偏基础，近期改动频繁",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["无锡"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertIn("赵清禾", [item["name"] for item in payload["results"]])

        status, payload = self._call(
            "POST",
            "/v1/profile-review/risk-cases/evaluate",
            {
                "profile_id": 3001,
                "source_dsn": self.search_dsn,
                "subject_user_id": "candidate-3001",
                "now": "2026-05-05 14:05:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        risk_case = payload["risk_case"]
        self.assertEqual(risk_case["recommended_action"], "limited_exposure")
        self.assertEqual(risk_case["severity"], "high")
        rule_codes = {item["rule_code"] for item in payload["rule_hits"]}
        self.assertIn("income_job_mismatch", rule_codes)
        self.assertIn("frequent_profile_changes", rule_codes)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["无锡"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertNotIn("赵清禾", [item["name"] for item in payload["results"]])

        status, payload = self._call(
            "POST",
            "/v1/profile-verifications/submissions",
            {
                "field_key": "job",
                "profile_id": 3001,
                "source_dsn": self.search_dsn,
                "subject_user_id": "candidate-3001",
                "declared_value": "行政主管",
                "evidence": {"doc_type": "employment_letter"},
                "now": "2026-05-05 14:10:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        job_submission_id = payload["submission"]["submission_id"]
        self.assertEqual(payload["submission"]["status"], "submitted")

        status, payload = self._call(
            "POST",
            f"/v1/profile-verifications/submissions/{job_submission_id}/review",
            {
                "reviewer_id": "moderator-1",
                "decision": "approve",
                "approved_value": "行政主管",
                "review_note": "岗位证明与补充说明一致",
                "now": "2026-05-05 14:12:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["submission"]["status"], "approved")

        status, payload = self._call(
            "POST",
            "/v1/profile-verifications/submissions",
            {
                "field_key": "income",
                "profile_id": 3001,
                "source_dsn": self.search_dsn,
                "subject_user_id": "candidate-3001",
                "declared_value": "50-80万/年",
                "evidence": {"doc_type": "payslip_bundle"},
                "now": "2026-05-05 14:13:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        income_submission_id = payload["submission"]["submission_id"]

        status, payload = self._call(
            "POST",
            f"/v1/profile-verifications/submissions/{income_submission_id}/review",
            {
                "reviewer_id": "moderator-2",
                "decision": "approve",
                "approved_value": "50-80万/年",
                "review_note": "收入区间按材料核到 50-80 万",
                "now": "2026-05-05 14:15:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["submission"]["status"], "approved")

        status, payload = self._call(
            "POST",
            f"/v1/profile-review/risk-cases/{risk_case['profile_review_case_id']}/review",
            {
                "resolver_id": "moderator-3",
                "status": "resolved",
                "resolution_note": "补件完成，恢复正常曝光",
                "now": "2026-05-05 14:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_case"]["status"], "resolved")

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["无锡"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        by_name = {item["name"]: item for item in payload["results"]}
        self.assertIn("赵清禾", by_name)
        restored = by_name["赵清禾"]
        job_item = next(item for item in restored["verification_items"] if item["key"] == "job")
        income_item = next(item for item in restored["verification_items"] if item["key"] == "income")
        self.assertEqual(job_item["status"], "verified")
        self.assertEqual(income_item["status"], "verified")

    def test_field_verification_supports_lifecycle_dispute_and_expiry(self) -> None:
        active_at = datetime(2026, 5, 5, 16, 0, 0)
        self._insert_search_profile(
            (
                3501,
                "沈知意",
                "女",
                30,
                "上海",
                "硕士",
                "产品经理",
                "50-80万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                0,
                4,
                "生活规律",
                "主动沟通",
                "希望资料真实性更强",
                "用于字段核验生命周期测试",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/profile-verifications/submissions",
            {
                "field_key": "education",
                "profile_id": 3501,
                "source_dsn": self.search_dsn,
                "subject_user_id": "candidate-3501",
                "declared_value": "硕士",
                "evidence_type": "degree_certificate",
                "evidence_channel": "authority_lookup",
                "evidence": {"doc_type": "degree_certificate", "issuer": "学位证明"},
                "now": "2026-05-05 16:05:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        submission = payload["submission"]
        submission_id = submission["submission_id"]
        self.assertEqual(submission["evidence_type"], "degree_certificate")
        self.assertEqual(submission["evidence_channel"], "authority_lookup")
        self.assertEqual(submission["dispute_status"], "none")

        status, payload = self._call(
            "POST",
            f"/v1/profile-verifications/submissions/{submission_id}/review",
            {
                "reviewer_id": "moderator-edu-1",
                "decision": "approve",
                "approved_value": "硕士",
                "review_note": "学历证明与资料一致",
                "validity_days": 1,
                "next_review_days": 1,
                "reverify_strategy": "annual_refresh",
                "now": "2026-05-05 16:10:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        approved = payload["submission"]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["reverify_strategy"], "annual_refresh")
        self.assertEqual(approved["review_count"], 1)
        self.assertEqual(approved["verification_expires_at"], "2026-05-06 16:10:00")
        self.assertEqual(approved["next_review_due_at"], "2026-05-06 16:10:00")

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["上海"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        profile = next(item for item in payload["results"] if item["name"] == "沈知意")
        education_item = next(item for item in profile["verification_items"] if item["key"] == "education")
        self.assertEqual(education_item["status"], "verified")

        status, payload = self._call(
            "POST",
            f"/v1/profile-verifications/submissions/{submission_id}/dispute",
            {
                "subject_user_id": "candidate-3501",
                "dispute_reason": "学历展示与学校层级备注不一致，申请复核",
                "evidence": {"appeal_note": "补充新的在读/毕业说明"},
                "now": "2026-05-05 16:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        disputed = payload["submission"]
        self.assertEqual(disputed["status"], "under_review")
        self.assertEqual(disputed["dispute_status"], "open")
        self.assertEqual(disputed["review_count"], 2)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["上海"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        profile = next(item for item in payload["results"] if item["name"] == "沈知意")
        education_item = next(item for item in profile["verification_items"] if item["key"] == "education")
        self.assertEqual(education_item["raw_status"], "disputed")
        self.assertIn("争议", education_item["summary"])
        self.assertTrue(any("争议复核" in item for item in profile["caution_items"]))

        status, payload = self._call(
            "POST",
            f"/v1/profile-verifications/submissions/{submission_id}/review",
            {
                "reviewer_id": "moderator-edu-2",
                "decision": "approve",
                "approved_value": "硕士",
                "review_note": "争议复核后维持学历认证",
                "validity_days": 1,
                "next_review_days": 1,
                "now": "2026-05-05 16:30:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        reviewed = payload["submission"]
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["dispute_status"], "resolved")
        self.assertEqual(reviewed["review_count"], 3)

        status, payload = self._call(
            "POST",
            "/v1/profile-verifications/expire-due",
            {
                "now": "2026-05-07 08:00:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["expired_count"], 1)
        expired = payload["submissions"][0]
        self.assertEqual(expired["submission_id"], submission_id)
        self.assertEqual(expired["status"], "expired")
        self.assertEqual(expired["review_count"], 4)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {"gender": "女", "cities": ["上海"]},
                "limit": 10,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        profile = next(item for item in payload["results"] if item["name"] == "沈知意")
        education_item = next(item for item in profile["verification_items"] if item["key"] == "education")
        self.assertEqual(education_item["raw_status"], "expired")
        self.assertIn("认证已过期", education_item["summary"])
        self.assertTrue(any("认证已过期" in item for item in profile["caution_items"]))

    def test_trust_hub_can_surface_profile_review_tasks_appeals_and_history(self) -> None:
        active_at = datetime(2026, 5, 5, 17, 0, 0)
        self._insert_search_profile(
            (
                3601,
                "周以宁",
                "女",
                31,
                "嘉兴",
                "本科",
                "行政助理",
                "120万+/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                2,
                3,
                "生活规律",
                "主动沟通",
                "希望认真了解彼此",
                "用于用户中心聚合测试",
                active_at,
            )
        )

        status, payload = self._call(
            "POST",
            "/v1/profile-review/risk-cases/evaluate",
            {
                "profile_id": 3601,
                "source_dsn": self.search_dsn,
                "subject_user_id": "candidate-3601",
                "now": "2026-05-05 17:05:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        risk_case = payload["risk_case"]
        risk_case_id = risk_case["profile_review_case_id"]
        self.assertEqual(risk_case["recommended_action"], "limited_exposure")

        status, payload = self._call(
            "GET",
            "/v1/user-center/trust-hub",
            query="user_id=candidate-3601&profile_id=3601",
        )
        self.assertTrue(status.startswith("200"), status)
        trust_hub = payload["trust_hub"]
        self.assertGreaterEqual(trust_hub["summary"]["pending_verification_count"], 2)
        verification_items = trust_hub["verification_center"]["items"]
        derived_fields = {
            item["field_key"]
            for item in verification_items
            if item["item_type"] == "field_verification_request"
        }
        self.assertEqual(derived_fields, {"job", "income"})
        profile_appeal_item = next(
            item
            for item in trust_hub["appeal_center"]["items"]
            if item["target_type"] == "profile_review_case"
        )
        self.assertEqual(profile_appeal_item["status"], "available")
        profile_record = next(
            item
            for item in trust_hub["risk_records"]["items"]
            if item["record_id"] == risk_case_id
        )
        self.assertEqual(profile_record["current_action"], "limited_exposure")

        status, payload = self._call(
            "POST",
            f"/v1/profile-review/risk-cases/{risk_case_id}/appeals",
            {
                "appellant_id": "candidate-3601",
                "reason_text": "职业和收入补充说明还没来得及提交，申请先人工复核",
                "evidence": {"note": "可补充职业证明和收入区间材料"},
                "now": "2026-05-05 17:10:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        self.assertEqual(payload["appeal"]["appeal_status"], "submitted")
        appeal_id = payload["appeal"]["appeal_id"]

        status, payload = self._call(
            "GET",
            "/v1/profile-review/appeals",
            query="subject_user_id=candidate-3601",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["appeals"]), 1)
        self.assertEqual(payload["appeals"][0]["appeal_id"], appeal_id)

        status, payload = self._call(
            "GET",
            "/v1/user-center/trust-hub",
            query="user_id=candidate-3601&profile_id=3601",
        )
        self.assertTrue(status.startswith("200"), status)
        trust_hub = payload["trust_hub"]
        profile_appeal_item = next(
            item
            for item in trust_hub["appeal_center"]["items"]
            if item["target_type"] == "profile_review_case"
        )
        self.assertEqual(profile_appeal_item["status"], "submitted")

        status, payload = self._call(
            "POST",
            f"/v1/profile-review/appeals/{appeal_id}/review",
            {
                "resolver_id": "appeal-moderator-1",
                "appeal_status": "upheld",
                "resolution_note": "申诉成立，先恢复曝光，后续继续人工跟进补件",
                "now": "2026-05-05 17:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["appeal"]["appeal_status"], "upheld")

        status, payload = self._call(
            "GET",
            f"/v1/profile-review/risk-cases/{risk_case_id}",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_case"]["status"], "resolved")

        status, payload = self._call(
            "GET",
            "/v1/user-center/trust-hub",
            query="user_id=candidate-3601&profile_id=3601",
        )
        self.assertTrue(status.startswith("200"), status)
        trust_hub = payload["trust_hub"]
        self.assertEqual(trust_hub["summary"]["active_risk_count"], 0)
        self.assertEqual(
            [
                item
                for item in trust_hub["verification_center"]["items"]
                if item["item_type"] == "field_verification_request"
            ],
            [],
        )

    def test_global_limit_chat_appeal_and_weekly_dashboard_flow(self) -> None:
        active_at = datetime(2026, 5, 5, 15, 0, 0)
        self._insert_search_profile(
            (
                4001,
                "嫌疑账号",
                "男",
                34,
                "上海",
                "本科",
                "投资顾问",
                "50-80万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                0,
                2,
                "作息不固定",
                "主动沟通",
                "喜欢聊投资项目",
                "资料普通，用于风控链路测试",
                active_at,
            )
        )

        metadata = {
            "participant_profiles": {
                "suspect-4001": {
                    "profile_id": 4001,
                    "source_dsn": self.search_dsn,
                    "source_table_name": "profiles",
                }
            }
        }
        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-risk-global-1",
                "relation_key": "risk-global-1",
                "participant_a_id": "victim-4001-a",
                "participant_b_id": "suspect-4001",
                "metadata": metadata,
                "now": "2026-05-05 15:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{thread_id}/messages",
            {
                "author_id": "suspect-4001",
                "body": "加微信吧，我带你做投资，收益稳，先转一笔就能进群",
                "visibility": "dyadic",
                "now": "2026-05-05 15:01:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call("GET", "/v1/chat/risk-cases", query=f"thread_id={thread_id}")
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["risk_cases"]), 1)
        risk_case_id = payload["risk_cases"][0]["risk_case_id"]

        status, payload = self._call(
            "POST",
            "/v1/chat/risk-cases/batch-review",
            {
                "risk_case_ids": [risk_case_id],
                "resolver_id": "moderator-batch",
                "status": "action_applied",
                "applied_action": "limit_chat",
                "resolution_note": "批量审核命中诈骗模板，先全局限聊",
                "now": "2026-05-05 15:03:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["reviewed"]), 1)

        status, payload = self._call(
            "POST",
            "/v1/chat/threads",
            {
                "case_id": "case-risk-global-2",
                "relation_key": "risk-global-2",
                "participant_a_id": "victim-4001-b",
                "participant_b_id": "suspect-4001",
                "metadata": metadata,
                "now": "2026-05-05 15:04:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        second_thread_id = payload["thread"]["thread_id"]

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{second_thread_id}/messages",
            {
                "author_id": "suspect-4001",
                "body": "你好，我们加微信细聊吧",
                "visibility": "dyadic",
                "now": "2026-05-05 15:05:00",
            },
        )
        self.assertTrue(status.startswith("400"), status)
        self.assertIn("restricted by risk action", payload["error"]["message"])

        status, payload = self._call(
            "POST",
            f"/v1/chat/risk-cases/{risk_case_id}/appeals",
            {
                "appellant_id": "suspect-4001",
                "reason_text": "这是误判，我愿意接受人工复核",
                "evidence": {"statement": "愿意配合补认证"},
                "now": "2026-05-05 15:06:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        appeal_id = payload["appeal"]["appeal_id"]

        status, payload = self._call("GET", "/v1/chat/risk-appeals", query=f"risk_case_id={risk_case_id}")
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["appeals"]), 1)

        status, payload = self._call(
            "POST",
            f"/v1/chat/risk-appeals/{appeal_id}/review",
            {
                "resolver_id": "appeal-moderator",
                "appeal_status": "upheld",
                "resolution_note": "申诉成立，解除全局限聊，改为继续人工观察",
                "now": "2026-05-05 15:08:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["appeal"]["appeal_status"], "upheld")

        status, payload = self._call("GET", f"/v1/chat/risk-cases/{risk_case_id}")
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["risk_case"]["status"], "resolved")
        self.assertEqual(len(payload["appeals"]), 1)
        self.assertIsNone(payload["moderation_state"])

        status, payload = self._call(
            "POST",
            f"/v1/chat/threads/{second_thread_id}/messages",
            {
                "author_id": "suspect-4001",
                "body": "你好，我们重新在平台内聊聊",
                "visibility": "dyadic",
                "now": "2026-05-05 15:09:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "GET",
            "/v1/chat/risk-dashboard/weekly",
            query="now=2026-05-05 15:10:00&days=7",
        )
        self.assertTrue(status.startswith("200"), status)
        dashboard = payload["dashboard"]
        self.assertGreaterEqual(dashboard["risk_case_count"], 1)
        self.assertGreaterEqual(dashboard["appeal_count"], 1)
        self.assertGreaterEqual(dashboard["appeal_upheld_count"], 1)

    def test_fraud_network_evaluation_can_freeze_cluster_and_hide_profiles_from_search(self) -> None:
        active_at = datetime(2026, 5, 5, 16, 0, 0)
        suspect_rows = [
            (
                5001,
                "嫌疑账号A",
                "男",
                35,
                "上海",
                "本科",
                "投资顾问",
                "50-80万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                0,
                3,
                "作息不固定",
                "主动沟通",
                "喜欢聊投资项目",
                "用于深度反诈图谱测试",
                active_at,
            ),
            (
                5002,
                "嫌疑账号B",
                "男",
                34,
                "上海",
                "本科",
                "理财顾问",
                "50-80万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                0,
                3,
                "作息不固定",
                "主动沟通",
                "喜欢聊投资项目",
                "用于深度反诈图谱测试",
                active_at,
            ),
            (
                5003,
                "嫌疑账号C",
                "男",
                33,
                "上海",
                "本科",
                "财富顾问",
                "50-80万/年",
                "未婚",
                0,
                "认真恋爱",
                "active",
                "basic",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                0,
                3,
                "作息不固定",
                "主动沟通",
                "喜欢聊投资项目",
                "用于深度反诈图谱测试",
                active_at,
            ),
        ]
        for row in suspect_rows:
            self._insert_search_profile(row)

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "男",
                    "cities": ["上海"],
                    "relationship_goals": ["认真恋爱"],
                },
                "self_profile": {"age": 30, "city": "上海", "education": "本科"},
                "limit": 10,
                "photo_preview_count": 1,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 3)

        suspects = [
            ("suspect-5001", 5001, "203.0.113.21"),
            ("suspect-5002", 5002, "203.0.113.22"),
            ("suspect-5003", 5003, "203.0.113.23"),
        ]
        for idx, (suspect_user_id, profile_id, client_ip) in enumerate(suspects):
            metadata = {
                "participant_profiles": {
                    suspect_user_id: {
                        "profile_id": profile_id,
                        "source_dsn": self.search_dsn,
                        "source_table_name": "profiles",
                    }
                }
            }
            status, payload = self._call(
                "POST",
                "/v1/chat/threads",
                {
                    "case_id": f"case-fraud-network-{idx}",
                    "relation_key": f"fraud-network-{idx}",
                    "participant_a_id": f"victim-fraud-{idx}",
                    "participant_b_id": suspect_user_id,
                    "metadata": metadata,
                    "now": f"2026-05-05 16:0{idx}:00",
                },
            )
            self.assertTrue(status.startswith("201"), status)
            thread_id = payload["thread"]["thread_id"]

            status, payload = self._call(
                "POST",
                f"/v1/chat/threads/{thread_id}/messages",
                {
                    "author_id": suspect_user_id,
                    "body": "加微信 ringcenter01，我带你做投资，收益稳，先转一笔就能进群",
                    "visibility": "dyadic",
                    "metadata": {
                        "risk_observation": {
                            "device_fingerprint": "device-cluster-001",
                            "contact_handles": ["wechat:ringcenter01"],
                            "avatar_fingerprint": "avatar-same-001",
                            "registration_path": "ios_invite",
                            "client_ip": client_ip,
                            "user_agent": "Her/1.0 (iPhone; iOS 18.1)",
                        }
                    },
                    "now": f"2026-05-05 16:1{idx}:00",
                },
            )
            self.assertTrue(status.startswith("201"), status)

        status, payload = self._call(
            "POST",
            "/v1/chat/fraud-networks/evaluate",
            {
                "subject_user_id": "suspect-5001",
                "source_dsn": self.search_dsn,
                "source_table_name": "profiles",
                "profile_id": 5001,
                "now": "2026-05-05 16:20:00",
            },
        )
        self.assertTrue(status.startswith("200"), status)
        network = payload["fraud_network"]
        self.assertEqual(network["network_profile"]["applied_action"], "freeze")
        self.assertEqual(network["network_profile"]["connected_subject_count"], 2)
        self.assertGreaterEqual(network["network_profile"]["graph_risk_score"], 160)
        self.assertEqual(len(network["account_links"]), 2)

        status, payload = self._call("GET", "/v1/chat/fraud-networks/suspect-5001")
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["fraud_network"]["moderation_state"]["applied_action"], "freeze")

        status, payload = self._call(
            "POST",
            "/v1/search/profiles",
            {
                "source": self.search_dsn,
                "criteria": {
                    "gender": "男",
                    "cities": ["上海"],
                    "relationship_goals": ["认真恋爱"],
                },
                "self_profile": {"age": 30, "city": "上海", "education": "本科"},
                "limit": 10,
                "photo_preview_count": 1,
            },
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["result_count"], 0)

        status, payload = self._call(
            "GET",
            "/v1/chat/risk-dashboard/weekly",
            query="now=2026-05-05 16:25:00&days=7",
        )
        self.assertTrue(status.startswith("200"), status)
        dashboard = payload["dashboard"]
        self.assertGreaterEqual(dashboard["fraud_network_profile_count"], 3)
        self.assertGreaterEqual(dashboard["high_risk_network_count"], 3)

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
