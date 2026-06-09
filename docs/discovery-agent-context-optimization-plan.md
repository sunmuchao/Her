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

## 17. 代码落地任务清单

下面的任务清单按“先止血，再重构”的顺序组织，直接对应到当前代码文件。

### T1. 给 discovery 请求增加上下文体积观测

状态：`部分完成`

目标：

- 在不改逻辑的前提下，先能量化每轮请求大小
- 为后续裁剪提供基线

文件：

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`

任务：

1. 在真正调用 `Runner.run_sync(...)` 前，记录：
   - `messages` 条数
   - prompt 总字符数
   - `response_format` 字符数
   - `tools` 字符数
2. 增加 discovery 专用 debug/audit 日志字段，便于后续对比裁剪前后变化。
3. 对单轮上下文体积设置告警阈值，例如：
   - `> 4000 tokens` 记 warning
   - `> 8000 tokens` 记 error

验收标准：

- 每轮 discovery agent 调用都能在日志中看到上下文体积统计
- 能快速判断是 `messages`、`tools` 还是 `schema` 过重

当前进展：

- 已完成：在 `agent_runtime.py` 中记录 `instructions/input/schema/tools/total` 体积，并按阈值输出 `DEBUG/WARNING/ERROR`
- 已完成：新增 [discovery_context_size_report.py](/Users/sunmuchao/Downloads/Her/scripts/discovery_context_size_report.py) 脚本，可输出代表性场景的体积统计
- 未完成：尚未单独记录 `messages` 条数
- 未完成：尚未打通 completion tokens / latency 的统一观测链路

### T2. 阻止长历史 `messages` 持续累积

状态：`已完成`

目标：

- 不再把大量历史消息原样发回 `/chat/completions`

文件：

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
- `external-systems/partner-discovery-system/discovery_system/service.py`

任务：

1. 梳理当前 `run_input.agent_session` 的来源和生命周期。
2. 确认是否由 Agents SDK 自动携带了长历史 transcript。
3. 将输入模式从“历史 message 累计”改成：
   - 当前 system prompt
   - 当前轮 event payload
   - 必要的短摘要
4. 如果必须保留 session，则引入“摘要替换”策略，而不是保留全部原始 turn。

验收标准：

- 请求中的 `messages` 数量不再随会话无限增长
- 正常多轮会话下，`messages` 数量应稳定在一个小范围内

当前进展：

- 已完成：`Runner.run_sync(...)` 不再传 `session=run_input.agent_session`
- 已完成：Agents SDK 长历史 transcript 不再自动回灌到 discovery prompt

### T3. 删除重复 `note`，并将其合并进短版 prompt

状态：`已完成`

目标：

- 移除每轮 payload 中重复发送的固定说明文字

文件：

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`

任务：

1. 从 `_build_runtime_prompt()` 中删除 payload 里的 `note` 字段。
2. 把确实必要的约束收敛进精简版 system prompt。
3. 检查是否有其他重复性固定说明同时存在于：
   - system prompt
   - `note`
   - tool schema

验收标准：

- 单轮 payload 固定长度下降
- 同一条规则不再在多处重复出现

当前进展：

- 已完成：`_build_runtime_prompt()` 中已删除 payload 的 `note`
- 已完成：相关约束已收敛进 prompt

### T4. 精简 `build_runtime_context()` 输出结构

状态：`部分完成`

目标：

- 把当前 `official_context` 改造成真正的最小决策状态

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`
- `external-systems/partner-discovery-system/discovery_system/service.py`

任务：

1. 将 `build_runtime_context()` 产物拆成更清晰的子结构：
   - `session`
   - `user_profile`
   - `current_results`
   - `visible_actions`
   - `last_search`
   - `memory_summary`
2. 删除不是当前轮决策必需的字段。
3. 为每个子结构设定体积上限和允许字段白名单。

验收标准：

- `runtime_context` 字段结构可读、可控
- 不再出现“顺手把整个页面模型塞进去”的情况

当前进展：

- 已完成：`runtime_context` 已大幅压缩，候选卡、timeline、action、last_search 都已瘦身
- 未完成：尚未完全重构成文档定义的标准子结构：
  - `session`
  - `user_profile`
  - `current_results`
  - `visible_actions`
  - `last_search`
  - `memory_summary`

### T5. 重写 `build_page_summary()`，去掉重型候选卡上下文

状态：`已完成`

目标：

- 切掉当前最大头之一：`result_cards[*].personality_match_context`

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`

