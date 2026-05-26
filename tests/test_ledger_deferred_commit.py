import unittest
from unittest.mock import MagicMock, patch

from relationship_ledger.runtime import commit_conn_with_ledger, defer_ledger_event, ledger_mirror_for_conn


class LedgerDeferredCommitTests(unittest.TestCase):
    def test_defer_flushes_after_commit(self) -> None:
        conn = MagicMock()
        calls: list[str] = []

        def fake_flush(entries):
            calls.append(f"flush:{len(entries)}")
            return []

        defer_ledger_event(
            conn,
            {
                "event": object(),
                "relation_key": "rel-1",
            },
        )
        self.assertEqual(len(ledger_mirror_for_conn(conn)), 1)
        with patch("relationship_ledger.runtime.flush_ledger_mirror", side_effect=fake_flush):
            commit_conn_with_ledger(conn)
        self.assertEqual(calls, ["flush:1"])
        self.assertEqual(ledger_mirror_for_conn(conn), [])


if __name__ == "__main__":
    unittest.main()
