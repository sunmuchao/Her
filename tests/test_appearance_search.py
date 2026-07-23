from __future__ import annotations

import unittest
from unittest import mock

from match_domain.appearance_search import (
    AppearanceProfileEmbeddingExtractor,
    AppearanceStyleIndexBuilder,
    AppearanceStyleSearcher,
    AttributeFilterSearcher,
    CelebrityReferenceGallery,
    FaceSimilaritySearcher,
    FaceVectorIndexBuilder,
    HybridAppearanceRecallSearcher,
    UploadedReferenceFaceProcessor,
    search_profiles_by_reference_image,
)


class AppearanceSearchTests(unittest.TestCase):
    def test_appearance_profile_embedding_extractor_is_stable(self):
        left = AppearanceProfileEmbeddingExtractor.extract(
            appearance_summary="成熟清爽，偏温柔。",
            appearance_tags=["成熟感", "干净清爽"],
        )
        right = AppearanceProfileEmbeddingExtractor.extract(
            appearance_summary="成熟清爽，偏温柔。",
            appearance_tags=["成熟感", "干净清爽"],
        )
        self.assertEqual(len(left), 1024)
        self.assertEqual(left[:8], right[:8])

    def test_face_vector_index_builder_saves_face_embedding_to_vector_store(self):
        vector_store = mock.Mock()
        vector_store.save_vector_with_version.return_value = {"success": True, "version": 2}

        with mock.patch(
            "match_domain.appearance_search.load_profile_face_embeddings",
            return_value=[{"profile_id": 12, "embedding_json": [0.1, 0.2, 0.3]}],
        ):
            result = FaceVectorIndexBuilder.build_profile_index(
                source_dsn="mysql://persona",
                profile_id=12,
                vector_store=vector_store,
            )

        vector_store.save_vector_with_version.assert_called_once()
        self.assertTrue(result["saved"])
        self.assertEqual(result["vector_type"], "face_embedding")

    def test_appearance_style_index_builder_saves_summary_vector(self):
        vector_store = mock.Mock()
        vector_store.save_vector_with_version.return_value = {"success": True, "version": 1}
        with mock.patch(
            "match_domain.appearance_search.load_candidate_photo_features",
            return_value={
                12: {
                    "appearance_summary": "成熟清爽，偏温柔。",
                    "appearance_tags_json": [{"label": "成熟感"}, {"label": "干净清爽"}],
                }
            },
        ):
            result = AppearanceStyleIndexBuilder.build_profile_index(
                source_dsn="mysql://persona",
                profile_id=12,
                vector_store=vector_store,
            )

        self.assertTrue(result["saved"])
        vector_store.save_vector_with_version.assert_called_once()

    def test_face_similarity_searcher_aggregates_multi_hits(self):
        vector_store = mock.Mock()
        vector_store.search_similar_users.return_value = [
            {"user_id": 12, "similarity": 0.91, "raw_text": "hit-a"},
            {"user_id": 12, "similarity": 0.83, "raw_text": "hit-b"},
            {"user_id": 18, "similarity": 0.79, "raw_text": "hit-c"},
        ]

        results = FaceSimilaritySearcher.search(
            source_dsn="mysql://persona",
            reference_embedding=[0.1, 0.2, 0.3],
            vector_store=vector_store,
            top_k=5,
        )

        self.assertEqual(results[0].profile_id, 12)
        self.assertGreater(results[0].similarity, results[1].similarity)

    def test_appearance_style_searcher_falls_back_to_feature_rows(self):
        with (
            mock.patch("match_domain.appearance_search.list_profile_photo_feature_rows", return_value=[
                {
                    "profile_id": 12,
                    "appearance_summary": "阳光清爽，偏自然。",
                    "appearance_tags_json": [{"label": "阳光感"}, {"label": "干净清爽"}],
                },
                {
                    "profile_id": 18,
                    "appearance_summary": "成熟利落，偏精致。",
                    "appearance_tags_json": [{"label": "成熟感"}, {"label": "利落精致"}],
                },
            ]),
            mock.patch("match_domain.vector_store_lite.VectorStoreLite", side_effect=RuntimeError("missing")),
        ):
            results = AppearanceStyleSearcher.search_by_text(
                source_dsn="mysql://persona",
                query_text="阳光 清爽",
                top_k=5,
            )

        self.assertEqual(results[0]["profile_id"], 12)

    def test_hybrid_appearance_recall_searcher_applies_tag_bonus(self):
        with mock.patch(
            "match_domain.appearance_search.AppearanceStyleSearcher.search_by_text",
            return_value=[
                {"profile_id": 12, "similarity": 0.72, "tags": ["阳光", "清爽"], "raw_text": "阳光清爽"},
                {"profile_id": 18, "similarity": 0.74, "tags": ["成熟"], "raw_text": "成熟利落"},
            ],
        ):
            results = HybridAppearanceRecallSearcher.search(
                source_dsn="mysql://persona",
                query_text="阳光 清爽",
                top_k=5,
            )

        self.assertEqual(results[0]["profile_id"], 12)
        self.assertGreater(results[0]["similarity"], results[1]["similarity"])

    def test_attribute_filter_searcher_filters_and_explains(self):
        with (
            mock.patch("match_domain.appearance_search.list_profile_photo_feature_rows", return_value=[
                {"profile_id": 12, "clean_score": 81},
                {"profile_id": 18, "clean_score": 50},
            ]),
            mock.patch(
                "match_domain.appearance_search.load_profile_face_attributes",
                return_value={
                    12: {"eye_size_score": 72, "youthfulness_score": 68, "attribute_source": "landmark", "attribute_confidence": 0.82},
                    18: {"eye_size_score": 42, "youthfulness_score": 45, "attribute_source": "landmark", "attribute_confidence": 0.79},
                },
            ),
        ):
            results = AttributeFilterSearcher.search(
                source_dsn="mysql://persona",
                filters={"eye_size_score": {"min": 60}, "clean_score": {"min": 70}},
                top_k=5,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["profile_id"], 12)
        self.assertIn("eye_size_score", results[0]["explanation"])

    def test_attribute_filter_searcher_skips_non_landmark_face_attributes(self):
        with (
            mock.patch("match_domain.appearance_search.list_profile_photo_feature_rows", return_value=[
                {"profile_id": 12, "clean_score": 81},
                {"profile_id": 18, "clean_score": 88},
            ]),
            mock.patch(
                "match_domain.appearance_search.load_profile_face_attributes",
                return_value={
                    12: {"eye_size_score": 72, "attribute_source": "landmark", "attribute_confidence": 0.81},
                    18: {"eye_size_score": 75, "attribute_source": "heuristic_fallback", "attribute_confidence": 0.95},
                },
            ),
        ):
            results = AttributeFilterSearcher.search(
                source_dsn="mysql://persona",
                filters={"eye_size_score": {"min": 60}},
                top_k=5,
            )

        self.assertEqual([item["profile_id"] for item in results], [12])

    def test_uploaded_reference_face_processor_and_search_job(self):
        processed = UploadedReferenceFaceProcessor.process(
            image_source="https://img.her.local/reference.jpg",
            requester_profile_id=9,
        )
        self.assertTrue(processed["saved"])
        self.assertEqual(processed["embedding_dim"], 16)

        with (
            mock.patch(
                "match_domain.appearance_search.FaceSimilaritySearcher.search",
                return_value=[],
            ),
            mock.patch(
                "match_domain.appearance_search.create_reference_face_search_job",
                return_value={"saved": True},
            ) as mocked_job,
        ):
            result = search_profiles_by_reference_image(
                source_dsn="mysql://persona",
                requester_user_key="user-1",
                requester_profile_id=9,
                image_source="https://img.her.local/reference.jpg",
            )

        self.assertTrue(result["saved"])
        mocked_job.assert_called_once()

    def test_celebrity_reference_gallery_searches_by_name(self):
        results = CelebrityReferenceGallery.search_by_name("刘亦菲", top_k=2)
        self.assertEqual(len(results), 2)
        self.assertIn("name", results[0])

    def test_celebrity_reference_gallery_extracts_name_candidates(self):
        candidates = CelebrityReferenceGallery.extract_name_candidates("我想找像迪丽热巴那种感觉")
        self.assertIn("迪丽热巴", candidates)

    def test_celebrity_reference_gallery_prefers_online_reference_when_available(self):
        with mock.patch(
            "match_domain.appearance_search.CelebrityReferenceGallery._online_reference_candidates",
            return_value=[
                {
                    "name": "迪丽热巴",
                    "source": "https://upload.wikimedia.org/fake/dilireba.jpg",
                    "provider": "wikipedia_zh",
                    "similarity": 1.0,
                }
            ],
        ):
            results = CelebrityReferenceGallery.search_by_name("迪丽热巴", top_k=1)
            embedding = CelebrityReferenceGallery.reference_embedding_for_name("迪丽热巴")

        self.assertEqual(results[0]["provider"], "wikipedia_zh")
        self.assertEqual(results[0]["name"], "迪丽热巴")
        self.assertEqual(len(embedding), 16)


if __name__ == "__main__":
    unittest.main()
