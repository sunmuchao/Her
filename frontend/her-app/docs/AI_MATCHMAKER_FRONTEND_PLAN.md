# AI红娘主动提示前端接入方案

> **核心理念**: AI Native架构 - AI是决策引擎，而非被动工具

## 一、问题诊断

### 现状分析
- **已接入**: 私信悬浮球（用户主动点击咨询AI红娘）
- **未接入**: AI红娘在聊天前/中/后的主动提示

### 根因
```
问题现象：聊天页面只显示用户对话，缺少AI红娘主动提示
├─ 为什么 1: 前端只加载普通用户消息，未处理agent消息
├─ 为什么 2: 消息类型判断逻辑缺失（source字段）
├─ 为什么 3: timeline API已返回agent消息但前端未解析
└─ 为什么 5: 设计理念偏差 - 把AI红娘当成"被动工具"而非"主动伙伴"

根本对策：重构为AI Native架构，AI红娘主动推送，用户被动接收+确认
```

## 二、技术架构

### 后端API端点（已实现）
```
GET  /v2/chat/cases/{case_id}/timeline              # 获取所有会话消息
POST /v2/chat/conversations/{conv_id}/messages      # 发送消息
GET  /v2/chat/conversations/{conv_id}/messages      # 获取特定会话消息
```

### 消息数据结构
```typescript
type ChatMessage = {
  message_id: number
  author_id: string        // 'user-a' | 'user-b' | 'agent-c'
  source: string           // 'user' | 'agent' | 'system'
  body: string
  created_at: string
}

type Conversation = {
  conversation_id: string
  channel_key: string      // 'main_group' | 'assistant_dm_a' | 'assistant_dm_b'
  conversation_kind: string
  members: Array<{
    participant_id: string
    member_role: string    // 'human' | 'agent'
  }>
}
```

### 会话布局
- **main_group**: 用户公开聊天 + AI红娘主动提示
- **assistant_dm_a**: 用户A与AI红娘私信（已接入）
- **assistant_dm_b**: 用户B与AI红娘私信（已接入）

## 三、前端架构设计

### 1. API接口封装

**新增文件**: `frontend/her-app/lib/api/endpoints/chat-timeline.ts`

```typescript
/**
 * 获取案例timeline（包含AI红娘主动提示）
 */
export async function fetchCaseTimeline(
  caseId: string,
  requesterId: string,
): Promise<CaseTimelineResponse> {
  return gatewayJson<CaseTimelineResponse>(
    `/v2/chat/cases/${caseId}/timeline${queryString({ requester_id: requesterId })}`
  )
}

type CaseTimelineResponse = {
  case_id: string
  conversation_count: number
  conversations: Array<{
    conversation: Conversation
    messages: ChatMessage[]
  }>
}
```

### 2. 消息处理逻辑

**修改文件**: `frontend/her-app/components/her/chat-page.tsx`

**关键改动**:
1. 加载timeline而非单一会话
2. 根据`source`字段区分消息类型
3. 合并展示main_group中的用户消息和agent消息

```typescript
// 现在的逻辑（错误）
const messages = messageData.messages.map(msg => ({
  type: msg.author_id === requesterId ? 'sent' : 'received',  // ❌ 只判断用户
  content: msg.body,
}))

// 应该的逻辑（正确）
const messages = conversationData.messages.map(msg => {
  const isAI = msg.source === 'agent'  // ✅ 区分AI红娘
  const isMe = msg.author_id === requesterId

  return {
    type: isAI ? 'assistant' : (isMe ? 'sent' : 'received'),
    content: msg.body,
    timestamp: msg.created_at,
    authorId: msg.author_id,
    source: msg.source,  // ✅ 保留来源信息
  }
})
```

### 3. UI展示设计

**AI Native理念**: AI红娘提示应**主动推送**，而非被动等待点击

#### 3.1 消息展示层

