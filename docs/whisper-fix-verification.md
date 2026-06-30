# Whisper 语音识别修复验证流程

## 修复状态

| 项目 | 状态 | 说明 |
|------|------|------|
| ffmpeg 安装 | 🔄 进行中 | Homebrew 正在下载解码器（Opus/AAC） |
| pydub 安装 | ✅ 完成 | 音频格式转换库已安装 |
| voice_routes.py | ✅ 完成 | 已添加音频格式转换和诊断日志 |
| requirements.txt | ✅ 完成 | 已添加 pydub 依赖 |
| 前端优化 | ✅ 完成 | 已优化错误提示和诊断日志 |
| 修复文档 | ✅ 完成 | [whisper-audio-format-compatibility.md](../docs/whisper-audio-format-compatibility.md) |

---

## 验证步骤

### Step 1: 等待 ffmpeg 安装完成

```bash
# 查看安装进度
tail -f /private/tmp/claude-501/-Users-sunmuchao-Downloads-Her/0574cbb0-8276-4639-a8ef-8bf61a08c72c/tasks/bnahe1smz.output

# 或等待几分钟后手动检查
ffmpeg -version
ffmpeg -codecs | grep -E "(opus|aac)"
```

**预期输出**：
```
ffmpeg version 8.1.2
...
DEA.L. opus                  Opus (Opus Interactive Audio Codec)
DEA.L. aac                   AAC (Advanced Audio Coding)
```

---

### Step 2: 验证环境完整性

```bash
# 激活虚拟环境
source .venv/bin/activate

# 验证所有依赖
python -c "
import sys
print('Python:', sys.version)

try:
    import pydub
    print('✓ pydub: installed')
except ImportError:
    print('✗ pydub: missing')

try:
    from faster_whisper import WhisperModel
    print('✓ faster-whisper: installed')
except ImportError:
    print('✗ faster-whisper: missing')

try:
    import numpy
    print('✓ numpy:', numpy.__version__)
    if numpy.__version__.startswith('2'):
        print('  ⚠ NumPy 2.x may cause issues, recommend 1.x')
except ImportError:
    print('✗ numpy: missing')
"

# 验证 ffmpeg
ffmpeg -version | head -5
```

---

### Step 3: 启动 Gateway

```bash
# 启动 Gateway（在新终端）
source .venv/bin/activate
docker compose up -d gateway-public

# 或使用现有的启动脚本
# bash scripts/start-gateway.sh
```

**预期日志**：
```
INFO: Loading Whisper model: size=small, device=cpu
INFO: Using Hugging Face endpoint: https://hf-mirror.com
INFO: Whisper model loaded successfully
```

---

### Step 4: 快速测试 WAV 格式

**WAV 格式不需要格式转换，可以快速验证基础功能**

```bash
# 运行快速测试
python external-systems/partner-http-gateway/tests/test_wav_quick.py
```

**预期输出**：
```
✓ WAV format works! (No conversion needed)
```

---

### Step 5: 完整测试多格式兼容性

**等待 ffmpeg 安装完成后运行**

```bash
# 运行多格式测试（webm, mp4, wav）
python external-systems/partner-http-gateway/tests/test_voice_formats.py
```

**预期输出**：
```
Test Summary:
  Passed: 8/8
  Failed: 0/8

Format Conversion:
  ✓ SUCCESS - webm → WAV
  ✓ SUCCESS - mp4 → WAV

✓ All tests passed!
```

---

### Step 6: 浏览器端到端测试

#### 6.1 Chrome/Firefox 测试（WebM 格式）

1. 打开浏览器应用（http://localhost:3000）
2. 打开 Console（F12 → Console）
3. 录制语音并发送

**预期 Console 日志**：
```
[useVoiceInput] Audio recorded:
  - Blob size: 2048 bytes
  - Blob type: audio/webm
  - Duration: 1000 ms
  - Chunks: 4
```

**预期后端日志**：
```
INFO: Transcribing audio: format=webm, size=2048 bytes
INFO: Converting webm to WAV for Whisper compatibility
INFO: Audio loaded: duration=1000ms, channels=1, sample_rate=48000Hz
INFO: Resampled to 16kHz for Whisper compatibility
INFO: Conversion successful: output size=32000 bytes
INFO: Transcription successful: language=zh, probability=0.98
```

