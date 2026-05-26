"""Unit tests for reciprocal preference enrichment."""

from __future__ import annotations

import unittest

from match_domain.reciprocal_preferences import enrich_record_for_reciprocal, merge_persona_into_profile_record


class ReciprocalPreferenceTests(unittest.TestCase):
    def test_enrich_maps_target_fields_to_legacy_profile_keys(self) -> None:
        enriched = enrich_record_for_reciprocal({"target_age_min": 25, "target_cities": "上海,杭州"})
        self.assertEqual(enriched["preferred_age_min"], 25)
        self.assertEqual(enriched["preferred_cities"], "上海,杭州")

    def test_merge_persona_into_profile_record(self) -> None:
        merged = merge_persona_into_profile_record(
            {"id": 1, "age": 30, "city": "上海"},
            {"target_age_max": 35, "must_have_tags": "成熟稳重"},
        )
        self.assertEqual(merged["preferred_age_max"], 35)
        self.assertIn("matcher_preferences", merged)


if __name__ == "__main__":
    unittest.main()
