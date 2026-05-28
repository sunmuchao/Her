# 推荐与撮合边界修复方案

> 版本：v1.0
> 创建时间：2026-05-28
> 状态：实施中

---

## 1. 问题背景

### 1.1 发现的问题

用户反馈：点击"愿意认识"后，对方的信息应该显示在"推荐来信"中，但实际显示在了"关系页 - 牵线中"。

经过分析，发现两个层面的问题：

1. **数据层 Bug**：发给被请求方（B）的消息内容是 B 自己的信息，应该是发起方（A）的信息
2. **流程层设计问题**：单向意愿表达后直接进入撮合流程，跳过了"推给对方看"步骤

### 1.2 问题定位

从代码 [proxy_intro_core.py:627-632](external-systems/partner-matchmaking-system/matchmaking_system/proxy_intro_core.py#L627-L632) 分析：

```python
# 当前代码（问题）
safe_summary = build_safe_summary(subscription, recommendation)  # recommendation 是 B
outreach_payload = build_outreach_payload(subscription, safe_summary)
# 发给 B 的消息内容是 B 的年龄、城市...
```

**根本原因**：
- `build_safe_summary` 从 `recommendation`（B 的推荐记录）提取信息
- `recommendation` 存储的是被推荐方（B）的信息
- 应该从 `subscription`（A 的订阅）提取 A 的信息

---

## 2. 设计方案

### 2.1 核心定义修正

**推荐** = 单向推送（系统推给你看，或有人想认识你）

**撮合** = 双向意愿确认后才建立关系

### 2.2 正确的流程

```
A 在推荐来信看到 B
    ↓
A 点击"愿意认识"
    ↓
系统把 A 的信息作为"被动推荐"推送给 B
    ↓
B 在"推荐来信 - 有人想认识你"看到 A
    ↓
B 点击进入 A 的详情页
    ↓
B 点击"愿意认识" 或 "暂不考虑"
    ↓
如果双方都愿意 → 创建 ProxyIntroCase → 开聊
```

### 2.3 与现有设计文档的关系

本方案补充 [mutual-intent-and-proxy-intro-flow.md](mutual-intent-and-proxy-intro-flow.md) 中定义的整体流程，重点修复：

- 数据层的具体 bug
- 新增"被动推荐卡片"机制
- 前端交互的具体调整

---

## 3. 实施方案

### Phase 1: 数据层修复（优先级高）

**目标**：发给 B 的消息内容应该是 A 的信息

**修改文件**：`proxy_intro_core.py`

**新增函数**：

```python
def build_requester_safe_summary(subscription: dict[str, Any]) -> dict[str, Any]:
    """构建发起方（requester）的信息摘要，用于发送给被请求方。"""
    self_profile = json_loads(subscription.get("self_profile_json"), {})

    safe_summary = {
        "requester_name": self_profile.get("display_name") or self_profile.get("name") or "有人",
        "age_bracket": _age_bracket(self_profile.get("age")),
        "city": self_profile.get("city") or self_profile.get("settlement_city"),
        "height_bracket": _height_bracket(self_profile.get("height")),
        "education": self_profile.get("education"),
        "occupation": self_profile.get("job") or self_profile.get("occupation"),
        "relationship_goal": self_profile.get("relationship_goal"),
        "matched_on": [],
        "subscription_title": subscription.get("title"),
    }

    safe_summary["summary_text"] = "；".join(
        part for part in [
            safe_summary["age_bracket"],
            safe_summary["city"],
            safe_summary["education"],
            safe_summary["occupation"],
            safe_summary["relationship_goal"],
        ] if part
    )
    return safe_summary
```

**修改 `create_match_case` 函数**：

```python
# 修改后的调用
requester_summary = build_requester_safe_summary(subscription)
outreach_payload = build_outreach_payload_from_requester(
    requester_summary,
    outreach_channel=outreach_channel,
)
```

---

### Phase 2: 新增被动推荐机制

**目标**：A 表达意愿后，创建被动推荐卡片推送给 B

**新增数据表**：`requester_interest_cards`

```sql
CREATE TABLE requester_interest_cards (
    card_id TEXT PRIMARY KEY,
    requester_id INTEGER NOT NULL,
    requester_subscription_id TEXT,
    target_profile_id INTEGER NOT NULL,
    requester_summary_json TEXT,
    card_status TEXT DEFAULT 'unread',
    reply_type TEXT,
    created_at TEXT,
    read_at TEXT,
    replied_at TEXT,
    expires_at TEXT
);
```

**新增 API**：

- `POST /v1/requester-interest/cards` - 创建卡片
- `GET /v1/requester-interest/cards` - 查询卡片
- `POST /v1/requester-interest/cards/{card_id}/reply` - 回复卡片

---

### Phase 3: 前端交互调整

**目标**：B 在"推荐来信"中看到 A 的信息

**修改文件**：`discover-page.tsx`

**新增 tab**：

```typescript
const tabs = [
    { id: 'all', label: '全部' },
    { id: 'delayed', label: '延迟推荐' },
    { id: 'matched', label: '主动撮合' },
    { id: 'interest', label: '有人想认识你' },  // 新增
];
```

**新增组件**：`RequesterInterestCard.tsx`

---

### Phase 4: 状态流转调整

**目标**：推荐记录状态增加"被动推荐"阶段

**新增状态**：

```python
delivery_status: pending → delivered → viewed → interest_sent → mutual_accepted
```

- `interest_sent`：A 已表达意愿，卡片已推送给 B
- `mutual_accepted`：双方都愿意，进入撮合

**新增动作类型**：

```python
action_types = [
    "view",
    "skip",
    "save",
    "request_intro",
    "interest_sent",
    "reply_accepted",
    "reply_declined",
]
```

---

## 4. 实施进度

| Phase | 状态 | 说明 |
|-------|------|------|
| Phase 1: 数据层修复 | ✅ 已完成 | outreach_payload 包含 requester 信息 |
| Phase 2: 被动推荐机制 | ✅ 已完成 | 简化方案：直接使用 ProxyIntroCase 在推荐来信显示 |
| Phase 3: 前端交互调整 | ✅ 已完成 | 推荐来信增加"有人想认识你"tab |
| Phase 4: 状态流转调整 | ✅ 已完成 | 被动推荐卡片支持回复操作 |
| 测试验证 | ✅ 已完成 | 后端测试通过，前端 lint 通过 |

---

## 5. 实际修改的文件

### 后端文件

| 文件 | 修改内容 |
|------|---------|
| `proxy_intro_core.py` | 新增 `build_requester_safe_summary` 和 `build_outreach_payload_from_requester` 函数 |
| `proxy_intro_core.py` | 修改 `create_match_case` 函数，使用新函数构建 outreach_payload |

### 前端文件

| 文件 | 修改内容 |
|------|---------|
| `use-recommendation-inbox.ts` | 新增 `interest` 类型，加载 ProxyIntroCase 作为被动推荐 |
| `discover-page.tsx` | 新增"有人想认识你" tab，被动推荐卡片显示操作按钮 |
| `proxy-intro.ts` | 扩展 `ProxyIntroCase` 类型定义，增加 outreach_payload 字段 |

---

## 6. 简化方案说明

原方案设计新增 `requester_interest_cards` 数据表，实际实施时采用简化方案：

**简化方案**：
- 直接使用现有的 `ProxyIntroCase` 数据结构
- 将 `role === 'candidate'` 且 `case_status === 'awaiting_reply'` 的 case 在推荐来信中显示
- 修改前端 hook 加载这些 case 并合并到推荐列表
- 被动推荐卡片显示"愿意认识"和"暂不考虑"按钮，点击后调用 `replyProxyIntroCase` API

**优点**：
- 不需要新增数据表
- 不需要新增 API
- 复用现有的 ProxyIntro 状态流转机制
- 实施更快速

---

## 7. 验收标准

1. ✅ A 点击"愿意认识"后，outreach_payload 包含 A 的信息（而非 B 的信息）
2. ✅ B 在"推荐来信"中可以看到"有人想认识你" tab
3. ✅ B 可以看到发起方（A）的基本信息（年龄、城市、职业等）
4. ✅ B 可以点击"愿意认识"或"暂不考虑"按钮
5. ✅ 后端测试通过
6. ✅ 前端 lint 通过

---

## 6. 相关文档

- [mutual-intent-and-proxy-intro-flow.md](mutual-intent-and-proxy-intro-flow.md) - 整体流程设计
- [SYSTEM_DOC.md](SYSTEM_DOC.md) - 系统架构文档