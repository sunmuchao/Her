from __future__ import annotations

import pathlib
import os
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for path in (REPO_ROOT, RECOMMENDATION_ROOT, CHAT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from recommendation_system import (  # noqa: E402
    close_match_case,
    close_timed_out_match_cases,
    connect_db as connect_recommendation_db,
    create_match_case,
    create_subscription,
    deliver_in_app_recommendations,
    dispatch_match_case_outreach,
    initialize_database as initialize_recommendation_database,
    list_recommendation_conversion_views_for_subscription,
    list_recommendations_for_subscription,
    record_match_case_reply,
    record_user_review,
    refresh_subscription,
    reset_all_tables as reset_recommendation_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402

from chat_system import (  # noqa: E402
    build_case_conversation_timeline,
    build_chat_timeline,
    connect_db as connect_chat_db,
    create_assistant_case_layout,
    get_or_create_thread,
    initialize_database as initialize_chat_database,
    list_case_conversations,
    post_message,
    post_conversation_message,
    reset_all_tables as reset_chat_tables,
)
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN  # noqa: E402
from relationship_ledger import (  # noqa: E402
    build_cross_system_funnel_dashboard,
    connect_db as connect_relation_ledger_db,
    get_relation_by_key,
    initialize_database as initialize_relation_ledger_database,
    reset_all_tables as reset_relation_ledger_tables,
)
from relationship_ledger.storage import DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN  # noqa: E402


def build_result(candidate_id: int, name: str, score: int) -> dict[str, object]:
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
        "profile": {
            "age": 28,
            "city": "无锡",
            "height": 170,
            "education": "本科",
            "relationship_goal": "认真恋爱",
        },
    }


class RecommendationChatIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
        self.recommendation_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_database(self.recommendation_conn)
        reset_recommendation_tables(self.recommendation_conn)

        self.chat_conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_chat_database(self.chat_conn)
        reset_chat_tables(self.chat_conn)

        self.ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        initialize_relation_ledger_database(self.ledger_conn)
        reset_relation_ledger_tables(self.ledger_conn)

    def tearDown(self) -> None:
        self.recommendation_conn.close()
        self.chat_conn.close()
        self.ledger_conn.close()
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db

    def load_relation(self, relation_key: str):
        self.ledger_conn.close()
        self.ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        return get_relation_by_key(self.ledger_conn, relation_key)

    def load_funnel(self):
        self.ledger_conn.close()
        self.ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        return build_cross_system_funnel_dashboard(self.ledger_conn)

    def test_proxy_intro_handoff_can_open_chat_on_same_case_and_relation(self) -> None:
        subscription = create_subscription(
            self.recommendation_conn,
            requester_id=72001,
            title="跨系统接力测试",
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 29, "city": "无锡", "height": 180},
            now=datetime(2026, 5, 10, 9, 0, 0),
        )
        refresh_subscription(
            self.recommendation_conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 10, 9, 5, 0),
            search_runner=lambda **_: {"results": [build_result(92001, "候选跨系统", 68)]},
        )
        record_user_review(
            self.recommendation_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=92001,
            review_type="direct_greet",
            now=datetime(2026, 5, 10, 9, 10, 0),
        )
        deliver_in_app_recommendations(self.recommendation_conn, now=datetime(2026, 5, 10, 9, 20, 0))
        case = create_match_case(
            self.recommendation_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=92001,
            now=datetime(2026, 5, 10, 10, 0, 0),
        )
        dispatch_match_case_outreach(
            self.recommendation_conn,
            case_id=case["case_id"],
            now=datetime(2026, 5, 10, 10, 5, 0),
        )
        record_match_case_reply(
            self.recommendation_conn,
            case_id=case["case_id"],
            reply_type="accepted",
            now=datetime(2026, 5, 10, 11, 0, 0),
            reply_payload={"note": "愿意继续了解"},
        )
        close_match_case(
            self.recommendation_conn,
            case_id=case["case_id"],
            close_reason="handoff_completed",
            now=datetime(2026, 5, 10, 11, 30, 0),
        )

        recommendation = list_recommendations_for_subscription(
            self.recommendation_conn,
            subscription["subscription_id"],
        )[0]
        conversion_view = list_recommendation_conversion_views_for_subscription(
            self.recommendation_conn,
            subscription["subscription_id"],
        )[0]
        self.assertEqual(conversion_view["conversion_stage"], "case_closed")
        self.assertEqual(conversion_view["latest_case_id"], case["case_id"])
        self.assertEqual(conversion_view["latest_case_close_reason"], "handoff_completed")

        requester_user_id = f"user:{subscription['requester_id']}"
        candidate_user_id = f"user:{case['candidate_id']}"
        relation_key = recommendation["relation_key"]
        thread = get_or_create_thread(
            self.chat_conn,
            case_id=case["case_id"],
            relation_key=relation_key,
            participant_a_id=requester_user_id,
            participant_b_id=candidate_user_id,
            metadata={
                "source": "recommendation_proxy_intro_handoff",
                "recommendation_id": recommendation["recommendation_id"],
                "subscription_id": subscription["subscription_id"],
            },
            now=datetime(2026, 5, 10, 11, 35, 0),
        )
        layout = create_assistant_case_layout(
            self.chat_conn,
            case_id=case["case_id"],
            relation_key=relation_key,
            participant_a_id=requester_user_id,
            participant_b_id=candidate_user_id,
            agent_id="agent-matchmaker",
            metadata={"handoff_reason": "proxy_intro_handoff_completed"},
            now=datetime(2026, 5, 10, 11, 36, 0),
        )

        main_group = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "main_group"
        )
        post_conversation_message(
            self.chat_conn,
            main_group["conversation_id"],
            requester_user_id,
            "你好，很高兴认识你。",
            now=datetime(2026, 5, 10, 11, 40, 0),
        )
        post_message(
            self.chat_conn,
            thread["thread_id"],
            requester_user_id,
            "你好，很高兴认识你。",
            now=datetime(2026, 5, 10, 11, 41, 0),
        )

        conversation_timeline = build_case_conversation_timeline(
            self.chat_conn,
            case["case_id"],
            requester_user_id,
            message_limit=20,
        )
        chat_timeline = build_chat_timeline(
            self.chat_conn,
            case["case_id"],
            requester_user_id,
            message_limit=20,
        )
        visible_conversations = list_case_conversations(
            self.chat_conn,
            case["case_id"],
            requester_id=requester_user_id,
        )
        relation = self.load_relation(relation_key)

        self.assertEqual(thread["case_id"], case["case_id"])
        self.assertEqual(thread["relation_key"], relation_key)
        self.assertEqual(layout["case_id"], case["case_id"])
        self.assertEqual(layout["relation_key"], relation_key)
        self.assertEqual(layout["conversation_count"], 3)
        self.assertEqual(chat_timeline["thread"]["case_id"], case["case_id"])
        self.assertEqual(chat_timeline["thread"]["relation_key"], relation_key)
        self.assertEqual(len(chat_timeline["messages"]), 1)
        self.assertEqual(chat_timeline["messages"][0]["body"], "你好，很高兴认识你。")
        self.assertEqual(conversation_timeline["conversation_count"], 2)
        self.assertEqual(
            {item["metadata"]["layout_role"] for item in visible_conversations},
            {"main_group", "assistant_dm_a"},
        )
        assert relation is not None
        self.assertEqual(relation["relation_key"], relation_key)
        self.assertEqual(relation["relation_status"], "closed")
        self.assertEqual(relation["current_phase"], "chat_active")
        self.assertEqual(relation["active_case_id"], None)
        self.assertEqual(relation["latest_chat_thread_id"], thread["thread_id"])
        self.assertEqual(len(relation["cases"]), 1)
        self.assertEqual(relation["cases"][0]["case_id"], case["case_id"])
        self.assertEqual(relation["cases"][0]["case_status"], "closed")
        self.assertGreaterEqual(len(relation["events"]), 6)
        self.assertIn("chat.thread.opened", {event["event_type"] for event in relation["events"]})
        self.assertIn("chat.message.created", {event["event_type"] for event in relation["events"]})

    def test_proxy_intro_timeout_flows_into_cooling_funnel_stage(self) -> None:
        subscription = create_subscription(
            self.recommendation_conn,
            requester_id=72002,
            title="跨系统超时测试",
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 29, "city": "无锡", "height": 180},
            now=datetime(2026, 5, 10, 9, 0, 0),
        )
        refresh_subscription(
            self.recommendation_conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 10, 9, 5, 0),
            search_runner=lambda **_: {"results": [build_result(92002, "候选超时", 67)]},
        )
        record_user_review(
            self.recommendation_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=92002,
            review_type="direct_greet",
            now=datetime(2026, 5, 10, 9, 10, 0),
        )
        deliver_in_app_recommendations(self.recommendation_conn, now=datetime(2026, 5, 10, 9, 20, 0))
        case = create_match_case(
            self.recommendation_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=92002,
            now=datetime(2026, 5, 10, 10, 0, 0),
        )
        dispatch_match_case_outreach(
            self.recommendation_conn,
            case_id=case["case_id"],
            now=datetime(2026, 5, 10, 10, 5, 0),
        )
        self.recommendation_conn.execute(
            "UPDATE match_cases SET reply_deadline_at = ? WHERE case_id = ?",
            ("2026-05-10 10:10:00", case["case_id"]),
        )
        self.recommendation_conn.commit()
        close_timed_out_match_cases(
            self.recommendation_conn,
            now=datetime(2026, 5, 10, 12, 0, 0),
        )

        recommendation = list_recommendations_for_subscription(
            self.recommendation_conn,
            subscription["subscription_id"],
        )[0]
        relation = self.load_relation(recommendation["relation_key"])
        funnel = self.load_funnel()

        assert relation is not None
        self.assertEqual(relation["relation_status"], "cooling")
        self.assertGreaterEqual(funnel["relation_stages"]["cooling"], 1)
        self.assertGreaterEqual(funnel["case_stages"]["timed_out"], 1)


if __name__ == "__main__":
    unittest.main()
