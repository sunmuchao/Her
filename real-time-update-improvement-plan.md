# 实时更新功能改进完整方案

> **文档创建时间**：2026-07-01  
> **目标**：解决系统中缺少自动更新的功能，统一实时推送架构

---

## 一、问题总结

### 当前存在的问题

| 场景 | 问题描述 | 用户体验影响 | 严重程度 |
|------|---------|-------------|---------|
| 关系页面状态同步 | 卡片状态变化需手动刷新 | 错过聊天机会 | 中 |
| 验证状态变化 | 验证通过/失败需刷新查看 | 用户困惑 | 中 |
| 导航栏徽章更新 | 徽章延迟最多30秒 | 以为没消息 | 低 |
| 聊天"正在输入" | 看不到对方正在输入 | 聊天体验不流畅 | 低 |
| 用户档案更新 | 对方资料更新需刷新 | 看到旧资料 | 低 |
| 系统通知 | 缺少系统通知功能 | 缺少系统级通知 | 低 |

### 已实现的实时推送（对比）

| 场景 | 实现方式 | 状态 |
|------|---------|------|
| 聊天页面新消息 | SSE + 30秒轮询兜底 | ✅ 完善 |
| 发现页候选人准备 | SSE + 30秒轮询兜底 | ✅ 完善 |
| 发现页推荐卡片推送 | SSE（已修复类型问题） | ✅ 完善 |
| 视频通话信令 | WebSocket + 自动重连 | ✅ 完善 |

---

## 二、架构设计方案

### 核心原则

**统一实时推送架构**：
- ✅ SSE（Server-Sent Events）作为主要推送机制
- ✅ 轮询作为兜底机制（SSE失败时）
- ✅ 事件驱动的状态更新
- ✅ 复用现有SSE服务器基础设施

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端监听层                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  关系页面 Hook          导航栏 Hook          验证页面 Hook       │
│  use-relationships      use-badge-counts     use-verification   │
│       │                      │                      │          │
│       └──────────────────────┴──────────────────────┘          │
│                              │                                  │
│                    SSE Connection Manager                        │
│                    (统一连接管理)                                │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SSE Server (现有)                           │
│                  /sse-server:8000                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  /sse/chat/{caseId}              聊天消息推送          ✅ 已有   │
│  /sse/discovery/{sessionId}      发现页推送            ✅ 已有   │
│  /sse/relationships/{profileId}  关系页面推送          🆕 新增   │
│  /sse/verification/{profileId}   验证状态推送          🆕 新增   │
│  /sse/notifications/{profileId} 全局通知推送          🆕 新增   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     后端事件触发层                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  匹配服务              验证服务              通知服务             │
│  (匹配状态变化)        (验证状态变化)        (系统通知)          │
│       │                      │                      │          │
│       └──────────────────────┴──────────────────────┘          │
│                              │                                  │
│                    SSE Event Publisher                         │
│                    (统一事件发布)                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、分场景改进方案

### 场景1：关系页面状态同步（高优先级）

#### 问题根因

**当前实现**：
- 关系页面使用 `useRelationshipsPageData` hook
- 只使用 React Query，没有SSE监听
- 依赖导航栏徽章的30秒轮询
- 用户操作后调用 `refetch()` 手动刷新

**根因**：关系页面没有接入SSE推送机制

#### 改进方案

**1. 后端新增SSE端点**

```python
# external-systems/sse-server/sse_server/handlers.py

async def relationships_stream(request, profile_id: str):
    """
    关系页面SSE推送端点
    
    推送事件类型：
    - new_match: 新匹配到达
    - status_change: 卡片状态变化（等待回复 → 开始聊天）
    - profile_update: 对方资料更新
    """
    queue = await get_or_create_queue(f"relationships:{profile_id}")
    
    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

# 路由注册
app.add_route("/sse/relationships/{profile_id}", relationships_stream)
```

**2. 后端事件触发点**

