from __future__ import annotations

import unittest
from unittest import mock

from match_domain.photo_intent_agent import (
    build_photo_recommendation_explanation,
    detect_photo_preference_intent,
    execute_photo_preference_search,
    translate_intent_to_search_plan,
)


class PhotoIntentAgentTests(unittest.TestCase):
    def test_detect_photo_preference_intent_for_style(self):
        intent = detect_photo_preference_intent("我想找阳光一点、清爽一点的")
        self.assertEqual(intent.mode, "style")
        self.assertIn("sunny_score", intent.attribute_filters)
        self.assertIn("清爽", intent.query_text)

    def test_detect_photo_preference_intent_for_celebrity(self):
        intent = detect_photo_preference_intent("找像刘亦菲那种感觉")
        self.assertEqual(intent.mode, "celebrity")
        self.assertEqual(intent.celebrity_name, "刘亦菲")

    def test_translate_intent_to_search_plan(self):
        intent = detect_photo_preference_intent("成熟型，眼睛大一点")
        plan = translate_intent_to_search_plan(intent)
        self.assertEqual(plan["mode"], "style")
        self.assertIn("eye_size_score", plan["attribute_filters"])

    def test_execute_photo_preference_search_routes_by_mode(self):
        celebrity_intent = detect_photo_preference_intent("像刘亦菲")
        face_intent = detect_photo_preference_intent("找像这张脸")
        style_intent = detect_photo_preference_intent("阳光清爽")

        with (
            mock.patch("match_domain.photo_intent_agent.search_celebrity_face_candidates", return_value={"saved": True, "mode": "celebrity"}) as mocked_celeb,
            mock.patch("match_domain.photo_intent_agent.search_similar_face_candidates", return_value={"saved": True, "mode": "face"}) as mocked_face,
            mock.patch("match_domain.photo_intent_agent.search_style_candidates", return_value={"saved": True, "mode": "style"}) as mocked_style,
        ):
            celeb_result = execute_photo_preference_search(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                intent=celebrity_intent,
            )
            face_result = execute_photo_preference_search(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                intent=face_intent,
                image_source="https://img.her.local/ref.jpg",
            )
            style_result = execute_photo_preference_search(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                intent=style_intent,
                image_source="https://img.her.local/style.jpg",
            )

        mocked_celeb.assert_called_once()
        mocked_face.assert_called_once()
        mocked_style.assert_called_once()
        self.assertEqual(celeb_result["mode"], "celebrity")
        self.assertEqual(face_result["mode"], "face")
        self.assertEqual(style_result["mode"], "style")

    def test_build_photo_recommendation_explanation(self):
        intent = detect_photo_preference_intent("阳光清爽")
        payload = build_photo_recommendation_explanation(
            intent=intent,
            candidate_row={"appearance_summary": "阳光清爽，偏自然。"},
            matched_reasons=["同城", "目标一致"],
        )
        self.assertEqual(payload["mode"], "style")
        self.assertIn("同城", payload["highlights"])


if __name__ == "__main__":
    unittest.main()
