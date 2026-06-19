# 新建会话后系统完整流程梳理

## 📊 时间线概览

```
18:55:02 用户创建新会话
         ↓
18:55:02 系统触发处理上一个会话
         ↓
18:55:02-18:55:29 系统提取摘要（耗时27秒）
         ↓
18:55:29 数据持久化完成
```

---

## 🔍 详细流程分析

### Step 1：创建新会话（18:55:02）

```
【事件】：用户创建新会话

Line 360: Funnel: session_open_profile_first
         Session: discovery-session-61728e5094da
         → 用户打开新会话

Line 361: Audit: discovery.session.create
         Resource_id: discovery-session-61728e5094da
         Requester_id: 10015
         → 审计记录：会话创建成功

Line 367: POST /v1/discovery/sessions - 201
         Response: 10862字节
         → HTTP响应：新会话创建成功
```

---

### Step 2：检测上一个会话是否有新增内容（18:55:02）

```
【核心逻辑】：检查上一个会话是否需要处理

Line 362: 会话 discovery-session-2a1820953e6c 从未处理过
         → processed_at=None（第一次处理）

Line 363: 新建会话触发上一个会话处理
         Current_session_id: discovery-session-61728e5094da（新会话）
         Previous_session_id: discovery-session-2a1820953e6c（上一个会话）
         Has_new_content: True
         → 系统判断：上一个会话有新增内容，需要处理

Line 364: Using selector: KqueueSelector
         → 使用异步选择器

Line 365: 触发会话结束处理（线程模式）
         Thread: session_end_discovery-session-2a1820953e6c
         Processed_at: None
         → 启动独立线程处理（不阻塞新会话创建）

Line 366: 触发上一个会话处理
         Task_name: session_end_discovery-session-2a1820953e6c
         → 服务层触发处理
```

---

### Step 3：加载聊天记录（18:55:02）

```
【数据加载】：从数据库加载上一个会话的聊天记录

Line 368: 开始处理会话结束
         Session_id: discovery-session-2a1820953e6c
         Processed_at: None
         → 开始处理

Line 372: 全量加载聊天记录
         Loaded_count: 17
         → 加载17条聊天记录（因为processed_at=None，全量加载）

Line 373: 加载了 17 条聊天记录
         → 确认加载成功
```

---

### Step 4：LLM提炼摘要（18:55:02-18:55:29）

```
【AI处理】：调用LLM提炼用户画像特征

Line 374: Request options: LLM调用
         Model: qwen3.7-plus
         Max_tokens: 500
         Temperature: 0.3
         → 配置LLM参数

Line 375: Sending HTTP Request: POST
         URL: https://coding.dashscope.aliyuncs.com/v1/chat/completions
         → 发送LLM请求

Line 397: HTTP Response: 200 OK
         Req-cost-time: 26872ms（约27秒）
         → LLM响应成功，耗时27秒

Line 405: LLM提炼摘要成功
         提取字段：
           - partner_expectation: "希望找比自己大的女生（28岁以上）"
           - marital_status: "未婚"
           - has_children: "没有孩子"
           - city: "无锡"
           - age: "28"
         → LLM成功提取用户画像特征
```

---

### Step 5：字段分流（18:55:29）

```
【数据处理】：区分可量化字段和不可量化字段

Line 406: 分流完成
         Quantifiable_fields: ['marital_status', 'has_children', 'city', 'age']
         Non_quantifiable_fields: ['partner_expectation']
         → 分流结果：
           - 可量化字段：4个（婚姻状态、孩子、城市、年龄）
           - 不可量化字段：1个（择偶期望）
```

---

### Step 6：可量化字段写入（18:55:29）

```
【数据写入】：写入可量化字段到画像表

Line 408: 可量化字段写入成功
         User_key: 10015
         Applied_fields: []（空）
         → 写入成功，但没有应用任何字段

Line 409: 可量化字段写入画像表
         Persona_result:
           - Success: True
           - Applied_fields: []
           - Skipped_fields: 4个
           - Note: "inference_not_persisted"
         → 所有可量化字段被跳过，原因是"推断字段不持久化"

原因分析：
  - marital_status、has_children、city、age 都是从对话推断出来的
  - 系统策略：推断的字段不写入画像表（避免猜测错误）
```

---

### Step 7：不可量化字段摘要存储（18:55:29）

```
【摘要存储】：存储不可量化字段的摘要文本

Line 410: 不可量化字段摘要存储成功
         Saved_keys: ['partner_expectation']
         → 成功存储择偶期望摘要

Line 411: 批量查询历史摘要完成
         Query_fields: ['partner_expectation']
         Historical_data: {'partner_expectation': '希望找比自己大的女生（28岁以上）'}
         → 查询历史摘要数据
```

---

### Step 8：AI合并判断（18:55:29）