```python
# 匹配服务：匹配成功时触发
async def on_match_created(match_data: dict):
    """匹配创建时触发SSE推送"""
    # 推送给发起方
    await publish_event(
        f"relationships:{match_data['requester_id']}",
        {
            "type": "new_match",
            "data": {
                "match_id": match_data["match_id"],
                "profile_id": match_data["target_id"],
                "status": "waiting_response"
            }
        }
    )
    
    # 推送给接收方
    await publish_event(
        f"relationships:{match_data['target_id']}",
        {
            "type": "new_match",
            "data": {
                "match_id": match_data["match_id"],
                "profile_id": match_data["requester_id"],
                "status": "pending_accept"
            }
        }
    )

# 匹配服务：状态变化时触发
async def on_match_status_changed(match_id: str, old_status: str, new_status: str):
    """匹配状态变化时触发SSE推送"""
    match = await get_match(match_id)
    
    # 推送给双方
    for profile_id in [match["requester_id"], match["target_id"]]:
        await publish_event(
            f"relationships:{profile_id}",
            {
                "type": "status_change",
                "data": {
                    "match_id": match_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "timestamp": datetime.now().isoformat()
                }
            }
        )
```

**3. 前端Hook改造**

```typescript
// frontend/her-app/lib/hooks/use-relationships-realtime.ts

import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface RelationshipsSSEEvent {
  type: 'new_match' | 'status_change' | 'profile_update';
  data: any;
}

export function useRelationshipsRealtime(profileId: string | null) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (!profileId) return;

    const eventSource = new EventSource(
      `${SSE_SERVER_URL}/sse/relationships/${profileId}`
    );

    eventSource.addEventListener('new_match', (e) => {
      const event: RelationshipsSSEEvent = JSON.parse(e.data);
      // 刷新关系列表
      queryClient.invalidateQueries({ queryKey: ['relationships'] });
      // 更新导航栏徽章
      queryClient.invalidateQueries({ queryKey: ['badge-counts'] });
      // 可选：显示通知
      showNotification('新匹配到达', event.data.profile_id);
    });

    eventSource.addEventListener('status_change', (e) => {
      const event: RelationshipsSSEEvent = JSON.parse(e.data);
      // 刷新关系列表（状态变化）
      queryClient.invalidateQueries({ queryKey: ['relationships'] });
      // 更新导航栏徽章
      queryClient.invalidateQueries({ queryKey: ['badge-counts'] });
    });

    eventSource.addEventListener('profile_update', (e) => {
      const event: RelationshipsSSEEvent = JSON.parse(e.data);
      // 刷新对方资料
      queryClient.invalidateQueries({ 
        queryKey: ['profile', event.data.profile_id] 
      });
    });

    eventSource.onerror = () => {
      eventSource.close();
      // 3秒后重连
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    eventSourceRef.current = eventSource;
  }, [profileId, queryClient]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return {
    isConnected: eventSourceRef.current?.readyState === EventSource.OPEN
  };
}
```

**4. 关系页面集成**

```typescript
// frontend/her-app/components/her/relationships-page.tsx

export function RelationshipsPage({ profileId }: { profileId: string }) {
  const { data, isLoading, refetch } = useRelationshipsPageData(profileId);
  
  // ✅ 新增：实时推送
  const { isConnected } = useRelationshipsRealtime(profileId);

  // 页面渲染...
}
```

**5. 兜底机制**

```typescript
// 如果SSE连接失败，回退到30秒轮询
export function useRelationshipsRealtime(profileId: string | null) {
  const [usePolling, setUsePolling] = useState(false);

  useEffect(() => {
    const eventSource = new EventSource(/* ... */);
    
    eventSource.onerror = () => {
      // SSE失败，切换到轮询
      setUsePolling(true);
    };
  }, [profileId]);

  // 轮询兜底
  useEffect(() => {
    if (!usePolling || !profileId) return;

    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['relationships'] });
    }, 30000);

    return () => clearInterval(interval);
  }, [usePolling, profileId, queryClient]);
}
```

#### 验收标准

- ✅ 新匹配到达时，关系页面自动刷新，无需手动刷新
- ✅ 卡片状态变化（等待回复 → 开始聊天）自动更新
- ✅ SSE连接失败时，自动切换到30秒轮询兜底
- ✅ 连接断开后自动重连（3秒延迟）

---

### 场景2：验证状态变化（高优先级）

#### 问题根因

**当前实现**：
- 验证完成后，用户档案状态变化不会实时推送
- 用户必须刷新页面查看验证结果
- 其他用户也无法实时看到验证状态变化

