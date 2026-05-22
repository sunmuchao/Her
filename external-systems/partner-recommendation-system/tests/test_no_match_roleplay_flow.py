import pathlib
import sys
import unittest
from datetime import datetime


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    connect_db,
    deliver_in_app_recommendations,
    handle_opt_in_decision,
    initialize_database,
    list_in_app_cards,
    list_recommendations_for_subscription,
    record_recommendation_action,
    record_user_review,
    refresh_due_subscriptions,
    reset_all_tables,
    run_search_session,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402


def build_candidate():
    return {
        "id": 30010,
        "name": "周砚川",
        "score": 67,
        "fit_score": 55,
        "confidence_score": 12,
        "risk_score": 0,
        "matched_on": ["城市 无锡", "目标 结婚导向", "情绪稳定"],
        "reciprocal_on": [],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [],
        "photo_preview": [],
        "profile": {
            "age": 36,
            "city": "无锡",
            "job": "法务",
            "relationship_goal": "结婚导向",
        },
    }


class NoMatchRoleplayFlowTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_no_match_opt_in_then_supplement_candidate_can_be_direct_greeted(self):
        candidate_pool = []

        def search_runner(**_):
            return {
                "has_match": bool(candidate_pool),
                "result_count": len(candidate_pool),
                "results": list(candidate_pool),
                "fallback_results": [],
            }

        session = run_search_session(
            source="mock://roleplay/no-match-then-notify",
            criteria={
                "gender": "男",
                "cities": ["无锡", "苏州"],
                "relationship_goals": ["认真恋爱", "结婚导向"],
                "must_have": ["情绪稳定", "责任心", "稳定工作", "愿意沟通"],
                "must_not_have": ["抽烟严重", "暧昧不清", "失联冷处理"],
                "verified_level_min": "photo",
                "photo_count_min": 2,
            },
            self_profile={
                "age": 29,
                "city": "无锡",
                "height": 165,
                "education": "硕士",
                "income_wan": 24,
                "marital_status": "未婚",
                "has_children": 0,
            },
            limit=5,
            search_runner=search_runner,
        )

        self.assertTrue(session["needs_opt_in_prompt"])

        decision = handle_opt_in_decision(
            self.conn,
            requester_id=88001,
            search_session=session,
            user_opted_in=True,
            title="无锡稳定认真关系持续留意",
            quiet_hours_start=23,
            quiet_hours_end=8,
            refresh_interval_hours=24,
        )
        subscription = decision["subscription"]

        candidate_pool.append(build_candidate())

        refresh_batch = refresh_due_subscriptions(
            self.conn,
            now=datetime(2026, 5, 3, 9, 0, 0),
            search_runner=search_runner,
        )
        refresh_summaries = refresh_batch["summaries"]
        self.assertEqual(len(refresh_summaries), 1)
        self.assertEqual(refresh_summaries[0]["result_count"], 1)
        self.assertEqual(refresh_batch["errors"], [])
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "review_pending")
        self.assertEqual(recommendation["final_review_status"], "direct_greet_ready")

        review = record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=30010,
            review_type="direct_greet",
            now=datetime(2026, 5, 3, 9, 20, 0),
            review_payload={"reason": "同城稳定，愿意主动开聊"},
        )
        self.assertEqual(review["delivery_status"], "pending_delivery")

        delivery_summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 5, 3, 10, 0, 0),
        )
        self.assertEqual(delivery_summary["delivered_count"], 1)

        cards = list_in_app_cards(self.conn, requester_id=88001)
        self.assertEqual(len(cards), 1)
        self.assertIn("发现新的合适对象", cards[0]["title"])
        self.assertIn("周砚川", cards[0]["title"])

        greeted = record_recommendation_action(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=30010,
            action_type="direct_greet",
            now=datetime(2026, 5, 3, 10, 15, 0),
            action_payload={"reason": "同城稳定，目标明确，愿意直接开始聊"},
        )
        self.assertEqual(greeted["delivery_status"], "direct_greet_started")
        self.assertEqual(greeted["last_action_type"], "direct_greet")

        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")
        self.assertEqual(recommendations[0]["delivery_status"], "direct_greet_started")
        self.assertEqual(recommendations[0]["candidate_name"], "周砚川")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
