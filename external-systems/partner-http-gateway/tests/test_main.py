from __future__ import annotations

import os
import unittest
from unittest import mock

import gateway.__main__ as gateway_main


class GatewayMainTests(unittest.TestCase):
    def test_should_warmup_face_model_defaults_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(gateway_main._should_warmup_face_model())

    def test_should_warmup_face_model_respects_disabled_values(self):
        for raw in ("0", "false", "off", "no"):
            with self.subTest(raw=raw):
                with mock.patch.dict(os.environ, {"HER_FACE_MODEL_WARMUP_ON_STARTUP": raw}, clear=True):
                    self.assertFalse(gateway_main._should_warmup_face_model())

    def test_warmup_startup_dependencies_logs_skip_when_disabled(self):
        with mock.patch.dict(os.environ, {"HER_FACE_MODEL_WARMUP_ON_STARTUP": "0"}, clear=True):
            with self.assertLogs("gateway.__main__", level="INFO") as logs:
                gateway_main._warmup_startup_dependencies()

        self.assertIn("跳过启动预热", "\n".join(logs.output))

    def test_warmup_startup_dependencies_logs_success(self):
        with (
            mock.patch.dict(os.environ, {"HER_FACE_MODEL_WARMUP_ON_STARTUP": "1"}, clear=True),
            mock.patch(
                "match_domain.face_embedding_extractor.warmup_face_embedding_model",
                return_value={"success": True, "model_name": "Facenet512", "weights_path": "/tmp/facenet512_weights.h5"},
            ),
        ):
            with self.assertLogs("gateway.__main__", level="INFO") as logs:
                gateway_main._warmup_startup_dependencies()

        joined_logs = "\n".join(logs.output)
        self.assertIn("启动预热完成", joined_logs)
        self.assertIn("Facenet512", joined_logs)

    def test_warmup_startup_dependencies_logs_warning_on_failure(self):
        with (
            mock.patch.dict(os.environ, {"HER_FACE_MODEL_WARMUP_ON_STARTUP": "1"}, clear=True),
            mock.patch(
                "match_domain.face_embedding_extractor.warmup_face_embedding_model",
                return_value={"success": False, "model_name": "Facenet512", "error": "boom"},
            ),
        ):
            with self.assertLogs("gateway.__main__", level="WARNING") as logs:
                gateway_main._warmup_startup_dependencies()

        joined_logs = "\n".join(logs.output)
        self.assertIn("启动预热失败", joined_logs)
        self.assertIn("boom", joined_logs)


if __name__ == "__main__":
    unittest.main()
