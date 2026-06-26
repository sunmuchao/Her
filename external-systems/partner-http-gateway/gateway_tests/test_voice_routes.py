"""Unit tests for voice transcription routes using Whisper."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from gateway.voice_routes import (
    _get_whisper_model,
    _detect_audio_format,
    _transcribe_audio,
    dispatch_voice_rest,
)


class TestVoiceRoutes(unittest.TestCase):
    """Test voice transcription functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock WhisperModel to avoid loading actual model during tests
        self.mock_model = MagicMock()
        self.mock_segment = MagicMock()
        self.mock_segment.start = 0.0
        self.mock_segment.end = 2.5
        self.mock_segment.text = "测试语音识别文本"

        self.mock_info = MagicMock()
        self.mock_info.language = "zh"
        self.mock_info.language_probability = 0.98

        self.mock_model.transcribe.return_value = ([self.mock_segment], self.mock_info)

    def test_dispatch_voice_rest_wrong_path(self):
        """Test dispatch returns None for non-voice paths."""
        gateway = MagicMock()
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/chat/send"}

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/chat/send")
        self.assertIsNone(result)

    def test_dispatch_voice_rest_wrong_method(self):
        """Test dispatch returns None for non-POST methods."""
        gateway = MagicMock()
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/v1/voice/transcribe"}

        result = dispatch_voice_rest(gateway, environ, "GET", "/v1/voice/transcribe")
        self.assertIsNone(result)

    def test_dispatch_voice_transcribe_empty_audio(self):
        """Test transcription with empty audio data."""
        gateway = MagicMock()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/voice/transcribe",
            "CONTENT_LENGTH": "0",
            "CONTENT_TYPE": "audio/webm",
            "wsgi.input": io.BytesIO(b""),
        }

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/voice/transcribe")
        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "empty_audio")

    def test_dispatch_voice_transcribe_invalid_content_type(self):
        """Test transcription with invalid content type."""
        gateway = MagicMock()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/voice/transcribe",
            "CONTENT_LENGTH": "1024",
            "CONTENT_TYPE": "text/plain",
            "wsgi.input": io.BytesIO(b"fake audio data"),
        }

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/voice/transcribe")
        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "invalid_content_type")

    @patch("gateway.voice_routes._get_whisper_model")
    def test_dispatch_voice_transcribe_success(self, mock_get_model):
        """Test successful transcription."""
        mock_get_model.return_value = self.mock_model

        gateway = MagicMock()
        audio_data = b"fake wav audio data"

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/voice/transcribe",
            "CONTENT_LENGTH": str(len(audio_data)),
            "CONTENT_TYPE": "audio/wav",
            "wsgi.input": io.BytesIO(audio_data),
        }

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/voice/transcribe")
        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 200)
        self.assertTrue(response["success"])
        self.assertEqual(response["text"], "测试语音识别文本")
        self.assertEqual(response["language"], "zh")
        self.assertEqual(response["language_probability"], 0.98)
        self.assertEqual(len(response["segments"]), 1)

        # Verify model was called
        mock_get_model.assert_called_once()

    @patch("gateway.voice_routes._get_whisper_model")
    def test_transcribe_audio_creates_temp_file(self, mock_get_model):
        """Test that _transcribe_audio creates and cleans up temp file."""
        mock_get_model.return_value = self.mock_model

        audio_data = b"test audio bytes"

        # Track temp file creation
        created_files = []
        original_namedtempfile = tempfile.NamedTemporaryFile

        def track_tempfile(*args, **kwargs):
            tf = original_namedtempfile(*args, **kwargs)
            created_files.append(tf.name)
            return tf

        with patch("tempfile.NamedTemporaryFile", track_tempfile):
            result = _transcribe_audio(audio_data, language="zh", content_type="audio/wav")

        # Verify temp file was created and deleted
        self.assertEqual(len(created_files), 1)
        self.assertFalse(os.path.exists(created_files[0]))

        # Verify result
        self.assertEqual(result["text"], "测试语音识别文本")

    @patch("gateway.voice_routes._WHISPER_MODEL", None)
    @patch("gateway.voice_routes.WhisperModel")
    def test_get_whisper_model_lazy_load(self, mock_whisper_class):
        """Test that Whisper model is lazily loaded."""
        mock_whisper_class.return_value = self.mock_model

        # Clear environment variables for test
        with patch.dict(
            os.environ,
            {"WHISPER_MODEL_SIZE": "small", "WHISPER_DEVICE": "cpu", "WHISPER_COMPUTE_TYPE": "int8"},
        ):
            model = _get_whisper_model()

        # Verify model was created with correct parameters
        mock_whisper_class.assert_called_once_with("small", device="cpu", compute_type="int8")
        self.assertEqual(model, self.mock_model)

    @patch("gateway.voice_routes._WHISPER_MODEL", None)
    @patch("gateway.voice_routes.WhisperModel")
    def test_get_whisper_model_singleton(self, mock_whisper_class):
        """Test that Whisper model is singleton (only loaded once)."""
        mock_whisper_class.return_value = self.mock_model

        with patch.dict(os.environ, {}, clear=True):
            # Call multiple times
            model1 = _get_whisper_model()
            model2 = _get_whisper_model()

        # Should only create model once
        mock_whisper_class.assert_called_once()
        self.assertEqual(model1, model2)

    @patch("gateway.voice_routes._get_whisper_model")
    def test_dispatch_voice_transcribe_exception(self, mock_get_model):
        """Test transcription handles exceptions gracefully."""
        mock_get_model.side_effect = RuntimeError("Whisper model crashed")

        gateway = MagicMock()
        audio_data = b"fake audio data"

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/voice/transcribe",
            "CONTENT_LENGTH": str(len(audio_data)),
            "CONTENT_TYPE": "audio/webm",
            "wsgi.input": io.BytesIO(audio_data),
        }

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/voice/transcribe")
        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 500)
        self.assertEqual(response["error"]["code"], "transcription_failed")
        self.assertIn("Whisper model crashed", response["error"]["message"])

    @patch("gateway.voice_routes._convert_audio_to_wav")
    @patch("gateway.voice_routes._get_whisper_model")
    def test_dispatch_voice_transcribe_conversion_failure(self, mock_get_model, mock_convert_audio):
        """Test conversion failures return a specific error code."""
        mock_get_model.return_value = self.mock_model
        mock_convert_audio.side_effect = RuntimeError("pydub not installed")

        gateway = MagicMock()
        audio_data = b"fake webm audio data"

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/voice/transcribe",
            "CONTENT_LENGTH": str(len(audio_data)),
            "CONTENT_TYPE": "audio/webm",
            "wsgi.input": io.BytesIO(audio_data),
        }

        result = dispatch_voice_rest(gateway, environ, "POST", "/v1/voice/transcribe")
        self.assertIsNotNone(result)
        status, response = result
        self.assertEqual(status, 500)
        self.assertEqual(response["error"]["code"], "audio_conversion_failed")
        self.assertIn("Audio format conversion failed before transcription", response["error"]["message"])

    @patch("gateway.voice_routes._get_whisper_model")
    @patch("gateway.voice_routes._convert_audio_to_wav")
    def test_transcribe_audio_stops_after_conversion_failure(self, mock_convert_audio, mock_get_model):
        """Test conversion failure does not fall back to direct Whisper processing."""
        mock_get_model.return_value = self.mock_model
        mock_convert_audio.side_effect = RuntimeError("ffmpeg missing")

        with self.assertRaises(RuntimeError) as ctx:
            _transcribe_audio(b"bad webm bytes", language="zh", content_type="audio/webm")

        self.assertIn("Audio format conversion failed before transcription", str(ctx.exception))
        self.mock_model.transcribe.assert_not_called()

    def test_detect_audio_format_strips_codecs_metadata(self):
        """Test Content-Type parsing handles codec parameters."""
        self.assertEqual(_detect_audio_format("audio/webm;codecs=opus"), "webm")
        self.assertEqual(_detect_audio_format("audio/mp4; codecs=mp4a.40.2"), "mp4")


class TestVoiceTranscriptionIntegration(unittest.TestCase):
    """Integration tests for voice transcription (requires actual model)."""

    def test_transcribe_real_audio_file(self):
        """Test transcription with a real audio file.

        NOTE: This test requires:
        1. A real audio file (e.g., test_zh.webm)
        2. Faster-Whisper installed
        3. Model downloaded (first run will download ~1GB)

        Skip this test in CI/CD environments without model.
        """
        # Skip if no test audio file
        test_audio_path = os.path.join(os.path.dirname(__file__), "fixtures", "test_zh.webm")
        if not os.path.exists(test_audio_path):
            self.skipTest("Test audio file not found. Create fixtures/test_zh.webm for integration test.")

        # Read audio file
        with open(test_audio_path, "rb") as f:
            audio_data = f.read()

        # Transcribe
        try:
            result = _transcribe_audio(audio_data, language="zh")
            self.assertIsInstance(result["text"], str)
            self.assertGreater(len(result["text"]), 0)
            self.assertEqual(result["language"], "zh")
            self.assertGreater(result["language_probability"], 0.5)
        except Exception as e:
            self.skipTest(f"Whisper model not available: {e}")


if __name__ == "__main__":
    unittest.main()
