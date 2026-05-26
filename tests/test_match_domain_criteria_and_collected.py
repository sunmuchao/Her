from __future__ import annotations

import unittest

from match_domain.collected_profile import (
    extract_collected_statements,
    extract_profile_facts,
    filter_explicit_patch,
)
from match_domain.criteria_compiler import compile_effective_criteria
from match_domain.criteria_snapshots import get_criteria_snapshot_store, save_compiled_snapshot
from persona_memory_sync import persona_memory_lib


class MatchDomainCriteriaTests(unittest.TestCase):
    def test_compile_uses_collected_persona_only(self):
        compiled = compile_effective_criteria(
            scene="discovery_search",
            profile_row={"gender": "男", "age": 30, "city": "上海"},
            persona_row={
                "target_age_min": 25,
                "target_age_max": 32,
                "target_cities": "上海",
                "must_have_tags": "成熟稳重",
            },
            overrides={"gender": "女"},
        )
        self.assertEqual(compiled.criteria.get("age_min"), 25)
        self.assertEqual(compiled.criteria.get("age_max"), 32)
        self.assertEqual(compiled.criteria.get("gender"), "女")
        self.assertIn("age_min", compiled.source_map)

    def test_extract_profile_facts_filters_preference_columns(self):
        facts = extract_profile_facts(
            {
                "age": 28,
                "city": "上海",
                "preferred_age_min": 25,
                "matcher_preferences_json": '{"must_have_tags":["x"]}',
            }
        )
        self.assertEqual(facts.get("age"), 28)
        self.assertNotIn("preferred_age_min", facts)
        self.assertNotIn("matcher_preferences_json", facts)

    def test_extract_collected_statements(self):
        collected = extract_collected_statements(
            {
                "target_age_min": 27,
                "persona_summary_internal": "推断摘要",
            }
        )
        self.assertEqual(collected.get("target_age_min"), 27)
        self.assertNotIn("persona_summary_internal", collected)

    def test_filter_explicit_patch_rejects_inference(self):
        self.assertEqual(
            filter_explicit_patch({"target_age_min": 30}, "strong_inference"),
            {},
        )

    def test_save_compiled_snapshot(self):
        store = get_criteria_snapshot_store()
        before = len(store._rows)
        saved = save_compiled_snapshot(
            {
                "criteria_hash": "abc",
                "criteria": {"age_min": 25},
                "source_map": {"age_min": {"source": "explicit_statement"}},
            },
            scene="discovery_search",
            profile_id=1001,
            recommendation_id=42,
        )
        self.assertEqual(len(store._rows), before + 1)
        self.assertEqual(saved["snapshot_id"], store._rows[-1].snapshot_id)


class PersonaInferencePersistenceTests(unittest.TestCase):
    def test_merge_persona_does_not_persist_strong_inference(self):
        merged, results = persona_memory_lib.merge_persona(
            {"target_age_min": 28},
            {"target_age_min": 30, "preferred_traits": "成熟稳重"},
            "strong_inference",
        )
        self.assertEqual(merged.get("target_age_min"), 28)
        self.assertTrue(all(not item["applied_to_persona"] for item in results))
        self.assertTrue(all(item["note"] == "inference_not_persisted" for item in results))

    def test_merge_persona_persists_explicit(self):
        merged, results = persona_memory_lib.merge_persona(
            {},
            {"target_age_min": 30, "target_age_max": 35},
            "explicit",
        )
        self.assertEqual(merged.get("target_age_min"), 30)
        self.assertEqual(merged.get("target_age_max"), 35)
        self.assertTrue(all(item["applied_to_persona"] for item in results))


if __name__ == "__main__":
    unittest.main()
