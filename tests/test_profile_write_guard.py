"""Tests for profile vs persona patch splitting."""

from __future__ import annotations

import unittest

from match_domain.profile_write_guard import (
    build_profile_change_rows,
    merge_working_criteria,
    split_persona_patch,
)


class ProfileWriteGuardTests(unittest.TestCase):
    def test_split_persona_patch(self) -> None:
        profile, persona, search = split_persona_patch(
            {
                "self_city": "杭州",
                "target_cities": "上海,苏州",
                "cities": ["上海", "苏州"],
                "target_age_min": 24,
            }
        )
        self.assertEqual(search["self_city"], "杭州")
        self.assertEqual(search["target_cities"], "上海,苏州")
        self.assertEqual(search["cities"], ["上海", "苏州"])
        self.assertEqual(search["target_age_min"], 24)

    def test_public_notes_routes_to_profile_patch(self) -> None:
        profile, persona, search = split_persona_patch(
            {
                "public_notes": "平时作息规律，比较看重相处舒服和沟通顺畅",
            }
        )
        self.assertEqual(
            profile["public_notes"],
            "平时作息规律，比较看重相处舒服和沟通顺畅",
        )
        self.assertEqual(persona, {})
        self.assertEqual(search, {})

    def test_build_profile_change_rows(self) -> None:
        rows = build_profile_change_rows(
            current_profile={"city": "上海", "age": 31},
            proposed_patch={"city": "杭州"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "city")
        self.assertEqual(rows[0]["from"], "上海")
        self.assertEqual(rows[0]["to"], "杭州")

    def test_merge_working_criteria(self) -> None:
        merged = merge_working_criteria(
            {"working_criteria": {"age_min": 26}},
            {"cities": ["无锡"], "age_max": 36},
        )
        self.assertEqual(merged["age_min"], 26)
        self.assertEqual(merged["cities"], ["无锡"])
        self.assertEqual(merged["age_max"], 36)


if __name__ == "__main__":
    unittest.main()
