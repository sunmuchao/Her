import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    DEFAULT_NO_MATCH_OPT_IN_PROMPT,
    connect_db,
    create_subscription,
    deliver_in_app_recommendations,
    get_subscription,
    handle_opt_in_decision,
    initialize_database,
    list_in_app_cards,
    list_recommendations_for_subscription,
    record_recommendation_action,
    refresh_due_subscriptions,
    refresh_subscription,
    run_search_session,
)


def build_result(
    candidate_id,
    name,
    score,
    city="无锡",
    matched_on=None,
    risk_flags=None,
    reciprocal_on=None,
    follow_up_questions=None,
    missing_fields=None,
    self_profile_gaps=None,
    profile_overrides=None,
):
    matched_on = matched_on or ["城市 无锡", "目标 认真恋爱"]
    risk_flags = risk_flags or []
    reciprocal_on = reciprocal_on or []
    if follow_up_questions is None:
        follow_up_questions = ["确认最近的见面频率安排。"] if risk_flags else []
    missing_fields = missing_fields or []
    self_profile_gaps = self_profile_gaps or []
    profile = {
        "age": 28,
        "city": city,
        "job": "产品经理",
        "relationship_goal": "认真恋爱",
    }
    profile.update(profile_overrides or {})
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 10, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": matched_on,
        "reciprocal_on": reciprocal_on,
        "missing_fields": missing_fields,
        "self_profile_gaps": self_profile_gaps,
        "risk_flags": risk_flags,
        "match_evidence": [],
        "follow_up_questions": follow_up_questions,
        "photo_preview": [],
        "profile": profile,
    }


class RecommendationSystemTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.tempdir.name) / "phase3.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_database(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tempdir.cleanup()

    def create_active_subscription(self, **overrides):
        base = {
            "requester_id": 70001,
            "title": "无锡认真恋爱",
            "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            "criteria": {
                "gender": "女",
                "cities": ["无锡"],
                "relationship_goals": ["认真恋爱", "结婚导向"],
            },
            "self_profile": {"age": 28, "city": "无锡", "height": 178},
            "limit_count": 10,
            "top_k": 5,
            "min_notify_score": 40,
            "daily_notification_cap": 2,
            "quiet_hours_start": 23,
            "quiet_hours_end": 23,
            "refresh_interval_hours": 24,
            "skip_cooldown_days": 30,
            "recommendation_mode": "direct_greet_only",
            "max_review_candidates_per_refresh": 3,
            "min_direct_greet_score": 60,
            "now": datetime(2026, 4, 30, 9, 0, 0),
        }
        base.update(overrides)
        return create_subscription(self.conn, **base)

    def test_refresh_due_subscriptions_queues_new_candidates_and_calls_partner_search(self):
        subscription = self.create_active_subscription()
        called = {}

        def fake_search_runner(**kwargs):
            called.update(kwargs)
            return {
                "results": [
                    build_result(101, "新对象A", 62),
                    build_result(102, "分数偏低", 33),
                ]
            }

        summaries = refresh_due_subscriptions(
            self.conn,
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=fake_search_runner,
        )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(called["criteria"]["cities"], ["无锡"])
        self.assertEqual(called["self_profile"]["city"], "无锡")
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(recommendations), 2)
        self.assertEqual(recommendations[0]["delivery_status"], "pending_delivery")
        self.assertEqual(recommendations[1]["delivery_status"], "suppressed_low_score")
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")

    def test_deliver_pending_recommendations_creates_in_app_card(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(201, "提醒对象", 61)]},
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 1)
        cards = list_in_app_cards(self.conn, requester_id=70001)
        self.assertEqual(len(cards), 1)
        self.assertIn("发现新的合适对象", cards[0]["title"])
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["delivery_status"], "delivered")
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")
        self.assertIsNotNone(recommendations[0]["latest_card_id"])

    def test_direct_greet_only_mode_keeps_save_level_candidate_out_of_notifications(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(
                        211,
                        "先收藏对象",
                        68,
                        follow_up_questions=["确认见面频率和关系推进节奏。"],
                    )
                ]
            },
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 0)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["delivery_status"], "save_only")
        self.assertEqual(recommendations[0]["final_review_status"], "save_only")
        self.assertEqual(list_in_app_cards(self.conn, requester_id=70001), [])

    def test_match_based_mode_can_still_push_candidate_that_is_not_direct_greet_ready(self):
        subscription = self.create_active_subscription(recommendation_mode="match_based")
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(
                        212,
                        "传统匹配候选",
                        68,
                        follow_up_questions=["确认见面频率和关系推进节奏。"],
                    )
                ]
            },
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 1)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["final_review_status"], "match_ready")
        self.assertEqual(recommendations[0]["delivery_status"], "delivered")

    def test_skip_action_applies_cooldown_and_blocks_redelivery_until_expiry(self):
        subscription = self.create_active_subscription(daily_notification_cap=5)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 62)]},
        )
        deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))
        record_recommendation_action(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=301,
            action_type="skip",
            now=datetime(2026, 4, 30, 11, 0, 0),
        )

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 1, 12, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 62)]},
        )
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "cooled_down")
        self.assertEqual(
            deliver_in_app_recommendations(self.conn, now=datetime(2026, 5, 1, 12, 5, 0))["delivered_count"],
            0,
        )

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 6, 1, 12, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 65)]},
        )
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "pending_delivery")

    def test_daily_notification_cap_defers_extra_cards(self):
        subscription = self.create_active_subscription(daily_notification_cap=1)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(401, "第一位", 66),
                    build_result(402, "第二位", 64),
                ]
            },
        )

        summary = deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))

        self.assertEqual(summary["delivered_count"], 1)
        self.assertEqual(summary["held_daily_cap"], 1)
        cards = list_in_app_cards(self.conn, requester_id=70001)
        self.assertEqual(len(cards), 1)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(
            [item["delivery_status"] for item in recommendations],
            ["delivered", "pending_delivery"],
        )

    def test_quiet_hours_hold_delivery(self):
        subscription = self.create_active_subscription(
            quiet_hours_start=0,
            quiet_hours_end=23,
        )
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(501, "静默时段对象", 60)]},
        )

        summary = deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))

        self.assertEqual(summary["delivered_count"], 0)
        self.assertEqual(summary["held_quiet_hours"], 1)
        self.assertEqual(list_in_app_cards(self.conn, requester_id=70001), [])

    def test_get_subscription_and_refresh_interval_keep_not_due_subscription_idle(self):
        subscription = self.create_active_subscription(refresh_interval_hours=48)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(601, "首次对象", 60)]},
        )

        due = refresh_due_subscriptions(
            self.conn,
            now=datetime(2026, 5, 1, 8, 0, 0),
            search_runner=lambda **_: {"results": [build_result(602, "不该触发", 99)]},
        )

        self.assertEqual(due, [])
        loaded = get_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(loaded["last_result_count"], 1)

    def test_run_search_session_requests_opt_in_prompt_when_no_match(self):
        called = {}

        def fake_search_runner(**kwargs):
            called.update(kwargs)
            return {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            }

        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"]},
            self_profile={"age": 28, "city": "无锡"},
            limit=8,
            search_runner=fake_search_runner,
        )

        self.assertEqual(called["criteria"]["cities"], ["无锡"])
        self.assertEqual(called["limit"], 8)
        self.assertTrue(session["needs_opt_in_prompt"])
        self.assertEqual(session["opt_in_prompt"], DEFAULT_NO_MATCH_OPT_IN_PROMPT)

    def test_run_search_session_skips_opt_in_prompt_when_match_exists(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"]},
            search_runner=lambda **_: {
                "has_match": True,
                "result_count": 1,
                "results": [build_result(701, "已有结果", 61)],
            },
        )

        self.assertFalse(session["needs_opt_in_prompt"])
        self.assertIsNone(session["opt_in_prompt"])
        self.assertEqual(session["result_count"], 1)

    def test_handle_opt_in_decision_creates_subscription_from_original_search_request(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_id=90001,
            table_name="profiles",
            photos_table_name="profile_photos",
            limit=6,
            search_runner=lambda **_: {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            },
        )

        decision = handle_opt_in_decision(
            self.conn,
            requester_id=70001,
            search_session=session,
            user_opted_in=True,
            title="空结果后继续留意",
        )

        self.assertTrue(decision["created_subscription"])
        subscription = decision["subscription"]
        self.assertEqual(subscription["requester_id"], 70001)
        self.assertEqual(subscription["title"], "空结果后继续留意")
        self.assertEqual(subscription["self_id"], 90001)
        self.assertEqual(subscription["table_name"], "profiles")
        self.assertEqual(subscription["photos_table_name"], "profile_photos")
        self.assertEqual(subscription["limit_count"], 6)

        called = {}
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **kwargs: called.update(kwargs) or {"results": []},
        )
        self.assertEqual(called["self_id"], 90001)
        self.assertEqual(called["criteria"]["relationship_goals"], ["认真恋爱"])
        self.assertEqual(called["limit"], 6)
        self.assertEqual(subscription["recommendation_mode"], "direct_greet_only")

    def test_handle_opt_in_decision_rejection_creates_no_subscription(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女"},
            search_runner=lambda **_: {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            },
        )

        decision = handle_opt_in_decision(
            self.conn,
            requester_id=70001,
            search_session=session,
            user_opted_in=False,
        )

        saved_count = self.conn.execute("SELECT COUNT(*) AS c FROM saved_search_subscriptions").fetchone()["c"]
        self.assertFalse(decision["created_subscription"])
        self.assertIsNone(decision["subscription"])
        self.assertEqual(saved_count, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
