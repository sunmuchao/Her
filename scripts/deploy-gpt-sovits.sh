#!/bin/bash

# GPT-SoVITS 一键部署脚本
# 用法：./deploy-gpt-sovits.sh

set -e  # 遇到错误立即退出

echo "========================================="
echo "GPT-SoVITS 一键部署脚本"
echo "========================================="
echo ""

# 配置变量
PROJECT_DIR="/Users/sunmuchao/Downloads/Her/external-systems"
GPT_SOVITS_DIR="$PROJECT_DIR/GPT-SoVITS"
MODEL_DIR="$GPT_SOVITS_DIR/GPT_SoVITS/pretrained_models"
HF_ENDPOINT="https://hf-mirror.com"  # 中国镜像

# 步骤 1：检查依赖
echo "步骤 1：检查依赖..."
echo ""

if ! command -v git &> /dev/null; then
    echo "❌ Git 未安装，请先安装 Git"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v wget &> /dev/null && ! command -v curl &> /dev/null; then
    echo "❌ wget 或 curl 未安装，请先安装"
    exit 1
fi

echo "✅ 依赖检查通过"
echo ""

# 步骤 2：克隆仓库
echo "步骤 2：克隆 GPT-SoVITS 仓库..."
echo ""

if [ -d "$GPT_SOVITS_DIR" ]; then
    echo "⚠️  目录已存在，跳过克隆"
    cd "$GPT_SOVITS_DIR"
else
    cd "$PROJECT_DIR"

    # 尝试使用 Gitee 镜像（中国更快）
    echo "尝试使用 Gitee 镜像..."
    if git clone https://gitee.com/RVC-Boss/GPT-SoVITS.git; then
        echo "✅ 从 Gitee 克隆成功"
    else
        echo "Gitee 克隆失败，尝试 GitHub..."
        if git clone https://github.com/RVC-Boss/GPT-SoVITS.git; then
            echo "✅ 从 GitHub 克隆成功"
        else
            echo "❌ 克隆失败，请检查网络或手动下载"
            exit 1
        fi
    fi

    cd "$GPT_SOVITS_DIR"
fi

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
        wget -O "$output" "$url" --timeout=60 --tries=3
    else
        curl -L -o "$output" "$url" --max-time 60 --retry 3
    fi

    if [ -f "$output" ]; then
        echo "✅ $description 下载完成"
        ls -lh "$output"
    else
        echo "❌ $description 下载失败"
        return 1
    fi
}

# 下载 GPT 模型（约 1GB）
download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2bert48cn.pt" \
    "$MODEL_DIR/s2bert48cn.pt" \
    "GPT 模型"

# 下载 SoVITS 模型（约 500MB）
download_file \
    "$HF_ENDPOINT/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2dim488.pt" \
    "$MODEL_DIR/s2dim488.pt" \
    "SoVITS 模型"

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
    echo "⚠️  未找到小雅音色样本，需要准备"

    # 方案 1：使用 edge-tts 生成样本（推荐）
    if command -v edge-tts &> /dev/null; then
        echo "使用 edge-tts 生成小雅音色样本..."
        edge-tts --text "你好，我是小雅，很高兴认识你。有什么可以帮助你的吗？" \
            --voice zh-CN-XiaoxiaoNeural \
            --write-media "$REFERENCE_DIR/xiaoya-sample.mp3"

        # 转换为 WAV
        if command -v ffmpeg &> /dev/null; then
            ffmpeg -i "$REFERENCE_DIR/xiaoya-sample.mp3" \
                -ar 16000 -ac 1 "$XIAOYA_SAMPLE"
            echo "✅ 小雅音色样本生成完成"
            rm "$REFERENCE_DIR/xiaoya-sample.mp3"
        else
            echo "⚠️  ffmpeg 未安装，无法转换为 WAV"
            echo "请手动准备 WAV 格式样本"
        fi
    else
        echo "⚠️  edge-tts 未安装，无法生成样本"
        echo ""
        echo "请手动准备小雅音色样本："
        echo "1. 录制 5-10 秒的女声音频（温柔、友好）"
        echo "2. 格式：WAV（16-bit PCM）"
        echo "3. 保存到：$XIAOYA_SAMPLE"
        echo ""
        echo "或安装 edge-tts："
        echo "pip install edge-tts"
    fi
