# Section 13.1 Mainline Architecture Improvement Plan

本文档对应 [`SYSTEM_DOC.md`](../SYSTEM_DOC.md) 中 `13.1 模块数量多，产品边界已经接近平台化` 的展开方案。

目标不是减少模块数量，也不是立刻拆服务，而是先把系统重新围绕唯一主线组织起来，降低跨域耦合。

## 1. 问题定义

当前系统同时承载：

- `discovery`
- `partner_search`
- `recommendation`
- `matchmaking`
- `chat`
- `auth`
- `verification`
- `review`
- `risk`
- `persona`
- `ops`

问题不在于模块本身多，而在于这些模块正在共同参与产品主流程，导致：

- 一个业务改动会扩散到多个域
- 很难快速判断某个核心状态到底由谁负责
- 联调、发布、排障都依赖跨系统理解

这说明系统复杂度的主要来源，已经从“单模块内部复杂”转向“模块之间协作复杂”。

## 2. 主线定义

当前系统必须先承认只有一条最核心业务线：

`找对象 -> 建立连接 -> 聊天`

翻译成系统链路就是：

`discovery -> recommendation/search -> matchmaking/relationship -> chat`

后续所有架构判断，都应优先服务这条主线。

判断原则：

- 直接推进这条主线的能力，属于主链路域
- 只提供放行、拦截、校验、辅助决策的能力，属于支撑域

## 3. 目标架构

建议将系统明确分为三层。

### 3.1 主链路域

- `Discovery`
- `Recommendation/Search`
- `Relationship/Matchmaking`
- `Chat`

这些域负责把用户从“表达需求”推进到“进入聊天”。

### 3.2 支撑域

- `Auth`
- `Verification`
- `Review`
- `Risk/Safety`
- `Persona/Profile`
- `Async Jobs / Scheduler / Observability`
- `Ops Tools`

这些域不定义主流程，只为主流程提供约束和辅助。

### 3.3 接入层

- `partner-http-gateway`
- `frontend/her-app`

接入层负责承接请求、协议整形、路由和展示，不承担深业务真相判断。

## 4. 责任重划

### 4.1 Discovery

对应：

- `external-systems/partner-discovery-system`

职责：

- 采集用户需求
- 维护发现页会话
- 输出可展示的 `view`
- 在合适时机触发搜索

不负责：

- 推荐投递
- 关系建立
- 聊天权限判断

### 4.2 Search / Recommendation

对应：

- `partner_search`
- `external-systems/partner-recommendation-system`

职责分层：

- `partner_search` 只回答“这次按条件搜到谁”
- `recommendation_system` 只负责“给谁推、何时推、推荐历史、用户对推荐的动作”

不负责：

- 关系是否成立
- 聊天是否开放

### 4.3 Relationship / Matchmaking

对应：

- `external-systems/partner-matchmaking-system`
- `match_domain`

职责：

- 定义双方是否进入关系
- 维护 pair / case / relationship 推进状态
- 成为“是否已建立连接”的真相源

不负责：

- 推荐卡策略
- 聊天消息能力

### 4.4 Chat

对应：

- `external-systems/partner-chat-system`

职责：

- 会话创建
- 消息发送
- 聊天维护
- 聊天相关时间线与摘要

约束：

- `chat` 只处理“已建立连接后的沟通”
- 是否允许开聊，不应由 `chat` 自己重新定义推荐或撮合逻辑

### 4.5 Gateway

对应：

- `external-systems/partner-http-gateway`

职责：

- 鉴权
- 路由
- 参数校验
- 限流
- `trace_id`
- 少量协议整形

不负责：

- 深业务编排
- 跨域真相判断
- 主流程状态归因

## 5. 四个真相源

为避免多个模块共同维护同一事实，建议明确四个真相源。

### 5.1 用户需求真相源

- 当前会话态需求：`discovery`
- 长期偏好与画像沉淀：`persona/profile`

### 5.2 推荐真相源

- 是否生成推荐
- 是否已投递
- 用户对推荐做了什么动作

以上统一由 `recommendation` 负责。

### 5.3 关系真相源

- 双方是否已建立连接
- 当前 relationship / pair / case 到了哪一步

以上统一由 `matchmaking` 负责。

### 5.4 聊天真相源

- 是否已创建会话
- 消息内容
- 会话维护状态

以上统一由 `chat` 负责。

可执行判断：

- “有没有被推荐过”只查 `recommendation`
- “有没有建立关系”只查 `matchmaking`
- “能不能聊、聊了什么”只查 `chat`

## 6. 代码改造原则

### 6.1 recommendation 只管推荐

允许：

- 搜索候选人
- 生成推荐结果
- 记录推荐投递和用户动作

