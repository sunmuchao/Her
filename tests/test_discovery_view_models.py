from __future__ import annotations

import pathlib
import sys
import unittest


DISCOVERY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "external-systems" / "partner-discovery-system"
if str(DISCOVERY_ROOT) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_ROOT))

from discovery_system.view_models import build_candidate_card  # noqa: E402


class DiscoveryViewModelsTests(unittest.TestCase):
    def test_build_candidate_card_falls_back_to_match_explanation(self) -> None:
        card = build_candidate_card(
            {
                "id": 3101,
                "name": "顾清和",
                "score": 92,
                "profile": {"age": 28, "city": "杭州", "job": "品牌策划", "education": "本科"},
                "match_explanation": {
                    "summary": "第一眼眼缘会更强，长相类型也更贴近你的偏好",
                    "highlights": ["第一眼眼缘会更强", "长相类型贴近你最近常点喜欢的那一挂"],
                },
            }
        )

        self.assertEqual(card["reason_summary"], "第一眼眼缘会更强，长相类型也更贴近你的偏好")
        self.assertEqual(
            card["match_highlights"],
            ["第一眼眼缘会更强", "长相类型贴近你最近常点喜欢的那一挂"],
        )


if __name__ == "__main__":
    unittest.main()
