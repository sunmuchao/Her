#!/bin/bash

# 小雅音色样本生成脚本
# 用法：./generate-xiaoya-voice-sample.sh

set -e

echo "========================================="
echo "小雅音色样本生成脚本"
echo "========================================="
echo ""

# 配置
OUTPUT_DIR="/Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS/reference_audio"
mkdir -p "$OUTPUT_DIR"

XIAOYA_SAMPLE_MP3="$OUTPUT_DIR/xiaoya-sample.mp3"
XIAOYA_SAMPLE_WAV="$OUTPUT_DIR/xiaoya-sample.wav"

# 文本内容（建议 5-10 秒）
XIAOYA_TEXT="你好，我是小雅，很高兴认识你。有什么可以帮助你的吗？"

# 检查 edge-tts
if ! command -v edge-tts &> /dev/null; then
    echo "❌ edge-tts 未安装"
    echo ""
    echo "安装 edge-tts："
    echo "pip install edge-tts"
    echo ""
    exit 1
fi

# 检查 ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg 未安装"
    echo ""
    echo "安装 ffmpeg："
    echo "brew install ffmpeg  # macOS"
    echo "apt install ffmpeg   # Linux"
    echo ""
    exit 1
fi

echo "步骤 1：使用 edge-tts 生成语音样本..."
echo ""

echo "文本内容：$XIAOYA_TEXT"
echo "音色选择：zh-CN-XiaoxiaoNeural（晓晓 - 微软高质量女声）"
echo ""

edge-tts --text "$XIAOYA_TEXT" \
    --voice zh-CN-XiaoxiaoNeural \
    --write-media "$XIAOYA_SAMPLE_MP3"

if [ -f "$XIAOYA_SAMPLE_MP3" ]; then
    echo "✅ MP3 生成成功"
    ls -lh "$XIAOYA_SAMPLE_MP3"
else
    echo "❌ MP3 生成失败"
    exit 1
fi

echo ""

echo "步骤 2：转换为 WAV 格式（GPT-SoVITS 要求）..."
echo ""

ffmpeg -i "$XIAOYA_SAMPLE_MP3" \
    -ar 16000 \
    -ac 1 \
    -acodec pcm_s16le \
    "$XIAOYA_SAMPLE_WAV"

if [ -f "$XIAOYA_SAMPLE_WAV" ]; then
    echo "✅ WAV 转换成功"
    ls -lh "$XIAOYA_SAMPLE_WAV"

    # 删除临时 MP3
    rm "$XIAOYA_SAMPLE_MP3"
else
    echo "❌ WAV 转换失败"
    exit 1
fi

echo ""

echo "========================================="
echo "音色样本生成完成！"
echo "========================================="
echo ""
echo "文件位置：$XIAOYA_SAMPLE_WAV"
echo ""
echo "音频信息："
echo "- 格式：WAV（16-bit PCM）"
echo "- 采样率：16kHz"
echo "- 声道：单声道"
echo "- 时长：约 5-8 秒"
echo ""
echo "下一步："
echo "1. 在 GPT-SoVITS Web UI 中上传此文件"
echo "   http://localhost:9874"
echo ""
echo "2. 或使用 API 上传："
echo "   curl -X POST http://localhost:9880/upload_reference"
echo "   -F 'audio=@$XIAOYA_SAMPLE_WAV'"
echo "   -F 'speaker_name=xiaoya-default'"
echo ""
echo "3. 训练小雅专属音色后，即可使用"
echo "   curl -X POST http://localhost:9880/tts"
echo "   -d '{\"text\": \"你好\", \"speaker\": \"xiaoya-default\"}'"
echo ""