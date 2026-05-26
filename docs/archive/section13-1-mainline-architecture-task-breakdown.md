# Section 13.1 Mainline Architecture Task Breakdown

本文档是 [`section13-1-mainline-architecture-improvement-plan.md`](./section13-1-mainline-architecture-improvement-plan.md) 的执行拆解版本。

目标是把 `13.1 模块数量多，产品边界已经接近平台化` 的治理方案，拆成可以分配、排期、验收的具体任务。

## 1. 总体拆解方式

按五个阶段拆解：

1. 主线与 owner 对齐
2. recommendation -> matchmaking -> chat 边界收敛
3. Gateway 收敛为接入层
4. 主链路事件化
5. 支撑域服务化

每个阶段都包含：

- 任务目标
- 具体任务
- 涉及文件
- 交付物
- 验收标准

## 2. 阶段一：主线与 owner 对齐

### 任务 1.1：固化唯一主线

目标：

- 把系统唯一主线固定为 `找对象 -> 建立连接 -> 聊天`

具体任务：

- 在系统文档中明确主线定义
- 统一术语：`recommendation` 表示推荐，`relationship/matchmaking` 表示连接建立，`chat` 表示进入沟通
- 删除或标注那些会让辅助域看起来像主流程的描述

涉及文件：

- `SYSTEM_DOC.md`
- `archive/section13-1-mainline-architecture-improvement-plan.md`

交付物：

- 一版统一术语后的主线定义

验收标准：

- 团队讨论“主流程”时不再出现多套说法

### 任务 1.2：定义主域职责表

目标：

- 为 `discovery`、`recommendation/search`、`matchmaking`、`chat` 建立清晰 owner 表

具体任务：

- 为每个主域补充“负责什么 / 不负责什么”
- 明确辅助域只能放行、拦截、校验、辅助，不定义主流程

涉及文件：

- `archive/section13-1-mainline-architecture-improvement-plan.md`
- 可选新增 `docs/permission-matrix.md` 的补充章节

交付物：

- 一张领域职责表

验收标准：

- 对任一功能点，都能回答“主 owner 是谁”

### 任务 1.3：定义四个真相源

目标：

- 固定推荐、关系、聊天、需求的唯一真相源

具体任务：

- 明确“有没有被推荐过”查 recommendation
- 明确“有没有建立关系”查 matchmaking
- 明确“能不能聊、聊了什么”查 chat
- 明确“当前会话态需求”查 discovery，“长期偏好”查 persona/profile

涉及文件：

- `archive/section13-1-mainline-architecture-improvement-plan.md`
- `external-systems/partner-http-gateway/API_CONTRACT.md`

交付物：

- 一张真相源说明表

验收标准：

- 排障时不需要跨多个系统拼一个基础事实

## 3. 阶段二：recommendation -> matchmaking -> chat 边界收敛

### 任务 2.1：盘点 recommendation 域越界逻辑

目标：

- 找出 recommendation 域中不该承担的 relationship/chat 判断

具体任务：

- 审查推荐服务是否直接持有 relationship 语义
- 审查推荐动作、投递、proxy intro 流程里是否混入“是否可聊”的判断
- 列出应迁移到 matchmaking 或 chat 的逻辑

涉及文件：

- `external-systems/partner-recommendation-system/recommendation_system/service.py`
- `external-systems/partner-recommendation-system/recommendation_system/proxy_intro.py`
- `external-systems/partner-recommendation-system/recommendation_system/outbox.py`
- `external-systems/partner-recommendation-system/tests/test_recommendation_system.py`

交付物：

- 一份 recommendation 越界逻辑清单

验收标准：

- recommendation 域只对“推荐是否生成、是否投递、用户做了什么动作”负责

### 任务 2.2：定义 relationship 建立统一入口

目标：

- 把“什么时候算建立连接”收敛到 matchmaking 域

具体任务：

- 梳理 pair / case / relationship 状态转换
- 定义 recommendation 进入 relationship 的标准入口
- 明确 proxy intro、系统 pair、case 创建之间的责任关系

涉及文件：

