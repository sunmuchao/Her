# Edge-TTS 实施进度总结

## ✅ 已完成部分

### 1. Edge-TTS 安装和测试
- ✅ 安装 edge-tts 包（使用清华镜像）
- ✅ 测试语音合成成功（微软晓晓女声，zh-CN-XiaoxiaoNeural）
- ✅ 生成测试音频文件（21KB MP3，音质良好）

### 2. TTS API 实现
- ✅ 创建 [edge_tts_routes.py](../external-systems/partner-http-gateway/gateway/edge_tts_routes.py)
- ✅ 实现 `POST /v1/voice/synthesize` 路由
- ✅ 支持参数：
  - `text`: 要合成的文本（必填）
  - `voice`: 音色选择（可选：xiaoxiao/xiaoyi/yunxi/yunjian）
  - `format`: 输出格式（mp3/wav）

### 3. Gateway 路由集成
- ✅ 在 [rest_dispatch.py](../external-systems/partner-http-gateway/gateway/rest_dispatch.py) 中添加路由注册
- ✅ 导入 `dispatch_edge_tts_rest`
- ✅ 添加到 dispatcher 列表

### 4. 音频存储扩展
- ✅ 在 [media_storage.py](../external-systems/partner-chat-system/chat_system/media_storage.py) 中添加 `upload_audio` 函数
- ✅ 支持格式检测（MP3/WAV/OGG/M4A）
- ✅ 计算音频时长（使用 pydub）
- ✅ 上传到 MinIO（类似图片存储）

---

## 🔄 后续步骤

### 步骤 3：集成到 Agent 回复流程（预计15分钟）

**目标**：Agent回复时自动生成语音并附加到消息

**实施位置**：
- [assistant_runtime.py](../external-systems/partner-chat-system/chat_system/assistant_runtime.py)
- [assistant_sessions.py](../external-systems/partner-chat-system/chat_system/assistant_sessions.py)

**集成逻辑**：
```python
def _generate_tts_for_agent_reply(text: str, voice: str = "xiaoxiao") -> dict:
    """为Agent回复生成语音"""
    # 1. 调用 TTS API 合成语音
    audio_data, metadata = synthesize_audio_edge_tts(text, voice, "mp3")

    # 2. 上传到 MinIO
    upload_result = upload_audio(audio_data, f"tts-{voice}.mp3", "xiaoya")

    # 3. 返回音频元数据
    return {
        "media_type": "audio",
        "media_url": upload_result["media_url"],
        "media_metadata": {
            "duration_ms": metadata["duration_ms"],
            "format": metadata["format"],
            "size": metadata["size"],
            "tts_engine": "edge-tts",
            "voice": voice,
        }
    }
```

**触发场景**（需验证）：
1. ✅ **开场白**：用户注册后小雅主动发送（自动生成语音）
2. ✅ **私信小雅**：用户主动问小雅，小雅回复（自动生成语音）
3. ✅ **AI红娘提示**：在主群聊中主动提示（自动生成语音）

---

### 步骤 4：前端音频播放组件（预计20分钟）

#### 4.1 AudioMessage 组件

**位置**：[audio-message.tsx](../frontend/her-app/components/her/audio-message.tsx)（需创建）

**功能**：
- ✅ 显示播放按钮（圆形，带进度动画）
- ✅ 播放/暂停控制
- ✅ 进度条显示
- ✅ 音量图标
- ✅ 时间显示（当前时间/总时长）

**Props**：
```typescript
interface AudioMessageProps {
  audioUrl: string      // 音频URL
  durationMs: number    // 音频时长（毫秒）
  format: string        // 音频格式（mp3/wav）
  onPlayStart?: () => void
  onPlayEnd?: () => void
}
```

#### 4.2 XiaoyaRichText 扩展

**位置**：[xiaoya-rich-text.tsx](../frontend/her-app/components/her/ui/xiaoya-rich-text.tsx)（需修改）

**修改**：
```typescript
interface XiaoyaRichTextProps {
  content: string
  mediaType?: string       // 新增
  mediaUrl?: string        // 新增
  mediaMetadata?: {...}    // 新增
}
```

**渲染逻辑**：
- 如果 `mediaType === 'audio'`，显示 AudioMessage 组件
- 文本内容显示在音频下方

#### 4.3 chat-page.tsx 修改

