"""Voice transcription routes using Faster-Whisper."""

from __future__ import annotations

import logging
import os
import re
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
    logging.info("pydub not available, audio format conversion disabled")

LOGGER = logging.getLogger(__name__)

# Lazy-loaded Whisper model singleton
_WHISPER_MODEL: WhisperModel | None = None

SUPPORTED_AUDIO_FORMATS = {"wav", "webm", "ogg", "mp4", "m4a", "mpeg", "mp3"}
# Whisper幻觉检测模式（扩展YouTube常见结尾词，包含简体和繁体中文）
SUSPICIOUS_HALLUCINATION_PATTERNS = (
    # 字幕组标识（简体+繁体）
    re.compile(r"字幕\s*by", re.IGNORECASE),
    re.compile(r"字幕組", re.IGNORECASE),  # 繁体
    re.compile(r"字幕制作", re.IGNORECASE),
    re.compile(r"字幕翻译", re.IGNORECASE),

    # 特定人物/栏目名称（简体+繁体）
    re.compile(r"索兰娅"),
    re.compile(r"明镜与点点", re.IGNORECASE),  # 简体
    re.compile(r"明鏡與點點", re.IGNORECASE),  # 繁体
    re.compile(r"一点点点", re.IGNORECASE),
    re.compile(r"一點點點", re.IGNORECASE),  # 繁体

    # YouTube视频结尾词（简体中文）
    re.compile(r"请不吝[点赞订阅转发打赏关注分享]+", re.IGNORECASE),
    re.compile(r"不吝点赞", re.IGNORECASE),
    re.compile(r"点赞订阅", re.IGNORECASE),
    re.compile(r"订阅转发", re.IGNORECASE),
    re.compile(r"转发打赏", re.IGNORECASE),
    re.compile(r"打赏支持", re.IGNORECASE),
    re.compile(r"支持[\w]+栏目", re.IGNORECASE),
    re.compile(r"点赞关注", re.IGNORECASE),
    re.compile(r"关注分享", re.IGNORECASE),
    re.compile(r"分享转发", re.IGNORECASE),

    # YouTube视频结尾词（繁体中文）- 最常见的幻觉！
    re.compile(r"請不吝[點贊訂閱轉發打賞關注分享]+", re.IGNORECASE),  # 繁体完整版
    re.compile(r"不吝點贊", re.IGNORECASE),  # 繁体
    re.compile(r"點贊訂閱", re.IGNORECASE),  # 繁体
    re.compile(r"訂閱轉發", re.IGNORECASE),  # 繁体
    re.compile(r"轉發打賞", re.IGNORECASE),  # 繁体
    re.compile(r"打賞支持", re.IGNORECASE),  # 繁体
    re.compile(r"支持[\w]+欄目", re.IGNORECASE),  # 繁体
    re.compile(r"點贊關注", re.IGNORECASE),  # 繁体
    re.compile(r"關注分享", re.IGNORECASE),  # 繁体
    re.compile(r"分享轉發", re.IGNORECASE),  # 繁体

    # YouTube常见感谢词（简体）
    re.compile(r"谢谢观看", re.IGNORECASE),
    re.compile(r"感谢观看", re.IGNORECASE),
    re.compile(r"感谢大家的观看", re.IGNORECASE),
    re.compile(r"感谢各位的观看", re.IGNORECASE),
    re.compile(r"谢谢大家", re.IGNORECASE),
    re.compile(r"谢谢各位", re.IGNORECASE),

    # YouTube常见感谢词（繁体）
    re.compile(r"謝謝觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝大家的觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝各位的觀看", re.IGNORECASE),  # 繁体
    re.compile(r"謝謝大家", re.IGNORECASE),  # 繁体
    re.compile(r"謝謝各位", re.IGNORECASE),  # 繁体

    # YouTube结尾再见词（简体）
    re.compile(r"下期再见", re.IGNORECASE),
    re.compile(r"我们下期再见", re.IGNORECASE),
    re.compile(r"朋友们再见", re.IGNORECASE),
    re.compile(r"下期视频", re.IGNORECASE),
    re.compile(r"下个视频", re.IGNORECASE),

    # YouTube结尾再见词（繁体）
    re.compile(r"下期再見", re.IGNORECASE),  # 繁体
    re.compile(r"我們下期再見", re.IGNORECASE),  # 繁体
    re.compile(r"朋友們再見", re.IGNORECASE),  # 繁体
    re.compile(r"下期視頻", re.IGNORECASE),  # 繁体
    re.compile(r"下個視頻", re.IGNORECASE),  # 繁体

    # 其他常见幻觉模式（简体+繁体）
    re.compile(r"谢谢您的收看", re.IGNORECASE),
    re.compile(r"感谢您的收看", re.IGNORECASE),
    re.compile(r"謝謝您的收看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝您的收看", re.IGNORECASE),  # 繁体
)
LOW_AUDIO_DBFS_THRESHOLD = -35.0
MAX_GAIN_DB = 30.0


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
            "dbfs": audio_segment.dBFS,
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

        # Boost very quiet recordings to improve transcription reliability.
        dbfs = float(audio_segment.dBFS) if audio_segment.dBFS != float("-inf") else float("-inf")
        if dbfs != float("-inf") and dbfs < LOW_AUDIO_DBFS_THRESHOLD:
            gain_db = min(LOW_AUDIO_DBFS_THRESHOLD - dbfs, MAX_GAIN_DB)
            audio_segment = audio_segment.apply_gain(gain_db)
            metadata["applied_gain_db"] = gain_db
            metadata["normalized_dbfs"] = audio_segment.dBFS
            LOGGER.info(
                "Applied gain for quiet audio: original_dbfs=%.2f, gain_db=%.2f, normalized_dbfs=%.2f",
                dbfs,
                gain_db,
                audio_segment.dBFS,
            )

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


