from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest import mock

from match_domain.appearance_features import (
    AppearanceInterestSignal,
    backfill_profile_photo_features,
    backfill_user_appearance_preferences,
    build_photo_feature_patch,
    compute_appearance_interest_signal,
    compute_photo_bonus_breakdown,
    rebuild_user_preference_from_history,
)


class AppearanceFeaturesTests(unittest.TestCase):
    def test_compute_appearance_interest_signal_detects_quick_bounce(self):
        signal = compute_appearance_interest_signal(
            event_weight=1.0,
            detail_view_duration_ms=1200,
            card_visible_duration_ms=800,
            photo_swipe_count=0,
            return_view_count=0,
        )

        self.assertIsInstance(signal, AppearanceInterestSignal)
        self.assertTrue(signal.is_quick_bounce)
        self.assertEqual(signal.detail_quality, 'low')
        self.assertLess(signal.net_signal, 0)

    def test_compute_appearance_interest_signal_rewards_engaged_detail_view(self):
        signal = compute_appearance_interest_signal(
            event_weight=0.5,
            detail_view_duration_ms=9500,
            card_visible_duration_ms=2600,
            photo_swipe_count=3,
            return_view_count=1,
        )

        self.assertFalse(signal.is_quick_bounce)
        self.assertEqual(signal.detail_quality, 'high')
        self.assertGreater(signal.telemetry_weight, 0)
        self.assertGreater(signal.net_signal, 0)

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

    def test_backfill_profile_photo_features_processes_batches_and_skips_existing(self):
        rows = [
            {"id": 11, "avatar_url": "https://img.her.local/11.jpg"},
            {"id": 12, "avatar_url": "https://img.her.local/12.jpg"},
            {"id": 13, "avatar_url": "https://img.her.local/13.jpg"},
        ]
        refreshed_ids: list[int] = []

        def fake_refresh(**kwargs):
            refreshed_ids.append(int(kwargs["profile_id"]))
            return {"analysis_status": "done", "profile_id": kwargs["profile_id"]}

        with (
            mock.patch("match_domain.appearance_features.resolve_profile_source", return_value=("mysql://profiles", "profiles")),
            mock.patch("match_domain.appearance_features.iter_profile_batches", return_value=[rows[:2], rows[2:]]),
            mock.patch(
                "match_domain.appearance_features.load_candidate_photo_features",
                return_value={12: {"profile_id": 12, "analysis_status": "done"}},
            ),
            mock.patch("match_domain.appearance_features.refresh_profile_photo_features", side_effect=fake_refresh),
        ):
            result = backfill_profile_photo_features(
                source_dsn="mysql://persona",
                profile_source_dsn="mysql://profiles",
                only_missing=True,
            )

        self.assertEqual(refreshed_ids, [11, 13])
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["saved_count"], 2)
        self.assertEqual(result["failed_count"], 0)

    def test_backfill_profile_photo_features_stops_at_limit(self):
        rows = [
            {"id": 21},
            {"id": 22},
            {"id": 23},
        ]
        refreshed_ids: list[int] = []

        def fake_refresh(**kwargs):
            refreshed_ids.append(int(kwargs["profile_id"]))
            return {"analysis_status": "done"}

        with (
            mock.patch("match_domain.appearance_features.resolve_profile_source", return_value=("mysql://profiles", "profiles")),
            mock.patch("match_domain.appearance_features.iter_profile_batches", return_value=[rows]),
            mock.patch("match_domain.appearance_features.refresh_profile_photo_features", side_effect=fake_refresh),
        ):
            result = backfill_profile_photo_features(
                source_dsn="mysql://persona",
                limit=2,
            )

        self.assertEqual(refreshed_ids, [21, 22])
        self.assertEqual(result["processed"], 2)
        self.assertTrue(result["stopped_early"])

    def test_backfill_user_appearance_preferences_aggregates_results(self):
        with mock.patch(
            "match_domain.appearance_features.rebuild_user_preference_from_history",
            side_effect=[
                {"user_key": "u1", "preferred_mature_score": 71},
                {"saved": False, "error": "no_feedback_events"},
            ],
        ):
            result = backfill_user_appearance_preferences(
                source_dsn="mysql://persona",
                user_keys=["u1", "u2", "u1"],
                scene="discovery",
            )

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["results"][0]["user_key"], "u1")

    def test_rebuild_user_preference_from_history_applies_time_decay(self):
        recent_row = {
            "mature_score": 80,
            "clean_score": 78,
            "gentle_score": 60,
            "sunny_score": 40,
            "stylish_score": 58,
            "appearance_summary": "偏成熟清爽。",
        }
        old_row = {
            "mature_score": 20,
            "clean_score": 22,
            "gentle_score": 45,
            "sunny_score": 85,
            "stylish_score": 30,
            "appearance_summary": "偏活力阳光。",
        }
        captured_patches: list[dict[str, object]] = []
        now = datetime(2026, 7, 4, 12, 0, 0)

        def fake_upsert(**kwargs):
            captured_patches.append(dict(kwargs["patch"]))
            return {"user_key": kwargs["user_key"], **kwargs["patch"]}

        with (
            mock.patch(
                "match_domain.appearance_features.list_appearance_feedback_events",
                return_value=[
                    {
                        "candidate_profile_id": 18,
                        "event_type": "express_interest",
                        "event_weight": 3.0,
                        "created_at": now - timedelta(days=2),
                    },
                    {
                        "candidate_profile_id": 19,
                        "event_type": "express_interest",
                        "event_weight": 3.0,
                        "created_at": now - timedelta(days=180),
                    },
                ],
            ),
            mock.patch(
                "match_domain.appearance_features.load_candidate_photo_features",
                return_value={18: recent_row, 19: old_row},
            ),
            mock.patch("match_domain.appearance_features.upsert_user_appearance_preference", side_effect=fake_upsert),
            mock.patch("match_domain.appearance_features.sync_user_appearance_preference_embedding", return_value={"saved": True}),
            mock.patch("match_domain.appearance_features.load_requester_appearance_preference", return_value=None),
        ):
            result = rebuild_user_preference_from_history(
                source_dsn="mysql://persona",
                user_key="user-1",
                profile_id=12,
                scene="discovery",
                now=now,
            )

        self.assertGreater(result["preferred_mature_score"], 60)
        self.assertTrue(captured_patches)


if __name__ == "__main__":
    unittest.main()
