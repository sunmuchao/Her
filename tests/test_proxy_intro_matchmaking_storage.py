"""Integration tests for proxy-intro cases stored on matchmaking DB (dual connection)."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"

for path in (REPO_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from match_domain.proxy_intro_storage import table_names, use_matchmaking_storage  # noqa: E402
from matchmaking_system.proxy_intro import (  # noqa: E402
    PROXY_INTRO_STORAGE_ADAPTER,
    create_match_case,
    dispatch_match_case_outreach,
    get_match_case,
)
from recommendation_system import (  # noqa: E402
    connect_db as connect_recommendation_db,
    create_subscription,
    deliver_in_app_recommendations,
    initialize_database as initialize_recommendation_database,
    list_recommendations_for_subscription,
    record_user_review,
    refresh_subscription,
    reset_all_tables as reset_recommendation_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import connect_db as connect_matchmaking_db  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import initialize_database as initialize_matchmaking_database  # noqa: E402
from matchmaking_system import reset_all_tables as reset_matchmaking_tables  # noqa: E402


def _build_result(candidate_id: int, name: str, score: int) -> dict[str, object]:
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 10, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": ["城市 无锡"],
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
            "height": 178,
            "education": "本科",
            "relationship_goal": "认真恋爱",
        },
    }


class ProxyIntroMatchmakingStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"
        self.assertTrue(use_matchmaking_storage())

        self.rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_database(self.rec_conn)
        reset_recommendation_tables(self.rec_conn)

        self.mm_conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_database(self.mm_conn)
        reset_matchmaking_tables(self.mm_conn)

        self.tn = table_names()

    def tearDown(self) -> None:
        self.rec_conn.close()
        self.mm_conn.close()
        if self._old_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_storage

    def _seed_delivered_recommendation(self, candidate_id: int = 91001) -> dict[str, object]:
        subscription = create_subscription(
            self.rec_conn,
            requester_id=72001,
            title="撮合库存储测试",
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 28, "city": "无锡", "height": 178},
            now=datetime(2026, 6, 1, 9, 0, 0),
        )
        refresh_subscription(
            self.rec_conn,
            subscription["subscription_id"],
            now=datetime(2026, 6, 1, 9, 5, 0),
            search_runner=lambda **_: {"results": [_build_result(candidate_id, "候选M", 70)]},
        )
        record_user_review(
            self.rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=candidate_id,
            review_type="direct_greet",
            now=datetime(2026, 6, 1, 9, 10, 0),
        )
        deliver_in_app_recommendations(self.rec_conn, now=datetime(2026, 6, 1, 9, 20, 0))
        return subscription

    def test_case_persisted_on_matchmaking_not_legacy_rec_table(self) -> None:
        subscription = self._seed_delivered_recommendation()
        case = create_match_case(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=91001,
            now=datetime(2026, 6, 1, 10, 0, 0),
        )

        mm_row = self.mm_conn.execute(
            f"SELECT case_id FROM {self.tn.cases} WHERE case_id = ?",
            (case["case_id"],),
        ).fetchone()
        rec_row = self.rec_conn.execute(
            "SELECT case_id FROM match_cases WHERE case_id = ?",
            (case["case_id"],),
        ).fetchone()
        self.assertIsNotNone(mm_row)
        self.assertIsNone(rec_row)

        tagged = get_match_case(
            self.mm_conn,
            case["case_id"],
            recommendation_conn=self.rec_conn,
        )
        self.assertEqual(tagged["owner_service"], "matchmaking-system")
        self.assertEqual(tagged["storage_adapter"], PROXY_INTRO_STORAGE_ADAPTER)
        self.assertEqual(tagged["storage_adapter"], "matchmaking-db")

        recommendation = list_recommendations_for_subscription(
            self.rec_conn,
            subscription["subscription_id"],
        )[0]
        self.assertEqual(recommendation["active_match_case_id"], case["case_id"])
        self.assertEqual(recommendation["delivery_status"], "escalated_to_case")

    def test_dispatch_updates_mm_case_and_rec_mirror(self) -> None:
        subscription = self._seed_delivered_recommendation(candidate_id=91002)
        case = create_match_case(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=91002,
            now=datetime(2026, 6, 2, 10, 0, 0),
        )
        dispatched = dispatch_match_case_outreach(
            self.mm_conn,
            recommendation_conn=self.rec_conn,
            case_id=case["case_id"],
            now=datetime(2026, 6, 2, 10, 5, 0),
        )
        self.assertEqual(dispatched["case_status"], "awaiting_reply")

        mm_status = self.mm_conn.execute(
            f"SELECT case_status FROM {self.tn.cases} WHERE case_id = ?",
            (case["case_id"],),
        ).fetchone()["case_status"]
        self.assertEqual(mm_status, "awaiting_reply")

        rec = list_recommendations_for_subscription(self.rec_conn, subscription["subscription_id"])[0]
        self.assertEqual(rec["active_case_status"], "awaiting_reply")

if __name__ == "__main__":
    unittest.main()