- `external-systems/partner-matchmaking-system/matchmaking_system/service.py`
- `external-systems/partner-matchmaking-system/matchmaking_system/storage.py`
- `match_domain/model.py`
- `match_domain/case_events.py`
- `tests/test_match_domain.py`

交付物：

- 一版 relationship 状态机说明
- 一版 recommendation -> matchmaking 交接契约

验收标准：

- “这两个人是否已建立连接”只能由 matchmaking 回答

### 任务 2.3：定义 chat 开聊准入规则

目标：

- 让 chat 只在 relationship 满足条件后开聊

具体任务：

- 审查 chat 当前创建会话和发送消息前的准入检查
- 把“是否允许开聊”收敛成对 relationship/risk 结果的依赖
- 去掉 chat 内部重复定义 recommendation 或 matchmaking 状态的逻辑

涉及文件：

- `external-systems/partner-chat-system/chat_system/service.py`
- `external-systems/partner-chat-system/chat_system/conversations.py`
- `external-systems/partner-chat-system/chat_system/timeline.py`
- `external-systems/partner-chat-system/chat_system/risk.py`
- `external-systems/partner-chat-system/tests/test_chat_system.py`
- `external-systems/partner-http-gateway/gateway/chat_access.py`

交付物：

- 一版 chat 准入规则说明
- 一版 relationship -> chat 开聊契约

验收标准：

- chat 不再自己发明“什么情况下能聊”

### 任务 2.4：补主链路交接测试

目标：

- 用测试固化 recommendation -> matchmaking -> chat 的边界

具体任务：

- 新增“推荐后进入关系”的回归测试
- 新增“未建立关系不能聊天”的回归测试
- 新增“建立关系后可以聊天”的回归测试

涉及文件：

- `external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py`
- `external-systems/partner-http-gateway/gateway_tests/test_end_to_end_regression.py`
- `external-systems/partner-matchmaking-system/tests/test_matchmaking_system.py`
- `external-systems/partner-chat-system/tests/test_chat_conversations.py`

交付物：

- 一组主链路边界测试

验收标准：

- 推荐、关系、聊天三段交接都有自动化保护

## 4. 阶段三：Gateway 收敛为接入层

### 任务 3.1：盘点 Gateway 内的深业务判断

目标：

- 找出 Gateway 中不该存在的跨域业务编排和真相判断

具体任务：

- 审查路由层是否拼装了 recommendation / matchmaking / chat 的业务状态
- 标记哪些逻辑只是参数适配，哪些已经是业务编排

涉及文件：

- `external-systems/partner-http-gateway/gateway/app.py`
- `external-systems/partner-http-gateway/gateway/recommendation_routes.py`
- `external-systems/partner-http-gateway/gateway/matchmaking_routes.py`
- `external-systems/partner-http-gateway/gateway/chat_routes.py`
- `external-systems/partner-http-gateway/gateway/chat_access.py`

交付物：

- 一份 Gateway 越界逻辑清单

验收标准：

- 能明确区分“接入逻辑”和“业务逻辑”

### 任务 3.2：把跨域编排迁回主域

目标：

- 让主域重新掌握各自的业务判断

具体任务：

- 将 recommendation 真相判断迁回 recommendation
- 将 relationship 真相判断迁回 matchmaking
- 将 chat 准入与消息相关判断迁回 chat

涉及文件：

- `external-systems/partner-http-gateway/gateway/recommendation_jsonrpc.py`
- `external-systems/partner-http-gateway/gateway/matchmaking_jsonrpc.py`
- `external-systems/partner-http-gateway/gateway/chat_jsonrpc.py`
- 对应各主域 `service.py`

交付物：

- 一版瘦身后的 Gateway 调用边界

验收标准：

- Gateway 只知道“请求该交给谁”，不负责“主流程怎么判”

### 任务 3.3：更新 API 契约说明

目标：

- 让外部调用方看到收敛后的边界

具体任务：

- 更新 Gateway 契约文档中的状态口径
- 补充 recommendation、relationship、chat 的真相源说明

涉及文件：

- `external-systems/partner-http-gateway/API_CONTRACT.md`

交付物：

- 更新后的 API 契约文档

验收标准：

- 外部调用方可以看文档判断该向哪个域查询什么信息

