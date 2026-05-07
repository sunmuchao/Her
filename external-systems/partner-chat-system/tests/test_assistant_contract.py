import pathlib
import sys
import unittest


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.assistant_contract import (  # noqa: E402
    ASSISTANT_GUIDANCE_FIELDS,
    FOLLOW_LEVELS,
    FOLLOW_LEVEL_NOT_APPLICABLE,
    GUIDANCE_SCHEMA_VERSION,
    INTERACTION_MODES,
    MUTUAL_INTENT_ASSESSMENTS,
    ROLEPLAY_TURN_EVALUATION_FIELDS,
    SHARED_TURN_EVALUATION_FIELDS,
    TURN_EVALUATION_SCHEMA_VERSION,
    default_interaction_mode,
    is_rescue_interaction_mode,
    normalize_interaction_mode,
    normalize_mutual_intent_assessment,
)


class AssistantContractTests(unittest.TestCase):
    def test_shared_contract_constants_are_repair_only(self):
        self.assertEqual(GUIDANCE_SCHEMA_VERSION, 2)
        self.assertEqual(TURN_EVALUATION_SCHEMA_VERSION, 1)
        self.assertEqual(INTERACTION_MODES, ("repair", "none"))
        self.assertEqual(MUTUAL_INTENT_ASSESSMENTS, ("communication_problem", "normal"))
        self.assertEqual(FOLLOW_LEVELS, ("none", "partial", "strong"))
        self.assertEqual(FOLLOW_LEVEL_NOT_APPLICABLE, "not_applicable")
        self.assertIn("interaction_mode", ASSISTANT_GUIDANCE_FIELDS)
        self.assertIn("advice", ASSISTANT_GUIDANCE_FIELDS)
        self.assertNotIn("risk_axis", ASSISTANT_GUIDANCE_FIELDS)
        self.assertNotIn("hold_subtype", ASSISTANT_GUIDANCE_FIELDS)
        self.assertNotIn("graceful_exit_score", SHARED_TURN_EVALUATION_FIELDS)
        self.assertIn("assistant_guidance", ROLEPLAY_TURN_EVALUATION_FIELDS)

    def test_mutual_intent_normalization_collapses_old_categories(self):
        self.assertEqual(
            normalize_mutual_intent_assessment("双方都还想继续聊，只是这轮没接好"),
            "communication_problem",
        )
        self.assertEqual(normalize_mutual_intent_assessment("有点冷场，像没接住"), "communication_problem")
        self.assertEqual(normalize_mutual_intent_assessment("interest_unclear"), "normal")
        self.assertEqual(normalize_mutual_intent_assessment("boundary_risk"), "normal")
        self.assertEqual(normalize_mutual_intent_assessment("先试探一下"), "normal")

    def test_interaction_mode_normalization_collapses_old_modes(self):
        self.assertEqual(
            normalize_interaction_mode(
                "",
                mutual_intent_assessment="communication_problem",
            ),
            "repair",
        )
        self.assertEqual(
            normalize_interaction_mode(
                "",
                mutual_intent_assessment="communication_problem",
                need_rescue=False,
            ),
            "none",
        )
        self.assertEqual(
            normalize_interaction_mode(
                "先收住，别硬推",
                mutual_intent_assessment="normal",
            ),
            "none",
        )
        self.assertEqual(default_interaction_mode("normal"), "none")
        self.assertTrue(is_rescue_interaction_mode("repair"))
        self.assertFalse(is_rescue_interaction_mode("none"))


if __name__ == "__main__":
    unittest.main()
