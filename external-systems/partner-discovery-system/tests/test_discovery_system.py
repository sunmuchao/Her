from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

from agents import AgentOutputSchema


DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.agent_runtime import (  # noqa: E402
    AgentsSdkDiscoveryAgentRuntime,
    DiscoveryActionSuggestion,
    DiscoveryActionSuggestionModel,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryDecisionModel,
    DiscoveryRunInput,
    DiscoveryRuntimeResult,
    _configure_agents_sdk_provider,
)
from discovery_system.agent_session_store import InMemoryDiscoveryAgentSessionStore  # noqa: E402
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


class _PersonaSyncRuntime:
    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先告诉我你的偏好。",
            )
        )

    def run_turn(self, run_input, *, user_message=None, action_context=None):
        del user_message, action_context
        run_input.sync_requester_persona_memory(
            {
                "self_city": "上海",
                "self_relationship_goal": "认真恋爱",
                "must_not_have_tags": ["抽烟"],
            }
        )
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="我先把你刚说的稳定偏好记下来了。",
                criteria_labels=["上海", "认真恋爱", "不接受抽烟"],
                suggested_actions=[
                    DiscoveryActionSuggestion(label="继续补充年龄范围"),
                ],
            )
        )


class _SearchToolRuntime:
    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先告诉我你想找什么样的人。",
            )
        )

    def run_turn(self, run_input, *, user_message=None, action_context=None):
        del user_message, action_context
        response = run_input.search_partner_candidates(
            {
                "gender": "女",
                "cities": ["无锡"],
                "relationship_goals": ["认真恋爱"],
            },
            3,
        )
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown",
                assistant_message="我先给你看一位比较贴近的。",
                criteria_labels=["无锡", "认真恋爱"],
                result_group_title="这一轮先给你看 1 位",
                selected_candidates=[
                    DiscoveryCandidateSelection(
                        profile_id=1002,
                        reason_summary="城市一致、关系目标一致。",
                    )
                ],
            ),
            search_response=response,
        )


