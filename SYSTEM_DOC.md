# SYSTEM_DOC

> 编写时间：2026-05-15  
> 编写依据：当前代码库中的配置文件、Python 模块、数据库 schema、网关入口与测试文件。  
> 说明：本仓库并非典型的前端 `src/` 结构，而是一个以 Python 为主的模块化 monorepo；本文未将仓库内既有 `.md` 文档作为事实来源。

## 1. 文档范围与结论摘要

本项目当前已经不是单一“相亲资料搜索脚本”，而是一个围绕“找对象/撮合/建立信任/促成互动”的关系运营平台原型。系统已经实现了如下完整能力链路：

- 用户画像与长期 persona memory 沉淀
- 基于规则与双边约束的候选人搜索
- 会话式 Discovery 找人体验
- Saved Search 驱动的持续推荐
- 代理牵线 / 代问 / 代打招呼类 case 管理
- 互选撮合池与双向匹配流水线
- 聊天、群聊与 AI 红娘协同
- 活体认证、资料核验、举报、风控、反欺诈图谱
- 统一 HTTP Gateway、异步任务、调度、健康观测

从成熟度上看，这是一套“高保真后端产品原型 / 早期可运营系统”，而不是只停留在概念验证阶段。它已经具备明确的领域模型、分库边界、任务调度、回归测试和运营侧接口，但距离严格生产级 SaaS 仍有若干工程化缺口，例如鉴权方式较轻、跨库一致性依赖 outbox/任务机制、部分 AI/审核能力仍需要更多运营闭环与成本治理。

## 2. 项目定位、愿景与核心痛点

### 2.1 基于代码推断的产品定位

从 `pyproject.toml` 的描述“relationship-operations prototype: search, persona memory, recommendation, and matchmaking”，以及各子系统实现看，本项目的真实定位更接近：

**一个信任优先的关系运营平台（Relationship Operations Platform），用于把“找对象”从一次性检索，升级为持续画像、智能推荐、运营撮合、互动辅助与风险治理的一体化流程。**

它既服务终端用户，也明显服务平台内部运营角色，例如：

- 红娘 / 撮合运营
- 资料审核员
- 风控审核员
- 客服 / 支持人员
- 平台管理员
- 异步任务与调度 worker

### 2.2 系统试图解决的核心痛点

#### 痛点 1：传统资料搜索是静态的，无法承载长期偏好变化

普通相亲/婚恋系统往往只有一份静态资料和一次性筛选条件，但用户真实偏好会逐步澄清、修正甚至自相矛盾。当前代码通过 `persona_memory_sync` 将“用户自述、强推断、弱推断、观察值、公开可见值”拆层管理，说明系统试图解决“偏好长期记忆与渐进建模”问题。

#### 痛点 2：单边匹配不够，真实成单依赖双边适配与可运营推进

搜索引擎不仅评估 A 喜不喜欢 B，还评估 reciprocal / contextual fit / caution / trust 信息；撮合系统进一步构建 directional edge、mutual pair 和 match case，说明系统关注的是“双边可推进关系”，而不是单次打分。

#### 痛点 3：推荐不是发卡片，而是要控制节奏、质量与打扰成本

推荐系统里存在 quiet hours、daily cap、saved search subscription、delivery gate、direct greet only、人工预审等逻辑，说明系统试图把推荐做成“持续运营漏斗”，而不是简单推送列表。

#### 痛点 4：撮合成功率依赖跟进、辅助沟通和中间人机制

推荐系统的 `proxy_intro`、撮合系统的 staged outreach、聊天系统的 `main_group + assistant_dm_a + assistant_dm_b` 多会话布局，说明系统假设“平台/红娘不是旁观者，而是关系推进中的参与者”。

#### 痛点 5：婚恋场景天然高风险，必须把信任能力做成基础设施

聊天风控、资料核验、活体认证、照片风险评估、申诉、反欺诈图谱都已经是独立模块。这意味着项目不是把安全视为附属能力，而是视为成交前置条件。

### 2.3 愿景总结

如果用一句话概括，本项目的愿景是：

**构建一个可持续学习、可运营推进、可审计、可控风险的智能婚恋撮合操作系统。**

