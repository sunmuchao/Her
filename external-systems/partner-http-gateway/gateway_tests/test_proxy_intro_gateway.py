"""Gateway integration: proxy-intro case access via _with_proxy_intro (matchmaking storage)."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for root in (GATEWAY_ROOT, RECOMMENDATION_ROOT, MATCHMAKING_ROOT, CHAT_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from gateway.app import PartnerGateway  # noqa: E402
from gateway.identity import ActorPrincipal, ROLE_END_USER  # noqa: E402
from matchmaking_system.proxy_intro import create_match_case, get_match_case  # noqa: E402
from recommendation_system import (  # noqa: E402
    connect_db as connect_recommendation_db,
    create_subscription,
    deliver_in_app_recommendations,
    initialize_database as initialize_recommendation_db,
    record_user_review,
    refresh_subscription,
    reset_all_tables as reset_recommendation_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import connect_db as connect_matchmaking_db  # noqa: E402
from matchmaking_system import initialize_database as initialize_matchmaking_db  # noqa: E402
from matchmaking_system import reset_all_tables as reset_matchmaking_tables  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN  # noqa: E402


def _search_result(candidate_id: int) -> dict[str, object]:
    return {
        "id": candidate_id,
        "name": "GW候选",
        "score": 60,
        "fit_score": 50,
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": [],
        "reciprocal_on": [],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [],
        "photo_preview": [],
        "profile": {"age": 27, "city": "无锡", "relationship_goal": "认真恋爱"},
    }


class ProxyIntroGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"

        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_recommendation_db(rec)
        reset_recommendation_tables(rec)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_matchmaking_db(mm)
        reset_matchmaking_tables(mm)
        rec.close()
        mm.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )
        self._case_id: str | None = None
        self._requester_id = 75001

    def tearDown(self) -> None:
        if self._old_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_storage

    def _seed_case(self) -> str:
        rec = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        mm = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            sub = create_subscription(
                rec,
                requester_id=self._requester_id,
                title="gateway-proxy",
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["无锡"]},
                self_profile={"age": 30, "city": "无锡"},
                now=datetime(2026, 6, 10, 9, 0, 0),
            )
            refresh_subscription(
                rec,
                sub["subscription_id"],
                now=datetime(2026, 6, 10, 9, 5, 0),
                search_runner=lambda **_: {"results": [_search_result(92001)]},
            )
            record_user_review(
                rec,
                subscription_id=sub["subscription_id"],
                candidate_id=92001,
                review_type="direct_greet",
                now=datetime(2026, 6, 10, 9, 10, 0),
            )
            deliver_in_app_recommendations(rec, now=datetime(2026, 6, 10, 9, 20, 0))
            case = create_match_case(
                mm,
                recommendation_conn=rec,
                subscription_id=sub["subscription_id"],
                candidate_id=92001,
                now=datetime(2026, 6, 10, 10, 0, 0),
            )
            return str(case["case_id"])
        finally:
            rec.close()
            mm.close()

    def test_with_proxy_intro_loads_case_from_matchmaking_db(self) -> None:
        case_id = self._seed_case()
        loaded = self.gw._with_proxy_intro(get_match_case, case_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["case_id"], case_id)
        self.assertEqual(loaded["storage_adapter"], "matchmaking-db")
        self.assertEqual(loaded["owner_service"], "matchmaking-system")

    def test_get_case_for_actor_resolves_proxy_intro_participant(self) -> None:
        case_id = self._seed_case()
        environ = {
            "_actor": ActorPrincipal(
                actor_id=str(self._requester_id),
                roles=frozenset({ROLE_END_USER}),
                token_id="test",
                auth_source="static_token",
            ),
        }
        case = self.gw._get_case_for_actor(environ, case_id)
        self.assertEqual(case["case_id"], case_id)
        self.assertEqual(case["requester_id"], self._requester_id)


if __name__ == "__main__":
    unittest.main()
