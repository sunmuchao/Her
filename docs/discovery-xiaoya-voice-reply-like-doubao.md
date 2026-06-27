# 发现页小雅语音回复功能（类似豆包）

## 功能描述

**类似豆包的模式**：小雅每次回复消息时，都自动生成语音并播放，文本下方显示重复播放按钮。

## 已完成的修改

### 后端修改（3个文件）

**1. service.py - 核心修改**
- 在 `_apply_runtime_result` 方法中，为**每条小雅回复**都调用 TTS 服务
- 文件：[service.py:1448-1497](../external-systems/partner-discovery-system/discovery_system/service.py#L1448-L1497)

**2. tts_service.py - 独立TTS服务**
- 提供统一的语音生成能力
- 文件：[tts_service.py](../external-systems/partner-chat-system/chat_system/tts_service.py)

**3. decision_models.py - 支持metadata**
- DiscoveryDecision 添加 assistant_message_metadata 字段
- 文件：[decision_models.py](../external-systems/partner-discovery-system/discovery_system/decision_models.py)

### 前端修改（2个文件）

**1. map-discovery-view.ts - 自动播放逻辑**
- 10秒内的消息自动播放（isNewMessage逻辑）
- 文件：[map-discovery-view.ts:137-156](../frontend/her-app/lib/discovery/map-discovery-view.ts#L137-L156)

**2. audio-message.tsx - 播放按钮改进**
- 更明显的播放按钮（圆形按钮 + 文字标签）
- 显示"播放中"状态和音频时长
- 文件：[audio-message.tsx:129-156](../frontend/her-app/components/her/audio-message.tsx#L129-L156)

## 验证步骤

### 1. 启动 MinIO 服务（关键）

```bash
# 启动 MinIO（TTS 需要上传音频）
docker compose up -d minio

# 验证 MinIO 是否运行
docker compose ps minio
curl http://127.0.0.1:9000
```

### 2. 测试完整对话流程

**打开发现页**：
```bash
open http://127.0.0.1:3000/discover
```

**测试场景1：开场白**
- 预期：小雅发送开场白消息
- 文本："我根据你刚填的资料筛了几位..."
- 播放按钮：**"播放语音"** 显示在文本上方
- 自动播放：10秒内的消息自动播放语音

**测试场景2：对话回复**
- 发送消息："喔唷喔唷喔唷"
- 预期：小雅回复
- 文本："哈哈，听你这语气..."
- 播放按钮：**"播放语音"** 显示在文本上方
- 自动播放：因为是新回复，应该自动播放

**测试场景3：重复播放**
- 点击播放按钮可以重复播放
- 播放时显示："播放中"
- 可以暂停和重新播放

## 预期效果截图

```
┌─────────────────────────────────────┐
│ 小雅消息                            │
│                                     │
│ 🔊 [播放语音] 3秒                    │
│                                     │
│ 哈哈，听你这语气，是对这批候选人     │
│ 有什么想法？😄                       │
│                                     │
│ 是想说"就这？"还是"有点意思"？      │
│跟我说说嘛，是哪里不太满意，还是想   │
│换一批看看？                          │
│                                     │
│ 刚刚                                │
└─────────────────────────────────────┘
```

## 数据流完整链路

```
用户发送消息："喔唷喔唷喔唷"
        ↓
Discovery Service 接收 turn
        ↓
Agent 生成回复："哈哈，听你这语气..."
        ↓
_apply_runtime_result 方法
        ↓
调用 TTS 服务：synthesize_tts(text, voice="xiaoxiao")
        ↓
edge-tts 生成语音 → MinIO 上传 → 返回 URL
        ↓
assistant_message metadata = {
  media_type: "audio",
  media_url: "http://...",
  media_metadata: {duration_ms, format, ...}
}
        ↓
API 返回 DiscoveryView
        ↓
前端 mapDiscoveryView 提取 metadata
        ↓
isNewMessage = true (10秒内)
        ↓
XiaoyaRichText 渲染 AudioMessage
        ↓
autoPlay = true → 自动播放语音
        ↓
用户听到语音 + 看到播放按钮
```

## 常见问题排查

### Q1: 看不到播放按钮

**原因1**：MinIO 没有运行
```bash
docker compose up -d minio
```

**原因2**：文本超过500字符（不生成语音）
- 短消息：生成语音 + 播放按钮
- 长消息：仅显示文本（无播放按钮）

### Q2: 播放按钮显示但不自动播放

**原因**：消息超过10秒（isNewMessage = false）

**解决**：
- 新消息会自动播放
- 历史消息点击播放按钮手动播放

### Q3: 点击播放按钮没有声音

**原因**：MinIO URL 不可访问

**排查**：
```bash
# 检查音频 URL
curl {media_url}

# 检查浏览器控制台
# Network → 查看是否有音频请求失败
```

## 测试脚本

```bash
# 测试 TTS 服务
python3 scripts/test_tts_service.py

# 测试 Discovery API
curl -X POST http://localhost:8081/v1/discovery/sessions \
  -H "Content-Type: application/json" \
  -d '{"profile_id": 1001}'

# 查看 timeline 是否包含 metadata
curl http://localhost:8081/v1/discovery/sessions/{session_id} | jq '.view.timeline[-1].metadata'
```

## 关键改进点

### 之前的问题
- ❌ 只有开场白有语音
- ❌ turn 回复没有语音
- ❌ 播放按钮不明显（小喇叭图标）
- ❌ isNewMessage 硬编码为 false

### 现在的改进
- ✅ **每条小雅回复都有语音**
- ✅ **10秒内的消息自动播放**
- ✅ **明显的播放按钮**（圆形按钮 + 文字标签）
- ✅ **播放状态提示**（"播放中"）
- ✅ **音频时长显示**（"3秒"）

---

**下一步**：启动 MinIO 服务，然后在发现页测试完整对话流程