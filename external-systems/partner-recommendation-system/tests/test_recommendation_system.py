import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    connect_db,
    create_subscription,
    deliver_in_app_recommendations,
    get_subscription,
    initialize_database,
    list_in_app_cards,
    list_recommendations_for_subscription,
    record_recommendation_action,
    refresh_due_subscriptions,
    refresh_subscription,
)


def build_result(candidate_id, name, score, city="无锡", matched_on=None, risk_flags=None):
    matched_on = matched_on or ["城市 无锡", "目标 认真恋爱"]
    risk_flags = risk_flags or []
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 10, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": matched_on,
        "reciprocal_on": [],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": risk_flags,
        "match_evidence": [],
        "follow_up_questions": ["确认最近的见面频率安排。"] if risk_flags else [],
        "photo_preview": [],
        "profile": {
            "age": 28,
            "city": city,
            "job": "产品经理",
            "relationship_goal": "认真恋爱",
        },
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
                    build_result(101, "新对象A", 58),
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
        self.assertIsNotNone(recommendations[0]["latest_card_id"])

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
