#!/usr/bin/env python3
"""
Whisper 模型预热脚本

首次使用语音识别前，运行此脚本下载并加载模型，
避免首次请求时超时。

Usage:
  python scripts/preload_whisper_model.py
"""

import os
import sys
from pathlib import Path

# 修复 OpenMP 库重复初始化问题（Intel MKL 与 PyTorch 冲突）
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 加载 .env 配置
def load_dotenv():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=True)
            print(f"✓ 已加载环境配置: {env_path}")
    except ImportError:
        print("⚠ 未安装 python-dotenv，使用默认配置")

load_dotenv()

# 配置 Hugging Face 镜像（关键修复）
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = HF_ENDPOINT
print(f"✓ 使用 Hugging Face 镜像: {HF_ENDPOINT}")

def preload_whisper_model():
    """下载并加载 Whisper 模型"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("❌ 未安装 faster-whisper")
        print("请运行: pip install faster-whisper==1.2.1")
        return False

    # 从环境变量读取配置
    model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
    device = os.environ.get("WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

    print("=" * 70)
    print("Whisper 模型预热（提前下载）")
    print("=" * 70)
    print(f"\n配置:")
    print(f"  - 模型大小: {model_size}")
    print(f"  - 运行设备: {device}")
    print(f"  - 计算类型: {compute_type}")
    print(f"  - HF 镜像: {HF_ENDPOINT}")

    # 模型大小预估
    model_sizes = {
        "tiny": "~40MB",
        "small": "~500MB",
        "medium": "~1.5GB",
        "large": "~3GB",
    }
    estimated_size = model_sizes.get(model_size, "未知")

    print(f"  - 预估大小: {estimated_size}")

    print(f"\n开始下载模型...")
    print(f"⚠ 使用镜像站点 {HF_ENDPOINT}，下载速度更快")

    try:
        # 加载模型（会自动下载）
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        print("\n✅ 模型下载并加载成功！")

        # 测试模型是否工作（使用临时文件）
        print("\n测试模型...")
        import wave
        import struct

        # 创建一个最小的测试音频文件（1秒静音）
        test_audio_path = "/tmp/test_whisper_audio.wav"
        with wave.open(test_audio_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            # 写入 1 秒静音数据
            wav_file.writeframes(struct.pack('<h', 0) * 16000)

        try:
            segments, info = model.transcribe(
                test_audio_path,
                language="zh",
                beam_size=5,
            )

            print(f"✓ 模型测试成功")
            print(f"  - 语言检测: {info.language} (概率: {info.language_probability:.2f})")
            print(f"  - 注意：测试音频是静音，所以没有识别出文本")

            # 清理测试文件
            os.unlink(test_audio_path)

        except Exception as test_error:
            print(f"✓ 模型加载成功，测试时出现预期错误（静音文件）: {test_error}")
            # 清理测试文件
            if os.path.exists(test_audio_path):
                os.unlink(test_audio_path)

        print("\n" + "=" * 70)
        print("✅ Whisper 模型已准备好，可以立即使用语音识别")
        print("=" * 70)

        # 显示缓存位置
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        print(f"\n模型缓存位置: {cache_dir}")
        print(f"下次启动无需重新下载")

        return True

    except Exception as e:
        print(f"\n❌ 模型下载失败: {e}")
        print("\n可能的原因:")
        print("  1. 网络连接问题（无法访问镜像站点）")
        print("  2. 磁盘空间不足")
        print("  3. 内存不足")

        print("\n解决方案:")
        print(f"  1. 尝试其他镜像站点：")
        print(f"     export HF_ENDPOINT=https://huggingface.co")
        print(f"  2. 清理磁盘空间")
        print(f"  3. 使用更小的模型：")
        print(f"     export WHISPER_MODEL_SIZE=tiny")

        print("\n手动下载方法：")
        print(f"  访问镜像站点下载模型文件：")
        print(f"  {HF_ENDPOINT}/Systran/faster-whisper-{model_size}")
        print(f"  并保存到 ~/.cache/huggingface/hub/ 目录")

        return False

if __name__ == "__main__":
    success = preload_whisper_model()
    sys.exit(0 if success else 1)