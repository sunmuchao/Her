# 推荐来信体验优化完整解决方案

> 针对"点击愿意认识后"流程中的三个核心问题，给出完整的技术解决方案。

---

## 问题概述

| 问题 | 现状 | 影响 |
|------|------|------|
| 1. 卡片不可点击 | B 只能看摘要，看不到 A 的完整资料 | 决策信息不足，降低匹配成功率 |
| 2. 双向同时发起 | 系统不检测双向匹配，创建两个独立案件 | 可能造成重复案件，流程混乱 |
| 3. 流程割裂 | 点愿意认识后需手动去关系页开聊 | 用户体验中断，操作繁琐 |

---

## 问题 1：推荐来信卡片可点击查看完整信息

### 方案设计

**核心思路**：让 interest 类型卡片可点击，进入候选人详情页，详情页底部按钮改为案件回复操作。

### 前端改动

#### 文件 1：`discover-page.tsx`

**改动位置**：第 491-512 行

**改动内容**：

```tsx
// BEFORE：interest 卡片不可点击
onClick={() => {
  if (item.type !== 'interest') {  // ← 排除 interest
    void markRead(item)
    onViewCandidate(item.id, {...})
  }
}

// AFTER：interest 卡片也可点击，传递案件信息
onClick={() => {
  void markRead(item)
  onViewCandidate(item.id, {
    ...item,
    // 新增：传递案件信息，让详情页知道这是"有人想认识你"场景
    caseId: item.caseId,           // 案件 ID
    caseStatus: item.caseStatus,   // 案件状态（awaiting_reply）
    viewType: item.type,           // 'interest' 表示被动推荐
  })
}
```

**同时修改 CSS 类**：

```tsx
// BEFORE：interest 卡片没有 hover 效果
className={`... ${item.type !== 'interest' ? 'cursor-pointer hover:border-primary/30' : ''}`}

// AFTER：所有卡片都有 hover 效果
className={`... cursor-pointer hover:border-primary/30`}
```

**删除卡片上的操作按钮**（移到详情页）：

```tsx
// 删除第 547-571 行的 interest 卡片按钮区域
// 保留其他类型卡片的"跳过"、"收藏"按钮
```

---

#### 文件 2：`candidate-detail-page.tsx`

**改动位置**：第 262-290 行（handleExpressInterest 函数）

**新增逻辑**：根据 `viewType` 和 `caseId` 判断是"主动发起"还是"回复案件"

```tsx
const handleExpressInterest = async () => {
  if (isExpressingInterest) return

  // 新增：判断是否是回复案件场景
  if (viewType === 'interest' && caseId) {
    // 场景：有人想认识你 → 点击愿意认识 = 回复案件
    setIsExpressingInterest(true)
    try {
      await replyProxyIntroCase({
        caseId,
        replyType: 'accepted',
        source: 'candidate_detail_reply',
      })
      setShowSubmittedHint(true)
      // 问题3方案：自动开聊（见下方）
    } catch (error) {
      notifyError(error, '接受失败，请稍后重试')
    } finally {
      setIsExpressingInterest(false)
    }
    return
  }

  // 原有逻辑：主动发起认识请求
  if (!candidateData.id) {
    notifyError(new Error('interest_unavailable'), '当前候选人暂时无法发起认识')
    return
  }
  setIsExpressingInterest(true)
  try {
    if (subscriptionId) {
      await createProxyIntroRequest({
        subscriptionId,
        candidateId: Number(candidateData.id),
        source: 'candidate_detail',
      })
    } else if (sessionId) {
      await expressDiscoveryCandidateInterest({
        sessionId,
        candidateId: candidateData.id,
      })
    } else {
      throw new Error('interest_unavailable')
    }
    setShowSubmittedHint(true)
  } catch (error) {
    notifyError(error, '发起意愿失败，请稍后重试')
  } finally {
    setIsExpressingInterest(false)
  }
}
```

**新增 Props 定义**：

```tsx
interface CandidateDetailPageProps {
  // ... 原有 props
  caseId?: string           // 新增：案件 ID（被动推荐场景）
  caseStatus?: string       // 新增：案件状态
  viewType?: 'interest' | 'delayed' | 'matched' | 'candidate'  // 新增：卡片类型
}
```

**按钮文案调整**：

```tsx
// 根据场景显示不同文案
const buttonText = viewType === 'interest'
  ? '愿意认识'           // 被动推荐：回复案件
  : '愿意认识TA'         // 主动发起：创建请求
```

---

### 数据流变化

```
BEFORE：
推荐来信卡片 → 点不了 → 只能看摘要 → 直接在卡片上点"愿意认识"

AFTER：
推荐来信卡片 → 点击进入 → 候选人详情页 → 看完整资料 → 点"愿意认识"（回复案件）
```

