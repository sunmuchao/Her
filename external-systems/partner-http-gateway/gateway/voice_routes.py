"""Voice transcription routes using Faster-Whisper."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

# 修复 OpenMP 库重复初始化问题（Intel MKL 与 PyTorch 冲突）
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 配置 Hugging Face 镜像（解决中国访问超时问题）
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")  # 默认使用中国镜像
os.environ["HF_ENDPOINT"] = HF_ENDPOINT

from faster_whisper import WhisperModel  # type: ignore[import-untyped]

try:
    from pydub import AudioSegment  # type: ignore[import-untyped]
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available, audio format conversion disabled")

LOGGER = logging.getLogger(__name__)

# Lazy-loaded Whisper model singleton
_WHISPER_MODEL: WhisperModel | None = None

SUPPORTED_AUDIO_FORMATS = {"wav", "webm", "ogg", "mp4", "m4a", "mpeg", "mp3"}


def _get_whisper_model() -> WhisperModel:
    """Lazy load Whisper model to avoid startup overhead."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")  # 默认改为 small（更快下载）
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

        LOGGER.info(f"Loading Whisper model: size={model_size}, device={device}, compute_type={compute_type}")
        LOGGER.info(f"Using Hugging Face endpoint: {HF_ENDPOINT}")

        try:
            _WHISPER_MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
            LOGGER.info("Whisper model loaded successfully")
        except Exception as e:
            LOGGER.error(f"Failed to load Whisper model: {e}")
            LOGGER.error("Please check network connection or use HF_ENDPOINT environment variable")
            LOGGER.error("Example: HF_ENDPOINT=https://hf-mirror.com")
            raise

    return _WHISPER_MODEL


def _convert_audio_to_wav(audio_data: bytes, input_format: str = "webm") -> tuple[bytes, dict[str, Any]]:
    """Convert audio data to WAV format for Whisper.

    Args:
        audio_data: Raw audio bytes (webm/mp4/ogg format)
        input_format: Input audio format (webm, mp4, ogg, etc.)

    Returns:
        tuple of (wav_audio_bytes, metadata_dict)

    Raises:
        RuntimeError: If ffmpeg/pydub not available or conversion fails
    """
    if not PYDUB_AVAILABLE:
        raise RuntimeError(
            "pydub not installed, cannot convert audio format. "
            "Install pydub: pip install pydub. "
            "Also ensure ffmpeg is installed: brew install ffmpeg (macOS)"
        )

    # Write to temp file for pydub
    with tempfile.NamedTemporaryFile(suffix=f".{input_format}", delete=False) as tmp_in:
        tmp_in.write(audio_data)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path.replace(f".{input_format}", ".wav")

    try:
        LOGGER.info(f"Converting audio: {input_format} → wav, size={len(audio_data)} bytes")

        # Load audio with pydub (uses ffmpeg internally)
        audio_segment = AudioSegment.from_file(tmp_in_path, format=input_format)

        # Extract metadata
        metadata = {
            "duration_ms": len(audio_segment),
            "channels": audio_segment.channels,
            "sample_rate": audio_segment.frame_rate,
            "bits_per_sample": audio_segment.sample_width * 8,
        }

        LOGGER.info(
            f"Audio loaded: duration={metadata['duration_ms']}ms, "
            f"channels={metadata['channels']}, "
            f"sample_rate={metadata['sample_rate']}Hz"
        )

        # Export to WAV format (16-bit PCM, mono, 16kHz recommended for Whisper)
        # Convert to mono if stereo
        if audio_segment.channels > 1:
            audio_segment = audio_segment.set_channels(1)
            LOGGER.info("Converted to mono for Whisper compatibility")

        # Resample to 16kHz (Whisper's native sample rate)
        if audio_segment.frame_rate != 16000:
            audio_segment = audio_segment.set_frame_rate(16000)
            LOGGER.info(f"Resampled to 16kHz for Whisper compatibility")

        # Export to WAV
        audio_segment.export(tmp_out_path, format="wav")

        # Read converted audio
        with open(tmp_out_path, "rb") as tmp_out:
            wav_audio = tmp_out.read()

        LOGGER.info(f"Conversion successful: output size={len(wav_audio)} bytes")

        return wav_audio, metadata

    except Exception as e:
        LOGGER.error(f"Audio conversion failed: {e}")
        LOGGER.error(f"Input format: {input_format}, size: {len(audio_data)} bytes")
        raise RuntimeError(
            f"Failed to convert audio format: {e}. "
            f"Ensure ffmpeg is installed and supports {input_format} format. "
            f"Install ffmpeg: brew install ffmpeg (macOS)"
        ) from e

    finally:
        # Cleanup temp files
        if os.path.exists(tmp_in_path):
            os.unlink(tmp_in_path)
        if os.path.exists(tmp_out_path):
            os.unlink(tmp_out_path)


