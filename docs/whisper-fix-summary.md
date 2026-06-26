# Whisper 语音识别修复总结

## 问题诊断（五问法）

```
问题现象：[Errno 1094995529] Invalid data found when processing input: 'tmp9du6ekiw.webm'
├─ 为什么 1: 错误码 AVERROR_INVALIDDATA 表明 ffmpeg 无法解析音频容器
├─ 为什么 2: MediaRecorder API 在不同浏览器使用不同编码（Opus/AAC）
├─ 为什么 3: ffmpeg 未安装或缺少 Opus/AAC 解码器
├─ 为什么 4: 后端缺少音频格式验证和转换机制
└─ 为什么 5: 【根本原因】音频格式兼容性检查缺失

根本对策：建立三层防御机制（诊断层 + 兼容层 + 验证层）
```

---

## 修复方案

### 架构改进：三层防御机制

```
┌─────────────────────────────────────────────────────────────────┐
│                     浏览器层（前端）                              │
│                                                                 │
│  ✓ 录制音频：MediaRecorder API                                  │
│  ✓ 格式选择：webm（Chrome/Firefox）或 mp4（Safari）              │
│  ✓ 诊断日志：Blob size/type/duration                            │
│  ✓ 错误提示：根据错误类型提供友好提示                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓ 发送音频 Blob
┌─────────────────────────────────────────────────────────────────┐
│                     Gateway 层（后端）                           │
│                                                                 │
│  ✓ 格式检测：从 Content-Type 提取音频格式                       │
│  ✓ 格式转换：pydub + ffmpeg 转换为 WAV                          │
│  ✓ 音频优化：mono + 16kHz（Whisper 原生支持）                    │
│  ✓ 诊断日志：记录转换过程和音频元数据                            │
│  ✓ 错误处理：详细错误信息 + 安装指引                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓ 发送 WAV 文件
┌─────────────────────────────────────────────────────────────────┐
│                     Whisper 层（AI）                             │
│                                                                 │
│  ✓ 音频转录：faster-whisper                                     │
│  ✓ 语言检测：自动识别（zh/en/...）                               │
│  ✓ 结果返回：text + segments + audio_info                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 代码改动清单

### 1. 后端改动

#### [voice_routes.py](../external-systems/partner-http-gateway/gateway/voice_routes.py)

**新增功能**：
- ✅ `_convert_audio_to_wav()` 函数：使用 pydub 转换音频格式
- ✅ 音频格式检测：从 Content-Type 提取格式（webm/mp4/wav）
- ✅ 音频优化：转换为 mono + 16kHz（Whisper 推荐格式）
- ✅ 诊断日志：记录转换过程、音频元数据、错误详情
- ✅ 错误处理：包含安装指引（ffmpeg/pydub）

**关键改动**：
```python
# 新增：音频格式转换函数
def _convert_audio_to_wav(audio_data: bytes, input_format: str = "webm"):
    # 使用 pydub 加载音频（ffmpeg 自动处理编码）
    audio_segment = AudioSegment.from_file(tmp_path, format=input_format)

    # 转换为 Whisper 推荐格式
    audio_segment = audio_segment.set_channels(1)      # 单声道
    audio_segment = audio_segment.set_frame_rate(16000)  # 16kHz

    # 导出为 WAV
    audio_segment.export(tmp_out_path, format="wav")

    return wav_audio, metadata

# 修改：转录函数添加格式转换
def _transcribe_audio(audio_data: bytes, language: str = "zh", content_type: str = ""):
    # 检测音频格式
    audio_format = content_type.split("/")[-1]

    # 非 WAV 格式自动转换
    if audio_format != "wav":
        audio_data, metadata = _convert_audio_to_wav(audio_data, audio_format)

    # Whisper 转录（使用转换后的 WAV）
    segments, info = model.transcribe(tmp_path, language=language)
```

---

### 2. 前端改动

#### [use-voice-input.ts](../frontend/her-app/hooks/use-voice-input.ts)

**优化功能**：
- ✅ 诊断日志：记录 Blob size/type/duration/chunks
- ✅ 错误提示：根据错误类型提供友好提示
- ✅ 错误分类：timeout/ffmpeg/Invalid data/Network

**关键改动**：
```typescript
// 新增：诊断日志
recorder.onstop = () => {
  const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType })

  console.log('[useVoiceInput] Audio recorded:')
  console.log('  - Blob size:', audioBlob.size, 'bytes')
  console.log('  - Blob type:', audioBlob.type)
  console.log('  - Duration:', Date.now() - startTimeRef.current, 'ms')

  void processAudioViaWhisper(audioBlob)
}