---

## 问题 2：双向匹配检测逻辑

### 方案设计

**核心思路**：在 `create_match_case` 时检查是否存在反向案件，若双向匹配则直接开聊。

### 后端改动

#### 文件：`proxy_intro_core.py`

**改动位置**：第 665-707 行（create_match_case 函数开头）

**新增函数**：检查反向案件

```python
def get_reverse_pending_case(
    case_conn,
    requester_profile_ref: str,
    candidate_profile_ref: str,
) -> dict[str, Any] | None:
    """
    检查是否存在反向案件（candidate → requester）

    Args:
        requester_profile_ref: 发起方 A 的 profile_ref
        candidate_profile_ref: 被请求方 B 的 profile_ref

    Returns:
        若存在 B→A 的案件且状态为 awaiting_reply，返回该案件；否则返回 None
    """
    reverse_case = case_conn.execute(
        f"""
        SELECT * FROM {_t().cases}
        WHERE requester_profile_ref = ?
          AND candidate_profile_ref = ?
          AND case_status = 'awaiting_reply'
        LIMIT 1
        """,
        (candidate_profile_ref, requester_profile_ref),
    ).fetchone()
    return dict(reverse_case) if reverse_case else None
```

**新增函数**：处理双向匹配

```python
def handle_mutual_match(
    case_conn,
    recommendation_conn=None,
    *,
    forward_case: dict[str, Any],    # A→B 刚创建的案件
    reverse_case: dict[str, Any],    # B→A 已存在的案件
    now: datetime,
) -> dict[str, Any]:
    """
    处理双向匹配：两个案件都接受，直接创建对话

    流程：
    1. 更新 forward_case 状态为 accepted
    2. 更新 reverse_case 状态为 accepted
    3. 创建对话（调用 create_assistant_case_layout）
    4. 关闭两个案件
    5. 更新关系状态为 matched

    Returns:
        包含 conversation_id 和两个 case_id 的结果
    """
    _, rec_conn = _pair(case_conn, recommendation_conn)

    # 1. 更新 forward_case (A→B) 为 accepted
    _update_case_status(
        case_conn,
        recommendation_conn=rec_conn,
        case=forward_case,
        new_status="accepted",
        now=now,
        event_type="mutual_match_auto_accepted",
        actor_type="system",
        active_match_case_id=forward_case["case_id"],
        active_case_status="accepted",
    )

    # 2. 更新 reverse_case (B→A) 为 accepted
    _update_case_status(
        case_conn,
        recommendation_conn=rec_conn,
        case=reverse_case,
        new_status="accepted",
        now=now,
        event_type="mutual_match_auto_accepted",
        actor_type="system",
        active_match_case_id=reverse_case["case_id"],
        active_case_status="accepted",
    )

    # 3. 创建对话（需要导入 create_assistant_case_layout）
    # 注：这里需要跨服务调用，建议通过事件驱动或直接调用
    from chat_system.conversations import create_assistant_case_layout

    conversation_result = create_assistant_case_layout(
        # 参数：双方的 profile 信息
        profile_a=forward_case["requester_profile_ref"],
        profile_b=forward_case["candidate_profile_ref"],
        case_id=forward_case["case_id"],  # 使用 forward_case 作为主案件
        now=now,
    )

    # 4. 关闭两个案件
    close_match_case(
        case_conn,
        recommendation_conn=rec_conn,
        case_id=forward_case["case_id"],
        close_reason="mutual_match_handoff",
        now=now,
    )
    close_match_case(
        case_conn,
        recommendation_conn=rec_conn,
        case_id=reverse_case["case_id"],
        close_reason="mutual_match_handoff",
        now=now,
    )

    # 5. 更新关系状态（需要调用 relationship_ledger 服务）
    # ...

    return {
        "status": "mutual_match",
        "forward_case_id": forward_case["case_id"],
        "reverse_case_id": reverse_case["case_id"],
        "conversation_id": conversation_result.get("main_conversation_id"),
    }
```

**修改 create_match_case 函数**：

```python
def create_match_case(
    case_conn,
    *,
    subscription_id: str,
    candidate_id: int,
    now: datetime | None = None,
    # ... 其他参数
) -> dict[str, Any]:
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)

    # ... 原有的 subscription 和 recommendation 查询 ...

    # ===== 新增：双向匹配检测 =====
    requester_profile_ref = subscription.get("self_id")  # A 的 profile_ref
    candidate_profile_ref = recommendation.get("candidate_profile_ref")  # B 的 profile_ref

    reverse_case = get_reverse_pending_case(
        case_conn,
        requester_profile_ref,
        candidate_profile_ref,
    )

    if reverse_case:
        # 双向匹配！直接处理
        # 先创建 forward_case（但状态直接设为 accepted，跳过 outreach）
        case_id = generate_case_id()
        # ... 创建案件记录，状态直接为 accepted ...

        # 调用双向匹配处理函数
        result = handle_mutual_match(
            case_conn,
            recommendation_conn=rec_conn,
            forward_case={"case_id": case_id, ...},
            reverse_case=reverse_case,
            now=now,
        )
        return result  # 返回 mutual_match 结果，前端可直接跳转聊天

    # ===== 原有逻辑：正常创建案件 =====
    # ... 原有的案件创建和 outreach 发送逻辑 ...
```

