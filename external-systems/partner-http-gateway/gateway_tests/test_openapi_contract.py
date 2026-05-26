"""OpenAPI contract smoke tests for public Gateway REST (§10.3)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import yaml

from gateway.surface_config import classify_rest_path, is_rest_path_allowed


OPENAPI_PATH = (
    Path(__file__).resolve().parents[1] / "openapi" / "gateway-public-v1.yaml"
)


class OpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with OPENAPI_PATH.open(encoding="utf-8") as handle:
            cls.spec = yaml.safe_load(handle)

    def test_openapi_file_loads(self) -> None:
        self.assertTrue(str(self.spec["openapi"]).startswith("3.0"))
        paths = self.spec.get("paths") or {}
        self.assertIn("/health", paths)
        self.assertIn("/v1/search/profiles", paths)

    def test_public_surface_allows_contract_paths(self) -> None:
        paths = list((self.spec.get("paths") or {}).keys())
        with mock.patch.dict(
            "os.environ",
            {"PARTNER_GATEWAY_SURFACE": "public", "PARTNER_GATEWAY_ENABLE_JSONRPC": "0"},
        ):
            for path in paths:
                methods = ["GET", "POST"]
                allowed = any(is_rest_path_allowed(path, method) for method in methods)
                kind = classify_rest_path(path)
                self.assertTrue(
                    allowed or kind == "health",
                    msg=f"public surface must allow contract path {path}",
                )

    def test_contract_paths_are_not_ops_only(self) -> None:
        for path in (self.spec.get("paths") or {}):
            self.assertFalse(
                path.startswith("/v1/ops/"),
                msg=f"public contract must not include ops path {path}",
            )

    def test_spec_json_serializable(self) -> None:
        json.dumps(self.spec, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
