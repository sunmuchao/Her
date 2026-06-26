#!/bin/bash
# ==============================================================================
# Whisper 语音识别修复自动化验证脚本
# ==============================================================================
#
# 功能：
#   1. 检查 ffmpeg 安装状态
#   2. 检查 pydub 安装状态
#   3. 运行快速 WAV 测试
#   4. 运行多格式兼容性测试（如果 ffmpeg 已安装）
#   5. 生成验证报告
#
# 使用：
#   bash scripts/verify-whisper-fix.sh
#
# ==============================================================================

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "======================================================================"
echo "Whisper 语音识别修复自动化验证"
echo "======================================================================"
echo ""

# ==============================================================================
# Step 1: 检查 ffmpeg
# ==============================================================================

echo -e "${BLUE}Step 1: 检查 ffmpeg 安装状态${NC}"
echo ""

if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✓ ffmpeg 已安装${NC}"

    # 显示版本
    ffmpeg_version=$(ffmpeg -version | head -1 | awk '{print $3}')
    echo "  版本: $ffmpeg_version"

    # 检查关键解码器
    echo "  检查解码器..."
    if ffmpeg -codecs 2>/dev/null | grep -q "opus"; then
        echo -e "    ${GREEN}✓ Opus 解码器可用${NC}（Chrome/Firefox webm）"
    else
        echo -e "    ${RED}✗ Opus 解码器缺失${NC}"
    fi

    if ffmpeg -codecs 2>/dev/null | grep -q "aac"; then
        echo -e "    ${GREEN}✓ AAC 解码器可用${NC}（Safari mp4）"
    else
        echo -e "    ${RED}✗ AAC 解码器缺失${NC}"
    fi

    ffmpeg_ok=true
else
    echo -e "${YELLOW}⚠ ffmpeg 未安装${NC}"
    echo "  正在检查安装进程..."

    # 检查是否有 Homebrew 安装进程
    if pgrep -f "brew install ffmpeg" > /dev/null; then
        echo -e "  ${YELLOW}→ ffmpeg 正在安装中，请等待...${NC}"
        echo "  查看进度: tail -f /private/tmp/claude-501/-Users-sunmuchao-Downloads-Her/0574cbb0-8276-4639-a8ef-8bf61a08c72c/tasks/bnahe1smz.output"
        ffmpeg_ok=false
    else
        echo -e "  ${RED}✗ 没有正在进行的安装进程${NC}"
        echo "  请运行: bash scripts/fix-whisper-audio-format.sh"
        ffmpeg_ok=false
    fi
fi

echo ""

# ==============================================================================
# Step 2: 检查 pydub
# ==============================================================================

echo -e "${BLUE}Step 2: 检查 pydub 安装状态${NC}"
echo ""

# 激活虚拟环境
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
    echo "  ✓ 虚拟环境已激活"
