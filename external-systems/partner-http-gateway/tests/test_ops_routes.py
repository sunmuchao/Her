from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest

GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.ops_routes import dispatch_ops_rest, rest_ops_photo_search_dashboard


class _FakeOpsGateway:
    def _require_roles(self, _environ, _roles, *, message):
        self.last_message = message

    def _build_async_job_dashboard(self, *, limit: int) -> dict[str, object]:
        return {"limit": limit}


class OpsRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = _FakeOpsGateway()

    def test_rest_ops_photo_search_dashboard_accepts_posted_events(self):
        payload = {
            "events": [
                {
                    "search_type": "face",
                    "stage": "result_returned",
                    "result_count": 8,
                    "latency_ms": 120,
                    "experiment_bucket": "control",
                    "success": True,
                },
                {
                    "search_type": "style",
                    "stage": "result_returned",
                    "result_count": 5,
                    "latency_ms": 160,
                    "experiment_bucket": "appearance_boost_v1",
                    "success": False,
                },
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }

        status, response = rest_ops_photo_search_dashboard(self.gateway, environ)

        self.assertEqual(status, 200)
        self.assertEqual(response["event_count"], 2)
        self.assertEqual(response["summary"]["total_events"], 2)
        self.assertEqual(response["funnel"]["search_succeeded"], 1)
        self.assertEqual(response["funnel"]["search_failed"], 1)
        self.assertEqual(response["by_stage"]["result_returned"], 2)
        self.assertIn("route_comparison", response)
        self.assertIn("key_metrics", response)
        self.assertIn("migration_progress", response)
        self.assertIn("shadow_compare", response)
        self.assertEqual(response["switchpoints"]["current_primary_entrypoint"], "/v1/discovery/turns")
        self.assertIn("trace_id", response)

    def test_rest_ops_photo_search_dashboard_returns_funnel_breakdown(self):
        payload = {
            "events": [
                {"stage": "client_submit_failed", "success": False, "search_type": "unknown"},
                {"stage": "gateway_rejected", "success": False, "search_type": "face_similarity"},
                {"stage": "search_failed", "success": False, "search_type": "style_similarity"},
                {"stage": "search_completed", "success": True, "search_type": "hybrid_photo_similarity", "result_count": 0},
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }

        status, response = rest_ops_photo_search_dashboard(self.gateway, environ)

        self.assertEqual(status, 200)
        self.assertEqual(response["funnel"]["request_not_entered_gateway"], 1)
        self.assertEqual(response["funnel"]["gateway_rejected"], 1)
        self.assertEqual(response["funnel"]["search_failed"], 1)
        self.assertEqual(response["funnel"]["search_empty"], 1)

    def test_rest_ops_photo_search_dashboard_compares_legacy_and_unified_routes(self):
        payload = {
            "events": [
                {
                    "search_type": "style_similarity",
                    "stage": "results_ready",
                    "result_count": 4,
                    "success": True,
                    "entrypoint": "legacy_photo_search_route",
                    "has_image": True,
                },
                {
                    "search_type": "unified_visual_search",
                    "stage": "results_ready",
                    "result_count": 3,
                    "success": True,
                    "entrypoint": "unified_discovery_turn",
                    "has_image": True,
                    "is_first_visual_turn": True,
                },
                {
                    "search_type": "unified_visual_search",
                    "stage": "empty_result",
                    "result_count": 0,
                    "success": False,
                    "entrypoint": "unified_discovery_turn",
                    "has_image": True,
                    "reused_reference_image": True,
                    "is_refinement": True,
                    "follows_empty_result": True,
                },
                {
                    "search_type": "unified_visual_search_shadow_compare",
                    "stage": "shadow_compare",
                    "success": False,
                    "entrypoint": "unified_discovery_turn",
                    "shadow_diff_detected": True,
                    "shadow_overlap_count": 1,
                    "primary_mode": "face",
                    "baseline_mode": "hybrid",
                },
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }

        status, response = rest_ops_photo_search_dashboard(self.gateway, environ)

        self.assertEqual(status, 200)
        route_map = {item["entrypoint"]: item for item in response["route_comparison"]}
        self.assertIn("legacy_photo_search_route", route_map)
        self.assertIn("unified_discovery_turn", route_map)
        self.assertEqual(response["key_metrics"]["image_turn_success_rate"]["denominator"], 3)
        self.assertEqual(response["key_metrics"]["first_turn_result_rate"]["numerator"], 1)
        self.assertEqual(response["key_metrics"]["reuse_reference_success_rate"]["denominator"], 1)
        self.assertEqual(response["key_metrics"]["refinement_success_rate"]["denominator"], 1)
        self.assertEqual(response["migration_progress"]["shadow_compare"]["diff_event_count"], 1)
        self.assertFalse(response["migration_progress"]["legacy_route_retired"])

    def test_dispatch_ops_rest_routes_photo_search_dashboard(self):
        environ = {
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "",
        }

        result = dispatch_ops_rest(
            self.gateway,
            environ,
            method="GET",
            path="/v1/ops/photo-search/dashboard",
        )

        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)
        self.assertEqual(response["summary"]["total_events"], 0)
        self.assertEqual(response["event_count"], 0)


if __name__ == "__main__":
    unittest.main()