## 3. 仓库结构与系统边界

### 3.1 仓库不是单一应用，而是模块化 monorepo

当前仓库主要分为两层：

#### 根目录共享能力

- `partner_search/`：候选人搜索与规则匹配引擎
- `persona_memory_sync/`：persona memory、公开资料渲染、画像回写
- `profile_service/`：统一资料读写接口
- `match_domain/`：关系状态、case 状态、事件账本、outbox
- `async_jobs/`：持久化异步任务队列
- `task_scheduler/`：APScheduler 定时作业注册
- `db_migrations/`：多库 schema migration
- `observability/`：健康指标与观测

#### `external-systems/` 下的业务子系统

- `partner-recommendation-system/`
- `partner-matchmaking-system/`
- `partner-chat-system/`
- `partner-discovery-system/`
- `partner-http-gateway/`

### 3.2 系统边界

从 `.env.example` 和 schema 设计看，系统当前边界如下：

- 使用多个 MySQL 数据库或逻辑分库承载不同子系统
- 通过 Python 包直接复用共享领域代码，而不是通过远程 RPC 微服务通信
- 通过统一 HTTP Gateway 暴露 REST + JSON-RPC 接口
- 通过 OpenAI / OpenAI-compatible runtime 驱动 Discovery Agent 与 Matchmaker Assistant
- 通过本地或外部活体/人脸/语音审核能力完成验证流程

因此，它在部署形态上更像**模块化单仓库 + 逻辑分服务架构**，而不是完全独立部署的分布式微服务。

## 4. 总体架构

### 4.1 分层架构

```text
┌────────────────────────────────────────────────────────────┐
│ Experience Layer                                           │
│ - Discovery 会话式找人                                     │
│ - Recommendation 推荐卡片 / Saved Search                   │
│ - Matchmaking 撮合流程                                     │
│ - Chat / Assistant / Trust Hub                             │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ HTTP Gateway                                               │
│ - REST / JSON-RPC                                          │
│ - Actor 身份解析                                           │
│ - 角色鉴权                                                 │
│ - owner 绑定校验                                           │
│ - 审计与限流                                               │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ Domain Services                                            │
│ - partner_search                                           │
│ - persona_memory_sync                                      │
│ - recommendation_system                                    │
│ - matchmaking_system                                       │
│ - chat_system                                              │
│ - discovery_system                                         │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ Shared Infrastructure                                      │
│ - match_domain 事件模型                                    │
│ - outbox                                                   │
│ - async_jobs                                               │
│ - task_scheduler                                           │
│ - observability                                            │
│ - db_migrations                                            │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ Storage                                                    │
│ - recommendation DB                                        │
│ - matchmaking DB                                           │
│ - chat DB                                                  │
│ - discovery DB                                             │
│ - persona DB                                               │
│ - 外部 profile source / 候选资料表                         │
└────────────────────────────────────────────────────────────┘
```

### 4.2 关键架构特征

#### 1. 共享领域模型先行

`match_domain/model.py`、`match_domain/ledger.py` 把 recommendation、proxy intro、matchmaking case 等关系状态统一建模，这降低了各业务子系统之间的语义漂移。

#### 2. 分库解耦，但在代码层统一编排

推荐、撮合、聊天、Discovery、Persona 都有独立 schema；但在 Python monorepo 中通过模块导入共享逻辑，获得较高迭代速度。

#### 3. 同步 API + 异步任务 + 定时调度并存

系统不是纯在线请求模型，而是大量使用：

- 事务内写 outbox
- worker 消费 outbox
- 持久化 async job 重试
- APScheduler 定时执行维护任务

这很适合推荐刷新、撮合推进、聊天巡检、超时关闭、资料同步等业务。

#### 4. 运营与审核角色被纳入一等公民

`gateway/identity.py` 中存在 `ops_operator`、`risk_reviewer`、`profile_reviewer`、`customer_support`、`platform_admin`、`service_worker` 等角色，说明系统天然面向“用户 + 平台运营”的双边工作流设计。

## 5. 核心领域模型与状态机

### 5.1 关系状态模型

`match_domain/model.py` 中定义的 `RelationStatus` 覆盖了关系从发现到关闭的关键过程：

