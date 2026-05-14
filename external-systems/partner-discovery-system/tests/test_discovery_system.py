from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock


DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (  # noqa: E402
    DiscoveryActionSuggestion,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryRuntimeResult,
)
from discovery_system.service import DiscoveryService  # noqa: E402
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
        del user_message, action_context
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message="我先给你看一位比较贴近的。",
                criteria_labels=["无锡", "认真恋爱"],
                suggested_actions=[
                    DiscoveryActionSuggestion(label="再看更稳定一点的"),
                ],
                result_group_title="这一轮先给你看 1 位",
                selected_candidates=[
                    DiscoveryCandidateSelection(
                        profile_id=1001,
                        reason_summary="城市一致、关系目标一致、工作节奏稳定。",
                    )
                ],
            ),
            search_response={
                "has_match": True,
                "result_count": 1,
                "results": [
                    {
                        "id": 1001,
                        "name": "林知夏",
                        "score": 92,
                        "photo_preview": ["https://static.example.com/1001.jpg"],
                        "verification_items": [
                            {"key": "photo", "label": "真人照认证", "status": "verified"},
                            {"key": "education", "label": "学历已核验", "status": "verified"},
                        ],
                        "matched_on": ["城市一致", "关系目标一致", "工作稳定"],
                        "trust_summary": {"headline": "已实名认证"},
                        "profile": {
                            "age": 29,
                            "city": "无锡",
                            "job": "中学老师",
                            "education": "硕士",
                        },
                    }
                ],
            },
        )


class _NoMatchOptInRuntime:
    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先说说你的要求，我来替你筛。",
            )
        )

    def run_turn(self, run_input, *, user_message=None, action_context=None):
        if dict((action_context or {}).get("semantic_payload") or {}).get("kind") == "saved_search_opt_in":
            tool_result = run_input.create_saved_search_subscription_from_last_search()
            body = "好，我已经替你继续留意了。"
            if tool_result.get("already_exists"):
                body = "这轮条件我已经替你记下了，会继续帮你留意。"
            elif not tool_result.get("created_subscription"):
                body = "我这边先没成功记下持续留意。"
            return DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="no_result",
                    assistant_message=body,
                    criteria_labels=list(run_input.criteria_labels),
                    suggested_actions=[],
                )
            )

        del user_message
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="no_result",
                assistant_message="这一轮我还没找到特别合适的，要不要我后面继续替你留意？",
                criteria_labels=["上海", "认真恋爱"],
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label="愿意，继续帮我留意",
                        style="primary",
                        semantic_payload={"kind": "saved_search_opt_in"},
                    )
                ],
            ),
            search_response={
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
                "diagnostics": {},
                "request_meta": {
                    "source": "mysql://root@127.0.0.1:3307/her?table=profiles",
                    "criteria": {
                        "gender": "男",
                        "cities": ["上海"],
                        "relationship_goals": ["认真恋爱"],
                    },
                    "self_profile": {"self_city": "上海"},
                    "self_id": 10001,
                    "table_name": None,
                    "photos_table_name": None,
                    "limit_count": 5,
                },
            },
        )


