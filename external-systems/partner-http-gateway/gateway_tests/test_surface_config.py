"""Tests for §13.4 gateway surface configuration."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from gateway.surface_config import (
    SURFACE_OPS,
    SURFACE_PUBLIC,
    classify_rest_path,
    is_jsonrpc_allowed,
    is_rest_path_allowed,
)


class SurfaceConfigTests(unittest.TestCase):
    def test_classify_rest_path(self) -> None:
        self.assertEqual(classify_rest_path("/health"), "health")
        self.assertEqual(classify_rest_path("/v1/ops/workbench/summary"), "ops")
        self.assertEqual(classify_rest_path("/v1/recommendation/cards"), "public")

    @patch.dict("os.environ", {"PARTNER_GATEWAY_SURFACE": "public"})
    def test_public_surface_blocks_ops_routes(self) -> None:
        self.assertTrue(is_rest_path_allowed("/v1/recommendation/cards", "GET"))
        self.assertFalse(is_rest_path_allowed("/v1/ops/overrides", "POST"))

    @patch.dict("os.environ", {"PARTNER_GATEWAY_SURFACE": "ops"})
    def test_ops_surface_blocks_user_routes(self) -> None:
        self.assertTrue(is_rest_path_allowed("/v1/ops/async-jobs/dashboard", "GET"))
        self.assertFalse(is_rest_path_allowed("/v1/recommendation/cards", "GET"))

    @patch.dict("os.environ", {"PARTNER_GATEWAY_ENABLE_JSONRPC": "0", "PARTNER_GATEWAY_SURFACE": "all"})
    def test_jsonrpc_disabled(self) -> None:
        self.assertFalse(is_jsonrpc_allowed())

    @patch.dict("os.environ", {"PARTNER_GATEWAY_ENABLE_JSONRPC": "1", "PARTNER_GATEWAY_SURFACE": SURFACE_PUBLIC})
    def test_jsonrpc_blocked_on_public_surface(self) -> None:
        self.assertFalse(is_jsonrpc_allowed())

    @patch.dict("os.environ", {"PARTNER_GATEWAY_ENABLE_JSONRPC": "1", "PARTNER_GATEWAY_SURFACE": SURFACE_OPS})
    def test_jsonrpc_blocked_on_ops_surface(self) -> None:
        self.assertFalse(is_jsonrpc_allowed())


if __name__ == "__main__":
    unittest.main()
