"""Tests for collected metadata helpers."""

from __future__ import annotations

import unittest

from match_domain.collected_metadata import build_collected_items, infer_source_channel


class CollectedMetadataTests(unittest.TestCase):
    def test_infer_source_channel_from_basis(self) -> None:
        self.assertEqual(infer_source_channel(basis="discovery_agent"), "matchmaker_chat")
        self.assertEqual(infer_source_channel(conversation_ref="discovery/s-1"), "matchmaker_chat")

    def test_build_collected_items_requires_explicit_obs_for_tags(self) -> None:
        items = build_collected_items(
            {"target_cities": "上海", "must_have_tags": "情绪稳定"},
            observations=[{"field_name": "target_cities", "source_type": "explicit", "created_at": "2026-01-01"}],
        )
        self.assertIn("target_cities", items)
        self.assertNotIn("must_have_tags", items)

    def test_build_collected_items_includes_tag_with_explicit_obs(self) -> None:
        items = build_collected_items(
            {"must_have_tags": "情绪稳定"},
            observations=[
                {
                    "field_name": "must_have_tags",
                    "source_type": "explicit",
                    "created_at": "2026-01-01",
                    "evidence_text": "对话中明确提到",
                    "source_channel": "matchmaker_chat",
                }
            ],
        )
        self.assertEqual(items["must_have_tags"]["value"], "情绪稳定")
        self.assertEqual(items["must_have_tags"]["source_channel"], "matchmaker_chat")


if __name__ == "__main__":
    unittest.main()
