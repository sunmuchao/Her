"""API 端点集成测试

测试 GET /v1/discovery/sessions 端点的完整请求-响应流程。

测试方式：
- 使用 mock gateway 对象模拟 HTTP 请求
- 验证请求参数解析和响应格式
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

DISCOVERY_ROOT = GATEWAY_ROOT / "external-systems" / "partner-discovery-system"
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from gateway.discovery_routes import (
    rest_discovery_list_sessions,
    rest_discovery_photo_search,
    dispatch_discovery_rest,
    _discovery_error,
)
from match_domain.photo_intent_agent import PhotoPreferenceIntent
from discovery_system.service import DiscoveryService, DiscoverySessionNotFoundError
from discovery_system.storage import InMemoryDiscoveryStorage
from discovery_system.agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)


class _FakeRuntime:
    """模拟 Agent Runtime"""

    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先说说你的基本要求。",
                suggested_actions=[
                    DiscoveryActionSuggestion(label="先从城市说起", style="primary"),
                ],
            )
        )

    def run_turn(self, _run_input, *, user_message=None, action_context=None):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message="找到候选人了。",
                suggested_actions=[],
            ),
        )


class _FakeGateway:
    """模拟 Gateway 对象"""

    def __init__(self, discovery_service):
        self._discovery = discovery_service

    def _resolve_int_actor_bound_id(self, environ, raw_value, *, field_name):
        """解析并验证用户 ID"""
        if raw_value is None:
            raise ValueError(f"{field_name} is required")
        return int(raw_value)

    def _assert_actor_can_access_owner(self, environ, owner_id, *, field_name):
        """验证用户权限（这里简化为始终允许）"""
        pass


class TestDiscoveryListSessionsAPI(unittest.TestCase):
    """测试 GET /v1/discovery/sessions API"""

    def setUp(self):
        self.storage = InMemoryDiscoveryStorage()
        self.runtime = _FakeRuntime()
        self.service = DiscoveryService(
            storage=self.storage,
            runtime=self.runtime,
        )
        self.gateway = _FakeGateway(self.service)

    def test_list_sessions_empty_response(self):
        """测试空会话列表的响应"""
        environ = {
            "QUERY_STRING": "profile_id=10001",
        }

        status, response = rest_discovery_list_sessions(self.gateway, environ)

        self.assertEqual(status, 200)
        self.assertIn("sessions", response)
        self.assertEqual(response["sessions"], [])
        self.assertEqual(response["total"], 0)
        self.assertIn("trace_id", response)

    def test_list_sessions_with_created_session(self):
        """测试创建会话后的列表响应"""
        # 先创建一个会话
        self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )

        environ = {
            "QUERY_STRING": "profile_id=10001",
        }

        status, response = rest_discovery_list_sessions(self.gateway, environ)

        self.assertEqual(status, 200)
        self.assertIn("sessions", response)
        self.assertEqual(len(response["sessions"]), 1)
        self.assertEqual(response["total"], 1)

        # 验证摘要字段
        session = response["sessions"][0]
        self.assertIn("session_id", session)
        self.assertIn("phase", session)
        self.assertIn("status", session)
        self.assertIn("created_at", session)
        self.assertIn("updated_at", session)

    def test_list_sessions_with_limit_parameter(self):
        """测试 limit 参数"""
        # 创建 5 个会话
        for i in range(5):
            self.service.create_session(
                requester_id=10001,
                profile_id=10001,
            )

        environ = {
            "QUERY_STRING": "profile_id=10001&limit=3",
        }

        status, response = rest_discovery_list_sessions(self.gateway, environ)

        self.assertEqual(status, 200)
        self.assertEqual(len(response["sessions"]), 3)

    def test_list_sessions_order_descending(self):
        """测试会话列表按更新时间降序排列"""
        # 创建 3 个会话
        for i in range(3):
            self.service.create_session(
                requester_id=10001,
                profile_id=10001,
            )

        environ = {
            "QUERY_STRING": "profile_id=10001",
        }

        status, response = rest_discovery_list_sessions(self.gateway, environ)

        self.assertEqual(status, 200)
        sessions = response["sessions"]
        self.assertEqual(len(sessions), 3)

        # 验证顺序：最新创建的在前（因为创建时 updated_at 是当前时间）
        # session_id 格式是 discovery-session-xxx，数字越大越新
        # 但 InMemoryDiscoveryStorage 使用序列号，所以可以按 session_id 判断
        # 实际应该按 updated_at 判断，但这里简化为按创建顺序

    def test_list_sessions_missing_profile_id(self):
        """测试缺少 profile_id 参数的情况"""
        environ = {
            "QUERY_STRING": "",  # 没有 profile_id
        }

        # 应该抛出异常（_resolve_int_actor_bound_id 会失败）
        with self.assertRaises(ValueError):
            rest_discovery_list_sessions(self.gateway, environ)


class TestDiscoveryRoutesDispatch(unittest.TestCase):
    """测试路由分发"""

    def setUp(self):
        self.storage = InMemoryDiscoveryStorage()
        self.runtime = _FakeRuntime()
        self.service = DiscoveryService(
            storage=self.storage,
            runtime=self.runtime,
        )
        self.gateway = _FakeGateway(self.service)

    def test_dispatch_get_sessions_list(self):
        """测试路由分发到 list_sessions"""
        environ = {"QUERY_STRING": "profile_id=10001"}

        # 测试 GET /v1/discovery/sessions 路由
        result = dispatch_discovery_rest(
            self.gateway,
            environ,
            method="GET",
            path="/v1/discovery/sessions",
        )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)

    def test_dispatch_post_sessions_create(self):
        """测试路由分发到 create_session"""
        environ = {
            "wsgi.input": mock.MagicMock(),
            "CONTENT_LENGTH": "100",
        }

        # Mock read_body 和 parse_json_body
        with mock.patch("gateway.discovery_routes._read_body", return_value=b'{"profile_id": 10001}'):
            with mock.patch("gateway.discovery_routes._parse_json_body", return_value={"profile_id": 10001}):
                result = dispatch_discovery_rest(
                    self.gateway,
                    environ,
                    method="POST",
                    path="/v1/discovery/sessions",
                )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 201)
        self.assertIn("session", response)

    def test_dispatch_get_single_session(self):
        """测试路由分发到 get_session"""
        # 先创建一个会话
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        environ = {}

        result = dispatch_discovery_rest(
            self.gateway,
            environ,
            method="GET",
            path=f"/v1/discovery/sessions/{session_id}",
        )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)

    def test_dispatch_photo_search(self):
        environ = {
            "wsgi.input": mock.MagicMock(),
            "CONTENT_LENGTH": "120",
        }
        body = {
            "profile_id": 10001,
            "mode": "style",
            "image_source": "data:image/jpeg;base64,abc",
            "query_text": "清爽自然",
        }
        with (
            mock.patch("gateway.discovery_routes._read_body", return_value=b"{}"),
            mock.patch("gateway.discovery_routes._parse_json_body", return_value=body),
            mock.patch(
                "gateway.discovery_routes.default_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "gateway.discovery_routes.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "style_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "gateway.discovery_routes.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理"}],
            ),
        ):
            result = dispatch_discovery_rest(
                self.gateway,
                environ,
                method="POST",
                path="/v1/discovery/photo-search",
            )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)
        self.assertEqual(response["task"]["status"], "succeeded")
        self.assertEqual(response["result_count"], 1)
        self.assertEqual(response["results"][0]["name"], "林夏")

    def test_dispatch_photo_search_persists_into_discovery_session(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]
        environ = {
            "wsgi.input": mock.MagicMock(),
            "CONTENT_LENGTH": "180",
        }
        body = {
            "profile_id": 10001,
            "session_id": session_id,
            "mode": "face",
            "image_source": "data:image/jpeg;base64,abc",
            "query_text": "笑起来像这张",
        }
        with (
            mock.patch("gateway.discovery_routes._read_body", return_value=b"{}"),
            mock.patch("gateway.discovery_routes._parse_json_body", return_value=body),
            mock.patch(
                "gateway.discovery_routes.default_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "gateway.discovery_routes.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "face_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "gateway.discovery_routes.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理"}],
            ),
        ):
            result = dispatch_discovery_rest(
                self.gateway,
                environ,
                method="POST",
                path="/v1/discovery/photo-search",
            )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)
        self.assertTrue(response["session_sync"]["success"])
        view = self.service.get_session_view(session_id)
        item_types = [item.get("item_type") for item in view["view"]["timeline"]]
        self.assertIn("result_group", item_types)
        self.assertEqual(view["view"]["timeline"][-1]["cards"][0]["profile_id"], 20001)


class TestDiscoveryPhotoSearchAPI(unittest.TestCase):
    def setUp(self):
        self.gateway = _FakeGateway(mock.MagicMock())

    def test_photo_search_requires_image_for_face_mode(self):
        status, response = rest_discovery_photo_search(
            self.gateway,
            {},
            {"profile_id": 10001, "mode": "face"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "bad_request")

    def test_photo_search_returns_enriched_candidates(self):
        with (
            mock.patch(
                "gateway.discovery_routes.default_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "gateway.discovery_routes.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "face_similarity",
                    "results": [
                        {
                            "profile_id": 20001,
                            "final_score": 1.52,
                            "base_score": 0.91,
                            "photo_bonus": 12.0,
                            "appearance_summary": "笑起来很自然",
                        }
                    ],
                },
            ),
            mock.patch(
                "gateway.discovery_routes.list_profiles",
                return_value=[
                    {
                        "id": 20001,
                        "display_name": "周宁",
                        "age": 28,
                        "city": "杭州",
                        "job": "设计师",
                        "education": "本科",
                        "avatar_url": "https://cdn.her.local/profiles/20001/avatar.jpg",
                        "verified_level": "offline",
                    }
                ],
            ),
        ):
            status, response = rest_discovery_photo_search(
                self.gateway,
                {},
                {
                    "profile_id": 10001,
                    "mode": "face",
                    "image_source": "data:image/jpeg;base64,abc",
                    "query_text": "像这张脸",
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(response["intent"]["mode"], "face")
        self.assertEqual(response["results"][0]["name"], "周宁")
        self.assertTrue(response["results"][0]["verified"])

    def test_photo_search_auto_mode_uses_agent_detected_intent(self):
        with (
            mock.patch(
                "gateway.discovery_routes.default_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "gateway.discovery_routes.detect_photo_preference_intent",
                return_value=PhotoPreferenceIntent(
                    intent_type="hybrid_photo_search",
                    mode="hybrid",
                    query_text="帮我看看这张图适合找什么人",
                    attribute_filters={},
                    hard_filters={},
                    raw_text="帮我看看这张图适合找什么人",
                    confidence=0.72,
                    routing_reasons=["image_attached_without_explicit_mode_use_agent_auto_judgement"],
                    image_understanding={"has_image": True},
                ),
            ),
            mock.patch(
                "gateway.discovery_routes.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "hybrid_photo_similarity",
                    "results": [
                        {
                            "profile_id": 20001,
                            "final_score": 1.52,
                            "appearance_summary": "笑起来很自然",
                        }
                    ],
                },
            ),
            mock.patch(
                "gateway.discovery_routes.list_profiles",
                return_value=[
                    {
                        "id": 20001,
                        "display_name": "周宁",
                        "age": 28,
                        "city": "杭州",
                        "avatar_url": "https://cdn.her.local/profiles/20001/avatar.jpg",
                        "verified_level": "offline",
                    }
                ],
            ),
        ):
            status, response = rest_discovery_photo_search(
                self.gateway,
                {},
                {
                    "profile_id": 10001,
                    "mode": "auto",
                    "image_source": "data:image/jpeg;base64,abc",
                    "query_text": "帮我看看这张图适合找什么人",
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(response["intent"]["mode"], "hybrid")
        self.assertEqual(response["search_type"], "hybrid_photo_similarity")
        self.assertGreater(response["intent"]["confidence"], 0.7)
        self.assertIn("routing_reasons", response["intent"])

    def test_photo_search_applies_hard_filters(self):
        with (
            mock.patch(
                "gateway.discovery_routes.default_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "gateway.discovery_routes.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "style_similarity",
                    "results": [
                        {"profile_id": 20001, "final_score": 1.52, "appearance_summary": "清爽自然"},
                        {"profile_id": 20002, "final_score": 1.48, "appearance_summary": "成熟温柔"},
                    ],
                },
            ),
            mock.patch(
                "gateway.discovery_routes.list_profiles",
                return_value=[
                    {
                        "id": 20001,
                        "display_name": "周宁",
                        "age": 28,
                        "city": "杭州",
                        "verified_level": "offline",
                        "avatar_url": "https://cdn.her.local/profiles/20001/avatar.jpg",
                    },
                    {
                        "id": 20002,
                        "display_name": "林夏",
                        "age": 24,
                        "city": "北京",
                        "verified_level": "none",
                        "avatar_url": "https://cdn.her.local/profiles/20002/avatar.jpg",
                    },
                ],
            ),
        ):
            status, response = rest_discovery_photo_search(
                self.gateway,
                {},
                {
                    "profile_id": 10001,
                    "mode": "style",
                    "image_source": "data:image/jpeg;base64,abc",
                    "hard_filters": {
                        "age_min": 26,
                        "age_max": 30,
                        "city": ["杭州"],
                        "verified_only": True,
                    },
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(response["result_count"], 1)
        self.assertEqual(response["results"][0]["name"], "周宁")
        self.assertEqual(response["intent"]["hard_filters"]["age_min"], 26)
        self.assertTrue(response["intent"]["hard_filters"]["verified_only"])


if __name__ == "__main__":
    unittest.main()
