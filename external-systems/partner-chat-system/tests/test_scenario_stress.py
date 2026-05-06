import pathlib
import random
import sys
import unittest


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.assistant_contract import INTERACTION_MODES, MUTUAL_INTENT_ASSESSMENTS  # noqa: E402
from chat_system.scenario_stress import STRESS_BEATS, pick_stress_beat, stress_log_entry  # noqa: E402


class ScenarioStressTests(unittest.TestCase):
    def test_all_stress_beats_include_expected_metadata(self):
        self.assertTrue(STRESS_BEATS)
        for beat in STRESS_BEATS:
            self.assertGreaterEqual(beat.severity, 1)
            self.assertTrue(beat.expected_problem_tags)
            self.assertTrue(beat.suggested_strategy_tags)
            self.assertIn(beat.expected_mutual_intent_assessment, MUTUAL_INTENT_ASSESSMENTS)
            self.assertIn(beat.expected_interaction_mode, INTERACTION_MODES)
            self.assertGreaterEqual(beat.expected_need_rescue_after_turns, 0)

    def test_stress_log_entry_exports_new_expected_fields(self):
        beat = STRESS_BEATS[0]
        entry = stress_log_entry(3, "user-a", beat)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["beat_id"], beat.id)
        self.assertEqual(
            entry["expected_mutual_intent_assessment"],
            beat.expected_mutual_intent_assessment,
        )
        self.assertEqual(entry["expected_interaction_mode"], beat.expected_interaction_mode)
        self.assertEqual(entry["expected_problem_tags"], list(beat.expected_problem_tags))
        self.assertEqual(entry["suggested_strategy_tags"], list(beat.suggested_strategy_tags))

    def test_rotate_mode_keeps_expected_metadata(self):
        rng = random.Random(7)
        beat = pick_stress_beat(turn_index=0, mode="rotate", rng=rng)
        self.assertIsNotNone(beat)
        assert beat is not None
        self.assertIn(beat.expected_mutual_intent_assessment, MUTUAL_INTENT_ASSESSMENTS)
        self.assertIn(beat.expected_interaction_mode, INTERACTION_MODES)


if __name__ == "__main__":
    unittest.main()
