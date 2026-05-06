import pathlib
import sys
import unittest


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.mode_router import fast_mode_route  # noqa: E402


def _msg(author_id: str, body: str) -> dict[str, str]:
    return {
        "author_id": author_id,
        "body": body,
        "visibility": "dyadic",
    }


class ModeRouterTests(unittest.TestCase):
    def test_fast_mode_route_bootstrap(self):
        out = fast_mode_route([])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["problem_tags"], [])

    def test_fast_mode_route_probe_lightly_on_cold_reply(self):
        out = fast_mode_route([_msg("a", "嗯")])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["decision_source"], "heuristic")
        self.assertEqual(out["interaction_mode"], "probe_lightly")
        self.assertEqual(out["mutual_intent_assessment"], "interest_unclear")
        self.assertIn("closed_reply", out["problem_tags"])

    def test_fast_mode_route_repair_after_prior_mutual_engagement(self):
        messages = [
            _msg("a", "我周末一般会打羽毛球，你平时怎么放松？"),
            _msg("b", "我一般会出去走走，有时找家店坐会儿喝咖啡。"),
            _msg("a", "那还挺舒服的，我最近也会这样慢一点。"),
            _msg("b", "嗯"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "repair")
        self.assertEqual(out["mutual_intent_assessment"], "communication_problem")
        self.assertIn("missed_connection", out["problem_tags"])

    def test_fast_mode_route_hold_on_repeated_low_interest(self):
        messages = [
            _msg("a", "你好，我周末一般会出去走走。"),
            _msg("b", "嗯"),
            _msg("a", "我一般就随便走走，你呢？"),
            _msg("b", "都行"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "hold")
        self.assertEqual(out["mutual_intent_assessment"], "interest_low")
        self.assertIn("disengaged", out["problem_tags"])

    def test_fast_mode_route_hold_on_boundary_risk(self):
        out = fast_mode_route([_msg("a", "你收入大概多少呀？")])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "hold")
        self.assertEqual(out["mutual_intent_assessment"], "boundary_risk")
        self.assertEqual(out["problem_tags"], ["boundary_risk", "sensitive_topic"])


if __name__ == "__main__":
    unittest.main()
