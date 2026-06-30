# Whisper 音频格式兼容性问题修复

## 问题现象

### 错误信息

```
[Errno 1094995529] Invalid data found when processing input: '/var/folders/.../tmp9du6ekiw.webm'
```

**错误码含义**：
- `1094995529` (十六进制 `0x41414149`) = `AVERROR_INVALIDDATA`
- ffmpeg/libav 无法解析输入数据

---

## 根因分析（五问法）

```
问题现象：Whisper 无法处理浏览器录制的 webm 文件
├─ 为什么 1: 错误码 AVERROR_INVALIDDATA 表明 ffmpeg 无法解析音频容器
│   → webm 文件内部的音频编码不被 ffmpeg 支持
├─ 为什么 2: MediaRecorder API 在不同浏览器使用不同编码
│   → Chrome/Firefox 使用 Opus 编码，Safari 使用 AAC 编码
│   → webm 容器 + Opus 编码的组合在某些 ffmpeg 版本中缺少解码器
├─ 为什么 3: ffmpeg 未安装或解码器缺失
│   → macOS 上 ffmpeg 可能未安装，或缺少 Opus/AAC 解码器
├─ 为什么 4: 后端缺少音频格式验证和转换机制
│   → voice_routes.py 直接保存为 .webm，未验证编码格式
│   → 未转换为 Whisper 原生支持的 WAV 格式
└─ 为什么 5: 【根本原因】音频格式兼容性检查缺失
    → 前端未检查录制格式是否被后端支持
    → 后端未验证音频编码是否可解析
    → 缺少自动转换到统一格式的机制
```

---

## 修复方案

### 三层防御机制

| 层级 | 问题 | 修复 |
|------|------|------|
| **诊断层** | 缺少日志导致无法定位问题 | 添加详细日志（格式、编码、大小、转换过程） |
| **兼容层** | 多浏览器多编码导致不兼容 | 自动转换为 WAV 格式（Whisper 原生支持） |
| **验证层** | 缺少端到端测试 | 多格式、多浏览器自动化测试 |

---

## 实施修复

### Phase 1：环境修复（必需）

#### 1.1 安装 ffmpeg（音频解码器）

```bash
# macOS (使用 Homebrew)
brew install ffmpeg

# 验证安装
ffmpeg -version
ffmpeg -codecs | grep -E "(opus|aac)"
```

**ffmpeg 包含的解码器**：
- ✅ Opus (Chrome/Firefox webm 编码)
- ✅ AAC (Safari mp4 编码)
- ✅ Vorbis (Firefox webm 编码)

---

#### 1.2 安装 pydub（音频格式转换）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装 pydub
pip install pydub

# 验证安装
python -c "import pydub; print(pydub.__version__)"
```

**pydub 功能**：
- 使用 ffmpeg 加载任意音频格式
- 自动转换为 WAV（Whisper 原生支持）
- 提取音频元数据（时长、采样率、声道）

---

#### 1.3 一键修复脚本

```bash
# 运行修复脚本（自动安装 ffmpeg 和 pydub）
bash scripts/fix-whisper-audio-format.sh
```

**脚本功能**：
- ✅ 检查并安装 ffmpeg（包含所有解码器）
- ✅ 检查并安装 pydub
- ✅ 验证音频格式转换能力
- ✅ 测试 faster-whisper WAV 支持

---

### Phase 2：后端代码修复

#### 2.1 voice_routes.py 改动

**新增功能**：
1. **音频格式检测**：从 Content-Type 提取格式（webm/mp4/wav）
2. **格式转换函数**：`_convert_audio_to_wav()` 使用 pydub 转换
3. **诊断日志**：记录格式、大小、转换过程、音频元数据
4. **错误处理**：更详细的错误信息（包含安装指引）

**关键代码**：

```python
# 新增：音频格式转换函数
def _convert_audio_to_wav(audio_data: bytes, input_format: str = "webm"):
    # 使用 pydub 加载音频（ffmpeg 自动处理编码）
    audio_segment = AudioSegment.from_file(tmp_path, format=input_format)

    # 转换为 Whisper 推荐格式（mono, 16kHz, 16-bit）
    audio_segment = audio_segment.set_channels(1)      # 单声道
    audio_segment = audio_segment.set_frame_rate(16000)  # 16kHz

    # 导出为 WAV
    audio_segment.export(tmp_out_path, format="wav")

    return wav_audio, metadata

# 修改：转录函数添加格式转换
def _transcribe_audio(audio_data: bytes, language: str = "zh", content_type: str = ""):
    # 检测音频格式
    audio_format = content_type.split("/")[-1]  # "webm", "mp4", "wav"

    # 非 WAV 格式自动转换
    if audio_format != "wav":
        audio_data, metadata = _convert_audio_to_wav(audio_data, audio_format)

    # Whisper 转录（使用转换后的 WAV）
    segments, info = model.transcribe(tmp_path, language=language)