fi

echo ""

# 步骤 5：Docker 部署
echo "步骤 5：Docker 部署..."
echo ""

# 检查是否已部署
if docker ps | grep -q gpt-sovits-service; then
    echo "⚠️  GPT-SoVITS 容器已运行，跳过部署"
else
    # 创建 docker-compose.yml（如果不存在）
    if [ ! -f "docker-compose.yml" ]; then
        echo "创建 docker-compose.yml..."
        cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  gpt-sovits:
    build: .
    container_name: gpt-sovits-service
    ports:
      - "9880:9880"  # API 端口
      - "9874:9874"  # Web UI 端口（可选）
    volumes:
      - ./GPT_SoVITS/pretrained_models:/app/GPT_SoVITS/pretrained_models
      - ./output:/app/output  # 输出音频目录
      - ./reference_audio:/app/reference_audio  # 参考音频目录
    environment:
      - DEVICE=cpu  # 或 cuda（如果有 GPU）
      - MODEL_PATH=/app/GPT_SoVITS/pretrained_models
      - API_PORT=9880
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9880/health"]
      interval: 30s
      timeout: 10s
      retries: 3
EOF
        echo "✅ docker-compose.yml 创建完成"
    fi

    echo "构建 Docker 镜像..."
    docker build -t gpt-sovits:latest .

    echo "启动 Docker 容器..."
    docker-compose up -d

    echo "✅ Docker 部署完成"
fi

echo ""

# 步骤 6：等待服务启动
echo "步骤 6：等待服务启动..."
echo ""

echo "等待 30 秒让服务完全启动..."
sleep 30

# 检查服务状态
if curl -f http://localhost:9880/health &> /dev/null; then
    echo "✅ GPT-SoVITS 服务已启动"
    echo ""
    echo "API 地址：http://localhost:9880"
    echo "API 文档：http://localhost:9880/docs"
    echo "Web UI：http://localhost:9874"
else
    echo "⚠️  服务启动可能失败，请检查日志"
    echo ""
    echo "查看日志："
    echo "docker logs gpt-sovits-service"
fi

echo ""

# 步骤 7：测试语音合成
echo "步骤 7：测试语音合成..."
echo ""

OUTPUT_DIR="$GPT_SOVITS_DIR/output"
mkdir -p "$OUTPUT_DIR"

echo "测试合成语音..."
if curl -X POST http://localhost:9880/tts \
    -H "Content-Type: application/json" \
    -d '{"text": "你好，我是小雅，很高兴认识你", "text_lang": "zh"}' \
    --output "$OUTPUT_DIR/test.wav" \
    --max-time 30; then

    if [ -f "$OUTPUT_DIR/test.wav" ]; then
        echo "✅ 语音合成成功"
        ls -lh "$OUTPUT_DIR/test.wav"

        echo ""
        echo "播放测试音频："
        echo "afplay $OUTPUT_DIR/test.wav  # macOS"
        echo "vlc $OUTPUT_DIR/test.wav     # Linux"
    else
        echo "⚠️  测试音频未生成"
    fi
else
    echo "⚠️  语音合成测试失败"
fi

echo ""

# 完成
echo "========================================="
echo "部署完成！"
echo "========================================="
echo ""
echo "下一步："
echo "1. 训练小雅专属音色（如果未准备）"
echo "   - 打开 Web UI: http://localhost:9874"
echo "   - 上传音色样本: $XIAOYA_SAMPLE"
echo "   - 训练音色名称: xiaoya-default"
echo ""
echo "2. 测试小雅音色"
echo "   curl -X POST http://localhost:9880/tts"
echo "   -d '{\"text\": \"你好，我是小雅\", \"speaker\": \"xiaoya-default\"}'"
echo ""
echo "3. 查看服务状态"
echo "   docker logs gpt-sovits-service"
echo ""
echo "4. 停止服务"
echo "   docker-compose down"
echo ""
echo "5. 重启服务"
echo "   docker-compose restart"
echo ""