import pathlib
import os
import types
import unittest
from unittest import mock


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "persona_memory_lib.py"
)
persona_memory_lib = types.ModuleType("persona_memory_lib")
persona_memory_lib.__file__ = str(SCRIPT_PATH)
exec(compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"), persona_memory_lib.__dict__)


class PersonaMemoryTests(unittest.TestCase):
    def test_resolve_mysql_source_requires_explicit_config(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                persona_memory_lib.resolve_mysql_source()

    def test_resolve_mysql_source_reads_persona_env(self):
        with mock.patch.dict(
            os.environ,
            {"PERSONA_MEMORY_MYSQL_SOURCE": "mysql://demo@127.0.0.1:3306/her?table=profiles"},
            clear=True,
        ):
            self.assertEqual(
                persona_memory_lib.resolve_mysql_source(),
                "mysql://demo@127.0.0.1:3306/her?table=profiles",
            )

    def test_normalize_patch_supports_lists_and_ints(self):
        patch = persona_memory_lib.normalize_patch(
            {
                "self_age": "28岁",
                "self_has_children": "否",
                "must_have_tags": ["情绪稳定", "沟通", "情绪稳定"],
                "target_cities": "无锡,苏州",
            }
        )
        self.assertEqual(patch["self_age"], 28)
        self.assertEqual(patch["self_has_children"], 0)
        self.assertEqual(patch["must_have_tags"], "情绪稳定,沟通")
        self.assertEqual(patch["target_cities"], "无锡,苏州")

    def test_merge_explicit_overwrites_hard_fields(self):
        existing = {"self_city": "上海", "must_have_tags": "情绪稳定"}
        patch = {"self_city": "无锡", "must_have_tags": "情绪稳定,消费观正常"}
        merged, field_results = persona_memory_lib.merge_persona(existing, patch, "explicit")
        self.assertEqual(merged["self_city"], "无锡")
        self.assertEqual(merged["must_have_tags"], "情绪稳定,消费观正常")
        self.assertEqual(field_results[0]["action_type"], "update")

    def test_strong_inference_does_not_override_explicit_hard_field(self):
        existing = {"self_city": "无锡", "preferred_traits": "稳定"}
        patch = {"self_city": "上海", "preferred_traits": "沟通顺畅"}
        merged, field_results = persona_memory_lib.merge_persona(existing, patch, "strong_inference")
        self.assertEqual(merged["self_city"], "无锡")
        self.assertEqual(merged["preferred_traits"], "稳定,沟通顺畅")
        city_result = [item for item in field_results if item["field_name"] == "self_city"][0]
        self.assertFalse(city_result["applied_to_persona"])
        self.assertEqual(city_result["note"], "explicit_only_scalar")

    def test_build_matcher_payload_normalizes_negative_terms(self):
        persona = {
            "must_have_tags": "情绪稳定,愿意沟通,消费观正常",
            "must_not_have_tags": "绿茶,拜金,冷暴力,暧昧不清",
            "target_cities": "无锡",
            "target_accept_long_distance": "不接受",
        }
        payload = persona_memory_lib.build_matcher_payload(persona)
        risks = payload["matcher_risks_json"]
        prefs = payload["matcher_preferences_json"]
        self.assertIn("boundary_clarity_risk", risks)
        self.assertIn("spending_values_mismatch_risk", risks)
        self.assertIn("communication_shutdown_risk", risks)
        self.assertIn("emotional_stability_priority", prefs)
        self.assertIn("communication_directness_preference", prefs)

    def test_build_public_profile_hides_raw_negative_labels(self):
        persona = {
            "self_city": "无锡",
            "self_relationship_goal": "结婚",
            "self_smoking": "否",
            "target_accept_long_distance": "不接受",
            "must_have_tags": "情绪稳定,愿意沟通,消费观正常",
            "must_not_have_tags": "绿茶,拜金,冷暴力,暧昧不清",
        }
        payload = persona_memory_lib.build_public_profile(persona)
        combined = " ".join(value for value in payload.values() if value)
        self.assertNotIn("绿茶", combined)
        self.assertNotIn("拜金", combined)
        self.assertIn("关系边界", combined)
        self.assertIn("消费观", combined)

    def test_build_profile_payload_maps_acceptance_fields(self):
        persona = {
            "user_key": "demo-user",
            "display_name": "Demo",
            "self_gender": "男",
            "self_age": 28,
            "self_city": "无锡",
            "self_income_wan": 40,
            "self_relationship_goal": "结婚导向",
            "persona_summary_internal": "慢热但反馈稳定，认真推进关系。",
            "preference_summary_internal": "看重沟通效率，也看重情绪稳定。",
            "target_age_min": 24,
            "target_age_max": 30,
            "target_cities": "无锡",
            "target_accept_long_distance": "不接受",
            "target_accept_partner_children": "不接受",
            "target_marital_statuses": "未婚",
            "must_have_tags": "情绪稳定,消费观正常",
        }
        payload = persona_memory_lib.build_profile_payload(persona)
        self.assertEqual(payload["gender"], "男")
        self.assertEqual(payload["preferred_age_min"], 24)
        self.assertEqual(payload["preferred_age_max"], 30)
        self.assertEqual(payload["preferred_cities"], "无锡")
        self.assertEqual(payload["accept_long_distance"], "不接受")
        self.assertEqual(payload["accept_partner_children"], "不接受")
        self.assertEqual(payload["accept_marital_status"], "未婚")
        self.assertEqual(payload["income_range"], "36-45万/年")
        self.assertEqual(payload["personality"], "慢热但反馈稳定，认真推进关系。")
        self.assertEqual(payload["values"], "看重沟通效率，也看重情绪稳定。")
        self.assertIn("matcher_traits_json", payload)
        self.assertIn("public_personality", payload)

    def test_build_profile_payload_preserves_existing_internal_text_over_public_fallback(self):
        persona = {
            "user_key": "demo-user",
            "display_name": "Demo",
            "self_city": "无锡",
            "self_relationship_goal": "认真恋爱",
            "must_have_tags": "情绪稳定",
        }
        existing_profile = {
            "personality": "真实聊天里很会接话，也会主动推进。",
            "values": "看重沟通和现实执行感。",
            "notes": "明确不接受长期拉扯。",
        }
        payload = persona_memory_lib.build_profile_payload(persona, existing_profile=existing_profile)
        self.assertEqual(payload["personality"], existing_profile["personality"])
        self.assertEqual(payload["values"], existing_profile["values"])
        self.assertEqual(payload["notes"], existing_profile["notes"])
        self.assertNotEqual(payload["personality"], payload["public_personality"])

    def test_mark_profile_sync_results_only_marks_profile_affecting_fields(self):
        field_results = [
            {"field_name": "self_city", "applied_to_persona": True},
            {"field_name": "profile_id", "applied_to_persona": True},
            {"field_name": "self_age", "applied_to_persona": False},
        ]
        persona_memory_lib.mark_profile_sync_results(field_results, synced_profile=True)
        self.assertTrue(field_results[0]["applied_to_profile"])
        self.assertFalse(field_results[1]["applied_to_profile"])
        self.assertFalse(field_results[2]["applied_to_profile"])


if __name__ == "__main__":
    unittest.main()
