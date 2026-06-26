#!/bin/bash
#
# 修复 Whisper 语音识别依赖问题
#
# 问题：
# 1. NumPy 2.x 与 faster-whisper 不兼容
# 2. OpenMP 库重复初始化（Intel MKL 与 PyTorch 冲突）
#
# Usage:
#   ./scripts/fix-whisper-dependencies.sh
#

set -e

echo "======================================================================"
echo "修复 Whisper 语音识别依赖问题"
echo "======================================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "${YELLOW}⚠ 虚拟环境 .venv 不存在${NC}"
    echo "建议创建虚拟环境："
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    exit 1
fi

echo "激活虚拟环境..."
source .venv/bin/activate

echo ""
echo "检查 NumPy 版本..."
NUMPY_VERSION=$(python -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "未安装")

echo "当前 NumPy 版本: $NUMPY_VERSION"

if [[ $NUMPY_VERSION =~ ^2\. ]]; then
    echo "${RED}✗ NumPy 2.x 与 faster-whisper 不兼容${NC}"
    echo ""
    echo "修复方案：降级到 NumPy 1.x"
    echo ""

    # 卸载 NumPy 2.x
    pip uninstall numpy -y

    # 安装 NumPy 1.x
    pip install "numpy<2"

    echo "${GREEN}✓ NumPy 已降级到 1.x${NC}"
else
    echo "${GREEN}✓ NumPy 版本兼容${NC}"
fi

echo ""
echo "验证 faster-whisper 安装..."
pip show faster-whisper || pip install faster-whisper==1.2.1

echo ""
echo "======================================================================"
echo "依赖修复完成"
echo "======================================================================"
echo ""
echo "下一步："
echo "  1. 运行预热脚本下载模型："
echo "     python scripts/preload_whisper_model.py"
echo ""
echo "  2. 或启动 Gateway："
echo "     python -m gateway"
echo ""
echo "环境变量已自动设置："
echo "  - KMP_DUPLICATE_LIB_OK=TRUE（修复 OpenMP 冲突）"
echo "  - HF_ENDPOINT=https://hf-mirror.com（使用中国镜像）"
echo ""