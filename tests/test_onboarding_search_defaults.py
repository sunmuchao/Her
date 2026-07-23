"""Tests for onboarding → search defaults."""

from __future__ import annotations

import unittest

from match_domain.criteria_compiler import build_discovery_search_request
from match_domain.onboarding_search import (
    age_from_birthday,
    build_onboarding_persona_patch,
    build_onboarding_profile_fields,
    build_profile_search_defaults,
    default_target_age_range,
    expand_relationship_goals_for_search,
    expand_search_gender_values,
    format_criteria_labels,
    genders_match_for_search,
    map_sexual_orientation_to_target_gender,
    normalize_compiled_criteria,
)


class OnboardingSearchDefaultsTests(unittest.TestCase):
    def test_genders_match_for_search_across_aliases(self) -> None:
        self.assertTrue(genders_match_for_search("女", "female"))
        self.assertTrue(genders_match_for_search("male", "男"))
        self.assertFalse(genders_match_for_search("男", "female"))

    def test_expand_search_gender_values(self) -> None:
        self.assertEqual(
            set(expand_search_gender_values("female")),
            {"female", "f", "女"},
        )

    def test_map_sexual_orientation_to_target_gender(self) -> None:
        self.assertEqual(map_sexual_orientation_to_target_gender("like_female"), "female")
        self.assertEqual(map_sexual_orientation_to_target_gender("like_male"), "male")
        self.assertIsNone(map_sexual_orientation_to_target_gender("both"))

    def test_build_onboarding_profile_fields_includes_sexual_orientation(self) -> None:
        fields = build_onboarding_profile_fields(
            {
                "name": "smc",
                "gender": "male",
                "birthday": "1994-05-01",
                "location": "上海",
                "sexual_orientation": "like_female",
                "marriage_status": "never_married",
                "has_children": "no",
            },
            {"relationship_goal": "dating"},
        )
        self.assertEqual(fields["sexual_orientation"], "like_female")
        # 数据库应存储英文标准值，显示时转换为中文
        self.assertEqual(fields["marital_status"], "never_married")
        self.assertEqual(fields["has_children"], 0)
        self.assertEqual(fields["city"], "上海")

    def test_build_onboarding_persona_patch_maps_preference_defaults_only(self) -> None:
        patch = build_onboarding_persona_patch(
            {
                "name": "smc",
                "gender": "male",
                "birthday": "1994-05-01",
                "location": "上海",
                "sexual_orientation": "like_female",
                "relationship_goal": "dating",
                "profile_id": 9010,
            },
            {"relationship_goal": "dating"},
        )
        self_age = age_from_birthday("1994-05-01")
        age_min, age_max = default_target_age_range(self_age)
        self.assertNotIn("target_gender", patch)
        self.assertNotIn("self_city", patch)
        self.assertEqual(patch["target_cities"], "上海")
        self.assertEqual(patch["target_age_min"], age_min)
        self.assertEqual(patch["target_age_max"], age_max)
        self.assertEqual(patch["profile_id"], 9010)

    def test_build_profile_search_defaults_from_profile_row(self) -> None:
        profile_row = {
            "sexual_orientation": "like_female",
            "age": 31,
            "city": "上海",
            "relationship_goal": "dating",
        }
        defaults = build_profile_search_defaults(profile_row)
        self.assertEqual(defaults["gender"], "female")
        self.assertEqual(defaults["cities"], ["上海"])
        self.assertEqual(defaults["age_min"], 26)
        self.assertEqual(defaults["age_max"], 36)
        self.assertIn("dating", defaults["relationship_goals"])

    def test_expand_relationship_goals_for_search(self) -> None:
        expanded = expand_relationship_goals_for_search(["dating"])
        self.assertIn("dating", expanded)
        self.assertIn("认真恋爱", expanded)

    def test_normalize_compiled_criteria_normalizes_gender_and_goals(self) -> None:
        normalized = normalize_compiled_criteria(
            {
                "gender": "女",
                "relationship_goals": ["dating"],
            }
        )
        self.assertEqual(normalized["gender"], "female")
        self.assertIn("认真恋爱", normalized["relationship_goals"])

    def test_format_criteria_labels_uses_human_readable_labels(self) -> None:
        labels = format_criteria_labels(
            {
                "cities": ["上海"],
                "gender": "female",
                "age_min": 26,
                "age_max": 36,
                "relationship_goals": ["dating"],
            }
        )
        self.assertEqual(labels, ["上海", "女", "26-36岁", "先谈恋爱"])

    def test_format_criteria_labels_converts_marital_status_to_chinese(self) -> None:
        """验证婚况英文标准值转换为中文显示标签"""
        labels = format_criteria_labels(
            {
                "cities": ["无锡"],
                "gender": "female",
                "age_min": 26,
                "age_max": 36,
                "relationship_goals": ["marriage"],
                "height_min": 167,
                "height_max": 172,
                "marital_statuses": ["never_married"],
                "accept_partner_children": "不接受",
                "long_distance": "可协商",
            }
        )
        # 验证关键标签
        self.assertIn("无锡", labels)
        self.assertIn("女", labels)
        self.assertIn("26-36岁", labels)
        self.assertIn("奔着结婚", labels)
        self.assertIn("身高167-172cm", labels)
        self.assertIn("婚况未婚", labels)  # 关键：never_married -> 未婚
        self.assertIn("孩子不接受", labels)
        self.assertIn("异地可协商", labels)

    def test_discovery_search_request_includes_profile_defaults(self) -> None:
        profile_row = {
            "gender": "male",
            "age": 31,
            "city": "上海",
            "relationship_goal": "dating",
            "sexual_orientation": "like_female",
        }
        persona_row = build_onboarding_persona_patch(
            {
                "gender": "male",
                "birthday": "1994-05-01",
                "location": "上海",
                "sexual_orientation": "like_female",
                "relationship_goal": "dating",
            },
            {"relationship_goal": "dating"},
        )
        self_age = age_from_birthday("1994-05-01")
        age_min, age_max = default_target_age_range(self_age)
        request = build_discovery_search_request(
            source="mysql://test/her",
            profile_row=profile_row,
            persona_row=persona_row,
            criteria_overrides={},
            self_id=9010,
            limit=5,
        )
        criteria = request["criteria"]
        self.assertEqual(criteria.get("gender"), "female")
        self.assertEqual(criteria.get("cities"), ["上海"])
        self.assertEqual(criteria.get("age_min"), age_min)
        self.assertEqual(criteria.get("age_max"), age_max)
        self.assertIn("dating", criteria.get("relationship_goals") or [])


if __name__ == "__main__":
    unittest.main()