- `new`
- `recommended`
- `saved`
- `skipped`
- `cooling`
- `direct_greeted`
- `proxy_intro_requested`
- `proxy_intro_active`
- `closed`

这表明系统并不把“推荐命中”视为终点，而是把后续动作、冷静期、代理牵线、关闭等状态都作为正式业务状态。

### 5.2 双边撮合状态模型

`PairStatus` 体现了撮合池中的双边进展：

- `eligible`
- `below_threshold`
- `blocked`
- `cooling`
- `case_opened`
- `mutual_accept`
- `needs_revalidation`
- `stale`

这使系统可以区分“算法上可匹配”和“运营上可推进”的差异。

### 5.3 Case 模型

`CaseType` 目前至少支持：

- `proxy_intro`
- `matchmaking`

`CaseStatus` 支持从待处理、等待回复、接受、拒绝、超时到关闭的完整流程，说明 proxy intro 与 matchmaking 已被统一抽象成可追踪 case。

### 5.4 事件账本与状态归约

`match_domain/ledger.py` 的作用是将事件流归约为当前关系/撮合状态。这个设计非常关键，因为它意味着：

- 状态变更是可追溯的
- case 演进可以重建
- 更适合后续做审计、漏斗分析、补偿和重放

## 6. 功能模块清单

### 6.1 画像与 Persona Memory

核心代码：

- `persona_memory_sync/persona_memory_lib.py`
- `persona_memory_sync/schema_tools.py`
- `profile_service/api.py`

已实现能力：

- 支持 persona 属性按来源区分为显式陈述、强推断、弱推断
- 区分 persona-only、observation-only、persona-and-profile 等范围
- 支持公开可展示字段与内部匹配字段分层
- 支持 persona 渲染为公开 profile 视图
- 支持 persona 内容回写到 profile 相关表/扩展列
- 支持面向匹配引擎的结构化 matcher payload

交互逻辑：

1. 用户资料、观察信息、后续反馈进入 persona memory。
2. persona memory 合并不同证据源，形成较稳定的偏好与自我描述。
3. `profile_service` 将其渲染为公开资料、对外展示字段与匹配字段。
4. 搜索、推荐、Discovery、聊天助手都可以消费这层数据。

产品意义：

这层能力是系统的“长期记忆内核”。没有它，推荐与撮合只能基于静态资料工作。

### 6.2 候选人搜索与规则匹配引擎

核心代码：

- `partner_search/search_candidates.py`
- `partner_search/search_inputs.py`
- `partner_search/api.py`
- `profile_detail_reader.py`

已实现能力：

- 读取 MySQL 资料源并做标准化
- 支持 self profile / persona profile 作为查询上下文
- 根据筛选条件、偏好强度、缺失项进行综合评分
- 评估 reciprocal compatibility 与 contextual fit
- 生成原因解释、缺失字段、追问问题、风险提示、信任摘要
- 支持多样性选择，避免结果过于同质
- 输出照片预览与公开详情
- 对无结果场景提供 diagnostics

交互逻辑：

1. 输入筛选条件、用户画像或 persona。
2. 系统清洗条件并标准化“硬约束/软约束/可追问项”。
3. 对候选人集合做规则匹配与双边适配计算。
4. 输出可解释候选列表，而不是黑盒分数。

产品意义：

搜索引擎已经承担“候选人解释器”职责，这为 Discovery、推荐和运营撮合提供了统一底座。

### 6.3 Discovery 会话式找人

核心代码：

- `external-systems/partner-discovery-system/discovery_system/service.py`
- `discovery_system/agent_runtime.py`
- `discovery_system/view_models.py`

已实现能力：

- 创建 Discovery session
- 处理用户 turn 和 action click
- 保存会话记忆、搜索 run、timeline 和候选卡片
- 生成候选卡、资料详情视图
- 将最近一次搜索转化为 saved search subscription

交互逻辑：

1. 用户通过对话方式表达偏好或点击预设动作。
2. Discovery Agent 决定是追问、执行搜索、展示候选卡，还是转入订阅推荐。
3. 搜索结果通过视图模型组织成适合前端消费的 timeline/cards/actions。
4. 若用户暂时没有合适对象，可直接把搜索意图沉淀为持续订阅。

