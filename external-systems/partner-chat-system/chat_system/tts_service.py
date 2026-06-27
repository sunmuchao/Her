"""独立的TTS服务模块，提供统一的语音生成能力。

使用edge-tts（微软云端TTS）为文本生成语音，支持多种音色。
可被 assistant_orchestrator、discovery service 等多个模块复用。

主要功能：
- synthesize_tts: 为文本生成语音
- 支持4种音色（xiaoxiao/xiaoyi/yunxi/yunjian）
- 自动上传到MinIO
- 计算音频时长和大小
- 返回标准化的metadata结构

使用示例：
    from .tts_service import synthesize_tts

    result = synthesize_tts("你好，我是小雅", voice="xiaoxiao")
    if result:
        media_type = result["media_type"]  # "audio"
        media_url = result["media_url"]    # MinIO URL
        metadata = result["media_metadata"]
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any

LOGGER = logging.getLogger(__name__)


def synthesize_tts(text: str, voice: str = "xiaoxiao") -> dict[str, Any] | None:
    """为文本生成语音（使用edge-tts）

    Args:
        text: 要合成的文本
        voice: 音色（xiaoxiao/xiaoyi/yunxi/yunjian）
            - xiaoxiao: 晓晓（温柔女声，推荐小雅使用）
            - xiaoyi: 晓伊（活泼女声）
            - yunxi: 云希（沉稳男声）
            - yunjian: 云健（成熟男声）

    Returns:
        音频元数据字典或None（生成失败时）
        {
            "media_type": "audio",
            "media_url": "https://minio.example.com/bucket/object_key",
            "media_metadata": {
                "duration_ms": 3000,
                "format": "mp3",
                "size": 21000,
                "tts_engine": "edge-tts",
                "voice": "zh-CN-XiaoxiaoNeural",
            }
        }
    """
    try:
        import edge_tts

        LOGGER.info(f"[TTS Service] 开始生成语音: text_length={len(text)}, voice={voice}")

        # 音色映射
        voice_map = {
            "xiaoxiao": "zh-CN-XiaoxiaoNeural",  # 晓晓（温柔，推荐小雅）
            "xiaoyi": "zh-CN-XiaoyiNeural",      # 晓伊（活泼）
            "yunxi": "zh-CN-YunxiNeural",        # 云希（沉稳男声）
            "yunjian": "zh-CN-YunjianNeural",    # 云健（成熟男声）
        }
        edge_voice = voice_map.get(voice, "zh-CN-XiaoxiaoNeural")

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        # 异步合成语音
        communicate = edge_tts.Communicate(text, edge_voice)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(communicate.save(tmp_path))
        finally:
            loop.close()

        # 读取音频数据
        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        # 计算时长（可选）
        duration_ms = None
        try:
            from pydub import AudioSegment
            audio_segment = AudioSegment.from_file(tmp_path, format="mp3")
            duration_ms = len(audio_segment)
        except ImportError:
            LOGGER.warning("[TTS Service] pydub未安装，无法计算音频时长")
        except Exception as e:
            LOGGER.warning(f"[TTS Service] 计算音频时长失败: {e}")

        # 上传到MinIO（复用现有的media_storage）
        from .media_storage import upload_audio

        upload_result = upload_audio(
            audio_data,
            f"tts-{voice}-{int(os.times().elapsed * 1000)}.mp3",
            "xiaoya",
            metadata={"tts_engine": "edge-tts", "voice": edge_voice},
        )

        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

        LOGGER.info(
            f"[TTS Service] 语音生成成功: url={upload_result['media_url']}, "
            f"duration={duration_ms}ms, size={len(audio_data)}bytes"
        )

        return {
            "media_type": "audio",
            "media_url": upload_result["media_url"],
            "media_metadata": {
                "duration_ms": duration_ms,
                "format": "mp3",
                "size": len(audio_data),
                "tts_engine": "edge-tts",
                "voice": edge_voice,
            },
        }

    except ImportError as e:
        LOGGER.error(f"[TTS Service] edge-tts未安装: {e}")
        return None
    except Exception as e:
        LOGGER.error(f"[TTS Service] 语音生成失败: {e}")
        return None


__all__ = ["synthesize_tts"]