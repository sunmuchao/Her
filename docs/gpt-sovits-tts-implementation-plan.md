# GPT-SoVITS 语音合成系统 - 技术方案

## 一、消息结构设计

### 1.1 数据库表结构（现有）

```sql
-- chat_conversation_messages 表（已存在）
CREATE TABLE chat_conversation_messages (
    message_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    author_id VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL,  -- 'user' | 'agent' | 'system'
    body TEXT NOT NULL,           -- 文本内容
    metadata_json TEXT,           -- JSON 元数据（包含 media 信息）
    created_at TIMESTAMP NOT NULL,
    ...
);
```

### 1.2 消息 metadata_json 结构

```json
{
  "media_type": "audio",              // 新增：消息类型（'text' | 'image' | 'audio'）
  "media_url": "https://minio.xxx/audio/xxx.wav",  // 音频文件 URL
  "media_metadata": {
    "duration_ms": 3000,              // 音频时长（毫秒）
    "format": "wav",                  // 音频格式
    "size": 45000,                    // 文件大小（字节）
    "sample_rate": 16000,             // 采样率
    "channels": 1,                    // 声道数
    "tts_engine": "gpt-sovits",       // TTS 引擎标识
    "voice_id": "xiaoya-default",     // 音色 ID
    "generated_at": "2026-06-27T10:00:00Z"  // 生成时间
  }
}
```

### 1.3 消息示例

**纯文本消息（现有）**:
```json
{
  "message_id": 123,
  "author_id": "xiaoya",
  "source": "agent",
  "body": "你好，有什么可以帮助你的吗？",
  "metadata_json": null
}
```

**音频 + 文本消息（新增）**:
```json
{
  "message_id": 124,
  "author_id": "xiaoya",
  "source": "agent",
  "body": "你好，有什么可以帮助你的吗？",  // 文本内容（用于显示）
  "metadata_json": {
    "media_type": "audio",
    "media_url": "https://minio.example.com/audio/msg-124.wav",
    "media_metadata": {
      "duration_ms": 3000,
      "format": "wav",
      "size": 45000,
      "sample_rate": 16000,
      "channels": 1,
      "tts_engine": "gpt-sovits",
      "voice_id": "xiaoya-default"
    }
  }
}
```

## 二、GPT-SoVITS 部署方案

### 2.1 系统架构

```
┌────────────────────────────────────────────────────────────┐
│                    GPT-SoVITS 服务架构                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────┐      ┌──────────────┐                   │
│  │  Gateway    │ ───> │  TTS Service │                   │
│  │  (Python)   │      │  (FastAPI)   │                   │
│  └─────────────┘      └──────────────┘                   │
│                            │                              │
│                            ↓                              │
│                    ┌──────────────┐                       │
│                    │ GPT-SoVITS   │                       │
│                    │   Model      │                       │
│                    └──────────────┘                       │
│                            │                              │
│                            ↓                              │
│                    ┌──────────────┐                       │
│                    │    MinIO     │                       │
│                    │   Storage    │                       │
│                    └──────────────┘                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 2.2 GPT-SoVITS 模型部署

**方案 A：独立容器部署（推荐）**
```yaml
# docker-compose.yml
services:
  gpt-sovits:
    image: "gpt-sovits:latest"  # 或使用官方镜像
    container_name: gpt-sovits-service
    ports:
      - "9880:9880"  # TTS API 端口
    volumes:
      - ./models:/app/models  # 模型文件目录
      - ./voices:/app/voices  # 音色样本目录
    environment:
      - DEVICE=cpu  # 或 cuda（如果有 GPU）
      - MODEL_SIZE=small
    restart: unless-stopped
```

**方案 B：Python 服务集成**
```python
# external-systems/partner-http-gateway/gateway/tts_service.py
from fastapi import FastAPI
from pydantic import BaseModel
import tempfile
import os

# GPT-SoVITS Python SDK（假设）
from gpt_sovits import TTSModel

app = FastAPI()
tts_model = TTSModel(
    model_path="/path/to/models",
    device="cpu"  # 或 "cuda"
)

class SynthesizeRequest(BaseModel):
    text: str
    voice_id: str = "xiaoya-default"
    output_format: str = "wav"

