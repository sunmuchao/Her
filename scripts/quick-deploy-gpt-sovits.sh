#!/bin/bash

# GPT-SoVITS 快速部署脚本（无需 Conda）
# 用法：./quick-deploy-gpt-sovits.sh

set -e

echo "========================================="
echo "GPT-SoVITS 快速部署（CPU 模式）"
echo "========================================="
echo ""

# 配置
GPT_SOVITS_DIR="/Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS"
HF_ENDPOINT="https://hf-mirror.com"  # 中国镜像
MODEL_DIR="$GPT_SOVITS_DIR/GPT_SoVITS/pretrained_models"

# 步骤 1：进入目录
echo "步骤 1：进入 GPT-SoVITS 目录..."
cd "$GPT_SOVITS_DIR"
echo "✅ 当前目录：$(pwd)"
echo ""

# 步骤 2：安装 Python 依赖
echo "步骤 2：安装 Python 依赖..."
echo ""

# 使用项目的虚拟环境（如果存在）
if [ -d "/Users/sunmuchao/Downloads/Her/.venv" ]; then
    echo "使用项目虚拟环境..."
    source /Users/sunmuchao/Downloads/Her/.venv/bin/activate
fi

# 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "✅ Python 依赖安装完成"
echo ""

# 步骤 3：下载预训练模型
echo "步骤 3：下载预训练模型..."
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
        wget -O "$output" "$url" --timeout=120 --tries=3 --progress=bar:force
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

# 下载核心模型
echo "=== 下载核心模型（必需） ==="
download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2bert48cn.pt" \
    "$MODEL_DIR/s2bert48cn.pt" \
    "GPT 模型（约 1GB）"

download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2dim488.pt" \
    "$MODEL_DIR/s2dim488.pt" \
    "SoVITS 模型（约 500MB）"

# 下载中文 RoBERTa 模型（可选，如果下载失败可以跳过）
echo ""
echo "=== 下载中文 RoBERTa 模型（可选） ==="
if download_file \
    "$HF_ENDPOINT/hfl/chinese-roberta-wwm-ext-large/resolve/main/pytorch_model.bin" \
    "$MODEL_DIR/chinese-roberta-wwm-ext-large.bin" \
    "中文 RoBERTa 模型（约 1.2GB）"; then
    echo "✅ RoBERTa 模型下载成功"
else
    echo "⚠️  RoBERTa 模型下载失败，但不影响基本功能"
fi

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

    # 检查 edge-tts
    if ! pip show edge-tts &> /dev/null; then
        echo "安装 edge-tts..."
        pip install edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
    fi

    # 检查 ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        echo "⚠️  ffmpeg 未安装，无法转换音频格式"
        echo "请手动安装：brew install ffmpeg"
        echo "或手动准备 WAV 格式音色样本"
    else
        echo "使用 edge-tts 生成音色样本..."
        edge-tts --text "你好，我是小雅，很高兴认识你。有什么可以帮助你的吗？" \
            --voice zh-CN-XiaoxiaoNeural \
            --write-media "$REFERENCE_DIR/xiaoya-sample.mp3"

        # 转换为 WAV
        ffmpeg -y -i "$REFERENCE_DIR/xiaoya-sample.mp3" \
            -ar 16000 -ac 1 -acodec pcm_s16le \
            "$XIAOYA_SAMPLE"

        rm "$REFERENCE_DIR/xiaoya-sample.mp3"

        echo "✅ 小雅音色样本生成完成"
        ls -lh "$XIAOYA_SAMPLE"
    fi
fi

echo ""

# 步骤 5：启动 API 服务
echo "步骤 5：启动 API 服务..."
echo ""

echo "准备启动 API 服务（端口 9880）..."
echo ""
echo "启动命令："
echo "python api_v2.py -a 0.0.0.0 -p 9880"
echo ""
echo "API 接口："
echo "POST http://localhost:9880/tts"
echo ""
echo "参数示例："
echo '{'
echo '  "text": "你好，我是小雅",'
echo '  "text_lang": "zh",'
echo '  "ref_audio_path": "reference_audio/xiaoya-sample.wav",'
echo '  "prompt_text": "你好，我是小雅，很高兴认识你",'
echo '  "prompt_lang": "zh",'
echo '  "top_k": 15,'
echo '  "top_p": 1,'
echo '  "temperature": 1,'
echo '  "speed_factor": 1.0'
echo '}'
echo ""

# 创建启动脚本
cat > "$GPT_SOVITS_DIR/start-api.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

# 激活虚拟环境（如果存在）
if [ -f "/Users/sunmuchao/Downloads/Her/.venv/bin/activate" ]; then
    source /Users/sunmuchao/Downloads/Her/.venv/bin/activate
fi

# 启动 API 服务
echo "启动 GPT-SoVITS API 服务..."
python api_v2.py -a 0.0.0.0 -p 9880

EOF

chmod +x "$GPT_SOVITS_DIR/start-api.sh"

echo "✅ 启动脚本已创建：$GPT_SOVITS_DIR/start-api.sh"
echo ""

# 完成提示
echo "========================================="
echo "部署完成！"
echo "========================================="
echo ""
echo "下一步："
echo "1. 启动 API 服务："
echo "   cd $GPT_SOVITS_DIR"
echo "   ./start-api.sh"
echo ""
echo "2. 测试语音合成："
echo "   curl -X POST http://localhost:9880/tts"
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
echo "3. 播放测试音频："
echo "   afplay test.wav"
echo ""
echo "注意事项："
echo "- 首次运行会加载模型，可能需要等待 10-30 秒"
echo "- CPU 模式合成速度约 10-20秒/条"
echo "- 模型加载后会占用约 2-4GB 内存"
echo ""