from __future__ import annotations

import unittest
from unittest import mock

from match_domain.appearance_features import (
    build_photo_feature_patch,
    compute_photo_bonus_breakdown,
    rebuild_user_preference_from_history,
)


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

    def test_build_photo_feature_patch_returns_done_payload(self):
        patch = build_photo_feature_patch(
            profile_row={"id": 12, "age": 31, "photo_verification_level": "id"},
            photo_entries=[
                {"photo_source": "https://img.her.local/12/avatar.jpg"},
                {"photo_source": "https://img.her.local/12/gallery.jpg"},
            ],
        )

        self.assertEqual(patch["analysis_status"], "done")
        self.assertIn("appearance_summary", patch)
        self.assertGreater(patch["appearance_score_global"], 0)
        self.assertEqual(patch["analysis_model"], "deterministic-photo-feature-v1")

    def test_rebuild_user_preference_from_history_uses_signed_events(self):
        feature_row = {
            "mature_score": 80,
            "clean_score": 76,
            "gentle_score": 62,
            "sunny_score": 41,
            "stylish_score": 58,
            "appearance_summary": "偏成熟清爽，整体比较利落。",
        }
        opposite_row = {
            "mature_score": 22,
            "clean_score": 35,
            "gentle_score": 40,
            "sunny_score": 82,
            "stylish_score": 30,
            "appearance_summary": "更偏阳光活力型。",
        }
        saved_rows: list[dict[str, object]] = []

        def fake_upsert(**kwargs):
            saved_rows.append(dict(kwargs["patch"]))
            return {"user_key": kwargs["user_key"], **kwargs["patch"]}

        with (
            mock.patch("match_domain.appearance_features.list_appearance_feedback_events", return_value=[
                {"candidate_profile_id": 18, "event_type": "express_interest", "event_weight": 3.0},
                {"candidate_profile_id": 19, "event_type": "skip", "event_weight": -2.0},
            ]),
            mock.patch("match_domain.appearance_features.load_candidate_photo_features", return_value={18: feature_row, 19: opposite_row}),
            mock.patch("match_domain.appearance_features.upsert_user_appearance_preference", side_effect=fake_upsert),
            mock.patch("match_domain.appearance_features.sync_user_appearance_preference_embedding", return_value={"saved": True}),
            mock.patch("match_domain.appearance_features.load_requester_appearance_preference", return_value=None),
        ):
            result = rebuild_user_preference_from_history(
                source_dsn="mysql://persona",
                user_key="user-1",
                profile_id=12,
                scene="recommendation_action",
            )

        self.assertEqual(result["positive_sample_count"], 1)
        self.assertEqual(result["negative_sample_count"], 1)
        self.assertGreater(result["preferred_mature_score"], 50)
        self.assertIn("更容易被这类风格吸引", result["appearance_preference_summary"])
        self.assertTrue(saved_rows)


if __name__ == "__main__":
    unittest.main()
