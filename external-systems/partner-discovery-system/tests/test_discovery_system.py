from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import pathlib
import sys
import types
import unittest
from unittest import mock

from agents import AgentOutputSchema


DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

_DISCOVERY_TEST_PROFILE_SOURCE = "mysql://root@127.0.0.1:3307/her_discovery_test?table=profiles"
_DISCOVERY_TEST_PERSONA_SOURCE = "mysql://root@127.0.0.1:3307/her_discovery_test?table=user_personas"

from discovery_system.agent_runtime import (  # noqa: E402
    AgentsSdkDiscoveryAgentRuntime,
    DiscoveryActionSuggestion,
    DiscoveryActionSuggestionModel,
    _BAILIAN_RESPONSES_BASE_URL,
    _BAILIAN_RESPONSES_DEFAULT_MODEL,
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


class _PhantomSearchingRuntime:
    def initial_decision(self, _run_input):
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="先告诉我你想找什么样的人。",
            )
        )

    def run_turn(self, _run_input, *, user_message=None, action_context=None):
        del user_message, action_context
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="searching",
                assistant_message="我先帮你搜一下。",
                criteria_labels=["无锡", "25-30岁"],
                suggested_actions=[
                    DiscoveryActionSuggestion(label="先看看有没有人", style="primary"),
                ],
            ),
            search_response=None,
        )


class DiscoveryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_profile_source = os.environ.get("HER_DISCOVERY_PROFILE_SOURCE")
        self._old_persona_source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        self._old_create_session_mode = os.environ.get("HER_DISCOVERY_CREATE_SESSION_MODE")
        os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = _DISCOVERY_TEST_PROFILE_SOURCE
        os.environ["PERSONA_MEMORY_MYSQL_SOURCE"] = _DISCOVERY_TEST_PERSONA_SOURCE
        os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = "agent"

    def tearDown(self) -> None:
        if self._old_profile_source is None:
            os.environ.pop("HER_DISCOVERY_PROFILE_SOURCE", None)
        else:
            os.environ["HER_DISCOVERY_PROFILE_SOURCE"] = self._old_profile_source
        if self._old_persona_source is None:
            os.environ.pop("PERSONA_MEMORY_MYSQL_SOURCE", None)
        else:
            os.environ["PERSONA_MEMORY_MYSQL_SOURCE"] = self._old_persona_source
        if self._old_create_session_mode is None:
            os.environ.pop("HER_DISCOVERY_CREATE_SESSION_MODE", None)
        else:
            os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = self._old_create_session_mode

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
            captured["instructions"] = kwargs.get("instructions")
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
                "page_summary": {
                    "criteria_labels": ["上海"],
                    "result_cards": [
                        {
                            "profile_id": 1002,
                            "title": "郑星涵 27",
                            "subtitle": "无锡 · 药师 · 本科",
                            "match_score": 92,
                            "reason_summary": "先前主要因为情绪稳定。",
                            "personality_match_context": {
                                "mbti": {"type_code": "ISFJ"},
                                "attachment": {"type_code": "secure", "anxiety": 30, "avoidance": 20},
                                "values": {"top_values": ["稳定经营", "家庭责任"]},
                                "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                            },
                        }
                    ],
                },
            },
            search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
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
        result_cards = payload["official_context"]["page_summary"]["result_cards"]
        self.assertEqual(result_cards[0]["profile_id"], 1002)
        self.assertEqual(result_cards[0]["personality_match_context"]["mbti"]["type_code"], "ISFJ")
        self.assertEqual(result_cards[0]["personality_match_context"]["attachment"]["type_code"], "secure")
        tool_names = [
            getattr(tool, "name", None) or getattr(tool, "__name__", "")
            for tool in list(captured["tools"] or [])
        ]
        self.assertEqual(
            tool_names,
            [
                "sync_requester_persona_memory",
                "propose_requester_profile_update",
                "search_partner_candidates",
                "create_saved_search_subscription_from_last_search",
            ],
        )
        output_type = captured["output_type"]
        self.assertIsInstance(output_type, AgentOutputSchema)
        self.assertTrue(output_type.is_strict_json_schema())
        self.assertEqual(result.decision.assistant_message, "先说说你的基本要求。")
        instructions = str(captured.get("instructions") or "")
        self.assertIn("不要输出形如 `{\"tool_calls\":[...]}` 的文本", instructions)
        self.assertIn("不要说“本地没有符合条件的人”", instructions)
        self.assertIn("优先基于 page_summary.result_cards", instructions)

    def test_agents_runtime_passes_assessment_result_in_recent_timeline_summary(self) -> None:
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session = InMemoryDiscoveryAgentSessionStore().get_session("discovery-session-004")
        captured: dict[str, object] = {}

        def _fake_agent(**kwargs):
            captured["output_type"] = kwargs.get("output_type")
            return object()

        def _fake_run_sync(_agent, input, **kwargs):
            captured["input"] = input
            captured["session"] = kwargs.get("session")
            return {
                "phase": "collecting_preferences",
                "assistant_message": "继续问我你的匹配建议。",
                "criteria_labels": [],
                "suggested_actions": [],
                "selected_candidates": [],
            }

        run_input = DiscoveryRunInput(
            session_id="discovery-session-004",
            requester_id=70001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=[],
            recent_timeline=[
                {
                    "item_type": "assessment_result",
                    "card": {
                        "result_data": {
                            "type_code": "INTJ",
                            "interpretation_data": {"summary": "偏理性，慢热但稳定。"},
                        }
                    },
                },
                {"item_type": "assistant_message", "body": "亲爱的，你的测试结果出来啦！"},
            ],
            runtime_context={
                "recent_timeline_summary": [
                    {
                        "item_type": "assessment_result",
                        "card": {
                            "result_data": {
                                "type_code": "INTJ",
                                "interpretation_data": {"summary": "偏理性，慢热但稳定。"},
                            }
                        },
                    }
                ]
            },
            search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            agent_session=session,
        )

        with mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), mock.patch(
            "agents.Agent",
            side_effect=_fake_agent,
        ), mock.patch("agents.Runner.run_sync", side_effect=_fake_run_sync):
            runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="我的 MBTI 适合什么人？",
                action_context=None,
            )

        payload = json.loads(str(captured["input"]))
        summary = payload["official_context"]["recent_timeline_summary"]
        self.assertEqual(summary[0]["item_type"], "assessment_result")
        self.assertEqual(summary[0]["type_code"], "INTJ")
        self.assertEqual(summary[0]["summary"], "偏理性，慢热但稳定。")

    def test_agents_runtime_uses_personality_explanation_fallback_for_shown_candidates(self) -> None:
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session = InMemoryDiscoveryAgentSessionStore().get_session("discovery-session-005")

        run_input = DiscoveryRunInput(
            session_id="discovery-session-005",
            requester_id=70001,
            profile_id=10001,
            phase="results_shown",
            criteria_labels=["无锡", "结婚导向"],
            recent_timeline=[],
            runtime_context={
                "requester_profile_snapshot": {
                    "personality_traits": {
                        "mbti": {"type_code": "ISTP"},
                        "attachment": {"type_code": "secure", "anxiety": 27, "avoidance": 48},
                        "values": {
                            "value_type": "稳定经营型",
                            "top_values": ["稳定经营", "家庭责任", "独立空间"],
                        },
                    }
                },
                "page_summary": {
                    "result_cards": [
                        {
                            "profile_id": 9202,
                            "title": "宋若嘉 26",
                            "subtitle": "无锡 · 教师 · 硕士",
                            "personality_match_context": {
                                "mbti": {"type_code": "ISTJ"},
                                "attachment": {"type_code": "secure", "anxiety": 30, "avoidance": 41},
                                "values": {
                                    "value_type": "稳定经营型",
                                    "top_values": ["稳定经营", "家庭责任", "成长探索"],
                                },
                                "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                            },
                        }
                    ]
                },
            },
            search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            tool_call_buffer=[],
            agent_session=session,
        )

        with mock.patch.object(runtime, "_should_use_agents_sdk", return_value=False):
            result = runtime.run_turn(
                run_input,
                user_message="就按第一位，从测评角度解释为什么推荐她，不要重新搜索。",
                action_context=None,
            )

        self.assertEqual(result.decision.phase, "results_shown")
        self.assertIn("宋若嘉", result.decision.assistant_message)
        self.assertIn("MBTI", result.decision.assistant_message)
        self.assertIn("依恋", result.decision.assistant_message)
        self.assertIn("价值观", result.decision.assistant_message)

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
                "HER_DISCOVERY_AGENT_WIRE_API": "",
                "HER_DISCOVERY_AGENT_OPENAI_API": "",
                "HER_CHAT_AGENT_OPENAI_API": "chat_completions",
                "HER_CHAT_ASSISTANT_OPENAI_API": "chat_completions",
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
                "HER_DISCOVERY_AGENT_WIRE_API": "",
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

    def test_configure_agents_sdk_provider_maps_dashscope_shared_base_to_bailian_responses_base(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_WIRE_API": "",
                "HER_DISCOVERY_AGENT_OPENAI_API": "responses",
                "HER_DISCOVERY_AGENT_BASE_URL": "",
                "DASHSCOPE_BASE_URL": "",
                "OPENAI_BASE_URL": "https://coding.dashscope.aliyuncs.com/v1",
                "DASHSCOPE_API_KEY": "",
                "OPENAI_API_KEY": "shared-key",
            },
            clear=False,
        ), mock.patch("openai.AsyncOpenAI") as mocked_client, mock.patch(
            "agents.set_default_openai_client"
        ), mock.patch("agents.set_default_openai_api"), mock.patch("agents.set_tracing_disabled"):
            _configure_agents_sdk_provider()

        self.assertEqual(mocked_client.call_args.kwargs["base_url"], _BAILIAN_RESPONSES_BASE_URL)
        self.assertEqual(mocked_client.call_args.kwargs["api_key"], "shared-key")

    def test_configure_agents_sdk_provider_prefers_discovery_specific_api_key(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_API_KEY": "discovery-key",
                "OPENAI_API_KEY": "shared-key",
                "HER_DISCOVERY_AGENT_BASE_URL": "https://api.example.com/v1",
                "HER_DISCOVERY_AGENT_OPENAI_API": "responses",
            },
            clear=False,
        ), mock.patch("openai.AsyncOpenAI") as mocked_client, mock.patch(
            "agents.set_default_openai_client"
        ), mock.patch("agents.set_default_openai_api"), mock.patch("agents.set_tracing_disabled"):
            _configure_agents_sdk_provider()

        self.assertEqual(mocked_client.call_args.kwargs["api_key"], "discovery-key")

    def test_agents_sdk_runtime_accepts_discovery_specific_api_key(self) -> None:
        runtime = AgentsSdkDiscoveryAgentRuntime()
        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_RUNTIME": "agents_sdk",
                "HER_CHAT_AGENT_RUNTIME": "",
                "HER_DISCOVERY_AGENT_API_KEY": "discovery-key",
                "OPENAI_API_KEY": "",
            },
            clear=False,
        ):
            self.assertTrue(runtime._should_use_agents_sdk())

    def test_run_with_agents_sdk_defaults_model_to_bailian_responses_model(self) -> None:
        runtime = AgentsSdkDiscoveryAgentRuntime()
        session = InMemoryDiscoveryAgentSessionStore().get_session("discovery-session-003")
        captured: dict[str, object] = {}

        def _fake_agent(*args, **kwargs):
            captured["instructions"] = kwargs.get("instructions")
            captured["model"] = kwargs.get("model")
            captured["output_type"] = kwargs.get("output_type")
            captured["tools"] = kwargs.get("tools")
            return object()

        def _fake_run_sync(_agent, *, input=None, session=None):
            captured["input"] = input
            captured["session"] = session
            return type(
                "_Result",
                (),
                {
                    "final_output": {
                        "phase": "collecting_preferences",
                        "assistant_message": "先说说你的基本要求。",
                        "criteria_labels": [],
                        "suggested_actions": [],
                    }
                },
            )()

        run_input = DiscoveryRunInput(
            session_id="discovery-session-003",
            requester_id=70001,
            profile_id=10001,
            phase="collecting_preferences",
            criteria_labels=[],
            recent_timeline=[],
            runtime_context={},
            search_partner_candidates=lambda _criteria, _limit: {"has_match": False, "result_count": 0, "results": []},
            sync_requester_persona_memory=lambda _patch: {"synced": True},
            propose_requester_profile_update=lambda _patch_json, _evidence="": {"proposed": False},
            create_saved_search_subscription_from_last_search=lambda: {"created_subscription": False},
            agent_session=session,
        )

        with mock.patch.dict(
            os.environ,
            {
                "HER_DISCOVERY_AGENT_WIRE_API": "",
                "HER_DISCOVERY_AGENT_OPENAI_API": "",
                "HER_DISCOVERY_AGENT_MODEL": "",
                "HER_CHAT_AGENT_MODEL": "glm-5",
            },
            clear=False,
        ), mock.patch("discovery_system.agent_runtime._configure_agents_sdk_provider"), mock.patch(
            "agents.Agent",
            side_effect=_fake_agent,
        ), mock.patch("agents.Runner.run_sync", side_effect=_fake_run_sync):
            runtime._run_with_agents_sdk(
                run_input,
                event="user_message",
                user_message="我在上海，想认真恋爱。",
                action_context=None,
            )

        self.assertEqual(captured["model"], _BAILIAN_RESPONSES_DEFAULT_MODEL)

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

    def test_service_appends_proactive_personality_blurb_to_results_message(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_FakeRuntime(),
        )

        with mock.patch.object(
            service,
            "_load_requester_profile",
            return_value={
                "personality_traits": {
                    "mbti": {"type_code": "ISTP"},
                    "attachment": {"type_code": "secure"},
                    "values": {"top_values": ["稳定经营", "家庭责任", "独立空间"]},
                }
            },
        ):
            created = service.create_session(requester_id=70001, profile_id=10001)
            session_id = created["session"]["session_id"]
            session = service.storage.get_session(session_id)
            runtime_result = DiscoveryRuntimeResult(
                decision=DiscoveryDecision(
                    phase="results_shown",
                    assistant_message="这一轮先给你看两位。",
                    criteria_labels=["无锡"],
                    selected_candidates=[
                        DiscoveryCandidateSelection(profile_id=2001, reason_summary=""),
                        DiscoveryCandidateSelection(profile_id=2002, reason_summary=""),
                    ],
                ),
                search_response={
                    "has_match": True,
                    "result_count": 2,
                    "results": [
                        {
                            "id": 2001,
                            "name": "张安萌",
                            "score": 91,
                            "profile": {"age": 27, "city": "无锡", "job": "采购", "education": "本科"},
                            "personality_traits": {
                                "mbti": {"type_code": "ESFJ"},
                                "attachment": {"type_code": "secure"},
                                "values": {"top_values": ["稳定经营", "家庭责任"]},
                                "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                            },
                        },
                        {
                            "id": 2002,
                            "name": "唐语妍",
                            "score": 90,
                            "profile": {"age": 26, "city": "无锡", "job": "审计", "education": "硕士"},
                            "personality_traits": {
                                "mbti": {"type_code": "ISTJ"},
                                "attachment": {"type_code": "secure"},
                                "values": {"top_values": ["稳定经营", "成长探索"]},
                                "availability": {"has_mbti": True, "has_attachment": True, "has_values": True},
                            },
                        },
                    ],
                },
            )
            service._apply_runtime_result(session, runtime_result, now=datetime.now())

        timeline = session.view["timeline"]
        last_assistant = next(item for item in reversed(timeline) if item.get("item_type") == "assistant_message")
        self.assertIn("从测评角度看", last_assistant["body"])
        self.assertIn("张安萌这位", last_assistant["body"])
        self.assertIn("唐语妍这位", last_assistant["body"])

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

    def test_express_interest_from_discovery_does_not_deliver_recommendation_card(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_FakeRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]
        current = created["session"]["updated_at"]
        search_run_id = service.storage.create_search_run(
            session_id=session_id,
            requester_id=70001,
            profile_id=10001,
            source="discovery_session",
            criteria={"cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"city": "无锡"},
            limit_count=5,
            response={
                "has_match": True,
                "result_count": 1,
                "results": [
                    {
                        "id": 1001,
                        "name": "林知夏",
                        "score": 92,
                        "matched_on": ["城市一致", "关系目标一致"],
                        "profile": {"age": 29, "city": "无锡", "job": "中学老师"},
                    }
                ],
                "request_meta": {
                    "source": "discovery_session",
                    "criteria": {"cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
                    "self_profile": {"city": "无锡"},
                    "self_id": 10001,
                },
            },
            created_at=current,
        )
        stored_session = service.storage.get_session(session_id)
        assert stored_session is not None
        stored_session.state["last_search_run_id"] = search_run_id
        service.storage.save_session(stored_session)

        fake_conn = mock.Mock()
        fake_case_conn = mock.Mock()
        create_subscription = mock.Mock(return_value={"subscription_id": "saved-search-proxy-123"})
        deliver_in_app_recommendations = mock.Mock()
        upsert_recommendation = mock.Mock(return_value={"recommendation_id": 1, "candidate_id": 1001})
        create_match_case = mock.Mock(return_value={"case_id": "match-case-1", "case_status": "pending_outreach"})
        dispatch_match_case_outreach = mock.Mock(
            return_value={"case_id": "match-case-1", "case_status": "awaiting_reply"}
        )

        recommendation_module = types.ModuleType("recommendation_system")
        recommendation_module.create_subscription = create_subscription
        recommendation_module.deliver_in_app_recommendations = deliver_in_app_recommendations

        recommendation_rows_module = types.ModuleType("recommendation_system.recommendation_rows")
        recommendation_rows_module.upsert_recommendation = upsert_recommendation

        proxy_intro_module = types.ModuleType("matchmaking_system.proxy_intro")
        proxy_intro_module.create_match_case = create_match_case
        proxy_intro_module.dispatch_match_case_outreach = dispatch_match_case_outreach

        proxy_intro_storage_module = types.ModuleType("match_domain.proxy_intro_storage")
        proxy_intro_storage_module.open_proxy_intro_case_connection = mock.Mock(return_value=fake_case_conn)

        with mock.patch.object(service, "_open_recommendation_conn", return_value=fake_conn), mock.patch.dict(
            sys.modules,
            {
                "recommendation_system": recommendation_module,
                "recommendation_system.recommendation_rows": recommendation_rows_module,
                "matchmaking_system.proxy_intro": proxy_intro_module,
                "match_domain.proxy_intro_storage": proxy_intro_storage_module,
            },
        ):
            out = service.express_interest(session_id, candidate_id=1001)

        self.assertTrue(out["ok"])
        self.assertEqual(out["subscription_id"], "saved-search-proxy-123")
        self.assertEqual(out["candidate_id"], 1001)
        deliver_in_app_recommendations.assert_not_called()
        create_subscription.assert_called_once()
        upsert_recommendation.assert_called_once()
        create_match_case.assert_called_once()
        dispatch_match_case_outreach.assert_called_once()
        fake_conn.close.assert_called_once()

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

        with mock.patch.object(
            service,
            "_load_persona_memory_bindings",
            return_value=_fake_upsert,
        ):
            service.process_turn(
                session_id=session_id,
                user_message_text="我在上海，不接受抽烟，想认真恋爱。",
            )

        request = dict(captured["request"] or {})
        self.assertEqual(request["source"], _DISCOVERY_TEST_PERSONA_SOURCE)
        self.assertEqual(request["user_key"], "70001")
        self.assertFalse(request["sync_profile"])
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

        with mock.patch.dict(
            os.environ,
            {"PERSONA_MEMORY_MYSQL_SOURCE": "", "HER_DISCOVERY_PROFILE_SOURCE": ""},
            clear=False,
        ):
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

        with mock.patch(
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

    def test_service_search_omits_missing_requester_self_id(self) -> None:
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
                    "photo_preview": [],
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

        with mock.patch(
            "discovery_system.service.load_self_profile",
            return_value=None,
        ), mock.patch(
            "discovery_system.service.search_profiles",
            return_value=dict(fake_search_response),
        ) as mocked_search:
            result = service.process_turn(
                session_id=session_id,
                user_message_text="我想找无锡、认真恋爱的女生。",
            )

        self.assertIsNone(mocked_search.call_args.kwargs["self_id"])
        self.assertIsNone(mocked_search.call_args.kwargs["self_profile"])
        tool_calls = service.storage.list_tool_calls(session_id)
        search_tool_call = next(item for item in tool_calls if item.tool_name == "search_partner_candidates")
        self.assertIsNone(search_tool_call.result["request_meta"]["self_id"])
        self.assertEqual(search_tool_call.result["request_meta"]["requested_self_id"], 10001)
        self.assertTrue(search_tool_call.result["request_meta"]["self_profile_lookup_failed"])
        self.assertEqual(result["session"]["phase"], "results_shown")
        self.assertEqual(result["view"]["timeline"][-1]["item_type"], "result_group")

    def test_service_coerces_failed_search_into_non_no_result_message(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_SearchToolRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        with mock.patch(
            "discovery_system.service.load_self_profile",
            return_value={"self_city": "无锡"},
        ), mock.patch(
            "discovery_system.service.search_profiles",
            side_effect=ValueError("Could not find self profile id 10001 in the selected source."),
        ):
            result = service.process_turn(
                session_id=session_id,
                user_message_text="我想找无锡、认真恋爱的女生。",
            )

        self.assertEqual(result["session"]["phase"], "collecting_preferences")
        self.assertIn("不代表没有合适人选", result["view"]["timeline"][-1]["body"])
        self.assertEqual(result["view"]["suggested_actions"], [])
        self.assertNotEqual(result["view"]["timeline"][-1]["item_type"], "result_group")
        tool_calls = service.storage.list_tool_calls(session_id)
        search_tool_call = next(item for item in tool_calls if item.tool_name == "search_partner_candidates")
        self.assertEqual(search_tool_call.status, "failed")
        self.assertEqual(search_tool_call.result["error_code"], "partner_search_failed")
        stored_session = service.storage.get_session(session_id)
        assert stored_session is not None
        last_search_summary = service._build_last_search_summary(stored_session)
        assert last_search_summary is not None
        self.assertEqual(last_search_summary["error_code"], "partner_search_failed")
        blocked = service._create_saved_search_subscription_from_last_search(stored_session)
        self.assertEqual(blocked["error_code"], "search_run_failed")

    def test_service_coerces_searching_without_tool_call_back_to_collecting(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_PhantomSearchingRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        result = service.process_turn(
            session_id=session_id,
            user_message_text="帮我找对象",
        )

        self.assertEqual(result["session"]["phase"], "collecting_preferences")
        self.assertIn("还没真正发起筛选", result["view"]["timeline"][-1]["body"])
        self.assertEqual(result["view"]["suggested_actions"][0]["label"], "先看看有没有人")
        tool_calls = service.storage.list_tool_calls(session_id)
        self.assertEqual(tool_calls, [])

    def test_service_observability_snapshot_tracks_counters(self) -> None:
        service = DiscoveryService(
            storage=InMemoryDiscoveryStorage(),
            runtime=_SearchToolRuntime(),
        )
        created = service.create_session(requester_id=70001, profile_id=10001)
        session_id = created["session"]["session_id"]

        with mock.patch(
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


class DiscoveryProfileFirstSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_create_session_mode = os.environ.get("HER_DISCOVERY_CREATE_SESSION_MODE")
        os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = "profile_first"

    def tearDown(self) -> None:
        if self._old_create_session_mode is None:
            os.environ.pop("HER_DISCOVERY_CREATE_SESSION_MODE", None)
        else:
            os.environ["HER_DISCOVERY_CREATE_SESSION_MODE"] = self._old_create_session_mode

    def test_create_session_profile_first_skips_initial_decision_and_searches(self) -> None:
        runtime = _FakeRuntime()
        service = DiscoveryService(storage=InMemoryDiscoveryStorage(), runtime=runtime)
        search_response = {
            "has_match": True,
            "result_count": 1,
            "results": [
                {
                    "id": 1001,
                    "name": "林知夏",
                    "score": 92,
                    "matched_on": ["城市一致", "关系目标一致"],
                    "profile": {"age": 29, "city": "无锡", "job": "中学老师", "education": "硕士"},
                }
            ],
            "request_meta": {
                "criteria": {
                    "cities": ["无锡"],
                    "gender": "女",
                    "age_min": 26,
                    "age_max": 30,
                    "relationship_goals": ["认真恋爱"],
                }
            },
        }

        with mock.patch.object(service, "_search_partner_candidates", return_value=search_response) as search_mock:
            created = service.create_session(requester_id=70001, profile_id=10001)

        search_mock.assert_called_once()
        self.assertEqual(search_mock.call_args.kwargs["criteria"], {})
        self.assertEqual(search_mock.call_args.kwargs["limit"], 5)

        timeline = created["view"]["timeline"]
        self.assertEqual(timeline[0]["item_type"], "assistant_message")
        self.assertIn("有没有眼缘", timeline[0]["body"])
        self.assertEqual(timeline[-1]["item_type"], "result_group")
        self.assertEqual(timeline[-1]["cards"][0]["profile_id"], 1001)
        self.assertEqual(created["session"]["phase"], "results_shown")
        self.assertEqual(
            [chip["label"] for chip in created["view"]["criteria_chips"]],
            ["无锡", "女", "26-30岁", "认真恋爱"],
        )

        tool_calls = service.storage.list_tool_calls(created["session"]["session_id"])
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].tool_name, "search_partner_candidates")

        stored_session = service.storage.get_session(created["session"]["session_id"])
        assert stored_session is not None
        self.assertEqual(stored_session.state["create_session_mode"], "profile_first")

    def test_create_session_profile_first_empty_search_keeps_starter_actions(self) -> None:
        service = DiscoveryService(storage=InMemoryDiscoveryStorage(), runtime=_FakeRuntime())
        search_response = {
            "has_match": False,
            "result_count": 0,
            "results": [],
            "request_meta": {"criteria": {"cities": ["上海"]}},
        }

        with mock.patch.object(service, "_search_partner_candidates", return_value=search_response):
            created = service.create_session(requester_id=70001, profile_id=10001)

        timeline = created["view"]["timeline"]
        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["item_type"], "assistant_message")
        self.assertIn("暂时没找到", timeline[0]["body"])
        self.assertTrue(created["view"]["suggested_actions"])
        self.assertEqual(created["session"]["phase"], "collecting_preferences")


class DiscoveryProfileUpdateFlowTests(unittest.TestCase):
    def test_confirm_profile_update_applies_profiles_and_updates_timeline(self) -> None:
        from datetime import datetime

        from discovery_system.profile_updates import propose_profile_update
        from discovery_system.storage import StoredSession

        storage = InMemoryDiscoveryStorage()
        session = StoredSession(
            session_id="discovery-session-profile-update",
            requester_id=80001,
            profile_id=80001,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={"timeline": []},
            state={},
        )
        storage.save_session(session)

        proposed = propose_profile_update(
            storage,
            session,
            patch={"city": "杭州"},
            current_profile={"city": "上海", "age": 31},
        )
        self.assertTrue(proposed["proposed"])
        request_id = proposed["request_id"]
        storage.save_session(session)

        service = DiscoveryService(storage=storage, runtime=_FakeRuntime())
        with mock.patch("profile_service.apply_profile_updates") as apply_mock:
            out = service.confirm_profile_update(session.session_id, request_id)
        apply_mock.assert_called_once()
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "confirmed")
        self.assertIn("city", out.get("applied_fields", []))

        record = storage.get_profile_update_request(request_id)
        assert record is not None
        self.assertEqual(record["status"], "confirmed")

    def test_reject_profile_update_marks_request_rejected(self) -> None:
        from datetime import datetime

        from discovery_system.profile_updates import propose_profile_update
        from discovery_system.storage import StoredSession

        storage = InMemoryDiscoveryStorage()
        session = StoredSession(
            session_id="discovery-session-profile-reject",
            requester_id=80002,
            profile_id=80002,
            status="active",
            phase="collecting_preferences",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            view={"timeline": []},
            state={},
        )
        storage.save_session(session)

        proposed = propose_profile_update(
            storage,
            session,
            patch={"city": "杭州"},
            current_profile={"city": "上海"},
        )
        request_id = proposed["request_id"]
        storage.save_session(session)
        service = DiscoveryService(storage=storage, runtime=_FakeRuntime())
        out = service.reject_profile_update(session.session_id, request_id)
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "rejected")
        record = storage.get_profile_update_request(request_id)
        assert record is not None
        self.assertEqual(record["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