```
【增量合并】：判断新摘要与历史摘要如何合并

Line 414: 需要AI判断的字段: ['partner_expectation']
         → 需要AI判断择偶期望字段如何合并

Line 415: ERROR 批量处理失败
         Error: Invalid format specifier
         → ❌ AI合并判断失败（格式错误）

问题：
  - AI合并逻辑有bug
  - 格式化字符串错误
```

---

### Step 9：向量库存储（18:55:29）

```
【向量化】：写入向量库（Milvus）

Line 421: 不可量化字段向量化存储成功
         Vectorized_keys: []（空）
         → ✅ 向量化成功，但没有实际写入（因为AI合并失败）
```

---

### Step 10：清空working_criteria（18:55:29）

```
【清理】：清空会话的临时筛选条件

Line 422: ERROR 清空 working_criteria 失败
         Error: Unknown column 'session_state' in 'field list'
         → ❌ 清空失败，数据库字段不存在

问题：
  - 数据库表缺少 session_state 字段
  - 清空逻辑失败

Line 423: working_criteria 已清空
         → ✅ 尝试清空成功（可能使用了其他方式）
```

---

### Step 11：更新processed_at（18:55:29）

```
【标记完成】：更新会话的处理时间戳

Line 424: 更新 processed_at
         Session_id: discovery-session-2a1820953e6c
         Processed_at: 2026-06-18 18:52:54
         → ✅ 成功更新processed_at

注意：
  - processed_at记录的是会话的最后更新时间（18:52:54）
  - 而不是处理完成时间（18:55:29）
  - 这样下次检查时，能正确识别是否有新增内容
```

---

## 📈 性能统计

| 指标 | 数值 |
|------|------|
| **总耗时** | 27秒 |
| **LLM耗时** | 26.8秒 |
| **聊天记录数** | 17条 |
| **提取字段数** | 5个 |
| **成功写入数** | 1个（partner_expectation摘要）|
| **失败数** | 3个（AI合并、清空working_criteria、可量化字段跳过）|

---

## ⚠️ 发现的问题

### 问题1：AI合并判断失败

```
ERROR: Invalid format specifier
原因：格式化字符串错误
影响：无法正确合并历史摘要
建议：修复AI合并逻辑的格式化问题
```

### 问题2：清空working_criteria失败

```
ERROR: Unknown column 'session_state'
原因：数据库表缺少字段
影响：无法清空临时筛选条件
建议：添加数据库字段或修改清空逻辑
```

### 问题3：可量化字段被跳过

```
所有可量化字段都被跳过
原因：inference_not_persisted（推断字段不持久化）
影响：无法记录用户的明确偏好（如年龄、城市）
建议：优化推断策略，明确表达的偏好应持久化
```

---

## ✅ 成功的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| **新建会话触发处理** | ✅ 成功 | 正确触发处理上一个会话 |
| **检测新增内容** | ✅ 成功 | 正确判断processed_at是否为空 |
| **加载聊天记录** | ✅ 成功 | 全量加载17条记录 |
| **LLM提炼摘要** | ✅ 成功 | 提取5个字段 |
| **摘要存储** | ✅ 成功 | 存储partner_expectation摘要 |
| **更新processed_at** | ✅ 成功 | 正确标记处理完成 |

---

## 🎯 核心流程总结

```
用户创建新会话 discovery-session-61728e5094da
    ↓
系统检测上一个会话 discovery-session-2a1820953e6c
    ↓
判断：processed_at=None → 第一次处理
    ↓
全量加载17条聊天记录
    ↓
LLM提炼摘要（耗时27秒）
    ↓
提取：择偶期望、婚姻状态、孩子、城市、年龄
    ↓
分流：可量化字段 vs 不可量化字段
    ↓
可量化字段：全部跳过（推断不持久化）
    ↓
不可量化字段：存储摘要成功
    ↓
AI合并判断：❌ 失败（格式错误）
    ↓
向量库存储：成功但未写入
    ↓
清空working_criteria：❌ 失败（字段不存在）
    ↓
更新processed_at：✅ 成功
```

---

## 💡 改进建议

### 高优先级

1. **修复AI合并判断错误**
   - 定位格式化字符串错误
   - 确保历史摘要能正确合并

2. **修复数据库字段缺失**
   - 添加session_state字段
   - 或修改清空working_criteria逻辑

3. **优化可量化字段策略**
   - 明确表达的偏好应持久化
   - 区分"推断"和"明确表达"

### 中优先级

4. **优化LLM响应延迟**
   - 27秒耗时较长
   - 考虑缓存或异步处理

5. **增加错误日志详细度**
   - 记录具体的错误栈
   - 方便问题排查

---

## 📌 结论

**整体流程成功运行**，但存在一些需要修复的问题：

- ✅ 新建会话触发处理逻辑正常
- ✅ 检测新增内容逻辑正常
- ✅ LLM提炼摘要成功
- ❌ AI合并判断失败（需修复）
- ❌ 清空working_criteria失败（需修复）
- ⚠️ 可量化字段策略需要优化

建议在生产环境前修复这些问题。