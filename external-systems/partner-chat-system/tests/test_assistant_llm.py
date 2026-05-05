import pathlib
import sys
import unittest


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.assistant_llm import normalize_assistant_guidance, parse_assistant_guidance, render_assistant_guidance  # noqa: E402


class AssistantLLMTests(unittest.TestCase):
    def test_guidance_render_and_parse_round_trip(self):
        guidance = normalize_assistant_guidance(
            {
                "current_problem": ["对方上一句太短，原话题快聊干了"],
                "avoid": ["不要继续追着同一个点硬问"],
                "topic_directions": ["周末出门走走", "咖啡"],
                "easy_question_types": ["低门槛生活习惯问题"],
                "rescue_flow": ["先接住短回复", "再切生活话题", "最后问轻问题"],
                "graceful_exit_plan": ["如果对方还是很冷，就先轻轻收住"],
                "reply_suggestions": ["先回应，再补一点自己", "不要整句代写"],
                "profile_hooks_used": ["周末会出门走走", "咖啡"],
            }
        )

        body = render_assistant_guidance(guidance)
        parsed = parse_assistant_guidance(body)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("建议按这个顺序来：", body)
        self.assertIn("如果还是接不动：", body)
        self.assertEqual(parsed["rescue_flow"], ["先接住短回复", "再切生活话题", "最后问轻问题"])
        self.assertEqual(parsed["graceful_exit_plan"], ["如果对方还是很冷，就先轻轻收住"])
        self.assertEqual(parsed["profile_hooks_used"], ["周末会出门走走", "咖啡"])


if __name__ == "__main__":
    unittest.main()
