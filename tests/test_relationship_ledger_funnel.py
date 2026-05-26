from __future__ import annotations

import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for path in (REPO_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT, CHAT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from recommendation_system import (  # noqa: E402
    close_match_case,
    connect_db as connect_recommendation_db,
    create_match_case,
    create_subscription,
    deliver_in_app_recommendations,
    dispatch_match_case_outreach,
    initialize_database as initialize_recommendation_database,
    record_match_case_reply,
    record_user_review,
    refresh_subscription,
    reset_all_tables as reset_recommendation_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import (  # noqa: E402
    build_mutual_pairs,
    connect_db as connect_matchmaking_db,
    create_pool_member,
    dispatch_case_contact,
    initialize_database as initialize_matchmaking_database,
    open_match_cases,
    record_case_reply,
    refresh_active_pool,
    reset_all_tables as reset_matchmaking_tables,
)
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402
from chat_system import (  # noqa: E402
    connect_db as connect_chat_db,
    get_or_create_thread,
    initialize_database as initialize_chat_database,
    post_message,
    reset_all_tables as reset_chat_tables,
)
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN  # noqa: E402
from relationship_ledger import (  # noqa: E402
    build_cross_system_funnel_dashboard,
    connect_db as connect_relation_ledger_db,
    initialize_database as initialize_relation_ledger_database,
    reset_all_tables as reset_relation_ledger_tables,
)
from relationship_ledger.storage import DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN  # noqa: E402


def build_recommendation_result(candidate_id: int, name: str, score: int) -> dict[str, object]:
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


def build_matchmaking_result(candidate_id: int, name: str, score: int) -> dict[str, object]:
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 8, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": ["同城", "目标一致"],
        "reciprocal_on": ["偏好匹配"],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [],
        "photo_preview": [],
        "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
        "profile": {
            "age": 29,
            "city": "无锡",
            "job": "产品经理",
            "relationship_goal": "认真恋爱",
        },
    }


class RelationshipLedgerFunnelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        self._old_proxy_intro_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"

        self.rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_database(self.rec_conn)
        reset_recommendation_tables(self.rec_conn)

        self.mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_database(self.mm_conn)
        reset_matchmaking_tables(self.mm_conn)

        self.chat_conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_chat_database(self.chat_conn)
        reset_chat_tables(self.chat_conn)

        self.ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        initialize_relation_ledger_database(self.ledger_conn)
        reset_relation_ledger_tables(self.ledger_conn)

    def tearDown(self) -> None:
        self.rec_conn.close()
        self.mm_conn.close()
        self.chat_conn.close()
        self.ledger_conn.close()
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db
        if self._old_proxy_intro_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_proxy_intro_storage

    def load_funnel(self):
        self.ledger_conn.close()
        self.ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        return build_cross_system_funnel_dashboard(self.ledger_conn)

    def _seed_recommendation_handoff_to_chat(self) -> None:
        subscription = create_subscription(
            self.rec_conn,
            requester_id=73001,
            title="统一漏斗-推荐接力",
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 29, "city": "无锡", "height": 180},
            now=datetime(2026, 5, 11, 9, 0, 0),
        )
        refresh_subscription(
            self.rec_conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 11, 9, 5, 0),
            search_runner=lambda **_: {"results": [build_recommendation_result(93001, "推荐候选A", 68)]},
        )
        record_user_review(
            self.rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=93001,
            review_type="direct_greet",
            now=datetime(2026, 5, 11, 9, 10, 0),
        )
        deliver_in_app_recommendations(self.rec_conn, now=datetime(2026, 5, 11, 9, 20, 0))
        case = create_match_case(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=93001,
            now=datetime(2026, 5, 11, 10, 0, 0),
        )
        dispatch_match_case_outreach(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            case_id=case["case_id"],
            now=datetime(2026, 5, 11, 10, 5, 0),
        )
        record_match_case_reply(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            case_id=case["case_id"],
            reply_type="accepted",
            now=datetime(2026, 5, 11, 10, 30, 0),
            reply_payload={"note": "愿意继续了解"},
        )
        close_match_case(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            case_id=case["case_id"],
            close_reason="handoff_completed",
            now=datetime(2026, 5, 11, 11, 0, 0),
        )
        recommendation = self.rec_conn.execute(
            "SELECT relation_key FROM profile_recommendations ORDER BY recommendation_id DESC LIMIT 1"
        ).fetchone()
        relation_key = recommendation["relation_key"]
        thread = get_or_create_thread(
            self.chat_conn,
            case_id=case["case_id"],
            relation_key=relation_key,
            participant_a_id="user:73001",
            participant_b_id="user:93001",
            now=datetime(2026, 5, 11, 11, 5, 0),
        )
        post_message(
            self.chat_conn,
            thread["thread_id"],
            "user:73001",
            "你好，很高兴认识你。",
            now=datetime(2026, 5, 11, 11, 6, 0),
        )

    def _seed_matchmaking_decline_cooling(self) -> None:
        source = "mysql://user:pass@127.0.0.1:3306/her?table=profiles"
        create_pool_member(
            self.mm_conn,
            user_key="user-a",
            source=source,
            self_id=1001,
            search_criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱", "结婚导向"]},
            self_profile={"age": 29, "city": "无锡", "height": 170},
            min_pair_score=80,
            limit_count=5,
            refresh_interval_hours=24,
            now=datetime(2026, 5, 11, 12, 0, 0),
        )
        create_pool_member(
            self.mm_conn,
            user_key="user-b",
            source=source,
            self_id=1002,
            search_criteria={"gender": "男", "cities": ["无锡"], "relationship_goals": ["认真恋爱", "结婚导向"]},
            self_profile={"age": 28, "city": "无锡", "height": 168},
            min_pair_score=80,
            limit_count=5,
            refresh_interval_hours=24,
            now=datetime(2026, 5, 11, 12, 0, 0),
        )

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_matchmaking_result(1002, "撮合候选B", 90)]}
            if self_id == 1002:
                return {"results": [build_matchmaking_result(1001, "撮合候选A", 91)]}
            return {"results": []}

        refresh_active_pool(
            self.mm_conn,
            now=datetime(2026, 5, 11, 12, 5, 0),
            search_runner=fake_search_runner,
        )
        build_mutual_pairs(self.mm_conn, now=datetime(2026, 5, 11, 12, 10, 0))
        case = open_match_cases(self.mm_conn, now=datetime(2026, 5, 11, 12, 15, 0))[0]
        case = dispatch_case_contact(
            self.mm_conn,
            case["case_id"],
            now=datetime(2026, 5, 11, 12, 16, 0),
        )
        record_case_reply(
            self.mm_conn,
            case["case_id"],
            member_id=case["first_contact_member_id"],
            reply_type="decline",
            now=datetime(2026, 5, 11, 12, 17, 0),
        )

    def test_cross_system_funnel_dashboard_counts_unified_stages(self) -> None:
        self._seed_recommendation_handoff_to_chat()
        self._seed_matchmaking_decline_cooling()

        dashboard = self.load_funnel()

        self.assertEqual(dashboard["relation_stages"]["relation_total"], 2)
        self.assertGreaterEqual(dashboard["relation_stages"]["chat_active"], 1)
        self.assertGreaterEqual(dashboard["relation_stages"]["closed"], 1)
        self.assertGreaterEqual(dashboard["relation_stages"]["cooling"], 1)
        self.assertGreaterEqual(dashboard["case_stages"]["case_total"], 2)
        self.assertGreaterEqual(dashboard["case_stages"]["proxy_intro_cases"], 1)
        self.assertGreaterEqual(dashboard["case_stages"]["matchmaking_cases"], 1)
        self.assertGreaterEqual(dashboard["case_stages"]["closed"], 1)
        self.assertGreaterEqual(dashboard["case_stages"]["declined"], 1)
