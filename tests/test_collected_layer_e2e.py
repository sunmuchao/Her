"""E2E-style tests for collected profile layer cleanup (§13.1.2)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from match_domain.criteria_compiler import build_discovery_search_request, build_effective_search_request
from match_domain.deprecated_profile_columns import DEPRECATED_PROFILE_COLUMNS
from match_domain.reciprocal_preferences import enrich_record_for_reciprocal
from match_domain.search_self_profile import prepare_gateway_search_body
from partner_search.search_reciprocal import SearchReciprocalRuntime, evaluate_reciprocal_compatibility


class CollectedLayerE2ETests(unittest.TestCase):
    def test_gateway_search_compile_matches_discovery_refresh(self) -> None:
        profile_row = {"gender": "男", "age": 30, "city": "上海"}
        persona_row = {"target_age_min": 26, "target_age_max": 34, "target_cities": "上海"}

        with patch("match_domain.search_self_profile.get_profile", return_value=profile_row), patch(
            "match_domain.search_self_profile.load_persona_by_profile_id",
            return_value=persona_row,
        ):
            prepared = prepare_gateway_search_body(
                {
                    "source": "mysql://test/her",
                    "self_id": 1001,
                    "criteria": {},
                },
                profile_source_dsn="mysql://test/her",
                profile_table_name="profiles",
            )

        discovery = build_discovery_search_request(
            source="mysql://test/her",
            profile_row=profile_row,
            persona_row=persona_row,
            criteria_overrides={},
            self_id=1001,
            limit=10,
        )
        recommendation = build_effective_search_request(
            {
                "source": "mysql://test/her",
                "self_id": 1001,
                "criteria_json": "{}",
                "self_profile_json": "{}",
            },
            profile_row=profile_row,
            persona_profile=persona_row,
        )

        self.assertEqual(
            prepared["search_kwargs"]["criteria"].get("age_min"),
            discovery["criteria"].get("age_min"),
        )
        self.assertEqual(
            prepared["search_kwargs"]["criteria"].get("age_min"),
            recommendation["criteria"].get("age_min"),
        )

    def test_reciprocal_uses_collected_preferences_without_profile_columns(self) -> None:
        runtime = SearchReciprocalRuntime(
            as_int=lambda value: int(value) if value is not None else None,
            as_lower=lambda value: str(value or "").lower(),
            as_text=lambda value: str(value or ""),
            normalize_bool=lambda value: bool(value) if value is not None else None,
            split_keywords=lambda value: [part.strip() for part in str(value or "").split(",") if part.strip()],
            parse_json_object=lambda value: {},
            unique_ordered=lambda values: list(dict.fromkeys(values)),
            build_rejection_reason=lambda reason, detail: reason,
            normalize_strictness_state=lambda value: str(value or "soft"),
            soft_preference_risk_flag=lambda field, strictness: None,
            reciprocal_city_preference_risk_flag=lambda state, mode: None,
            normalize_acceptance_state=lambda value: str(value or "unknown"),
            location_semantics_risk_flags=lambda record: [],
            education_rank=lambda value: 3 if value else None,
            marital_status_match_options=lambda record: [],
            normalize_acceptance_strength=lambda value: str(value or ""),
            marital_acceptance_risk_flag=lambda a, b: None,
            children_acceptance_risk_flag=lambda a, b, c: "",
            habit_requires_acceptance=lambda value: False,
        )
        record = enrich_record_for_reciprocal(
            {
                "id": 2001,
                "target_age_min": 28,
                "target_age_max": 35,
                "target_cities": "上海",
            }
        )
        result = evaluate_reciprocal_compatibility(
            runtime,
            record,
            {"age": 30, "city": "上海"},
        )
        assert result is not None
        self.assertTrue(result.get("matched", True))
        self.assertIn("对方年龄偏好命中", result.get("matched_on", []))

    def test_deprecated_profile_columns_list_is_stable(self) -> None:
        self.assertIn("preferred_age_min", DEPRECATED_PROFILE_COLUMNS)
        self.assertIn("matcher_preferences_json", DEPRECATED_PROFILE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
