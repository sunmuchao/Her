import pathlib
import sys
import tempfile
import unittest
from datetime import datetime


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    close_match_case,
    close_timed_out_match_cases,
    connect_db,
    create_match_case,
    create_subscription,
    deliver_in_app_recommendations,
    dispatch_match_case_outreach,
    get_match_case,
    initialize_database,
    list_match_case_outreach_attempts,
    list_recommendations_for_subscription,
    record_match_case_reply,
    record_user_review,
    refresh_subscription,
)


def build_result(candidate_id, name, score, city="无锡", profile_overrides=None):
    profile = {
        "age": 28,
        "city": city,
        "height": 178,
        "education": "本科",
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
        "matched_on": ["城市 无锡", "目标 认真恋爱"],
        "reciprocal_on": [],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [],
        "photo_preview": [],
        "profile": profile,
    }


class ProxyIntroSystemTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.tempdir.name) / "proxy-intro.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_database(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tempdir.cleanup()

    def seed_delivered_recommendation(self, candidate_id=90001, score=66):
        subscription = create_subscription(
            self.conn,
            requester_id=71001,
            title="代理开口测试",
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 28, "city": "无锡", "height": 178},
            now=datetime(2026, 4, 30, 9, 0, 0),
        )
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 5, 0),
            search_runner=lambda **_: {"results": [build_result(candidate_id, "候选A", score)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=candidate_id,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 10, 0),
        )
        deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 9, 20, 0))
        return subscription

    def test_create_match_case_syncs_recommendation_and_redacts_summary(self):
        subscription = self.seed_delivered_recommendation()
        case = create_match_case(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=90001,
            now=datetime(2026, 4, 30, 10, 0, 0),
            request_payload={"source": "card_action"},
        )

        self.assertEqual(case["case_status"], "pending_outreach")
        self.assertEqual(case["safe_summary"]["age_bracket"], "25-29岁")
        self.assertEqual(case["safe_summary"]["height_bracket"], "175-179cm")
        self.assertEqual(case["outreach_payload"]["safe_summary"]["city"], "无锡")
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["delivery_status"], "proxy_intro_in_progress")
        self.assertEqual(recommendations[0]["active_match_case_id"], case["case_id"])

    def test_dispatch_reply_and_close_flow(self):
        subscription = self.seed_delivered_recommendation(candidate_id=90002)
        case = create_match_case(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=90002,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        dispatched = dispatch_match_case_outreach(
            self.conn,
            case_id=case["case_id"],
            now=datetime(2026, 4, 30, 10, 5, 0),
            provider_message_id="msg-1",
        )
        self.assertEqual(dispatched["case_status"], "awaiting_reply")
        self.assertEqual(len(list_match_case_outreach_attempts(self.conn, case["case_id"])), 1)

        replied = record_match_case_reply(
            self.conn,
            case_id=case["case_id"],
            reply_type="accepted",
            now=datetime(2026, 4, 30, 12, 0, 0),
            reply_payload={"note": "愿意继续了解"},
        )
        self.assertEqual(replied["case_status"], "accepted")
        self.assertEqual(
            list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]["delivery_status"],
            "proxy_intro_accepted",
        )

        closed = close_match_case(
            self.conn,
            case_id=case["case_id"],
            close_reason="handoff_completed",
            now=datetime(2026, 4, 30, 15, 0, 0),
        )
        self.assertEqual(closed["case_status"], "closed")
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "proxy_intro_handed_off")
        self.assertIsNone(recommendation["active_match_case_id"])

    def test_declined_case_applies_cooling_and_blocks_duplicate_creation(self):
        subscription = self.seed_delivered_recommendation(candidate_id=90003)
        case = create_match_case(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=90003,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )
        dispatch_match_case_outreach(self.conn, case_id=case["case_id"], now=datetime(2026, 4, 30, 10, 5, 0))
        declined = record_match_case_reply(
            self.conn,
            case_id=case["case_id"],
            reply_type="declined",
            now=datetime(2026, 4, 30, 11, 0, 0),
        )

        self.assertEqual(declined["case_status"], "declined")
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "proxy_intro_declined")
        self.assertIsNotNone(recommendation["cooling_until"])

        with self.assertRaises(ValueError):
            create_match_case(
                self.conn,
                subscription_id=subscription["subscription_id"],
                candidate_id=90003,
                now=datetime(2026, 5, 1, 10, 0, 0),
            )

    def test_timed_out_case_remains_cold_until_cooling_expires(self):
        subscription = self.seed_delivered_recommendation(candidate_id=90004)
        case = create_match_case(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=90004,
            now=datetime(2026, 4, 30, 10, 0, 0),
            reply_window_hours=1,
        )
        dispatch_match_case_outreach(self.conn, case_id=case["case_id"], now=datetime(2026, 4, 30, 10, 5, 0))

        summary = close_timed_out_match_cases(self.conn, now=datetime(2026, 4, 30, 12, 0, 0))
        self.assertEqual(summary["timed_out_count"], 1)
        timed_out_case = get_match_case(self.conn, case["case_id"])
        self.assertEqual(timed_out_case["case_status"], "timed_out")
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "proxy_intro_timed_out")
        self.assertIsNotNone(recommendation["cooling_until"])

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 13, 0, 0),
            search_runner=lambda **_: {"results": [build_result(90004, "候选A", 80)]},
        )
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "proxy_intro_timed_out")


if __name__ == "__main__":
    unittest.main()
