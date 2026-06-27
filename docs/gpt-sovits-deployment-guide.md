# GPT-SoVITS 部署指南

## 一、快速部署方案（Docker）

### 1.1 系统要求

- **操作系统**：Linux / macOS / Windows (with Docker)
- **内存**：至少 4GB RAM（推荐 8GB）
- **存储**：至少 10GB 可用空间（模型 + 音频）
- **GPU**：可选（CUDA 支持，但 CPU 也能运行）

### 1.2 方案选择

**方案 A：使用官方 Docker 部署（推荐）**
- ✅ 最简单，一键部署
- ✅ 包含 Web UI 和 API
- ✅ 官方维护，稳定性好

**方案 B：使用第三方 FastAPI 包装**
- ✅ 更轻量，专注于 API
- ✅ 适合生产环境
- ❌ 需要额外配置

**方案 C：手动 Python 部署**
- ✅ 最灵活，完全可控
- ❌ 配置复杂，依赖多

**推荐选择方案 A**（快速上手，后续可迁移到方案 B）

---

## 二、方案 A：官方 Docker 部署

### 2.1 克隆官方仓库

```bash
cd /Users/sunmuchao/Downloads/Her/external-systems
git clone https://github.com/RVC-Boss/GPT-SoVITS.git
cd GPT-SoVITS
```

**中国用户镜像加速**：
```bash
# 使用 Gitee 镜像（更快）
git clone https://gitee.com/RVC-Boss/GPT-SoVITS.git
```

### 2.2 下载预训练模型

**模型下载脚本**：
```bash
# 创建模型下载脚本
cat > download_models.sh << 'EOF'
#!/bin/bash

# 设置 Hugging Face 镜像（中国用户）
export HF_ENDPOINT=https://hf-mirror.com

# 模型保存目录
MODEL_DIR="./GPT_SoVITS/pretrained_models"
mkdir -p "$MODEL_DIR"

echo "开始下载 GPT-SoVITS 预训练模型..."

# 下载 GPT 模型（约 1GB）
echo "下载 GPT 模型..."
wget -O "$MODEL_DIR/s2bert48cn.pt" \
  "https://hf-mirror.com/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2bert48cn.pt" \
  || curl -L -o "$MODEL_DIR/s2bert48cn.pt" \
  "https://hf-mirror.com/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2bert48cn.pt"

# 下载 SoVITS 模型（约 500MB）
echo "下载 SoVITS 模型..."
wget -O "$MODEL_DIR/s2dim488.pt" \
  "https://hf-mirror.com/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2dim488.pt" \
  || curl -L -o "$MODEL_DIR/s2dim488.pt" \
  "https://hf-mirror.com/RVC-Boss/GPT-SoVITS/resolve/main/pretrained_models/s2dim488.pt"

# 下载中文 RoBERTa 模型（约 400MB）
echo "下载中文 RoBERTa 模型..."
wget -O "$MODEL_DIR/chinese-roberta-wwm-ext-large.tar.gz" \
  "https://hf-mirror.com/hfl/chinese-roberta-wwm-ext-large/resolve/main/pytorch_model.bin" \
  || curl -L -o "$MODEL_DIR/chinese-roberta-wwm-ext-large.tar.gz" \
  "https://hf-mirror.com/hfl/chinese-roberta-wwm-ext-large/resolve/main/pytorch_model.bin"

echo "模型下载完成！"
echo "模型文件列表："
ls -lh "$MODEL_DIR"

EOF

chmod +x download_models.sh
./download_models.sh
```

### 2.3 Docker 部署

**Dockerfile（官方提供）**：
```bash
# 使用官方 Dockerfile
docker build -t gpt-sovits:latest .
```

**或使用预构建镜像（如果有）**：
```bash
# 搜索 Docker Hub 是否有预构建镜像
docker search gpt-sovits
```

**Docker Compose 配置**：
```yaml
# docker-compose.yml
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
```

**启动服务**：
```bash
docker-compose up -d
```

### 2.4 验证部署

**检查服务状态**：
```bash
# 查看容器日志
docker logs gpt-sovits-service

# 检查 API 是否启动
curl http://localhost:9880/health

# 查看 API 文档
open http://localhost:9880/docs  # Swagger UI
```

**测试语音合成**：
```bash
# 简单测试
curl -X POST http://localhost:9880/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，我是小雅，很高兴认识你",
    "text_lang": "zh"
  }' \
  --output test_audio.wav

# 播放测试音频
afplay test_audio.wav  # macOS
# 或
vlc test_audio.wav  # Linux
```

---

## 三、小雅专属音色训练

### 3.1 准备音色样本

**音色样本要求**：
- **时长**：5-10 秒（推荐）
- **质量**：
  - 清晰、无噪音
  - 自然语调，不要夸张
  - 单一说话人
- **格式**：WAV（16-bit PCM）、MP3（高质量）
- **采样率**：16kHz 或更高

**小雅音色建议**：
- **风格**：温柔、友好、亲切
- **语速**：中等偏慢（适合语音助手）
- **音调**：中等偏高（女性音色）

**录制方案**：

**方案 1：真人录制（最佳）**
```bash
# 找一位声音温柔的女性录制
# 录制内容建议：
"你好，我是小雅，很高兴认识你。有什么可以帮助你的吗？"

# 录制设备：手机录音机、电脑麦克风
# 录制环境：安静室内
```

**方案 2：使用现有语音库**
```bash
# 使用公开的中文女声语音库
# 注意：需要确保版权允许使用

# 示例：使用标准普通话女声
wget https://example.com/chinese-female-voice-sample.wav
```

