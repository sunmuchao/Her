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

    def test_fast_mode_route_ignores_single_cold_reply_without_clear_repair_context(self):
        out = fast_mode_route([_msg("a", "嗯")])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["decision_source"], "heuristic_scope_filter")
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")
        self.assertEqual(out["engagement_level"], "low")
        self.assertEqual(out["warmth_level"], "cold")
        self.assertEqual(out["irritation_level"], "mild")
        self.assertEqual(out["problem_tags"], [])

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

    def test_fast_mode_route_ignores_repeated_low_interest(self):
        messages = [
            _msg("a", "你好，我周末一般会出去走走。"),
            _msg("b", "嗯"),
            _msg("a", "我一般就随便走走，你呢？"),
            _msg("b", "都行"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")
        self.assertEqual(out["problem_tags"], [])

    def test_fast_mode_route_ignores_boundary_risk(self):
        out = fast_mode_route([_msg("a", "你收入大概多少呀？")])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")
        self.assertEqual(out["irritation_level"], "medium")
        self.assertEqual(out["state_trend"], "worsening")
        self.assertEqual(out["problem_tags"], [])

    def test_fast_mode_route_repair_on_cold_prefix_question_after_cold_opening(self):
        messages = [
            _msg("a", "你好"),
            _msg("b", "嗯。你周末都干嘛"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "repair")
        self.assertEqual(out["mutual_intent_assessment"], "communication_problem")
        self.assertIn("awkward_transition", out["problem_tags"])

    def test_fast_mode_route_ignores_cold_prefix_question_without_awkward_context(self):
        messages = [
            _msg("a", "我最近工作节奏有点满，不过周末会找个公园走走。"),
            _msg("b", "嗯。你平时怎么放松"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")

    def test_fast_mode_route_repair_on_low_energy_reply_after_awkward_question(self):
        messages = [
            _msg("a", "你好"),
            _msg("b", "嗯。你周末都干嘛"),
            _msg("a", "睡觉。"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "repair")
        self.assertEqual(out["mutual_intent_assessment"], "communication_problem")
        self.assertIn("missed_connection", out["problem_tags"])

    def test_fast_mode_route_does_not_clear_continue_after_cold_context(self):
        messages = [
            _msg("a", "睡觉。"),
            _msg("b", "挺能睡的"),
            _msg("a", "平时上班累，周末不睡觉还能干嘛。你呢？"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "repair")
        self.assertNotEqual(out["decision_source"], "heuristic_clear_continue")

    def test_fast_mode_route_ignores_defensive_boundary_question(self):
        messages = [
            _msg("b", "还行，我平时比较随性一点。你呢？"),
            _msg("a", "随性。你照片看着挺瘦，是本人吧？别差距太大。"),
            _msg("b", "是本人。怎么，怕见光死？"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")
        self.assertEqual(out["warmth_level"], "sharp")
        self.assertEqual(out["irritation_level"], "high")
        self.assertEqual(out["problem_tags"], [])

    def test_fast_mode_route_ignores_recent_risk_carryover(self):
        messages = [
            _msg("a", "随性。你照片看着挺瘦，是本人吧？别差距太大。"),
            _msg("b", "是本人。怎么，怕见光死？"),
            _msg("a", "朋友都劝我别抱太大希望，说网上见光死的多。不想浪费时间。"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")

    def test_fast_mode_route_ignores_conflict_tail(self):
        messages = [
            _msg("b", "哦。那挺省事的。"),
            _msg("a", "那行。既然省事，这周末有空出来见见？"),
            _msg("b", "你理解能力挺别致的。我说省事是让你不用费劲了，不是答应见面。"),
        ]
        out = fast_mode_route(messages)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["interaction_mode"], "none")
        self.assertEqual(out["mutual_intent_assessment"], "normal")
        self.assertNotEqual(out["decision_source"], "heuristic_clear_continue")


if __name__ == "__main__":
    unittest.main()
