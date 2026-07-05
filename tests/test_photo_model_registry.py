from __future__ import annotations

import unittest
from unittest import mock

from match_domain.photo_model_registry import (
    PHOTO_MODEL_KEYS,
    build_photo_feature_recompute_plan,
    build_photo_model_rollout_plan,
    evaluate_photo_model_candidate,
    normalize_photo_model_versions,
    trigger_photo_feature_recompute,
)


class PhotoModelRegistryTests(unittest.TestCase):
    def test_normalize_photo_model_versions_fills_defaults(self):
        payload = normalize_photo_model_versions({"face_embedding_model": "face_v2"})
        self.assertEqual(set(payload.keys()), set(PHOTO_MODEL_KEYS))
        self.assertEqual(payload["face_embedding_model"], "face_v2")
        self.assertEqual(payload["style_model"], "deterministic_v1")

    def test_evaluate_photo_model_candidate_rejects_latency_regression(self):
        result = evaluate_photo_model_candidate(
            baseline_metrics={"success_rate": 0.72, "avg_latency_ms": 90, "avg_result_count": 12},
            candidate_metrics={"success_rate": 0.75, "avg_latency_ms": 135, "avg_result_count": 12},
            max_latency_regression_ms=20,
        )
        self.assertFalse(result["approved"])
        self.assertIn("latency_regression_too_high", result["reasons"])

    def test_build_photo_model_rollout_plan_marks_recompute_if_versions_changed(self):
        plan = build_photo_model_rollout_plan(
            current_versions={"face_embedding_model": "face_v1"},
            candidate_versions={"face_embedding_model": "face_v2"},
            rollout_ratio=0.25,
        )
        self.assertTrue(plan["requires_recompute"])
        self.assertEqual(plan["rollout_ratio"], 0.25)
        self.assertIn("face_embedding_model", plan["changed_keys"])

    def test_build_photo_feature_recompute_plan_batches_ids(self):
        plan = build_photo_feature_recompute_plan(
            profile_ids=[1, 2, 3, 4, 5],
            target_versions={"face_embedding_model": "face_v2"},
            batch_size=2,
        )
        self.assertEqual(plan["total_profiles"], 5)
        self.assertEqual(plan["batches"], [[1, 2], [3, 4], [5]])

    def test_trigger_photo_feature_recompute_collects_results(self):
        refresh_fn = mock.Mock(
            side_effect=[
                {"saved": True, "analysis_status": "done"},
                {"saved": False, "error": "failed"},
            ]
        )
        out = trigger_photo_feature_recompute(
            source_dsn="mysql://example/her",
            profile_ids=[1001, 1002],
            target_versions={"summary_model": "summary_v2"},
            batch_size=1,
            refresh_fn=refresh_fn,
        )
        self.assertEqual(out["succeeded"], 1)
        self.assertEqual(out["failed"], 1)
        self.assertEqual(len(out["processed"]), 2)
        self.assertEqual(out["processed"][0]["target_versions"]["summary_model"], "summary_v2")


if __name__ == "__main__":
    unittest.main()
