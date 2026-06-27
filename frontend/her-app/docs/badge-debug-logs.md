# 导航栏Badge调试日志说明

## 日志位置和内容

### 日志1：所有cases数据（Badge计算入口）

**位置**：[lib/api/endpoints/chat.ts](frontend/her-app/lib/api/endpoints/chat.ts)

**日志标识**：`[Badge Debug] 所有cases:`

**内容**：
- 所有case的详细信息
- 包括：case_id, role, case_status, can_reply, can_open_chat, main_conversation_id, counterpart_name

**用途**：
- 查看后端返回的所有case数据
- 理解数据结构和状态

---

### 日志2：pendingCount计算详情

**位置**：[lib/api/endpoints/chat.ts](frontend/her-app/lib/api/endpoints/chat.ts)

**日志标识**：`[Badge Debug] Pending cases:` 和 `[Badge Debug] pendingCount:`

**内容**：
- 计入pendingCount的所有case
- 每个case计入的原因（发起方未开聊 / 被推荐方已接受）
- pendingCount总数

**用途**：
- 查看哪些case计入pendingCount
- 对比页面显示的"牵线中"case

---

### 日志3：chatUnread详情

**位置**：[lib/api/endpoints/chat.ts](frontend/her-app/lib/api/endpoints/chat.ts)

**日志标识**：`[Badge Debug] Chat unread case:` 和 `[Badge Debug] chatUnread:`

**内容**：
- 每个有未读消息的case详情
- 未读消息数量
- chatUnread总数

**用途**：
- 查看哪些case有未读消息
- 理解chatUnread的计算逻辑

---

### 日志4：badge总数

**位置**：[lib/api/endpoints/chat.ts](frontend/her-app/lib/api/endpoints/chat.ts)

**日志标识**：`[Badge Debug] total badge:`

**内容**：
- badge总数（pendingCount + chatUnread）

**用途**：
- 查看最终badge数字
- 对比导航栏显示的数字

---

### 日志5：页面pendingIntroItems详情

**位置**：[lib/mappers/relationships-view.ts](frontend/her-app/lib/mappers/relationships-view.ts)

**日志标识**：`[Page Debug] pendingIntroItems:` 和 `[Page Debug] pendingIntroItems count:`

**内容**：
- 页面"牵线中"section显示的所有case
- 每个case的详细信息
- pendingIntroItems总数

**用途**：
- 查看页面实际显示的case
- 对比badge的pendingCount

---

### 日志6：页面activeRelationships详情

**位置**：[lib/mappers/relationships-view.ts](frontend/her-app/lib/mappers/relationships-view.ts)

**日志标识**：`[Page Debug] activeRelationships:` 和 `[Page Debug] activeRelationships count:`

**内容**：
- 页面"正在进行中"section显示的所有case
- 每个case的未读消息数
- activeRelationships总数

**用途**：
- 查看页面实际显示的已开聊case
- 对比badge的chatUnread

---

### 日志7：inbox badge详情

**位置**：[hooks/use-badge-counts.ts](frontend/her-app/hooks/use-badge-counts.ts)

**日志标识**：`[Badge Debug] Inbox badge:`

**内容**：
- 推荐卡片未读数
- 被动推荐未读数
- inbox badge总数

**用途**：
- 查看inbox badge的组成
- 理解红娘Tab的badge计算

---

### 日志8：relationships badge详情

**位置**：[hooks/use-badge-counts.ts](frontend/her-app/hooks/use-badge-counts.ts)

**日志标识**：`[Badge Debug] Relationships badge:`

**内容**：
- pendingCount
- chatUnread
- relationships badge总数
- byCaseId（各case的未读数）

**用途**：
- 查看relationships badge的组成
- 理解关系Tab的badge计算

---

## 如何查看日志

### 方法1：浏览器开发者工具

1. 打开应用（http://localhost:3000）
2. 打开浏览器开发者工具（F12）
3. 切换到Console标签
4. 刷新页面，查看日志输出

---

### 方法2：筛选特定日志

在Console中输入筛选条件：

```javascript
// 只看Badge相关日志
console.log只显示包含'[Badge Debug]'的日志

// 只看Page相关日志
console.log只显示包含'[Page Debug]'的日志

// 只看pendingCount相关日志
console.log只显示包含'pendingCount'的日志
```

---

## 验证步骤

### 步骤1：查看所有cases数据

查看日志1：`[Badge Debug] 所有cases`

