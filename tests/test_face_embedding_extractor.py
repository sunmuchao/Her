from __future__ import annotations

import unittest
from unittest import mock
from urllib.error import URLError

from match_domain import face_embedding_extractor as extractor


class FaceEmbeddingExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        extractor._face_embedding_cache.clear_cache()

    def tearDown(self) -> None:
        extractor._face_embedding_cache.clear_cache()

    def test_warmup_face_embedding_model_logs_success(self):
        fake_model = object()
        fake_deepface = mock.Mock()
        fake_deepface.build_model.return_value = fake_model

        with (
            mock.patch.object(extractor, "_lazy_import_deepface", return_value=(fake_deepface, object())),
            mock.patch.object(extractor.os, "makedirs"),
            mock.patch.object(extractor.os.path, "exists", return_value=True),
        ):
            with self.assertLogs("match_domain.face_embedding_extractor", level="INFO") as logs:
                result = extractor.warmup_face_embedding_model()

        self.assertTrue(result["success"])
        self.assertEqual(result["model_name"], extractor.FACE_EMBEDDING_MODEL_NAME)
        joined_logs = "\n".join(logs.output)
        self.assertIn("stage=model_load_start", joined_logs)
        self.assertIn("stage=model_load_done", joined_logs)

    def test_extract_face_embedding_remote_success_logs_stages_and_caches_result(self):
        fake_deepface = mock.Mock()
        fake_deepface.represent.return_value = [
            {
                "embedding": [0.1, 0.2, 0.3],
                "confidence": 0.99,
                "facial_area": {"x": 1, "y": 2, "w": 3, "h": 4},
            }
        ]
        fake_response = mock.MagicMock()
        fake_response.read.return_value = b"x" * 2048
        fake_urlopen = mock.MagicMock()
        fake_urlopen.return_value.__enter__.return_value = fake_response
        fake_image = mock.Mock()
        fake_image.size = (256, 256)

        with (
            mock.patch.object(extractor, "_lazy_import_deepface", return_value=(fake_deepface, object())),
            mock.patch("urllib.request.urlopen", fake_urlopen),
            mock.patch("PIL.Image.open", return_value=fake_image),
            mock.patch.object(extractor, "warmup_face_embedding_model", return_value={"success": True}),
        ):
            with self.assertLogs("match_domain.face_embedding_extractor", level="INFO") as logs:
                first = extractor.extract_face_embedding("https://img.her.local/reference.jpg")
            second = extractor.extract_face_embedding("https://img.her.local/reference.jpg")

        self.assertTrue(first["success"])
        self.assertEqual(second, first)
        self.assertEqual(fake_deepface.represent.call_count, 1)
        joined_logs = "\n".join(logs.output)
        self.assertIn("stage=request_received", joined_logs)
        self.assertIn("stage=reference_fetch_start", joined_logs)
        self.assertIn("stage=reference_fetch_done", joined_logs)
        self.assertIn("stage=embedding_compute_start", joined_logs)
        self.assertIn("stage=embedding_compute_done", joined_logs)

    def test_extract_face_embedding_returns_friendly_error_for_unreachable_url(self):
        fake_deepface = mock.Mock()

        with (
            mock.patch.object(extractor, "_lazy_import_deepface", return_value=(fake_deepface, object())),
            mock.patch("urllib.request.urlopen", side_effect=URLError("boom")),
        ):
            result = extractor.extract_face_embedding("https://img.her.local/missing.jpg")

        self.assertFalse(result["success"])
        self.assertIn("照片链接无法访问", result["error"])


if __name__ == "__main__":
    unittest.main()