任务：

1. 将 `build_page_summary()` 改造成极简 `current_results` 视图。
2. 每张卡只保留：
   - `profile_id`
   - `title`
   - `reason_summary`
   - 可选一条 `compatibility_summary`
3. 删除：
   - `personality_match_context`
   - `personality_reasoning` 原始对象
   - `personality_availability`
   - 非必要展示字段

验收标准：

- 单张卡片上下文体积下降到当前的很小一部分
- 模型仍能回答“为什么推荐她”

当前进展：

- 已完成：`build_page_summary()` 已仅保留 `profile_id/title/reason_summary/compatibility_summary`
- 已完成：候选卡中的原始大测评对象不再直接进入 prompt

### T6. 增加候选人“兼容性摘要”生成层

状态：`已完成`

目标：

- 不再把原始测评对象交给模型
- 改为后端先生产一句简短兼容性摘要

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`
- 如有需要，补充到 `service_integrations.py` 或新 helper 文件

任务：

1. 设计 `compatibility_summary` 生成规则。
2. 只保留一条短摘要，例如：
   - “生活节奏接近，价值观偏长期投入”
   - “MBTI 节奏接近，依恋更稳定”
3. 确保这层是结构化压缩，而不是把原始对象重新包装成长文本。

验收标准：

- 用户追问“为什么推荐”时，模型可直接使用摘要回答
- 不再需要完整 personality nested object 进入 prompt

当前进展：

- 已完成：新增 `compatibility_summary`
- 已完成：模型可基于兼容性摘要和压缩信号解释推荐理由

### T7. 精简 `build_last_search_summary()`

状态：`已完成`

目标：

- 让最近一次搜索只保留“当前决策需要知道的结果”

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`

任务：

1. 将 `last_search_summary` 限制为：
   - `status`
   - `result_count`
   - `criteria_summary`
   - `error_code` / `short_error`
2. 删除：
   - 完整 `criteria`
   - `personality_trace`
   - `source`
   - 其他调试型字段

验收标准：

- `last_search_summary` 只描述“结果状态”，不再承载大对象

当前进展：

- 已完成：`last_search_summary` 已压缩为 `status/result_count/criteria_summary/error`

### T8. 精简 `build_visible_action_summaries()`

状态：`已完成`

目标：