**验证**：
- 确认马沐瑶、刘舒彤的数据
- 检查role、case_status、main_conversation_id等字段

---

### 步骤2：查看pendingCount计算

查看日志2：`[Badge Debug] Pending cases`

**验证**：
- 马沐瑶、刘舒彤是否计入pendingCount？
- 计入原因是什么？

---

### 步骤3：查看页面显示

查看日志5：`[Page Debug] pendingIntroItems`

**验证**：
- 马沐瑶、刘舒彤是否在pendingIntroItems中？
- pendingIntroItems count是多少？

---

### 步骤4：对比badge和页面

对比：
- 日志2的pendingCount
- 日志5的pendingIntroItems count

**验证**：
- 两者是否一致？
- 如果不一致，找出差异原因

---

### 步骤5：查看badge总数

查看日志4和日志8：

**验证**：
- badge总数 = pendingCount + chatUnread
- 是否有chatUnread？
- chatUnread是否合理？

---

## 常见问题诊断

### 问题1：badge显示3，页面显示2

**诊断步骤**：

1. 查看日志2（Pending cases）：
   - pendingCount是多少？
   - 包含哪些case？

2. 查看日志5（pendingIntroItems）：
   - pendingIntroItems count是多少？
   - 包含哪些case？

3. 对比差异：
   - 哪个case计入badge但页面不显示？
   - 或哪个case页面显示但badge不计入？

4. 查看日志3（chatUnread）：
   - 是否有chatUnread？
   - chatUnread是否导致badge多1？

---

### 问题2：badge显示数字跳动

**诊断步骤**：

1. 查看日志7和日志8：
   - 每次刷新时badge数字是否变化？
   - 数据源是否稳定？

2. 查看日志1：
   - 后端返回的数据是否每次都不同？
   - 是否有缓存问题？

---

### 问题3：badge计算逻辑不明确

**诊断步骤**：

1. 查看日志2：
   - 每个case的计入原因（发起方未开聊 / 被推荐方已接受）
   - 理解计算逻辑

2. 查看日志5：
   - 页面显示逻辑
   - 对比badge计算逻辑

---

## 日志输出示例

### 示例1：正常情况（badge = page）

```
[Badge Debug] 所有cases: [
  { case_id: '1', role: 'requester', case_status: 'awaiting_reply', ... },
  { case_id: '2', role: 'requester', case_status: 'awaiting_reply', ... }
]

[Badge Debug] Pending cases: [
  { case_id: '1', counterpart_name: '马沐瑶', reason: '发起方未开聊' },
  { case_id: '2', counterpart_name: '刘舒彤', reason: '发起方未开聊' }
]
[Badge Debug] pendingCount: 2

[Page Debug] pendingIntroItems: [
  { case_id: '1', counterpart_name: '马沐瑶' },
  { case_id: '2', counterpart_name: '刘舒彤' }
]
[Page Debug] pendingIntroItems count: 2

[Badge Debug] chatUnread: 0
[Badge Debug] total badge: 2
```

**结果**：badge显示2，页面显示2，一致！

---

### 示例2：异常情况（badge = 3, page = 2）

```
[Badge Debug] 所有cases: [
  { case_id: '1', role: 'requester', case_status: 'awaiting_reply', ... },
  { case_id: '2', role: 'requester', case_status: 'awaiting_reply', ... },
  { case_id: '3', role: 'candidate', case_status: 'accepted', ... }
]

[Badge Debug] Pending cases: [
  { case_id: '1', counterpart_name: '马沐瑶', reason: '发起方未开聊' },
  { case_id: '2', counterpart_name: '刘舒彤', reason: '发起方未开聊' },
  { case_id: '3', counterpart_name: '被推荐方已接受', reason: '被推荐方已接受' }
]
[Badge Debug] pendingCount: 3

[Page Debug] pendingIntroItems: [
  { case_id: '1', counterpart_name: '马沐瑶' },
  { case_id: '2', counterpart_name: '刘舒彤' }
]
[Page Debug] pendingIntroItems count: 2

[Badge Debug] chatUnread: 0
[Badge Debug] total badge: 3
```

**结果**：badge显示3，页面显示2，不一致！

**原因**：被推荐方已接受的case（case_id: '3'）计入badge，但页面不显示

---

## 下一步

查看日志后，如果发现不一致：
1. 分析具体哪个case导致差异
2. 确认该case的状态和字段
3. 判断是badge计算问题还是页面展示问题
4. 针对性修复