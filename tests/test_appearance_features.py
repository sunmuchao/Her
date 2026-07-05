from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest import mock

from match_domain.appearance_features import (
    AppearanceInterestSignal,
    AppearanceStyleScorer,
    AppearanceWeightStrategy,
    AppearanceSummaryGenerator,
    AppearanceTagExtractor,
    EnvironmentGapCompensator,
    FaceDetector,
    FaceEmbeddingExtractor,
    FaceConsistencyScorer,
    FaceQualityAssessor,
    FacialAttributeScorer,
    GlobalAppearanceScorer,
    PrimaryPhotoSelector,
    ProfilePhotoTrustScore,
    ProfilePhotoTrustScorer,
    PhotoAnalysisRetryQueue,
    PhotoAnalysisStateMachine,
    PhotoFeatureVersionManager,
    PhotoQualityScorer,
    RiskPenaltyCalculator,
    TrustBonusCalculator,
    YouthfulnessScorer,
    apply_click_quality_correction,
    backfill_profile_photo_features,
    backfill_user_appearance_preferences,
    build_appearance_explanation,
    build_match_explanation_payload,
    build_photo_feature_patch,
    calibrate_global_appearance_score,
    create_reference_face_search_job,
    classify_click_quality,
    compute_cover_authenticity_score,
    compute_cover_detail_consistency_score,
    compute_detail_duration_strength,
    compute_appearance_interest_signal,
    compute_photo_bonus_breakdown,
    load_profile_photo_feature_versions,
    load_verified_face_anchors,
    load_face_consistency_score,
    rebuild_user_preference_from_history,
    retry_failed_profile_photo_features,
    resolve_appearance_weight_strategy,
    resolve_global_bonus_multiplier,
    resolve_preference_weight_multiplier,
    VerifiedFaceAnchorWriter,
    VerifiedPhotoQualityScorer,
)


