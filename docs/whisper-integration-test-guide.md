# Whisper 语音识别集成测试指南

## 🚀 启动服务（Docker Compose）

**统一启动方式**：

```bash
cd /Users/sunmuchao/Downloads/Her
docker compose up -d
docker compose ps
docker compose logs -f gateway-public frontend
```

**自动完成**：
- ✅ 启动 MySQL、Redis、MinIO
- ✅ 启动 Gateway（Public、Ops、Internal）
- ✅ 启动 Scheduler、SSE Server、Signaling Server
- ✅ 启动 Frontend（Next.js）
- ✅ 显示服务状态

** Whisper 模型预热**：

首次使用语音功能时，需要下载 Whisper 模型（500MB-1.5GB），建议提前预热：

```bash
python scripts/preload_whisper_model.py
```

---

## 架构说明

本项目使用 **Faster-Whisper** 进行语音识别，架构如下：

```
前端 (Next.js)                    后端 (Python Gateway)
┌─────────────────┐              ┌──────────────────┐
│ 按住录音        │              │ Whisper Model    │
│ MediaRecorder   │──────────────│ POST /v1/voice/  │
│ audio/webm     │  HTTP POST   │ transcribe       │
│ 松开发送        │  audio blob  │ faster-whisper   │
└─────────────────┘              │ medium/int8      │
                                 └──────────────────┘
```

---

## ⚠️ 网络超时问题（重要）

**如果遇到 "ConnectTimeout" 错误，请先解决网络问题！**

**错误现象**：
```
ConnectTimeout: [Errno 60] Operation timed out
huggingface_hub.errors.LocalEntryNotFoundError
```

**根本原因**：首次使用时需要从 Hugging Face Hub 下载模型（500MB-1.5GB）

**最佳解决方案**：**提前下载模型**（避免首次使用超时）

---

## ✅ 提前下载模型（推荐）

### 方案 1：预热模型脚本

```bash
cd /Users/sunmuchao/Downloads/Her
python scripts/preload_whisper_model.py
```

**优势**：
- ✅ 自动检查模型是否已下载
- ✅ 如果未下载，自动预热模型
- ✅ 使用镜像站点，下载速度快

---

### 方案 2：单独预热模型

```bash
cd /Users/sunmuchao/Downloads/Her
python scripts/preload_whisper_model.py
```

**优势**：
- ✅ 提前下载模型到缓存（~/.cache/huggingface/hub）
- ✅ 使用中国镜像，下载更快（1-2 分钟）
- ✅ 测试模型是否正常工作
- ✅ 后续使用无需等待下载

**预热完成后**，启动 Gateway：
```bash
docker compose up -d gateway-public
```

---

### 方案 3：自动配置（已生效）

