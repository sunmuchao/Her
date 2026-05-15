from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for root in (GATEWAY_ROOT, CHAT_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
)
from gateway.app import PartnerGateway  # noqa: E402


class GatewayChatConversationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        chat_conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_chat_db(chat_conn)
        reset_chat_tables(chat_conn)
        chat_conn.close()

        self.gw = PartnerGateway(
            recommendation_dsn="mysql://noop",
            matchmaking_dsn="mysql://noop",
            chat_dsn=DEFAULT_CHAT_TEST_MYSQL_DSN,
            db_pool_max=0,
        )

    def _call(self, method: str, path: str, body: dict | None = None, query: str = "") -> tuple[str, dict]:
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
            "REMOTE_ADDR": "127.0.0.1",
        }
        state: dict[str, object] = {"status": "", "headers": []}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            state["status"] = status
            state["headers"] = headers

        out = b"".join(self.gw(env, start_response))
        data = json.loads(out.decode("utf-8")) if out else {}
        return str(state["status"]), data

    def test_assistant_layout_routes_and_visibility(self) -> None:
        status, payload = self._call(
            "POST",
            "/v2/chat/cases/case-v2-1/assistant-layout",
            {
                "relation_key": "rel-v2-1",
                "participant_a_id": "user-a",
                "participant_b_id": "user-b",
                "agent_id": "agent-c",
                "now": "2026-05-08 22:00:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        conversations = payload["layout"]["conversations"]
        self.assertEqual(len(conversations), 3)

        by_role = {
            item["metadata"]["layout_role"]: item
            for item in conversations
        }
        dm_a_id = by_role["assistant_dm_a"]["conversation_id"]
        dm_b_id = by_role["assistant_dm_b"]["conversation_id"]
        main_id = by_role["main_group"]["conversation_id"]

        status, payload = self._call(
            "GET",
            "/v2/chat/cases/case-v2-1/conversations",
            query="requester_id=user-a",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["conversation_count"], 2)

        status, payload = self._call(
            "POST",
            f"/v2/chat/conversations/{dm_a_id}/messages",
            {
                "author_id": "agent-c",
                "source": "agent",
                "body": "你可以先从周末安排开始。",
                "now": "2026-05-08 22:01:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        self.assertEqual(payload["message"]["source"], "agent")

        status, payload = self._call(
            "POST",
            f"/v2/chat/conversations/{main_id}/messages",
            {
                "author_id": "user-b",
                "body": "我周末一般会去跑步或者找咖啡馆坐坐。",
                "now": "2026-05-08 22:02:00",
            },
        )
        self.assertTrue(status.startswith("201"), status)
        self.assertEqual(payload["message"]["source"], "user")

        status, payload = self._call(
            "GET",
            f"/v2/chat/conversations/{dm_a_id}/messages",
            query="requester_id=user-a",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(len(payload["messages"]), 1)

        status, payload = self._call(
            "GET",
            f"/v2/chat/conversations/{dm_b_id}/messages",
            query="requester_id=user-a",
        )
        self.assertTrue(status.startswith("400"), status)
        self.assertIn("not allowed to read", payload["error"]["message"])

        status, payload = self._call(
            "GET",
            "/v2/chat/cases/case-v2-1/timeline",
            query="requester_id=agent-c&message_limit=20",
        )
        self.assertTrue(status.startswith("200"), status)
        self.assertEqual(payload["conversation_count"], 3)


if __name__ == "__main__":
    unittest.main()