**根因**：缺少验证状态变化的SSE推送机制

#### 改进方案

**1. 后端新增SSE端点**

```python
# external-systems/sse-server/sse_server/handlers.py

async def verification_stream(request, profile_id: str):
    """
    验证状态SSE推送端点
    
    推送事件类型：
    - verification_submitted: 验证材料已提交
    - verification_passed: 验证通过
    - verification_failed: 验证失败
    """
    queue = await get_or_create_queue(f"verification:{profile_id}")
    
    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )

# 路由注册
app.add_route("/sse/verification/{profile_id}", verification_stream)
```

**2. 后端事件触发点**

```python
# verification-service/verification_service/handlers.py

async def on_verification_completed(profile_id: str, result: str):
    """验证完成时触发SSE推送"""
    
    if result == "passed":
        event_type = "verification_passed"
        message = "恭喜！您的身份验证已通过"
    else:
        event_type = "verification_failed"
        message = "身份验证未通过，请重新提交材料"
    
    await publish_event(
        f"verification:{profile_id}",
        {
            "type": event_type,
            "data": {
                "profile_id": profile_id,
                "result": result,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
        }
    )
    
    # 同时推送到关系页面（对方可以看到验证状态变化）
    # 获取该用户的所有匹配关系
    matches = await get_user_matches(profile_id)
    for match in matches:
        other_profile_id = match["requester_id"] if match["target_id"] == profile_id else match["target_id"]
        await publish_event(
            f"relationships:{other_profile_id}",
            {
                "type": "profile_update",
                "data": {
                    "profile_id": profile_id,
                    "field": "verification_status",
                    "new_value": result
                }
            }
        )
```

**3. 前端Hook实现**

```typescript
// frontend/her-app/lib/hooks/use-verification-realtime.ts

export function useVerificationRealtime(profileId: string | null) {
  const queryClient = useQueryClient();
  const [verificationStatus, setVerificationStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!profileId) return;

    const eventSource = new EventSource(
      `${SSE_SERVER_URL}/sse/verification/${profileId}`
    );

    eventSource.addEventListener('verification_passed', (e) => {
      const event = JSON.parse(e.data);
      setVerificationStatus('passed');
      // 刷新用户档案
      queryClient.invalidateQueries({ queryKey: ['profile', profileId] });
      // 显示成功通知
      showSuccessNotification('验证通过', event.message);
    });

    eventSource.addEventListener('verification_failed', (e) => {
      const event = JSON.parse(e.data);
      setVerificationStatus('failed');
      // 显示失败通知
      showErrorNotification('验证失败', event.message);
    });

    return () => eventSource.close();
  }, [profileId, queryClient]);

  return { verificationStatus };
}
```

**4. 验证页面集成**

```typescript
// frontend/her-app/components/her/verification-page.tsx

export function VerificationPage({ profileId }: { profileId: string }) {
  const { data, isLoading } = useVerificationStatus(profileId);
  
  // ✅ 新增：实时推送
  const { verificationStatus } = useVerificationRealtime(profileId);

  // 显示验证状态
  if (verificationStatus === 'passed') {
    return <VerificationPassed />;
  }

  // 页面渲染...
}
```

#### 验收标准

- ✅ 验证通过时，用户立即看到"验证通过"通知，无需刷新
- ✅ 验证失败时，用户立即看到"验证失败"通知
- ✅ 对方用户在关系页面可以看到验证状态变化（如"已验证"标签）
- ✅ SSE连接失败时，有兜底机制

---

### 场景3：导航栏徽章实时更新（中优先级）

#### 问题根因

**当前实现**：
- `use-badge-counts.ts` 使用30秒轮询刷新徽章
- 监听本地事件 `RELATIONSHIP_READ_EVENT` 和 `RECOMMENDATION_READ_EVENT`
- 没有SSE实时推送机制

**根因**：依赖轮询而非实时推送

#### 改进方案

**方案A：缩短轮询间隔（简单方案）**

```typescript
// frontend/her-app/hooks/use-badge-counts.ts

export function useBadgeCounts(profileId: string | null) {
  const { data, refetch } = useQuery({
    queryKey: ['badge-counts', profileId],
    queryFn: () => fetchBadgeCounts(profileId),
    refetchInterval: 5000, // ✅ 改为5秒（原来是30秒）
  });

  // 其他逻辑...
}
```

