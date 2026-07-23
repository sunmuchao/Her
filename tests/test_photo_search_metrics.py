from __future__ import annotations

import unittest
from unittest import mock

from observability.photo_search_metrics import (
    build_photo_search_dashboard,
    build_photo_search_funnel,
    classify_photo_search_event,
    compare_photo_search_bucket_effect,
    emit_photo_search_event,
    normalize_photo_search_rollout,
    resolve_photo_search_experiment_bucket,
    summarize_photo_search_events,
)


class PhotoSearchMetricsTests(unittest.TestCase):
    def test_resolve_photo_search_experiment_bucket_is_stable(self):
        rollout = {"control": 0.5, "appearance_boost_v1": 0.3, "trust_bias_v1": 0.2}
        left = resolve_photo_search_experiment_bucket("user-1", rollout=rollout)
        right = resolve_photo_search_experiment_bucket("user-1", rollout=rollout)
        self.assertEqual(left, right)

    def test_normalize_photo_search_rollout_defaults_when_invalid(self):
        rollout = normalize_photo_search_rollout({"control": 0, "appearance_boost_v1": 0, "trust_bias_v1": 0})
        self.assertAlmostEqual(sum(rollout.values()), 1.0, places=4)

    def test_emit_photo_search_event_emits_metrics(self):
        with (
            mock.patch("observability.photo_search_metrics.funnel_stage") as mocked_funnel,
            mock.patch("observability.photo_search_metrics.metric_gauge") as mocked_metric,
        ):
            payload = emit_photo_search_event(
                user_key="user-1",
                search_type="style_similarity",
                stage="search_completed",
                result_count=12,
                latency_ms=88,
            )
        mocked_funnel.assert_called_once()
        self.assertGreaterEqual(mocked_metric.call_count, 2)
        self.assertTrue(payload["emitted"])

    def test_summarize_and_compare_photo_search_events(self):
        events = [
            {"search_type": "face_similarity", "experiment_bucket": "control", "stage": "search_completed", "success": True, "latency_ms": 110, "result_count": 10},
            {"search_type": "face_similarity", "experiment_bucket": "control", "stage": "search_failed", "success": False, "latency_ms": 150, "result_count": 0},
            {"search_type": "style_similarity", "experiment_bucket": "appearance_boost_v1", "stage": "search_completed", "success": True, "latency_ms": 90, "result_count": 15},
        ]
        summary = summarize_photo_search_events(events)
        compare = compare_photo_search_bucket_effect(events)
        dashboard = build_photo_search_dashboard(events)

        self.assertEqual(summary["total_events"], 3)
        self.assertIn("control", summary["by_experiment_bucket"])
        self.assertEqual(len(compare), 2)
        self.assertIn("search_completed", dashboard["by_stage"])

    def test_build_photo_search_funnel_distinguishes_failure_layers(self):
        events = [
            {"stage": "client_submit_failed", "success": False, "search_type": "unknown"},
            {"stage": "gateway_rejected", "success": False, "search_type": "face_similarity"},
            {"stage": "search_failed", "success": False, "search_type": "style_similarity"},
            {"stage": "search_completed", "success": True, "search_type": "hybrid_photo_similarity", "result_count": 0},
            {"stage": "results_ready", "success": True, "search_type": "hybrid_photo_similarity", "result_count": 6},
        ]

        funnel = build_photo_search_funnel(events)

        self.assertEqual(funnel["request_not_entered_gateway"], 1)
        self.assertEqual(funnel["gateway_rejected"], 1)
        self.assertEqual(funnel["search_failed"], 1)
        self.assertEqual(funnel["search_empty"], 1)
        self.assertEqual(funnel["search_succeeded"], 1)

    def test_classify_photo_search_event_marks_empty_results(self):
        category = classify_photo_search_event(
            {"stage": "search_completed", "success": True, "result_count": 0},
        )

        self.assertEqual(category, "search_empty")


if __name__ == "__main__":
    unittest.main()