```typescript
// 消息类型扩展
type Message = {
  id: string
  type: 'sent' | 'received' | 'assistant'  // ✅ 新增assistant类型
  content: string
  timestamp: string
  authorId?: string
  source?: 'user' | 'agent'
}

// 消息样式区分
<div className={cn(
  'px-3.5 py-2.5 rounded-2xl text-sm',
  msg.type === 'assistant'
    ? 'bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-2xl'  // AI红娘特殊样式
    : msg.type === 'sent'
    ? 'bg-primary text-primary-foreground rounded-br-md'
    : 'bg-card border border-border rounded-bl-md'
)}>
  {msg.content}
  {msg.type === 'assistant' && (
    <div className="flex items-center gap-1 mt-1 text-xs text-purple-600">
      <Sparkles className="w-3 h-3" />
      <span>小雅的建议</span>
    </div>
  )}
</div>
```

#### 3.2 AI红娘头像处理

```typescript
// AI红娘头像（紫色渐变背景）
{msg.type === 'assistant' && (
  <div className="w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-purple-400 to-blue-400 flex-shrink-0">
    <Image
      src="/xiaoya-avatar.png"
      alt="小雅"
      width={32}
      height={32}
      className="object-cover"
    />
  </div>
)}
```

### 4. 实时更新机制

#### 方案A: 轮询（推荐用于MVP）
```typescript
// 每30秒轮询timeline更新
useEffect(() => {
  if (!resolvedCaseId) return

  const interval = setInterval(async () => {
    const timeline = await fetchCaseTimeline(resolvedCaseId, requesterId)
    const mainGroup = timeline.conversations.find(
      c => c.conversation.channel_key === 'main_group'
    )

    if (mainGroup && mainGroup.messages.length > messages.length) {
      setMessages(mapMessages(mainGroup.messages, requesterId))
    }
  }, 30000)  // 30秒轮询

  return () => clearInterval(interval)
}, [resolvedCaseId, requesterId])
```

#### 方案B: WebSocket（长期方案）
```typescript
// 监听新消息事件
const socket = new WebSocket(`wss://gateway/v2/chat/cases/${caseId}/stream`)
socket.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.type === 'new_message') {
    setMessages(prev => [...prev, mapMessage(msg.data)])
  }
}
```

### 5. AI Native交互设计

#### 5.1 主动推送时机（由后端AI决策）

| 场景 | trigger | AI红娘行为 | 前端展示 |
|------|---------|-----------|---------|
| **聊天前** | `opening_probe` | 主动开场引导 | 在main_group显示引导消息 |
| **聊天中** | `silence_probe` | 沉默5分钟后提示 | 在main_group显示破冰建议 |
| **聊天后** | `post_chat_followup` | 聊天结束2小时后跟进 | 在assistant_dm私信询问 |

#### 5.2 用户交互模式

**传统模式（❌ 错误）**:
- 用户主动点击悬浮球 → 输入问题 → AI回答
- AI是被动工具，等待用户触发

**AI Native模式（✅ 正确）**:
- AI主动推送提示 → 用户被动看到 → 可选择回复/忽略
- AI是主动伙伴，用户是审批者

#### 5.3 提示卡片设计

```typescript
// AI红娘提示卡片（可交互）
<div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-xl p-3">
  <div className="flex items-start gap-2">
    <Sparkles className="w-4 h-4 text-purple-500 mt-1" />
    <div className="flex-1">
      <p className="text-sm text-purple-900">{msg.content}</p>
      {/* 可交互按钮 */}
      <div className="flex gap-2 mt-2">
        <button
          onClick={() => handleApplySuggestion(msg.suggestion_id)}
          className="text-xs px-2 py-1 bg-purple-100 hover:bg-purple-200 rounded-md"
        >
          按建议调整
        </button>
        <button
          onClick={() => handleDismiss(msg.id)}
          className="text-xs px-2 py-1 text-purple-600 hover:bg-purple-50 rounded-md"
        >
          稍后再说
        </button>
      </div>
    </div>
  </div>
