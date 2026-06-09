# 发现页 Agent 上下文优化方案

> 适用范围：`external-systems/partner-discovery-system/discovery_system/` 发现页 Agent 运行时、上下文拼装、tool 结果回灌、Agents SDK session 管理。
>
> 核心问题：当前发给 `/chat/completions` 的请求过大，导致 token 成本高、响应变慢、上下文污染严重，且存在持续逼近上下文上限的风险。

## 1. 问题定义

发现页当前不是单纯“prompt 有点长”，而是整条请求被多层内容一起撑大：

1. system prompt 本身较长。
2. 每轮 `user payload` 都带一份较重的 `official_context`。
3. Agents SDK session 会把较长历史 `messages` 一起带回下一轮。
4. search tool 的完整结果被回灌进模型上下文。
5. 输出 schema 和 tools schema 也会固定占用上下文。

结果不是单个字段略大，而是每轮都在重复发送：

- 一份说明书
- 一份页面快照
- 一份候选卡片摘要
- 一份搜索结果
- 一份历史对话堆栈
- 一套 schema / tool contract

这会直接带来：

- 首 token 延迟变长
- 整体响应时间上升
- token 成本明显增加
- 模型更容易被旧上下文和噪音字段干扰
- 上下文持续累积后更容易逼近模型上限

## 2. 当前诊断结论

基于 `gateway.log` 中实际发给 `/chat/completions` 的请求样本，问题重点不是单一 system prompt，而是历史和工具结果累积。

一次真实请求中：

- `messages` 数量达到 57 条
- `messages` 总体量约 245,719 字符
- 粗估约 61k tokens
- 再叠加 `response_format` schema 和 `tools` schema 后，总体量约 63k+ tokens

按大类拆分，最大头依次为：

1. `user_payload`
2. `tool_result`
3. `assistant_output`
4. `system_instructions`

其中：

- 多条 `user_payload` 单条就在约 1.8k tokens
- 一条 search tool result 单独约 11k tokens
- `user_payload` 中最大头是 `official_context.page_summary`
- `page_summary` 中最大头是 `result_cards[*].personality_match_context`

结论很明确：

- 真正的问题不是“单轮输入稍长”
- 而是“每轮都把重状态、重历史、重工具结果重新塞一遍”

## 3. 设计原则

发现页上下文必须分三类处理：

### 3.1 Hard State

定义：只要模型记错，就会导致业务行为错误。

这些信息必须由后端每轮手动注入，作为权威状态。

### 3.2 Soft Memory

定义：记错了不会导致状态错乱，只会让回复不够自然。

这些信息不需要每轮全量手动传，可以交给 agent memory 或后端摘要。

### 3.3 Junk Context

定义：既大，又不构成当前轮决策的必要条件。

这些信息必须删除，不能继续进入模型上下文。

判断标准只有一句：

- 如果模型记错它，会不会导致产品行为错？

如果会，则归入 Hard State。  
如果不会，只影响自然度，则归入 Soft Memory。  
如果既不会又很大，则归入 Junk Context。

## 4. 为什么不能只靠 Agent 自己的“记忆”

发现页不是纯聊天场景，而是“聊天 + 页面状态 + 结构化交互”的混合场景。

agent memory 适合记“聊天印象”，不适合承担“当前权威状态”。

### 4.1 Agent memory 适合记住的内容

- 用户整体偏好倾向
- 用户说话风格
- 前几轮的语气和软偏好
- 最近几轮红娘如何接话

### 4.2 不能只靠 agent memory 的内容

- 当前页面展示的是哪 3 张卡
- 当前哪些 action 还能点
- 用户刚点了哪个 action，以及 semantic payload 是什么
- 当前 phase 是什么
- 上一轮搜索真实返回了哪些候选人
- 哪些 profile_id 才允许被 agent 选回前端

这些都属于“系统真实状态”，必须由后端显式注入，而不是让模型凭历史去猜。

因此正确做法不是“手动传”和“记忆”二选一，而是：

- 手动传事实
- 记忆保留感觉

## 5. 目标形态

每轮发给模型的内容收敛成四块：

1. 短版 system instructions
2. 当前事件 `event`
3. 当前权威状态 `state`
4. 极短历史摘要 `memory_summary`

而不是继续发送一长串原始历史 `messages`。

推荐形态：

```json
{
  "event": {
    "type": "user_message",
    "text": "帮我换一批"
  },
  "state": {
    "session": {},
    "user_profile": {},
    "current_results": [],
    "visible_actions": [],
    "last_search": {}
  },
  "memory_summary": {
    "stable_preferences": [],
    "recent_conversation_summary": "",
    "recent_feedback_summary": ""
  }
}
```

## 6. 字段级方案：保留 / 压缩 / 删除

### 6.1 `session`

保留：

- `session_id`
- `phase`
- `criteria_labels`

删除：

- `requester_id`
- `profile_id`

原因：这些 id 对语言决策价值有限，属于后端内部标识。

### 6.2 当前用户输入

保留：

- 当前这轮 `latest_user_message`