def _is_suspicious_hallucination(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in SUSPICIOUS_HALLUCINATION_PATTERNS)


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
            f"duration={conversion_metadata.get('duration_ms', 'unknown')}ms, "
            f"dbfs={conversion_metadata.get('dbfs', 'unknown')}, "
            f"applied_gain={conversion_metadata.get('applied_gain_db', 'none')}"
        )

        # 检查音频音量级别（判断是否为静音）
        dbfs = conversion_metadata.get('dbfs')
        if dbfs is not None and dbfs < -40.0:
            LOGGER.warning("[Whisper] 音频音量过低（dbfs=%.2f），可能是静音或噪音", dbfs)

        def run_transcription(*, vad_filter: bool) -> tuple[list[Any], Any]:
            segments_iter, transcription_info = model.transcribe(
                tmp_path,
                language=language,
                beam_size=5,
                vad_filter=vad_filter,
                hallucination_silence_threshold=1.5 if vad_filter else None,
            )
            return list(segments_iter), transcription_info

        segment_list, info = run_transcription(vad_filter=True)
        filtered_segments = segment_list

        LOGGER.info("[Whisper] VAD识别结果: segments_count=%d, first_segment_text=%s",
                    len(filtered_segments),
                    filtered_segments[0].text if filtered_segments else "(empty)")

        # Extract full text
        full_text = "".join(segment.text for segment in filtered_segments)
        if not full_text.strip():
            LOGGER.warning("[Whisper] VAD识别结果为空，尝试不带VAD重新识别")
            segment_list, info = run_transcription(vad_filter=False)
            filtered_segments = segment_list
            full_text = "".join(segment.text for segment in filtered_segments)

            LOGGER.info("[Whisper] 不带VAD识别结果: segments_count=%d, text_length=%d, text_preview=%s",
                        len(filtered_segments),
                        len(full_text),
                        full_text[:50] if len(full_text) > 0 else "(empty)")
        else:
            LOGGER.info("[Whisper] VAD识别成功: text_length=%d, text_preview=%s",
                        len(full_text),
                        full_text[:50])

        if _is_suspicious_hallucination(full_text):
            LOGGER.warning("[Whisper] 检测到幻觉内容，已丢弃: text=%r, matched_patterns=%s",
                          full_text,
                          [p.pattern for p in SUSPICIOUS_HALLUCINATION_PATTERNS if p.search(full_text.strip())])
            full_text = ""
            filtered_segments = []
        else:
            LOGGER.info("[Whisper] 幻觉检测通过: text_length=%d, is_hallucination=False", len(full_text))

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
                for segment in filtered_segments
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
            LOGGER.info("[voice_routes] 收到语音识别请求: method=%s, path=%s", method, path)

            # Read raw audio data from request body
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            LOGGER.info("[voice_routes] 请求体长度: content_length=%d", content_length)

            if content_length == 0:
                LOGGER.error("[voice_routes] 音频数据为空: content_length=0")
                return 400, {
                    "error": {
                        "code": "empty_audio",
                        "message": "No audio data provided",
                    }
                }

            # Read audio bytes
            audio_data = environ["wsgi.input"].read(content_length)
            LOGGER.info("[voice_routes] 读取音频数据: size=%d bytes", len(audio_data))

            # Validate content type
            content_type = environ.get("CONTENT_TYPE", "")
            LOGGER.info("[voice_routes] Content-Type: %s", content_type)

            if not content_type.startswith(("audio/", "application/octet-stream")):
                LOGGER.error("[voice_routes] Content-Type 不支持: %s", content_type)
                return 400, {
                    "error": {
                        "code": "invalid_content_type",
                        "message": f"Expected audio/*, got {content_type}",
                    }
                }

            # Transcribe with content type for format detection
            LOGGER.info("[voice_routes] 开始语音识别...")
            result = _transcribe_audio(audio_data, language="zh", content_type=content_type)
            LOGGER.info("[voice_routes] 语音识别完成: text_length=%d, language=%s", len(result["text"]), result["language"])

            return 200, {
                "success": True,
                "text": result["text"],
                "language": result["language"],
                "language_probability": result["language_probability"],
                "segments": result["segments"],
            }

        except Exception as e:
            LOGGER.exception("[voice_routes] 语音识别失败: %s", e)
            error_message = str(e)
            error_code = "transcription_failed"

            if "Audio format conversion failed" in error_message:
                error_code = "audio_conversion_failed"
            elif "pydub not installed" in error_message or "ffmpeg" in error_message:
                error_code = "audio_dependency_missing"

            LOGGER.error("[voice_routes] 返回错误: code=%s, message=%s", error_code, error_message)

            return 500, {
                "error": {
                    "code": error_code,
                    "message": error_message,
                }
            }

    # Route not found
    return None


__all__ = ["dispatch_voice_rest"]
