"""Edge-TTS语音合成路由（微软云端TTS）.

使用微软Azure Cognitive Services后端（免费，无需API Key）
音色：zh-CN-XiaoxiaoNeural（晓晓，温柔女声）
"""

from __future__ import annotations

import logging
import os
import tempfile
import asyncio
from typing import Any

LOGGER = logging.getLogger(__name__)

# 默认音色（微软晓晓，温柔女声）
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 可选的其他中文女声
CHINESE_FEMALE_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",      # 晓晓（温柔，推荐用于小雅）
    "xiaoyi": "zh-CN-XiaoyiNeural",          # 晓伊（活泼）
    "yunxi": "zh-CN-YunxiNeural",            # 云希（沉稳男声）
    "yunjian": "zh-CN-YunjianNeural",        # 云健（成熟男声）
}


async def synthesize_audio_edge_tts(
    text: str,
    voice: str = DEFAULT_VOICE,
    output_format: str = "mp3",
) -> tuple[bytes, dict[str, Any]]:
    """使用edge-tts合成语音.

    Args:
        text: 要合成的文本
        voice: 音色ID（默认：zh-CN-XiaoxiaoNeural）
        output_format: 输出格式（mp3或wav）

    Returns:
        tuple: (音频数据bytes, 元数据dict)
        元数据包含：duration_ms, format, size, voice, engine

    Raises:
        RuntimeError: 合成失败
    """
    import edge_tts

    LOGGER.info(f"[edge-tts] 开始合成: text_length={len(text)}, voice={voice}")

    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # 创建Communicate对象
        communicate = edge_tts.Communicate(text, voice)

        # 合成并保存到文件
        await communicate.save(tmp_path)

        # 读取音频数据
        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        # 获取音频元数据（使用pydub计算时长）
        duration_ms = None
        try:
            from pydub import AudioSegment
            audio_segment = AudioSegment.from_file(tmp_path, format=output_format)
            duration_ms = len(audio_segment)
        except ImportError:
            LOGGER.warning("pydub未安装，无法计算音频时长")
        except Exception as e:
            LOGGER.warning(f"计算音频时长失败: {e}")

        metadata = {
            "duration_ms": duration_ms,
            "format": output_format,
            "size": len(audio_data),
            "voice": voice,
            "engine": "edge-tts",
            "tts_service": "microsoft-azure",
        }

        LOGGER.info(
            f"[edge-tts] 合成成功: size={len(audio_data)}bytes, "
            f"duration={duration_ms}ms, voice={voice}"
        )

        return audio_data, metadata

    except Exception as e:
        LOGGER.error(f"[edge-tts] 合成失败: {e}")
        raise RuntimeError(f"语音合成失败: {e}")

    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def dispatch_edge_tts_rest(
    gateway: Any,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Edge-TTS REST API路由.

    Routes:
        POST /v1/voice/synthesize - 合成语音（返回音频URL）

    Returns:
        (status_code, response_dict) or None if route doesn't match
    """
    if not path.startswith("/v1/voice"):
        return None

    # POST /v1/voice/synthesize
    if path == "/v1/voice/synthesize" and method == "POST":
        try:
            LOGGER.info("[edge_tts_routes] 收到语音合成请求")

            # 读取请求体
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            if content_length == 0:
                return 400, {
                    "error": {"code": "empty_request", "message": "Request body is empty"},
                    "trace_id": get_trace_id(),
                }

            import json
            raw_body = environ["wsgi.input"].read(content_length)
            request_data = json.loads(raw_body)

            # 验证参数
            text = request_data.get("text", "").strip()
            if not text:
                return 400, {
                    "error": {"code": "missing_text", "message": "text is required"},
                    "trace_id": get_trace_id(),
                }

            # 音色参数（可选）
            voice_key = request_data.get("voice", "xiaoxiao")
            voice = CHINESE_FEMALE_VOICES.get(voice_key, DEFAULT_VOICE)

            # 输出格式（可选）
            output_format = request_data.get("format", "mp3")

            LOGGER.info(
                f"[edge_tts_routes] 合成参数: text_length={len(text)}, "
                f"voice={voice}, format={output_format}"
            )

            # 异步合成语音
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                audio_data, metadata = loop.run_until_complete(
                    synthesize_audio_edge_tts(text, voice, output_format)
                )
            finally:
                loop.close()

            # 上传到MinIO（类似图片存储）
            try:
                from chat_system.media_storage import upload_audio
                upload_result = upload_audio(
                    audio_data,
                    f"tts-{voice_key}-{int(os.times().elapsed * 1000)}.{output_format}",
                    "xiaoya",
                    metadata={"tts_engine": "edge-tts", "voice": voice},
                )
                audio_url = upload_result["media_url"]
                LOGGER.info(f"[edge_tts_routes] 音频上传成功: url={audio_url}")
            except ImportError:
                # 如果media_storage不可用，返回base64编码的音频数据
                import base64
                audio_base64 = base64.b64encode(audio_data).decode("utf-8")
                audio_url = f"data:audio/{output_format};base64,{audio_base64}"
                LOGGER.warning(
                    "[edge_tts_routes] media_storage不可用，返回base64音频数据"
                )

            # 返回结果
            return 200, {
                "success": True,
                "audio_url": audio_url,
                "duration_ms": metadata["duration_ms"],
                "format": metadata["format"],
                "size": metadata["size"],
                "voice": voice,
                "engine": "edge-tts",
                "trace_id": get_trace_id(),
            }

        except Exception as e:
            LOGGER.exception(f"[edge_tts_routes] 语音合成失败: {e}")
            return 500, {
                "error": {"code": "tts_failed", "message": str(e)},
                "trace_id": get_trace_id(),
            }

    # Route not found
    return None


def get_trace_id():
    """获取trace_id（简化版）"""
    from her_runtime_context import get_trace_id as _get_trace_id
    try:
        return _get_trace_id()
    except:
        return "unknown"


__all__ = ["dispatch_edge_tts_rest", "synthesize_audio_edge_tts"]