## 5. 阶段四：主链路事件化

### 任务 4.1：定义主链路领域事件

目标：

- 为主链路建立统一事件名和载荷结构

具体任务：

- 固定事件名
- 明确每个事件的 producer 和 consumer
- 明确最小必要字段：`trace_id`、`requester_id`、`profile_id`、`case_id`、`occurred_at`

建议事件：

- `discovery.criteria_confirmed`
- `recommendation.created`
- `recommendation.delivered`
- `relationship.connected`
- `chat.conversation_opened`
- `chat.message_sent`
- `risk.block_applied`

涉及文件：

- `match_domain/outbox.py`
- `match_domain/outbox_runtime.py`
- `match_domain/case_events.py`
- `external-systems/partner-recommendation-system/recommendation_system/outbox.py`
- `external-systems/partner-matchmaking-system/matchmaking_system/outbox.py`
- `external-systems/partner-chat-system/chat_system/events.py`

交付物：

- 一版主链路事件清单
- 一版事件载荷规范

验收标准：

- 跨域联动可以基于统一事件名理解

### 任务 4.2：补事件生产与消费链路

目标：

- 让主链路关键动作都能发出事件并被消费

具体任务：

- recommendation 生成/投递时发事件
- relationship 建立时发事件
- chat 开会话和发消息时发事件
- 对接现有 async jobs / outbox worker

涉及文件：

- `external-systems/partner-recommendation-system/recommendation_system/async_tasks.py`
- `external-systems/partner-matchmaking-system/matchmaking_system/async_tasks.py`
- `external-systems/partner-chat-system/chat_system/async_tasks.py`
- `external-systems/partner-chat-system/chat_system/outbox_consumer.py`
- `external-systems/partner-chat-system/chat_system/outbox.py`

交付物：

- 一条能跑通的主链路事件流

验收标准：

- 至少能追踪一个用户从推荐到聊天的事件序列

### 任务 4.3：补端到端链路监控

目标：

- 让主链路可观测

具体任务：

- 为关键事件补 trace_id 串联
- 建立按主链路节点统计的漏斗
- 建立“卡在哪一段”的排障视图

涉及文件：

- `observability/`
- `external-systems/partner-http-gateway/gateway/logging_setup.py`
- `external-systems/partner-http-gateway/gateway_tests/test_end_to_end_regression.py`

交付物：

- 一版主链路漏斗和链路日志规范

验收标准：

- 能回答“用户从找对象到聊天，卡在哪一步”

## 6. 阶段五：支撑域服务化

### 任务 5.1：收敛 verification 输出

目标：

- 让 verification 只输出认证结果，不定义主流程

具体任务：

- 梳理认证结果类型
- 统一向主链路输出认证等级或状态

涉及文件：

- `external-systems/partner-chat-system/chat_system/verification.py`
- `external-systems/partner-chat-system/chat_system/verification_scoring.py`
- `external-systems/partner-http-gateway/gateway/verification_routes.py`

交付物：

- 一版 verification 输出契约

验收标准：

- 主链路消费 verification 结果，而不是复写 verification 逻辑

### 任务 5.2：收敛 risk 输出

目标：

- 让 risk 只输出放行、限制、拦截结果

具体任务：

- 统一 risk 判定结果结构
- 明确 recommendation、matchmaking、chat 分别如何消费 risk 结果

涉及文件：

- `external-systems/partner-chat-system/chat_system/risk.py`
- `external-systems/partner-chat-system/chat_system/moderation_ops.py`
- `external-systems/partner-http-gateway/gateway/chat_safety_routes.py`

交付物：

- 一版 risk 输出契约

验收标准：

- risk 是信号源，不是流程 owner

### 任务 5.3：收敛 profile review 输出

目标：

- 让 review 只输出审核结果

具体任务：

- 梳理 profile review、photo review 的结果枚举
- 统一主链路对审核结果的消费口径

涉及文件：

- `external-systems/partner-chat-system/chat_system/profile_reviews.py`
- `external-systems/partner-chat-system/chat_system/profile_review_rules.py`
- `external-systems/partner-chat-system/chat_system/verification_photo_review.py`

交付物：

