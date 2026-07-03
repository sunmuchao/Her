from __future__ import annotations

import unittest

from match_domain.appearance_features import compute_photo_bonus_breakdown


class AppearanceFeaturesTests(unittest.TestCase):
    def test_compute_photo_bonus_breakdown_without_preference(self):
        bonus = compute_photo_bonus_breakdown(
            {
                "appearance_score_global": 80,
                "photo_quality_score": 70,
                "photo_authenticity_score": 90,
            },
            None,
        )

        self.assertGreater(bonus.global_bonus, 0)
        self.assertGreater(bonus.quality_bonus, 0)
        self.assertEqual(bonus.preference_bonus, 0.0)
        self.assertAlmostEqual(bonus.total, bonus.global_bonus + bonus.quality_bonus, places=2)

    def test_compute_photo_bonus_breakdown_with_preference_match(self):
        bonus = compute_photo_bonus_breakdown(
            {
                "appearance_score_global": 78,
                "photo_quality_score": 85,
                "photo_authenticity_score": 90,
                "mature_score": 82,
                "clean_score": 75,
                "gentle_score": 65,
                "sunny_score": 45,
                "stylish_score": 60,
            },
            {
                "preferred_mature_score": 80,
                "preferred_clean_score": 72,
                "preferred_gentle_score": 68,
                "preferred_sunny_score": 43,
                "preferred_stylish_score": 58,
            },
        )

        self.assertGreater(bonus.preference_bonus, 8)
        self.assertGreater(bonus.total, bonus.global_bonus)


if __name__ == "__main__":
    unittest.main()
