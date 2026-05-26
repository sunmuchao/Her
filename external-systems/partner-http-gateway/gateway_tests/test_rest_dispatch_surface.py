"""REST dispatch surface integration tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from gateway.app import PartnerGateway
from gateway.rest_dispatch import dispatch_gateway_rest


class RestDispatchSurfaceTests(unittest.TestCase):
    @patch.dict("os.environ", {"PARTNER_GATEWAY_SURFACE": "public"})
    def test_public_surface_blocks_ops_dashboard(self) -> None:
        gw = PartnerGateway(
            recommendation_dsn="mysql://x",
            matchmaking_dsn="mysql://x",
            chat_dsn="mysql://x",
            db_pool_max=0,
        )
        status, body = dispatch_gateway_rest(
            gw,
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/v1/ops/async-jobs/dashboard",
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "surface_forbidden")


if __name__ == "__main__":
    unittest.main()
