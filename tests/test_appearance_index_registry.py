from __future__ import annotations

import unittest
from unittest import mock

from match_domain.appearance_index_registry import (
    APPEARANCE_INDEX_KEYS,
    build_appearance_index_rollback_plan,
    build_appearance_index_rollout_plan,
    normalize_appearance_index_versions,
    trigger_appearance_index_rebuild,
)


class AppearanceIndexRegistryTests(unittest.TestCase):
    def test_normalize_appearance_index_versions_fills_defaults(self):
        payload = normalize_appearance_index_versions({"face_embedding_index": "face_idx_v2"})
        self.assertEqual(set(payload.keys()), set(APPEARANCE_INDEX_KEYS))
        self.assertEqual(payload["face_embedding_index"], "face_idx_v2")
        self.assertEqual(payload["appearance_profile_index"], "milvus_lite_v1")

    def test_build_rollout_plan_marks_rebuild_when_versions_changed(self):
        plan = build_appearance_index_rollout_plan(
            current_versions={"face_embedding_index": "face_idx_v1"},
            candidate_versions={"face_embedding_index": "face_idx_v2"},
            rollout_ratio=0.2,
            canary_profile_ids=[11, 12],
        )
        self.assertTrue(plan["requires_rebuild"])
        self.assertEqual(plan["rollout_ratio"], 0.2)
        self.assertEqual(plan["canary_profile_ids"], [11, 12])
        self.assertIn("face_embedding_index", plan["changed_keys"])

    def test_build_rollback_plan_points_back_to_target(self):
        plan = build_appearance_index_rollback_plan(
            current_versions={"appearance_profile_index": "style_idx_v2"},
            rollback_target_versions={"appearance_profile_index": "style_idx_v1"},
            reason="latency_regression",
        )
        self.assertTrue(plan["requires_rebuild"])
        self.assertEqual(plan["reason"], "latency_regression")
        self.assertEqual(plan["rollback_target_versions"]["appearance_profile_index"], "style_idx_v1")

    def test_trigger_appearance_index_rebuild_collects_per_profile_results(self):
        face_rebuild = mock.Mock(
            side_effect=[
                {"saved": True, "version": 2},
                {"saved": False, "error": "face_missing"},
            ]
        )
        style_rebuild = mock.Mock(
            side_effect=[
                {"saved": True, "version": 5},
                {"saved": True, "version": 5},
            ]
        )
        result = trigger_appearance_index_rebuild(
            source_dsn="mysql://persona",
            profile_ids=[101, 102],
            target_versions={"appearance_profile_index": "style_idx_v5"},
            batch_size=1,
            rebuild_face_index_fn=face_rebuild,
            rebuild_style_index_fn=style_rebuild,
        )
        self.assertEqual(result["total_profiles"], 2)
        self.assertEqual(result["succeeded"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["processed"][0]["target_versions"]["appearance_profile_index"], "style_idx_v5")


if __name__ == "__main__":
    unittest.main()
