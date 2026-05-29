# 小雅主动提示前端实现方案

## 概述

小雅作为AI红娘助手，需要在用户聊天的不同阶段主动提供帮助。小雅会根据场景同时发送**公共消息**（群里，双方可见）和**私信**（只有用户可见）两种类型的消息。

---

## 消息类型说明

### 公共消息（main_group）

- **谁能看到**：双方都能看到
- **显示位置**：聊天消息流中，紫色卡片居中显示
- **用途**：公开的建议、破冰提示、欢迎引导

### 私信（assistant_dm）

- **谁能看到**：只有用户自己看到
- **显示位置**：小雅私信面板（输入框上方）
- **用途**：个性化建议、私密指导、复盘跟进

---

## 三阶段消息发送规则

| 阶段 | 公共消息（main_group） | 私信（assistant_dm） | 触发时机 |
|------|----------------------|---------------------|---------|
| **聊天前** | ✓ 发送欢迎引导 | ✓ 发送私信建议 | 匹配成功后5分钟 |
| **聊天中** | ✓ 发送破冰提示 | ✓ 发送详细指导 | 双方沉默超5分钟 |
| **聊天后** | - 不发送 | ✓ 发送复盘跟进 | 聊天结束2小时 |

---

## 阶段一：聊天前（匹配成功）

### 触发时机

匹配成功后5分钟，后端同时发送：
- `opening_probe` → `main_group`（公共消息）
- `opening_probe_dm` → `assistant_dm`（私信）

### 公共消息效果（已实现）

```
┌─────────────────────────────────────┐
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 💡 小雅的建议                    │ │ ← 紫色卡片，双方可见
│ │ "你们刚匹配成功，可以先从       │ │
│ │   共同的兴趣爱好聊起～"         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ 对方: 你周末一般做什么？            │
│                                     │
│ 我: 我喜欢跑步和看书～              │
│                                     │
└─────────────────────────────────────┘
```

### 私信效果（待实现自动弹出）

如果小雅同时发了私信，前端应该自动展开小雅私信面板：

```
┌─────────────────────────────────────┐
│ 对方: 你周末一般做什么？            │
│                                     │
├─────────────────────────────────────┤
│ ░░░ 小雅私信面板（自动弹出）░░░░   │
│ ┌─────────────────────────────────┐ │
│ │ 🤖 小雅 · 私信助手      [X]     │ │ ← 只有用户可见
│ │ ─────────────────────────────── │ │
│ │ "我看了你们资料，              │ │
│ │  你们都喜欢运动，可以聊聊      │ │
│ │  平常去哪跑步～"               │ │
│ │ ─────────────────────────────── │ │
│ │ [跟小雅说点悄悄话...    ] [➤]  │ │
│ └─────────────────────────────────┘ │
├─────────────────────────────────────┤
│ [+] [🎤] [输入消息...        ] [➤] │
└─────────────────────────────────────┘
```

### 实现要点

- 公共消息：已在聊天流显示 ✓
- 私信：需检测 `assistant_dm` 新消息，自动展开面板

---

## 阶段二：聊天中（沉默破冰）

### 触发时机

双方沉默超5分钟，后端同时发送：
- `silence_probe` → `main_group`（公共消息）
- `silence_probe_dm` → `assistant_dm`（私信）

### 公共消息效果（已实现）

```
┌─────────────────────────────────────┐
│ 对方: 你周末一般做什么？            │
│                                     │
│ 我: 我喜欢跑步和看书～              │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 💡 小雅的建议                    │ │ ← 紫色卡片，双方可见
│ │ "对方提到喜欢跑步，            │ │
│ │  你可以问问跑多远？"           │ │
│ └─────────────────────────────────┘ │
│                                     │
└─────────────────────────────────────┘
```

### 私信效果（待实现自动弹出）