---

### 前端适配

**文件**：`candidate-detail-page.tsx`

**新增处理**：检测返回的 `status === 'mutual_match'`

```tsx
const handleExpressInterest = async () => {
  // ... 主动发起逻辑 ...
  try {
    if (subscriptionId) {
      const response = await createProxyIntroRequest({
        subscriptionId,
        candidateId: Number(candidateData.id),
        source: 'candidate_detail',
      })

      // 新增：检测双向匹配
      if (response.status === 'mutual_match') {
        // 双向匹配成功，直接跳转聊天
        toast.success('双向匹配成功！开始聊天吧')
        onOpenChat(response.conversation_id)
        return
      }

      // 正常流程：等待对方回复
      setShowSubmittedHint(true)
    }
  } catch (error) {
    // ...
  }
}
```

---

### 流程对比

```
BEFORE（无双向匹配检测）：
A 点愿意认识 → 创建案件 A→B
B 点愿意认识 → 创建案件 B→A
结果：两个独立案件，流程混乱

AFTER（有双向匹配检测）：
A 点愿意认识 → 创建案件 A→B
系统检测到 B→A 案件存在 → 自动双向匹配
结果：直接创建对话，双方进入聊天
```

---

## 问题 3：愿意认识后一步开聊

### 方案设计

**核心思路**：点愿意认识后，自动开聊并跳转，无需用户手动去关系页。

### 方案 A：自动开聊（推荐）

#### 后端改动

**文件**：`proxy_intro_core.py`

**改动位置**：第 1044-1068 行（record_match_case_reply 函数）

**新增逻辑**：reply accepted 时自动创建对话

```python
def record_match_case_reply(
    case_conn,
    *,
    case_id: str,
    reply_type: str,
    now: datetime | None = None,
    # ... 其他参数
) -> dict[str, Any]:
    # ... 原有逻辑 ...

    if reply_type == "accepted":
        updated_case = _update_case_status(
            # ... 原有参数 ...
        )

        # ===== 新增：自动创建对话 =====
        from chat_system.conversations import create_assistant_case_layout

        conversation_result = create_assistant_case_layout(
            profile_a=case["requester_profile_ref"],
            profile_b=case["candidate_profile_ref"],
            case_id=case_id,
            now=now,
        )

        # 更新案件的 main_conversation_id
        case_conn.execute(
            f"""
            UPDATE {_t().cases}
            SET main_conversation_id = ?
            WHERE case_id = ?
            """,
            (conversation_result["main_conversation_id"], case_id),
        )

        # 自动关闭案件
        close_match_case(
            case_conn,
            case_id=case_id,
            close_reason="auto_handoff_after_accept",
            now=now,
        )

        # 返回结果包含 conversation_id
        return {
            "case": updated_case,
            "conversation": conversation_result,
            "status": "accepted_and_chat_created",
        }

    # ... declined 逻辑 ...
```

---

#### 前端改动

**文件 1**：`discover-page.tsx`

**改动位置**：第 388-406 行（handleInterestReply 函数）

```tsx
const handleInterestReply = async (caseId: string, replyType: 'accepted' | 'declined') => {
  if (actingCaseId) return
  setActingCaseId(caseId)
  try {
    const response = await replyProxyIntroCase({
      caseId,
      replyType,
      source: 'recommendation_inbox',
    })

    if (replyType === 'accepted') {
      // ===== 新增：自动跳转聊天 =====
      const conversationId = response.conversation?.conversation_id
      if (conversationId) {
        toast.success('已接受，开始聊天！')
        onOpenChat(String(conversationId))  // 直接跳转聊天页
      } else {
        // 兜底：没有 conversation_id 时，提示用户去关系页
        toast.success('已表达意愿，请去关系页开始聊天')
      }
      setDismissedIds((prev) => new Set(prev).add(`case:${caseId}`))
    } else {
      toast.success('已暂不考虑')
      setDismissedIds((prev) => new Set(prev).add(`case:${caseId}`))
    }
  } catch (error) {
    notifyError(error, replyType === 'accepted' ? '接受失败' : '暂不考虑失败')
  } finally {
    setActingCaseId(null)
  }
}
```

---

**文件 2**：`candidate-detail-page.tsx`

