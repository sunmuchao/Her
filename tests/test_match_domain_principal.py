"""Tests for §13.3 identity vocabulary helpers."""

from __future__ import annotations

import unittest

from match_domain.principal import (
    coalesce_profile_id_param,
    coalesce_profile_requester,
    principal_identity_table,
    profile_ref_from_profile_id,
    sync_user_block_from_principal,
    user_key_from_profile_id,
)


class MatchDomainPrincipalTests(unittest.TestCase):
    def test_coalesce_profile_id_param_prefers_first_alias(self) -> None:
        self.assertEqual(coalesce_profile_id_param(7, 9), 7)
        self.assertEqual(coalesce_profile_id_param(None, 12), 12)

    def test_coalesce_profile_requester_prefers_profile_id(self) -> None:
        self.assertEqual(coalesce_profile_requester(profile_id=7, requester_id=9), 7)

    def test_user_key_and_profile_ref(self) -> None:
        self.assertEqual(user_key_from_profile_id(42), "42")
        self.assertEqual(profile_ref_from_profile_id(42), "profile:42")

    def test_sync_user_block_from_principal(self) -> None:
        merged = sync_user_block_from_principal(
            {"user_id": "u1"},
            {
                "user_id": "u1",
                "profile_id": 11,
                "requester_id": 11,
                "user_key": "11",
            },
        )
        self.assertEqual(merged["profile_id"], 11)
        self.assertEqual(merged["requester_id"], 11)
        self.assertEqual(merged["user_key"], "11")

    def test_identity_table_documents_core_fields(self) -> None:
        fields = {row["field"] for row in principal_identity_table()}
        self.assertTrue({"user_id", "profile_id", "requester_id", "user_key"}.issubset(fields))


if __name__ == "__main__":
    unittest.main()
