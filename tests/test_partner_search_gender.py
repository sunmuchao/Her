"""Gender alias handling in partner_search SQL prefilter and matching."""

from __future__ import annotations

import unittest

from match_domain.onboarding_search import (
    expand_search_gender_values,
    genders_match_for_search,
    normalize_search_gender,
)
from partner_search import load_self_profile, search_profiles


class PartnerSearchGenderTests(unittest.TestCase):
    def test_normalize_and_expand_female_aliases(self) -> None:
        self.assertEqual(normalize_search_gender("女"), "female")
        self.assertEqual(normalize_search_gender("female"), "female")
        self.assertEqual(
            set(expand_search_gender_values("female")),
            {"female", "f", "女"},
        )

    def test_genders_match_for_search_across_aliases(self) -> None:
        self.assertTrue(genders_match_for_search("女", "female"))
        self.assertTrue(genders_match_for_search("male", "男"))
        self.assertFalse(genders_match_for_search("男", "female"))

    def test_search_female_finds_chinese_gender_rows(self) -> None:
        source = "mysql://root@127.0.0.1:3307/her?table=profiles"
        try:
            self_profile = load_self_profile(source=source, self_id=9014)
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"local profile DB unavailable: {exc}")
        if not self_profile:
            self.skipTest("profile 9014 not found in local DB")

        criteria = {
            "age_max": 38,
            "age_min": 24,
            "cities": ["上海", "无锡"],
            "gender": "female",
            "relationship_goals": ["dating", "认真恋爱"],
        }
        response = search_profiles(
            source=source,
            criteria=criteria,
            self_profile=self_profile,
            self_id=9014,
            limit=10,
        )
        pool = response.get("pool_summary") or {}
        self.assertGreaterEqual(int(pool.get("scanned_count") or 0), 2)
        self.assertGreaterEqual(int(response.get("result_count") or 0), 2)
        result_ids = {int(item.get("id") or 0) for item in response.get("results") or []}
        self.assertTrue({9001, 9002}.issubset(result_ids))


if __name__ == "__main__":
    unittest.main()
