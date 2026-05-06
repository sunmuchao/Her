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

    def __init__(self, **_kwargs):
        self.chat = self
        self.completions = self

    def create(self, **_kwargs):
        return _FakeOpenAIResponse(self.response_content)


class AssistantLLMTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("HER_CHAT_ASSISTANT_BASE_URL", None)
        os.environ.pop("OPENAI_BASE_URL", None)

    def test_guidance_render_and_parse_round_trip(self):
        guidance = normalize_assistant_guidance(
            {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["对方上一句太短，原话题快聊干了"],
                "why_not_to_push": [],
                "low_pressure_options": [],
                "advice": ["先回应，再补一点自己", "不要整句代写"],
                "avoid": ["不要继续追着同一个点硬问"],
                "topic_directions": ["周末出门走走", "咖啡"],
                "easy_question_types": ["低门槛生活习惯问题"],
                "rescue_flow": ["先接住短回复", "再切生活话题", "最后问轻问题"],
                "graceful_exit_plan": ["如果对方还是很冷，就先轻轻收住"],
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
        self.assertIn("如果还是接不动：", body)
        self.assertEqual(parsed["schema_version"], GUIDANCE_SCHEMA_VERSION)
        self.assertEqual(parsed["mutual_intent_assessment"], "communication_problem")
        self.assertEqual(parsed["interaction_mode"], "repair")
        self.assertEqual(parsed["rescue_flow"], ["先接住短回复", "再切生活话题", "最后问轻问题"])
        self.assertEqual(parsed["graceful_exit_plan"], ["如果对方还是很冷，就先轻轻收住"])
        self.assertEqual(parsed["advice"], ["先回应，再补一点自己", "不要整句代写"])
        self.assertEqual(parsed["reply_suggestions"], ["先回应，再补一点自己", "不要整句代写"])
        self.assertEqual(parsed["profile_hooks_used"], ["周末会出门走走", "咖啡"])

    def test_normalize_guidance_adds_defaults_for_probe_lightly(self):
        guidance = normalize_assistant_guidance(
            {
                "mutual_intent_assessment": "interest_unclear",
                "interaction_mode": "probe_lightly",
                "current_problem": ["对方回得短，意愿还看不清"],
                "problem_tags": ["closed_reply"],
            }
        )

        self.assertEqual(guidance["schema_version"], GUIDANCE_SCHEMA_VERSION)
        self.assertEqual(guidance["interaction_mode"], "probe_lightly")
        self.assertTrue(guidance["why_not_to_push"])
        self.assertTrue(guidance["low_pressure_options"])
        self.assertTrue(guidance["avoid"])
        self.assertTrue(guidance["advice"])
        self.assertEqual(guidance["advice"], guidance["reply_suggestions"])

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

    def test_generate_assistant_guidance_falls_back_on_invalid_json(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = "不是 JSON"
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)
        expected = build_placeholder_assistant_guidance(profile_hooks=["咖啡"])

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接话？",
                thread_context="bob: 嗯",
                profile_hooks=["咖啡"],
            )

        self.assertEqual(guidance, expected)

    def test_generate_assistant_guidance_normalizes_model_schema_gaps(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        _FakeOpenAIClient.response_content = (
            '{"mutual_intent_assessment":"interest_low","interaction_mode":"hold",'
            '"current_problem":["对方回得很冷"],'
            '"problem_tags":["low_energy"],'
            '"advice":["我觉得我们改天再聊吧。"]}'
        )
        fake_module = SimpleNamespace(OpenAI=_FakeOpenAIClient)

        with patch.dict(sys.modules, {"openai": fake_module}):
            guidance = generate_assistant_guidance(
                user_query="怎么接？",
                thread_context="bob: 哦",
            )

        assert guidance is not None
        self.assertEqual(guidance["interaction_mode"], "hold")
        self.assertTrue(guidance["why_not_to_push"])
        self.assertTrue(guidance["avoid"])
        self.assertNotIn("我觉得我们改天再聊吧。", guidance["advice"])
        self.assertIn("先把节奏收住，不要继续追着聊。", guidance["advice"])


if __name__ == "__main__":
    unittest.main()