产品意义：

Discovery 是系统的前门，把复杂的筛选条件输入变成低门槛的会话式体验。

### 6.4 Saved Search 与持续推荐

核心代码：

- `external-systems/partner-recommendation-system/recommendation_system/service.py`
- `recommendation_system/criteria_compiler.py`
- `recommendation_system/direct_greet_gate.py`
- `recommendation_system/no_match_opt_in.py`

已实现能力：

- 创建 saved search subscription
- 编译有效搜索条件：初始条件 + persona + 覆盖项
- 周期性刷新订阅并写入 recommendation
- 记录 search runs 与规则来源
- 生成 in-app recommendation cards
- 控制静默时段、每日上限和投递节奏
- 处理 `skip` / `save` / `direct_greet` 行为
- 支持某些场景下的人工预审或 `direct_greet_only`
- 无结果时引导用户订阅后续机会

交互逻辑：

1. 用户通过 Discovery 或直接操作创建订阅。
2. 推荐系统定时拉取到期订阅并执行搜索。
3. 候选人结果被 upsert 为 recommendation 记录。
4. 经过投递 gate 后，生成站内卡片或等待人工/规则判断。
5. 用户动作进一步更新 relation 状态，并可能进入牵线或聊天链路。

产品意义：

这不是“猜你喜欢”式推荐，而是把用户主动意图运营成持续机会流。

### 6.5 代理牵线 / 代问 / 代打招呼

核心代码：

- `external-systems/partner-recommendation-system/recommendation_system/proxy_intro.py`

已实现能力：

- 创建 proxy intro match case
- 记录 outreach payload 与 outreach 尝试
- 接收接受、拒绝、超时等回应
- 对 case 施加 cooling
- 将 case 结果同步回 recommendation relation 状态

交互逻辑：

1. 用户对某个推荐对象触发代问/牵线类动作。
2. 系统建立 `proxy_intro` case，并发起联系。
3. 对方接受、拒绝或超时后，case 进入下一状态。
4. 结果影响双方关系状态，以及后续是否继续推荐/冷却。

产品意义：

这使平台能够扮演“可信中间人”，降低用户直接开场的心理成本。

### 6.6 互选撮合池与双向撮合

核心代码：

- `external-systems/partner-matchmaking-system/matchmaking_system/service.py`

已实现能力：

- 管理撮合池成员与入池条件
- 为每个成员维护搜索条件与自画像
- 周期性计算 directional edges
- 根据双边 edge 构建 mutual pairs
- 按阈值、日限额、状态打开 match cases
- 管理第一触达、第二触达、接受/拒绝/超时
- stale case 关闭与重验
- 记录会后反馈，并反哺 persona memory

交互逻辑：

1. 用户进入撮合池，带入搜索偏好与自我画像。
2. 系统周期性计算“我看你合适”和“你看我合适”的双向边。
3. 双向都满足阈值后，进入 mutual pair。
4. 运营系统按节奏打开正式撮合 case。
5. 双方反馈和后续结果反写到画像与状态机中。

产品意义：

撮合系统本质上是一个“可运营的双边市场编排器”，已经超出传统推荐逻辑。

### 6.7 聊天系统

核心代码：

- `external-systems/partner-chat-system/chat_system/service.py`
- `chat_system/conversations.py`

已实现能力：

- 一对一 thread 聊天
- case 维度的多会话布局
- 消息发布、可见性控制、事件出箱
- case 相关 timeline 聚合
- 对消息元数据、权限与风控做联动处理

多会话布局特征：

- `main_group`
- `assistant_dm_a`
- `assistant_dm_b`

这说明系统不是单纯的双方私聊，而是支持平台/助手在不同上下文中介入。

### 6.8 AI 红娘 / Assistant 协同

核心代码：

- `chat_system/assistant_sessions.py`
- `chat_system/assistant_orchestrator.py`
- `chat_system/assistant_runtime.py`
- `chat_system/assistant_context.py`
- `chat_system/outbox_consumer.py`

已实现能力：