class DiscoveryServiceTests(unittest.TestCase):
    def test_in_memory_agent_session_store_persists_items_across_instances(self) -> None:
        store = InMemoryDiscoveryAgentSessionStore()
        session = store.get_session("discovery-session-001")
        items = [
            {"role": "user", "content": [{"type": "input_text", "text": "你好"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "你好呀"}]},
        ]

        asyncio.run(session.add_items(items))

        reloaded = store.get_session("discovery-session-001")
        self.assertEqual(asyncio.run(reloaded.get_items()), items)
        self.assertEqual(asyncio.run(reloaded.pop_item()), items[-1])
        self.assertEqual(asyncio.run(reloaded.get_items()), items[:1])
        asyncio.run(reloaded.clear_session())
        self.assertEqual(asyncio.run(reloaded.get_items()), [])

    def test_agents_runtime_passes_session_memory_to_runner(self) -> None:
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session_store = InMemoryDiscoveryAgentSessionStore()
        session = session_store.get_session("discovery-session-002")
        captured: dict[str, object] = {}

        def _fake_agent(**kwargs):
            captured["tools"] = kwargs.get("tools")
            captured["output_type"] = kwargs.get("output_type")
            return object()

        def _fake_run_sync(_agent, input, **kwargs):
            captured["input"] = input
            captured["session"] = kwargs.get("session")
            return {
                "phase": "collecting_preferences",
                "assistant_message": "先说说你的基本要求。",
                "criteria_labels": [],
                "suggested_actions": [],
                "selected_candidates": [],
            }

        run_input = DiscoveryRunInput(
            session_id="discovery-session-002",
            requester_id=70001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=["上海"],
            recent_timeline=[
                {"item_type": "assistant_message", "body": "前面聊过城市和关系目标。"},
            ],
            runtime_context={
                "requester_profile_snapshot": {"self_city": "上海"},
                "recent_timeline_summary": [
                    {"item_type": "assistant_message", "body": "前面聊过城市和关系目标。"},
                ],
                "visible_actions": [{"label": "继续补充城市", "style": "secondary", "hint": {"kind": "followup"}}],
                "last_search_summary": {"result_count": 0, "has_match": False},
                "page_summary": {"criteria_labels": ["上海"]},
            },
            search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), mock.patch(
            "agents.Agent",
            side_effect=_fake_agent,
        ), mock.patch("agents.Runner.run_sync", side_effect=_fake_run_sync):
            result = runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="我在上海，想认真恋爱。",
                action_context=None,
            )

        self.assertIs(captured["session"], session)
        payload = json.loads(str(captured["input"]))
        self.assertEqual(payload["official_context"]["requester_profile_snapshot"]["self_city"], "上海")
        self.assertEqual(len(payload["official_context"]["recent_timeline_summary"]), 1)
        tool_names = [
            getattr(tool, "name", None) or getattr(tool, "__name__", "")
            for tool in list(captured["tools"] or [])
        ]
        self.assertEqual(
            tool_names,
            [
                "sync_requester_persona_memory",
                "search_partner_candidates",
                "create_saved_search_subscription_from_last_search",
            ],
        )
        output_type = captured["output_type"]
        self.assertIsInstance(output_type, AgentOutputSchema)
        self.assertTrue(output_type.is_strict_json_schema())
        self.assertEqual(result.decision.assistant_message, "先说说你的基本要求。")

    def test_discovery_decision_schema_is_strict_compatible_and_enumerated(self) -> None:
        schema = AgentOutputSchema(DiscoveryDecisionModel, strict_json_schema=True).json_schema()
        self.assertEqual(
            schema["properties"]["phase"]["enum"],
            ["collecting_preferences", "searching", "results_shown", "no_result"],
        )
        action_schema = schema["$defs"]["DiscoveryActionSuggestionModel"]
        style_schema = action_schema["properties"]["style"]
        self.assertEqual(style_schema["enum"], ["primary", "secondary", "ghost"])
        self.assertFalse(action_schema["additionalProperties"])
        payload_schema = action_schema["properties"]["semantic_payload"]
        self.assertIn("anyOf", payload_schema)
        union_schema = next(
            item for item in payload_schema["anyOf"] if isinstance(item, dict) and "discriminator" in item
        )
        mapping = union_schema["discriminator"]["mapping"]
        self.assertIn("saved_search_opt_in", mapping)

    def test_discovery_action_suggestion_model_supports_known_payload_shapes(self) -> None:
        model = DiscoveryActionSuggestionModel.model_validate(
            {
                "label": "细聊这三位",
                "style": "primary",
                "semantic_payload": {
                    "kind": "refine_candidates",
                    "candidates": [30017, 30003, 30029],
                },
            }
        )
        payload = model.semantic_payload
        assert payload is not None
        self.assertEqual(payload.kind, "refine_candidates")
        self.assertEqual(payload.candidates, [30017, 30003, 30029])

    def test_discovery_decision_model_accepts_message_alias_and_age_preference_payload(self) -> None:
        model = DiscoveryDecisionModel.model_validate(
            {
                "phase": "collecting_preferences",
                "message": "先确认一下你想找男生还是女生。",
                "criteria_labels": ["上海", "认真恋爱"],
                "suggested_actions": [
                    {
                        "label": "男生，27-35岁",
                        "style": "secondary",
                        "semantic_payload": {
                            "kind": "age_preference",
                            "target_gender": "男",
                            "age_min": 27,
                            "age_max": 35,
                        },
                    }
                ],
            }
        )
        self.assertEqual(model.assistant_message, "先确认一下你想找男生还是女生。")
        payload = model.suggested_actions[0].semantic_payload
        assert payload is not None
        self.assertEqual(payload.kind, "age_preference")
        self.assertEqual(payload.target_gender, "男")
        self.assertEqual(payload.age_min, 27)
        self.assertEqual(payload.age_max, 35)

    def test_configure_agents_sdk_provider_defaults_to_responses(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_OPENAI_API": "",
                "HER_CHAT_AGENT_OPENAI_API": "",
                "HER_CHAT_ASSISTANT_OPENAI_API": "",
                "HER_DISCOVERY_AGENT_BASE_URL": "",
                "HER_CHAT_AGENT_BASE_URL": "",
                "HER_CHAT_ASSISTANT_BASE_URL": "",
                "OPENAI_BASE_URL": "",
            },
            clear=False,
        ), mock.patch("agents.set_default_openai_api") as mocked_set_api:
            _configure_agents_sdk_provider()

        mocked_set_api.assert_called_once_with("responses")

    def test_configure_agents_sdk_provider_allows_explicit_chat_completions_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_OPENAI_API": "chat_completions",
                "HER_CHAT_AGENT_OPENAI_API": "",
                "HER_CHAT_ASSISTANT_OPENAI_API": "",
                "HER_DISCOVERY_AGENT_BASE_URL": "",
                "HER_CHAT_AGENT_BASE_URL": "",
                "HER_CHAT_ASSISTANT_BASE_URL": "",
                "OPENAI_BASE_URL": "",
            },
            clear=False,
        ), mock.patch("agents.set_default_openai_api") as mocked_set_api:
            _configure_agents_sdk_provider()

        mocked_set_api.assert_called_once_with("chat_completions")

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
        tool_calls = service.storage.list_tool_calls(session_id)
        self.assertEqual(tool_calls[-1].tool_name, "create_saved_search_subscription_from_last_search")
        self.assertTrue(tool_calls[-1].result["created_subscription"])
        fake_conn.close.assert_called_once()

    def test_service_persists_view_snapshots_for_session_restore(self) -> None:
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

        snapshots = service.storage.list_view_snapshots(session_id)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].phase, "collecting_preferences")
        self.assertEqual(snapshots[-1].phase, "results_shown")
        latest_snapshot = service.storage.get_latest_view_snapshot(session_id)
        assert latest_snapshot is not None
        self.assertEqual(latest_snapshot.view["timeline"][-1]["item_type"], "result_group")

        restored = service.get_session_view(session_id)
        self.assertEqual(restored["view"]["timeline"][-1]["item_type"], "result_group")

    def test_service_records_persona_memory_tool_call(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_PersonaSyncRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]
        captured: dict[str, object] = {}

        def _fake_upsert(request, *, include_normalized_patch=False):
            captured["request"] = request
            captured["include_normalized_patch"] = include_normalized_patch
            return {
                "user_key": request["user_key"],
                "normalized_patch": dict(request["patch"]),
                "synced_profile": True,
            }

        with mock.patch.dict(os.environ, {"PERSONA_MEMORY_MYSQL_SOURCE": "mysql://persona-demo"}, clear=False), mock.patch.object(
            service,
            "_load_persona_memory_bindings",
            return_value=_fake_upsert,
        ):
            service.process_turn(
                session_id=session_id,
                user_message_text="我在上海，不接受抽烟，想认真恋爱。",
            )

        request = dict(captured["request"] or {})
        self.assertEqual(request["source"], "mysql://persona-demo")
        self.assertEqual(request["user_key"], "70001")
        self.assertTrue(request["sync_profile"])
        self.assertTrue(captured["include_normalized_patch"])
        tool_calls = service.storage.list_tool_calls(session_id)
        persona_tool_calls = [item for item in tool_calls if item.tool_name == "sync_requester_persona_memory"]
        self.assertEqual(len(persona_tool_calls), 1)
        self.assertTrue(persona_tool_calls[0].result["synced"])
        self.assertEqual(persona_tool_calls[0].arguments["patch"]["must_not_have_tags"], ["抽烟"])

    def test_service_marks_failed_tool_call_and_updates_metrics(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_PersonaSyncRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        with mock.patch.dict(os.environ, {"PERSONA_MEMORY_MYSQL_SOURCE": ""}, clear=False):
            service.process_turn(
                session_id=session_id,
                user_message_text="我在上海，不接受抽烟，想认真恋爱。",
            )

        tool_calls = service.storage.list_tool_calls(session_id)
        persona_tool_calls = [item for item in tool_calls if item.tool_name == "sync_requester_persona_memory"]
        self.assertEqual(len(persona_tool_calls), 1)
        self.assertEqual(persona_tool_calls[0].status, "failed")
        self.assertEqual(persona_tool_calls[0].result["error_code"], "persona_memory_source_not_configured")
        metrics = service.get_observability_snapshot()["counters"]
        self.assertEqual(metrics["tool_calls.failed"], 1)

    def test_service_records_search_tool_call_with_search_run_reference(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_SearchToolRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        fake_search_response = {
            "has_match": True,
            "result_count": 1,
            "results": [
                {
                    "id": 1002,
                    "name": "周晴",
                    "score": 88,
                    "photo_preview": ["https://static.example.com/1002.jpg"],
                    "verification_items": [],
                    "matched_on": ["城市一致", "关系目标一致"],
                    "trust_summary": {"headline": "真人认证"},
                    "profile": {
                        "age": 30,
                        "city": "无锡",
                        "job": "产品经理",
                        "education": "本科",
                    },
                }
            ],
        }

        with mock.patch.dict(os.environ, {"HER_DISCOVERY_PROFILE_SOURCE": "mysql://search-demo"}, clear=False), mock.patch(
            "discovery_system.service.load_self_profile",
            return_value={"self_city": "无锡"},
        ), mock.patch(
            "discovery_system.service.search_profiles",
            return_value=dict(fake_search_response),
        ):
            service.process_turn(
                session_id=session_id,
                user_message_text="我想找无锡、认真恋爱的女生。",
            )

        tool_calls = service.storage.list_tool_calls(session_id)
        search_tool_calls = [item for item in tool_calls if item.tool_name == "search_partner_candidates"]
        self.assertEqual(len(search_tool_calls), 1)
        self.assertEqual(search_tool_calls[0].search_run_id, 1)
        self.assertEqual(search_tool_calls[0].result["result_count"], 1)

    def test_service_observability_snapshot_tracks_counters(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_SearchToolRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        with mock.patch.dict(os.environ, {"HER_DISCOVERY_PROFILE_SOURCE": "mysql://search-demo"}, clear=False), mock.patch(
            "discovery_system.service.load_self_profile",
            return_value={"self_city": "无锡"},
        ), mock.patch(
            "discovery_system.service.search_profiles",
            return_value={
                "has_match": True,
                "result_count": 1,
                "results": [
                    {
                        "id": 1002,
                        "name": "周晴",
                        "score": 88,
                        "photo_preview": [],
                        "verification_items": [],
                        "matched_on": [],
                        "trust_summary": {"headline": "真人认证"},
                        "profile": {"age": 30, "city": "无锡", "job": "产品经理", "education": "本科"},
                    }
                ],
            },
        ), mock.patch(
            "discovery_system.service.load_profile_detail",
            return_value={
                "id": 1002,
                "name": "周晴",
                "photo_preview": [],
                "verification_items": [],
                "profile": {"job": "产品经理", "education": "本科", "relationship_goal": "认真恋爱"},
            },
        ):
            service.process_turn(
                session_id=session_id,
                user_message_text="我想找无锡、认真恋爱的女生。",
            )
            service.get_session_view(session_id)
            service.get_profile_detail(1002, session_id=session_id)

        counters = service.get_observability_snapshot()["counters"]
        self.assertEqual(counters["sessions.created"], 1)
        self.assertEqual(counters["turns.created"], 2)
        self.assertEqual(counters["turns.user_message"], 1)
        self.assertEqual(counters["search_runs.created"], 1)
        self.assertEqual(counters["tool_calls.total"], 1)
        self.assertEqual(counters["tool_calls.search_partner_candidates"], 1)
        self.assertEqual(counters["view_snapshots.written"], 2)
        self.assertEqual(counters["session_restores"], 1)
        self.assertEqual(counters["profile_detail_reads"], 1)


if __name__ == "__main__":
    unittest.main()