def _detect_audio_format(content_type: str) -> str:
    """Extract the canonical audio format from a Content-Type header."""
    if not content_type:
        return "webm"

    mime_type = content_type.split(";", 1)[0].strip().lower()
    if "/" not in mime_type:
        return "webm"

    audio_format = mime_type.split("/", 1)[1]
    return audio_format if audio_format in SUPPORTED_AUDIO_FORMATS else "webm"


def _transcribe_audio(audio_data: bytes, language: str = "zh", content_type: str = "") -> dict[str, Any]:
    """Transcribe audio data using Whisper.

    Args:
        audio_data: Raw audio bytes (webm/mp4/wav format)
        language: Language code (default: zh for Chinese)
        content_type: Content type header (e.g., "audio/webm", "audio/mp4")

    Returns:
        dict with 'text' (transcribed text) and 'segments' (detailed timing info)
    """
    model = _get_whisper_model()

    # Detect audio format from content type
    audio_format = _detect_audio_format(content_type)
    LOGGER.info(f"Detected audio format: {audio_format} from content-type: {content_type or 'unknown'}")

    # Convert to WAV if not already WAV
    conversion_metadata = {}
    if audio_format != "wav":
        LOGGER.info(f"Converting {audio_format} to WAV for Whisper compatibility")
        try:
            audio_data, conversion_metadata = _convert_audio_to_wav(audio_data, input_format=audio_format)
            audio_format = "wav"
        except RuntimeError as e:
            raise RuntimeError(
                "Audio format conversion failed before transcription. "
                f"Input format was {audio_format}. {e}"
            ) from e

    # Write audio to temporary file (Whisper needs file path)
    suffix = f".{audio_format}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        tmp_file.write(audio_data)
        tmp_path = tmp_file.name

    try:
        LOGGER.info(
            f"Transcribing audio: format={audio_format}, "
            f"size={len(audio_data)} bytes, "
            f"duration={conversion_metadata.get('duration_ms', 'unknown')}ms"
        )

        segments, info = model.transcribe(tmp_path, language=language, beam_size=5)

        # Extract full text
        full_text = "".join(segment.text for segment in segments)

        LOGGER.info(
            f"Transcription successful: language={info.language}, "
            f"probability={info.language_probability:.2f}, "
            f"text_length={len(full_text)}"
        )

        return {
            "text": full_text.strip(),
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
                for segment in segments
            ],
            "audio_info": conversion_metadata,  # Include conversion metadata for debugging
        }
    except Exception as e:
        LOGGER.error(f"Whisper transcription failed: {e}")
        LOGGER.error(
            f"Audio details: format={audio_format}, size={len(audio_data)}, "
            f"conversion={conversion_metadata}"
        )
        raise
    finally:
        # Clean up temp file
        os.unlink(tmp_path)


def dispatch_voice_rest(
    gateway: Any,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Dispatch voice transcription REST routes.

    Routes:
        POST /v1/voice/transcribe - Transcribe audio file

    Returns:
        (status_code, response_dict) or None if route doesn't match
    """
    # Only handle /v1/voice/* paths
    if not path.startswith("/v1/voice"):
        return None

    # POST /v1/voice/transcribe
    if path == "/v1/voice/transcribe" and method == "POST":
        try:
            # Read raw audio data from request body
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            if content_length == 0:
                return 400, {
                    "error": {
                        "code": "empty_audio",
                        "message": "No audio data provided",
                    }
                }

            # Read audio bytes
            audio_data = environ["wsgi.input"].read(content_length)

            # Validate content type
            content_type = environ.get("CONTENT_TYPE", "")
            if not content_type.startswith(("audio/", "application/octet-stream")):
                return 400, {
                    "error": {
                        "code": "invalid_content_type",
                        "message": f"Expected audio/*, got {content_type}",
                    }
                }

            # Transcribe with content type for format detection
            content_type = environ.get("CONTENT_TYPE", "")
            LOGGER.info(
                f"Transcribing audio: size={len(audio_data)} bytes, "
                f"type={content_type}, format={content_type.split('/')[-1] if '/' in content_type else 'unknown'}"
            )
            result = _transcribe_audio(audio_data, language="zh", content_type=content_type)

            return 200, {
                "success": True,
                "text": result["text"],
                "language": result["language"],
                "language_probability": result["language_probability"],
                "segments": result["segments"],
            }

        except Exception as e:
            LOGGER.exception("Failed to transcribe audio")
            error_message = str(e)
            error_code = "transcription_failed"

            if "Audio format conversion failed" in error_message:
                error_code = "audio_conversion_failed"
            elif "pydub not installed" in error_message or "ffmpeg" in error_message:
                error_code = "audio_dependency_missing"

            return 500, {
                "error": {
                    "code": error_code,
                    "message": error_message,
                }
            }

    # Route not found
    return None


__all__ = ["dispatch_voice_rest"]