- 为 case 创建 assistant session 与任务
- 基于用户消息触发 agent task
- 支持 opening probe、silence probe、post-chat follow-up
- 合并重复任务、控制 cooldown
- 在正确会话中投递 assistant 回复
- 提出 persona update 建议
- 汇总跨会话历史、资料快照、公开 persona 作为上下文

交互逻辑：

1. 用户或系统消息进入聊天 outbox。
2. outbox consumer 识别需要 AI 介入的场景，创建 assistant task。
3. Assistant Runtime 基于上下文输出结构化决策。
4. Orchestrator 将回复发布到主群聊或单独 DM。
5. 后续可能触发跟进、提醒、画像建议更新。

当前边界：

代码明确体现“persona sync job 存在，但聊天中的直接自动回写被有意识地收敛”，说明团队对“AI 直接改画像”持审慎态度，倾向于先让 AI 产出建议，再进入审查闭环。

### 6.9 活体认证与真实身份/真人确认

核心代码：

- `chat_system/verification.py`

已实现能力：

- 创建 live video verification challenge
- 申请、提交、重提活体认证
- 本地模型/审核流程进行 liveness、speech、face 等检查
- 通知、复核、状态流转
- 与风险判断、资料审核形成联动

产品意义：

它服务的不只是“实名认证”，更是关系建立前的真实性门槛。

### 6.10 举报、会面反馈与聊天风控

核心代码：

- `chat_system/risk.py`
- `chat_system/moderation_ops.py`

已实现能力：

- 用户举报与系统信号上报
- 风险 case 与风险 signal 管理
- 会面反馈回收
- 线程级限制与处置
- 风控申诉与复核
- 播放式审查、看板和批量审核

交互逻辑：

1. 举报、模型信号、会面反馈进入风险系统。
2. 系统归并为风险 case，并生成信号记录。
3. 审核员可以查看回放、处置、批量审核、受理申诉。
4. 结果反向影响聊天权限、资料状态与用户信任中心展示。

### 6.11 资料核验、资料一致性与照片风控

核心代码：

- `chat_system/profile_reviews.py`

已实现能力：

- 教育、工作、收入等字段核验提交流程
- 审核、重提、申诉
- 资料一致性评估
- 照片真实性分析与风险评分
- profile review case 与 appeal 流程
- 与 moderation state 同步

产品意义：

这一层让“资料是否可信”从主观印象变成平台可审计流程。

### 6.12 反欺诈图谱

核心代码：

- `chat_system/fraud_graph.py`

已实现能力：

- 对设备、联系方式、支付、IP、消息模式等实体做哈希化关联
- 建立用户之间的可疑联系图谱
- 传播与聚合欺诈风险分值
- 支持网络概览和对象级查询

产品意义：

这表明团队已经开始从“单事件风控”升级到“关系图谱反欺诈”。

### 6.13 用户信任中心

核心代码：

- `chat_system/self_service.py`

已实现能力：

- 聚合活体认证、资料核验、风控历史、申诉状态
- 为前端提供统一 trust hub payload

产品意义：

用户不是被动接受风控，系统允许其查看、补件、申诉和修复信任状态。

### 6.14 统一网关与 API 编排

核心代码：

- `external-systems/partner-http-gateway/gateway/app.py`
- `gateway/identity.py`

已实现能力：

- REST 风格 `/v1/...` 接口
- `POST /jsonrpc` 接口
- ActorPrincipal 解析
- Bearer / API Key 静态 token 鉴权
- 角色权限校验
- owner 归属校验
- 审计事件与限流
- 可选数据库连接池
- 统一暴露 recommendation / matchmaking / chat / discovery / verification / profile review / trust hub / timeline / async jobs / maintenance 能力

产品意义：

网关已经把本项目从“若干 Python 模块”提升为“可被前端、运营台、外部服务统一消费的产品后端”。

### 6.15 调度、异步任务与系统观测

核心代码：

- `task_scheduler/build.py`
- `async_jobs/queue.py`
- `match_domain/outbox_runtime.py`
- `observability/health.py`
- `db_migrations/runner.py`

已实现能力：

- recommendation 定时刷新、投递、proxy case 超时关闭
- matchmaking 池刷新、pair 构建、case 打开与 stale 关闭
- chat outbox、assistant 维护、异步任务处理
- 通用 async job 入队、重试、失败、成功状态跟踪
- outbox claim / retry / publish / stale recovery
- 多库 schema migration
- backlog、代理 case、pool refresh 等健康指标

