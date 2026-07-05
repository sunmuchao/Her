from __future__ import annotations

import unittest
from unittest import mock

from observability.photo_search_metrics import (
    compare_photo_search_bucket_effect,
    emit_photo_search_event,
    resolve_photo_search_experiment_bucket,
    summarize_photo_search_events,
)


class PhotoSearchMetricsTests(unittest.TestCase):
    def test_resolve_photo_search_experiment_bucket_is_stable(self):
        left = resolve_photo_search_experiment_bucket("user-1")
        right = resolve_photo_search_experiment_bucket("user-1")
        self.assertEqual(left, right)

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
            {"search_type": "face_similarity", "experiment_bucket": "control", "success": True, "latency_ms": 110, "result_count": 10},
            {"search_type": "face_similarity", "experiment_bucket": "control", "success": False, "latency_ms": 150, "result_count": 0},
            {"search_type": "style_similarity", "experiment_bucket": "appearance_boost_v1", "success": True, "latency_ms": 90, "result_count": 15},
        ]
        summary = summarize_photo_search_events(events)
        compare = compare_photo_search_bucket_effect(events)

        self.assertEqual(summary["total_events"], 3)
        self.assertIn("control", summary["by_experiment_bucket"])
        self.assertEqual(len(compare), 2)


if __name__ == "__main__":
    unittest.main()