这是本轮最核心的信息，不应删除。

### 6.3 `clicked_action`

保留，但压缩为最小语义形态：

- `label`
- `kind`
- 必要参数

例如：

```json
{
  "label": "职业不太匹配",
  "kind": "rejection_feedback",
  "feedback_type": "occupation_mismatch"
}
```

删除：

- 原始整包 `hint`
- 非决策必需的内部字段

### 6.4 `requester_profile_snapshot`

仅保留本轮决策必要字段：

- `age`
- `city`
- `gender`
- `relationship_goal`
- `target_gender`
- `target_age_min`
- `target_age_max`
- `target_cities`

若当前轮涉及测评解释，可补充极简测评摘要：

- `mbti.type_code`
- `attachment.type_code`
- `values.top_values` 前 2 个

删除：

- 完整 personality 原始结构
- `assessment_id`
- `completed_at`
- 大量原始数值

原则：不给模型“原始档案”，只给“决策摘要”。

### 6.5 `recent_timeline_summary`

不要继续把最近多条原始 timeline item 每轮都发进去。

改成一句后端摘要：

```json
{
  "recent_conversation_summary": "刚展示过一轮偏稳定职业的苏州女生，用户要求再换一批。"
}
```

保留：

- 最近一轮发生了什么
- 最近是否展示过候选人
- 最近是否问过测评

删除：

- 原始逐条消息
- 原始 `result_group`
- 原始 `assessment_result`

### 6.6 `page_summary`

这是当前最该优化的重灾区。

现状问题：

- `page_summary.result_cards` 中每张卡都带完整 `personality_match_context`
- 3 张卡一起就吃掉约 1k+ tokens

改造方式：

把 `page_summary` 重构成 `current_results`，每张卡只保留最小摘要：

```json
[
  {
    "profile_id": 573,
    "title": "30岁硕士公务员",
    "reason_summary": "工作稳定，作息规律，倾向长期关系",
    "compatibility_summary": "生活节奏稳，价值观偏长期投入"
  }
]
```

保留：

- `profile_id`
- `title`
- `reason_summary`
- 可选一条 `compatibility_summary`

删除：

- `personality_match_context`
- `personality_reasoning` 原始对象
- `personality_availability`
- `match_score`
- 非关键展示字段

如果模型要回答“为什么推荐她”，不要把完整测评对象交给模型，而是后端先压成一句兼容性摘要再传入。

### 6.7 `visible_actions`

保留极简 action 语义：

- `label`
- `kind`
- 必要参数

例如：

```json
[
  {"label":"看看更多","kind":"show_more_candidates"},
  {"label":"调整条件","kind":"refine_preferences"}
]
```

删除：

- `action_id`
- 多余 hint 原始结构

### 6.8 `last_search_summary`

保留最小摘要：

- `status`：`success` / `empty` / `error`
- `result_count`
- `criteria_summary`
- `error_code` 或简短错误信息

例如：

```json
{
  "status": "success",
  "result_count": 5,
  "criteria_summary": "苏州，26-36岁，女，偏稳定职业",
  "error_code": null
}
```

删除：

- 完整 `criteria`
- `personality_trace`
- `source`
- 调试性字段

### 6.9 `note`

当前 `note` 每轮重复发送，纯属固定消耗。

处理方式：

- 合并进短版 system prompt
- 不再放在每轮 user payload 中重复发送

## 7. 历史消息处理方案

### 7.1 当前问题

现在不是只发送“当前轮输入”，而是大量历史 message 一起进入模型：

- user payload
- assistant 输出
- tool result
- tool 错误
- 搜索结果回灌

这会导致请求体持续膨胀。

### 7.2 目标

把 session 从“原始 transcript 累计模式”改成“状态 + 摘要模式”。

### 7.3 方案

每轮结束后：

1. 把结构化状态落后端存储
2. 把长历史压成短摘要
3. 下轮只发送：
   - 当前 event
   - 当前 state
   - 最新 memory summary

不再把长串历史 `messages` 原样重发。

## 8. Tool Result 瘦身方案

### 8.1 当前问题

search tool 返回给模型的是完整大对象：

- 每个候选人对象极重
- 一次 5 个结果即可吃掉 10k+ tokens

### 8.2 原则

完整候选人对象属于后端数据层，不属于 LLM 决策层。

### 8.3 两层结果

#### A. 后端完整结果

保留在后端，用于：

- 渲染卡片
- 落库
- 审计
- 详情页读取

#### B. 模型精简结果

只把最小摘要喂给模型：

```json
{
  "has_match": true,
  "result_count": 5,
  "results": [
    {
      "profile_id": 573,
      "summary": "30岁硕士公务员，苏州，工作稳定，倾向长期关系"
    },
    {
      "profile_id": 6609,
      "summary": "32岁药师，苏州定居，情绪稳定顾家"
    }
  ]
}
```

这样足够模型做：

- 选人
- 排序
- 生成简要解释

但不会再吃掉海量上下文。

## 9. System Prompt 瘦身方案

### 9.1 当前问题

