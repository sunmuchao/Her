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
    def test_shared_contract_constants_cover_core_terms(self):
        self.assertEqual(GUIDANCE_SCHEMA_VERSION, 2)
        self.assertEqual(TURN_EVALUATION_SCHEMA_VERSION, 1)
        self.assertEqual(INTERACTION_MODES, ("repair", "probe_lightly", "hold", "none"))
        self.assertIn("communication_problem", MUTUAL_INTENT_ASSESSMENTS)
        self.assertEqual(FOLLOW_LEVELS, ("none", "partial", "strong"))
        self.assertEqual(FOLLOW_LEVEL_NOT_APPLICABLE, "not_applicable")
        self.assertIn("interaction_mode", ASSISTANT_GUIDANCE_FIELDS)
        self.assertIn("advice", ASSISTANT_GUIDANCE_FIELDS)
        self.assertIn("reply_suggestions", ASSISTANT_GUIDANCE_FIELDS)
        self.assertIn("turn_index", SHARED_TURN_EVALUATION_FIELDS)
        self.assertIn("graceful_exit_score", SHARED_TURN_EVALUATION_FIELDS)
        self.assertIn("assistant_guidance", ROLEPLAY_TURN_EVALUATION_FIELDS)

    def test_mutual_intent_normalization_uses_shared_rules(self):
        self.assertEqual(
            normalize_mutual_intent_assessment("双方都还想继续聊，只是这轮没接好"),
            "communication_problem",
        )
        self.assertEqual(
            normalize_mutual_intent_assessment("这轮已经碰到边界和压力"),
            "boundary_risk",
        )
        self.assertEqual(normalize_mutual_intent_assessment("先试探一下"), "interest_unclear")

    def test_interaction_mode_normalization_uses_shared_rules(self):
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
                mutual_intent_assessment="interest_low",
            ),
            "hold",
        )
        self.assertEqual(default_interaction_mode("interest_unclear"), "probe_lightly")
        self.assertTrue(is_rescue_interaction_mode("repair"))
        self.assertFalse(is_rescue_interaction_mode("hold"))


if __name__ == "__main__":
    unittest.main()