**配置已自动优化**：
- ✅ 使用中国镜像：`HF_ENDPOINT=https://hf-mirror.com`
- ✅ 使用小模型：`WHISPER_MODEL_SIZE=small`（500MB）
- ✅ 配置在 [.env](../.env#L51-L58) 和 [voice_routes.py](../external-systems/partner-http-gateway/gateway/voice_routes.py#L8-L9)

**只需重启 Gateway**：
```bash
docker compose up -d gateway-public
```

---

**详细排查步骤**：
参见 [网络超时问题排查文档](../docs/whisper-network-timeout-troubleshooting.md)

---

## 测试运行指南

### 1. 后端单元测试

运行 Python Gateway 单元测试：

```bash
cd /Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway

# 运行所有测试
pytest

# 只运行语音识别测试
pytest gateway_tests/test_voice_routes.py

# 运行单元测试（不包括需要真实模型的集成测试）
pytest -m unit

# 运行集成测试（需要 Whisper 模型）
pytest -m integration

# 生成覆盖率报告
pytest --cov=gateway --cov-report=html
```

**预期结果**：
- 所有单元测试通过 ✓
- 集成测试可能跳过（如果没有测试音频文件）

### 2. 前端单元测试

运行 Next.js 前端单元测试：

```bash
cd /Users/sunmuchao/Downloads/Her/frontend/her-app

# 运行所有测试
npm test

# 只运行语音相关测试
npm test use-voice-input.test

# 运行 API endpoint 测试
npm test voice.test

# 生成覆盖率报告
npm test -- --coverage
```

**预期结果**：
- `use-voice-input.test.ts` - 所有测试通过 ✓
- `voice.test.ts` - 所有测试通过 ✓

### 3. 端到端集成测试

运行完整的端到端测试流程：

```bash
# 1. 启动后端 Gateway
cd /Users/sunmuchao/Downloads/Her
docker compose up -d gateway-public

# 2. 在另一个终端启动前端
cd frontend/her-app
npm run dev

# 3. 运行端到端测试脚本
cd /Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/tests
python test_voice_e2e.py
```

**预期结果**：
```
======================================================================
Voice Transcription End-to-End Test
======================================================================

Configuration:
  Backend URL: http://127.0.0.1:8080
  Next.js URL: http://localhost:3000

1. Testing health check...
   ✓ Gateway is healthy

2. Testing voice transcription...
   ✓ Transcription successful

3. Testing via Next.js gateway proxy...
   ✓ Via Next.js proxy successful

======================================================================
Test Summary:
  Passed: 3/3
  Failed: 0/3

✓ All tests passed!
```

---

## 测试文件清单

### 后端测试文件

| 文件路径 | 测试内容 | 类型 |
|---------|---------|------|
| [test_voice_routes.py](../external-systems/partner-http-gateway/gateway_tests/test_voice_routes.py) | voice_routes.py 单元测试 | Unit + Integration |
| [test_voice_e2e.py](../external-systems/partner-http-gateway/tests/test_voice_e2e.py) | 端到端集成测试 | E2E |
| [fixtures/README.md](../external-systems/partner-http-gateway/tests/fixtures/README.md) | 测试音频文件说明 | - |

### 前端测试文件

| 文件路径 | 测试内容 | 类型 |
|---------|---------|------|
| [use-voice-input.test.ts](../frontend/her-app/hooks/tests/use-voice-input.test.ts) | useVoiceInput hook 单元测试 | Unit |
| [voice.test.ts](../frontend/her-app/lib/api/tests/voice.test.ts) | voice API endpoint 单元测试 | Unit |

---

## 创建真实测试音频

为了运行集成测试，你需要创建真实的音频文件：

### 方法 1：浏览器录制（推荐）

1. 打开浏览器控制台（F12）
2. 运行以下代码：

```javascript
// 录制 3 秒测试音频
async function recordTestAudio() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  const chunks = [];

  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'test_zh.webm';
    a.click();
  };

  recorder.start();
  console.log('Recording... Speak: "测试语音识别"');
  setTimeout(() => recorder.stop(), 3000);
}

recordTestAudio();
```

3. 将下载的 `test_zh.webm` 文件保存到：
   ```
   external-systems/partner-http-gateway/tests/fixtures/test_zh.webm
   ```

### 方法 2：使用现有录音

使用手机录音应用录制中文语音，导出为 WebM/WAV 格式。

---

## 自动化测试

### 运行所有测试脚本

一键运行所有语音识别测试：

```bash
cd /Users/sunmuchao/Downloads/Her
./scripts/run-voice-tests.sh
```

**预期输出**：
```
======================================================================
Running All Voice Transcription Tests
======================================================================

======================================================================
Running: Backend Unit Tests (Gateway)
======================================================================
✓ test_dispatch_voice_rest_wrong_path PASSED
✓ test_dispatch_voice_rest_wrong_method PASSED
✓ test_dispatch_voice_transcribe_empty_audio PASSED
✓ test_dispatch_voice_transcribe_invalid_content_type PASSED
✓ test_dispatch_voice_transcribe_success PASSED
...

======================================================================
Running: Frontend Unit Tests (Hooks)
======================================================================
✓ useVoiceInput > support detection > should return isSupported=true PASSED
✓ useVoiceInput > recording lifecycle > should start recording PASSED
...

======================================================================
Test Summary
======================================================================

  ✓ Backend Unit Tests (Gateway)
  ✓ Frontend Unit Tests (Hooks)
  ○ Backend Integration Tests (skipped)

======================================================================
All tests passed! (2/3)
```

### CI/CD 集成

参考 [voice-tests.yml.example](../.github/workflows/voice-tests.yml.example) 配置 CI/CD：

```yaml
# .github/workflows/voice-tests.yml
jobs:
  backend-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: pip install pytest faster-whisper==1.2.1
      - name: Run tests
        run: pytest gateway_tests/test_voice_routes.py -m unit

  frontend-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        run: npm run test:voice
```

### 性能基准测试

运行性能基准测试（需要 pytest-benchmark）：

```bash
pip install pytest-benchmark
pytest gateway_tests/test_voice_routes.py --benchmark-only
```

---

## 测试覆盖率

### 后端覆盖率目标

| 模块 | 目标覆盖率 | 当前覆盖率 | 备注 |
|------|-----------|-----------|------|
| `voice_routes.py` | ≥ 80% | 待测量 | 核心语音识别逻辑 |
| `dispatch_voice_rest` | ≥ 90% | 待测量 | REST 路由分发 |
| `_transcribe_audio` | ≥ 70% | 待测量 | Whisper 调用（依赖真实音频） |

### 前端覆盖率目标

| 模块 | 目标覆盖率 | 当前覆盖率 | 备注 |
|------|-----------|-----------|------|
| `useVoiceInput` | ≥ 85% | 待测量 | Hook 核心逻辑 |
| `transcribeVoice` | ≥ 90% | 待测量 | API endpoint |

查看覆盖率报告：

```bash
# 后端
pytest --cov=gateway.voice_routes --cov-report=html
open htmlcov/index.html

# 前端
npm run test:coverage
open coverage/index.html
```

---

## 手动测试步骤

### 1. 启动后端 Gateway 服务

```bash
cd /Users/sunmuchao/Downloads/Her
docker compose up -d gateway-public
```

或者使用 gunicorn：

```bash
gunicorn -c external-systems/partner-http-gateway/gunicorn_config.py gateway.app:PartnerGateway
```

### 2. 启动前端服务

```bash
cd frontend/her-app
npm run dev
```

### 3. 测试语音识别

打开浏览器访问发现页：`http://localhost:3000/discover`

1. 点击麦克风按钮，**按住说话**
2. 说一段中文（如："帮我找一个年龄在25到30岁之间的女生"）
3. 松开按钮，等待识别完成
4. 查看识别结果是否自动发送到聊天框

### 4. 查看日志

#### 后端日志
查看 Gateway 日志，应该看到：
```
Loading Whisper model: size=medium, device=cpu, compute_type=int8
Whisper model loaded successfully
Transcribing audio: size=XXX bytes, type=audio/webm
Transcribed audio: language=zh, probability=0.XX, text_length=XX
```

#### 前端日志
浏览器控制台（F12）应该看到：
```
[useVoiceInput] 支持情况诊断:
  - window: true
  - navigator: true
  - mediaDevices: true
  - getUserMedia: true
  - isSupported: true
  - 方案: 后端 Whisper API
```

## 配置选项

### Whisper 模型配置

在 `.env` 文件中可以配置：

```bash
# Whisper 模型大小（small/medium/large）
WHISPER_MODEL_SIZE=medium

# 运行设备（cpu/cuda/auto）
WHISPER_DEVICE=cpu

# 计算类型（int8/float16/float32）
WHISPER_COMPUTE_TYPE=int8
```

推荐配置：
- **开发环境**：`medium + cpu + int8`（准确率高，速度适中）
- **生产环境**：`large + cuda + float16`（最准确，需要 GPU）

### 音频格式支持

浏览器 MediaRecorder 支持的格式：
- Chrome/Edge: `audio/webm`（推荐）
- Safari: `audio/mp4`
- Firefox: `audio/webm`

后端 Whisper 支持所有常见格式（webm/mp4/wav/mp3）。

## 性能优化建议

### 1. 模型预热（可选）

在 Gateway 启动时预热模型，避免首次请求延迟：

```python
# gateway/app.py
def __init__(self, ...):
    ...
    # 预热 Whisper 模型
    from .voice_routes import _get_whisper_model
    _get_whisper_model()
```

### 2. GPU 加速（推荐）

如果有 GPU，配置：

```bash
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

识别速度可提升 5-10 倍。

### 3. 模型大小选择

| 模型大小 | 内存占用 | 速度 | 准确率 | 推荐场景 |
|---------|---------|------|-------|---------|
| small   | ~1GB    | 快   | 中    | 快速识别 |
| medium  | ~2GB    | 中   | 高    | 平衡方案（推荐） |
| large   | ~3GB    | 慢   | 最高  | 精确识别 |

## 常见问题排查

### Q1: 后端报错 "No module named 'faster_whisper'"

**原因**：依赖未安装

**解决**：
```bash
pip install faster-whisper==1.2.1
```

### Q2: 前端报错 "无法访问麦克风"

**原因**：浏览器权限未授权

**解决**：
- 点击浏览器地址栏左侧的锁图标
- 授权麦克风权限
- 或在 Chrome 设置中手动授权

### Q3: 识别速度慢（超过 10 秒）

**原因**：使用 CPU + medium 模型

**解决**：
- 使用 GPU 加速（`WHISPER_DEVICE=cuda`）
- 或降低模型大小（`WHISPER_MODEL_SIZE=small`）

### Q4: 识别准确率低

**原因**：模型太小或音频质量差

**解决**：
- 使用 `medium` 或 `large` 模型
- 确保麦克风质量好，环境噪音小
- 提高录音时长（至少 2 秒）

## API 接口文档

### POST /v1/voice/transcribe

**请求**：
```http
POST /api/gateway/v1/voice/transcribe
Content-Type: audio/webm

<audio binary data>
```

**响应**：
```json
{
  "success": true,
  "text": "帮我找一个年龄在25到30岁之间的女生",
  "language": "zh",
  "language_probability": 0.98,
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "帮我找一个年龄在25到30岁之间的女生"
    }
  ]
}
```

## 后续优化方向

1. **流式识别**：实时识别，边说边显示文字
2. **多语言支持**：自动检测语言（已支持）
3. **语音命令**：识别特定命令词（如"发送"、"取消"）
4. **降噪处理**：使用 WebRTC 降噪提升识别质量

---

生成时间：2026-06-26
作者：Claude Code
