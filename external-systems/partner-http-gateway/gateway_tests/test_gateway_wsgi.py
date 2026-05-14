from __future__ import annotations

import io
import json
import os
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


def _auth_headers(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class GatewayWsgiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._discovery_runtime_patch = mock.patch.dict(
            os.environ,
            {"HER_DISCOVERY_AGENT_RUNTIME": "stub"},
            clear=False,
        )
        self._discovery_runtime_patch.start()
        self.addCleanup(self._discovery_runtime_patch.stop)
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

    def _run_with_gateway(self, gateway: PartnerGateway, env: dict) -> tuple[str, dict]:
        status = ""
        headers: list[tuple[str, str]] = []

        def start_response(current_status: str, current_headers: list[tuple[str, str]]) -> None:
            nonlocal status, headers
            status = current_status
            headers = current_headers

        out = b"".join(gateway(env, start_response))
        self.headers = headers
        payload = json.loads(out.decode("utf-8")) if out else {}
        return status, payload

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

    def test_health_skips_static_token_auth(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            status, payload = self._run_with_gateway(gw, _wsgi_env("GET", "/health"))

        self.assertIn("200", status)
        self.assertTrue(payload["ok"])

    def test_rest_not_found(self) -> None:
        env = _wsgi_env("GET", "/v1/unknown")
        out = b"".join(self.gw(env, self.start_response))
        self.assertIn("404", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data.get("error", {}).get("code"), "not_found")

    def test_discovery_create_session_returns_render_model(self) -> None:
        env = _wsgi_env(
            "POST",
            "/v1/discovery/sessions",
            json.dumps({"requester_id": 70001, "profile_id": 10001}).encode("utf-8"),
        )
        out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data["session"]["status"], "active")
        self.assertEqual(data["session"]["phase"], "collecting_preferences")
        self.assertTrue(data["view"]["timeline"])
        self.assertTrue(data["view"]["suggested_actions"])
        self.assertIn("trace_id", data)

    def test_discovery_turn_accepts_user_message(self) -> None:
        create_env = _wsgi_env(
            "POST",
            "/v1/discovery/sessions",
            json.dumps({"requester_id": 70001, "profile_id": 10001}).encode("utf-8"),
        )
        created = json.loads(b"".join(self.gw(create_env, self.start_response)).decode("utf-8"))
        session_id = created["session"]["session_id"]

        turn_env = _wsgi_env(
            "POST",
            f"/v1/discovery/sessions/{session_id}/turns",
            json.dumps({"user_message": "我在无锡，想找认真恋爱的人。"}).encode("utf-8"),
        )
        out = b"".join(self.gw(turn_env, self.start_response))

        self.assertIn("200", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data["session"]["session_id"], session_id)
        timeline = data["view"]["timeline"]
        self.assertEqual(timeline[-2]["item_type"], "user_message")
        self.assertEqual(timeline[-1]["item_type"], "assistant_message")

    def test_discovery_turn_accepts_action_id_and_blocks_replay(self) -> None:
        create_env = _wsgi_env(
            "POST",
            "/v1/discovery/sessions",
            json.dumps({"requester_id": 70001, "profile_id": 10001}).encode("utf-8"),
        )
        created = json.loads(b"".join(self.gw(create_env, self.start_response)).decode("utf-8"))
        session_id = created["session"]["session_id"]
        action_id = created["view"]["suggested_actions"][0]["action_id"]

        turn_env = _wsgi_env(
            "POST",
            f"/v1/discovery/sessions/{session_id}/turns",
            json.dumps({"action_id": action_id}).encode("utf-8"),
        )
        out = b"".join(self.gw(turn_env, self.start_response))

        self.assertIn("200", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data["session"]["session_id"], session_id)

        replay_env = _wsgi_env(
            "POST",
            f"/v1/discovery/sessions/{session_id}/turns",
            json.dumps({"action_id": action_id}).encode("utf-8"),
        )
        replay_out = b"".join(self.gw(replay_env, self.start_response))

        self.assertIn("409", self.status)
        replay_data = json.loads(replay_out.decode("utf-8"))
        self.assertEqual(replay_data["error_code"], "DISCOVERY_ACTION_EXPIRED")
        self.assertTrue(replay_data["retryable"])

    def test_discovery_get_session_and_profile_detail(self) -> None:
        create_env = _wsgi_env(
            "POST",
            "/v1/discovery/sessions",
            json.dumps({"requester_id": 70001, "profile_id": 10001}).encode("utf-8"),
        )
        created = json.loads(b"".join(self.gw(create_env, self.start_response)).decode("utf-8"))
        session_id = created["session"]["session_id"]

        session_env = _wsgi_env("GET", f"/v1/discovery/sessions/{session_id}")
        session_out = b"".join(self.gw(session_env, self.start_response))

        self.assertIn("200", self.status)
        session_data = json.loads(session_out.decode("utf-8"))
        self.assertEqual(session_data["session"]["session_id"], session_id)

        detail_payload = {
            "id": 10001,
            "name": "林知夏",
            "photo_preview": ["https://static.example.com/p/10001/1.jpg"],
            "verification_items": [
                {"key": "photo", "status": "verified", "summary": "已真人照片认证（4张）"},
            ],
            "trust_summary": {"headline": "已实名认证"},
            "caution_items": ["工作日回复可能偏晚。"],
            "trust_actions": ["建议先视频核验真人状态"],
            "notes_summary": "平时作息规律，周末喜欢徒步和看展。",
            "profile": {
                "age": 29,
                "city": "无锡",
                "job": "中学老师",
                "education": "硕士",
                "relationship_goal": "认真恋爱",
            },
        }

        with mock.patch.dict(os.environ, {"HER_DISCOVERY_PROFILE_SOURCE": "mysql://demo"}, clear=False), mock.patch(
            "discovery_system.service.load_profile_detail",
            return_value=detail_payload,
        ):
            detail_env = _wsgi_env(
                "GET",
                "/v1/discovery/profiles/10001",
                query=f"session_id={session_id}",
            )
            detail_out = b"".join(self.gw(detail_env, self.start_response))

        self.assertIn("200", self.status)
        detail_data = json.loads(detail_out.decode("utf-8"))
        self.assertEqual(detail_data["profile_id"], 10001)
        self.assertEqual(detail_data["detail_view"]["hero"]["name"], "林知夏")
        self.assertEqual(detail_data["detail_view"]["photo_gallery"][0]["image_url"], "https://static.example.com/p/10001/1.jpg")
        self.assertIn("detail_view", detail_data)

    def test_live_video_demo_route_serves_html(self) -> None:
        env = _wsgi_env("GET", "/demo/live-video-verification")
        out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        hdrs = {k.lower(): v for k, v in self.headers}
        self.assertEqual(hdrs.get("content-type"), "text/html; charset=utf-8")
        body = out.decode("utf-8")
        self.assertIn("Live Video Verification Demo", body)
        self.assertIn("/v1/verifications/live-video-challenges", body)
        self.assertNotIn("machine_review_inputs", body)

    def test_live_video_demo_route_skips_api_key_guard(self) -> None:
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_API_KEY": "demo-secret"}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            status = ""
            headers: list[tuple[str, str]] = []

            def start_response(current_status: str, current_headers: list[tuple[str, str]]) -> None:
                nonlocal status, headers
                status = current_status
                headers = current_headers

            env = _wsgi_env("GET", "/demo/live-video-verification")
            out = b"".join(gw(env, start_response))

        self.assertIn("200", status)
        self.assertEqual({k.lower(): v for k, v in headers}.get("content-type"), "text/html; charset=utf-8")
        self.assertIn("Live Video Verification Demo", out.decode("utf-8"))

    def test_live_video_demo_asset_route_serves_local_module(self) -> None:
        env = _wsgi_env("GET", "/demo/assets/mediapipe/vision_bundle.mjs")
        out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        hdrs = {k.lower(): v for k, v in self.headers}
        self.assertIn("javascript", hdrs.get("content-type", ""))
        body = out.decode("utf-8")
        self.assertIn("FaceLandmarker", body)

    def test_live_video_demo_asset_route_skips_api_key_guard(self) -> None:
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_API_KEY": "demo-secret"}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            status = ""

            def start_response(current_status: str, _current_headers: list[tuple[str, str]]) -> None:
                nonlocal status
                status = current_status

            env = _wsgi_env("GET", "/demo/assets/mediapipe/vision_bundle.mjs")
            b"".join(gw(env, start_response))

        self.assertIn("200", status)

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

    def test_jsonrpc_async_job_dashboard_aggregates_three_systems(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        req = {
            "jsonrpc": "2.0",
            "method": "ops.get_async_job_dashboard",
            "params": {"limit": 2},
            "id": 3,
        }
        rec_summary = {
            "total": 1,
            "backlog_open": 1,
            "due_now": 1,
            "processing_overdue": 0,
            "by_status": {"pending": 1, "processing": 0, "retry_pending": 0, "succeeded": 0, "failed": 0},
        }
        rec_job_types = [
            {
                "job_type": "recommendation.refresh_due_subscriptions",
                "total": 1,
                "backlog_open": 1,
                "due_now": 1,
                "processing_overdue": 0,
                "oldest_due_created_at": None,
                "latest_finished_at": None,
                "by_status": {"pending": 1, "processing": 0, "retry_pending": 0, "succeeded": 0, "failed": 0},
            }
        ]
        mm_summary = {
            "total": 2,
            "backlog_open": 1,
            "due_now": 0,
            "processing_overdue": 0,
            "by_status": {"pending": 0, "processing": 1, "retry_pending": 0, "succeeded": 1, "failed": 0},
        }
        mm_job_types = [
            {
                "job_type": "matchmaking.build_mutual_pairs",
                "total": 2,
                "backlog_open": 1,
                "due_now": 0,
                "processing_overdue": 0,
                "oldest_due_created_at": None,
                "latest_finished_at": "2026-05-14 12:01:00",
                "by_status": {"pending": 0, "processing": 1, "retry_pending": 0, "succeeded": 1, "failed": 0},
            }
        ]
        chat_summary = {
            "total": 3,
            "backlog_open": 2,
            "due_now": 1,
            "processing_overdue": 1,
            "by_status": {"pending": 0, "processing": 0, "retry_pending": 1, "succeeded": 1, "failed": 1},
        }
        chat_job_types = [
            {
                "job_type": "chat.run_maintenance",
                "total": 3,
                "backlog_open": 2,
                "due_now": 1,
                "processing_overdue": 1,
                "oldest_due_created_at": "2026-05-14 11:59:00",
                "latest_finished_at": "2026-05-14 12:02:00",
                "by_status": {"pending": 0, "processing": 0, "retry_pending": 1, "succeeded": 1, "failed": 1},
            }
        ]
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_recommendation_async_jobs":
                    return rec_summary
                if fn.__name__ == "summarize_recommendation_async_jobs_by_type":
                    return rec_job_types
                if fn.__name__ == "list_recommendation_async_jobs":
                    self.assertEqual(kwargs["limit"], 2)
                    return [{"job_id": "job-rec-1", "job_type": "recommendation.refresh_due_subscriptions", "status": "pending", "payload": {}, "result": None}]
                raise AssertionError(fn.__name__)

            def mm_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_matchmaking_async_jobs":
                    return mm_summary
                if fn.__name__ == "summarize_matchmaking_async_jobs_by_type":
                    return mm_job_types
                if fn.__name__ == "list_matchmaking_async_jobs":
                    self.assertEqual(kwargs["limit"], 2)
                    return [{"job_id": "job-mm-1", "job_type": "matchmaking.build_mutual_pairs", "status": "processing", "payload": {}, "result": None}]
                raise AssertionError(fn.__name__)

            def chat_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_chat_async_jobs":
                    return chat_summary
                if fn.__name__ == "summarize_chat_async_jobs_by_type":
                    return chat_job_types
                if fn.__name__ == "list_chat_async_jobs":
                    self.assertEqual(kwargs["limit"], 2)
                    return [{"job_id": "job-chat-1", "job_type": "chat.run_maintenance", "status": "retry_pending", "payload": {}, "result": None}]
                raise AssertionError(fn.__name__)

            with (
                mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect),
                mock.patch.object(gw, "_with_mm", side_effect=mm_side_effect),
                mock.patch.object(gw, "_with_chat", side_effect=chat_side_effect),
            ):
                env = _wsgi_env(
                    "POST",
                    "/jsonrpc",
                    json.dumps(req).encode("utf-8"),
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["result"]["systems"]["chat"]["recent_jobs"][0]["poll_path"], "/v1/chat/jobs/job-chat-1")
        self.assertEqual(payload["result"]["systems"]["recommendation"]["job_types"][0]["job_type"], "recommendation.refresh_due_subscriptions")
        self.assertEqual(payload["result"]["job_types"][0]["job_type"], "chat.run_maintenance")
        self.assertEqual(payload["result"]["job_types"][0]["target"], "chat")
        self.assertEqual(payload["result"]["totals"]["total"], 6)
        self.assertEqual(payload["result"]["totals"]["backlog_open"], 4)
        self.assertEqual(payload["result"]["totals"]["failed"], 1)

    def test_static_token_auth_rejects_missing_credentials(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "POST",
                "/v1/search/profiles",
                json.dumps({"source": "mysql://demo", "criteria": {}}).encode("utf-8"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("401", status)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_end_user_cannot_impersonate_other_user_in_trust_hub(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "GET",
                "/v1/user-center/trust-hub",
                query="user_id=user-b&profile_id=3001",
                extra=_auth_headers("token-user-a"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_end_user_cannot_impersonate_other_reporter(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "POST",
                "/v1/chat/threads/cht-1/reports",
                json.dumps({"reporter_id": "user-b", "report_type": "fraud"}).encode("utf-8"),
                extra=_auth_headers("token-user-a"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_profile_reviewer_actor_is_injected_into_review_submission(self) -> None:
        tokens = json.dumps(
            {"token-reviewer": {"actor_id": "reviewer-7", "roles": ["profile_reviewer"]}}
        )
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with mock.patch.object(gw, "_with_chat", return_value={"submission_id": "sub-1"}) as mocked_chat:
                env = _wsgi_env(
                    "POST",
                    "/v1/verifications/live-video-submissions/sub-1/review",
                    json.dumps({"decision": "approve"}).encode("utf-8"),
                    extra=_auth_headers("token-reviewer"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["submission"]["submission_id"], "sub-1")
        mocked_chat.assert_called_once()
        self.assertEqual(mocked_chat.call_args.args[2], "reviewer-7")

    def test_end_user_cannot_review_risk_case(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "POST",
                "/v1/chat/risk-cases/rsk-1/review",
                json.dumps({"status": "closed_safe"}).encode("utf-8"),
                extra=_auth_headers("token-user-a"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_customer_support_can_read_thread_on_behalf_of_participant(self) -> None:
        tokens = json.dumps(
            {"token-support": {"actor_id": "support-1", "roles": ["customer_support"]}}
        )
        fake_thread = {
            "thread_id": "cht-1",
            "participant_a_id": "user-a",
            "participant_b_id": "user-b",
        }
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with mock.patch.object(gw, "_with_chat", return_value=fake_thread):
                env = _wsgi_env(
                    "GET",
                    "/v1/chat/threads/cht-1",
                    query="requester_id=user-a",
                    extra=_auth_headers("token-support"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["thread"]["thread_id"], "cht-1")

    def test_jsonrpc_reviewer_actor_is_injected(self) -> None:
        tokens = json.dumps(
            {"token-reviewer": {"actor_id": "reviewer-9", "roles": ["profile_reviewer"]}}
        )
        req = {
            "jsonrpc": "2.0",
            "method": "profile.review_field_verification",
            "params": {"submission_id": "pfv-1", "decision": "approve"},
            "id": 11,
        }
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with mock.patch.object(gw, "_with_chat", return_value={"submission_id": "pfv-1"}) as mocked_chat:
                env = _wsgi_env(
                    "POST",
                    "/jsonrpc",
                    json.dumps(req).encode("utf-8"),
                    extra=_auth_headers("token-reviewer"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["result"]["submission_id"], "pfv-1")
        self.assertEqual(mocked_chat.call_args.args[2], "reviewer-9")

    def test_end_user_cannot_read_other_recommendation_subscription(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "70001", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with mock.patch.object(
                gw,
                "_with_rec",
                return_value={"subscription_id": "sub-2", "requester_id": 70002},
            ):
                env = _wsgi_env(
                    "GET",
                    "/v1/recommendation/subscriptions/sub-2",
                    extra=_auth_headers("token-user-a"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_recommendation_action_binds_current_actor(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "70001", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "get_subscription":
                    return {"subscription_id": "sub-1", "requester_id": 70001}
                if fn.__name__ == "record_recommendation_action":
                    return {"subscription_id": kwargs["subscription_id"], "candidate_id": kwargs["candidate_id"]}
                raise AssertionError(fn.__name__)

            with mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect) as mocked_rec:
                env = _wsgi_env(
                    "POST",
                    "/v1/recommendation/actions",
                    json.dumps(
                        {
                            "subscription_id": "sub-1",
                            "candidate_id": 99,
                            "action_type": "save",
                        }
                    ).encode("utf-8"),
                    extra=_auth_headers("token-user-a"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["recommendation"]["candidate_id"], 99)
        self.assertEqual(mocked_rec.call_args.kwargs["actor_id"], "70001")

    def test_end_user_cannot_refresh_due_recommendations(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "70001", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "POST",
                "/v1/recommendation/subscriptions/refresh-due",
                json.dumps({}).encode("utf-8"),
                extra=_auth_headers("token-user-a"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_refresh_due_enqueues_async_job(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        fake_job = {
            "job_id": "job-1",
            "job_type": "recommendation.refresh_due_subscriptions",
            "status": "pending",
            "payload": {"subscription_ids": ["sub-1"], "now": "2026-05-14 12:00:00"},
            "result": None,
            "attempt_count": 0,
            "max_attempts": 3,
            "created_at": "2026-05-14 12:00:00",
            "started_at": None,
            "finished_at": None,
            "next_attempt_at": "2026-05-14 12:00:00",
            "created_by": "ops-1",
            "trace_id": "trace-1",
            "claim_token": None,
            "claim_started_at": None,
            "claim_worker": None,
            "error_text": None,
        }
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "enqueue_recommendation_async_job":
                    self.assertEqual(kwargs["job_type"], "recommendation.refresh_due_subscriptions")
                    self.assertEqual(kwargs["payload"]["subscription_ids"], ["sub-1"])
                    self.assertEqual(kwargs["payload"]["now"], "2026-05-14 12:00:00")
                    return fake_job
                raise AssertionError(fn.__name__)

            with mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect):
                env = _wsgi_env(
                    "POST",
                    "/v1/recommendation/subscriptions/refresh-due",
                    json.dumps({"subscription_ids": ["sub-1"], "now": "2026-05-14T12:00:00"}).encode("utf-8"),
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("202", status)
        self.assertEqual(payload["job"]["job_id"], "job-1")
        self.assertEqual(payload["job"]["poll_path"], "/v1/recommendation/jobs/job-1")
        self.assertEqual(payload["job"]["target"], "recommendation")

    def test_get_recommendation_job_returns_job_payload(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        fake_job = {
            "job_id": "job-1",
            "job_type": "recommendation.refresh_due_subscriptions",
            "status": "succeeded",
            "payload": {"subscription_ids": ["sub-1"]},
            "result": {"summaries": [{"subscription_id": "sub-1"}], "errors": []},
            "attempt_count": 1,
            "max_attempts": 3,
            "created_at": "2026-05-14 12:00:00",
            "started_at": "2026-05-14 12:00:01",
            "finished_at": "2026-05-14 12:00:02",
            "next_attempt_at": None,
            "created_by": "ops-1",
            "trace_id": "trace-1",
            "claim_token": None,
            "claim_started_at": None,
            "claim_worker": None,
            "error_text": None,
        }
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "get_recommendation_async_job":
                    self.assertEqual(args[0], "job-1")
                    return fake_job
                raise AssertionError(fn.__name__)

            with mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect):
                env = _wsgi_env(
                    "GET",
                    "/v1/recommendation/jobs/job-1",
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(payload["job"]["result"]["summaries"][0]["subscription_id"], "sub-1")

    def test_list_recommendation_jobs_returns_summary_and_jobs(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        fake_jobs = [
            {
                "job_id": "job-1",
                "job_type": "recommendation.refresh_due_subscriptions",
                "status": "pending",
                "payload": {"subscription_ids": ["sub-1"]},
                "result": None,
                "attempt_count": 0,
                "max_attempts": 3,
                "created_at": "2026-05-14 12:00:00",
                "started_at": None,
                "finished_at": None,
                "next_attempt_at": "2026-05-14 12:00:00",
                "created_by": "ops-1",
                "trace_id": "trace-1",
                "claim_token": None,
                "claim_started_at": None,
                "claim_worker": None,
                "error_text": None,
            }
        ]
        fake_summary = {
            "total": 4,
            "backlog_open": 2,
            "due_now": 1,
            "processing_overdue": 0,
            "oldest_due_created_at": "2026-05-14 12:00:00",
            "latest_finished_at": "2026-05-14 12:03:00",
            "by_status": {
                "pending": 1,
                "processing": 0,
                "retry_pending": 1,
                "succeeded": 1,
                "failed": 1,
            },
        }
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "list_recommendation_async_jobs":
                    self.assertEqual(kwargs["statuses"], ["pending", "retry_pending"])
                    self.assertEqual(kwargs["limit"], 2)
                    return fake_jobs
                if fn.__name__ == "summarize_recommendation_async_jobs":
                    return fake_summary
                raise AssertionError(fn.__name__)

            with mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect):
                env = _wsgi_env(
                    "GET",
                    "/v1/recommendation/jobs",
                    query="status=pending,retry_pending&limit=2",
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["summary"]["backlog_open"], 2)
        self.assertEqual(payload["jobs"][0]["job_id"], "job-1")
        self.assertEqual(payload["jobs"][0]["poll_path"], "/v1/recommendation/jobs/job-1")

    def test_async_job_dashboard_aggregates_three_systems(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        rec_jobs = [
            {
                "job_id": "job-rec-1",
                "job_type": "recommendation.refresh_due_subscriptions",
                "status": "pending",
                "payload": {"subscription_ids": ["sub-1"]},
                "result": None,
            }
        ]
        mm_jobs = [
            {
                "job_id": "job-mm-1",
                "job_type": "matchmaking.build_mutual_pairs",
                "status": "failed",
                "payload": {},
                "result": None,
            }
        ]
        chat_jobs = [
            {
                "job_id": "job-chat-1",
                "job_type": "chat.run_maintenance",
                "status": "processing",
                "payload": {"persona_limit": 10},
                "result": None,
            }
        ]
        rec_summary = {
            "total": 4,
            "backlog_open": 2,
            "due_now": 1,
            "processing_overdue": 0,
            "by_status": {
                "pending": 1,
                "processing": 0,
                "retry_pending": 1,
                "succeeded": 1,
                "failed": 1,
            },
        }
        rec_job_types = [
            {
                "job_type": "recommendation.refresh_due_subscriptions",
                "total": 2,
                "backlog_open": 2,
                "due_now": 1,
                "processing_overdue": 0,
                "oldest_due_created_at": "2026-05-14 12:00:00",
                "latest_finished_at": None,
                "by_status": {
                    "pending": 1,
                    "processing": 0,
                    "retry_pending": 1,
                    "succeeded": 0,
                    "failed": 0,
                },
            },
            {
                "job_type": "recommendation.deliver_in_app_recommendations",
                "total": 2,
                "backlog_open": 0,
                "due_now": 0,
                "processing_overdue": 0,
                "oldest_due_created_at": None,
                "latest_finished_at": "2026-05-14 12:03:00",
                "by_status": {
                    "pending": 0,
                    "processing": 0,
                    "retry_pending": 0,
                    "succeeded": 1,
                    "failed": 1,
                },
            },
        ]
        mm_summary = {
            "total": 3,
            "backlog_open": 1,
            "due_now": 1,
            "processing_overdue": 0,
            "by_status": {
                "pending": 1,
                "processing": 0,
                "retry_pending": 0,
                "succeeded": 1,
                "failed": 1,
            },
        }
        mm_job_types = [
            {
                "job_type": "matchmaking.build_mutual_pairs",
                "total": 3,
                "backlog_open": 1,
                "due_now": 1,
                "processing_overdue": 0,
                "oldest_due_created_at": "2026-05-14 11:58:00",
                "latest_finished_at": "2026-05-14 12:04:00",
                "by_status": {
                    "pending": 1,
                    "processing": 0,
                    "retry_pending": 0,
                    "succeeded": 1,
                    "failed": 1,
                },
            }
        ]
        chat_summary = {
            "total": 5,
            "backlog_open": 3,
            "due_now": 2,
            "processing_overdue": 1,
            "by_status": {
                "pending": 0,
                "processing": 1,
                "retry_pending": 2,
                "succeeded": 1,
                "failed": 1,
            },
        }
        chat_job_types = [
            {
                "job_type": "chat.run_maintenance",
                "total": 5,
                "backlog_open": 3,
                "due_now": 2,
                "processing_overdue": 1,
                "oldest_due_created_at": "2026-05-14 11:57:00",
                "latest_finished_at": "2026-05-14 12:05:00",
                "by_status": {
                    "pending": 0,
                    "processing": 1,
                    "retry_pending": 2,
                    "succeeded": 1,
                    "failed": 1,
                },
            }
        ]
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )

            def rec_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_recommendation_async_jobs":
                    return rec_summary
                if fn.__name__ == "summarize_recommendation_async_jobs_by_type":
                    return rec_job_types
                if fn.__name__ == "list_recommendation_async_jobs":
                    self.assertEqual(kwargs["limit"], 3)
                    return rec_jobs
                raise AssertionError(fn.__name__)

            def mm_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_matchmaking_async_jobs":
                    return mm_summary
                if fn.__name__ == "summarize_matchmaking_async_jobs_by_type":
                    return mm_job_types
                if fn.__name__ == "list_matchmaking_async_jobs":
                    self.assertEqual(kwargs["limit"], 3)
                    return mm_jobs
                raise AssertionError(fn.__name__)

            def chat_side_effect(fn, *args, **kwargs):
                if fn.__name__ == "summarize_chat_async_jobs":
                    return chat_summary
                if fn.__name__ == "summarize_chat_async_jobs_by_type":
                    return chat_job_types
                if fn.__name__ == "list_chat_async_jobs":
                    self.assertEqual(kwargs["limit"], 3)
                    return chat_jobs
                raise AssertionError(fn.__name__)

            with (
                mock.patch.object(gw, "_with_rec", side_effect=rec_side_effect),
                mock.patch.object(gw, "_with_mm", side_effect=mm_side_effect),
                mock.patch.object(gw, "_with_chat", side_effect=chat_side_effect),
            ):
                env = _wsgi_env(
                    "GET",
                    "/v1/ops/async-jobs/dashboard",
                    query="limit=3",
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["systems"]["recommendation"]["recent_jobs"][0]["poll_path"], "/v1/recommendation/jobs/job-rec-1")
        self.assertEqual(payload["systems"]["recommendation"]["job_types"][0]["job_type"], "recommendation.refresh_due_subscriptions")
        self.assertEqual(payload["systems"]["matchmaking"]["recent_jobs"][0]["poll_path"], "/v1/matchmaking/jobs/job-mm-1")
        self.assertEqual(payload["systems"]["chat"]["recent_jobs"][0]["target"], "chat")
        self.assertEqual(payload["job_types"][0]["job_type"], "chat.run_maintenance")
        self.assertEqual(payload["job_types"][0]["target"], "chat")
        self.assertEqual(
            payload["totals"],
            {
                "total": 12,
                "backlog_open": 6,
                "due_now": 4,
                "processing_overdue": 1,
                "pending": 2,
                "processing": 1,
                "retry_pending": 3,
                "succeeded": 3,
                "failed": 3,
            },
        )

    def test_end_user_cannot_list_matchmaking_pairs(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            env = _wsgi_env(
                "GET",
                "/v1/matchmaking/pairs",
                extra=_auth_headers("token-user-a"),
            )
            status, payload = self._run_with_gateway(gw, env)

        self.assertIn("403", status)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_matchmaking_reply_defaults_member_to_current_actor(self) -> None:
        tokens = json.dumps({"token-user-a": {"actor_id": "user-a", "roles": ["end_user"]}})
        fake_case = {
            "case_id": "case-1",
            "first_contact_member_id": "pool-a",
            "second_contact_member_id": "pool-b",
        }
        member_a = {"member_id": "pool-a", "user_key": "user-a"}
        member_b = {"member_id": "pool-b", "user_key": "user-b"}

        def mm_side_effect(fn, *args, **kwargs):
            if fn.__name__ == "get_match_case":
                return fake_case
            if fn.__name__ == "get_pool_member":
                return member_a if args[0] == "pool-a" else member_b
            if fn.__name__ == "record_case_reply":
                return {"case_id": args[0], "member_id": kwargs["member_id"], "reply_type": kwargs["reply_type"]}
            raise AssertionError(fn.__name__)

        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with mock.patch.object(gw, "_with_mm", side_effect=mm_side_effect):
                env = _wsgi_env(
                    "POST",
                    "/v1/matchmaking/cases/case-1/reply",
                    json.dumps({"reply_type": "accept"}).encode("utf-8"),
                    extra=_auth_headers("token-user-a"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["case"]["member_id"], "pool-a")

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

    def test_photo_review_request_and_notification_routes(self) -> None:
        fake_request = {
            "submission_id": "vfy-req-1",
            "status": "awaiting_submission",
            "photo_review_task": {"task_kind": "photo_review"},
        }
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_request) as mocked_chat:
            env = _wsgi_env(
                "POST",
                "/v1/verifications/live-video-requests",
                json.dumps(
                    {
                        "user_id": "candidate-a",
                        "signal_codes": ["suspected_fake_photo"],
                        "risk_case_id": "rsk-photo-1",
                    }
                ).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["request"]["submission_id"], "vfy-req-1")
        mocked_chat.assert_called_once()

        with mock.patch.object(self.gw, "_with_chat", return_value=[fake_request]) as mocked_chat:
            env = _wsgi_env("GET", "/v1/verifications/live-video-requests", query="user_id=candidate-a")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["requests"][0]["submission_id"], "vfy-req-1")
        mocked_chat.assert_called_once()

        with mock.patch.object(
            self.gw,
            "_with_chat",
            return_value=[{"notification_id": 1, "notification_type": "photo_review_requested"}],
        ) as mocked_chat:
            env = _wsgi_env("GET", "/v1/verifications/notifications", query="submission_id=vfy-req-1")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["notifications"][0]["notification_type"], "photo_review_requested")
        mocked_chat.assert_called_once()

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

    def test_chat_meeting_feedback_risk_signals_and_risk_overview_routes(self) -> None:
        fake_feedback = {
            "feedback": {"feedback_id": 31, "counterpart_user_id": "user-b"},
            "generated_reports": [{"report_id": 41, "report_type": "photo_mismatch"}],
            "risk_cases": [{"risk_case_id": "rsk-2", "recommended_action": "require_verification"}],
        }
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_feedback) as mocked_chat:
            env = _wsgi_env(
                "POST",
                "/v1/chat/threads/cht-2/meeting-feedback",
                json.dumps(
                    {
                        "reviewer_id": "user-a",
                        "photo_match_status": "mismatch",
                        "profile_consistency_status": "unclear",
                    }
                ).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["feedback"]["feedback_id"], 31)
        self.assertEqual(payload["generated_reports"][0]["report_type"], "photo_mismatch")
        mocked_chat.assert_called_once()

        with mock.patch.object(
            self.gw,
            "_with_chat",
            return_value=[{"signal_id": 7, "signal_code": "repeated_opening"}],
        ) as mocked_chat:
            env = _wsgi_env("GET", "/v1/chat/risk-signals", query="subject_user_id=user-b")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["risk_signals"][0]["signal_code"], "repeated_opening")
        mocked_chat.assert_called_once()

        with mock.patch.object(
            self.gw,
            "_with_chat",
            return_value={
                "thread_id": "cht-2",
                "counterpart_user_id": "user-b",
                "caution_messages": ["对方存在资料一致性风险，建议先确认照片、职业和收入信息。"],
            },
        ) as mocked_chat:
            env = _wsgi_env("GET", "/v1/chat/threads/cht-2/risk-overview", query="requester_id=user-a")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["risk_overview"]["counterpart_user_id"], "user-b")
        self.assertIn("资料一致性风险", payload["risk_overview"]["caution_messages"][0])
        mocked_chat.assert_called_once()

    def test_fraud_network_observation_and_query_routes(self) -> None:
        fake_observation = {
            "subject_user_id": "suspect-a",
            "entity_count": 4,
            "entity_types": ["device_fingerprint", "external_contact"],
        }
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_observation) as mocked_chat:
            env = _wsgi_env(
                "POST",
                "/v1/chat/fraud-networks/observations",
                json.dumps(
                    {
                        "subject_user_id": "suspect-a",
                        "signal_codes": ["investment"],
                        "evidence": {"device_fingerprint": "device-1"},
                    }
                ).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["observation"]["entity_count"], 4)
        mocked_chat.assert_called_once()

        fake_networks = [
            {"subject_user_id": "suspect-a", "graph_risk_score": 180, "applied_action": "freeze"},
            {"subject_user_id": "suspect-b", "graph_risk_score": 120, "applied_action": "limit_chat"},
        ]
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_networks) as mocked_chat:
            env = _wsgi_env("GET", "/v1/chat/fraud-networks", query="minimum_score=100")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["fraud_networks"][0]["subject_user_id"], "suspect-a")
        mocked_chat.assert_called_once()

        fake_profile = {"subject_user_id": "suspect-a", "graph_risk_score": 180}
        fake_overview = {
            "subject_user_id": "suspect-a",
            "network_profile": fake_profile,
            "account_links": [{"linked_user_id": "suspect-b", "link_score": 95}],
            "moderation_state": {"applied_action": "freeze"},
        }
        with mock.patch.object(self.gw, "_with_chat", side_effect=[fake_profile, fake_overview]) as mocked_chat:
            env = _wsgi_env("GET", "/v1/chat/fraud-networks/suspect-a")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["fraud_network"]["network_profile"]["graph_risk_score"], 180)
        self.assertEqual(payload["fraud_network"]["moderation_state"]["applied_action"], "freeze")
        self.assertEqual(mocked_chat.call_count, 2)

    def test_user_trust_hub_and_profile_review_appeal_routes(self) -> None:
        fake_hub = {
            "summary": {"pending_verification_count": 2, "pending_appeal_count": 1},
            "verification_center": {"items": [{"field_key": "job", "status": "awaiting_submission"}]},
        }
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_hub) as mocked_chat:
            env = _wsgi_env("GET", "/v1/user-center/trust-hub", query="user_id=candidate-1&profile_id=3001")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["trust_hub"]["summary"]["pending_verification_count"], 2)
        mocked_chat.assert_called_once()

        fake_appeal = {"appeal_id": 9, "appeal_status": "submitted"}
        with mock.patch.object(self.gw, "_with_chat", return_value=fake_appeal) as mocked_chat:
            env = _wsgi_env(
                "POST",
                "/v1/profile-review/risk-cases/prc-1/appeals",
                json.dumps({"appellant_id": "candidate-1", "reason_text": "申请复核"}).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("201", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["appeal"]["appeal_status"], "submitted")
        mocked_chat.assert_called_once()

        with mock.patch.object(self.gw, "_with_chat", return_value=fake_appeal) as mocked_chat:
            env = _wsgi_env("GET", "/v1/profile-review/appeals/9")
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["appeal"]["appeal_id"], 9)
        mocked_chat.assert_called_once()

    def test_profile_photo_risk_routes(self) -> None:
        fake_run = {"score_run_id": 12, "photo_authenticity_score": 38}
        fake_queue = [{"queue_item_id": 7, "queue_status": "open"}]

        with mock.patch.object(self.gw, "_with_chat", return_value=[fake_run]) as mocked_chat:
            env = _wsgi_env("GET", "/v1/profile-review/photo-risk/runs", query="profile_id=3001")
            out = b"".join(self.gw(env, self.start_response))
        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["score_runs"][0]["score_run_id"], 12)
        mocked_chat.assert_called_once()

        with mock.patch.object(self.gw, "_with_chat", return_value=fake_run) as mocked_chat:
            env = _wsgi_env("GET", "/v1/profile-review/photo-risk/runs/12")
            out = b"".join(self.gw(env, self.start_response))
        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["score_run"]["photo_authenticity_score"], 38)
        mocked_chat.assert_called_once()

        with mock.patch.object(self.gw, "_with_chat", return_value=fake_queue) as mocked_chat:
            env = _wsgi_env("GET", "/v1/profile-review/photo-risk/review-queue", query="queue_status=open")
            out = b"".join(self.gw(env, self.start_response))
        self.assertIn("200", self.status)
        payload = json.loads(out.decode("utf-8"))
        self.assertEqual(payload["review_queue"][0]["queue_item_id"], 7)
        mocked_chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