```

**日志输出示例**：

```
INFO: Transcribing audio: format=webm, size=2048 bytes, duration=1000ms
INFO: Converting webm to WAV for Whisper compatibility
INFO: Audio loaded: duration=1000ms, channels=1, sample_rate=48000Hz
INFO: Resampled to 16kHz for Whisper compatibility
INFO: Conversion successful: output size=32000 bytes
INFO: Transcription successful: language=zh, probability=0.98, text_length=12
```

---

### Phase 3：前端优化

#### 3.1 格式选择策略

**当前策略**：
```typescript
// use-voice-input.ts
const mimeType = MediaRecorder.isTypeSupported('audio/webm')
  ? 'audio/webm'
  : MediaRecorder.isTypeSupported('audio/mp4')
    ? 'audio/mp4'
    : ''
```

**问题**：
- Safari 优先选择 mp4（AAC 编码）
- Chrome/Firefox 优先选择 webm（Opus 编码）
- 未考虑 Whisper 兼容性

**优化建议**（可选）：
```typescript
// 优先选择广泛支持的格式
const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
  ? 'audio/webm;codecs=opus'
  : MediaRecorder.isTypeSupported('audio/mp4')
    ? 'audio/mp4'
    : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : ''
```

---

#### 3.2 错误提示优化

**当前提示**：
```typescript
throw new Error('语音识别失败，请重试')
```

**优化提示**：
```typescript
if (error.message.includes('ffmpeg')) {
  onError?.('音频格式不支持，请联系管理员安装 ffmpeg')
} else if (error.message.includes('timeout')) {
  onError?.('语音识别超时，首次使用需要下载模型，请稍后再试')
} else {
  onError?.('语音识别失败，请重试')
}
```

---

### Phase 4：端到端测试

#### 4.1 测试脚本

```bash
# 运行多格式兼容性测试
python external-systems/partner-http-gateway/tests/test_voice_formats.py
```

**测试覆盖**：
- ✅ WAV 格式（Whisper 原生支持）
- ✅ WebM 格式（Chrome/Firefox，Opus 编码）
- ✅ MP4 格式（Safari，AAC 编码）
- ✅ 格式转换验证（webm → wav, mp4 → wav）
- ✅ 直接后端 API 测试
- ✅ Next.js 代理测试

---

#### 4.2 测试报告示例

```
======================================================================
Voice Transcription Format Compatibility Test
======================================================================

Configuration:
  Backend URL: http://127.0.0.1:8080
  Next.js URL: http://localhost:3000
  pydub available: True

Creating test audio files...
  ✓ WAV test file: /tmp/test.wav (32000 bytes)
  ✓ WebM test file: /tmp/test.webm (2048 bytes)
  ✓ MP4 test file: /tmp/test.mp4 (4096 bytes)

1. Testing health check...
   ✓ Gateway is healthy

2. Testing audio format conversion...
   Testing webm → WAV conversion...
   ✓ Audio loaded successfully
     - Duration: 1000ms
     - Channels: 1
     - Sample rate: 48000Hz
   ✓ Conversion successful
     - Output: /tmp/test.converted.wav
     - Size: 32000 bytes

3. Testing transcription via backend...
   wav: ✓ Transcription successful
     - Text: ""
     - Language: zh (probability: 0.98)
     - Audio info:
       - Duration: 1000ms
       - Channels: 1
       - Sample rate: 16000Hz

   webm: ✓ Transcription successful
     - Text: ""
     - Language: zh (probability: 0.98)
     - Audio info:
       - Duration: 1000ms
       - Channels: 1
       - Sample rate: 16000Hz

   mp4: ✓ Transcription successful
     - Text: ""
     - Language: zh (probability: 0.98)

======================================================================
Test Summary:
======================================================================

Overall Results:
  Passed: 8/8
  Failed: 0/8

Detailed Results:
  ✓ PASS - health
  ✓ PASS - transcribe_wav
  ✓ PASS - transcribe_webm
  ✓ PASS - transcribe_mp4
  ✓ PASS - transcribe_webm.converted
  ✓ PASS - transcribe_mp4.converted
  ✓ PASS - proxy_wav
  ✓ PASS - proxy_webm

Format Conversion:
  ✓ SUCCESS - webm → WAV
  ✓ SUCCESS - mp4 → WAV

✓ All tests passed!
  → Audio format conversion is working correctly
  → Whisper transcription is working for all formats
  → Voice input should work in all browsers
```

---

## 验证修复

### 1. 环境验证

```bash
# 检查 ffmpeg
ffmpeg -version
ffmpeg -codecs | grep -E "(opus|aac)"

