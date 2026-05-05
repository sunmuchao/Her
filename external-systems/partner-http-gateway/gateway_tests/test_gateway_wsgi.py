from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from unittest import mock


GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.app import PartnerGateway  # noqa: E402


def _wsgi_env(
    method: str,
    path: str,
    body: bytes | None = None,
    query: str = "",
    extra: dict | None = None,
) -> dict:
    body = body or b""
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "REMOTE_ADDR": "127.0.0.1",
    }
    if extra:
        env.update(extra)
    return env


class GatewayWsgiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gw = PartnerGateway(
            recommendation_dsn="mysql://noop",
            matchmaking_dsn="mysql://noop",
            chat_dsn="mysql://noop",
            db_pool_max=0,
        )
        self.status: str = ""
        self.headers: list[tuple[str, str]] = []

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            self.status = status
            self.headers = headers

        self.start_response = start_response

    def test_health(self) -> None:
        env = _wsgi_env("GET", "/health")
        out = b"".join(self.gw(env, self.start_response))
        self.assertIn("200", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertIn("recommendation", data.get("services", []))
        self.assertIn("chat", data.get("services", []))
        hdrs = {k.lower(): v for k, v in self.headers}
        self.assertIn("x-trace-id", hdrs)

    def test_health_respects_incoming_trace(self) -> None:
        env = _wsgi_env("GET", "/health", extra={"HTTP_X_TRACE_ID": "client-trace-1"})
        b"".join(self.gw(env, self.start_response))
        hdrs = {k.lower(): v for k, v in self.headers}
        self.assertEqual(hdrs.get("x-trace-id"), "client-trace-1")

    def test_rest_not_found(self) -> None:
        env = _wsgi_env("GET", "/v1/unknown")
        out = b"".join(self.gw(env, self.start_response))
        self.assertIn("404", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data.get("error", {}).get("code"), "not_found")

    def test_jsonrpc_unknown_method(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "method": "recommendation.nonexistent",
            "params": {},
            "id": 1,
        }
        env = _wsgi_env("POST", "/jsonrpc", json.dumps(req).encode("utf-8"))
        out = b"".join(self.gw(env, self.start_response))
        self.assertIn("200", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertIn("error", data)
        self.assertEqual(data["id"], 1)

    def test_jsonrpc_invalid_params_type(self) -> None:
        req = {"jsonrpc": "2.0", "method": "recommendation.get_subscription", "params": [], "id": 2}
        env = _wsgi_env("POST", "/jsonrpc", json.dumps(req).encode("utf-8"))
        out = b"".join(self.gw(env, self.start_response))
        data = json.loads(out.decode("utf-8"))
        self.assertIn("error", data)

    def test_search_profiles_route_returns_structured_trust_fields(self) -> None:
        fake_response = {
            "has_match": True,
            "result_count": 1,
            "results": [
                {
                    "id": 1,
                    "name": "候选人A",
                    "verified_level": "id",
                    "verified_label": "实名认证",
                    "trust_summary": {"headline": "已实名认证；其余关键信息以资料填写为主：职业、结婚意向"},
                }
            ],
        }
        with mock.patch("gateway.app.partner_search_profiles", return_value=fake_response) as mocked_search:
            env = _wsgi_env(
                "POST",
                "/v1/search/profiles",
                json.dumps(
                    {
                        "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                        "criteria": {"verified_level_min": "photo"},
                    }
                ).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["results"][0]["verified_label"], "实名认证")
        self.assertIn("trust_summary", payload["results"][0])
        mocked_search.assert_called_once()

    def test_chat_report_and_risk_case_routes(self) -> None:
        fake_submission = {
            "report": {"report_id": 11, "report_type": "fraud"},
            "risk_case": {"risk_case_id": "rsk-1", "status": "open", "recommended_action": "limit_chat"},
        }
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_submission) as mocked_chat:
            env = _wsgi_env(
                "POST",
                "/v1/chat/threads/cht-1/reports",
                json.dumps(
                    {
                        "reporter_id": "user-a",
                        "report_type": "fraud",
                        "reason_text": "对方开始聊投资和转账",
                        "message_id": 9,
                    }
                ).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["report"]["report_id"], 11)
        self.assertEqual(payload["risk_case"]["risk_case_id"], "rsk-1")
        mocked_chat.assert_called_once()

        with mock.patch.object(
            self.gw,
            "_with_chat",
            return_value=[{"risk_case_id": "rsk-1", "status": "open", "severity": "high"}],
        ) as mocked_chat:
            env = _wsgi_env("GET", "/v1/chat/risk-cases", query="status=open")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["risk_cases"][0]["risk_case_id"], "rsk-1")
        mocked_chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
