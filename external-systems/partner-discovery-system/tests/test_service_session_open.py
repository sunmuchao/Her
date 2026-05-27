"""Tests for profile-first session open helpers."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

DISCOVERY_ROOT = Path(__file__).resolve().parents[1]
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.service_session_open import (  # noqa: E402
    PROFILE_FIRST_LOW_QUALITY_HINT,
    build_profile_first_open_result,
    criteria_labels_from_search_criteria,
)


class ProfileFirstSessionOpenTests(unittest.TestCase):
    def test_criteria_labels_use_human_readable_goal(self) -> None:
        labels = criteria_labels_from_search_criteria(
            {
                "cities": ["上海"],
                "gender": "female",
                "age_min": 26,
                "age_max": 36,
                "relationship_goals": ["dating", "认真恋爱"],
            }
        )
        self.assertIn("上海", labels)
        self.assertIn("女", labels)
        self.assertIn("26-36岁", labels)
        self.assertIn("先谈恋爱", labels)

    def test_low_quality_results_append_hint(self) -> None:
        result = build_profile_first_open_result(
            {
                "has_match": True,
                "results": [{"id": 9009, "score": 21}],
                "pool_summary": {"scanned_count": 2},
            },
            criteria_labels=["上海", "女", "26-36岁", "先谈恋爱"],
        )
        message = result.decision.assistant_message
        self.assertIn(PROFILE_FIRST_LOW_QUALITY_HINT, message)


if __name__ == "__main__":
    unittest.main()