**优点**：改动最小，立即生效  
**缺点**：增加服务器压力

---

**方案B：复用现有SSE推送（推荐方案）**

```typescript
// frontend/her-app/hooks/use-badge-counts.ts

export function useBadgeCounts(profileId: string | null) {
  const queryClient = useQueryClient();
  
  // 复用关系页面SSE连接
  useRelationshipsRealtime(profileId);
  
  // 复用验证页面SSE连接
  useVerificationRealtime(profileId);

  const { data } = useQuery({
    queryKey: ['badge-counts', profileId],
    queryFn: () => fetchBadgeCounts(profileId),
    // ✅ 移除轮询，依赖SSE推送刷新
    // refetchInterval: 30000, // 删除这行
  });

  // 当SSE事件到达时，徽章会自动刷新（在SSE事件处理中调用invalidateQueries）

  return { data };
}
```

**优点**：实时性更好，减少服务器压力  
**缺点**：依赖SSE连接稳定性

---

**方案C：独立徽章SSE推送（最完整方案）**

```python
# 后端新增SSE端点
async def notifications_stream(request, profile_id: str):
    """
    全局通知SSE推送端点
    
    推送事件类型：
    - badge_update: 徽章数量变化
    - system_notification: 系统通知
    """
    queue = await get_or_create_queue(f"notifications:{profile_id}")
    
    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 后端事件触发点
async def on_badge_count_changed(profile_id: str, badge_type: str, count: int):
    """徽章数量变化时触发SSE推送"""
    await publish_event(
        f"notifications:{profile_id}",
        {
            "type": "badge_update",
            "data": {
                "badge_type": badge_type,
                "count": count,
                "timestamp": datetime.now().isoformat()
            }
        }
    )
```

```typescript
// 前端Hook
export function useBadgeCountsRealtime(profileId: string | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!profileId) return;

    const eventSource = new EventSource(
      `${SSE_SERVER_URL}/sse/notifications/${profileId}`
    );

    eventSource.addEventListener('badge_update', (e) => {
      const event = JSON.parse(e.data);
      // 直接更新徽章数据，无需重新请求
      queryClient.setQueryData(['badge-counts', profileId], (old: any) => ({
        ...old,
        [event.badge_type]: event.count
      }));
    });

    return () => eventSource.close();
  }, [profileId, queryClient]);
}
```

**优点**：最完整的方案，支持系统通知扩展  
**缺点**：需要新增SSE端点

#### 推荐方案

**分阶段实施**：
1. **短期**：采用方案A（缩短轮询间隔到5秒）
2. **中期**：采用方案B（复用现有SSE连接）
3. **长期**：采用方案C（独立徽章SSE推送，支持系统通知）

#### 验收标准

- ✅ 徽章更新延迟从30秒降低到5秒（方案A）或实时（方案B/C）
- ✅ SSE连接失败时，有兜底机制

---

### 场景4：聊天"正在输入"状态（中优先级）

#### 问题根因

**当前实现**：
- 前端有 `TypingIndicator` 组件
- 但没有后端推送机制

**根因**：缺少WebSocket/SSE推送"typing_start"事件

#### 改进方案

**方案A：复用现有聊天SSE连接**

```python
# external-systems/sse-server/sse_server/handlers.py

async def chat_stream(request, case_id: str, participant_id: str):
    """
    聊天SSE推送端点（已有）
    
    新增事件类型：
    - typing_start: 对方正在输入
    - typing_end: 对方停止输入
    """
    queue = await get_or_create_queue(f"chat:{case_id}")
    
    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 触发点
async def on_typing_start(case_id: str, user_id: str):
    """用户开始输入时触发"""
    match = await get_match(case_id)
    other_user_id = match["requester_id"] if match["target_id"] == user_id else match["target_id"]
    
    await publish_event(
        f"chat:{case_id}",
        {
            "type": "typing_start",
            "data": {
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        }
    )

async def on_typing_end(case_id: str, user_id: str):
    """用户停止输入时触发"""
    await publish_event(
        f"chat:{case_id}",
        {
            "type": "typing_end",
            "data": {
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        }
    )
```

**前端实现**：