// 优化：错误提示
if (msg.includes('ffmpeg') || msg.includes('audio format')) {
  errorMessage = '音频格式不支持，请联系管理员安装 ffmpeg'
} else if (msg.includes('Invalid data')) {
  errorMessage = '音频数据无效，请检查麦克风是否正常工作'
} else if (msg.includes('timeout')) {
  errorMessage = '语音识别超时，首次使用需要下载模型，请稍后再试'
}
```

---

### 3. 依赖改动

#### [requirements.txt](../requirements.txt)

**新增依赖**：
```txt
pydub                       # Audio format conversion (requires ffmpeg)
```

**完整音频依赖**：
```txt
av==15.1.0                  # PyAV - FFmpeg bindings
faster-whisper==1.2.1       # Faster Whisper transcription
numpy<2                     # NumPy version constraint
pydub                       # Audio format conversion
```

---

### 4. 测试改动

#### 新增测试文件

- ✅ [test_wav_quick.py](../external-systems/partner-http-gateway/tests/test_wav_quick.py)：快速验证 WAV 格式
- ✅ [test_voice_formats.py](../external-systems/partner-http-gateway/tests/test_voice_formats.py)：多格式兼容性测试

**测试覆盖**：
- ✅ WAV 格式（Whisper 原生支持）
- ✅ WebM 格式（Chrome/Firefox，Opus 编码）
- ✅ MP4 格式（Safari，AAC 编码）
- ✅ 格式转换验证（webm → wav, mp4 → wav）
- ✅ 直接后端 API 测试
- ✅ Next.js 代理测试

---

### 5. 文档改动

#### 新增文档

- ✅ [whisper-audio-format-compatibility.md](../docs/whisper-audio-format-compatibility.md)：完整修复方案
- ✅ [whisper-fix-verification.md](../docs/whisper-fix-verification.md)：验证流程
- ✅ [whisper-fix-summary.md](../docs/whisper-fix-summary.md)：本总结文档

---

## 环境修复

### 安装脚本

#### [fix-whisper-audio-format.sh](../scripts/fix-whisper-audio-format.sh)

**功能**：
- ✅ 检查并安装 ffmpeg（包含 Opus/AAC 解码器）
- ✅ 检查并安装 pydub
- ✅ 验证音频格式转换能力
- ✅ 测试 faster-whisper WAV 支持

**执行**：
```bash
bash scripts/fix-whisper-audio-format.sh
```

---

## 测试验证

### 验证流程

| 步骤 | 测试 | 预期结果 |
|------|------|---------|
| Step 1 | 检查 ffmpeg | `ffmpeg -version` 显示版本 |
| Step 2 | 检查解码器 | `ffmpeg -codecs | grep -E "(opus|aac)"` |
| Step 3 | 验证环境 | pydub/faster-whisper/numpy 正常 |
| Step 4 | 启动 Gateway | 模型加载成功 |
| Step 5 | 快速测试 WAV | `test_wav_quick.py` 通过 |
| Step 6 | 多格式测试 | `test_voice_formats.py` 8/8 通过 |
| Step 7 | 浏览器测试 | Chrome/Safari 录制识别成功 |

---

### 成功标志

#### 测试输出

```
======================================================================
Test Summary:
======================================================================

Overall Results:
  Passed: 8/8
  Failed: 0/8

Format Conversion:
  ✓ SUCCESS - webm → WAV
  ✓ SUCCESS - mp4 → WAV

✓ All tests passed!
```

#### 浏览器日志

**前端 Console**：
```
[useVoiceInput] Audio recorded:
  - Blob size: 2048 bytes
  - Blob type: audio/webm
  - Duration: 1000 ms
```

**后端日志**：
```
INFO: Converting webm to WAV for Whisper compatibility
INFO: Audio loaded: duration=1000ms, channels=1, sample_rate=48000Hz
INFO: Resampled to 16kHz for Whisper compatibility
INFO: Conversion successful: output size=32000 bytes
INFO: Transcription successful: language=zh, probability=0.98
```

---

## 根因对比

### 修复前

| 问题 | 状态 |
|------|------|
| ffmpeg 缺失 | ❌ 无法解码 webm/mp4 |
| 音频格式转换缺失 | ❌ 直接处理 webm 导致 Invalid data |
| 诊断日志缺失 | ❌ 无法定位问题 |
| 错误提示模糊 | ❌ "语音识别失败，请重试" |

---

### 修复后

| 问题 | 状态 |
|------|------|
| ffmpeg 已安装 | ✅ 支持 Opus/AAC 解码 |
| 音频格式转换自动 | ✅ webm/mp4 → WAV |
| 诊断日志完整 | ✅ 记录转换过程和音频元数据 |
| 错误提示友好 | ✅ 根据错误类型提供指引 |

---

## 长期维护

### 定期检查

```bash
# 每月检查 ffmpeg 版本
ffmpeg -version

# 每月运行测试验证
python external-systems/partner-http-gateway/tests/test_voice_formats.py
```

### 新浏览器支持

当支持新浏览器或设备时：
1. 检查 MediaRecorder 支持的格式
2. 添加到测试脚本
3. 验证格式转换和识别

---

## 相关文档

- [whisper-audio-format-compatibility.md](../docs/whisper-audio-format-compatibility.md)：完整修复方案
- [whisper-fix-verification.md](../docs/whisper-fix-verification.md)：验证流程
- [whisper-dependency-fix.md](../docs/whisper-dependency-fix.md)：NumPy/OpenMP 修复

---

生成时间：2026-06-26
作者：Claude Code