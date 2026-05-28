from __future__ import annotations

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

from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
)
from gateway.app import PartnerGateway  # noqa: E402
from gateway_tests.helpers import (  # noqa: E402
    auth_headers,
    call_gateway_json,
    ensure_search_schema,
    reset_search_rows,
    search_test_config,
)
from matchmaking_system.storage import (  # noqa: E402
    DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
    connect_db as connect_matchmaking_db,
    initialize_database as initialize_matchmaking_db,
    reset_all_tables as reset_matchmaking_tables,
)
from recommendation_system import create_subscription, refresh_subscription  # noqa: E402
from recommendation_system.storage import (  # noqa: E402
    DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
    connect_db as connect_recommendation_db,
    initialize_database as initialize_recommendation_db,
    reset_all_tables as reset_recommendation_tables,
)
from relationship_ledger.storage import (  # noqa: E402
    DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN,
    connect_db as connect_relation_ledger_db,
    initialize_database as initialize_relation_ledger_db,
    reset_all_tables as reset_relation_ledger_tables,
)


DEFAULT_PROFILE_TEST_DSN = os.environ.get(
    "PARTNER_SEARCH_E2E_TEST_DB",
    os.environ.get(
        "PARTNER_SEARCH_REALISTIC_TEST_DB",
        "mysql://root@127.0.0.1:3307/her_partner_search_realistic_test?table=profiles&photos_table=profile_photos",
    ),
)


class _FakeSmsProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_code(self, phone: str, code: str) -> dict[str, str]:
        self.calls.append((phone, code))
        return {"provider": "fake"}


class ProxyIntroEndUserFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_search_config = search_test_config(DEFAULT_PROFILE_TEST_DSN)
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        self._old_proxy_intro_storage = os.environ.get("HER_PROXY_INTRO_STORAGE")
        self._old_profile_source_dsn = os.environ.get("HER_PROFILE_SOURCE_DSN")
        os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
        os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"
        os.environ["HER_PROFILE_SOURCE_DSN"] = DEFAULT_PROFILE_TEST_DSN
        ensure_search_schema(self.profile_search_config)
        reset_search_rows(self.profile_search_config)

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

        ledger_conn = connect_relation_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        initialize_relation_ledger_db(ledger_conn)
        reset_relation_ledger_tables(ledger_conn)
        ledger_conn.close()

        self.gw = PartnerGateway(
            recommendation_dsn=DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
            matchmaking_dsn=DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            relation_ledger_dsn=DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN,
            db_pool_max=0,
        )
        self.sms_provider = _FakeSmsProvider()
        self.gw._auth_otp._provider = self.sms_provider

    def tearDown(self) -> None:
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db
        if self._old_proxy_intro_storage is None:
            os.environ.pop("HER_PROXY_INTRO_STORAGE", None)
        else:
            os.environ["HER_PROXY_INTRO_STORAGE"] = self._old_proxy_intro_storage
        if self._old_profile_source_dsn is None:
            os.environ.pop("HER_PROFILE_SOURCE_DSN", None)
        else:
            os.environ["HER_PROFILE_SOURCE_DSN"] = self._old_profile_source_dsn

    def _call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        token: str | None = None,
        query: str = "",
    ) -> tuple[str, dict]:
        return call_gateway_json(
            self.gw,
            method,
            path,
            body=body,
            query=query,
            extra=auth_headers(token),
        )

    def _login_and_onboard(
        self,
        *,
        phone: str,
        name: str,
        gender: str,
        city: str,
        relationship_goal: str,
    ) -> dict[str, object]:
        status, payload = self._call(
            "POST",
            "/v1/auth/sms/send-code",
            {"phone": phone},
        )
        self.assertTrue(status.startswith("201"), status)
        code = self.sms_provider.calls[-1][1]

        status, payload = self._call(
            "POST",
            "/v1/auth/sms/verify-code",
            {"phone": phone, "code": code},
        )
        self.assertTrue(status.startswith("200"), status)
        access_token = str(payload["session"]["access_token"])

        status, payload = self._call(
            "PATCH",
            "/v1/auth/onboarding",
            {
                "basic_info": {
                    "name": name,
                    "gender": gender,
                    "birthday": "1996-06-01",
                    "location": city,
                },
                "preference": {
                    "relationship_goal": relationship_goal,
                },
                "mark_completed": True,
            },
            token=access_token,
        )
        self.assertTrue(status.startswith("200"), status)
        profile_id = int(payload["profile_id"])

        status, payload = self._call("GET", "/v1/auth/me", token=access_token)
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(int(payload["user"]["profile_id"]), profile_id)
        return {
            "access_token": access_token,
            "profile_id": profile_id,
            "user_id": str(payload["user"]["user_id"]),
        }

    def test_end_user_proxy_intro_can_request_reply_and_open_chat(self) -> None:
        requester = self._login_and_onboard(
            phone="13800138000",
            name="甲",
            gender="男",
            city="无锡",
            relationship_goal="认真恋爱",
        )
        candidate = self._login_and_onboard(
            phone="13800138001",
            name="乙",
            gender="女",
            city="无锡",
            relationship_goal="认真恋爱",
        )

        rec_conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            subscription = create_subscription(
                rec_conn,
                requester_id=int(requester["profile_id"]),
                self_id=int(requester["profile_id"]),
                title="端到端牵线验证",
                source="mysql://test",
                criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
                self_profile={"age": 29, "city": "无锡"},
                now=datetime(2026, 5, 28, 11, 0, 0),
            )
            refresh_subscription(
                rec_conn,
                subscription["subscription_id"],
                now=datetime(2026, 5, 28, 11, 1, 0),
                search_runner=lambda **_: {
                    "results": [
                        {
                            "id": int(candidate["profile_id"]),
                            "name": "乙",
                            "score": 86,
                            "fit_score": 80,
                            "confidence_score": 6,
                            "risk_score": 0,
                            "matched_on": ["同城", "认真恋爱"],
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
                                "job": "老师",
                                "education": "本科",
                                "relationship_goal": "认真恋爱",
                            },
                        }
                    ]
                },
            )
        finally:
            rec_conn.close()

        status, payload = self._call(
            "POST",
            "/v1/proxy-intro/requests",
            {
                "subscription_id": subscription["subscription_id"],
                "candidate_id": int(candidate["profile_id"]),
                "source": "test_case",
            },
            token=str(requester["access_token"]),
        )
        self.assertTrue(status.startswith("201"), status)
        case_id = str(payload["case"]["case_id"])
        self.assertEqual(payload["case"]["case_status"], "awaiting_reply")

        status, payload = self._call(
            "GET",
            "/v1/recommendation/cards",
            token=str(requester["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["cards"], [])

        status, payload = self._call(
            "GET",
            "/v1/proxy-intro/cases/mine",
            token=str(requester["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["cases"][0]["role"], "requester")
        self.assertFalse(payload["cases"][0]["can_reply"])

        status, payload = self._call(
            "GET",
            "/v1/proxy-intro/cases/mine",
            token=str(candidate["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["cases"][0]["can_reply"])

        status, payload = self._call(
            "POST",
            f"/v1/proxy-intro/cases/{case_id}/reply",
            {"reply_type": "accepted", "source": "test_case"},
            token=str(candidate["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["case"]["case_status"], "accepted")

        status, payload = self._call(
            "GET",
            "/v1/proxy-intro/cases/mine",
            token=str(requester["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertTrue(payload["cases"][0]["can_open_chat"])

        status, payload = self._call(
            "POST",
            f"/v1/proxy-intro/cases/{case_id}/open-chat",
            {"source": "test_case"},
            token=str(requester["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["conversation"]["channel_key"], "main_group")
        self.assertEqual(payload["case"]["case_status"], "closed")
        self.assertEqual(payload["case"]["stage_label"], "已开聊")

        status, payload = self._call(
            "GET",
            "/v1/proxy-intro/cases/mine",
            token=str(candidate["access_token"]),
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertTrue(str(payload["cases"][0]["main_conversation_id"]).strip())
        self.assertEqual(payload["cases"][0]["stage_label"], "已开聊")


if __name__ == "__main__":
    unittest.main()
