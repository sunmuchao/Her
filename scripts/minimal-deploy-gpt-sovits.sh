#!/bin/bash

# GPT-SoVITS 简化部署脚本（跳过复杂依赖）
# 用法：./minimal-deploy-gpt-sovits.sh

set -e

echo "========================================="
echo "GPT-SoVITS 简化部署（仅核心 TTS 功能）"
echo "========================================="
echo ""

# 配置
GPT_SOVITS_DIR="/Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS"
HF_ENDPOINT="https://hf-mirror.com"
MODEL_DIR="$GPT_SOVITS_DIR/GPT_SoVITS/pretrained_models"

# 步骤 1：进入目录
echo "步骤 1：进入 GPT-SoVITS 目录..."
cd "$GPT_SOVITS_DIR"
echo "✅ 当前目录：$(pwd)"
echo ""

# 步骤 2：安装核心依赖（简化版）
echo "步骤 2：安装核心 Python 依赖（简化版）..."
echo ""

if [ -f "/Users/sunmuchao/Downloads/Her/.venv/bin/activate" ]; then
    source /Users/sunmuchao/Downloads/Her/.venv/bin/activate
fi

pip install -r requirements-minimal.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "✅ 核心依赖安装完成"
echo ""

# 步骤 3：下载核心模型
echo "步骤 3：下载核心预训练模型..."
echo ""

mkdir -p "$MODEL_DIR"
export HF_ENDPOINT="$HF_ENDPOINT"

# 下载函数
download_file() {
    local url=$1
    local output=$2
    local description=$3

    echo "下载 $description..."

    if command -v wget &> /dev/null; then
        wget -O "$output" "$url" --timeout=120 --tries=3 --progress=bar:force || {
            echo "⚠️  wget 失败，尝试 curl..."
            curl -L -o "$output" "$url" --max-time 120 --retry 3
        }
    else
        curl -L -o "$output" "$url" --max-time 120 --retry 3 --progress-bar
    fi

    if [ -f "$output" ] && [ -s "$output" ]; then
        echo "✅ $description 下载完成 ($(du -h "$output" | cut -f1))"
    else
        echo "❌ $description 下载失败"
        rm -f "$output"
        return 1
    fi
}

# 仅下载必需的模型
download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2bert48cn.pt" \
    "$MODEL_DIR/s2bert48cn.pt" \
    "GPT 模型（约 1GB）"

download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2dim488.pt" \
    "$MODEL_DIR/s2dim488.pt" \
    "SoVITS 模型（约 500MB）"

echo ""
echo "模型文件列表："
ls -lh "$MODEL_DIR"
echo ""

# 步骤 4：准备小雅音色样本
echo "步骤 4：准备小雅音色样本..."
echo ""

REFERENCE_DIR="$GPT_SOVITS_DIR/reference_audio"
mkdir -p "$REFERENCE_DIR"

XIAOYA_SAMPLE="$REFERENCE_DIR/xiaoya-sample.wav"

if [ -f "$XIAOYA_SAMPLE" ]; then
    echo "✅ 小雅音色样本已存在"
    ls -lh "$XIAOYA_SAMPLE"
else
    echo "生成小雅音色样本..."

    if ! pip show edge-tts &> /dev/null; then
        pip install edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
    fi

    if command -v ffmpeg &> /dev/null; then
        edge-tts --text "你好，我是小雅，很高兴认识你。有什么可以帮助你的吗？" \
            --voice zh-CN-XiaoxiaoNeural \
            --write-media "$REFERENCE_DIR/xiaoya-sample.mp3"

        ffmpeg -y -i "$REFERENCE_DIR/xiaoya-sample.mp3" \
            -ar 16000 -ac 1 -acodec pcm_s16le \
            "$XIAOYA_SAMPLE"

        rm "$REFERENCE_DIR/xiaoya-sample.mp3"
        echo "✅ 小雅音色样本生成完成"
        ls -lh "$XIAOYA_SAMPLE"
    else
        echo "⚠️  ffmpeg 未安装，跳过音色样本生成"
        echo "请手动准备 WAV 格式音色样本到：$XIAOYA_SAMPLE"
    fi
fi

echo ""

# 步骤 5：创建启动脚本
echo "步骤 5：创建启动脚本..."
echo ""

cat > "$GPT_SOVITS_DIR/start-api-minimal.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

if [ -f "/Users/sunmuchao/Downloads/Her/.venv/bin/activate" ]; then
    source /Users/sunmuchao/Downloads/Her/.venv/bin/activate
fi

echo "启动 GPT-SoVITS API 服务（简化版）..."
echo "API 地址：http://localhost:9880"
echo ""

python api_v2.py -a 0.0.0.0 -p 9880
EOF

chmod +x "$GPT_SOVITS_DIR/start-api-minimal.sh"

echo "✅ 启动脚本已创建：$GPT_SOVITS_DIR/start-api-minimal.sh"
echo ""

# 完成提示
echo "========================================="
echo "简化部署完成！"
echo "========================================="
echo ""
echo "注意事项："
echo "- 此版本跳过了部分复杂依赖（如 numba、llvmlite）"
echo "- 可能缺少某些高级功能（如 ASR、音色训练）"
echo "- 但核心 TTS 功能完全可用"
echo ""
echo "下一步："
echo "1. 启动 API 服务："
echo "   cd $GPT_SOVITS_DIR"
echo "   ./start-api-minimal.sh"
echo ""
echo "2. 测试语音合成："
echo '   curl -X POST http://localhost:9880/tts'
echo '   -H "Content-Type: application/json"'
echo '   -d @- <<JSON'
echo '{'
echo '  "text": "你好，我是小雅",'
echo '  "text_lang": "zh",'
echo '  "ref_audio_path": "reference_audio/xiaoya-sample.wav",'
echo '  "prompt_text": "你好，我是小雅",'
echo '  "prompt_lang": "zh"'
echo '}'
echo 'JSON'
echo '   --output test.wav'
echo ""
echo "3. 如果需要完整功能，请安装 LLVM 工具链后重新运行原脚本"
echo ""