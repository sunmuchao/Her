from __future__ import annotations

import unittest

from match_domain import (
    canonical_case_status_value,
    matchmaking_relation_key,
    recommendation_relation_key,
)


class StatusVocabTests(unittest.TestCase):
    def test_pending_outreach_maps_to_pending_contact(self) -> None:
        self.assertEqual(canonical_case_status_value("pending_outreach"), "pending_contact")
        self.assertEqual(canonical_case_status_value("awaiting_reply"), "awaiting_reply")


class RelationKeyUnificationTests(unittest.TestCase):
    def test_matchmaking_and_recommendation_share_relation_key_format(self) -> None:
        subscription = {
            "source": "mysql://demo/profiles",
            "requester_id": 1,
            "self_id": 70001,
        }
        member_low = {
            "source": "mysql://demo/profiles",
            "user_key": "requester:1",
            "self_id": 70001,
        }
        member_high = {
            "source": "mysql://demo/profiles",
            "user_key": "candidate:101",
            "self_id": 101,
        }
        rec_key = recommendation_relation_key(subscription, 101)
        mm_key = matchmaking_relation_key(member_low, member_high)
        self.assertEqual(rec_key, mm_key)
        self.assertIn("->", rec_key)
        self.assertNotIn("<->", rec_key)


if __name__ == "__main__":
    unittest.main()
