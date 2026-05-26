"""Tests for §10.3 tech optimization validation and search snapshot cache."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]


class TechOptimizationEnvTests(unittest.TestCase):
    def test_validate_tech_optimization_env_passes_for_repo_defaults(self):
        env = os.environ.copy()
        env.update(
            {
                "HER_RELATION_LEDGER_READ_MODE": "ledger_primary",
                "HER_PROXY_INTRO_STORAGE": "matchmaking",
            }
        )
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate_tech_optimization_env.py"), "--skip-repo"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


class SearchSnapshotStoreTests(unittest.TestCase):
    def test_persist_and_read_roundtrip(self):
        from partner_search.search_cache import criteria_cache_key, get_cached_search_run, store_cached_search_run

        os.environ["PARTNER_SEARCH_CACHE_TTL_SECONDS"] = "120"
        os.environ["PARTNER_SEARCH_SNAPSHOT_PERSIST"] = "0"

        payload = {"results": [{"id": 1}], "result_count": 1}
        with mock.patch("partner_search.search_cache.get_persisted_search_run") as get_persisted:
            with mock.patch("partner_search.search_cache.store_persisted_search_run") as store_persisted:
                store_cached_search_run(
                    criteria={"gender": "女"},
                    self_id=100,
                    limit=5,
                    source="mysql://root@127.0.0.1:3307/her?table=profiles",
                    search_run=payload,
                )
                store_persisted.assert_called_once()
                key = store_persisted.call_args[0][0]
                self.assertTrue(key)

                get_persisted.return_value = None
                cached = get_cached_search_run(
                    criteria={"gender": "女"},
                    self_id=100,
                    limit=5,
                    source="mysql://root@127.0.0.1:3307/her?table=profiles",
                )
                self.assertEqual(cached, payload)
                get_persisted.assert_not_called()


if __name__ == "__main__":
    unittest.main()