产品意义：

这部分说明系统已经考虑到线上运行中的“节奏调度、失败补偿和可观测性”。

## 7. 核心交互链路

### 7.1 从找人到持续推荐

1. 用户通过 Discovery 对话或直接输入偏好。
2. `partner_search` 输出可解释候选结果。
3. 如果暂时没有合适对象，系统通过 `no_match_opt_in` 引导创建 saved search。
4. 推荐系统定时刷新订阅，持续寻找新候选。
5. 用户对卡片执行 `skip`、`save`、`direct_greet` 等动作。

这是“即时搜索 -> 长期订阅”的自然转化漏斗。

### 7.2 从推荐到代理牵线

1. 某个 recommendation 被用户保存或请求代问。
2. 推荐系统创建 `proxy_intro` case。
3. 系统发起 outreach 并等待对方回应。
4. 对方接受、拒绝或超时。
5. relation status 进入 `proxy_intro_active`、`cooling` 或 `closed` 等状态。

这是“兴趣表达 -> 平台中介推进”的低压转化路径。

### 7.3 从撮合池到正式 case

1. 用户加入撮合池。
2. 系统周期性对池内成员两两计算 directional edges。
3. 满足双边条件后生成 mutual pair。
4. 根据容量与策略打开 match case。
5. 通过 staged outreach 触发双方确认。
6. 结果与反馈回流至画像、pair 状态和后续推荐/撮合决策。

这是“后台持续编排 -> 前台择机推进”的运营型关系漏斗。

### 7.4 从聊天到画像更新与风险治理

1. 用户消息进入聊天线程或 case 对话。
2. outbox 将消息同步给 assistant task 管道。
3. Assistant 给出跟进建议、辅聊回复或后续动作。
4. 聊天中的举报、异常信号、会面反馈进入风险系统。
5. 风险结果影响聊天权限、资料审核、信任中心与后续推荐资格。

这是“互动促进 + 风险控制”并行发生的闭环。

## 8. 数据存储与关键表分布

### 8.1 Recommendation 库

关键表族：

- `saved_search_subscriptions`
- `saved_search_runs`
- `profile_recommendations`
- `recommendation_actions`
- `in_app_recommendation_cards`
- `match_cases`
- `match_case_events`
- `match_case_outreach_attempts`
- `outbox_events`
- `async_jobs`

主要职责：

- 管理持续推荐订阅与推荐结果
- 驱动 proxy intro case
- 追踪投递、动作、超时与补偿任务

### 8.2 Matchmaking 库

关键表族：

- `matchmaking_pool_members`
- `matchmaking_edges`
- `matchmaking_pairs`
- `match_cases`
- `match_case_events`
- `matchmaking_feedback_events`
- `outbox_events`
- `async_jobs`

主要职责：

- 管理撮合池
- 维护双边边关系与 mutual pair
- 承载正式撮合 case 生命周期

### 8.3 Chat / Trust 库

关键表族：

- `chat_threads`
- `chat_messages`
- `chat_conversations`
- `chat_conversation_members`
- `chat_conversation_messages`
- `chat_agent_sessions`
- `chat_agent_tasks`
- `chat_thread_summaries`
- `persona_sync_jobs`
- `verification_*`
- `chat_member_reports`
- `chat_risk_*`
- `profile_field_verification_*`
- `profile_review_*`
- `photo_risk_*`
- `outbox_events`
- `async_jobs`

主要职责：

- 承载聊天、AI 助手、活体认证、资料核验、举报风控与申诉

### 8.4 Discovery 库

关键表族：

- `discovery_agent_sessions`
- `discovery_agent_turns`
- `discovery_agent_actions`
- `discovery_search_runs`
- `discovery_agent_session_memory_items`

主要职责：

- 承载 Discovery 对话、动作、搜索历史与 session memory

### 8.5 Persona 库

Persona 相关 schema 由 `persona_memory_sync/schema_tools.py` 管理，同时通过 `profile_service` 与外部 profile 表发生映射和扩展。

## 9. 当前成熟度评估