class AppearanceFeaturesTests(unittest.TestCase):
    def test_compute_detail_duration_strength_maps_bounce_and_deep_read(self):
        self.assertLess(compute_detail_duration_strength(1200), 0)
        self.assertGreater(compute_detail_duration_strength(12000), 0)

    def test_classify_click_quality_distinguishes_low_medium_high(self):
        self.assertEqual(
            classify_click_quality(detail_view_duration_ms=1200, quick_bounce=True),
            'low',
        )
        self.assertEqual(
            classify_click_quality(detail_view_duration_ms=4200, photo_swipe_count=1),
            'medium',
        )
        self.assertEqual(
            classify_click_quality(detail_view_duration_ms=9500, return_view_count=1),
            'high',
        )

    def test_apply_click_quality_correction_penalizes_bounce_and_rewards_engagement(self):
        low = apply_click_quality_correction(
            base_event_weight=1.0,
            detail_view_duration_ms=1200,
            quick_bounce=True,
        )
        high = apply_click_quality_correction(
            base_event_weight=1.0,
            detail_view_duration_ms=9500,
            photo_swipe_count=3,
            return_view_count=1,
        )
        self.assertLess(low, 0)
        self.assertGreater(high, 1.0)

    def test_cover_authenticity_and_consistency_scores_are_reasonable(self):
        profile_row = {
            "id": 12,
            "avatar_url": "https://img.her.local/12/avatar.jpg",
            "photo_verification_level": "id",
        }
        photo_entries = [
            {"photo_source": "https://img.her.local/12/avatar.jpg"},
            {"photo_source": "https://img.her.local/12/gallery-1.jpg"},
            {"photo_source": "https://img.her.local/12/gallery-2.jpg"},
        ]
        authenticity = compute_cover_authenticity_score(
            profile_row=profile_row,
            photo_entries=photo_entries,
        )
        consistency = compute_cover_detail_consistency_score(photo_entries)
        self.assertGreater(authenticity, 60)
        self.assertGreater(consistency, 50)

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
                "positive_sample_count": 18,
                "negative_sample_count": 4,
            },
        )

        self.assertGreater(bonus.preference_bonus, 8)
        self.assertGreater(bonus.total, bonus.global_bonus)

    def test_preference_weight_multiplier_scales_with_history_size(self):
        self.assertEqual(
            resolve_preference_weight_multiplier({"positive_sample_count": 1, "negative_sample_count": 1}),
            0.45,
        )
        self.assertEqual(
            resolve_preference_weight_multiplier({"positive_sample_count": 5, "negative_sample_count": 2}),
            0.75,
        )
        self.assertEqual(
            resolve_preference_weight_multiplier({"positive_sample_count": 12, "negative_sample_count": 10}),
            1.15,
        )

    def test_global_score_calibration_and_new_user_multiplier(self):
        self.assertLess(calibrate_global_appearance_score(95), 95)
        self.assertGreater(calibrate_global_appearance_score(20), 20)
        self.assertEqual(resolve_global_bonus_multiplier(None), 1.2)
        self.assertEqual(
            resolve_global_bonus_multiplier({"positive_sample_count": 10, "negative_sample_count": 3}),
            1.0,
        )

    def test_compute_photo_bonus_breakdown_gives_new_users_more_base_and_less_preference(self):
        feature_row = {
            "appearance_score_global": 82,
            "photo_quality_score": 85,
            "photo_authenticity_score": 90,
            "mature_score": 82,
            "clean_score": 75,
            "gentle_score": 65,
            "sunny_score": 45,
            "stylish_score": 60,
        }
        new_user_bonus = compute_photo_bonus_breakdown(
            feature_row,
            {
                "preferred_mature_score": 80,
                "preferred_clean_score": 72,
                "preferred_gentle_score": 68,
                "preferred_sunny_score": 43,
                "preferred_stylish_score": 58,
                "positive_sample_count": 1,
                "negative_sample_count": 0,
            },
        )
        old_user_bonus = compute_photo_bonus_breakdown(
            feature_row,
            {
                "preferred_mature_score": 80,
                "preferred_clean_score": 72,
                "preferred_gentle_score": 68,
                "preferred_sunny_score": 43,
                "preferred_stylish_score": 58,
                "positive_sample_count": 20,
                "negative_sample_count": 4,
            },
        )

        self.assertGreater(new_user_bonus.global_bonus, old_user_bonus.global_bonus)
        self.assertLess(new_user_bonus.preference_bonus, old_user_bonus.preference_bonus)

    def test_resolve_appearance_weight_strategy_differs_by_scene_and_stage(self):
        discovery_new = resolve_appearance_weight_strategy(
            "discovery",
            {"positive_sample_count": 1, "negative_sample_count": 0},
        )
        recommendation_old = resolve_appearance_weight_strategy(
            "recommendation",
            {"positive_sample_count": 18, "negative_sample_count": 5},
        )

        self.assertIsInstance(discovery_new, AppearanceWeightStrategy)
        self.assertEqual(discovery_new.user_stage, "new_user")
        self.assertGreater(discovery_new.base_weight, recommendation_old.base_weight)
        self.assertLess(discovery_new.preference_weight, recommendation_old.preference_weight)
        self.assertGreater(recommendation_old.trust_weight, 1.0)

    def test_trust_and_risk_calculators_return_split_breakdowns(self):
        profile_row = {
            "verified_level": "id",
            "photo_verification_level": "live_video_verified",
        }
        feature_row = {
            "photo_authenticity_score": 36,
            "photo_quality_score": 42,
        }
        trust = TrustBonusCalculator.compute(profile_row, feature_row)
        risk = RiskPenaltyCalculator.compute(
            profile_row,
            feature_row,
            risk_flags=["疑似假图", "多人合照"],
        )

        self.assertGreater(trust.total, 5)
        self.assertGreater(risk.total, 5)
        self.assertIn("照片真实性需要再确认", risk.reasons)

    def test_profile_photo_trust_scorer_combines_bonus_penalty_and_confidence(self):
        trust_score = ProfilePhotoTrustScorer.score(
            {
                "verified_level": "id",
                "photo_verification_level": "live_video_verified",
            },
            {
                "photo_authenticity_score": 84,
                "photo_quality_score": 79,
            },
            risk_flags=[],
        )
        self.assertIsInstance(trust_score, ProfilePhotoTrustScore)
        self.assertGreater(trust_score.score, 60)
        self.assertEqual(trust_score.risk_level, "low")
        self.assertTrue(trust_score.badges)

    def test_verified_photo_quality_scorer_and_anchor_writer(self):
        with mock.patch(
            "match_domain.appearance_features.upsert_verified_face_anchor",
            return_value={"profile_id": 12, "quality_score": 84, "metadata_json": {"reasons": ["认证照质量整体稳定"]}},
        ) as mocked:
            quality = VerifiedPhotoQualityScorer.score(
                {"photo_verification_level": "id"},
                [{"photo_source": "https://img.her.local/verified.jpg"}],
            )
            anchor = VerifiedFaceAnchorWriter.write(
                source_dsn="mysql://persona",
                profile_id=12,
                profile_row={"photo_verification_level": "id"},
                photo_entries=[{"photo_source": "https://img.her.local/verified.jpg"}],
                face_embedding_row={"embedding_json": [0.1, 0.2, 0.3]},
            )

        self.assertGreater(quality.score, 70)
        mocked.assert_called_once()
        self.assertEqual(anchor["quality_score"], 84)

    def test_environment_gap_and_face_consistency_scorer(self):
        gap = EnvironmentGapCompensator.assess(
            {"quality_score": 86, "confidence_score": 88},
            {"photo_quality_score": 62, "photo_authenticity_score": 58, "appearance_score_global": 64},
        )
        result = FaceConsistencyScorer.score(
            {"quality_score": 86, "confidence_score": 88, "embedding_json": [0.5, 0.3, 0.1]},
            {"photo_quality_score": 62, "photo_authenticity_score": 58, "appearance_score_global": 64},
            face_embedding_row={"embedding_json": [0.45, 0.28, 0.12]},
        )

        self.assertGreater(gap.gap_score, 0)
        self.assertLessEqual(result.threshold, 78)
        self.assertTrue(result.risk_level in {"low", "medium", "high"})
        self.assertIsInstance(result.risk_flags, list)

    def test_face_detector_quality_embedding_and_primary_selector(self):
        photos = [
            {"photo_source": "https://img.her.local/group-shot.jpg"},
            {"photo_source": "https://img.her.local/avatar.jpg"},
        ]
        detections = FaceDetector.detect(photos)
        selected = PrimaryPhotoSelector.select(photos, detections)
        embedding = FaceEmbeddingExtractor.extract(profile_id=12, photo_entries=photos)

        self.assertEqual(detections[0]["face_count"], 2)
        self.assertEqual(selected["photo_source"], "https://img.her.local/avatar.jpg")
        self.assertEqual(embedding["embedding_dim"], 16)
        self.assertGreater(FaceQualityAssessor.score(detections[1]), FaceQualityAssessor.score(detections[0]))

    def test_photo_quality_and_attribute_style_scorers(self):
        profile = {"id": 12, "age": 29, "photo_verification_level": "id"}
        photos = [
            {"photo_source": "https://img.her.local/avatar.jpg"},
            {"photo_source": "https://img.her.local/gallery.jpg"},
        ]
        detections = FaceDetector.detect(photos)
        quality = PhotoQualityScorer.score(profile_row=profile, photo_entries=photos, detections=detections)
        attributes = FacialAttributeScorer.score(profile_row=profile, photo_entries=photos)
        styles = AppearanceStyleScorer.score(profile_row=profile, photo_entries=photos)
        tags = AppearanceTagExtractor.extract(styles)
        summary = AppearanceSummaryGenerator.generate(style_scores=styles, attribute_scores=attributes)
        youthfulness = YouthfulnessScorer.score(attributes)

        self.assertGreater(quality, 60)
        self.assertIn("eye_size_score", attributes)
        self.assertIn("clean_score", styles)
        self.assertTrue(tags)
        self.assertTrue(summary)
        self.assertGreaterEqual(youthfulness, 0)

    def test_build_appearance_explanation_produces_summary_and_highlights(self):
        explanation = build_appearance_explanation(
            {
                "appearance_score_global": 82,
                "photo_quality_score": 84,
                "photo_authenticity_score": 88,
                "mature_score": 79,
                "clean_score": 81,
                "gentle_score": 58,
                "sunny_score": 49,
                "stylish_score": 63,
                "appearance_summary": "偏成熟清爽。",
            },
            {
                "preferred_mature_score": 80,
                "preferred_clean_score": 75,
                "preferred_gentle_score": 60,
                "preferred_sunny_score": 44,
                "preferred_stylish_score": 61,
                "positive_sample_count": 10,
                "negative_sample_count": 2,
            },
        )

        self.assertTrue(explanation["summary"])
        self.assertIn("长相类型贴近你最近常点喜欢的那一挂", explanation["highlights"])
        self.assertEqual(explanation["stage"], "stable_preference")

    def test_build_match_explanation_payload_combines_base_and_appearance_templates(self):
        payload = build_match_explanation_payload(
            matched_on=["同城", "关系目标一致", "工作稳定"],
            appearance_reasoning={
                "summary": "第一眼眼缘会更强",
                "highlights": ["照片整体比较顺眼"],
            },
        )

        self.assertEqual(payload["template_key"], "base_plus_appearance")
        self.assertIn("同城、关系目标一致", payload["summary"])
        self.assertIn("第一眼眼缘会更强", payload["summary"])
        self.assertEqual(payload["highlights"][:2], ["同城", "关系目标一致"])

    def test_photo_analysis_state_machine_and_retry_queue(self):
        processing_patch = PhotoAnalysisStateMachine.build_transition_patch(
            {"analysis_status": "pending"},
            next_status="processing",
            embedding_status="pending",
        )
        self.assertEqual(processing_patch["analysis_status"], "processing")
        retry_patch = PhotoAnalysisRetryQueue.build_retry_patch(
            {"analysis_status": "failed", "retry_count": 1, "last_error": "timeout"},
            max_retry_count=3,
        )
        self.assertEqual(retry_patch["analysis_status"], "retrying")
        self.assertEqual(retry_patch["retry_count"], 2)
        exhausted_patch = PhotoAnalysisRetryQueue.build_retry_patch(
            {"analysis_status": "failed", "retry_count": 3, "last_error": "timeout"},
            max_retry_count=3,
        )
        self.assertEqual(exhausted_patch["analysis_status"], "failed")

    def test_photo_feature_version_manager_builds_snapshot(self):
        snapshot = PhotoFeatureVersionManager.build_snapshot(
            {
                "profile_id": 12,
                "photo_set_version": 3,
                "analysis_status": "done",
                "appearance_score_global": 82,
                "last_error": None,
            },
            trigger_reason="analysis_completed",
        )
        self.assertEqual(snapshot["profile_id"], 12)
        self.assertEqual(snapshot["trigger_reason"], "analysis_completed")

    def test_load_profile_photo_feature_versions_delegates_to_profile_service(self):
        with mock.patch(
            "match_domain.appearance_features.list_profile_photo_feature_versions",
            return_value=[{"profile_id": 12, "snapshot_json": {"analysis_status": "done"}}],
        ) as mocked:
            rows = load_profile_photo_feature_versions(
                source_dsn="mysql://persona",
                profile_id=12,
            )
        mocked.assert_called_once()
        self.assertEqual(rows[0]["profile_id"], 12)

    def test_retry_failed_profile_photo_features_retries_rows_until_done(self):
        feature_row = {
            "profile_id": 12,
            "analysis_status": "failed",
            "retry_count": 1,
            "last_error": "timeout",
        }
        with (
            mock.patch(
                "match_domain.appearance_features.list_profile_photo_feature_rows",
                return_value=[feature_row],
            ),
            mock.patch(
                "match_domain.appearance_features.upsert_profile_photo_features",
                side_effect=[
                    {"profile_id": 12, "analysis_status": "retrying", "retry_count": 2},
                ],
            ),
            mock.patch(
                "match_domain.appearance_features.refresh_profile_photo_features",
                return_value={"profile_id": 12, "analysis_status": "done"},
            ),
        ):
            result = retry_failed_profile_photo_features(
                source_dsn="mysql://persona",
                max_retry_count=3,
            )
        self.assertEqual(result["retried_count"], 1)

    def test_load_anchor_and_consistency_wrappers_delegate_to_profile_service(self):
        with (
            mock.patch(
                "match_domain.appearance_features.list_verified_face_anchors",
                return_value=[{"profile_id": 12, "anchor_version": "verified-anchor-v1:12"}],
            ) as mocked_anchors,
            mock.patch(
                "match_domain.appearance_features.get_face_consistency_score",
                return_value={"profile_id": 12, "consistency_score": 81},
            ) as mocked_consistency,
        ):
            anchors = load_verified_face_anchors(
                source_dsn="mysql://persona",
                profile_id=12,
            )
            consistency = load_face_consistency_score(
                source_dsn="mysql://persona",
                profile_id=12,
            )

        mocked_anchors.assert_called_once()
        mocked_consistency.assert_called_once()
        self.assertEqual(anchors[0]["profile_id"], 12)
        self.assertEqual(consistency["consistency_score"], 81)

    def test_create_reference_face_search_job_delegates_to_profile_service(self):
        with mock.patch(
            "match_domain.appearance_features.insert_reference_face_search_job",
            return_value={"requester_user_key": "user-1", "result_count": 2},
        ) as mocked:
            result = create_reference_face_search_job(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                requester_profile_id=9,
                input_source="https://img.her.local/reference.jpg",
                result_profile_ids=[12, 18],
                status="done",
            )

        mocked.assert_called_once()
        self.assertEqual(result["result_count"], 2)

    def test_global_appearance_scorer_uses_existing_or_fallback_formula(self):
        calibrated = GlobalAppearanceScorer.score({"appearance_score_global": 86})
        self.assertLess(calibrated, 86.0)
        self.assertGreater(calibrated, 65.0)
        self.assertGreater(
            GlobalAppearanceScorer.score(
                {
                    "photo_quality_score": 80,
                    "photo_authenticity_score": 70,
                    "face_score_global": 75,
                }
            ),
            60,
        )

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

    def test_rebuild_user_preference_from_history_uses_engagement_metrics_signal(self):
        feature_row = {
            "mature_score": 78,
            "clean_score": 72,
            "gentle_score": 61,
            "sunny_score": 48,
            "stylish_score": 55,
            "appearance_summary": "成熟清爽风格。",
        }
        saved_rows: list[dict[str, object]] = []

        def fake_upsert(**kwargs):
            saved_rows.append(dict(kwargs["patch"]))
            return {"user_key": kwargs["user_key"], **kwargs["patch"]}

        with (
            mock.patch("match_domain.appearance_features.list_appearance_feedback_events", return_value=[
                {
                    "candidate_profile_id": 18,
                    "event_type": "engagement_metrics",
                    "event_weight": 0.0,
                    "metadata": {
                        "detail_view_duration_ms": 9200,
                        "card_visible_duration_ms": 2600,
                        "photo_swipe_count": 2,
                        "return_view_count": 1,
                        "quick_bounce": False,
                    },
                },
            ]),
            mock.patch("match_domain.appearance_features.load_candidate_photo_features", return_value={18: feature_row}),
            mock.patch("match_domain.appearance_features.upsert_user_appearance_preference", side_effect=fake_upsert),
            mock.patch("match_domain.appearance_features.sync_user_appearance_preference_embedding", return_value={"saved": True}),
            mock.patch("match_domain.appearance_features.load_requester_appearance_preference", return_value=None),
        ):
            result = rebuild_user_preference_from_history(
                source_dsn="mysql://persona",
                user_key="user-telemetry",
                profile_id=12,
                scene="discovery",
            )

        self.assertEqual(result["positive_sample_count"], 1)
        self.assertGreater(result["preferred_mature_score"], 50)
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