system prompt 同时承载：

- 人设
- 搜索逻辑
- 测评逻辑
- 换一批反馈逻辑
- 输出格式规则
- tool 使用规则

导致固定成本偏高。

### 9.2 目标拆层

把 prompt 拆成三层：

#### Core Prompt

永远发送，控制在 300-600 tokens 内。

只保留：

- 角色
- 以 state 为准
- 不能编造候选人
- 输出 JSON 约束
- 搜索与解释的主原则

#### Mode Prompt

按事件动态拼接，例如：

- 只有在 `rejection_feedback` 场景才发送“换一批反馈闭环”规则
- 只有在测评追问场景才发送测评推荐规则

#### Schema / Tool Contract

尽量依赖 schema 和 tools 的正式 contract，不在 prompt 中重复写成长说明书。

## 10. Memory Summary 方案

后端替代长历史，维护三类摘要：

### 10.1 `stable_preferences_summary`

长期稳定偏好，例如：

- 介意互联网行业太忙
- 偏好生活节奏稳定
- 希望苏州周边
- 年龄期望 26-36

### 10.2 `recent_feedback_summary`

最近几轮换一批反馈，例如：

- 最近两轮主要排斥互联网、审计财务方向
- 更偏公务员、教师、医药、文职

### 10.3 `recent_conversation_summary`

近 2-3 轮对话状态，例如：

- 刚展示过一轮稳定职业候选人，用户要求继续换一批

三类摘要总预算建议控制在 150-300 tokens 以内。

## 11. 最终上下文预算

建议给发现页每轮设置硬预算：

- system prompt：`<= 600 tokens`
- state：`<= 700 tokens`
- memory summary：`<= 250 tokens`
- event：`<= 80 tokens`
- schema + tools：`<= 900 tokens`

总目标：

- 常规轮次：`2k - 3k tokens`
- 重场景轮次：不超过 `4k tokens`

与当前 `60k+ tokens` 级别相比，需要做数量级压缩，而不是微调。

## 12. 实施顺序

### Phase 1：止血

目标：先把最夸张的上下文膨胀点切掉。

1. 禁止把完整 search tool result 回灌给模型
2. 禁止累计全历史 `messages`
3. 删除 `page_summary.result_cards[*].personality_match_context`
4. 删除 payload 中重复 `note`

### Phase 2：上下文重构

目标：把当前 `official_context` 改造成最小决策状态。

1. `official_context` 改成极简 `state`
2. `recent_timeline_summary` 改成一句摘要
3. `page_summary` 改成 `current_results` 最小卡片摘要
4. `visible_actions` 改成简版 action 列表
5. `last_search_summary` 改成极简状态摘要

### Phase 3：Prompt 重构

目标：减少固定说明书成本。

1. 拆分 system prompt 为 `core + mode`
2. 场景规则按事件动态注入
3. 去掉和 schema / tools 重复的说明

### Phase 4：长期治理

目标：避免未来再次失控。

1. 增加 token 统计埋点
2. 记录每轮：
   - prompt tokens
   - completion tokens
   - 首 token 延迟
   - tool result 大小
3. 设置超限报警：
   - 单轮上下文 > 4k tokens 则报警

## 13. 预期收益

完成后，预期收益包括：

- 请求体从 `60k+ tokens` 降至 `2k-4k tokens`
- 首 token 延迟显著下降
- 整体响应速度更稳定
- token 成本显著下降
- 模型更少受旧上下文污染
- “换一批”与解释型场景更稳
- 上下文结构更清晰，便于长期维护

## 14. 最重要的五项立即行动

如果只做收益最高的五项，优先级如下：

1. 不再把完整历史 `messages` 发给 `/chat/completions`
2. search tool 只返回候选摘要，不返回完整候选对象
3. `page_summary.result_cards` 只保留 `profile_id + reason_summary + compatibility_summary`
4. `recent_timeline_summary` 改成一句后端摘要
5. system prompt 拆短，不再每轮发完整规则大全

## 15. 与现有代码的直接对应关系

本方案重点影响以下位置：

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
  - prompt 组装
  - runtime payload 结构
  - Agents SDK session 输入策略
- `external-systems/partner-discovery-system/discovery_system/service_context.py`
  - `build_runtime_context()`
  - `build_page_summary()`
  - `build_last_search_summary()`
  - `build_visible_action_summaries()`
- `external-systems/partner-discovery-system/discovery_system/service.py`
  - runtime input 组装
  - tool 调用后的上下文沉淀
- search tool 相关返回路径
  - search 结果对模型返回的摘要层

## 16. 最终结论

这次优化的本质，不是“把 prompt 写得更短一点”，而是把发现页从：

- 原始历史堆叠
- 重状态反复重发
- 大对象直接喂模型

改造成：

- 当前事实最小注入
- 历史通过摘要保留连续感
- 工具结果只给模型最小决策信息

一句话总结：

发现页 agent 以后应该每轮只看到“当前要做决策所必需的事实”，而不是继续背着一整本运行日志去说下一句话。