- 一版 review 输出契约

验收标准：

- review 不再分散嵌入多个主域逻辑

### 任务 5.4：收敛 persona/profile 输出

目标：

- 让 persona/profile 成为“长期偏好与资料事实源”，而不是主流程编排者

具体任务：

- 明确 persona 负责长期偏好沉淀
- 明确 discovery 负责当前会话偏好
- 明确 recommendation/search 只消费 persona/profile 结果

涉及文件：

- `persona_memory_sync/api.py`
- `persona_memory_sync/persona_memory_engine.py`
- `profile_service/api.py`
- `profile_service/persona_bridge.py`
- `partner_search/api.py`

交付物：

- 一版 persona/profile 使用边界说明

验收标准：

- persona/profile 不再隐式承担主流程控制

## 7. 并行安排建议

可以并行的任务：

- 阶段一全部任务
- `2.1` recommendation 越界盘点
- `3.1` Gateway 越界盘点
- `4.1` 事件定义
- `5.1` 到 `5.4` 支撑域输出梳理

建议串行的关键路径：

1. `1.1` -> `1.2` -> `1.3`
2. `2.2` -> `2.3` -> `2.4`
3. `3.1` -> `3.2` -> `3.3`
4. `4.1` -> `4.2` -> `4.3`

## 8. 建议里程碑

### 里程碑 M1：主线定义完成

完成条件：

- 阶段一完成

### 里程碑 M2：主链路边界完成

完成条件：

- `2.1` 到 `2.4` 完成
- recommendation、matchmaking、chat 各自只持有自己的核心事实

### 里程碑 M3：Gateway 瘦身完成

完成条件：

- 阶段三完成

### 里程碑 M4：主链路可追踪

完成条件：

- 阶段四完成

### 里程碑 M5：支撑域完成服务化收敛

完成条件：

- 阶段五完成

## 9. 最终验收口径

整个 `13.1` 任务拆解完成后，应满足：

1. 系统只围绕一条主线组织：`找对象 -> 建立连接 -> 聊天`
2. recommendation、matchmaking、chat 各自只有一个明确真相源
3. Gateway 不再承担深业务编排
4. recommendation -> matchmaking -> chat 有明确交接契约和自动化测试
5. verification、risk、review、persona/profile 都退回支撑角色

## 10. 近期执行优先级

下面这部分用于把前面的阶段任务压缩成更适合排期的执行清单。

原则：

- `P0` 解决“主线不清、真相源不清、边界不清”
- `P1` 解决“主链路交接不稳、Gateway 过重”
- `P2` 解决“跨域可观测性不足、支撑域反向长成流程域”

### P0：先把主线和边界定死

目标：

- 让团队先对“系统最核心在做什么”达成一致
- 让 recommendation、matchmaking、chat 的边界先稳定下来

包含任务：

1. `1.1` 固化唯一主线
2. `1.2` 定义主域职责表
3. `1.3` 定义四个真相源
4. `2.1` 盘点 recommendation 域越界逻辑
5. `2.2` 定义 relationship 建立统一入口
6. `2.3` 定义 chat 开聊准入规则

建议产出：

- 一张主链路图
- 一张主域职责表
- 一张真相源表
- 一张 recommendation -> matchmaking -> chat 交接图

建议涉及文件：

- `SYSTEM_DOC.md`
- `archive/section13-1-mainline-architecture-improvement-plan.md`
- `external-systems/partner-recommendation-system/recommendation_system/service.py`
- `external-systems/partner-recommendation-system/recommendation_system/proxy_intro.py`
- `external-systems/partner-matchmaking-system/matchmaking_system/service.py`
- `external-systems/partner-chat-system/chat_system/service.py`
- `external-systems/partner-chat-system/chat_system/conversations.py`
- `external-systems/partner-http-gateway/gateway/chat_access.py`
- `match_domain/model.py`

验收标准：

- “推没推”只问 recommendation
- “连没连上”只问 matchmaking
- “能不能聊、聊了什么”只问 chat
- chat 的开聊规则明确依赖 relationship/risk，而不是自行定义

### P1：把主链路交接固化成代码和测试

目标：

