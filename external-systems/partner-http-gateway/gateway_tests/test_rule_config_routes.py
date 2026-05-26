"""Gateway tests for ops rule-config routes (§13.5)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from gateway.rule_config_routes import (
    dispatch_rule_config_rest,
    rest_ops_rule_config_active,
)


class RuleConfigRouteTests(unittest.TestCase):
    def test_dispatch_unknown_path_returns_none(self):
        gateway = MagicMock()
        self.assertIsNone(
            dispatch_rule_config_rest(gateway, {}, "GET", "/v1/ops/unknown"),
        )

    def test_active_requires_auth(self):
        gateway = MagicMock()
        gateway._current_actor.return_value = None
        status, body = rest_ops_rule_config_active(gateway, {})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")


if __name__ == "__main__":
    unittest.main()
