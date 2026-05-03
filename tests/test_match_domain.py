import pathlib
import sys
import unittest
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain import (  # noqa: E402
    CaseStatus,
    CaseType,
    MatchEvent,
    PairStatus,
    ProfileRef,
    RelationStatus,
    pair_key,
    relation_key,
)


class MatchDomainTests(unittest.TestCase):
    def test_profile_ref_requires_identity(self):
        with self.assertRaises(ValueError):
            ProfileRef(source="mysql://root@127.0.0.1:3307/her?table=profiles")

    def test_relation_key_is_directional(self):
        owner = ProfileRef(source="mysql://a", profile_id=1001)
        target = ProfileRef(source="mysql://a", profile_id=1002)

        self.assertNotEqual(relation_key(owner, target), relation_key(target, owner))
        self.assertEqual(
            relation_key(owner, target),
            "mysql://a#profile:1001->mysql://a#profile:1002",
        )

    def test_pair_key_is_order_insensitive(self):
        left = ProfileRef(source="mysql://a", profile_id=1001)
        right = ProfileRef(source="mysql://a", user_key="user-b")

        self.assertEqual(pair_key(left, right), pair_key(right, left))
        self.assertIn("<->", pair_key(left, right))

    def test_match_event_to_dict_includes_contract_fields(self):
        event = MatchEvent(
            event_id="evt-1",
            event_type="relation_skipped",
            aggregate_type="relation",
            aggregate_id="rel-1",
            actor_type="user",
            actor_id="70001",
            source_service="recommendation-system",
            correlation_id="corr-1",
            idempotency_key="idem-1",
            occurred_at=datetime(2026, 5, 3, 9, 0, 0),
            payload={"cooldown_until": "2026-06-02 09:00:00"},
        )

        payload = event.to_dict()
        self.assertEqual(payload["event_type"], "relation_skipped")
        self.assertEqual(payload["aggregate_type"], "relation")
        self.assertEqual(payload["occurred_at"], "2026-05-03 09:00:00")
        self.assertEqual(payload["payload"]["cooldown_until"], "2026-06-02 09:00:00")

    def test_canonical_status_vocab_matches_design_doc(self):
        self.assertEqual(RelationStatus.COOLING.value, "cooling")
        self.assertEqual(RelationStatus.PROXY_INTRO_ACTIVE.value, "proxy_intro_active")
        self.assertEqual(PairStatus.NEEDS_REVALIDATION.value, "needs_revalidation")
        self.assertEqual(PairStatus.MUTUAL_ACCEPT.value, "mutual_accept")
        self.assertEqual(CaseType.MATCHMAKING.value, "matchmaking")
        self.assertEqual(CaseStatus.AWAITING_REPLY.value, "awaiting_reply")


if __name__ == "__main__":
    unittest.main()
