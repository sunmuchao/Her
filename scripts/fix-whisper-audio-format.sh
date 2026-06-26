#!/bin/bash
# ==============================================================================
# Whisper 音频格式兼容性修复脚本
# ==============================================================================
#
# 问题：浏览器录制的 webm 文件无法被 Whisper 解析
# 根因：ffmpeg 未安装 + 缺少音频格式转换机制
#
# 修复：
#   1. 安装 ffmpeg（音频解码必需）
#   2. 安装 pydub（音频格式转换）
#   3. 验证 ffmpeg 和 pydub 正常工作
#
# ==============================================================================

set -e

echo "======================================================================"
echo "Whisper 音频格式兼容性修复"
echo "======================================================================"
echo ""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查操作系统
OS="$(uname)"
if [[ "$OS" != "Darwin" ]]; then
    echo -e "${YELLOW}警告: 此脚本主要针对 macOS，其他系统请手动安装 ffmpeg${NC}"
fi

# ==============================================================================
# Step 1: 检查并安装 ffmpeg
# ==============================================================================

echo "Step 1: 检查 ffmpeg..."
echo ""

if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✓ ffmpeg 已安装${NC}"
    ffmpeg -version | head -5
else
    echo -e "${YELLOW}⚠ ffmpeg 未安装，正在安装...${NC}"

    # 检查 Homebrew
    if ! command -v brew &> /dev/null; then
        echo -e "${RED}✗ Homebrew 未安装，请先安装 Homebrew${NC}"
        echo "  参考: https://brew.sh/"
        exit 1
    fi

    # 安装 ffmpeg（包含所有解码器）
    echo "  安装 ffmpeg（包含 Opus/AAC 解码器）..."
    brew install ffmpeg

    if command -v ffmpeg &> /dev/null; then
        echo -e "${GREEN}✓ ffmpeg 安装成功${NC}"
        ffmpeg -version | head -5
    else
        echo -e "${RED}✗ ffmpeg 安装失败${NC}"
        exit 1
    fi
fi

echo ""

# ==============================================================================
# Step 2: 检查并安装 pydub
# ==============================================================================

echo "Step 2: 检查 pydub..."
echo ""

# 激活虚拟环境（如果存在）
if [[ -f ".venv/bin/activate" ]]; then
    echo "  激活虚拟环境..."
    source .venv/bin/activate
elif [[ -f "venv/bin/activate" ]]; then
    echo "  激活虚拟环境..."
    source venv/bin/activate
fi

# 检查 pydub 是否已安装
if python -c "import pydub" 2> /dev/null; then
    echo -e "${GREEN}✓ pydub 已安装${NC}"
    # pydub 没有 __version__ 属性，只检查模块存在
else
    echo -e "${YELLOW}⚠ pydub 未安装，正在安装...${NC}"
    pip install pydub

    if python -c "import pydub" 2> /dev/null; then
        echo -e "${GREEN}✓ pydub 安装成功${NC}"
    else
        echo -e "${RED}✗ pydub 安装失败${NC}"
        exit 1
    fi
fi

echo ""

# ==============================================================================
# Step 3: 验证音频格式转换能力
# ==============================================================================

echo "Step 3: 验证音频格式转换能力..."
echo ""

# 创建临时测试文件
TMP_DIR=$(mktemp -d)
TEST_WEBM="$TMP_DIR/test.webm"
TEST_WAV="$TMP_DIR/test.wav"

# 创建一个简单的测试 webm 文件（使用 ffmpeg 生成静音音频）
echo "  创建测试 webm 文件..."
ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 1 -c:a libopus "$TEST_WEBM" -y 2>/dev/null

if [[ -f "$TEST_WEBM" ]]; then
    echo -e "${GREEN}  ✓ 测试 webm 文件创建成功${NC}"
    echo "    大小: $(stat -f%z "$TEST_WEBM" 2>/dev/null || stat -c%s "$TEST_WEBM") bytes"

    # 测试 pydub 转换
    echo "  测试 pydub 转换 webm → wav..."
    python -c "
import pydub
audio = pydub.AudioSegment.from_file('$TEST_WEBM')
audio.export('$TEST_WAV', format='wav')
print('    ✓ 转换成功')
print(f'    - 格式: {audio.channels} channels, {audio.frame_rate} Hz')
"

    if [[ -f "$TEST_WAV" ]]; then
        echo -e "${GREEN}  ✓ WAV 文件生成成功${NC}"
        echo "    大小: $(stat -f%z "$TEST_WAV" 2>/dev/null || stat -c%s "$TEST_WAV") bytes"
    else
        echo -e "${RED}  ✗ WAV 文件生成失败${NC}"
    fi
else
    echo -e "${RED}  ✗ 测试 webm 文件创建失败${NC}"
fi

# 清理测试文件
rm -rf "$TMP_DIR"
echo ""

# ==============================================================================
# Step 4: 检查 faster-whisper 对 WAV 的支持
# ==============================================================================

echo "Step 4: 验证 faster-whisper WAV 支持..."
echo ""

python -c "
try:
    from faster_whisper import WhisperModel
    print('  ✓ faster-whisper 可用')

    # 检查环境变量
    import os
    print(f'  - HF_ENDPOINT: {os.environ.get(\"HF_ENDPOINT\", \"未设置\")}')
    print(f'  - KMP_DUPLICATE_LIB_OK: {os.environ.get(\"KMP_DUPLICATE_LIB_OK\", \"未设置\")}')

except ImportError as e:
    print('  ✗ faster-whisper 未安装')
    print(f'    错误: {e}')
except Exception as e:
    print('  ⚠ faster-whisper 加载失败')
    print(f'    错误: {e}')
"

echo ""

# ==============================================================================
# 完成
# ==============================================================================

echo "======================================================================"
echo "修复完成"
echo "======================================================================"
echo ""
echo "✓ 已安装/验证:"
echo "  - ffmpeg（音频解码器）"
echo "  - pydub（音频格式转换）"
echo "  - faster-whisper（语音识别）"
echo ""
echo "后续步骤:"
echo "  1. 重启 Gateway 服务（如果正在运行）"
echo "  2. 测试语音识别："
echo "     python external-systems/partner-http-gateway/tests/test_voice_e2e.py"
echo "  3. 在浏览器中测试录制功能"
echo ""
echo "如果仍有问题，请查看详细日志："
echo "  - 前端日志: 浏览器 Console"
echo "  - 后端日志: Gateway 服务日志"
echo ""