**改动位置**：handleExpressInterest 函数中的回复案件逻辑

```tsx
// 场景：被动推荐 → 点愿意认识
if (viewType === 'interest' && caseId) {
  setIsExpressingInterest(true)
  try {
    const response = await replyProxyIntroCase({
      caseId,
      replyType: 'accepted',
      source: 'candidate_detail_reply',
    })

    // ===== 新增：自动跳转聊天 =====
    const conversationId = response.conversation?.conversation_id
    if (conversationId) {
      toast.success('已接受，开始聊天！')
      onOpenChat(String(conversationId))
    } else {
      setShowSubmittedHint(true)  // 兜底：显示"已接受"
    }
  } catch (error) {
    notifyError(error, '接受失败，请稍后重试')
  } finally {
    setIsExpressingInterest(false)
  }
  return
}
```

---

**文件 3**：`relationships-page.tsx`

**改动位置**：handleReply 函数

```tsx
async function handleReply(caseId: string, replyType: 'accepted' | 'declined') {
  if (actingCaseId) return
  setActingCaseId(caseId)
  try {
    const response = await replyProxyIntroCase({
      caseId,
      replyType,
      source: 'relationships_page',
    })

    if (replyType === 'accepted') {
      // ===== 新增：自动跳转聊天 =====
      const conversationId = response.conversation?.conversation_id
      if (conversationId) {
        toast.success('已接受，开始聊天！')
        onOpenChat(String(conversationId))
      } else {
        // 兜底：更新本地状态
        if (response.case) {
          setCases((prev) => prev.map((item) => (item.case_id === caseId ? response.case! : item)))
        }
        toast.success('已接受，请点击开始聊天')
      }
    } else {
      // declined 逻辑不变
      if (response.case) {
        setCases((prev) => prev.map((item) => (item.case_id === caseId ? response.case! : item)))
      }
    }
  } catch (error) {
    setLoadError(getErrorMessage(error, replyType === 'accepted' ? '接受失败' : '暂不考虑失败'))
  } finally {
    setActingCaseId(null)
  }
}
```

---

### 方案 B：询问后开聊（备选）

如果不想自动开聊，可以在点愿意认识后弹窗询问：

```tsx
// 点愿意认识后
if (replyType === 'accepted') {
  // 弹窗询问
  const shouldChatNow = await showConfirmDialog({
    title: '已接受认识请求',
    message: '现在开始聊天吗？',
    confirmText: '立即开聊',
    cancelText: '稍后再聊',
  })

  if (shouldChatNow) {
    // 调用开聊 API
    const chatResponse = await openProxyIntroChat({ caseId })
    onOpenChat(chatResponse.conversation.conversation_id)
  } else {
    toast.success('已接受，可去关系页开聊')
  }
}
```

---

## 实施优先级建议

| 优先级 | 问题 | 原因 |
|--------|------|------|
| **P0** | 问题 3（一步开聊） | 直接影响用户体验，改动相对简单 |
| **P1** | 问题 1（卡片可点击） | 提升决策信息完整性，改动中等 |
| **P2** | 问题 2（双向匹配） | 特殊场景，改动较复杂，可后续迭代 |

---

## 测试场景清单

### 问题 1 测试

| 场景 | 验证点 |
|------|--------|
| 点击 interest 卡片 | 进入候选人详情页 |
| 详情页显示 | 包含完整资料（照片、介绍等） |
| 底部按钮 | 显示"愿意认识"（回复案件） |
| 点击愿意认识 | 调用 replyProxyIntroCase API |

### 问题 2 测试

| 场景 | 验证点 |
|------|--------|
| A 先点愿意认识 | 正常创建案件，发通知给 B |
| B 收到通知后点愿意认识 | 正常匹配，开聊 |
| A 和 B 几乎同时点愿意认识 | 检测双向匹配，直接开聊 |
| 双向匹配后 | 两个案件都关闭，只保留一个对话 |

### 问题 3 测试

| 场景 | 验证点 |
|------|--------|
| 推荐来信页点愿意认识 | 自动开聊，跳转聊天页 |
| 候选人详情页点愿意认识（被动推荐） | 自动开聊，跳转聊天页 |
| 关系页点愿意认识 | 自动开聊，跳转聊天页 |
| 开聊失败（兜底） | 提示去关系页手动开聊 |

---

## 风险与注意事项

1. **跨服务调用**：问题 2 和问题 3 都涉及 matchmaking 系统调用 chat 系统，需要确认服务间调用方式（同步/异步）

2. **幂等性**：自动开聊需要考虑幂等，避免重复创建对话

3. **事件顺序**：双向匹配时，需要确保两个案件的更新和对话创建在同一事务中

4. **前端跳转**：需要确保 `onOpenChat` 函数能正确跳转到聊天页，且聊天页能正确加载对话