不允许继续扩大到：

- 决定聊天开放规则
- 持有 relationship 真相

### 6.2 matchmaking 只管连接建立

允许：

- 建立 pair / case
- 推进 relationship 状态

不允许继续扩大到：

- 接管推荐策略
- 接管聊天实现

### 6.3 chat 只管连接后的沟通

允许：

- 开会话
- 发消息
- 维护聊天相关时间线

不允许继续扩大到：

- 重新判断推荐是否有效
- 重新定义撮合是否成立

### 6.4 gateway 退回接入层

允许：

- 接请求
- 校验身份
- 路由到正确域

不允许继续扩大到：

- 拼装过深业务规则
- 变成隐式业务中枢

## 7. 分阶段改进方案

### 第一阶段：定主线和 owner

目标：

- 固定唯一主线：`找对象 -> 建立连接 -> 聊天`
- 为 `discovery`、`recommendation`、`matchmaking`、`chat` 明确 owner
- 为推荐、关系、聊天分别明确真相源

产出：

- 一张主链路状态图
- 一张领域职责表
- 一张跨域依赖表

完成标准：

- 每个核心状态都能回答“谁说了算”

### 第二阶段：收敛 recommendation -> matchmaking -> chat 交接边界

目标：

- recommendation 不再承担 relationship 判断
- matchmaking 成为连接建立唯一真相源
- chat 只能在 relationship 满足条件后开聊

建议动作：

- 审查 `recommendation_system/service.py`
- 审查 `matchmaking_system/service.py`
- 审查 `chat_system/service.py`
- 去掉重复状态判断和跨域猜测逻辑

完成标准：

- “推荐结束后如何进入关系”
- “建立关系后如何开放聊天”

这两个问题分别只有一个主 owner。

### 第三阶段：收敛 Gateway

目标：

- 让 Gateway 退出深业务编排角色

建议动作：

- 审查 `gateway/app.py`
- 审查 `gateway/*routes.py`
- 审查 `gateway/*jsonrpc.py`
- 把跨域业务判断逐步迁回对应主域

Gateway 保留：

- 鉴权
- 限流
- 参数转换
- 路由分发
- 统一追踪

完成标准：

- 网关知道把请求交给谁
- 网关不负责定义主流程真相

### 第四阶段：把主链路显式事件化

当前仓库已具备基础设施：

- `match_domain/outbox.py`
- `async_jobs`
- `task_scheduler`

建议先建立轻量领域事件，而不是立刻引入重型总线。

建议事件：

- `discovery.criteria_confirmed`
- `recommendation.created`
- `recommendation.delivered`
- `relationship.connected`
- `chat.conversation_opened`
- `chat.message_sent`
- `risk.block_applied`

目标：

- 让跨域联动从“隐式调用”变成“显式事件”
- 让排障和漏斗分析有清晰链路

完成标准：

- 能追踪一个用户从找对象到进入聊天的完整路径

### 第五阶段：把支撑域改成能力服务

目标：

- 让审核、认证、风控、画像输出结果，而不是反向主导主流程

改法：

- `verification` 输出认证结果
- `review` 输出审核结果
- `risk` 输出放行 / 限制 / 拦截结果
- 主链路域消费这些结果

完成标准：

- 支撑域只提供约束
- 主链路仍由主域推进

## 8. 建议优先级

### P0

- 固定主线
- 固定主域 owner
- 固定真相源

### P1

- 收 recommendation -> matchmaking -> chat 三段交接边界

### P2

- 收 Gateway 职责

### P3

- 主链路事件化

### P4

- 支撑域服务化

## 9. 验收标准

如果 `13.1` 的治理有效，系统应满足：

1. 主链路可以被稳定画成一条线
2. 每个核心状态只有一个主 owner
3. 推荐、关系、聊天都存在明确真相源
4. Gateway 不再承担深业务中枢角色
5. 支撑域只能放行、拦截、校验，不重写主流程

## 10. 最短执行路径

第 1 周：

- 确认主线
- 确认主域职责
- 确认真相源

第 2 周：

- 盘点 `gateway` 与各主域中的跨域耦合点
- 列出应该删除、迁回或封装的判断逻辑

第 3-4 周：

- 优先收 recommendation -> matchmaking -> chat 的交接边界
- 确保“建立连接后才能聊天”成为统一规则

第 2 个月：

- 基于 outbox / async jobs 建立主链路事件
- 建立端到端主链路监控

## 11. 一句话结论

`13.1` 的改进，不是先拆服务，也不是先改一堆代码，而是先固定唯一主线，再让每个系统只负责主线中的一段，最后把其他模块降回支撑角色。