```
┌─────────────────────────────────────┤
│ ░░░ 小雅私信面板（自动弹出）░░░░   │
│ ┌─────────────────────────────────┐ │
│ │ 🤖 小雅 · 私信助手      [X]     │ │ ← 只有用户可见
│ │ ─────────────────────────────── │ │
│ │ "看你们聊到跑步了，            │ │
│ │  我有个小技巧：可以问问        │ │
│ │  他最喜欢的跑步路线，          │ │
│ │  这样话题能聊得更深～"         │ │
│ │ ─────────────────────────────── │ │
│ │ [跟小雅说点悄悄话...    ] [➤]  │ │
│ └─────────────────────────────────┘ │
├─────────────────────────────────────┤
│ [+] [🎤] [输入消息...        ] [➤] │
└─────────────────────────────────────┘
```

### 为什么同时发两种消息？

| 类型 | 内容特点 | 作用 |
|------|---------|------|
| **公共消息** | 简短、直接的建议 | 让双方都知道怎么继续聊 |
| **私信** | 更详细、个性化的指导 | 给用户私密的建议技巧 |

---

## 阶段三：聊天后（复盘跟进）

### 触发时机

聊天结束（双方沉默超2小时），后端发送：
- `post_chat_followup` → `assistant_dm`（私信）

### 为什么不发公共消息？

聊天后用户已经离开聊天页，发公共消息用户可能看不到，所以只发私信。

### 显示位置

不在聊天页显示，而是在**关系页**的匹配卡片上：

```
┌─────────────────────────────────────┐
│ 关系                                │
├─────────────────────────────────────┤
│ 正在进行中 (3位)                    │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ [头像] 小红 · 已开聊            │ │
│ │        昨天聊得挺开心的～        │ │
│ │                                 │ │
│ │        [🤖 小雅复盘] 🔴         │ │ ← 点击展开复盘对话
│ └─────────────────────────────────┘ │
│                                     │
└─────────────────────────────────────┘
```

---

### 前端实现要点

#### 1. 关系页数据结构扩展

```typescript
type ActiveRelationship = {
  id: string
  caseId: string
  name: string
  // ...现有字段
  hasXiaoyaUnread: boolean        // 小雅是否有未读私信
  xiaoyaConversationId?: string   // 小雅会话ID
  xiaoyaLastMessage?: string      // 小雅最新私信内容
}
```

#### 2. 加载时检测小雅私信

```typescript
// 在 loadCases 中添加
const timelines = await Promise.allSettled(
  activeCaseIds.map(async (caseId) => {
    const data = await fetchCaseConversationTimeline(caseId, userId)

    // 检测 assistant_dm 会话
    const assistantDm = data.conversations.find(
      c => c.conversation.channel_key === 'assistant_dm'
    )

    return {
      caseId,
      mainMessages: data.conversations.find(c => c.conversation.channel_key === 'main_group')?.messages,
      xiaoyaMessages: assistantDm?.messages || [],
      xiaoyaConversationId: assistantDm?.conversation?.conversation_id,
    }
  })
)

// 提取小雅未读状态
const xiaoyaUnreadByCaseId: Record<string, {
  hasUnread: boolean
  conversationId: string
  lastMessage: string
}> = {}

timelines.forEach((result) => {
  if (result.status === 'fulfilled') {
    const { caseId, xiaoyaMessages, xiaoyaConversationId } = result.value
    if (xiaoyaMessages.length > 0 && xiaoyaConversationId) {
      const lastMsg = xiaoyaMessages[xiaoyaMessages.length - 1]
      xiaoyaUnreadByCaseId[caseId] = {
        hasUnread: true, // 可根据已读标记判断
        conversationId: xiaoyaConversationId,
        lastMessage: lastMsg.body,
      }
    }
  }
})
```

#### 3. 关系卡片UI改动

```tsx
// 在关系卡片中添加小雅入口
<div className="flex items-center gap-2 mt-2">
  {/* 小雅复盘入口 */}
  {rel.hasXiaoyaUnread && (
    <button
      onClick={() => openXiaoyaReview(rel.caseId, rel.xiaoyaConversationId)}
      className="flex items-center gap-1 px-2 py-1 rounded-full bg-purple-100 text-purple-600 text-xs"
    >
      <Image src="/xiaoya-avatar.png" alt="小雅" width={16} height={16} />
      <span>小雅复盘</span>
      {rel.hasXiaoyaUnread && (
        <span className="w-2 h-2 rounded-full bg-rose" /> // 红点
      )}
    </button>
  )}
</div>
```

