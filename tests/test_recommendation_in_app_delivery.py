from __future__ import annotations

import pathlib
import sys
import unittest


RECOMMENDATION_ROOT = pathlib.Path(__file__).resolve().parents[1] / "external-systems" / "partner-recommendation-system"
if str(RECOMMENDATION_ROOT) not in sys.path:
    sys.path.insert(0, str(RECOMMENDATION_ROOT))

from recommendation_system.in_app_delivery import build_in_app_card  # noqa: E402


class RecommendationInAppDeliveryTests(unittest.TestCase):
    def test_build_in_app_card_uses_match_explanation_when_matched_on_missing(self) -> None:
        card = build_in_app_card(
            {
                "score": 88,
                "candidate_name": "沈知意",
                "latest_payload": {
                    "name": "沈知意",
                    "score": 88,
                    "matched_on": [],
                    "match_explanation": {
                        "summary": "第一眼眼缘会更强，长相类型也更贴近你的偏好",
                    },
                    "profile": {
                        "age": 29,
                        "city": "杭州",
                        "job": "运营经理",
                        "verified_level": "photo",
                    },
                },
            },
            "杭州认真恋爱",
        )

        self.assertIn("眼缘点：第一眼眼缘会更强，长相类型也更贴近你的偏好", card["body"])


if __name__ == "__main__":
    unittest.main()
