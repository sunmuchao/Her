"""Tests for field registry and search self_profile sanitization."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from match_domain.criteria_compiler import build_discovery_search_request, build_effective_search_request
from match_domain.field_registry import FIELD_REGISTRY, registry_entry
from match_domain.search_self_profile import strip_mixed_self_profile_fields


class FieldRegistryTests(unittest.TestCase):
    def test_registry_covers_profile_and_collected_fields(self) -> None:
        self.assertIsNotNone(registry_entry("age"))
        self.assertIsNotNone(registry_entry("target_cities"))
        inference = registry_entry("persona_summary_internal")
        assert inference is not None
        self.assertEqual(inference.target_layer, "P2")

    def test_registry_entry_lookup(self) -> None:
        entry = registry_entry("target_age_min")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.target_layer, "P1")
        self.assertIn("explicit_statement", entry.allowed_write_sources)


class SearchSelfProfileSanitizeTests(unittest.TestCase):
    def test_strip_mixed_profile_and_persona_keys(self) -> None:
        cleaned, stripped = strip_mixed_self_profile_fields(
            {
                "age": 30,
                "city": "上海",
                "preferred_age_min": 25,
                "target_cities": "上海",
                "matcher_preferences_json": "{}",
            }
        )
        self.assertEqual(cleaned, {"age": 30, "city": "上海"})
        self.assertEqual(
            set(stripped),
            {"preferred_age_min", "target_cities", "matcher_preferences_json"},
        )


class CrossPathCompileConsistencyTests(unittest.TestCase):
    def test_discovery_and_recommendation_share_collected_criteria(self) -> None:
        profile_row = {"gender": "男", "age": 30, "city": "上海"}
        persona_row = {"target_age_min": 25, "target_age_max": 32, "target_cities": "上海"}
        subscription = {
            "source": "mysql://test/her",
            "self_id": 1001,
            "criteria_json": "{}",
            "self_profile_json": "{}",
        }

        discovery = build_discovery_search_request(
            source="mysql://test/her",
            profile_row=profile_row,
            persona_row=persona_row,
            criteria_overrides={},
            self_id=1001,
            limit=10,
        )
        recommendation = build_effective_search_request(
            subscription,
            profile_row=profile_row,
            persona_profile=persona_row,
        )

        self.assertEqual(
            discovery["criteria"].get("age_min"),
            recommendation["criteria"].get("age_min"),
        )
        self.assertEqual(
            discovery["criteria"].get("age_max"),
            recommendation["criteria"].get("age_max"),
        )
        self.assertEqual(
            discovery["criteria"].get("cities"),
            recommendation["criteria"].get("cities"),
        )


class GatewaySearchPrepareTests(unittest.TestCase):
    @patch("match_domain.search_self_profile.get_profile")
    @patch("match_domain.search_self_profile.load_persona_by_profile_id")
    def test_prepare_gateway_search_body_strips_and_compiles(
        self,
        load_persona_mock: MagicMock,
        get_profile_mock: MagicMock,
    ) -> None:
        from match_domain.search_self_profile import prepare_gateway_search_body

        get_profile_mock.return_value = {"gender": "男", "age": 30, "city": "上海"}
        load_persona_mock.return_value = {"target_age_min": 26, "target_age_max": 34}

        prepared = prepare_gateway_search_body(
            {
                "source": "mysql://test/her",
                "self_id": 42,
                "self_profile": {"preferred_age_min": 25, "age": 30},
                "criteria": {},
            },
            profile_source_dsn="mysql://test/her",
            profile_table_name="profiles",
        )

        self.assertIn("preferred_age_min", prepared["deprecation"]["self_profile_fields_removed"])
        self.assertEqual(prepared["search_kwargs"]["criteria"].get("age_min"), 26)
        self.assertEqual(prepared["search_kwargs"]["self_profile"].get("age"), 30)


if __name__ == "__main__":
    unittest.main()