@app.post("/synthesize")
async def synthesize_audio(req: SynthesizeRequest):
    # 生成语音
    audio_data = tts_model.synthesize(
        text=req.text,
        voice_id=req.voice_id,
        output_format=req.output_format
    )

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(suffix=f".{req.output_format}", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    # 上传到 MinIO
    from chat_system.media_storage import upload_audio
    result = upload_audio(audio_data, f"tts-{req.voice_id}.wav", "xiaoya")

    return {
        "audio_url": result["media_url"],
        "duration_ms": result["duration_ms"],
        "format": req.output_format,
        "size": len(audio_data)
    }
```

### 2.3 模型下载

**预训练模型**:
```bash
# 下载 GPT-SoVITS 预训练模型（约 1-2GB）
wget https://huggingface.co/RVC-Boss/GPT-SoVITS/resolve/main/models/gpt-sovits-small.pt
wget https://huggingface.co/RVC-Boss/GPT-SoVITS/resolve/main/models/sovits-small.pt

# 或使用镜像（中国访问更快）
wget https://hf-mirror.com/RVC-Boss/GPT-SoVITS/resolve/main/models/gpt-sovits-small.pt
```

**小雅专属音色训练**:
```bash
# 准备小雅音色样本（5-10秒高质量音频）
# 录制要求：清晰、无噪音、自然语调

# 训练专属音色（可选，或使用预训练音色）
python train_voice.py \
  --sample-audio ./voices/xiaoya-sample.wav \
  --output-voice-id xiaoya-default \
  --model-path ./models/gpt-sovits-small.pt
```

## 三、后端实现

### 3.1 TTS API 路由

```python
# external-systems/partner-http-gateway/gateway/tts_routes.py

from __future__ import annotations
import logging
import os
import tempfile
from typing import Any

LOGGER = logging.getLogger(__name__)

# GPT-SoVITS 服务地址（独立容器）
TTS_SERVICE_URL = os.environ.get("TTS_SERVICE_URL", "http://localhost:9880")

def dispatch_tts_rest(
    gateway: Any,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """TTS REST API 路由"""

    if not path.startswith("/v1/voice"):
        return None

    # POST /v1/voice/synthesize
    if path == "/v1/voice/synthesize" and method == "POST":
        try:
            LOGGER.info("[tts_routes] 收到语音合成请求")

            # 读取请求体
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            if content_length == 0:
                return 400, {
                    "error": {"code": "empty_request", "message": "Request body is empty"}
                }

            import json
            raw_body = environ["wsgi.input"].read(content_length)
            request_data = json.loads(raw_body)

            # 验证参数
            text = request_data.get("text", "").strip()
            if not text:
                return 400, {
                    "error": {"code": "missing_text", "message": "text is required"}
                }

            voice_id = request_data.get("voice_id", "xiaoya-default")
            output_format = request_data.get("output_format", "wav")

            LOGGER.info(f"[tts_routes] 合成参数: text_length={len(text)}, voice_id={voice_id}")

            # 调用 GPT-SoVITS 服务
            import requests
            tts_response = requests.post(
                f"{TTS_SERVICE_URL}/synthesize",
                json={
                    "text": text,
                    "voice_id": voice_id,
                    "output_format": output_format
                },
                timeout=30  # 30秒超时
            )

            if not tts_response.ok:
                LOGGER.error(f"[tts_routes] TTS 服务失败: {tts_response.status_code}")
                return 500, {
                    "error": {
                        "code": "tts_service_failed",
                        "message": f"TTS service returned {tts_response.status_code}"
                    }
                }

            tts_result = tts_response.json()
            LOGGER.info(f"[tts_routes] 合成成功: duration={tts_result.get('duration_ms')}ms")

            return 200, {
                "success": True,
                "audio_url": tts_result["audio_url"],
                "duration_ms": tts_result["duration_ms"],
                "format": tts_result["format"],
                "size": tts_result["size"],
                "voice_id": voice_id,
                "tts_engine": "gpt-sovits"
            }

        except Exception as e:
            LOGGER.exception(f"[tts_routes] 语音合成失败: {e}")
            return 500, {
                "error": {"code": "tts_failed", "message": str(e)}
            }

    return None


__all__ = ["dispatch_tts_rest"]
```

### 3.2 音频存储扩展

```python
# external-systems/partner-chat-system/chat_system/media_storage.py（扩展）

def upload_audio(
    audio_data: bytes,
    filename: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upload audio file to MinIO storage.

    Args:
        audio_data: Audio bytes (WAV/MP3 format)
        filename: Original filename
        user_id: User ID for storage path
        metadata: Additional metadata (thread_id, etc.)

    Returns:
        dict with media_id, media_url, content_type, size, duration_ms
    """
    # 复用现有的 MinIO 上传逻辑
    from .media_storage import upload_image  # 现有函数

    # 检测音频格式
    if audio_data[:4] == b"RIFF" and audio_data[8:12] == b"WAVE":
        content_type = "audio/wav"
        detected_format = "wav"
    elif audio_data[:3] == b"ID3" or audio_data[:2] == b"\xFF\xFB":
        content_type = "audio/mp3"
        detected_format = "mp3"
    else:
        raise ValueError("Unsupported audio format")

    # 使用 MinIO 上传
    result = upload_image(audio_data, filename, user_id, metadata)  # 复用现有函数

    # 计算音频时长（使用 pydub）
    try:
        from pydub import AudioSegment
        with tempfile.NamedTemporaryFile(suffix=f".{detected_format}", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        audio_segment = AudioSegment.from_file(tmp_path, format=detected_format)
        duration_ms = len(audio_segment)

        os.unlink(tmp_path)

        result["duration_ms"] = duration_ms
        result["content_type"] = content_type
        result["format"] = detected_format

    except ImportError:
        LOGGER.warning("pydub not available, cannot calculate duration")
        result["duration_ms"] = None
        result["content_type"] = content_type
        result["format"] = detected_format

    return result
```

### 3.3 Agent 回复集成

```python
# external-systems/partner-chat-system/chat_system/assistant_runtime.py（修改）

# 在 Agent 回复生成后，自动调用 TTS
def _synthesize_and_append_audio_message(
    conn,
    conversation_id: str,
    author_id: str,
    text_body: str,
    source: str = "agent",
    voice_id: str = "xiaoya-default",
    now: datetime | None = None,
) -> dict[str, Any]:
    """合成语音并追加到消息"""

    # 1. 调用 TTS API
    import requests
    tts_response = requests.post(
        "http://localhost:9880/synthesize",  # GPT-SoVITS 服务地址
        json={
            "text": text_body,
            "voice_id": voice_id,
            "output_format": "wav"
        },
        timeout=30
    )

    if not tts_response.ok:
        LOGGER.error(f"TTS failed: {tts_response.status_code}")
        # 降级：只发送文本消息
        return post_conversation_message(
            conn,
            conversation_id=conversation_id,
            author_id=author_id,
            body=text_body,
            source=source,
            now=now,
        )

    tts_result = tts_response.json()

    # 2. 创建消息（包含文本 + 音频）
    from .conversations import post_conversation_message

    message = post_conversation_message(
        conn,
        conversation_id=conversation_id,
        author_id=author_id,
        body=text_body,  # 文本内容
        source=source,
        metadata={
            "media_type": "audio",
            "media_url": tts_result["audio_url"],
            "media_metadata": {
                "duration_ms": tts_result["duration_ms"],
                "format": tts_result["format"],
                "size": tts_result["size"],
                "tts_engine": "gpt-sovits",
                "voice_id": voice_id,
            }
        },
        now=now,
    )

    return message


# 在 MatchmakerAgent 运行时集成
def run_matchmaker_agent(run_input: MatchmakerRunInput) -> MatchmakerDecision:
    """运行 Agent，生成回复"""

    # ... Agent 思考过程 ...

    decision = MatchmakerDecision(
        should_reply=True,
        target_channel_key="assistant_dm_a",
        reply_body="你好，我是小雅...",
        ...
    )

    return decision


# 在回复发送时集成 TTS
def _send_agent_reply(
    conn,
    run_input: MatchmakerRunInput,
    decision: MatchmakerDecision,
) -> None:
    """发送 Agent 回复"""

    if decision.should_reply and decision.reply_body:
        # 检查是否需要生成语音
        # 场景：开场白、私信、AI红娘提示
        should_synthesize_audio = _should_generate_audio(
            run_input,
            decision
        )

        if should_synthesize_audio:
            # 合成语音并发送
            _synthesize_and_append_audio_message(
                conn,
                conversation_id=_get_conversation_id(run_input, decision.target_channel_key),
                author_id=run_input.session.get("agent_id"),
                text_body=decision.reply_body,
                source="agent",
                voice_id="xiaoya-default",
            )
        else:
            # 只发送文本
            post_conversation_message(
                conn,
                conversation_id=_get_conversation_id(run_input, decision.target_channel_key),
                author_id=run_input.session.get("agent_id"),
                body=decision.reply_body,
                source="agent",
            )
```

## 四、前端实现

### 4.1 AudioMessage 组件

```tsx
// frontend/her-app/components/her/audio-message.tsx

'use client'

import { useState, useRef } from 'react'
import { Play, Pause, Volume2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AudioMessageProps {
  audioUrl: string
  durationMs: number
  format: string
  onPlayStart?: () => void
  onPlayEnd?: () => void
}

export function AudioMessage({ audioUrl, durationMs, format, onPlayStart, onPlayEnd }: AudioMessageProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [progress, setProgress] = useState(0)
  const audioRef = useRef<HTMLAudioElement>(null)

  const handlePlayPause = () => {
    if (!audioRef.current) return

    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
      onPlayStart?.()
    }
    setIsPlaying(!isPlaying)
  }

  const handleTimeUpdate = () => {
    if (!audioRef.current) return
    const current = audioRef.current.currentTime * 1000  // 转为毫秒
    setCurrentTime(current)
    setProgress((current / durationMs) * 100)
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setProgress(100)
    onPlayEnd?.()
  }

  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const remainingMs = ms % 1000
    return `${seconds}.${remainingMs.toFixed(0)}s`
  }

  return (
    <div className="flex items-center gap-3 bg-secondary/50 rounded-lg px-3 py-2 max-w-[280px]">
      {/* 播放按钮 */}
      <button
        onClick={handlePlayPause}
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center transition-all',
          isPlaying ? 'bg-primary animate-pulse' : 'bg-primary/10 hover:bg-primary/20'
        )}
        aria-label={isPlaying ? '暂停' : '播放'}
      >
        {isPlaying ? (
          <Pause className="w-5 h-5 text-primary-foreground" />
        ) : (
          <Play className="w-5 h-5 text-primary" />
        )}
      </button>

      {/* 进度条 */}
      <div className="flex-1 flex flex-col gap-1">
        <div className="relative h-1 bg-secondary rounded-full overflow-hidden">
          <div
            className="absolute left-0 top-0 h-full bg-primary transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{formatDuration(currentTime)}</span>
          <span>{formatDuration(durationMs)}</span>
        </div>
      </div>

      {/* 音量图标 */}
      <Volume2 className="w-4 h-4 text-muted-foreground" />

      {/* 隐藏的 audio 元素 */}
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleEnded}
        preload="metadata"
      />
    </div>
  )
}
```

### 4.2 XiaoyaRichText 扩展

```tsx
// frontend/her-app/components/her/ui/xiaoya-rich-text.tsx（修改）

import { AudioMessage } from '@/components/her/audio-message'

interface XiaoyaRichTextProps {
  content: string
  className?: string
  mediaType?: string
  mediaUrl?: string
  mediaMetadata?: {
    duration_ms: number
    format: string
    size: number
    tts_engine: string
    voice_id: string
  }
}

export function XiaoyaRichText({
  content,
  className,
  mediaType,
  mediaUrl,
  mediaMetadata
}: XiaoyaRichTextProps) {
  return (
    <div className={cn('space-y-2', className)}>
      {/* 音频消息 */}
      {mediaType === 'audio' && mediaUrl && mediaMetadata && (
        <AudioMessage
          audioUrl={mediaUrl}
          durationMs={mediaMetadata.duration_ms}
          format={mediaMetadata.format}
        />
      )}

      {/* 文本内容 */}
      <div className="text-sm text-foreground">
        {content}
      </div>
    </div>
  )
}
```

### 4.3 chat-page.tsx 消息渲染

```tsx
// frontend/her-app/components/her/chat-page.tsx（修改）

// 在消息渲染部分（line 1089-1090）
{msg.isFromMe ? msg.body : (
  <XiaoyaRichText
    content={msg.body}
    mediaType={msg.mediaType}
    mediaUrl={msg.mediaUrl}
    mediaMetadata={msg.mediaMetadata}
    className="space-y-3.5"
  />
)}
```

## 五、测试验证

### 5.1 测试场景

1. **开场白场景**：
   - 新用户注册后，小雅主动发送开场白
   - 消息包含文本 + 语音
   - 用户可以播放语音或阅读文字

2. **私信小雅场景**：
   - 用户在小雅私信面板发送问题
   - 小雅回复包含文本 + 语音
   - 语音时长 < 10秒（快速回复）

3. **AI红娘提示场景**：
   - 在主群聊中，小雅主动发送提示
   - 消息包含文本 + 语音
   - 语音风格友好、自然

### 5.2 性能要求

- **生成速度**：< 5秒（文本 → 音频）
- **音频质量**：16kHz、16-bit PCM、单声道
- **文件大小**：< 50KB（10秒音频）
- **并发支持**：支持 10 个并发请求

## 六、部署步骤

1. **模型部署**：
   ```bash
   docker-compose up -d gpt-sovits
   ```

2. **网关集成**：
   ```bash
   # 在 gateway 主文件中添加路由
   from .tts_routes import dispatch_tts_rest
   ```

3. **前端部署**：
   ```bash
   cd frontend/her-app
   npm run build
   ```

4. **测试验证**：
   ```bash
   curl -X POST http://localhost:8081/v1/voice/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "你好，我是小雅", "voice_id": "xiaoya-default"}'
   ```

## 七、成本估算

- **模型文件**：1-2GB（GPT-SoVITS small）
- **存储成本**：每条语音 50KB，1000条 ≈ 50MB
- **计算成本**：CPU 模式，每秒合成约 0.5秒音频
- **内存需求**：500MB（模型加载）

---

**下一步实施**：
1. 部署 GPT-SoVITS 模型（独立容器）
2. 实现 TTS API 路由
3. 扩展 media_storage.py（音频存储）
4. 修改 Agent 回复流程（集成 TTS）
5. 前端 AudioMessage 组件实现
6. 三个场景测试验证