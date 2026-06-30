# Whisper 语音识别网络超时问题排查

## 问题现象

```
ConnectTimeout: [Errno 60] Operation timed out
huggingface_hub.errors.LocalEntryNotFoundError
An error happened while trying to locate the files on the Hub
```

**错误原因**：
- Whisper 模型需要从 Hugging Face Hub（huggingface.co）下载
- 连接 huggingface.co 网络超时（防火墙或网络限制）
- 本地没有缓存的模型文件

---

## 解决方案

### 方案 1：使用 Hugging Face 中国镜像（推荐，已配置）

**配置已自动生效**：
- ✅ [voice_routes.py](../external-systems/partner-http-gateway/gateway/voice_routes.py#L8-L9) 已添加镜像配置
- ✅ [.env](../.env#L51-L58) 已配置 `HF_ENDPOINT=https://hf-mirror.com`

**只需重启 Gateway**：
```bash
# 重启 Gateway 服务
docker compose up -d gateway-public
```

**镜像站点说明**：
- `https://hf-mirror.com` - Hugging Face 中国镜像（推荐）
- `https://huggingface.co` - 官方站点（国外网络）

---

### 方案 2：手动下载模型文件

如果镜像也无法访问，可以手动下载模型文件到本地缓存：

**步骤 1：创建模型缓存目录**
```bash
mkdir -p ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
cd ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
```

**步骤 2：下载模型文件**

访问国内镜像站点下载：
- **small 模型**：https://hf-mirror.com/Systran/faster-whisper-small
- **medium 模型**：https://hf-mirror.com/Systran/faster-whisper-medium

或使用其他下载工具：
```bash
# 使用 wget 下载（如果有代理）
wget https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/model.bin

# 或使用 curl
curl -L https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/model.bin -o model.bin
```

**步骤 3：验证模型文件**
```bash
ls -lh ~/.cache/huggingface/hub/models--Systran--faster-whisper-small/
# 应该看到 blobs/ refs/ snapshots/ 目录
```

---

### 方案 3：使用 HTTP 代理

如果有 HTTP 代理，可以配置环境变量：

```bash
# 配置 HTTP 代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890

# 或在 .env 文件中添加
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# 重启 Gateway
docker compose up -d gateway-public
```

---

### 方案 4：使用更小的模型（已配置）

**已自动配置为 `small` 模型**：
- ✅ 下载大小：约 **500MB**（比 medium 的 1.5GB 小得多）
- ✅ 下载时间：约 **1-2 分钟**（vs medium 的 5-10 分钟）
- ✅ 准确率：仍然很高，适合大多数场景

如果需要更高准确率，可以在下载成功后改为 `medium`：
```bash
# 在 .env 中修改
WHISPER_MODEL_SIZE=medium
```

---

## 验证修复

### 1. 检查 Gateway 日志

重启 Gateway 后，查看日志是否显示镜像配置：
```bash
tail -f .run/logs/gateway.log
```

**预期输出**：
```
Loading Whisper model: size=small, device=cpu, compute_type=int8
Using Hugging Face endpoint: https://hf-mirror.com
Whisper model loaded successfully
```

### 2. 测试语音识别

刷新浏览器页面，再次测试语音识别：
- 按住麦克风说话
- 松开后等待 **1-2 分钟**（首次下载）
- 第二次请求会很快（模型已缓存）

---

## 常见问题排查

### Q1: 镜像也无法访问

**原因**：镜像站点也可能被限制

**解决**：
1. 尝试其他镜像站点：
   ```bash
   # 在 .env 中修改
   HF_ENDPOINT=https://huggingface.co  # 官方站点
   ```

2. 或使用 HTTP 代理（方案 3）

### Q2: 模型下载成功但识别失败

**原因**：模型文件损坏或不完整

**解决**：
```bash
# 清理缓存重新下载
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-*

# 重启 Gateway
docker compose up -d gateway-public
```

### Q3: 识别速度慢

**原因**：使用 CPU + 模型较大

**解决**：
```bash
# 使用更小的模型
WHISPER_MODEL_SIZE=small

# 或使用 GPU（如果有）
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

---

## 模型大小对比

| 模型 | 下载大小 | 下载时间（镜像） | 准确率 | 推荐场景 |
|------|---------|----------------|-------|---------|
| **tiny** | ~40MB | 10 秒 | 低 | 测试 |
| **small** | ~500MB | 1-2 分钟 | 高 | ✅ **当前配置（推荐）** |
| **medium** | ~1.5GB | 5-10 分钟 | 很高 | 生产环境 |
| **large** | ~3GB | 15-30 分钟 | 最高 | 专业场景 |

---

## 网络诊断命令

检查网络连接：
```bash
# 测试官方站点
ping huggingface.co

# 测试中国镜像
ping hf-mirror.com

# 测试 HTTP 连接
curl -I https://hf-mirror.com
curl -I https://huggingface.co
```

---

## 配置总结

**当前配置（已生效）**：
- ✅ 模型大小：`small`（500MB）
- ✅ 镜像站点：`https://hf-mirror.com`
- ✅ 运行设备：`cpu`
- ✅ 计算类型：`int8`

**下一步操作**：
1. 重启 Gateway：`docker compose restart gateway-public`
2. 等待 1-2 分钟下载模型
3. 测试语音识别

---

生成时间：2026-06-26
作者：Claude Code