```typescript
// frontend/her-app/components/her/chat-page.tsx

export function ChatPage({ caseId, userId }: { caseId: string; userId: string }) {
  const [isTyping, setIsTyping] = useState(false);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // ✅ 新增：监听"正在输入"事件
  useEffect(() => {
    const eventSource = new EventSource(
      `${SSE_SERVER_URL}/sse/chat/${caseId}?participant_id=${userId}`
    );

    eventSource.addEventListener('typing_start', (e) => {
      const event = JSON.parse(e.data);
      if (event.user_id !== userId) {
        setIsTyping(true);
      }
    });

    eventSource.addEventListener('typing_end', (e) => {
      const event = JSON.parse(e.data);
      if (event.user_id !== userId) {
        setIsTyping(false);
      }
    });

    return () => eventSource.close();
  }, [caseId, userId]);

  // ✅ 新增：发送"正在输入"事件
  const handleTyping = useCallback(() => {
    // 发送typing_start
    fetch(`${API_URL}/chat/${caseId}/typing/start`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId })
    });

    // 3秒后自动发送typing_end
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    typingTimeoutRef.current = setTimeout(() => {
      fetch(`${API_URL}/chat/${caseId}/typing/end`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId })
      });
    }, 3000);
  }, [caseId, userId]);

  return (
    <div>
      <ChatInput onTyping={handleTyping} />
      {isTyping && <TypingIndicator />}
    </div>
  );
}
```

#### 验收标准

- ✅ 对方开始输入时，显示"对方正在输入..."提示
- ✅ 对方停止输入3秒后，提示消失
- ✅ SSE连接失败时，功能降级（不显示提示）

---

### 场景5：用户档案状态变化（低优先级）

#### 问题根因

**当前实现**：
- 用户档案更新后，其他用户无法实时看到变化
- 关系页面、发现页不会自动刷新用户档案信息

**根因**：缺少档案变化推送机制

#### 改进方案

**复用关系页面SSE连接**：

```python
# 档案服务：档案更新时触发
async def on_profile_updated(profile_id: str, updated_fields: list[str]):
    """用户档案更新时触发SSE推送"""
    
    # 获取该用户的所有匹配关系
    matches = await get_user_matches(profile_id)
    
    # 推送给所有匹配对象
    for match in matches:
        other_profile_id = match["requester_id"] if match["target_id"] == profile_id else match["target_id"]
        
        await publish_event(
            f"relationships:{other_profile_id}",
            {
                "type": "profile_update",
                "data": {
                    "profile_id": profile_id,
                    "updated_fields": updated_fields,
                    "timestamp": datetime.now().isoformat()
                }
            }
        )
```

**前端处理**：

```typescript
// 在 useRelationshipsRealtime 中已监听 profile_update 事件
eventSource.addEventListener('profile_update', (e) => {
  const event = JSON.parse(e.data);
  // 刷新对方资料
  queryClient.invalidateQueries({ 
    queryKey: ['profile', event.data.profile_id] 
  });
});
```

#### 验收标准

- ✅ 对方更新资料后，关系页面自动显示最新资料
- ✅ 更新照片、昵称等字段后，自动刷新

---

### 场景6：系统通知（低优先级）

#### 问题根因

**当前实现**：项目中没有系统通知架构

**根因**：缺少系统级通知功能

#### 改进方案

**长期规划**：
1. 建立系统通知中心
2. 添加全局通知组件
3. SSE推送系统级消息

**暂不实施**，纳入未来规划。

---

## 四、统一连接管理器

### 问题

当前每个页面独立管理SSE连接：
- 聊天页面：`/sse/chat/{caseId}`
- 发现页：`/sse/discovery/{sessionId}`
- 关系页面：`/sse/relationships/{profileId}`（新增）
- 验证页面：`/sse/verification/{profileId}`（新增）

可能导致：
- 多个SSE连接同时存在
- 连接管理分散
- 资源浪费

### 解决方案：统一SSE连接管理器

**方案A：单一SSE连接 + 多路复用**