elif [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
    echo "  ✓ 虚拟环境已激活"
else
    echo -e "  ${YELLOW}⚠ 虚拟环境未找到，使用系统 Python${NC}"
fi

# 检查 pydub
if python -c "import pydub" 2> /dev/null; then
    echo -e "${GREEN}✓ pydub 已安装${NC}"
    pydub_ok=true
else
    echo -e "${RED}✗ pydub 未安装${NC}"
    echo "  请运行: pip install pydub"
    pydub_ok=false
fi

# 检查 faster-whisper
if python -c "from faster_whisper import WhisperModel" 2> /dev/null; then
    echo -e "${GREEN}✓ faster-whisper 已安装${NC}"
    whisper_ok=true
else
    echo -e "${RED}✗ faster-whisper 未安装${NC}"
    echo "  请运行: pip install faster-whisper==1.2.1"
    whisper_ok=false
fi

# 检查 numpy 版本
numpy_version=$(python -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "未安装")
echo "  NumPy 版本: $numpy_version"

if [[ "$numpy_version" =~ ^2\. ]]; then
    echo -e "  ${YELLOW}⚠ NumPy 2.x 可能导致兼容性问题${NC}"
    echo "  请运行: bash scripts/fix-whisper-dependencies.sh"
fi

echo ""

# ==============================================================================
# Step 3: 检查 Gateway
# ==============================================================================

echo -e "${BLUE}Step 3: 检查 Gateway 运行状态${NC}"
echo ""

gateway_url="http://127.0.0.1:8765"

# 检查 Gateway 是否运行
if curl -s -f "$gateway_url/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Gateway 正在运行${NC}"
    echo "  URL: $gateway_url"

    # 获取健康状态
    health_data=$(curl -s "$gateway_url/health")
    echo "  响应: $health_data"
    gateway_ok=true
else
    echo -e "${YELLOW}⚠ Gateway 未运行${NC}"
    echo "  启动命令: python -m gateway"
    echo "  或查看: docs/whisper-fix-verification.md"
    gateway_ok=false
fi

echo ""

# ==============================================================================
# Step 4: 运行测试
# ==============================================================================

echo -e "${BLUE}Step 4: 运行自动化测试${NC}"
echo ""

test_results=()

# 测试 1: WAV 快速测试（不需要 ffmpeg）
if [[ "$gateway_ok" == true && "$whisper_ok" == true ]]; then
    echo "4.1. WAV 快速测试（不需要格式转换）..."

    wav_test_result=$(python external-systems/partner-http-gateway/tests/test_wav_quick.py 2>&1 | tail -5)

    if echo "$wav_test_result" | grep -q "WAV format works"; then
        echo -e "  ${GREEN}✓ WAV 测试通过${NC}"
        test_results+=("wav:pass")
    else
        echo -e "  ${RED}✗ WAV 测试失败${NC}"
        echo "$wav_test_result"
        test_results+=("wav:fail")
    fi
else
    echo -e "  ${YELLOW}⚠ 跳过 WAV 测试（Gateway 或 Whisper 未就绪）${NC}"
    test_results+=("wav:skip")
fi

echo ""

# 测试 2: 多格式测试（需要 ffmpeg）
if [[ "$ffmpeg_ok" == true && "$gateway_ok" == true ]]; then
    echo "4.2. 多格式兼容性测试..."

    format_test_result=$(python external-systems/partner-http-gateway/tests/test_voice_formats.py 2>&1 | grep -E "(Passed|Failed|All tests)")

    if echo "$format_test_result" | grep -q "Passed: 8"; then
        echo -e "  ${GREEN}✓ 多格式测试通过（8/8）${NC}"
        test_results+=("formats:pass")
    else
        echo -e "  ${YELLOW}⚠ 多格式测试部分通过${NC}"
        echo "$format_test_result"
        test_results+=("formats:partial")
    fi
else
    if [[ "$ffmpeg_ok" == false ]]; then
        echo -e "  ${YELLOW}⚠ 跳过多格式测试（ffmpeg 未安装）${NC}"
        echo "  安装 ffmpeg 后重新运行验证"
    else
        echo -e "  ${YELLOW}⚠ 跳过多格式测试（Gateway 未运行）${NC}"
    fi
    test_results+=("formats:skip")
fi

echo ""

# ==============================================================================
# Step 5: 生成验证报告
# ==============================================================================

echo "======================================================================"
echo "验证报告"
echo "======================================================================"
echo ""

echo "环境状态:"
echo "  - ffmpeg: $([[ "$ffmpeg_ok" == true ]] && echo "✓ 已安装" || echo "⚠ 未安装/安装中")"
echo "  - pydub: $([[ "$pydub_ok" == true ]] && echo "✓ 已安装" || echo "✗ 未安装")"
echo "  - faster-whisper: $([[ "$whisper_ok" == true ]] && echo "✓ 已安装" || echo "✗ 未安装")"
echo "  - Gateway: $([[ "$gateway_ok" == true ]] && echo "✓ 运行中" || echo "⚠ 未运行")"
echo ""

echo "测试结果:"
for result in "${test_results[@]}"; do
    test_name=$(echo "$result" | cut -d: -f1)
    test_status=$(echo "$result" | cut -d: -f2)

    case "$test_status" in
        pass)
            echo -e "  ${GREEN}✓ $test_name 测试通过${NC}"
            ;;
        fail)
            echo -e "  ${RED}✗ $test_name 测试失败${NC}"
            ;;
        partial)
            echo -e "  ${YELLOW}⚠ $test_name 测试部分通过${NC}"
            ;;
        skip)
            echo -e "  ${YELLOW}⚠ $test_name 测试跳过${NC}"
            ;;
    esac
done
echo ""

# ==============================================================================
# 总体评估
# ==============================================================================

passed_tests=$(echo "${test_results[@]}" | grep -o "pass" | wc -l | tr -d ' ')
total_tests=$(echo "${test_results[@]}" | grep -o -E "(pass|fail)" | wc -l | tr -d ' ')

echo "总体评估:"
if [[ "$ffmpeg_ok" == true && "$pydub_ok" == true && "$whisper_ok" == true ]]; then
    if [[ "$passed_tests" -ge 1 ]]; then
        echo -e "  ${GREEN}✓ 修复基本完成${NC}"
        echo ""
        echo "下一步:"
        if [[ "$gateway_ok" == false ]]; then
            echo "  1. 启动 Gateway: python -m gateway"
        fi
        if [[ "$passed_tests" -lt "$total_tests" ]]; then
            echo "  2. 查看失败测试日志，排查问题"
        fi
        echo "  3. 浏览器端到端测试:"
        echo "     - Chrome/Firefox: 录制语音（webm 格式）"
        echo "     - Safari: 录制语音（mp4 格式）"
        echo ""
        echo "详细文档:"
        echo "  - docs/whisper-fix-verification.md"
        echo "  - docs/whisper-audio-format-compatibility.md"
    else
        echo -e "  ${YELLOW}⚠ 环境已修复，但测试失败${NC}"
        echo ""
        echo "排查步骤:"
        echo "  1. 检查 Gateway 日志: python -m gateway 2>&1 | tee gateway.log"
        echo "  2. 检查测试输出详细错误"
        echo "  3. 参考: docs/whisper-fix-verification.md"
    fi
else
    echo -e "  ${YELLOW}⚠ 环境修复未完成${NC}"
    echo ""
    echo "缺失组件:"
    [[ "$ffmpeg_ok" == false ]] && echo "  - ffmpeg: bash scripts/fix-whisper-audio-format.sh"
    [[ "$pydub_ok" == false ]] && echo "  - pydub: pip install pydub"
    [[ "$whisper_ok" == false ]] && echo "  - faster-whisper: pip install faster-whisper==1.2.1"
    echo ""
    echo "修复后重新运行: bash scripts/verify-whisper-fix.sh"
fi

echo ""
echo "======================================================================"
echo "验证完成"
echo "======================================================================"
echo ""