from __future__ import annotations

import unittest
from unittest import mock

from match_domain.photo_discovery_search import (
    search_celebrity_face_candidates,
    search_similar_face_candidates,
    search_style_candidates,
)


class PhotoDiscoverySearchTests(unittest.TestCase):
    def test_search_similar_face_candidates_filters_and_reranks(self):
        with (
            mock.patch(
                "match_domain.photo_discovery_search.search_profiles_by_reference_image",
                return_value={
                    "saved": True,
                    "results": [
                        {"profile_id": 12, "similarity": 0.82},
                        {"profile_id": 18, "similarity": 0.79},
                    ],
                },
            ),
            mock.patch(
                "match_domain.photo_discovery_search.AttributeFilterSearcher.search",
                return_value=[{"profile_id": 12}],
            ),
            mock.patch(
                "match_domain.photo_discovery_search.load_candidate_photo_features",
                return_value={
                    12: {"appearance_summary": "成熟清爽", "appearance_score_global": 82, "photo_quality_score": 84, "photo_authenticity_score": 88},
                },
            ),
        ):
            result = search_similar_face_candidates(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                image_source="https://img.her.local/reference.jpg",
                attribute_filters={"clean_score": {"min": 70}},
            )

        self.assertTrue(result["saved"])
        self.assertEqual(result["results"][0]["profile_id"], 12)

    def test_search_style_candidates_builds_query_from_image_source(self):
        with (
            mock.patch(
                "match_domain.photo_discovery_search.AppearanceStyleSearcher.search_by_text",
                return_value=[{"profile_id": 12, "similarity": 0.75}],
            ),
            mock.patch(
                "match_domain.photo_discovery_search.load_candidate_photo_features",
                return_value={
                    12: {"appearance_summary": "阳光清爽", "appearance_score_global": 80, "photo_quality_score": 82, "photo_authenticity_score": 85},
                },
            ),
        ):
            result = search_style_candidates(
                source_dsn="mysql://persona",
                image_source="https://img.her.local/outdoor-clean-style.jpg",
            )

        self.assertTrue(result["saved"])
        self.assertIn("阳光", result["query_text"])
        self.assertEqual(result["results"][0]["profile_id"], 12)

    def test_search_celebrity_face_candidates_uses_reference_gallery(self):
        with (
            mock.patch(
                "match_domain.photo_discovery_search.FaceSimilaritySearcher.search",
                return_value=[mock.Mock(profile_id=12, similarity=0.77)],
            ),
            mock.patch(
                "match_domain.photo_discovery_search.load_candidate_photo_features",
                return_value={
                    12: {"appearance_summary": "清爽自然", "appearance_score_global": 79, "photo_quality_score": 81, "photo_authenticity_score": 84},
                },
            ),
        ):
            result = search_celebrity_face_candidates(
                source_dsn="mysql://persona",
                celebrity_name="刘亦菲",
            )

        self.assertTrue(result["saved"])
        self.assertEqual(result["celebrity_reference"]["name"], "刘亦菲")
        self.assertEqual(result["results"][0]["profile_id"], 12)


if __name__ == "__main__":
    unittest.main()
