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
        self.assertEqual(response["by_stage"]["result_returned"], 2)
        self.assertIn("trace_id", response)

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