### 9.1 已达到的成熟度

#### 产品层面

- 已经具备完整主线：找人、推荐、牵线、撮合、聊天、信任治理
- 已经具备用户侧与运营侧双端能力
- 已经形成从冷启动到长期跟进的关系生命周期

#### 架构层面

- 有明确模块边界
- 有统一网关
- 有共享领域状态机
- 有分库与迁移机制
- 有异步任务、outbox、定时维护
- 有健康指标

#### 工程层面

- 根目录与各 external systems 下存在测试文件
- 网关存在 realistic user flows / regression 类测试
- 说明项目已具备一定回归意识，而非完全手工验证

### 9.2 当前阶段判断

综合判断，本项目当前处于：

**“中后期原型 / 早期可运营后端系统”阶段。**

理由：

- 业务面已经足够完整，远超 demo
- 但部署形态、鉴权模式、配置管理、成本治理、数据治理仍偏工程内用或早期内部产品
- 多个 AI 与审核能力依赖环境变量、模型配置与人工流程协同，尚未体现成熟商业化平台常见的强治理层

### 9.3 主要短板

- 规则引擎复杂度高，后续维护成本可能快速上升
- 多库之间的一致性主要依赖 outbox / async job，需要更强的幂等与补偿标准
- Gateway 当前主要是静态 token + 角色，适合内部环境，不足以支撑复杂外部开放场景
- 安全/隐私/合规策略已开始建设，但还需要更严格的审计闭环
- Discovery 与 Assistant 的效果评估体系在代码层已具雏形，但尚未看到系统化实验框架

## 10. 未来 3-6 个月产品规划建议

### 10.1 0-3 个月：把“可用原型”打磨为“可稳定运营”

#### 方向 1：统一用户前台主旅程

建议把 Discovery、Saved Search、Recommendation、Proxy Intro、Chat 统一成一条连续主旅程：

- Discovery 负责冷启动表达需求
- Saved Search 负责不中断跟进
- Recommendation 负责机会触达
- Proxy Intro 负责降低首次互动门槛
- Chat + Assistant 负责推进后续沟通

目标是减少功能割裂感，让用户感知到“平台一直在替我推进关系”。

#### 方向 2：增强推荐与撮合反馈闭环

当前已经有 `save`、`skip`、反馈事件和 persona memory，建议进一步补齐：

- 明确“为什么推荐给我”前台解释
- 对 `skip` 原因做结构化归因
- 让撮合失败原因进入 persona 更新建议
- 让推荐/撮合策略可基于反馈自适应收敛

#### 方向 3：做出运营工作台最小闭环

系统已有 reviewer / operator / support 角色，下一步建议提供面向运营的统一工作台能力：

- 待处理 proxy intro case 列表
- 待审核资料/认证队列
- 风险 case 看板
- 用户信任状态总览
- case timeline 回放

这会显著提升系统真实落地价值。

### 10.2 3-6 个月：从“运营辅助系统”升级为“智能撮合平台”

#### 方向 4：建设分层会员/服务体系

基于当前能力，可以自然演化出：

- 普通用户：搜索 + Discovery + 基础推荐
- 高意向用户：持续推荐 + proxy intro
- 高客单撮合服务：进入 curated matchmaking pool + AI/人工协同跟进

代码已经有足够多的 case、会话和 trust 能力，适合承接差异化服务层。

#### 方向 5：建设关系推进效果指标体系

建议围绕整条漏斗建立指标：

- 搜索到查看详情转化率
- 订阅创建率
- 推荐卡片打开/保存/跳过率
- proxy intro 接受率
- mutual pair 形成率
- match case 回复率
- 会面反馈与风险事件率

这会让产品优化和模型优化都更可量化。

#### 方向 6：把信任系统从“风控兜底”升级为“增长资产”

当前已具备活体认证、资料核验、照片风控、反欺诈图谱。下一步建议做：

- 公开可信徽章体系
- 匹配排序中的 trust-aware weighting
- 高风险用户/高质量用户分层运营
- 用户自助补信任材料与修复路径

这样信任不只是拦截风险，也能提升成交效率。

## 11. 技术优化建议

### 11.1 P0：优先解决的工程问题

