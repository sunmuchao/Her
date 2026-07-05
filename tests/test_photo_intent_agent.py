from __future__ import annotations

import unittest
from unittest import mock

from match_domain.photo_intent_agent import (
    build_photo_recommendation_explanation_prompt,
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

    def test_detect_photo_preference_intent_for_dynamic_celebrity_name(self):
        intent = detect_photo_preference_intent("想找像迪丽热巴那种，眼睛大一点")
        self.assertEqual(intent.mode, "celebrity")
        self.assertEqual(intent.celebrity_name, "迪丽热巴")
        self.assertIn("eye_size_score", intent.attribute_filters)

    def test_detect_photo_preference_intent_prefers_hybrid_when_only_image_goal_is_unclear(self):
        intent = detect_photo_preference_intent("", image_source="data:image/jpeg;base64,abc")
        self.assertEqual(intent.mode, "hybrid")
        self.assertTrue(intent.image_understanding["has_image"])
        self.assertGreater(intent.confidence, 0.5)

    def test_translate_intent_to_search_plan(self):
        intent = detect_photo_preference_intent("成熟型，眼睛大一点")
        plan = translate_intent_to_search_plan(intent)
        self.assertEqual(plan["mode"], "style")
        self.assertIn("eye_size_score", plan["attribute_filters"])

    def test_translate_intent_to_search_plan_contains_agent_reasoning(self):
        intent = detect_photo_preference_intent("我喜欢这种感觉", image_source="data:image/jpeg;base64,abc")
        plan = translate_intent_to_search_plan(intent)
        self.assertIn("routing_reasons", plan)
        self.assertIn("image_understanding", plan)

    def test_execute_photo_preference_search_routes_by_mode(self):
        celebrity_intent = detect_photo_preference_intent("像刘亦菲")
        face_intent = detect_photo_preference_intent("找像这张脸")
        style_intent = detect_photo_preference_intent("阳光清爽")
        hybrid_intent = detect_photo_preference_intent("帮我看看这张图适合找什么人", image_source="https://img.her.local/ref.jpg")

        with (
            mock.patch("match_domain.photo_intent_agent.search_celebrity_face_candidates", return_value={"saved": True, "mode": "celebrity"}) as mocked_celeb,
            mock.patch("match_domain.photo_intent_agent.search_hybrid_photo_candidates", return_value={"saved": True, "mode": "hybrid"}) as mocked_hybrid,
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
            hybrid_result = execute_photo_preference_search(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                intent=hybrid_intent,
                image_source="https://img.her.local/hybrid.jpg",
            )

        mocked_celeb.assert_called_once()
        mocked_hybrid.assert_called_once()
        mocked_face.assert_called_once()
        mocked_style.assert_called_once()
        self.assertIn("attribute_filters", mocked_celeb.call_args.kwargs)
        self.assertEqual(celeb_result["mode"], "celebrity")
        self.assertEqual(face_result["mode"], "face")
        self.assertEqual(style_result["mode"], "style")
        self.assertEqual(hybrid_result["mode"], "hybrid")

    def test_build_photo_recommendation_explanation(self):
        intent = detect_photo_preference_intent("阳光清爽")
        payload = build_photo_recommendation_explanation(
            intent=intent,
            candidate_row={"appearance_summary": "阳光清爽，偏自然。"},
            matched_reasons=["同城", "目标一致"],
        )
        self.assertEqual(payload["mode"], "style")
        self.assertIn("同城", payload["highlights"])
        self.assertEqual(payload["prompt"]["prompt_version"], "photo-explanation-v1")
        self.assertIn("confidence", payload["prompt"]["facts"])

    def test_build_photo_recommendation_explanation_prompt(self):
        intent = detect_photo_preference_intent("想找像迪丽热巴那种，眼睛大一点")
        prompt = build_photo_recommendation_explanation_prompt(
            intent=intent,
            candidate_row={"display_name": "周宁", "appearance_summary": "明艳大气，眼部存在感强。"},
            matched_reasons=["同城"],
        )
        self.assertIn("外貌解释助手", prompt["system_prompt"])
        self.assertIn("周宁", prompt["user_prompt"])
        self.assertEqual(prompt["facts"]["candidate_name"], "周宁")
        self.assertIn("eye_size_score", prompt["facts"]["attribute_filters"])


if __name__ == "__main__":
    unittest.main()