- 让 recommendation -> matchmaking -> chat 的交接方式可运行、可回归
- 把 Gateway 从隐式业务中枢降回接入层

包含任务：

1. `2.4` 补主链路交接测试
2. `3.1` 盘点 Gateway 内的深业务判断
3. `3.2` 把跨域编排迁回主域
4. `3.3` 更新 API 契约说明

建议产出：

- 一组主链路回归测试
- 一份 Gateway 越界逻辑清单
- 一版瘦身后的 Gateway 边界说明

建议涉及文件：

- `external-systems/partner-http-gateway/gateway/app.py`
- `external-systems/partner-http-gateway/gateway/recommendation_routes.py`
- `external-systems/partner-http-gateway/gateway/matchmaking_routes.py`
- `external-systems/partner-http-gateway/gateway/chat_routes.py`
- `external-systems/partner-http-gateway/gateway/recommendation_jsonrpc.py`
- `external-systems/partner-http-gateway/gateway/matchmaking_jsonrpc.py`
- `external-systems/partner-http-gateway/gateway/chat_jsonrpc.py`
- `external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py`
- `external-systems/partner-http-gateway/gateway_tests/test_end_to_end_regression.py`
- `external-systems/partner-matchmaking-system/tests/test_matchmaking_system.py`
- `external-systems/partner-chat-system/tests/test_chat_conversations.py`
- `external-systems/partner-http-gateway/API_CONTRACT.md`

验收标准：

- 主链路关键交接有自动化保护
- Gateway 只处理接入逻辑，不再维护主流程真相
- 外部调用方可以通过 API 契约判断该去哪个域拿哪个事实

### P2：把主链路变成可追踪系统

目标：

- 让跨域协作从隐式调用变成显式事件
- 让主链路能被追踪、统计和排障

包含任务：

1. `4.1` 定义主链路领域事件
2. `4.2` 补事件生产与消费链路
3. `4.3` 补端到端链路监控
4. `5.1` 收敛 verification 输出
5. `5.2` 收敛 risk 输出
6. `5.3` 收敛 profile review 输出
7. `5.4` 收敛 persona/profile 输出

建议产出：

- 一份主链路事件清单
- 一份事件载荷规范
- 一份主链路漏斗与排障视图定义
- 一组支撑域输出契约

建议涉及文件：

- `match_domain/outbox.py`
- `match_domain/outbox_runtime.py`
- `match_domain/case_events.py`
- `external-systems/partner-recommendation-system/recommendation_system/outbox.py`
- `external-systems/partner-matchmaking-system/matchmaking_system/outbox.py`
- `external-systems/partner-chat-system/chat_system/events.py`
- `external-systems/partner-chat-system/chat_system/outbox_consumer.py`
- `external-systems/partner-chat-system/chat_system/outbox.py`
- `external-systems/partner-chat-system/chat_system/verification.py`
- `external-systems/partner-chat-system/chat_system/risk.py`
- `external-systems/partner-chat-system/chat_system/profile_reviews.py`
- `persona_memory_sync/api.py`
- `profile_service/api.py`
- `observability/`

验收标准：

- 至少可以追踪一个用户从“找对象”到“进入聊天”的完整链路
- 支撑域只输出结果，不再反向改写主流程

## 11. 推荐执行顺序

如果只按“最少投入，最大收益”的方式推进，建议顺序如下：

1. 先完成 `P0`
2. 再完成 `P1`
3. 最后做 `P2`

原因：

- 没有 `P0`，后面的代码改造会反复返工
- 没有 `P1`，边界即使说清楚了，也没有自动化保护
- 没有 `P2`，系统能运行，但很难长期稳定演进

## 12. 一个月落地建议

如果按四周推进，可以压成下面这个节奏。

### 第 1 周

- 完成 `P0` 中的主线定义、职责表、真相源表

### 第 2 周

- 完成 recommendation -> matchmaking 交接定义
- 完成 relationship -> chat 开聊准入定义

### 第 3 周

- 补主链路交接测试
- 开始收 Gateway 越界逻辑

### 第 4 周

- 完成 Gateway 边界收敛
- 更新 API 契约
- 形成下一阶段事件化改造输入