```typescript
// frontend/her-app/lib/sse-connection-manager.ts

class SSEConnectionManager {
  private connections: Map<string, EventSource> = new Map();
  private listeners: Map<string, Set<(event: any) => void>> = new Map();

  /**
   * 订阅SSE事件
   * @param channel 频道名称（如 'relationships:123'）
   * @param eventType 事件类型（如 'new_match'）
   * @param callback 回调函数
   */
  subscribe(channel: string, eventType: string, callback: (event: any) => void) {
    // 获取或创建连接
    if (!this.connections.has(channel)) {
      this.createConnection(channel);
    }

    // 注册监听器
    const key = `${channel}:${eventType}`;
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(callback);

    // 返回取消订阅函数
    return () => {
      this.listeners.get(key)?.delete(callback);
      // 如果没有监听器了，关闭连接
      if (this.listeners.get(key)?.size === 0) {
        this.connections.get(channel)?.close();
        this.connections.delete(channel);
      }
    };
  }

  private createConnection(channel: string) {
    const eventSource = new EventSource(
      `${SSE_SERVER_URL}/sse/${channel}`
    );

    eventSource.onmessage = (e) => {
      const event = JSON.parse(e.data);
      const key = `${channel}:${event.type}`;
      this.listeners.get(key)?.forEach(callback => callback(event));
    };

    eventSource.onerror = () => {
      // 3秒后重连
      setTimeout(() => {
        this.createConnection(channel);
      }, 3000);
    };

    this.connections.set(channel, eventSource);
  }
}

export const sseManager = new SSEConnectionManager();
```

**使用示例**：

```typescript
// 关系页面
useEffect(() => {
  const unsubscribe = sseManager.subscribe(
    `relationships:${profileId}`,
    'new_match',
    (event) => {
      queryClient.invalidateQueries({ queryKey: ['relationships'] });
    }
  );

  return unsubscribe;
}, [profileId]);
```

---

**方案B：后端多路复用SSE**

```python
# 后端统一SSE端点
async def unified_stream(request, profile_id: str):
    """
    统一SSE推送端点
    
    推送所有类型的事件：
    - new_match: 新匹配
    - status_change: 状态变化
    - verification_passed: 验证通过
    - badge_update: 徽章更新
    - typing_start: 正在输入
    - profile_update: 资料更新
    """
    queue = await get_or_create_queue(f"user:{profile_id}")
    
    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 路由
app.add_route("/sse/user/{profile_id}", unified_stream)
```

```typescript
// 前端统一监听
const eventSource = new EventSource(`${SSE_SERVER_URL}/sse/user/${profileId}`);

eventSource.addEventListener('new_match', handleNewMatch);
eventSource.addEventListener('status_change', handleStatusChange);
eventSource.addEventListener('verification_passed', handleVerification);
eventSource.addEventListener('badge_update', handleBadgeUpdate);
eventSource.addEventListener('typing_start', handleTyping);
eventSource.addEventListener('profile_update', handleProfileUpdate);
```

**优点**：单一连接，资源占用少  
**缺点**：需要改造后端架构

### 推荐

**短期**：方案A（前端统一连接管理器）  
**长期**：方案B（后端多路复用SSE）

---

## 五、实施计划

### 分阶段实施

#### 第一阶段：高优先级（预估3天）

**目标**：解决关系页面和验证状态同步问题

**任务**：
1. 后端新增 `/sse/relationships/{profileId}` 端点
2. 后端新增 `/sse/verification/{profileId}` 端点
3. 后端事件触发点（匹配成功、状态变化、验证完成）
4. 前端 `useRelationshipsRealtime` Hook
5. 前端 `useVerificationRealtime` Hook
6. 关系页面集成SSE
7. 验证页面集成SSE
8. 兜底机制（30秒轮询）

**验收标准**：
- ✅ 关系页面卡片状态自动更新
- ✅ 验证通过/失败实时通知
- ✅ SSE连接失败时自动切换轮询

---

#### 第二阶段：中优先级（预估2天）

**目标**：优化导航栏徽章和聊天"正在输入"

**任务**：
1. 缩短导航栏徽章轮询间隔（30秒 → 5秒）
2. 后端新增 `typing_start` / `typing_end` 事件
3. 前端发送"正在输入"事件
4. 前端监听"正在输入"事件
5. 显示"对方正在输入..."提示

**验收标准**：
- ✅ 徽章更新延迟降低到5秒
- ✅ 聊天时显示"对方正在输入..."提示

