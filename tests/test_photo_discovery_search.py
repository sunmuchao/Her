from __future__ import annotations

import unittest
from unittest import mock

from match_domain.photo_discovery_search import (
    search_hybrid_photo_candidates,
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
                "match_domain.photo_discovery_search._rerank_with_photo_bonus",
                return_value=[{"profile_id": 12, "final_score": 0.94, "appearance_summary": "成熟清爽"}],
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
                "match_domain.photo_discovery_search._rerank_with_photo_bonus",
                return_value=[{"profile_id": 12, "final_score": 0.88, "appearance_summary": "阳光清爽"}],
            ),
        ):
            result = search_style_candidates(
                source_dsn="mysql://persona",
                image_source="https://img.her.local/outdoor-clean-style.jpg",
            )

        self.assertTrue(result["saved"])
        self.assertIn("阳光", result["query_text"])
        self.assertEqual(result["results"][0]["profile_id"], 12)

    def test_search_celebrity_face_candidates_logs_stages_and_uses_photo_url(self):
        with (
            mock.patch(
                "match_domain.face_embedding_extractor.extract_face_embedding",
                return_value={
                    "success": True,
                    "face_embedding": [0.1, 0.2, 0.3],
                    "face_detection_confidence": 0.98,
                },
            ),
            mock.patch(
                "match_domain.photo_discovery_search.FaceSimilaritySearcher.search",
                return_value=[mock.Mock(profile_id=12, similarity=0.77), mock.Mock(profile_id=18, similarity=0.74)],
            ),
            mock.patch(
                "match_domain.photo_discovery_search._rerank_with_photo_bonus",
                return_value=[{"profile_id": 12, "final_score": 0.91, "appearance_summary": "清爽自然"}],
            ) as rerank_mock,
            mock.patch("match_domain.photo_discovery_search.emit_photo_search_event") as emit_mock,
        ):
            with self.assertLogs("match_domain.photo_discovery_search", level="INFO") as logs:
                result = search_celebrity_face_candidates(
                    source_dsn="mysql://persona",
                    photo_url="https://img.her.local/tian-xiwei.jpg",
                    celebrity_name="田曦薇",
                    requester_profile_id=10001,
                    requester_user_key="user-1",
                )

        self.assertTrue(result["saved"])
        self.assertEqual(result["celebrity_reference"]["name"], "田曦薇")
        self.assertEqual(result["celebrity_reference"]["photo_url"], "https://img.her.local/tian-xiwei.jpg")
        self.assertEqual(result["results"][0]["profile_id"], 12)
        rerank_mock.assert_called_once()
        emit_mock.assert_called_once_with(
            user_key="user-1",
            search_type="celebrity_face_similarity",
            stage="search_completed",
            result_count=1,
            success=True,
        )
        joined_logs = "\n".join(logs.output)
        self.assertIn("stage=request_received", joined_logs)
        self.assertIn("stage=reference_fetch_start", joined_logs)
        self.assertIn("stage=embedding_compute_done", joined_logs)
        self.assertIn("stage=search_candidates_start", joined_logs)
        self.assertIn("stage=search_candidates_done", joined_logs)
        self.assertIn("stage=rerank_start", joined_logs)
        self.assertIn("stage=rerank_done", joined_logs)
        self.assertIn("stage=response_ready", joined_logs)

    def test_search_celebrity_face_candidates_logs_failure_stage(self):
        with (
            mock.patch(
                "match_domain.face_embedding_extractor.extract_face_embedding",
                return_value={"success": False, "error": "照片链接无法访问。请确认照片链接正确"},
            ),
            mock.patch("match_domain.photo_discovery_search.FaceSimilaritySearcher.search") as search_mock,
        ):
            with self.assertLogs("match_domain.photo_discovery_search", level="INFO") as logs:
                result = search_celebrity_face_candidates(
                    source_dsn="mysql://persona",
                    photo_url="https://img.her.local/missing.jpg",
                    celebrity_name="田曦薇",
                )

        self.assertFalse(result["saved"])
        self.assertEqual(result["result_count"], 0)
        self.assertIn("照片链接无法访问", result["error"])
        search_mock.assert_not_called()
        self.assertIn("stage=embedding_compute_failed", "\n".join(logs.output))

    def test_search_hybrid_photo_candidates_merges_face_and_style(self):
        with (
            mock.patch(
                "match_domain.photo_discovery_search.search_similar_face_candidates",
                return_value={
                    "saved": True,
                    "results": [
                        {"profile_id": 12, "final_score": 1.31, "base_score": 0.91, "photo_bonus": 12.0},
                    ],
                },
            ),
            mock.patch(
                "match_domain.photo_discovery_search.search_style_candidates",
                return_value={
                    "saved": True,
                    "query_text": "清爽自然",
                    "results": [
                        {"profile_id": 12, "final_score": 1.24, "base_score": 0.82, "photo_bonus": 10.0},
                        {"profile_id": 18, "final_score": 1.11, "base_score": 0.76, "photo_bonus": 9.0},
                    ],
                },
            ),
        ):
            result = search_hybrid_photo_candidates(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                image_source="https://img.her.local/reference.jpg",
                query_text="我喜欢这种感觉",
            )

        self.assertTrue(result["saved"])
        self.assertEqual(result["search_type"], "hybrid_photo_similarity")
        self.assertEqual(result["results"][0]["profile_id"], 12)
        self.assertIn("face_similarity", result["results"][0]["search_sources"])


if __name__ == "__main__":
    unittest.main()