**位置**：[chat-page.tsx](../frontend/her-app/components/her/chat-page.tsx)（需修改）

**修改点**：
- 消息渲染部分支持 audio 类型
- 小雅消息（assistant）支持音频显示

---

### 步骤 5：完整测试验证（预计15分钟）

#### 测试场景

**场景 1：开场白**
- 新用户注册后
- 小雅主动发送欢迎消息
- 消息包含文本 + 语音
- 用户可播放语音或阅读文字

**场景 2：私信小雅**
- 用户在小雅私信面板发送问题
- 小雅回复包含文本 + 语音
- 语音时长 < 10秒（快速回复）

**场景 3：AI红娘提示**
- 在主群聊中，小雅主动发送提示
- 消息包含文本 + 语音
- 语音风格友好、自然

#### 测试脚本

```bash
# 测试 TTS API
curl -X POST http://localhost:8081/v1/voice/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是小雅，有什么可以帮助你的吗？", "voice": "xiaoxiao"}' \
  --output response.json

# 检查响应
cat response.json | jq .

# 播放生成的音频
curl -X GET "$(cat response.json | jq -r '.audio_url')" \
  --output test.mp3
afplay test.mp3
```

---

## 📊 技术对比总结

| 方案 | 优势 | 劣势 | 实施耗时 |
|------|------|------|---------|
| **edge-tts（已选）** | ✅ 无需本地部署<br>✅ 音质优秀<br>✅ 5分钟实现<br>✅ 免费 | ⚠️ 需联网<br>⚠️ 数据到云端 | **40分钟** |
| **GPT-SoVITS** | ✅ 完全本地<br>✅ 隐私安全 | ❌ 需LLVM<br>❌ 编译复杂 | 3-5小时 |

---

## 🎯 下一步行动

**立即开始步骤3和4**：
1. 集成到 Agent 回复流程（15分钟）
2. 实现前端音频播放组件（20分钟）
3. 完整测试验证（15分钟）

**总预计耗时**：50分钟完成全部功能

---

## 📝 文件清单

**已创建/修改文件**：
1. ✅ [edge_tts_routes.py](../external-systems/partner-http-gateway/gateway/edge_tts_routes.py) - TTS API路由
2. ✅ [rest_dispatch.py](../external-systems/partner-http-gateway/gateway/rest_dispatch.py) - 路由注册
3. ✅ [media_storage.py](../external-systems/partner-chat-system/chat_system/media_storage.py) - 音频上传函数

**待创建/修改文件**：
1. ⏳ [audio-message.tsx](../frontend/her-app/components/her/audio-message.tsx) - 音频播放组件
2. ⏳ [xiaoya-rich-text.tsx](../frontend/her-app/components/her/ui/xiaoya-rich-text.tsx) - 扩展支持音频
3. ⏳ [chat-page.tsx](../frontend/her-app/components/her/chat-page.tsx) - 消息渲染支持音频
4. ⏳ [assistant_runtime.py](../external-systems/partner-chat-system/chat_system/assistant_runtime.py) - Agent回复集成

---

## 🔍 API 文档

### POST /v1/voice/synthesize

**请求体**：
```json
{
  "text": "你好，我是小雅",
  "voice": "xiaoxiao",  // 可选：xiaoxiao/xiaoyi/yunxi/yunjian
  "format": "mp3"       // 可选：mp3/wav
}
```

**响应**：
```json
{
  "success": true,
  "audio_url": "https://minio.example.com/bucket/object_key",
  "duration_ms": 3000,
  "format": "mp3",
  "size": 21000,
  "voice": "zh-CN-XiaoxiaoNeural",
  "engine": "edge-tts",
  "trace_id": "..."
}
```

**错误响应**：
```json
{
  "error": {
    "code": "tts_failed",
    "message": "语音合成失败：..."
  },
  "trace_id": "..."
}
```

---

## ✅ 里程碑达成

**里程碑 1：语音合成能力部署**（已完成）
- ✅ Edge-TTS 安装和测试
- ✅ TTS API 实现和集成
- ✅ 音频存储功能扩展

**里程碑 2：Agent回复语音集成**（进行中）
- 🔄 Agent回复流程集成
- 🔄 三个场景验证

**里程碑 3：前端音频播放**（待开始）
- ⏳ AudioMessage 组件
- ⏳ 消息渲染支持音频
- ⏳ 完整测试验证