</div>
```

## 四、实施路径

### Phase 1: 基础接入（MVP）
1. ✅ 新增 `fetchCaseTimeline` API封装
2. ✅ 修改 chat-page.tsx 加载timeline而非单一会话
3. ✅ 根据 `source` 字段区分消息类型
4. ✅ 为assistant消息添加特殊样式
5. ✅ 实现30秒轮询更新

### Phase 2: 交互增强
1. ✅ AI提示卡片可交互（采纳/忽略）
2. ✅ 悬浮球改为未读提示指示器
3. ✅ 新消息气泡动画提示
4. ✅ 消息分类展示（用户对话 vs AI建议）

### Phase 3: 实时推送
1. ✅ WebSocket长连接
2. ✅ 实时消息推送
3. ✅ 离线消息缓存
4. ✅ 消息同步状态指示

## 五、关键代码示例

### 完整的chat-page.tsx改造（核心部分）

```typescript
// 1. 加载timeline而非单一会话
const loadCaseTimeline = async () => {
  const timeline = await fetchCaseTimeline(resolvedCaseId, requesterId)

  // 找到main_group会话
  const mainGroup = timeline.conversations.find(
    c => c.conversation.channel_key === 'main_group'
  )

  if (mainGroup) {
    // ✅ 区分用户消息和AI红娘消息
    const mappedMessages = mainGroup.messages.map(msg => ({
      id: String(msg.message_id),
      type: msg.source === 'agent' ? 'assistant'
           : msg.author_id === requesterId ? 'sent' : 'received',
      content: msg.body,
      timestamp: msg.created_at,
      authorId: msg.author_id,
      source: msg.source,
    }))
    setMessages(mappedMessages)
  }
}

// 2. 渲染消息列表
{messages.map((msg, index) => (
  <div key={msg.id} className={cn(
    'flex',
    msg.type === 'assistant' ? 'justify-center'  // AI居中显示
    : msg.type === 'sent' ? 'justify-end'
    : 'justify-start'
  )}>
    {/* AI红娘特殊样式 */}
    {msg.type === 'assistant' && (
      <div className="max-w-[85%] bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-xl p-3">
        <div className="flex items-center gap-2 mb-1">
          <Image src="/xiaoya-avatar.png" alt="小雅" width={20} height={20} />
          <span className="text-xs text-purple-600 font-medium">小雅的建议</span>
        </div>
        <p className="text-sm text-purple-900">{msg.content}</p>
      </div>
    )}

    {/* 用户消息保持原样 */}
    {msg.type !== 'assistant' && (
      <div className={cn(
        'max-w-[75%] px-3.5 py-2.5 rounded-2xl',
        msg.type === 'sent'
          ? 'bg-primary text-primary-foreground'
          : 'bg-card border border-border'
      )}>
        {msg.content}
      </div>
    )}
  </div>
))}
```

## 六、AI Native架构对比

| 维度 | 当前设计（错误） | AI Native设计（正确） |
|------|----------------|---------------------|
| **交互范式** | 用户点击 → AI回答 | AI主动推送 → 用户确认 |
| **AI角色** | 被动工具 | 主动伙伴 |
| **触发时机** | 用户手动触发 | AI根据context自动决策 |
| **消息展示** | 与用户消息混在一起 | 独立卡片，明确标识 |
| **用户角色** | 执行者 | 审批者 |
| **价值主张** | 辅助工具 | 智能助手 |

## 七、测试验收标准

### 功能测试
- ✅ 聊天页面能显示AI红娘的主动提示
- ✅ AI消息与用户消息样式区分明显
- ✅ 30秒轮询能获取新消息
- ✅ 悬浮球显示AI红娘未读消息数量

### UX测试
- ✅ AI提示不打断用户聊天流程
- ✅ 用户可选择采纳或忽略AI建议
- ✅ AI提示时机符合对话节奏（聊天前/中/后）

### 架构测试
- ✅ 消息类型判断基于`source`字段而非`author_id`
- ✅ timeline API作为数据来源而非单一会话API
- ✅ 符合AI Native三层分离架构

## 八、后续优化方向

1. **Generative UI**: AI提示卡片由AI动态生成样式和交互
2. **情境感知**: AI根据聊天内容实时调整提示策略
3. **个性化**: AI学习用户偏好，定制提示风格
4. **多模态**: 支持语音、图片等多种提示形式