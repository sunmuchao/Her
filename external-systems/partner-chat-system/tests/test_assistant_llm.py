import os
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.assistant_contract import GUIDANCE_SCHEMA_VERSION  # noqa: E402
from chat_system.assistant_llm import (  # noqa: E402
    _clear_assistant_llm_caches_for_tests,
    build_placeholder_assistant_guidance,
    generate_assistant_guidance,
    normalize_assistant_guidance,
    parse_assistant_guidance,
    render_assistant_guidance,
)


class _FakeOpenAIResponse:
    def __init__(self, content: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class _FakeOpenAIClient:
    response_content = "{}"
    last_create_kwargs = None
    create_call_count = 0
    instance_count = 0

    def __init__(self, **_kwargs):
        _FakeOpenAIClient.instance_count += 1
        self.chat = self
        self.completions = self

    def create(self, **_kwargs):
        _FakeOpenAIClient.last_create_kwargs = dict(_kwargs)
        _FakeOpenAIClient.create_call_count += 1
        return _FakeOpenAIResponse(self.response_content)


class _FakeTimeoutOpenAIClient:
    def __init__(self, **_kwargs):
        self.chat = self
        self.completions = self

    def create(self, **_kwargs):
        raise TimeoutError("request timed out")


class _FakeErrorOpenAIClient:
    def __init__(self, **_kwargs):
        self.chat = self
        self.completions = self

    def create(self, **_kwargs):
        raise RuntimeError("bad gateway")


class AssistantLLMTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("HER_CHAT_ASSISTANT_BASE_URL", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("HER_CHAT_ASSISTANT_MAX_TOKENS", None)
        _clear_assistant_llm_caches_for_tests()
        _FakeOpenAIClient.last_create_kwargs = None
        _FakeOpenAIClient.create_call_count = 0
        _FakeOpenAIClient.instance_count = 0

    def test_guidance_render_and_parse_round_trip(self):
        guidance = normalize_assistant_guidance(
            {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["对方上一句太短，原话题快聊干了"],
                "why_not_to_push": ["这轮更像没接顺，靠加大输出只会更僵。"],
                "advice": ["先回应，再补一点自己", "不要整句代写"],
                "avoid": ["不要继续追着同一个点硬问"],
                "topic_directions": ["周末出门走走", "咖啡"],
                "easy_question_types": ["低门槛生活习惯问题"],
                "rescue_flow": ["先接住短回复", "再切生活话题", "最后问轻问题"],
                "profile_hooks_used": ["周末会出门走走", "咖啡"],
            }
        )

        body = render_assistant_guidance(guidance)
        parsed = parse_assistant_guidance(body)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("意愿判断：", body)
        self.assertIn("这轮处理方式：", body)
        self.assertIn("建议按这个顺序来：", body)
        self.assertEqual(parsed["schema_version"], GUIDANCE_SCHEMA_VERSION)
        self.assertEqual(parsed["mutual_intent_assessment"], "communication_problem")
        self.assertEqual(parsed["interaction_mode"], "repair")
        self.assertEqual(parsed["rescue_flow"], ["先接住短回复", "再切生活话题", "最后问轻问题"])
        self.assertEqual(parsed["advice"], ["先回应，再补一点自己", "不要整句代写"])
        self.assertEqual(parsed["reply_suggestions"], ["先回应，再补一点自己", "不要整句代写"])
        self.assertEqual(parsed["profile_hooks_used"], ["周末会出门走走", "咖啡"])
        self.assertNotIn("如果还是接不动：", body)

    def test_normalize_guidance_defaults_to_none_for_out_of_scope_input(self):
        guidance = normalize_assistant_guidance(
            {
                "mutual_intent_assessment": "interest_unclear",
                "interaction_mode": "probe_lightly",
                "current_problem": ["对方回得短，意愿还看不清"],
            }
        )

        self.assertEqual(guidance["schema_version"], GUIDANCE_SCHEMA_VERSION)
        self.assertEqual(guidance["mutual_intent_assessment"], "normal")
        self.assertEqual(guidance["interaction_mode"], "none")
        self.assertEqual(guidance["topic_directions"], [])
        self.assertEqual(guidance["easy_question_types"], [])
        self.assertEqual(guidance["rescue_flow"], [])

    def test_normalize_guidance_filters_direct_send_like_suggestions(self):
        guidance = normalize_assistant_guidance(
            {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["旧话题已经聊干了"],
                "advice": [
                    "你可以自然一点，换个轻松话题，别太用力。",
                    "比如：哈哈那你周末一般会出去走走吗？",
                    "我平时周末会去咖啡店坐坐，你呢？",
                ],
            }
        )

        self.assertEqual(guidance["advice"], ["你可以自然一点，换个轻松话题，别太用力。"])
        self.assertEqual(guidance["reply_suggestions"], ["你可以自然一点，换个轻松话题，别太用力。"])

    def test_generate_assistant_guidance_hides_invalid_json_result(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = "不是 JSON"
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接话？",
                thread_context="bob: 嗯",
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
                profile_hooks=["咖啡"],
            )

        assert guidance is not None
        self.assertEqual(guidance["guidance_source"], "error_hidden")
        self.assertEqual(guidance["mutual_intent_assessment"], "communication_problem")
        self.assertEqual(guidance["interaction_mode"], "repair")
        self.assertNotIn("advice", guidance)

    def test_generate_assistant_guidance_hides_timeout_result(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        fake_module = SimpleNamespace(OpenAI=_FakeTimeoutOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接话？",
                thread_context="bob: 设计吧。",
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
            )

        assert guidance is not None
        self.assertEqual(guidance["guidance_source"], "timeout_hidden")
        self.assertEqual(guidance["mutual_intent_assessment"], "communication_problem")
        self.assertEqual(guidance["interaction_mode"], "repair")

    def test_generate_assistant_guidance_hides_non_timeout_error(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        fake_module = SimpleNamespace(OpenAI=_FakeErrorOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接话？",
                thread_context="bob: 嗯",
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
            )

        assert guidance is not None
        self.assertEqual(guidance["guidance_source"], "error_hidden")
        self.assertEqual(guidance["interaction_mode"], "repair")
        self.assertNotIn("advice", guidance)

    def test_generate_assistant_guidance_hides_when_model_unavailable(self):
        guidance = generate_assistant_guidance(
            user_query="怎么接话？",
            thread_context="bob: 嗯",
            preferred_mutual_intent_assessment="communication_problem",
            preferred_interaction_mode="repair",
        )

        assert guidance is not None
        self.assertEqual(guidance["guidance_source"], "error_hidden")
        self.assertEqual(guidance["mutual_intent_assessment"], "communication_problem")
        self.assertEqual(guidance["interaction_mode"], "repair")

    def test_generate_assistant_guidance_skips_model_for_none_route(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = '{"mutual_intent_assessment":"communication_problem","interaction_mode":"repair"}'
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接？",
                thread_context="bob: 正常继续吧",
                preferred_mutual_intent_assessment="normal",
                preferred_interaction_mode="none",
                online_scope_only=True,
            )

        assert guidance is not None
        self.assertEqual(guidance["mutual_intent_assessment"], "normal")
        self.assertEqual(guidance["interaction_mode"], "none")
        self.assertEqual(_FakeOpenAIClient.instance_count, 0)
        self.assertEqual(_FakeOpenAIClient.create_call_count, 0)

    def test_placeholder_guidance_deprioritizes_generic_profile_hooks(self):
        guidance = build_placeholder_assistant_guidance(
            profile_hooks=["电影", "旅行", "无锡", "咖啡"],
            mutual_intent_assessment="communication_problem",
            interaction_mode="repair",
        )

        self.assertEqual(guidance["topic_directions"][:2], ["无锡", "咖啡"])
        self.assertEqual(guidance["profile_hooks_used"], ["无锡", "咖啡"])
        self.assertNotIn("电影", guidance["topic_directions"])
        self.assertNotIn("旅行", guidance["topic_directions"])

    def test_placeholder_guidance_clears_topics_for_none_mode(self):
        guidance = build_placeholder_assistant_guidance(
            mutual_intent_assessment="normal",
            interaction_mode="none",
            profile_hooks=["无锡", "咖啡"],
            online_scope_only=True,
        )

        self.assertEqual(guidance["mutual_intent_assessment"], "normal")
        self.assertEqual(guidance["interaction_mode"], "none")
        self.assertEqual(guidance["topic_directions"], [])
        self.assertEqual(guidance["profile_hooks_used"], [])
        self.assertIn("顺着当前话题自然往下聊", guidance["advice"][0])

    def test_generate_assistant_guidance_uses_safe_summaries_and_ranked_hooks(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = (
            '{"mutual_intent_assessment":"communication_problem","interaction_mode":"repair",'
            '"current_problem":["旧话题快聊干了"],'
            '"topic_directions":["电影","旅行"],'
            '"advice":["先接住对方上一句，再换到更生活化的话题。"],'
            '"profile_hooks_used":[]}'
        )
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)

        actor_summary = (
            "name：小雨\n"
            "age：29\n"
            "settlement_city：无锡\n"
            "job：互联网运营\n"
            "lifestyle：咖啡、citywalk、运动\n"
            "hobbies：桌游、羽毛球、电影\n"
            "notes：周末会找家店坐坐慢慢聊。"
        )
        counterpart_summary = (
            "name：阿杰\n"
            "age：30\n"
            "settlement_city：无锡\n"
            "job：工程师\n"
            "lifestyle：咖啡、早起\n"
            "hobbies：桌游、旅行\n"
            "notes：偏慢热。"
        )

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="这轮怎么接？",
                thread_context="bob: 嗯",
                actor_profile_summary=actor_summary,
                counterpart_profile_summary=counterpart_summary,
                profile_hooks=["电影", "旅行", "无锡", "咖啡", "桌游", "羽毛球", "运动"],
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
            )

        assert guidance is not None
        self.assertEqual(guidance["topic_directions"][:3], ["无锡", "咖啡", "桌游"])
        self.assertEqual(guidance["profile_hooks_used"], ["无锡", "咖啡", "桌游"])

        create_kwargs = _FakeOpenAIClient.last_create_kwargs or {}
        messages = create_kwargs.get("messages") or []
        self.assertEqual(len(messages), 2)
        self.assertEqual(create_kwargs.get("max_tokens"), 120)
        prompt = messages[1]["content"]
        self.assertIn("我方画像:", prompt)
        self.assertIn("对方画像:", prompt)
        self.assertIn("优先钩子: 无锡, 咖啡, 桌游", prompt)
        self.assertNotIn('"problem_tags"', prompt)
        self.assertNotIn('"strategy_tags"', prompt)
        self.assertNotIn('"easy_question_types"', prompt)
        self.assertNotIn('"rescue_flow"', prompt)
        self.assertNotIn('"graceful_exit_plan"', prompt)
        self.assertNotIn("通用低门槛兜底", prompt)
        self.assertNotIn("name：小雨", prompt)
        self.assertNotIn("age：29", prompt)
        self.assertNotIn("优先画像钩子-双方交集", prompt)
        self.assertNotIn("电影, 旅行, 运动", prompt)

    def test_generate_assistant_guidance_reuses_cached_result_for_identical_input(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = (
            '{"mutual_intent_assessment":"communication_problem","interaction_mode":"repair",'
            '"current_problem":["旧话题有点接不下去"],'
            '"advice":["先接住，再轻一点换题。"]}'
        )
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            first = generate_assistant_guidance(
                user_query="这轮怎么接？",
                thread_context="bob: 嗯",
                actor_profile_summary="job：运营",
                counterpart_profile_summary="job：工程师",
                profile_hooks=["咖啡", "无锡"],
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
            )
            second = generate_assistant_guidance(
                user_query="这轮怎么接？",
                thread_context="bob: 嗯",
                actor_profile_summary="job：运营",
                counterpart_profile_summary="job：工程师",
                profile_hooks=["咖啡", "无锡"],
                preferred_mutual_intent_assessment="communication_problem",
                preferred_interaction_mode="repair",
            )

        self.assertEqual(_FakeOpenAIClient.instance_count, 1)
        self.assertEqual(_FakeOpenAIClient.create_call_count, 1)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