---

#### 6.2 Safari 测试（MP4 格式）

1. 在 Safari 中打开应用
2. 录制语音并发送

**预期 Console 日志**：
```
[useVoiceInput] Audio recorded:
  - Blob size: 4096 bytes
  - Blob type: audio/mp4
```

**预期后端日志**：
```
INFO: Converting mp4 to WAV for Whisper compatibility
INFO: Conversion successful
```

---

### Step 7: 验证修复效果

**检查以下问题是否解决**：

- ✅ `[Errno 1094995529] Invalid data found when processing input` 错误消失
- ✅ WebM 格式可以正常识别
- ✅ MP4 格式可以正常识别
- ✅ 后端日志显示格式转换过程
- ✅ 前端收到正确的识别结果

---

## 测试失败排查

### 问题 1: ffmpeg 仍然未找到

**检查 PATH**：
```bash
which ffmpeg

# 如果未找到，添加到 PATH
export PATH="/opt/homebrew/bin:$PATH"  # Apple Silicon
export PATH="/usr/local/bin:$PATH"     # Intel Mac
```

**重新运行安装**：
```bash
bash scripts/fix-whisper-audio-format.sh
```

---

### 问题 2: pydub 转换失败

**检查 ffmpeg 编解码器**：
```bash
ffmpeg -codecs | grep -E "(opus|aac)"

# 应显示:
# DEA.L. opus
# DEA.L. aac
```

**手动测试转换**：
```bash
python -c "
from pydub import AudioSegment
import tempfile

# 创建测试 webm 文件
temp_webm = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)

# 使用 ffmpeg 创建测试文件
import subprocess
subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '1', '-c:a', 'libopus', temp_webm.name, '-y'], capture_output=True)

# 使用 pydub 转换
audio = AudioSegment.from_file(temp_webm.name, format='webm')
audio.export(temp_wav.name, format='wav')

print(f'✓ Conversion successful: {temp_wav.name}')
print(f'  Duration: {len(audio)}ms')
print(f'  Channels: {audio.channels}')
print(f'  Sample rate: {audio.frame_rate}Hz')
"
```

---

### 问题 3: Gateway 未启动

**检查 Gateway 日志**：
```bash
# 查看 Gateway 启动错误
docker compose logs -f gateway-public

# 常见错误:
# - NumPy 2.x 冲突: 运行 scripts/fix-whisper-dependencies.sh
# - OpenMP 冲突: 已在代码中设置 KMP_DUPLICATE_LIB_OK=TRUE
# - 模型下载失败: 检查 HF_ENDPOINT 环境变量
```

---

### 问题 4: 模型下载超时

**使用中国镜像**：
```bash
export HF_ENDPOINT=https://hf-mirror.com
python scripts/preload_whisper_model.py
```

**或使用预下载模型**：
```bash
# 下载模型到缓存
python -c "
from faster_whisper import WhisperModel
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
model = WhisperModel('small', device='cpu', compute_type='int8')
print('Model downloaded and cached')
"
```

---

## 成功标志

### 所有测试通过

```
======================================================================
Test Summary:
======================================================================

Overall Results:
  Passed: 8/8
  Failed: 0/8

✓ All tests passed!
  → Audio format conversion is working correctly
  → Whisper transcription is working for all formats
  → Voice input should work in all browsers
```

### 浏览器语音识别正常工作

- ✅ Chrome/Firefox: WebM 格式识别成功
- ✅ Safari: MP4 格式识别成功
- ✅ 前端收到识别结果文本
- ✅ 后端日志完整记录转换过程

---

## 后续维护

### 定期检查

```bash
# 每月检查 ffmpeg 版本
ffmpeg -version

# 每月检查 pydub 是否正常
python -c "from pydub import AudioSegment; print('OK')"

# 每月运行测试验证
python external-systems/partner-http-gateway/tests/test_voice_formats.py
```

### 新浏览器测试

当支持新浏览器或新设备时：
1. 检查 MediaRecorder 支持的格式
2. 添加到测试脚本
3. 验证格式转换和识别

---

生成时间：2026-06-26
作者：Claude Code
