from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPO_ROOT = DISCOVERY_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (  # noqa: E402
    DiscoveryActionSuggestion,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)
from match_domain.photo_intent_agent import build_visual_search_plan  # noqa: E402
from discovery_system.service import DiscoveryInvalidTurnInputError, DiscoveryService  # noqa: E402
from discovery_system.storage import InMemoryDiscoveryStorage  # noqa: E402


class _FakeRuntime:
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
        _ = user_message, action_context
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message="收到，我继续帮你找。",
                suggested_actions=[],
            ),
        )


class DiscoveryMultimodalTurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_profile_source = os.environ.get("HER_DISCOVERY_PROFILE_SOURCE")
        self._old_create_session_mode = os.environ.get("HER_DISCOVERY_CREATE_SESSION_MODE")
        os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = "mysql://example/her#profiles"
        os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = "agent"
        self.service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_FakeRuntime(),
        )
        self.service._check_and_push_proxy_intro_cases = mock.MagicMock()
        self.service._trigger_previous_session_processing = mock.MagicMock()

    def tearDown(self) -> None:
        if self._old_profile_source is None:
            os.environ.pop("HER_DISCOVERY_PROFILE_SOURCE", None)
        else:
            os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = self._old_profile_source
        if self._old_create_session_mode is None:
            os.environ.pop("HER_DISCOVERY_CREATE_SESSION_MODE", None)
        else:
            os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = self._old_create_session_mode

    def test_process_multimodal_turn_with_image_attachment_appends_result_group(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "hybrid_photo_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理", "education": "本科"}],
            ),
        ):
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "帮我找像这张的",
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={
                    "intent_hint": {"mode": "auto"},
                    "top_k": 12,
                },
            )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-3]["item_type"], "user_message")
        self.assertEqual(timeline[-3]["metadata"]["media_type"], "image")
        self.assertEqual(timeline[-2]["item_type"], "assistant_message")
        self.assertEqual(timeline[-1]["item_type"], "result_group")
        card = timeline[-1]["cards"][0]
        self.assertEqual(card["title"], "林夏 27")
        self.assertEqual(card["subtitle"], "上海 · 产品经理 · 本科")
        self.assertEqual(card["age"], 27)
        self.assertEqual(card["city"], "上海")
        self.assertEqual(card["occupation"], "产品经理")
        self.assertEqual(card["education"], "本科")
        self.assertIn("match_highlights", card)
        self.assertTrue(result["visual_context"]["has_reference_image"])
        self.assertEqual(result["visual_context"]["active_visual_intent"]["mode"], "hybrid")

        stored = self.service.storage.get_session(session_id)
        visual_context = dict(stored.state.get("visual_context") or {})
        self.assertEqual(visual_context["active_reference_image"]["source"], "data:image/jpeg;base64,abc")
        self.assertEqual(visual_context["last_result_profile_ids"], [20001])

    def test_process_multimodal_turn_with_image_only_uses_default_visual_query(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "hybrid_photo_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海"}],
            ),
        ):
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={"entryPoint": "discover_photo_composer"},
            )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-3]["item_type"], "user_message")
        self.assertEqual(timeline[-3]["body"], "帮我看看这张图适合找什么人")
        self.assertEqual(timeline[-2]["item_type"], "assistant_message")
        self.assertEqual(timeline[-1]["item_type"], "result_group")

    def test_build_visual_search_plan_treats_inline_image_reference_as_face_search(self):
        plan = build_visual_search_plan(
            text="找长得像图中的女生",
            image_source="data:image/jpeg;base64,abc",
        )

        resolved = dict(plan["resolved_visual_plan"] or {})
        self.assertEqual(resolved["preference_kind"], "face")
        self.assertEqual(resolved["query_text"], "找长得像图中的女生")
        self.assertIsNone(resolved["celebrity_name"])
        self.assertIn("face_marker_detected", resolved["routing_reasons"])

    def test_process_multimodal_turn_with_inline_image_reference_uses_face_wording(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "face_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理", "education": "本科"}],
            ),
        ):
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "找长得像图中的女生",
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={"top_k": 12},
            )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-2]["item_type"], "assistant_message")
        self.assertIn("按脸更接近这张图", timeline[-2]["body"])
        self.assertNotIn("图中的女生", timeline[-2]["body"])
        self.assertEqual(timeline[-1]["item_type"], "result_group")
        self.assertEqual(timeline[-1]["title"], "像这张脸")
        self.assertEqual(result["visual_context"]["active_visual_intent"]["mode"], "face")

    def test_session_payload_hydrates_legacy_result_group_cards(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]
        session = self.service.storage.get_session(session_id)
        session.view = {
            "timeline": [
                {
                    "item_type": "result_group",
                    "item_id": "result-group-legacy",
                    "title": "像这张脸",
                    "cards": [
                        {
                            "card_id": "candidate-20001",
                            "profile_id": 20001,
                            "title": "林夏",
                            "subtitle": "上海",
                        }
                    ],
                }
            ]
        }
        self.service.storage.save_session(session)

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{
                    "id": 20001,
                    "name": "林夏",
                    "age": 27,
                    "city": "上海",
                    "job": "产品经理",
                    "education": "复旦大学",
                    "avatar_url": "https://cdn.her.local/20001.jpg",
                    "verified_level": "video_verified",
                }],
            ),
        ):
            payload = self.service.get_session_view(session_id)

        cards = payload["view"]["timeline"][-1]["cards"]
        self.assertEqual(cards[0]["title"], "林夏 27")
        self.assertEqual(cards[0]["subtitle"], "上海 · 产品经理 · 复旦大学")
        self.assertEqual(cards[0]["age"], 27)
        self.assertEqual(cards[0]["city"], "上海")
        self.assertEqual(cards[0]["occupation"], "产品经理")
        self.assertEqual(cards[0]["education"], "复旦大学")
        self.assertTrue(cards[0]["verified"])
        self.assertEqual(cards[0]["cover_image_url"], "https://cdn.her.local/20001.jpg")

    def test_process_multimodal_turn_without_attachment_falls_back_to_text_turn(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        result = self.service.process_multimodal_turn(
            session_id=session_id,
            message={"text": "我想找上海的"},
            client_context={"entryPoint": "discover_composer"},
        )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-2]["item_type"], "user_message")
        self.assertEqual(timeline[-2]["body"], "我想找上海的")
        self.assertEqual(timeline[-1]["item_type"], "assistant_message")

    def test_process_multimodal_turn_reuses_previous_image_for_visual_followup(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        captured_calls: list[dict[str, object]] = []

        def _fake_photo_search(**kwargs):
            captured_calls.append(kwargs)
            return {
                "saved": True,
                "search_type": "hybrid_photo_similarity",
                "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
            }

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                side_effect=_fake_photo_search,
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理"}],
            ),
        ):
            self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "帮我找像这张的",
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={"intent_hint": {"mode": "face"}},
            )
            followup = self.service.process_multimodal_turn(
                session_id=session_id,
                message={"text": "按刚才那张继续找，换成上海，温柔一点"},
                client_context={"entryPoint": "discover_composer"},
            )

        self.assertEqual(len(captured_calls), 2)
        self.assertEqual(captured_calls[1]["image_source"], "data:image/jpeg;base64,abc")
        self.assertEqual(captured_calls[1]["intent"].mode, "face")
        self.assertEqual(captured_calls[1]["intent"].hard_filters.get("cities"), ["上海"])

        timeline = followup["view"]["timeline"]
        self.assertEqual(timeline[-3]["item_type"], "user_message")
        self.assertEqual(timeline[-3]["metadata"]["media_url"], "data:image/jpeg;base64,abc")
        self.assertEqual(followup["visual_context"]["active_constraints"]["hard_filters"]["cities"], ["上海"])
        self.assertIn("温柔", followup["visual_context"]["active_constraints"]["style_keywords"])

    def test_process_multimodal_turn_asks_clarifying_question_when_visual_request_has_no_reference(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        result = self.service.process_multimodal_turn(
            session_id=session_id,
            message={"text": "还是这种感觉"},
            client_context={"entryPoint": "discover_composer"},
        )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-2]["item_type"], "user_message")
        self.assertEqual(timeline[-2]["body"], "还是这种感觉")
        self.assertEqual(timeline[-1]["item_type"], "assistant_message")
        self.assertIn("参考图再发一次", timeline[-1]["body"])

    def test_process_multimodal_turn_returns_empty_result_groupless_response_when_search_empty(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "hybrid_photo_similarity",
                    "results": [],
                },
            ),
        ):
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "帮我找像这张的",
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={"intent_hint": {"mode": "auto"}},
            )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-2]["item_type"], "user_message")
        self.assertEqual(timeline[-1]["item_type"], "assistant_message")
        self.assertNotEqual(timeline[-1].get("item_type"), "result_group")
        self.assertEqual(result["visual_context"]["last_result_profile_ids"], [])

    def test_process_multimodal_turn_rejects_broken_image_attachment(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with self.assertRaises(DiscoveryInvalidTurnInputError):
            self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "attachments": [
                        {"type": "image", "source": ""},
                    ],
                },
                client_context={"entryPoint": "discover_photo_composer"},
            )

    def test_process_multimodal_turn_emits_shadow_compare_when_enabled(self):
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch.dict(os.environ, {"HER_DISCOVERY_VISUAL_SHADOW_COMPARE": "1"}, clear=False),
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "face_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "discovery_system.service.execute_photo_preference_search",
                return_value={
                    "saved": True,
                    "search_type": "hybrid_photo_similarity",
                    "results": [{"profile_id": 20002, "final_score": 1.12, "appearance_summary": "成熟温柔"}],
                },
            ) as shadow_search,
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海"}],
            ),
            mock.patch("discovery_system.service.emit_photo_search_event") as emit_event,
        ):
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "按脸找像这张的",
                    "attachments": [
                        {"type": "image", "source": "data:image/jpeg;base64,abc", "mime_type": "image/jpeg"},
                    ],
                },
                client_context={"top_k": 12},
            )

        self.assertTrue(shadow_search.called)
        shadow_calls = [call.kwargs for call in emit_event.call_args_list if call.kwargs.get("stage") == "shadow_compare"]
        self.assertEqual(len(shadow_calls), 1)
        self.assertTrue(shadow_calls[0]["shadow_diff_detected"])
        self.assertIsNotNone(self.service.storage.get_latest_turn_id(session_id))
        self.assertEqual(result["visual_memory"]["active_preference"]["legacy_mode"], "face")

    def test_process_multimodal_turn_with_celebrity_name_without_attachments(self):
        """验证明星搜索场景（通过 celebrity_name 触发）不需要附件也能正常工作"""
        created = self.service.create_session(
            requester_id=10001,
            profile_id=10001,
        )
        session_id = created["session"]["session_id"]

        with (
            mock.patch(
                "discovery_system.service.resolve_profile_source",
                return_value=("mysql://example/her", "profiles"),
            ),
            mock.patch(
                "discovery_system.service.retrieve_visual_candidates",
                return_value={
                    "saved": True,
                    "search_type": "face_similarity",
                    "results": [{"profile_id": 20001, "final_score": 1.38, "appearance_summary": "清爽耐看"}],
                },
            ),
            mock.patch(
                "discovery_system.service.list_profiles",
                return_value=[{"id": 20001, "name": "林夏", "age": 27, "city": "上海", "job": "产品经理"}],
            ),
        ):
            # 关键：attachments 为空列表，通过 celebrity_name 触发明星搜索
            result = self.service.process_multimodal_turn(
                session_id=session_id,
                message={
                    "text": "找像田曦薇的",
                    "attachments": [],  # 空附件列表
                },
                client_context={
                    "intent_hint": {
                        "mode": "celebrity",
                        "celebrity_name": "田曦薇",
                    },
                    "top_k": 12,
                },
            )

        # 验证没有 IndexError，成功返回结果
        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-3]["item_type"], "user_message")
        self.assertEqual(timeline[-2]["item_type"], "assistant_message")
        self.assertEqual(timeline[-1]["item_type"], "result_group")
        # 验证 mime_type 正确处理（应该是 None 或空字符串）
        user_msg = timeline[-3]
        if user_msg.get("metadata") and user_msg["metadata"].get("media_metadata"):
            mime_type = user_msg["metadata"]["media_metadata"].get("mime_type")
            self.assertTrue(mime_type is None or mime_type == "")


if __name__ == "__main__":
    unittest.main()
