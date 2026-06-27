# 发现页语音播放功能验证指南

## 当前状态

已完成所有代码修改，但需要启动 MinIO 服务才能让 TTS 正常工作。

### 已完成的修改

**前端**：
1. ✅ 修复 isNewMessage 逻辑（10秒内的消息自动播放）
2. ✅ 改进 AudioMessage 组件（更明显的播放按钮）
3. ✅ 正确提取和传递 metadata

**后端**：
1. ✅ 创建独立 TTS 服务（tts_service.py）
2. ✅ 修复导入路径问题
3. ✅ Discovery service 调用 TTS 生成语音

### 问题根因

**MinIO 服务没有运行**，导致 TTS 无法上传音频文件，discovery service 返回的消息没有 metadata，前端看不到播放按钮。

## 快速解决方案

### 方案1：启动 MinIO 服务（推荐）

```bash
# 1. 启动 MinIO
cd /Users/sunmuchao/Downloads/Her
docker compose up -d minio

# 2. 验证 MinIO 是否运行
docker compose ps minio

# 3. 验证 MinIO 连接
curl http://127.0.0.1:9000  # 应该返回 MinIO UI

# 4. 重启 discovery service（如果需要）
docker compose restart partner-discovery-system
```

### 方案2：使用本地文件存储（临时方案）

如果不想启动 MinIO，可以修改 tts_service.py 使用本地文件存储：

```python
# 在 tts_service.py 中添加本地存储 fallback
def _save_audio_local(audio_data, filename):
    """本地存储 fallback（用于测试）"""
    audio_dir = Path("/tmp/xiaoya-audio")
    audio_dir.mkdir(exist_ok=True)
    audio_path = audio_dir / filename
    with open(audio_path, "wb") as f:
        f.write(audio_data)
    # 返回本地 URL（前端需要能访问）
    return f"http://127.0.0.1:3000/audio/{filename}"
```

## 验证步骤

### 1. 测试 TTS 服务

```bash
# 运行测试脚本
python3 scripts/test_tts_service.py

# 预期结果：
# ✅ 成功导入 tts_service
# ✅ 语音生成成功
# media_url: http://...
```

### 2. 测试 Discovery API

```bash
# 创建新的 discovery session
curl -X POST http://localhost:8081/v1/discovery/sessions \
  -H "Content-Type: application/json" \
  -d '{"profile_id": 1001}'

# 查看返回的开场白是否包含 metadata
curl http://localhost:8081/v1/discovery/sessions/{session_id} | jq '.view.timeline[0]'

# 预期结果：
{
  "item_type": "assistant_message",
  "item_id": "...",
  "body": "我根据你刚填的资料筛了几位...",
  "created_at": "2026-06-27T...",
  "metadata": {
    "media_type": "audio",
    "media_url": "http://...",
    "media_metadata": {
      "duration_ms": 3000,
      "format": "mp3",
      ...
    }
  }
}
```

### 3. 前端验证

1. 打开 http://127.0.0.1:3000/discover
2. 查看小雅开场白消息
3. 应该看到：
   - 📝 文本内容："我根据你刚填的资料筛了几位..."
   - 🔊 播放按钮："播放语音"（圆形按钮）
   - ⏱ 音频时长："3秒"（如果成功生成）

4. 点击播放按钮：
   - 应该自动播放语音
   - 播放时显示："播放中"

5. 新消息自动播放：
   - 刷新页面（或创建新 session）
   - 开场白消息应该自动播放（10秒内的消息）

## 测试场景

### 场景1：新用户打开发现页

**预期**：
- 小雅发送开场白（文本+语音）
- 播放按钮显示在文本上方
- 语音自动播放（因为是新消息）

### 场景2：重复播放

**预期**：
- 点击播放按钮可以重复播放
- 播放时显示"播放中"状态
- 可以暂停播放

### 场景3：历史消息

**预期**：
- 打开旧的 discovery session
- 小雅的历史消息有播放按钮
- 但不会自动播放（因为超过10秒）

## AudioMessage 组件改进

**改进内容**：
1. ✅ 更明显的播放按钮（圆形按钮 + 文字标签）
2. ✅ 播放状态提示（播放中）
3. ✅ 音频时长显示（3秒）
4. ✅ 全局音频管理（确保只有一个音频播放）

**代码位置**：
- [audio-message.tsx](../frontend/her-app/components/her/audio-message.tsx)

## 数据流完整链路

```
后端：
1. discovery service → build_profile_first_open_result
2. 确定开场白文本："我根据你刚填的资料筛了几位..."
3. 调用 TTS 服务 → synthesize_tts(text, voice="xiaoxiao")
4. edge-tts 生成语音 → MinIO 上传 → 返回 URL
5. DiscoveryDecision(含 metadata)
6. service.py → assistant_message(含 metadata)
7. API 返回 → DiscoveryView

前端：
1. API 返回 DiscoveryView
2. mapDiscoveryView → 提取 metadata
3. DiscoveryTimelineItem(mediaType, mediaUrl, isNewMessage)
4. discover-page.tsx → XiaoyaRichText
5. XiaoyaRichText → AudioMessage(autoPlay={isNewMessage})
6. AudioMessage 渲染播放按钮
7. 用户点击播放 → 播放语音
```

## 常见问题排查

### Q1: 看不到播放按钮

**原因**：MinIO 没有运行，TTS 无法生成 metadata

**解决**：
```bash
docker compose up -d minio
docker compose restart partner-discovery-system
```

### Q2: 点击播放按钮没有声音

**原因**：音频 URL 不可访问

**排查**：
1. 检查 MinIO 是否运行：`curl http://127.0.0.1:9000`
2. 检查音频 URL 是否有效：`curl {media_url}`
3. 检查浏览器控制台是否有错误

### Q3: 播放按钮显示但不自动播放

**原因**：isNewMessage = false（消息超过10秒）

**解决**：
- 刷新页面（创建新 session）
- 或修改 isNewMessage 判断逻辑（延长到60秒）

### Q4: TTS 服务导入失败

**原因**：Python path 问题

**解决**：
- 检查 chat_system 是否在 Python path 中
- 或修改 service_session_open.py 的导入路径

## 完整启动命令

```bash
# 1. 启动所有服务
docker compose up -d

# 2. 验证服务状态
docker compose ps

# 3. 验证 MinIO
curl http://127.0.0.1:9000

# 4. 验证 Discovery API
curl -X POST http://localhost:8081/v1/discovery/sessions \
  -H "Content-Type: application/json" \
  -d '{"profile_id": 1001}'

# 5. 打开前端
open http://127.0.0.1:3000/discover
```

## 文件清单

**新建文件**：
1. [tts_service.py](../external-systems/partner-chat-system/chat_system/tts_service.py)
2. [test_tts_service.py](../scripts/test_tts_service.py)
3. [discovery-page-voice-playback-verification-guide.md](../docs/discovery-page-voice-playback-verification-guide.md)

**修改文件**：
1. [map-discovery-view.ts](../frontend/her-app/lib/discovery/map-discovery-view.ts) - isNewMessage 逻辑
2. [audio-message.tsx](../frontend/her-app/components/her/audio-message.tsx) - 改进播放按钮
3. [service_session_open.py](../external-systems/partner-discovery-system/discovery_system/service_session_open.py) - TTS 调用
4. 其他 7 个文件（见之前的总结）

---

**下一步**：启动 MinIO 服务，然后刷新发现页验证功能