class DiscoveryServiceTests(unittest.TestCase):
    def test_service_renders_cards_from_canonical_search_result(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_FakeRuntime(),
        )

        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        result = service.process_turn(
            session_id=session_id,
            user_message_text="我在无锡，想找认真恋爱的人。",
        )

        timeline = result["view"]["timeline"]
        self.assertEqual(timeline[-1]["item_type"], "result_group")
        cards = timeline[-1]["cards"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["profile_id"], 1001)
        self.assertEqual(cards[0]["title"], "林知夏 29")
        self.assertEqual(cards[0]["subtitle"], "无锡 · 中学老师 · 硕士")
        self.assertEqual(cards[0]["reason_summary"], "城市一致、关系目标一致、工作节奏稳定。")
        self.assertEqual(cards[0]["trust_badges"], ["真人照认证", "学历已核验"])

    def test_service_renders_profile_detail_from_canonical_payload(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_FakeRuntime(),
        )

        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]
        service.process_turn(
            session_id=session_id,
            user_message_text="我在无锡，想找认真恋爱的人。",
        )

        detail_payload = {
            "id": 1001,
            "name": "林知夏",
            "photo_preview": ["https://static.example.com/p/1001/1.jpg"],
            "verification_items": [
                {"key": "photo", "status": "verified", "summary": "已真人照片认证（4张）"},
                {"key": "education", "status": "verified", "summary": "硕士（已核验）"},
            ],
            "trust_summary": {"headline": "已实名认证"},
            "caution_items": ["工作日回复可能偏晚。"],
            "trust_actions": ["建议先确认职业、学历和收入区间是否真实"],
            "notes_summary": "平时作息规律，周末喜欢徒步和看展。",
            "profile": {
                "gender": "女",
                "age": 29,
                "city": "无锡",
                "job": "中学老师",
                "education": "硕士",
                "relationship_goal": "认真恋爱",
                "income_range": "20-30万/年",
                "marital_status": "未婚",
            },
        }

        with mock.patch.dict(os.environ, {"HER_DISCOVERY_PROFILE_SOURCE": "mysql://demo"}, clear=False), mock.patch(
            "discovery_system.service.load_profile_detail",
            return_value=detail_payload,
        ):
            detail = service.get_profile_detail(1001, session_id=session_id)

        view = detail["detail_view"]
        self.assertEqual(view["hero"]["name"], "林知夏")
        self.assertEqual(view["hero"]["headline"], "中学老师 · 硕士 · 认真恋爱")
        self.assertEqual(view["photo_gallery"][0]["image_url"], "https://static.example.com/p/1001/1.jpg")
        self.assertEqual(view["verified_sections"][0]["title"], "已核验信息")
        self.assertIn("硕士（已核验）", view["verified_sections"][0]["items"])
        self.assertEqual(view["self_reported_sections"][0]["title"], "她的自我介绍")
        self.assertIn("平时作息规律", view["self_reported_sections"][0]["items"][0])
        self.assertIn("工作日回复可能偏晚。", view["caution_sections"][0]["items"])
        self.assertIn("城市一致、关系目标一致、工作节奏稳定。", view["matchmaker_notes"][0])

    def test_service_can_create_saved_search_subscription_from_last_empty_search(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_NoMatchOptInRuntime(),
        )

        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]
        first_turn = service.process_turn(
            session_id=session_id,
            user_message_text="我在上海，想找认真恋爱的男生。",
        )
        action_id = first_turn["view"]["suggested_actions"][0]["action_id"]

        fake_conn = mock.Mock()
        captured: dict[str, object] = {}

        def _fake_handle_opt_in_decision(conn, **kwargs):
            captured["conn"] = conn
            captured["kwargs"] = kwargs
            return {
                "created_subscription": True,
                "subscription": {
                    "subscription_id": "saved-search-abc123",
                    "title": kwargs["title"],
                },
            }

        with mock.patch.object(service, "_open_recommendation_conn", return_value=fake_conn), mock.patch.object(
            service,
            "_load_recommendation_bindings",
            return_value=(None, _fake_handle_opt_in_decision, None),
        ):
            second_turn = service.process_turn(
                session_id=session_id,
                action_id=action_id,
            )

        self.assertEqual(captured["conn"], fake_conn)
        kwargs = dict(captured["kwargs"] or {})
        self.assertEqual(kwargs["requester_id"], 70001)
        self.assertTrue(kwargs["user_opted_in"])
        self.assertEqual(kwargs["search_session"]["search_request"]["criteria"]["cities"], ["上海"])
        self.assertEqual(kwargs["search_session"]["search_request"]["self_id"], 10001)
        self.assertEqual(kwargs["title"], "持续留意：上海 / 认真恋爱")
        self.assertEqual(second_turn["view"]["timeline"][-1]["body"], "好，我已经替你继续留意了。")

        stored_session = service.storage.get_session(session_id)
        assert stored_session is not None
        self.assertEqual(stored_session.state["last_created_subscription_id"], "saved-search-abc123")
        self.assertEqual(stored_session.state["last_opt_in_search_run_id"], 1)
        fake_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