---

#### 第三阶段：低优先级（预估1天）

**目标**：用户档案实时更新

**任务**：
1. 后端档案更新事件触发
2. 复用关系页面SSE连接推送档案更新

**验收标准**：
- ✅ 对方更新资料后，关系页面自动显示最新资料

---

#### 第四阶段：架构优化（预估2天）

**目标**：统一SSE连接管理

**任务**：
1. 实现前端统一连接管理器
2. 迁移现有SSE连接到统一管理器
3. 测试连接复用、自动重连

**验收标准**：
- ✅ 单一页面最多一个SSE连接
- ✅ 连接自动重连
- ✅ 资源占用减少

---

### 总工作量预估

| 阶段 | 工作量 | 优先级 |
|------|--------|--------|
| 第一阶段 | 3天 | 高 |
| 第二阶段 | 2天 | 中 |
| 第三阶段 | 1天 | 低 |
| 第四阶段 | 2天 | 低 |
| **总计** | **8天** | - |

---

## 六、风险评估

### 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| SSE连接不稳定 | 用户无法实时更新 | 兜底机制：30秒轮询 |
| 服务器压力增加 | 性能下降 | 限制连接数、心跳间隔优化 |
| 多SSE连接资源浪费 | 浏览器性能下降 | 统一连接管理器 |
| 事件推送延迟 | 用户体验下降 | 监控推送延迟、优化队列 |

### 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 用户期望过高 | 误以为即时通讯 | 引导文案：状态更新可能延迟 |
| 通知过多打扰 | 用户反感 | 通知频率限制、用户可关闭 |

---

## 七、监控指标

### 技术指标

| 指标 | 目标 | 监控方式 |
|------|------|---------|
| SSE连接成功率 | >95% | 连接日志 |
| SSE推送延迟 | <1秒 | 时间戳对比 |
| 轮询兜底触发率 | <5% | 兜底事件日志 |
| 连接断开重连成功率 | >99% | 重连日志 |

### 业务指标

| 指标 | 目标 | 监控方式 |
|------|------|---------|
| 关系页面刷新次数减少 | >50% | 用户行为埋点 |
| 验证状态查看延迟降低 | >80% | 用户行为埋点 |
| 用户满意度提升 | >10% | 用户调研 |

---

## 八、总结

### 核心改进

1. **关系页面状态同步**：新增SSE推送，卡片状态自动更新
2. **验证状态变化**：新增SSE推送，实时通知验证结果
3. **导航栏徽章更新**：缩短轮询间隔，提升实时性
4. **聊天"正在输入"**：新增SSE事件，显示输入提示
5. **用户档案更新**：复用SSE推送，自动刷新资料

### 架构优化

- 统一SSE连接管理器
- 兜底机制（轮询）
- 自动重连机制

### 实施优先级

1. **高优先级**：关系页面、验证状态（3天）
2. **中优先级**：导航栏徽章、正在输入（2天）
3. **低优先级**：档案更新、架构优化（3天）

### 总工作量

**预估8天**，分4个阶段实施。

---

## 附录：相关代码文件

### 后端文件

- `/Users/sunmuchao/Downloads/Her/external-systems/sse-server/sse_server/handlers.py`
- `/Users/sunmuchao/Downloads/Her/backend/app/services/matching_service.py`
- `/Users/sunmuchao/Downloads/Her/backend/app/services/verification_service.py`
- `/Users/sunmuchao/Downloads/Her/backend/app/services/profile_service.py`

### 前端文件

- `/Users/sunmuchao/Downloads/Her/frontend/her-app/components/her/relationships-page.tsx`
- `/Users/sunmuchao/Downloads/Her/frontend/her-app/lib/hooks/use-relationships-page-data.ts`
- `/Users/sunmuchao/Downloads/Her/frontend/her-app/hooks/use-badge-counts.ts`
- `/Users/sunmuchao/Downloads/Her/frontend/her-app/components/her/chat-page.tsx`
- `/Users/sunmuchao/Downloads/Her/frontend/her-app/components/her/verification-page.tsx`

### 参考文档

- `/Users/sunmuchao/Downloads/Her/verification-real-time-notification-fix.md`
- `/Users/sunmuchao/Downloads/Her/test-summary-real-time-notification.md`