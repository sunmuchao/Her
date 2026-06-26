#!/bin/bash
#
# 启动 Gateway 并自动预热 Whisper 模型
# 避免首次使用语音识别时超时
#
# Usage:
#   ./scripts/start-gateway-with-whisper.sh
#

set -e

echo "======================================================================"
echo "启动 Gateway + 预热 Whisper 模型"
echo "======================================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查是否已下载模型
CACHE_DIR="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-small"
MODEL_SIZE=$(grep WHISPER_MODEL_SIZE .env 2>/dev/null | cut -d'=' -f2 || echo "small")

if [ "$MODEL_SIZE" = "medium" ]; then
    CACHE_DIR="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-medium"
fi

echo "检查模型缓存: $CACHE_DIR"

if [ -d "$CACHE_DIR/snapshots" ]; then
    echo "${GREEN}✓ Whisper 模型已存在，无需重新下载${NC}"
    echo ""
else
    echo "${YELLOW}⚠ Whisper 模型未下载，开始预热...${NC}"
    echo ""

    # 运行预热脚本
    python scripts/preload_whisper_model.py

    if [ $? -eq 0 ]; then
        echo ""
        echo "${GREEN}✓ 模型预热成功${NC}"
        echo ""
    else
        echo ""
        echo "${YELLOW}⚠ 模型预热失败，首次使用语音识别时可能需要等待下载${NC}"
        echo ""
    fi
fi

echo "======================================================================"
echo "启动 Gateway 服务"
echo "======================================================================"
echo ""

# 启动 Gateway
python -m gateway