- 页面 action 对模型只暴露语义，不暴露 UI/存储细节

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`

任务：

1. `visible_actions` 只保留：
   - `label`
   - `kind`
   - 必要参数
2. 删除：
   - `action_id`
   - 非必要风格和内部 hint
3. 对 action payload 做字段白名单约束。

验收标准：

- action 语义足够模型理解
- action 结构明显缩短

当前进展：

- 已完成：`visible_actions` 已去掉 `action_id`
- 已完成：当前只保留 `label/kind/hint`，且 `hint` 已做字段白名单收缩

### T9. 用后端摘要替换 `recent_timeline_summary`

状态：`部分完成`

目标：

- 不再把最近几条原始 timeline item 每轮传给模型

文件：

- `external-systems/partner-discovery-system/discovery_system/service_context.py`
- `external-systems/partner-discovery-system/discovery_system/service.py`

任务：

1. 引入：
   - `stable_preferences_summary`
   - `recent_feedback_summary`
   - `recent_conversation_summary`
2. `recent_timeline_summary` 从 list 改为几个短摘要字段。
3. 先用规则摘要实现，必要时再考虑小模型摘要。

验收标准：

- 多轮会话仍有连续感
- 不再发送逐条历史 timeline

当前进展：

- 已完成：`recent_timeline_summary` 已从原始大结构压成轻量列表摘要
- 未完成：尚未真正落成文档中定义的三类摘要字段：
  - `stable_preferences_summary`
  - `recent_feedback_summary`
  - `recent_conversation_summary`

### T10. search tool 返回增加“模型摘要层”

状态：`已完成`

目标：

- 切断完整 search 结果进入模型上下文的路径

文件：

- `external-systems/partner-discovery-system/discovery_system/service.py`
- `external-systems/partner-discovery-system/discovery_system/service_integrations.py`
- search tool 相关返回拼装位置

任务：

1. 保留后端完整 search 结果用于渲染和持久化。
2. 新增“模型可见结果摘要层”，只返回：
   - `has_match`
   - `result_count`
   - `results: [{profile_id, summary}]`
3. 检查 Agents SDK tool result 是否会自动把完整结果写回 transcript；若会，需改成只把摘要结果返回给模型。

验收标准：

- tool result 不再出现单条 10k+ tokens 的情况
- 模型依然能正确选择候选人和生成简短说明

当前进展：

- 已完成：search tool 现在只向模型返回摘要结果
- 已完成：完整 search response 仍保留在后端供渲染与业务使用

### T11. system prompt 拆分为 `core + mode`

状态：`已完成`

目标：

- 降低固定 prompt 成本

文件：

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
- 如有需要，可把 prompt 文本拆到单独文件

任务：

1. 提炼一个稳定短版 `core prompt`。
2. 将“换一批反馈闭环”“测评推荐”等重规则做成按场景拼接的 `mode prompt`。
3. 避免把已经由 schema 强约束的内容继续重复写进 prompt。

验收标准：

- 固定 prompt 明显缩短
- 不同场景下仅注入必要规则

当前进展：

- 已完成：system prompt 已改成 `core + mode`
- 已完成：测评推荐与换一批反馈闭环只在相关场景注入

### T12. 为上下文结构写回归测试

状态：`部分完成`

目标：

- 避免未来又把大对象重新塞回 prompt

文件：

- `external-systems/partner-discovery-system/tests/`

任务：

1. 为 `_build_runtime_prompt()` 或其上层输入结构增加测试。
2. 断言以下内容不会再出现在模型输入中：
   - 完整 `personality_match_context`
   - 完整 search result 大对象
   - 长 history transcript
3. 增加体积阈值测试，例如：
   - 单轮 payload 不超过设定字符数

验收标准：

- 以后改 discovery 上下文时，测试能第一时间发现回退

当前进展：

- 已完成：补充了 discovery runtime 相关回归测试
- 已完成：覆盖了不传 session history、不传完整 search 大对象、上下文字段压缩后的关键断言
- 未完成：尚未补充明确的上下文体积阈值测试

### T13. 增加性能对比验证

状态：`部分完成`

目标：

- 用数据证明优化生效

文件：

- 可新增到 `scripts/` 或现有 perf 脚本

任务：

1. 固定 3-5 个 discovery 场景：
   - 首次推荐
   - 换一批
   - 点击 rejection feedback
   - 追问“为什么推荐她”
2. 对比优化前后：
   - prompt tokens
   - completion tokens
   - 首 token 延迟
   - 总响应时长

验收标准：

- 能量化展示上下文缩减和性能收益

当前进展：

- 已完成：新增 [discovery_context_size_report.py](/Users/sunmuchao/Downloads/Her/scripts/discovery_context_size_report.py)
- 已完成：可量化 4 类代表场景的 `instructions/input/schema/tools/total` 体积
- 已完成：discovery runtime 日志已记录 `elapsed_ms` 与 Agents SDK usage（`input_tokens/output_tokens/total_tokens/requests`）
- 未完成：尚未自动输出优化前后对比
- 未完成：尚未自动固化“优化前后”对比报告
- 未完成：尚未记录真实 `first_token_latency_ms`

## 18. 推荐实施顺序

建议按以下顺序推进：

1. `T1` 先加观测，拿到可对比基线
2. `T2 + T10` 先切历史和大 tool result，立刻止血
3. `T5 + T7 + T8 + T9` 重构 `service_context.py`
4. `T3 + T11` 缩 prompt
5. `T12 + T13` 补回归和性能验证

如果资源有限，收益最高的最小集合是：

- `T2`
- `T5`
- `T9`
- `T10`
- `T11`
