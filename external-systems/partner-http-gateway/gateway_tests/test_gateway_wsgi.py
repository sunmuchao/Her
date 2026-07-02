from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock


GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.app import PartnerGateway  # noqa: E402
from gateway import auth_routes  # noqa: E402
from gateway.identity import ActorPrincipal  # noqa: E402
from gateway.logging_setup import configure_gateway_logging  # noqa: E402
from gateway_tests.helpers import build_wsgi_env as _wsgi_env, run_wsgi_json  # noqa: E402


def _auth_headers(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _restore_logger_state(
    logger: logging.Logger,
    *,
    handlers: list[logging.Handler],
    level: int,
    propagate: bool,
) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        if handler not in handlers:
            handler.close()
    for handler in handlers:
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = propagate


@contextmanager
def _configured_gateway_logging(*, stream: io.StringIO, log_file: str | None = None):
    root_logger = logging.getLogger()
    pipeline_logger = logging.getLogger("her.pipeline")
    root_handlers = root_logger.handlers[:]
    pipeline_handlers = pipeline_logger.handlers[:]
    root_level = root_logger.level
    pipeline_level = pipeline_logger.level
    root_propagate = root_logger.propagate
    pipeline_propagate = pipeline_logger.propagate
    try:
        configure_gateway_logging(stream=stream, log_file=log_file)
        yield
    finally:
        _restore_logger_state(
            root_logger,
            handlers=root_handlers,
            level=root_level,
            propagate=root_propagate,
        )
        _restore_logger_state(
            pipeline_logger,
            handlers=pipeline_handlers,
            level=pipeline_level,
            propagate=pipeline_propagate,
        )


class GatewayWsgiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._discovery_runtime_patch = mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_RUNTIME": "stub",
                "HER_DISCOVERY_CREATE_SESSION_MODE": "agent",
            },
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
        status, payload, headers = run_wsgi_json(gateway, env)
        self.headers = headers
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

    def test_health_emits_access_log(self) -> None:
        env = _wsgi_env("GET", "/health", extra={"HTTP_X_TRACE_ID": "trace-log-1"})
        stream = io.StringIO()

        with _configured_gateway_logging(stream=stream):
            b"".join(self.gw(env, self.start_response))

        text = stream.getvalue()
        self.assertIn('"her_kind": "gateway_access"', text)
        self.assertIn('"path": "/health"', text)
        self.assertIn('"status_code": 200', text)
        self.assertIn('"trace_id": "trace-log-1"', text)

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

    def test_removed_demo_routes_return_not_found(self) -> None:
        for path in ("/demo/discovery", "/demo/live-video-verification", "/demo/assets/mediapipe/vision_bundle.mjs"):
            with self.subTest(path=path):
                env = _wsgi_env("GET", path)
                out = b"".join(self.gw(env, self.start_response))
                self.assertIn("404", self.status)
                data = json.loads(out.decode("utf-8"))
                self.assertEqual(data.get("error", {}).get("code"), "not_found")

    def test_auth_sms_send_and_verify(self) -> None:
        class FakeSmsProvider:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def send_code(self, phone: str, code: str) -> dict[str, str]:
                self.calls.append((phone, code))
                return {"provider": "fake"}

        provider = FakeSmsProvider()
        self.gw._auth_otp._provider = provider
        self.gw._auth_otp._chat_executor = None

        send_env = _wsgi_env(
            "POST",
            "/v1/auth/sms/send-code",
            json.dumps({"phone": "13800138000"}).encode("utf-8"),
        )
        send_status, send_payload = self._run_with_gateway(self.gw, send_env)

        self.assertIn("201", send_status)
        self.assertEqual(send_payload["delivery"]["provider"], "fake")
        self.assertEqual(send_payload["flow"]["scenario"], "new")
        self.assertEqual(send_payload["flow"]["next_path"], "/onboarding")
        self.assertTrue(str(send_payload["challenge_id"]).startswith("otp-"))
        self.assertEqual(len(provider.calls), 1)

        verify_env = _wsgi_env(
            "POST",
            "/v1/auth/sms/verify-code",
            json.dumps({"phone": "13800138000", "code": provider.calls[0][1]}).encode("utf-8"),
        )
        verify_status, verify_payload = self._run_with_gateway(self.gw, verify_env)

        self.assertIn("200", verify_status)
        self.assertTrue(verify_payload["verified"])
        self.assertTrue(verify_payload["user"]["is_new_user"])
        self.assertTrue(str(verify_payload["user"]["user_id"]).startswith("usr-mem-"))
        self.assertTrue(str(verify_payload["session"]["access_token"]).startswith("atk_mem_"))
        self.assertEqual(verify_payload["flow"]["next_path"], "/onboarding")

    def test_aliyun_sms_provider_request_shape(self) -> None:
        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

            def read(self) -> bytes:
                return json.dumps({"Code": "OK", "RequestId": "req-1", "BizId": "biz-1"}).encode("utf-8")

        with mock.patch.dict(
            os.environ,
            {
                "HER_SMS_ALIYUN_ACCESS_KEY_ID": "ak-test",
                "HER_SMS_ALIYUN_ACCESS_KEY_SECRET": "sk-test",
                "HER_SMS_ALIYUN_SIGN_NAME": "遇见",
                "HER_SMS_ALIYUN_TEMPLATE_CODE": "SMS_123456789",
            },
            clear=False,
        ):
            provider = auth_routes.AliyunSmsProvider.from_env()

        with mock.patch("gateway.auth_routes.urllib_request.urlopen", return_value=FakeResponse()) as urlopen:
            result = provider.send_code("13800138000", "123456")

        self.assertEqual(result["provider"], "aliyun")
        self.assertEqual(result["request_id"], "req-1")
        request = urlopen.call_args.args[0]
        self.assertIn("Action=SendSms", request.full_url)
        self.assertIn("PhoneNumbers=13800138000", request.full_url)
        self.assertIn("TemplateCode=SMS_123456789", request.full_url)
        self.assertIn("TemplateParam=%7B%22code%22%3A%22123456%22%7D", request.full_url)
        self.assertIn("Signature=", request.full_url)

    def test_auth_wechat_login_and_bind_phone(self) -> None:
        self.gw._wechat_login_provider = auth_routes.StubWechatLoginProvider(
            {
                "wx-code-1": {
                    "openid": "wx-openid-1",
                    "unionid": "wx-union-1",
                    "nickname": "测试微信用户",
                    "avatar_url": "https://example.com/avatar.jpg",
                }
            }
        )

        def fake_with_chat(fn, *args, **kwargs):
            if fn is auth_routes.login_with_wechat_profile:
                return {
                    "user": {
                        "user_id": "usr-wechat-1",
                        "is_new_user": True,
                        "account_status": "active",
                        "onboarding_status": "not_started",
                        "phone_bound": False,
                    },
                    "session": {
                        "session_id": "sess-wechat-1",
                        "access_token": "atk-wechat-1",
                        "refresh_token": "rtk-wechat-1",
                        "token_type": "Bearer",
                        "expires_in_seconds": 7200,
                        "refresh_expires_in_seconds": 2592000,
                    },
                    "flow": {"scenario": "new", "next_path": "/bind-phone"},
                    "wechat_profile": {
                        "openid": kwargs["openid"],
                        "unionid": kwargs["unionid"],
                        "nickname": kwargs["nickname"],
                        "avatar_url": kwargs["avatar_url"],
                    },
                }
            if fn is auth_routes.bind_phone_with_sms:
                self.assertEqual(kwargs["user_id"], "usr-wechat-1")
                self.assertEqual(kwargs["phone"], "13800138000")
                self.assertEqual(kwargs["code"], "123456")
                return {
                    "ok": True,
                    "user": {
                        "user_id": "usr-wechat-1",
                        "phone": "13800138000",
                        "phone_bound": True,
                        "account_status": "active",
                        "onboarding_status": "not_started",
                    },
                }
            raise AssertionError(getattr(fn, "__name__", str(fn)))

        self.gw._with_chat = fake_with_chat  # type: ignore[method-assign]

        login_env = _wsgi_env(
            "POST",
            "/v1/auth/wechat/login",
            json.dumps({"code": "wx-code-1", "device_id": "ios-1", "client_type": "ios"}).encode("utf-8"),
        )
        login_status, login_payload = self._run_with_gateway(self.gw, login_env)

        self.assertIn("200", login_status)
        self.assertEqual(login_payload["user"]["user_id"], "usr-wechat-1")
        self.assertFalse(login_payload["user"]["phone_bound"])
        self.assertEqual(login_payload["flow"]["next_path"], "/bind-phone")
        self.assertEqual(login_payload["wechat_profile"]["openid"], "wx-openid-1")

        actor = ActorPrincipal(
            actor_id="usr-wechat-1",
            roles=frozenset({"end_user"}),
            token_id="sess-wechat-1",
            auth_source="auth_session",
        )
        self.gw._identity_resolver = mock.Mock(resolve=lambda _environ: actor)

        bind_env = _wsgi_env(
            "POST",
            "/v1/auth/wechat/bind-phone",
            json.dumps(
                {
                    "phone": "13800138000",
                    "code": "123456",
                    "challenge_id": "otp-bind-1",
                    "device_id": "ios-1",
                }
            ).encode("utf-8"),
            extra=_auth_headers("atk-wechat-1"),
        )
        bind_status, bind_payload = self._run_with_gateway(self.gw, bind_env)

        self.assertIn("200", bind_status)
        self.assertTrue(bind_payload["ok"])
        self.assertTrue(bind_payload["user"]["phone_bound"])
        self.assertEqual(bind_payload["user"]["phone"], "13800138000")

    def test_auth_one_tap_create_and_verify(self) -> None:
        self.gw._one_tap_login_provider = auth_routes.StubOneTapLoginProvider(
            phone="13800138000",
            operator_token="carrier-token-1",
        )

        def fake_with_chat(fn, *args, **kwargs):
            if fn is auth_routes.create_one_tap_attempt:
                return {
                    "attempt_id": "otl-1",
                    "provider": kwargs["provider"],
                    "masked_phone": kwargs["masked_phone"],
                    "expires_in_seconds": 600,
                    "provider_payload": kwargs["provider_payload"],
                }
            if fn is auth_routes._load_one_tap_attempt_context:
                self.assertEqual(args[0], "otl-1")
                return {
                    "attempt_id": "otl-1",
                    "provider": "stub_carrier",
                    "masked_phone": "138****8000",
                    "provider_payload_json": {"mode": "stub"},
                    "client_type": "ios",
                    "device_id": "ios-1",
                }
            if fn is auth_routes.verify_one_tap_login:
                self.assertEqual(kwargs["attempt_id"], "otl-1")
                self.assertEqual(kwargs["phone"], "13800138000")
                return {
                    "user": {
                        "user_id": "usr-one-tap-1",
                        "is_new_user": True,
                        "account_status": "active",
                        "onboarding_status": "not_started",
                        "phone_bound": True,
                    },
                    "session": {
                        "session_id": "sess-one-tap-1",
                        "access_token": "atk-one-tap-1",
                        "refresh_token": "rtk-one-tap-1",
                        "token_type": "Bearer",
                        "expires_in_seconds": 7200,
                        "refresh_expires_in_seconds": 2592000,
                    },
                    "flow": {"scenario": "new", "next_path": "/onboarding"},
                }
            raise AssertionError(getattr(fn, "__name__", str(fn)))

        self.gw._with_chat = fake_with_chat  # type: ignore[method-assign]

        create_env = _wsgi_env(
            "POST",
            "/v1/auth/one-tap/create",
            json.dumps({"device_id": "ios-1", "client_type": "ios"}).encode("utf-8"),
        )
        create_status, create_payload = self._run_with_gateway(self.gw, create_env)

        self.assertIn("201", create_status)
        self.assertEqual(create_payload["attempt_id"], "otl-1")
        self.assertEqual(create_payload["provider"], "stub_carrier")
        self.assertEqual(create_payload["masked_phone"], "138****8000")

        verify_env = _wsgi_env(
            "POST",
            "/v1/auth/one-tap/verify",
            json.dumps(
                {
                    "attempt_id": "otl-1",
                    "operator_token": "carrier-token-1",
                    "device_id": "ios-1",
                    "client_type": "ios",
                }
            ).encode("utf-8"),
        )
        verify_status, verify_payload = self._run_with_gateway(self.gw, verify_env)

        self.assertIn("200", verify_status)
        self.assertEqual(verify_payload["user"]["user_id"], "usr-one-tap-1")
        self.assertTrue(verify_payload["user"]["phone_bound"])
        self.assertEqual(verify_payload["flow"]["next_path"], "/onboarding")

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

    def test_discovery_profile_update_confirm_and_reject(self) -> None:
        create_env = _wsgi_env(
            "POST",
            "/v1/discovery/sessions",
            json.dumps({"requester_id": 70001, "profile_id": 10001}).encode("utf-8"),
        )
        created = json.loads(b"".join(self.gw(create_env, self.start_response)).decode("utf-8"))
        session_id = created["session"]["session_id"]
        request_id = "pur-test-confirm"

        with mock.patch.object(
            self.gw._discovery,
            "confirm_profile_update",
            return_value={"ok": True, "request_id": request_id, "status": "confirmed"},
        ) as confirm_mock:
            confirm_env = _wsgi_env(
                "POST",
                f"/v1/discovery/sessions/{session_id}/profile-updates/{request_id}/confirm",
            )
            confirm_out = b"".join(self.gw(confirm_env, self.start_response))

        self.assertIn("200", self.status)
        confirm_data = json.loads(confirm_out.decode("utf-8"))
        self.assertTrue(confirm_data["ok"])
        confirm_mock.assert_called_once_with(session_id, request_id)

        with mock.patch.object(
            self.gw._discovery,
            "reject_profile_update",
            return_value={"ok": True, "request_id": request_id, "status": "rejected"},
        ) as reject_mock:
            reject_env = _wsgi_env(
                "POST",
                f"/v1/discovery/sessions/{session_id}/profile-updates/{request_id}/reject",
            )
            reject_out = b"".join(self.gw(reject_env, self.start_response))

        self.assertIn("200", self.status)
        reject_data = json.loads(reject_out.decode("utf-8"))
        self.assertEqual(reject_data["status"], "rejected")
        reject_mock.assert_called_once_with(session_id, request_id)

    def test_discovery_get_session_and_candidate_bff_detail(self) -> None:
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

        detail_view = {
            "hero": {"name": "林知夏", "age": 29, "city": "无锡", "headline": "中学老师 · 硕士"},
            "photo_gallery": [{"image_url": "https://static.example.com/p/10001/1.jpg"}],
        }

        with mock.patch.dict(
            os.environ,
            {"HER_PROFILE_SOURCE_DSN": "mysql://demo?table=profiles", "HER_DISCOVERY_PROFILE_SOURCE": "mysql://demo"},
            clear=False,
        ), mock.patch(
            "gateway.bff.candidate_detail.get_profile",
            return_value={"id": 10001, "name": "林知夏", "verified_level": "basic"},
        ), mock.patch(
            "gateway.bff.candidate_detail.build_trust_summary",
            return_value=mock.MagicMock(to_dict=lambda: {"headline": "已实名认证"}),
        ), mock.patch.object(
            self.gw._discovery,
            "get_profile_detail",
            return_value={"profile_id": 10001, "detail_view": detail_view},
        ):
            detail_env = _wsgi_env(
                "GET",
                "/v1/candidates/10001",
                query=f"session_id={session_id}",
            )
            detail_out = b"".join(self.gw(detail_env, self.start_response))

        self.assertIn("200", self.status)
        detail_data = json.loads(detail_out.decode("utf-8"))
        self.assertEqual(detail_data["profile_id"], 10001)
        self.assertEqual(detail_data["detail_source"], "discovery")
        self.assertEqual(detail_data["detail_view"]["hero"]["name"], "林知夏")
        self.assertEqual(detail_data["detail_view"]["photo_gallery"][0]["image_url"], "https://static.example.com/p/10001/1.jpg")

    def test_discovery_express_interest(self) -> None:
        session_id = "discovery-session-abc"
        candidate_id = 7152

        with mock.patch.object(
            self.gw._discovery,
            "get_session_owner_id",
            return_value=10001,
        ), mock.patch.object(
            self.gw._discovery,
            "express_interest",
            return_value={
                "ok": True,
                "session_id": session_id,
                "candidate_id": candidate_id,
                "subscription_id": "sub-123",
            },
        ) as express_mock:
            env = _wsgi_env(
                "POST",
                f"/v1/discovery/sessions/{session_id}/candidates/{candidate_id}/express-interest",
                json.dumps({}).encode("utf-8"),
            )
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("200", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["subscription_id"], "sub-123")
        express_mock.assert_called_once()

    def test_internal_error_emits_error_log(self) -> None:
        env = _wsgi_env("GET", "/v1/failure")
        stream = io.StringIO()

        with mock.patch.object(self.gw, "dispatch_rest", side_effect=RuntimeError("boom")), _configured_gateway_logging(
            stream=stream
        ):
            out = b"".join(self.gw(env, self.start_response))

        self.assertIn("500", self.status)
        data = json.loads(out.decode("utf-8"))
        self.assertEqual(data["error"]["code"], "internal_error")
        text = stream.getvalue()
        self.assertIn('"her_kind": "gateway_error"', text)
        self.assertIn('"error_type": "RuntimeError"', text)
        self.assertIn("Unhandled gateway error for GET /v1/failure", text)

    def test_access_log_can_write_to_file(self) -> None:
        env = _wsgi_env("GET", "/health")
        stream = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(pathlib.Path(tmpdir) / "partner-http-gateway.log")
            with _configured_gateway_logging(stream=stream, log_file=log_file):
                b"".join(self.gw(env, self.start_response))

            text = pathlib.Path(log_file).read_text(encoding="utf-8")

        self.assertIn('"her_kind": "gateway_access"', text)
        self.assertIn('"path": "/health"', text)


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

    def test_ops_workbench_summary_allows_ops_actor(self) -> None:
        tokens = json.dumps({"token-ops": {"actor_id": "ops-1", "roles": ["ops_operator", "service_worker"]}})
        with mock.patch.dict(os.environ, {"PARTNER_GATEWAY_STATIC_TOKENS_JSON": tokens}, clear=False):
            gw = PartnerGateway(
                recommendation_dsn="mysql://noop",
                matchmaking_dsn="mysql://noop",
                chat_dsn="mysql://noop",
                db_pool_max=0,
            )
            with (
                mock.patch.object(gw, "_build_async_job_dashboard", return_value={"totals": {"total": 1}}),
                mock.patch.object(gw, "_with_ledger", return_value=[]),
            ):
                env = _wsgi_env(
                    "GET",
                    "/v1/ops/workbench/summary",
                    query="limit=3",
                    extra=_auth_headers("token-ops"),
                )
                status, payload = self._run_with_gateway(gw, env)

        self.assertIn("200", status)
        self.assertEqual(payload["dashboard"]["totals"]["total"], 1)
        self.assertEqual(payload["principal"]["user_id"], "ops-1")
        self.assertIn("ops_operator", payload["principal"]["roles"])

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
        with mock.patch("gateway.bff.search_profiles.partner_search_profiles", return_value=fake_response) as mocked_search:
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