#### 1. 把跨系统事件契约正式化

当前 recommendation、matchmaking、chat 都在使用 outbox 和共享状态模型。建议进一步定义统一事件 schema、版本号和消费幂等规范，避免后续子系统演化时出现事件语义漂移。

#### 2. 加强幂等、重试与补偿策略

异步任务和 outbox 已经存在，但建议对以下动作建立标准幂等键：

- recommendation 刷新
- case 开启
- outreach 派发
- assistant reply 发布
- persona update 建议入队

目标是把“可重试”从局部实现提升为系统性能力。

#### 3. 升级网关鉴权

当前 `gateway/identity.py` 更适合内部或早期环境。建议后续引入：

- 用户态 token 与后台态 token 分离
- 更强的 token 生命周期管理
- 审计字段标准化
- 细粒度 scope / permission

### 11.2 P1：提升系统可维护性与成本效率

#### 4. 逐步收敛超大规则引擎

`partner_search/search_candidates.py` 承载了大量规则与解释逻辑。建议分阶段拆分为：

- 条件标准化层
- 候选过滤层
- 打分层
- 双边适配层
- 风险/信任叠加层
- 解释生成层

否则未来产品规则变多后，搜索引擎会成为主要维护瓶颈。

#### 5. 为 AI 决策增加离线评估与在线实验能力

Discovery Agent 与 Matchmaker Assistant 已经接入结构化决策，但建议补齐：

- prompt / policy 版本记录
- 样本回放评测
- bad case 标注
- A/B 实验开关
- token 成本与成功率联动看板

#### 6. 统一前后台可观察性

现有 `observability/health.py` 更偏基础健康。建议扩展为：

- 队列 backlog
- case 漏斗转化
- 推荐 freshness
- assistant 响应延迟与采纳率
- 风险误伤/漏报率

### 11.3 P2：中期架构演进建议

#### 7. 增加配置分层与环境治理

当前较多能力依赖 `.env` 变量。建议引入：

- 环境模板分层
- 功能开关中心
- 敏感配置统一注入
- 审核/模型/实验参数集中管理

#### 8. 建立数据治理与隐私边界

系统涉及照片、视频、收入、教育、聊天内容、欺诈图谱等高敏数据。建议明确：

- 数据最小化原则
- 审计日志保留期
- 删除与导出策略
- 风险数据与公开资料隔离
- 人工审核访问权限边界

#### 9. 增加更完整的端到端回归

虽然仓库已存在多组测试，但建议补充跨子系统 e2e：

- Discovery -> Subscription -> Recommendation -> Proxy Intro
- Matchmaking -> Case -> Chat -> Feedback -> Persona Update
- Verification / Profile Review / Appeal / Trust Hub 全链路

## 12. 风险与注意事项

### 12.1 产品风险

- 当前能力很多，若前台交互没有统一编排，用户会感知为多个割裂工具
- 信任与风控能力很强，但如果解释不透明，可能引发误伤与体验成本
- AI 参与关系推进时，需要明确边界，避免“越权代替用户表达”

### 12.2 架构风险

- 多分库 + 共享代码的模式迭代很快，但容易在后期出现边界模糊
- outbox / async jobs 如果缺乏统一规范，长期会增加排障难度
- 搜索和撮合逻辑若持续集中在大文件中，团队协作成本会迅速上升

### 12.3 运营风险

- 若审核、举报、申诉流程量级上升，需要专门的运营控制台与 SLA 管理
- 活体认证、资料核验、照片风控都涉及人工和模型协同，必须监控单位成本

## 13. 总结

从代码事实看，本项目已经具备一个婚恋/撮合平台核心后端的主要骨架，而且其差异化不在“会不会推荐”，而在：

- 是否能记住用户长期真实偏好
- 是否能把单边兴趣运营为双边机会
- 是否能借助平台和 AI 促进真实互动
- 是否能在高风险场景下建立可解释的信任体系

因此，本项目最有潜力的发展方向不是继续堆砌零散功能，而是围绕“关系推进闭环”和“信任优先体验”做产品统一与工程收敛。如果沿着这条路线迭代，未来 3-6 个月内完全有机会从高保真原型进化为可稳定运营的智能撮合平台。