#### 4. 小雅复盘面板组件

```tsx
// 可复用聊天页的小雅私信面板组件
function XiaoyaReviewPanel({
  caseId,
  conversationId,
  onClose
}) {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')

  // 加载私信历史
  useEffect(() => {
    fetchPrivateMessages(conversationId).then(setMessages)
  }, [conversationId])

  return (
    <div className="bg-gradient-to-r from-purple-50/50 to-blue-50/50 rounded-xl p-3 mt-2">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Image src="/xiaoya-avatar.png" alt="小雅" width={24} height={24} />
          <span className="text-sm font-medium text-purple-700">小雅 · 复盘助手</span>
        </div>
        <button onClick={onClose}>✕</button>
      </div>

      {/* 消息列表 */}
      <div className="max-h-[120px] overflow-y-auto">
        {messages.slice(-3).map(msg => (
          <div key={msg.id} className={msg.isFromMe ? 'text-right' : 'text-left'}>
            <span className="inline-block px-2 py-1 rounded text-xs bg-secondary">
              {msg.body}
            </span>
          </div>
        ))}
      </div>

      {/* 输入框 */}
      <input
        value={inputValue}
        onChange={setInputValue}
        placeholder="跟小雅聊聊这次相亲..."
        className="w-full bg-white/60 rounded-lg px-3 py-2 text-xs mt-2"
      />
    </div>
  )
}
```

---

## 数据流总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           后端触发时机                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  匹配成功后5分钟                                                    │
│  ├─ opening_probe → main_group                                     │
│  └─ 前端：聊天流显示紫色卡片（已实现）                               │
│                                                                     │
│  双方沉默超5分钟                                                    │
│  ├─ silence_probe → assistant_dm                                   │
│  └─ 前端：检测新私信 → 自动展开面板（待实现）                        │
│                                                                     │
│  聊天结束2小时                                                      │
│  ├─ post_chat_followup → assistant_dm                               │
│  └─ 前端：关系页显示小雅入口+红点（待实现）                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 实现优先级

| 优先级 | 任务 | 复杂度 | 依赖 | 状态 |
|--------|------|--------|------|------|
| P0 | 聊天中：检测 assistant_dm 新消息自动展开面板 | 中 | 后端 silence_probe | ✅ 已完成 |
| P1 | 聊天后：关系页添加小雅复盘入口 | 中 | 后端 post_chat_followup | ✅ 已完成 |
| P2 | 聊天中：前端沉默检测补充机制 | 低 | 无 | 待实现 |

---

## 技术要点

### 1. 轮询优化

- 30秒轮询检测新消息
- 只在聊天页活跃时轮询
- 使用 `lastCheckTimeRef` 避免重复触发

### 2. 面板状态管理

- `showXiaoyaChat`: 控制面板展开/收起
- `xiaoyaTriggerReason`: 记录触发原因（用于展示不同提示）
- `xiaoyaMessages`: 私信消息列表
- `xiaoyaConversationId`: 会话ID

### 3. 组件复用

- 聊天页的小雅私信面板组件可复用于关系页
- 样式统一：紫色渐变背景、紧凑布局

### 4. 性能考虑

- 关系页加载时限制并发请求（最多10个case）
- 小雅私信面板只显示最近3条消息
- 使用乐观更新发送消息

---

## 相关文件

| 文件 | 改动内容 |
|------|---------|
| `chat-page.tsx` | 添加 assistant_dm 检测 + 自动展开逻辑 |
| `relationships-page.tsx` | 添加小雅复盘入口 + 面板组件 |
| `chat-timeline.ts` | timeline API 返回 assistant_dm 会话数据 |
| `chat.ts` | 私信API（fetchPrivateMessages, sendPrivateMessage） |