**方案 3：使用其他 TTS 生成样本**
```bash
# 使用 edge-tts 生成样本（微软高质量女声）
pip install edge-tts

edge-tts --text "你好，我是小雅，很高兴认识你" \
  --voice zh-CN-XiaoxiaoNeural \
  --write-media xiaoya-sample.mp3

# 转换为 WAV 格式
ffmpeg -i xiaoya-sample.mp3 -ar 16000 -ac 1 xiaoya-sample.wav
```

### 3.2 训练小雅音色

**使用 Web UI 训练**：
```bash
# 打开 Web UI
open http://localhost:9874

# 步骤：
1. 进入 "声音克隆" 页面
2. 上传 xiaoya-sample.wav
3. 设置音色名称：xiaoya-default
4. 点击 "训练"
5. 等待训练完成（约 5-10 分钟）
```

**使用 API 训练**：
```bash
# 上传参考音频
curl -X POST http://localhost:9880/upload_reference \
  -F "audio=@xiaoya-sample.wav" \
  -F "speaker_name=xiaoya-default"

# 训练音色
curl -X POST http://localhost:9880/train_speaker \
  -H "Content-Type: application/json" \
  -d '{"speaker_name": "xiaoya-default"}'
```

### 3.3 验证音色

**测试小雅音色**：
```bash
# 使用小雅音色合成语音
curl -X POST http://localhost:9880/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，我是小雅，有什么可以帮助你的吗？",
    "text_lang": "zh",
    "speaker": "xiaoya-default"
  }' \
  --output xiaoya-test.wav

# 播放测试
afplay xiaoya-test.wav
```

---

## 四、API 接口说明

### 4.1 核心 API 接口

**1. 语音合成接口**：
```
POST /tts
```

**请求参数**：
```json
{
  "text": "你好，我是小雅",  // 要合成的文本
  "text_lang": "zh",         // 语言（zh/en/jp）
  "speaker": "xiaoya-default",  // 音色 ID
  "speed": 1.0,              // 语速（0.5-2.0）
  "top_k": 15,               // 采样参数
  "top_p": 1.0,              // 采样参数
  "temperature": 1.0,        // 温度参数
  "stream": false            // 是否流式输出
}
```

**响应**：
- Content-Type: audio/wav
- Body: WAV 音频数据

**2. 音色管理接口**：
```
GET /speakers              // 获取可用音色列表
POST /upload_reference     // 上传参考音频
POST /train_speaker        // 训练新音色
DELETE /speaker/{name}     // 删除音色
```

**3. 健康检查接口**：
```
GET /health                // 服务健康状态
```

### 4.2 Python SDK 使用

```python
import requests

# GPT-SoVITS API 地址
TTS_API_URL = "http://localhost:9880"

def synthesize_audio(text, speaker="xiaoya-default"):
    """合成语音"""
    response = requests.post(
        f"{TTS_API_URL}/tts",
        json={
            "text": text,
            "text_lang": "zh",
            "speaker": speaker,
            "speed": 1.0
        },
        timeout=30
    )

    if response.ok:
        return response.content  # WAV 音频数据
    else:
        raise Exception(f"TTS failed: {response.status_code}")

# 使用示例
audio_data = synthesize_audio("你好，我是小雅")
with open("output.wav", "wb") as f:
    f.write(audio_data)
```

---

## 五、生产环境配置

### 5.1 性能优化

**CPU 模式优化**：
```yaml
environment:
  - DEVICE=cpu
  - OMP_NUM_THREADS=4  # 限制 CPU 线程数
  - MKL_NUM_THREADS=4
```

**GPU 模式优化**：
```yaml
environment:
  - DEVICE=cuda
  - CUDA_VISIBLE_DEVICES=0  # 指定 GPU

deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

### 5.2 并发处理

**启动多个实例**：
```yaml
services:
  gpt-sovits-1:
    ports: ["9881:9880"]
  gpt-sovits-2:
    ports: ["9882:9880"]
  gpt-sovits-3:
    ports: ["9883:9880"]

  # 负载均衡器（可选）
  nginx:
    image: nginx
    ports: ["9880:80"]
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### 5.3 监控与日志

**添加监控**：
```yaml
services:
  gpt-sovits:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 六、故障排查

### 6.1 常见问题

**问题 1：模型下载失败**
```bash
# 解决：使用镜像或手动下载
export HF_ENDPOINT=https://hf-mirror.com
# 或从百度网盘/阿里云盘下载
```

**问题 2：内存不足**
```bash
# 解决：使用小模型或增加系统内存
# small 模型约 1GB，medium 模型约 2GB
```

**问题 3：合成速度慢**
```bash
# 解决：使用 GPU 或减少并发
# CPU 模式：约 10-20秒/条
# GPU 模式：约 2-5秒/条
```

**问题 4：音色训练失败**
```bash
# 解决：检查参考音频质量
# 确保时长 >= 5秒
# 确保格式正确（WAV）
```

### 6.2 日志查看

```bash
# Docker 日志
docker logs -f gpt-sovits-service

# 进入容器排查
docker exec -it gpt-sovits-service bash

# 查看模型加载日志
cat /app/logs/gpt-sovits.log
```

---

## 七、下一步

部署完成后，下一步：
1. ✅ 测试 API 接口
2. ✅ 训练小雅专属音色
3. ➡️ 实现 TTS API 路由（集成到 gateway）
4. ➡️ 扩展 media_storage.py（音频存储）
5. ➡️ 修改 Agent 回复流程（集成 TTS）
6. ➡️ 前端 AudioMessage 组件实现

---

**Sources:**
- [GPT-SoVITS GitHub](https://github.com/RVC-Boss/GPT-SoVITS)
- [Hugging Face Mirror](https://hf-mirror.com)
- [GPT-SoVITS Wiki](https://github.com/RVC-Boss/GPT-SoVITS/wiki)