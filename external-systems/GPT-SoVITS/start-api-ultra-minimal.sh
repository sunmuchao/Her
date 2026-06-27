#!/bin/bash
cd "$(dirname "$0")"

if [ -f "/Users/sunmuchao/Downloads/Her/.venv/bin/activate" ]; then
    source /Users/sunmuchao/Downloads/Her/.venv/bin/activate
fi

echo "启动 GPT-SoVITS API 服务（超简化版）..."
echo "API 地址：http://localhost:9880"
echo "注意：此版本跳过了 librosa/numba/llvmlite"
echo "部分音频处理功能可能受限，但核心 TTS 功能可用"
echo ""

python api_v2.py -a 0.0.0.0 -p 9880