# 检查 pydub
python -c "import pydub; print('pydub:', pydub.__version__)"

# 检查 faster-whisper
python -c "from faster_whisper import WhisperModel; print('faster-whisper: OK')"
```

---

### 2. 后端验证

```bash
# 启动 Gateway
docker compose up -d gateway-public

# 查看日志（应该看到格式转换日志）
# INFO: Converting webm to WAV for Whisper compatibility
# INFO: Conversion successful: output size=32000 bytes
```

---

### 3. 端到端验证

```bash
# 运行测试脚本
python external-systems/partner-http-gateway/tests/test_voice_formats.py

# 或测试单个格式
curl -X POST http://127.0.0.1:8080/v1/voice/transcribe \
  --data-binary @test.webm \
  -H "Content-Type: audio/webm"
```

---

### 4. 浏览器验证

1. **Chrome/Firefox**：
   - 打开浏览器 Console
   - 录制语音并发送
   - 查看请求日志（应该看到 `audio/webm`）

2. **Safari**：
   - 打开浏览器 Console
   - 录制语音并发送
   - 查看请求日志（应该看到 `audio/mp4`）

3. **后端日志**：
   - 应该看到格式转换日志
   - 应该看到转录成功日志

---

## 常见问题排查

### Q1: ffmpeg 安装失败

**检查 Homebrew**：
```bash
brew doctor
brew update
```

**重新安装 ffmpeg**：
```bash
brew uninstall ffmpeg
brew install ffmpeg
```

---

### Q2: pydub 转换失败

**检查 ffmpeg 可用性**：
```bash
# pydub 需要 ffmpeg 在 PATH 中
which ffmpeg

# 如果未找到，添加到 PATH
export PATH="/opt/homebrew/bin:$PATH"  # macOS Apple Silicon
export PATH="/usr/local/bin:$PATH"     # macOS Intel
```

---

### Q3: 仍然报 Invalid data 错误

**检查音频编码**：
```bash
# 使用 ffprobe 检查音频文件
ffprobe -v error -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 test.webm

# 应输出: opus (Chrome/Firefox) 或 aac (Safari)
```

**检查 ffmpeg 解码器**：
```bash
ffmpeg -codecs | grep -E "(opus|aac)"

# 应输出:
# DEA.L. opus                  Opus (Opus Interactive Audio Codec)
# DEA.L. aac                   AAC (Advanced Audio Coding)
```

---

### Q4: 转换成功但识别为空

**检查音频内容**：
- 测试音频是静音，Whisper 会返回空字符串
- 使用真实录音测试（浏览器录制）

**检查语言设置**：
```python
# 默认中文，如果音频是其他语言需要调整
model.transcribe(tmp_path, language="en")  # 英文
model.transcribe(tmp_path, language="auto")  # 自动检测
```

---

## 长期优化建议

### 1. 前端格式协商

**理想方案**：
- 前端发送支持格式列表
- 后端返回推荐格式
- 前端按推荐格式录制

```typescript
// 前端请求
const supportedFormats = ['audio/webm', 'audio/mp4', 'audio/wav']
const response = await fetch('/api/gateway/v1/voice/negotiate', {
  method: 'POST',
  body: JSON.stringify({ supportedFormats })
})

const { recommendedFormat } = await response.json()
// 使用推荐格式录制
```

---

### 2. 音频预处理

**可选优化**：
- 去除静音片段（节省处理时间）
- 音量标准化（提高识别准确率）
- 噪音抑制（提高质量）

```python
# pydub 预处理示例
from pydub.effects import normalize

audio = AudioSegment.from_file(audio_path)
audio = normalize(audio)  # 音量标准化
audio = audio.strip_silence()  # 去除静音
```

---

### 3. 缓存机制

**避免重复转换**：
```python
# 缓存转换后的音频（相同 webm 文件）
import hashlib

audio_hash = hashlib.md5(audio_data).hexdigest()
cache_key = f"audio_{audio_hash}"

if cache.get(cache_key):
    wav_audio = cache.get(cache_key)
else:
    wav_audio = convert_audio(audio_data)
    cache.set(cache_key, wav_audio, ttl=3600)
```

---

## 依赖版本参考

| 依赖 | 推荐版本 | 状态 | 说明 |
|------|---------|------|------|
| ffmpeg | 最新 | ✅ 必需 | 音频解码器（Opus/AAC） |
| pydub | 最新 | ✅ 必需 | 音频格式转换 |
| faster-whisper | 1.2.1 | ✅ 稳定 | 语音识别引擎 |
| numpy | < 2, >= 1.24 | ✅ 兼容 | faster-whisper 依赖 |

---

生成时间：2026-06-26
作者：Claude Code
