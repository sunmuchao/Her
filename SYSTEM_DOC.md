# Her 系统文档

## 1. 文档说明

本文档基于当前代码仓库的实际实现整理，不参考仓库内既有 Markdown 说明。扫描范围覆盖：

- 根目录 Python 共享模块
- `partner_search/`
- `persona_memory_sync/`
- `profile_service/`
- `match_domain/`
- `async_jobs/`
- `db_migrations/`
- `task_scheduler/`
- `observability/`
- `external-systems/` 下的推荐、撮合、聊天、发现、HTTP Gateway 子系统
- `frontend/her-app/` 前端应用

文档目标：

- 还原系统当前的真实架构
- 总结系统愿景与核心痛点
- 盘点已实现的功能模块与交互闭环
- 给出未来 3-6 个月的产品与技术迭代建议

---

## 2. 项目概述

### 2.1 系统定位

`Her` 是一个“关系运营 / 红娘协作”产品原型，目标不是做传统开放式滑卡，而是围绕“认真关系建立”构建一套端到端能力：

- 用户登录与入驻
- 用户资料与画像沉淀
- 红娘式对话发现偏好
- 基于资料库的候选检索与推荐
- 双边撮合与案例推进
- 进入关系后的聊天与关系维护
- 安全风控、申诉、资料审核与活体认证

### 2.2 当前形态

项目是一个偏 monorepo 的组合式系统，包含：

- 一个共享 Python 领域层与基础设施层
- 多个独立的外部业务子系统
- 一个统一 HTTP Gateway
- 一个 Next.js 移动端前端

它已经不只是算法脚本或前端 Demo，而是具备完整业务链路的产品雏形。

### 2.3 核心技术栈

后端：

- Python 3.10+
- MySQL
- Pydantic
- APScheduler
- OpenAI / OpenAI Agents SDK 兼容接口

前端：

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4

---

## 3. 愿景与核心痛点

### 3.1 愿景（基于代码推断）

本系统的长期愿景是构建一个“高信任、高介入、强运营”的婚恋协作平台，让 AI 红娘、规则引擎和人工运营共同参与关系建立过程。

与泛社交产品相比，该系统明显更强调：

- 真实资料与可信身份
- 有目标的关系推进
- 红娘/系统辅助而非纯用户自助
- 风险控制、审核和申诉闭环
- 推荐、撮合、聊天、认证之间的数据联动

### 3.2 解决的核心痛点

从代码结构与规则设计看，系统试图解决以下问题：

#### 1. 用户“不会描述自己，也不会清晰表达择偶需求”

系统通过 `discovery_system` 的对话式发现页，把用户偏好采集从表单改成红娘式会话，并将结果回写为检索条件与画像。

#### 2. 纯关键词筛选或单向推荐质量不足

系统在 `partner_search` 中实现了：

- 结构化条件过滤
- 互选兼容性判断
- 风险标记
- 可信度与活跃度加权
- 多样性去重

这说明目标不是简单返回“符合条件的人”，而是返回“更可推进、更可信、更适合进入关系的人”。

#### 3. 推荐到关系建立之间断层严重

系统把链路拆成多个明确状态：

- 搜索命中
- 推荐入池
- 待审核 / 待投递
- 投递为推荐卡
- 用户跳过 / 收藏 / 直接打招呼
- 代理牵线 / 撮合立案
- 聊天与后续关系维护

这解决了传统推荐系统“只负责发牌，不负责成交”的问题。

#### 4. 婚恋场景对真实性和安全性的高要求

聊天系统内置：

- 举报
- 风险信号
- 欺诈网络分析
- 风险案件
- 风险申诉
- 资料审核
- 活体视频认证

说明平台把“安全运营”视为产品主流程的一部分，而不是外围补丁。

#### 5. 用户状态持续变化，系统需要长期经营而非一次匹配

仓库中存在：

- persona memory
- saved search subscriptions
- 定时刷新
- async jobs
- outbox
- matchmaking pool

这表明系统面向的是“持续运营中的关系机会管理”，而不是一次性搜索。

---

## 4. 总体架构

### 4.1 架构风格

系统采用“共享领域内核 + 多业务子系统 + 统一网关 + 单前端应用”的分层架构。

高层结构如下：

```text
Frontend (Next.js her-app)
        |
        v
Partner HTTP Gateway
        |
        +-------------------+-------------------+-------------------+-------------------+
        |                   |                   |                   |                   |
        v                   v                   v                   v                   v
Recommendation       Matchmaking          Chat / Safety        Discovery         Profile / Persona
System               System               / Verification       System            Shared Services
        \                   \                   /                   /                   /
         \___________________\_________________/___________________/__________________/
                                      |
                                      v
                         Shared Domain / Infra Layer
                         - match_domain
                         - async_jobs
                         - db_migrations
                         - observability
                         - profile_service
                         - persona_memory_sync
                         - partner_search
```

### 4.2 关键架构判断

#### 1. 子系统边界清晰

`external-systems/` 下至少有五个明确子系统：

- `partner-recommendation-system`
- `partner-matchmaking-system`
- `partner-chat-system`
- `partner-discovery-system`
- `partner-http-gateway`

每个子系统都有自己的 service / storage / tests，且通常对应独立数据库 DSN。

#### 2. 共享领域能力被抽到根目录

以下能力是多个子系统共同依赖的：

- `match_domain`: 统一状态、事件、账本、outbox
- `async_jobs`: 异步任务队列
- `db_migrations`: 多目标数据库迁移
- `observability`: 指标、漏斗、告警、审计
- `profile_service`: 资料读取与写入
- `persona_memory_sync`: 用户画像记忆
- `partner_search`: 匹配检索引擎

#### 3. 数据存储是“多库 + 共享资料源”的模式

从 `.env.example` 可以确认：

- recommendation、matchmaking、chat、discovery 都有独立 MySQL 库
- persona memory 与 profile source 可共享同一资料库
- 前台业务库与资料库不是完全同一个系统

#### 4. 系统已考虑异步一致性

代码中存在：

- transactional outbox
- async_jobs
- worker
- retry / backoff / claim timeout
- scheduler

这说明系统已经开始从“单进程业务逻辑”向“可持续运行的后台业务平台”演进。

---

## 5. 代码库结构解读

### 5.1 根目录共享模块

#### `partner_search/`

候选人检索与匹配引擎，负责：

- 数据源加载
- 条件标准化
- 画像映射
- 候选过滤
- 互选兼容性
- 风险标记
- 排序与多样性选择
- 无结果诊断

#### `persona_memory_sync/`

用户画像记忆服务，负责：

- persona memory 写入
- 观察证据落库
- persona -> public profile 渲染
- persona 与资料表同步

#### `profile_service/`

统一的资料读写接口层，负责：

- MySQL 资料源解析
- 自动识别 profile 表
- 列名兼容
- 获取 profile / photos
- 对资料表执行补丁与 onboarding 写入

#### `match_domain/`

共享领域模型层，负责：

- 推荐 / 撮合状态枚举
- 统一 ProfileRef / relation_key / pair_key
- 统一 MatchEvent 事件模型
- 账本收敛
- outbox 事件持久化
- trace / actor 上下文

#### `async_jobs/`

通用持久化异步任务队列，支持：

- enqueue / get / list
- 状态汇总
- retry pending / processing overdue
- worker 运行与回退

#### `db_migrations/`

多目标迁移框架，支持：

- recommendation
- matchmaking
- chat
- discovery
- persona

#### `task_scheduler/`

定时任务总线，负责调 recommendation / matchmaking / chat 的批处理作业。

#### `observability/`

负责：

- funnel 埋点
- metric gauge
- health 检查
- backlog 告警
- audit event

### 5.2 外部业务子系统

#### `partner-recommendation-system`

负责持续检索、推荐入池、推荐卡投递、用户动作记录、代理牵线前置状态管理。

#### `partner-matchmaking-system`

负责双边候选池、边关系、pair 生成、案例开启、回复和反馈闭环。

#### `partner-chat-system`

负责聊天、会话、AI 助手上下文、风险风控、举报、资料审核、活体认证、登录认证。

#### `partner-discovery-system`

负责发现页对话会话、AI 决策、候选人搜索调用、资料详情构建、会话视图快照。

#### `partner-http-gateway`

统一对外 HTTP 接口层，承接 REST / JSON-RPC、认证、鉴权、限流、路由分发。

### 5.3 前端

`frontend/her-app` 是移动端风格的单应用，当前以单页壳层组织：

- 登录与 onboarding
- 发现
- 推荐来信
- 关系
- 聊天
- 认证流程
- 信任中心
- 个人资料

---

## 6. 关键运行配置

### 6.1 数据库配置

环境变量中明确了以下数据库：

- `PARTNER_RECOMMENDATION_DB`
- `PARTNER_MATCHMAKING_DB`
- `PARTNER_CHAT_DB`
- `PARTNER_DISCOVERY_DB`
- `PERSONA_MEMORY_MYSQL_SOURCE`
- `HER_DISCOVERY_PROFILE_SOURCE`
- `HER_PROFILE_SOURCE_DSN`

这说明系统在逻辑上区分：

- 运营流程库
- 用户资料源
- persona 记忆源

### 6.2 模型与 AI 运行配置

系统支持至少两类 AI 场景：

- 聊天/红娘助手运行时
- Discovery 发现页 Agent 运行时

关键配置包括：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `HER_CHAT_AGENT_MODEL`
- `HER_CHAT_AGENT_RUNTIME`
- `HER_DISCOVERY_AGENT_RUNTIME`
- `HER_DISCOVERY_AGENT_MODEL`
- `HER_DISCOVERY_AGENT_WIRE_API`

`discovery_system.agent_runtime` 明确支持 Agents SDK，并适配 OpenAI 兼容 `/responses` 或 `/chat/completions` 接口。

### 6.3 运维与后台处理配置

环境变量中包含：

- schema 初始化模式
- outbox worker 批大小
- retry delay / backoff
- claim timeout
- scheduler 开关
- verification provider
- SMS provider

说明系统已考虑本地联调、预发和生产模式差异。

---

## 7. 核心领域模型

### 7.1 推荐关系状态

`match_domain.model.RelationStatus` 定义了从候选关系到经营动作的一组状态，例如：

- `new`
- `recommended`
- `saved`
- `skipped`
- `cooling`
- `direct_greet_started`
- `proxy_intro_active`
- `closed`

### 7.2 撮合 Pair 状态

`PairStatus` 用于描述双边关系成熟度：

- `eligible`
- `below_threshold`
- `blocked`
- `cooling`
- `case_opened`
- `mutual_accept`
- `needs_revalidation`
- `stale`

### 7.3 案例状态

`CaseType` 与 `CaseStatus` 统一了代理牵线与撮合案例的生命周期。

### 7.4 统一 Profile 引用

`ProfileRef` 通过 `source + profile_id / user_key` 建立稳定引用，用于跨系统关联用户资料。

### 7.5 事件模型

`MatchEvent` 统一事件字段：

- event_id
- event_type
- aggregate_type
- aggregate_id
- actor_type / actor_id
- source_service
- correlation_id
- idempotency_key
- payload
- trace_id

这为跨系统账本、事件追踪和 outbox 传播提供了基础。

---

## 8. 系统分层说明

### 8.1 表现层

前端 `her-app` 提供用户交互界面，通过 Next.js route handler 将请求代理到 Gateway。

### 8.2 接入层

`gateway/app.py` 是统一入口，负责：

- 健康检查
- 身份解析
- 权限控制
- 限流
- 数据库连接池
- 路由到 recommendation / matchmaking / chat / discovery / auth / verification / profile

### 8.3 业务服务层

五个业务子系统各自承担垂直职责。

### 8.4 共享能力层

匹配、persona、profile、事件、迁移、任务、观测等共享能力被集中管理。

### 8.5 数据层

采用多 MySQL 库 + 共享 profile source 的组织方式。

---

## 9. 已实现功能清单

以下功能为当前代码中已实现或明确接通的能力。

### 9.1 用户登录与账户体系

对应代码：

- `chat_system/auth_accounts.py`
- `gateway/auth_routes.py`
- `frontend/her-app/hooks/use-auth-flow.ts`

已实现能力：

- 手机短信验证码登录
- 微信登录
- 微信后绑定手机号
- 运营商一键登录尝试与验证
- access token / refresh token
- `auth/me`
- onboarding 状态查询与更新
- 开发环境 stub 登录

交互逻辑：

1. 用户选择登录方式
2. Gateway 调用 `chat_system` 账户服务
3. 登录成功后前端拉取 `auth/me`
4. 根据 `phone_bound`、`is_new_user`、`onboarding_status` 决定进入绑手机、欢迎页或主界面

### 9.2 新用户 Onboarding

对应代码：

- `auth_routes.py`
- `auth_accounts.py`
- `frontend/her-app/components/her/auth/onboarding-page.tsx`

已实现能力：

- 存储基础信息
- 存储偏好信息
- 标记 onboarding 完成
- 写入 profile / requester / case 等前台上下文

### 9.3 资料服务与档案读取

对应代码：

- `profile_service/api.py`

已实现能力：

- 自动识别 profile 表
- 列表 / 单条 profile 查询
- profile 列名兼容与检测
- 读取照片表
- persona patch 写回资料
- onboarding 资料落表

### 9.4 Persona Memory 画像记忆

对应代码：

- `persona_memory_sync/persona_memory_engine.py`
- `persona_memory_sync/api.py`

已实现能力：

- 用户画像 patch 写入
- 记录置信度、证据文本、对话引用
- persona 同步至 profile
- 生成公开资料视图

系统价值：

- 让“用户表达过但尚未结构化”的偏好和特征长期可复用
- 让发现页、撮合反馈、聊天反馈都能沉淀到同一画像底座

### 9.5 候选人搜索与匹配引擎

对应代码：

- `partner_search/search_candidates.py`
- `partner_search/search_matching.py`
- `partner_search/search_reciprocal.py`
- `partner_search/search_ranking.py`
- `partner_search/search_trust.py`

已实现能力：

- 多数据源搜索
- 自我画像构建
- 条件标准化
- 年龄、身高、学历、收入、城市、婚育等结构化匹配
- must-have / prefer / exclude 关键词
- 互选兼容性判断
- 风险标记与 follow-up questions
- 可信度、照片、活跃度、资料一致性加权
- 结果排序与多样性控制
- 无结果诊断与补救候选

这部分成熟度较高，是整个系统的核心引擎。

### 9.6 Discovery 发现页对话式找对象

对应代码：

- `discovery_system/service.py`
- `discovery_system/agent_runtime.py`
- `gateway/discovery_routes.py`
- `frontend/her-app/components/her/discover-page.tsx`

已实现能力：

- 创建 discovery session
- 基于会话状态运行 Agent 决策
- 用户输入文本或点击建议动作推进流程
- 调用候选搜索工具
- 构造会话 timeline、criteria chips、suggested actions、result groups
- 保存 turn、tool call、view snapshot、search run
- 获取候选人详情页数据

交互逻辑：

1. 前端创建 discovery session
2. Agent 输出初始欢迎语与引导
3. 用户持续描述偏好
4. Agent 在合适时机调用搜索
5. 返回候选结果卡片
6. 用户进入候选详情或继续补充偏好

### 9.7 持续推荐订阅

对应代码：

- `recommendation_system/service.py`
- `gateway/recommendation_routes.py`

已实现能力：

- 创建 saved search subscription
- 保存初始请求与订阅覆盖项
- 判断订阅是否到刷新时间
- 刷新时重新构建搜索请求
- 记录 `saved_search_runs`
- 记录规则版本与输入指纹 `rule_provenance`

这是“持续经营”能力的重要基础。

### 9.8 推荐结果入池与审核

对应代码：

- `recommendation_system/service.py`
- `recommendation_system/direct_greet_gate.py`

已实现能力：

- 搜索结果 upsert 为 `profile_recommendations`
- 记录 fit_score / confidence_score / risk_score
- 记录 final review 状态
- 区分 `review_pending`、`pending_delivery`、`delivered` 等投递状态
- 支持用户前置 review 决策

### 9.9 推荐卡投递与来信收件箱

对应代码：

- `recommendation_system/service.py`
- `frontend/her-app/components/her/discover-page.tsx`

已实现能力：

- 构建 in-app recommendation card
- quiet hours 控制
- 每日通知上限控制
- 标记未读 / 已读
- 前端来信页读取推荐卡

卡片中已包含：

- 标题 / 副标题 / 文案
- 风险提醒
- 匹配点
- 建议确认项
- CTA 动作

### 9.10 推荐动作记录

对应代码：

- `recommendation_system/service.py`

已实现能力：

- `skip`
- `save`
- `direct_greet`
- 冷却期设置
- 推荐状态切换
- 幂等键防重
- 关系状态修订事件写入

### 9.11 代理牵线 / Proxy Intro

对应代码：

- `recommendation_system/proxy_intro.py`

已实现能力：

- 创建牵线 case
- 记录 outreach attempts
- 记录 reply
- 查询某推荐关联的 case

说明推荐系统已经不止“发卡”，还在向“代为推进关系”延伸。

### 9.12 撮合池管理

对应代码：

- `matchmaking_system/service.py`

已实现能力：

- 创建 / 更新 pool member
- 成员状态管理
- 是否仍在找对象
- 每日 case cap
- 刷新周期
- 允许渠道
- min_pair_score

### 9.13 双边边关系与 Pair 生成

对应代码：

- `matchmaking_system/service.py`

已实现能力：

- 生成单向 edge
- 检查 reciprocal edge
- 合成 pair
- 标记 `eligible / blocked / stale / cooling / needs_revalidation`
- 对失效 pair 做回收

### 9.14 撮合案例开启与推进

对应代码：

- `matchmaking_system/service.py`

已实现能力：

- 从 eligible pair 开 case
- 检查成员是否可用
- 检查每日案件上限
- 设置有效期
- 回复事件记录
- case 状态推进

### 9.15 反馈驱动的画像与关系回流

对应代码：

- `matchmaking_system/service.py`
- `profile_service.apply_persona_patch`

已实现能力：

- 记录 member feedback
- 可附带 persona patch
- 将反馈同步回 persona memory
- 根据反馈关闭 case 或触发重验证

这是“撮合反馈反哺推荐能力”的关键闭环。

### 9.16 聊天线程与消息

对应代码：

- `chat_system/service.py`
- `chat_system/conversations.py`
- `gateway/chat_routes.py`
- `frontend/her-app/components/her/chat-page.tsx`

已实现能力：

- 按 case 创建 thread / conversation
- 列出消息
- 发送消息
- owner_only / dyadic / system 可见性
- client_msg_id 幂等
- timeline 聚合

前端当前主要接入了 `v2 chat conversation` 读取与发送。

### 9.17 关系页

对应代码：

- `chat_routes.py`
- `frontend/her-app/components/her/relationships-page.tsx`

已实现能力：

- 按 case 拉取 timeline
- 列出现有关系会话
- 展示最近消息
- 展示未读态
- 进入聊天页

### 9.18 AI 助手上下文与会话编排

对应代码：

- `chat_system/assistant_context.py`
- `chat_system/assistant_sessions.py`
- `chat_system/assistant_runtime.py`
- `chat_system/assistant_orchestrator.py`

已实现能力：

- 收集 case 最近消息
- 获取资料快照
- 获取 conversation catalog
- Agent session / task 管理

从代码看，这部分已经具备后续接入红娘助手或关系顾问的基础。

### 9.19 聊天安全与风控

对应代码：

- `chat_system/risk.py`
- `chat_system/fraud_graph.py`
- `chat_system/moderation_ops.py`
- `gateway/chat_safety_routes.py`

已实现能力：

- 举报
- 见面反馈
- 风险案件列表
- 风险信号列表
- 欺诈网络观察与分析
- 风险申诉
- 周报式风险 dashboard
- 用户信任中心数据源

### 9.20 资料审核

对应代码：

- `chat_system/profile_reviews.py`
- `chat_system/profile_review_photo_risk.py`
- `gateway/profile_routes.py`

已实现能力：

- 字段认证提交 / 补交 / 复核 / 争议
- 风险资料案例
- 照片风险跑分
- 审核队列
- 审核申诉

### 9.21 活体视频认证

对应代码：

- `chat_system/verification.py`
- `chat_system/verification_live_challenge.py`
- `chat_system/live_video_local.py`
- `gateway/verification_routes.py`
- `frontend/her-app/components/her/verification-flow-page.tsx`

已实现能力：

- 创建 live challenge
- challenge phrase 与动作要求
- 本地视频资产写入
- 本地活体检测 provider
- 语音 / 动作 / 音画同步评分
- 自动 triage
- 人工 review
- notification
- resubmission

前端目前使用 stub 视频提交，但链路已经真实连到后端审核域。

### 9.22 信任中心

对应代码：

- `gateway/chat_safety_routes.py`
- `frontend/her-app/components/her/trust-center-page.tsx`

已实现能力：

- 汇总认证状态
- 待处理认证项
- 风险记录
- 审核通知

### 9.23 任务调度、异步作业与后台 Worker

对应代码：

- `task_scheduler/jobs.py`
- `async_jobs/queue.py`
- `match_domain/outbox_runtime.py`

已实现能力：

- recommendation 定时刷新
- recommendation 投递 worker
- matchmaking 刷池 / 建 pair / 开 case
- chat maintenance
- async job worker
- outbox consume worker

### 9.24 数据库迁移与环境初始化

对应代码：

- `db_migrations/workflow.py`
- `db_migrations/targets/*`

已实现能力：

- 多目标 schema 初始化
- `migrate` / `validate` 模式
- release-check

### 9.25 监控、指标与审计

对应代码：

- `observability/health.py`
- 各系统 service 中的 funnel / audit / metric 调用

已实现能力：

- recommendation / matchmaking / chat / discovery 漏斗事件
- async backlog 指标
- case backlog 告警
- refresh 低命中告警
- 审计事件

---

## 10. 关键业务流程

### 10.1 新用户入驻流程

1. 用户通过短信、微信或一键登录进入系统
2. 后端创建或识别 `user_account`
3. 前端调用 `auth/me`
4. 若是新用户，进入 onboarding
5. onboarding 资料写入 profile / onboarding 表
6. 用户进入主界面

### 10.2 发现式找对象流程

1. 前端创建 discovery session
2. Agent 输出开场与问题
3. 用户输入偏好
4. Agent 结合 runtime context 决定是否调用搜索
5. `partner_search` 返回候选结果
6. Discovery 将结果组织为结果卡片与建议动作
7. 用户点击候选详情或继续 refine 条件
8. 可进一步沉淀为 saved search subscription

### 10.3 持续推荐流程

1. 创建 subscription
2. 定时任务发现到期订阅
3. 刷新搜索条件并搜索
4. upsert 为 recommendation
5. 通过规则 gate 决定待审核、待投递或前置 review
6. 投递为 in-app 卡片
7. 用户在收件箱执行 skip / save / direct greet

### 10.4 撮合流程

1. 用户或运营创建 matchmaking pool member
2. 系统刷新 pool member 的候选 edge
3. 双边 edge 汇聚成 pair
4. 满足阈值且双方可用则开 case
5. case 推进联系、回复、接受或关闭
6. 成员反馈可回写 persona 并影响后续 pair

### 10.5 关系维护与聊天流程

1. 已有 case 对应一组会话
2. 关系页展示 case timeline
3. 用户进入会话发送消息
4. 风险模块可对消息、举报、异常模式做检测
5. 助手上下文模块可为后续 AI 介入提供消息窗口与资料快照

### 10.6 认证与安全流程

1. 用户在信任中心或资料页进入认证
2. 创建 live video challenge
3. 提交视频或字段材料
4. 系统做本地机器评估和状态流转
5. 需要时进入人工复核 / 补件 / 冻结 / 申诉
6. 认证结果进入通知与信任中心汇总

---

## 11. 前端信息架构

### 11.1 页面结构

当前前端主流程包括：

- `splash`
- `auth-welcome`
- `auth-phone`
- `auth-verification-code`
- `auth-wechat-binding`
- `auth-new-user-welcome`
- `auth-onboarding`
- `auth-recovery`
- `main-matchmaker`
- `recommendation-inbox`
- `candidate-detail`
- `main-relationships`
- `chat`
- `verification`
- `trust-center`
- `main-profile`

### 11.2 主导航

底部主导航有三大页签：

- Matchmaker
- Relationships
- Profile

### 11.3 前后端连接方式

前端通过 `app/api/gateway/[...path]/route.ts` 代理到 `PARTNER_GATEWAY_BASE_URL`，特点是：

- 自动透传 cookie token
- 可注入 API key
- 所有页面统一走 `/api/gateway/*`

这是标准的 BFF 代理模式。

---

## 12. 当前成熟度评估

### 12.1 已较成熟的部分

- 匹配搜索引擎
- 推荐订阅与推荐卡链路
- 撮合池、pair、case 状态机
- 认证、审核、风险、安全域
- 数据迁移、异步任务、可观测性基础设施

### 12.2 中等成熟的部分

- Discovery 对话式找对象
- Persona memory 与业务联动
- 聊天与关系页真实接口接入
- 前端主流程打通

### 12.3 仍偏原型或待增强的部分

- 前端仍混合较多 fallback/mock 数据
- 一些字段认证前端仍是 UI 占位
- 聊天 AI 助手尚未全面产品化
- recommendation / discovery / matchmaking 跨域联动指标还不够统一
- 多租户、权限模型、后台运营台尚未成型

---

## 13. 主要问题与架构风险

### 13.1 模块数量多，产品边界已经接近平台化

当前系统同时承载推荐、撮合、聊天、审核、认证、风控、登录、AI 会话。优势是业务闭环已经较完整，但这也意味着系统复杂度不再只是“模块数量增加”，而是在向“多业务域协作平台”演进。

真正的风险在于跨域耦合会持续上升：

- 任一业务域变更都可能影响上下游链路
- 联调、发布、排障成本会越来越高
- 责任边界若不持续收敛，容易出现“问题大家都能处理，但没人真正负责”的情况

后续需要更明确地区分核心主链路、支撑能力和运营能力，避免所有能力继续堆叠在同一套演进节奏中。

对当前系统而言，最核心的业务主线应优先收敛为“找对象 -> 建立连接 -> 聊天”：

- `discovery` / `partner_search` / `recommendation` 负责帮助用户表达需求并找到合适对象
- `matchmaking` / `relationship` 负责让推荐结果进入可推进的双边关系
- `chat` 负责让关系进入实际交流与后续维护

而认证、审核、风控、画像、运营任务等能力应作为支撑域存在，负责放行、拦截、校验和辅助决策，而不应与主链路并列定义产品主流程。

这一收敛方向在当前代码中已经开始落地，尤其体现在 recommendation 与 proxy-intro / case 的边界调整上：

- `profile_recommendations.delivery_status` 已开始收缩为纯推荐主状态
- proxy-intro 生命周期由 `match_cases.case_status` 继续作为 owner
- recommendation 侧新增 `active_case_status` 作为活跃 case 的镜像字段，用于展示而不是定义主事实
- 已新增 recommendation 数据迁移，将历史 `proxy_intro_*`、`save_only`、`review_skipped` 等旧 `delivery_status` 值回填到新语义
- recommendation 读模型现已显式暴露 `recommendation_status` / `recommendation_phase` 与 `case_progress_status`，用来区分“推荐侧状态”和“matchmaking 侧 case 进度展示”
- recommendation refresh run 现已显式暴露 `recommendation_status_counts` / `review_status_counts`，避免把 recommendation 自己的统计误读为 case 统计
- recommendation system 现已提供正式的 recommendation conversion view，把 recommendation 主状态、用户动作、proxy-intro case 进度聚合为单一读模型，便于前端展示、转化统计和排障

这意味着系统正从“单字段混合表达推荐、关系、case 三层含义”，逐步过渡到“推荐状态、关系状态、案例状态分层管理”。

但这只完成了第一段，`13.1` 想要的“主链路清晰分层”还没有收口，当前仍有几类任务未完成：

1. recommendation / matchmaking 边界只拆了一半
   - recommendation 主状态、case 镜像字段、refresh 统计口径，以及 recommendation -> action -> case 的统一转化视图已经完成第一轮收敛
   - review 字段与规则参数入口已完成第一轮收敛：`subscription_overrides` 已区分搜索条件 override 与 `review_policy` override，recommendation 读模型也已显式投影 `review_policy`、`system_review_decision`、`user_review_decision`
   - recommendation -> proxy-intro -> chat、matchmaking -> case -> chat 的关键跨系统回归已补上，gateway timeline 与 async dashboard 也已开始按统一链路联调验证
   - recommendation / matchmaking / chat 的统一指标口径现已补到 `relationship_ledger` 读侧：新增跨系统 funnel dashboard，把 relation/case 统一投影为同一套阶段统计，供 gateway dashboard 和后续报表复用
   - recommendation / matchmaking / chat 的完整多场景回归矩阵已补到关键主链路：当前已覆盖 handoff -> chat、proxy-intro timeout -> cooling、matchmaking mutual accept、decline -> cooling、timeout -> cooling、timeline / dashboard 读侧一致性等关键分支

2. `profile` / `persona` / 搜索使用条件三层仍然混在一起
   - 理想上应区分：
     - `profile`：用户正式资料事实
     - `persona`：系统推断和理解
     - `effective_criteria`：最终给搜索/排序用的编译后条件
   - 但当前实现里，`persona_memory_sync` 仍会把一部分 persona 推断结果写回 profile，再被 discovery / recommendation / search 消费
   - 这意味着“用户明说的”和“系统猜出来的”还没有彻底分开，后续需要明确哪些字段可以同步，哪些只能停留在 persona 层，哪些只能作为搜索层编译结果存在
   - 更完整的目标状态应进一步收敛为四层，而不是只停留在概念区分：
     - `profile_facts`：用户自己填写或明确确认的正式资料事实
     - `preference_memory`：用户明确表达过、但不一定适合公开展示的择偶偏好
     - `persona_inference`：系统从对话、行为中推断出的理解，且必须区分 `strong_inference` 与 `weak_inference`
     - `effective_criteria`：推荐 / 搜索 / 排序运行时真正消费的编译后条件
   - 这四层在产品上的直白含义分别是：
     - `profile_facts`：用户档案
     - `preference_memory`：用户明确说过的偏好记录
     - `persona_inference`：系统自己的理解笔记
     - `effective_criteria`：系统内部拿去筛人的工作单
   - 后续收敛时应遵守以下强规则：
     - 基础且重要的事实字段不能通过对话推测直接写入正式资料，只能来自资料表单或用户显式确认
     - 用户资料展示页只能展示 `profile_facts`，不能把系统推断内容伪装成用户已填写资料
     - 对话和行为产生的信息必须至少区分 `explicit_statement`、`strong_inference`、`weak_inference`
     - 推荐运行时可以同时使用正式资料、明确偏好和推断信号，但系统必须清楚知道每个字段的来源与置信度
     - 用户后续显式填写或确认的内容，优先级必须高于系统推断
   - 字段层面建议进一步分层为：
     - `P0 强事实字段`：年龄、身高、城市、婚姻状态、是否要孩子、学历、职业等，只能通过资料填写或显式确认写入 `profile_facts`
     - `P1 明确偏好字段`：年龄范围、城市偏好、介意抽烟、关系目标、喜欢成熟型等，可来自资料填写或用户明确表达，进入 `preference_memory`
     - `P2 推断字段`：沟通风格、安全感需求、对节奏的偏好、对某类对象的隐性倾向等，只能进入 `persona_inference`
     - `P3 运行时条件`：过滤条件、排序权重、探索系数、场景策略修正等，只存在于 `effective_criteria`
   - 其中 `persona_inference` 不能只是一个松散 blob，而应至少带上：
     - `source`
     - `confidence`
     - `strength`
     - `evidence`
     - `updated_at`
   - 这意味着 `persona_memory_sync` 的职责也要收敛：它应从“既记忆 persona、又顺手改 profile”的混合模块，调整为三段式流程：
     - `signal extraction`：从对话、行为、历史记录中提取信号
     - `memory classification`：判断该信号应进入 `profile_facts`、`preference_memory` 还是 `persona_inference`
     - `safe persistence`：按层落库，并通过字段白名单禁止跨层乱写
   - 推荐 / 搜索 / discovery 后续不应继续各自直接拼接 profile 与 persona，而应统一改为消费类似 `compile_effective_criteria(user_id, scene)` 的编译入口：
     - 输入：`profile_facts`、`preference_memory`、`persona_inference`、当前场景与策略参数
     - 输出：`hard_filters`、`soft_preferences`、`ranking_features`、`source_map`
   - 其中 `source_map` 很关键，因为它决定系统能否回答“这条推荐为什么出现”，并区分：
     - 哪些条件来自用户正式资料
     - 哪些来自用户明确表达
     - 哪些只是强推断
     - 哪些只是弱推断
   - 前端读侧也应同步拆开，而不是继续共用同一份混合画像：
     - 资料页只读 `profile_facts`
     - 偏好管理页读取 `preference_memory`
     - AI 理解页可选读取 `persona_inference`，并允许用户确认、忽略或纠正
     - 推荐解释与排序审计读取 `effective_criteria` 与 `source_map`
   - 从状态流转上看，推断字段至少应支持：
     - `inferred_weak`
     - `inferred_strong`
     - `user_confirmed`
     - `user_rejected`
   - 核心原则是：系统可以猜，但不能自动把猜测升级成正式档案；只有用户确认后，部分内容才允许升格为正式偏好，`P0` 强事实字段则必须始终经过显式确认
   - 结合当前代码，这一层的实施顺序建议分三期推进：
     - 第一期止血：收紧 `persona_memory_sync -> profiles` 的同步白名单，禁止推断写入 `P0` 强事实字段，资料页只读正式资料源，并为推荐日志补充字段来源标记
    - 第二期拆层：保持 `profiles` 只承载资料填写事实，同时把聊天记忆继续统一留在 `persona_memory` / `user_personas` 一侧，但要求每条记忆显式标注“用户明确表达”还是“系统推断”，并补齐 `confidence`、`evidence`、`source_channel` 等元数据
     - 第三期统一编译：让 recommendation / matchmaking / search 统一消费 `effective_criteria` 编译结果，同时保留必要的 criteria snapshot 以支持推荐解释、AB 实验和排障
   - 这一改造完成后，系统会从“把聊天理解直接写进资料”转成“把聊天理解先记为笔记，再按规则编译进推荐”，从而真正完成 `profile` / `persona` / 推荐使用条件三层的边界收敛
   - 为了把这一方案真正落地，后续可以继续拆成以下 6 组具体任务：
     - 任务包 1：字段分层与规则冻结
       - 盘点当前所有 `profile / persona / search criteria` 相关字段
       - 为每个字段标注所属层：`P0 强事实字段`、`P1 明确偏好字段`、`P2 推断字段`、`P3 运行时条件`
       - 为每个字段补写入规则：只能资料填写、只能显式确认、可来自明确表达、可来自强推断、可来自弱推断
       - 为每个字段补展示规则：是否允许出现在资料页、偏好页、AI 理解页、内部推荐解释
       - 为每个字段补推荐使用规则：是否允许进入 `effective_criteria`、是硬过滤还是软偏好、推断权重上限是多少
       - 验收标准：所有现有画像字段都被归类，且不再存在“来源不明、权限不明”的字段
     - 当前代码基线下的第一版字段户口表可先冻结如下：
         - `P0 强事实字段（正式资料事实）`
           - 当前字段：`display_name`、`self_gender`、`self_age`、`self_city`、`self_district`、`self_height`、`self_education`、`self_income_wan`、`self_job`、`self_marital_status`、`self_has_children`、`self_children_count`、`self_children_living_with_self`
           - 边界说明：这些字段定义“我是谁、我当前现实情况如何”，属于正式资料，不允许系统靠对话推测直接写入
           - 写入规则：仅允许 `profile_form` 或 `explicit_confirmation`
           - 展示规则：资料页可展示；推荐解释可引用；AI 理解页不可把它们展示成“系统猜测结果”
           - 推荐规则：允许进入 `effective_criteria`，必要时可作为硬过滤或候选特征
         - `P0-P1 过渡字段（建议按正式偏好事实管理，不允许弱推断写入）`
           - 当前字段：`self_smoking`、`self_drinking`、`self_relationship_goal`
           - 边界说明：这几项既像自我资料，又带偏好/表达性，短期内应按“正式填写或明确确认后生效”的方式管理，而不是开放给推断自动改写
           - 写入规则：允许 `profile_form`、`explicit_confirmation`、`explicit_statement`，不允许 `weak_inference`
           - 展示规则：资料页可展示，但必须只展示用户填写或确认后的值
           - 推荐规则：允许进入 `effective_criteria`
         - `P1 明确偏好字段（用户明说的择偶条件与接受边界）`
           - 当前字段：`target_gender`、`target_age_min`、`target_age_max`、`target_cities`、`target_height_min`、`target_height_max`、`target_education_min`、`target_income_min_wan`、`target_income_max_wan`、`target_marital_statuses`、`target_marital_status_strength`、`target_accept_partner_children`、`target_accept_partner_children_strength`、`target_accept_long_distance`、`target_location_semantics`、`target_requires_partner_accept_my_children`、`target_want_children`、`target_marriage_timeline`
           - 边界说明：这些字段定义“我想找什么样的人、边界在哪里”，不是自我事实，也不应伪装成公开资料
           - 写入规则：允许 `profile_form`、`explicit_statement`、`explicit_confirmation`；不允许 `weak_inference` 直接写成正式偏好
           - 展示规则：偏好页可展示；资料公开页默认不展示；推荐解释可展示来源
           - 推荐规则：允许进入 `effective_criteria`；其中年龄、城市、婚况、子女接受度、异地接受度可按场景进入硬过滤，其余更多作为软偏好
         - `P2 推断标签字段（系统理解出的偏好标签）`
           - 当前字段：`must_have_tags`、`must_not_have_tags`、`preferred_traits`、`disliked_traits`
           - 边界说明：这些字段当前最混，代码里既被当成 matcher 偏好，又被当成 persona 推断；后续应统一归到 `persona_inference`
           - 写入规则：允许 `explicit_statement`、`strong_inference`、`weak_inference`，但必须带 `source`、`confidence`、`strength`
           - 展示规则：AI 理解页可展示；资料页不可展示成正式资料；偏好页只展示用户已确认或明确表达部分
           - 推荐规则：允许进入 `effective_criteria`，但默认只能作为软偏好，不能直接当硬过滤
         - `P2 推断总结字段（系统内部理解与公开草稿）`
           - 当前字段：`persona_summary_internal`、`preference_summary_internal`、`public_profile_summary_draft`、`public_preference_summary_draft`
           - 边界说明：这些字段是系统总结和文案草稿，不是用户正式资料，也不是可直接用于硬过滤的结构化条件
           - 写入规则：允许 `strong_inference`；其中 `public_*_draft` 允许运营或用户确认后再发布，不允许自动当正式资料
           - 展示规则：`*_internal` 仅内部可见；`public_*_draft` 仅作为草稿预览，不直接等同于资料页事实
           - 推荐规则：不直接当硬过滤；如要使用，只能经过结构化编译后转成软特征
         - `P2 软自我描述字段（当前代码里仍放在 explicit-only，但建议后续从正式事实中拆出）`
           - 当前字段：`self_life_rhythm`、`self_work_pattern`、`self_expression_style`
           - 边界说明：这类字段比年龄、城市更主观，更像“自我风格描述”；短期可继续要求明确表达，长期更适合落在 `persona_inference` 或“已确认的自我描述”层
           - 写入规则：短期允许 `explicit_statement` / `explicit_confirmation`；长期不建议让弱推断直接入正式资料
           - 展示规则：可在 AI 理解页或用户自我描述页展示；资料公开页谨慎展示
           - 推荐规则：允许作为软排序特征
         - `P3 运行时条件（搜索 / 推荐编译后条件）`
           - 当前代码中已散落存在的运行时字段包括：`height_min/max`、`cities`、`settlement_cities`、`relationship_goals`、`smoking`、`drinking`、`marital_statuses`、`want_children`、`accept_partner_children`、`must_not_have`，以及排序时使用的 `communication_style`、`relationship_capacity`、strictness、risk_flags 等
           - 边界说明：这些字段不是长期档案，而是每次搜索 / 推荐前由 `profile_facts + preference_memory + persona_inference` 编译出来的执行条件
           - 写入规则：不允许人工直接长期写库为主事实；应由 `compile_effective_criteria(...)` 动态生成
           - 展示规则：不在资料页展示；可在推荐解释、调试页、运营报表中展示
           - 推荐规则：这是推荐 / 搜索真正消费的一层，其中要明确区分 `hard_filters`、`soft_preferences`、`ranking_features`、`risk_controls`
       - 基于当前代码，还需要同步冻结以下跨层冲突判断：
         - `partner_search/api.py::normalize_persona_profile(...)` 当前把 `self_*`、`target_*`、`must_have_tags`、`preferred_traits` 等混入同一对象消费，说明 `P0/P1/P2` 仍未真正分开
         - `persona_memory_sync/persona_memory_lib.py::build_profile_payload(...)` 当前会把 persona 字段重新写回 profile payload，这是 `P2 -> P0/P1` 污染的主要入口
         - `persona_memory_sync/audit.py` 已经隐含了一部分正确边界：`strong_inference_patch` 仅允许 `must_have_tags`、`must_not_have_tags`、`preferred_traits`、`disliked_traits`、`persona_summary_internal`、`preference_summary_internal`、`public_*_draft`
       - 该任务包的第一轮落地已完成：
         - 已在 `persona_memory_sync/persona_memory_lib.py` 中把 `display_name`、`self_gender`、`self_age`、`self_city`、`self_district`、`self_height`、`self_education`、`self_income_wan`、`self_job`、`self_marital_status`、`self_has_children`、`self_children_count`、`self_children_living_with_self` 从 persona 自动回写 profile 的映射中摘除
         - 这意味着 `build_profile_payload(...)` 与 `profile_columns_for_persona_patch(...)` 的自动 profile 同步路径，已不再更新上述 `P0` 强事实字段
         - 同时保留了 `target_*` 偏好字段以及 `matcher/public` 相关安全投影的同步能力，避免 recommendation / search / public profile 依赖被一次性打断
         - 已补单元测试验证：persona patch 仍可更新安全偏好列，但不会再生成 `age`、`city`、`height`、`marital_status`、`has_children` 等正式资料列更新
       - 因此，任务包 1 的最终冻结结果应当形成一张正式字段表，至少包含以下列：
         - `field_name`
         - `current_source`
         - `target_layer`
         - `allowed_write_sources`
         - `display_surface`
         - `criteria_usage`
         - `notes`
     - 任务包 2：`persona_memory_sync` 写入止血
       - 梳理 `persona_memory_sync` 当前所有写 `profiles` 的入口
       - 梳理哪些字段现在会从 persona 自动同步到 profile
       - 建立 `profile sync allowlist`
       - 禁止推断写入所有 `P0` 强事实字段
       - 将非白名单字段改为写入 `persona_inference` 或临时观察记录，而不是继续写 `profiles`
       - 为同步逻辑补充来源标记：`profile_form`、`explicit_confirmation`、`explicit_statement`、`strong_inference`、`weak_inference`
       - 为资料页读模型加保护，确保只读正式资料源
       - 验收标准：对话推断不能再改年龄、城市、婚姻状态等正式资料字段，资料页也不再展示推断内容
     - 任务包 3：轻量化画像存储边界收敛
       - 明确 `profiles` 只保留用户资料填写或资料编辑确认后的正式事实，不再承载聊天中产生的偏好和推断
       - `persona_memory` / `user_personas` 继续作为聊天记忆主容器，统一接收来自 AI 红娘对话和匹配对象聊天的补充信息
       - 但每条聊天记忆必须最少补齐以下元数据：`field`、`value`、`source_type`、`source_channel`、`confidence`、`evidence`、`updated_at`
       - `source_type` 至少区分两类：`explicit`（用户明确说的）与 `inferred`（系统推断出的）
       - `source_channel` 至少区分两类：`matchmaker_chat` 与 `candidate_chat`
       - `confidence` 不做拍脑袋打标，而是根据信号强弱逐步累积：
         - `explicit`：用户只明确表达过 1 次通常为 `low`；跨 session 多次一致表达提升到 `medium`；跨场景稳定表达或用户主动确认后提升到 `high`
         - `inferred`：单条弱证据通常为 `low`；多条独立证据且语义一致提升到 `medium`；跨场景长期一致且无反证提升到 `high`
         - 同一会话内机械重复不应线性加分；跨 session、跨 channel 的独立重复权重更高
         - 出现反向表达或用户否定时，`confidence` 必须下降，严重冲突时应标记为 `contradicted` 或 `rejected`
       - 每条聊天记忆建议同时记录辅助统计字段，以支持后续置信度计算：`evidence_count`、`distinct_session_count`、`distinct_channel_count`、`last_seen_at`、`status`
       - 历史数据不要求一次性重拆成多张新表，但需要补 migration / backfill，把旧 persona blob 中后续还要参与推荐的字段补上来源标记和最小可用置信度
       - 为迁移与回填过程增加审计日志，避免“旧字段来源不明却被当成高可信输入”
       - 验收标准：
         - `profiles` 中只剩正式资料事实
         - 聊天得到的信息不再回写正式资料
         - 推荐系统能够区分“用户明确说的”和“系统推断的”
         - 每条参与推荐的聊天记忆都能回答“它从哪来、出现过几次、当前可信度如何”
     - 任务包 4：`effective_criteria` 编译层建设
       - 设计 `compile_effective_criteria(user_id, scene)` 接口
       - 定义标准输入：`profile_facts`、`persona_memory`、`scene`、`strategy params`
       - 定义标准输出：`hard_filters`、`soft_preferences`、`ranking_features`、`source_map`、`strategy_flags`
       - 制定优先级规则：`profile_facts` > `persona_memory[source_type=explicit]` > `persona_memory[source_type=inferred, confidence=high/medium/low]`
       - 制定冲突合并规则：用户资料填写覆盖聊天记忆；`explicit` 高于 `inferred`；低置信度推断不能变成硬过滤；被 `rejected` / `contradicted` 的记忆不应继续进入有效条件
       - 让 recommendation 改为只消费编译结果
       - 让 search 改为只消费编译结果
       - 让 discovery 的后续订阅 / 搜索条件保存也改走编译层
       - 增加 `criteria snapshot` 或调试日志，用于推荐解释和排障
       - 验收标准：推荐、搜索、发现不再各自直接拼接 profile 与 persona，系统可以解释某个推荐条件来自哪里
     - 任务包 5：前端与 API 读侧拆分
       - 拆分资料页 API，只返回 `profile_facts`
       - 偏好 / 记忆页 API 改为返回按 `source_type`、`source_channel`、`confidence` 分组后的 `persona_memory`
       - 新增 AI 理解页 API 或在现有偏好页中显式区分“你明确说过的”和“系统推测的”
       - 用户纠正系统理解的主路径应是继续和 AI 红娘对话，而不是要求用户专门进入后台页面点按钮
       - 当用户在对话中出现新的明确表达，且与旧推断冲突时，系统应自动把这段新话记为 `explicit`，并把旧 `inferred` 记忆降级为 `contradicted`、`rejected` 或更低 `confidence`
       - AI 理解页更适合作为“系统当前如何理解你”的查看页与辅助干预入口，而不是唯一纠错入口
       - 推荐解释接口读取 `effective_criteria` 与 `source_map`
       - 前端文案明确区分“你填写的”“你明确说过的”“系统推测的”
       - 逐步下线旧的混合画像接口
       - 验收标准：资料页只显示正式资料，推断内容不会再冒充资料展示；用户既可以在查看页理解系统当前认知，也可以直接通过与 AI 红娘继续对话来修正系统推断
     - 任务包 6：测试、审计与迁移收尾
       - 补字段写入边界测试
       - 补资料页展示隔离测试
       - 补 `effective_criteria` 编译测试
       - 补来源优先级测试
       - 补用户确认 / 拒绝后的状态流转测试
       - 补推荐解释 `source_map` 测试
       - 补历史 persona 迁移回归测试
       - 补跨 recommendation / search / discovery 的端到端回归
       - 增加后台审计报表：推断写入次数、被用户确认次数、被用户拒绝次数、不同来源字段占比
       - 验收标准：改造后不会再出现“推断偷偷写进资料”，推荐链路也具备可解释、可回放、可审计能力
   - 若继续往执行层排期，建议按以下顺序推进：
     - 1. 盘点并分类现有 persona / profile / search 字段
     - 2. 定义字段写入来源与展示规则
     - 3. 收紧 `persona_memory_sync -> profiles` 同步白名单
     - 4. 禁止推断写入 `P0` 强事实字段
     - 5. 明确 `profiles` 只承载资料填写事实
     - 6. 为 `persona_memory` / `user_personas` 补 `source_type / source_channel / confidence / evidence / status`
     - 7. 建立 `confidence` 提升 / 降级规则，并补 `evidence_count / distinct_session_count / distinct_channel_count`
     - 8. 设计并实现历史 persona 数据回填与来源标记迁移
     - 9. 实现 `compile_effective_criteria(user_id, scene)`
     - 10. 统一 recommendation 消费 `effective_criteria`
     - 11. 统一 search 消费 `effective_criteria`
     - 12. 统一 discovery 后续条件保存 / 消费逻辑
     - 13. 拆分资料页 / 记忆页 / AI 理解页 API
     - 14. 支持通过与 AI 红娘继续对话来修正旧推断，并保留查看页上的辅助确认 / 纠正入口
     - 15. 增加推荐解释 `source_map`
     - 16. 补完整测试矩阵与审计指标

3. 统一关系总账已落地最小正式版本，但读侧切换还未完成
   - 新增独立 `relationship_ledger` 目标库，已包含 `match_relations`、`match_relation_cases`、`match_relation_events` 三张核心表
   - recommendation action、proxy-intro case event、matchmaking pair/case event、chat thread/message event 现已自动镜像到 ledger，形成跨 recommendation / matchmaking / case / chat 的统一 timeline 与 relation/case 投影
   - 这意味着系统第一次有了正式的跨域主事实层，不再只能靠 recommendation / matchmaking / chat 三边人工对账
   - gateway `/v1/timeline` 与 async dashboard 已开始切到 ledger 读侧，说明第一轮读侧接管已经启动
   - 这一层仍未全部收尾：虽然 matchmaking pool / pair 已并入同一 ledger，前端与报表也已有部分入口切到 ledger 投影，但还没有全面替换所有旧读路径，更多页面与更细运营报表仍在过渡期

4. 支撑域和主链路的职责隔离还停留在方向，不是实现
   - 理想主线应是：找对象 -> 建立连接 -> 聊天
   - 认证、审核、风控、画像、运营任务应作为支撑域，只负责放行、拦截、校验和辅助决策
   - 但当前很多支撑模块仍会直接影响主流程字段表达和跨域判断，说明“谁负责什么”还没有完全固化

如果继续扩张功能而不先完成这几项，系统就会越来越像“很多模块都能处理主流程”，最终导致联调、排障、归因和发布成本持续上升。

### 13.2 前端与后端真实程度不完全一致

前端中仍存在：

- fallback 数据
- mock 模式
- 某些页面展示本地示例资料
- verification 提交使用 stub 视频

这些现象本身不是问题，问题在于“界面可运行”与“真实业务链路已打通”并不完全等价。

对应的架构风险包括：

- 前端展示出的能力不一定对应真实后端能力
- 联调通过不代表线上端到端闭环已经成立
- 埋点、指标、体验判断可能被 fallback 或 mock 数据误导

如果这一差距长期存在，系统会逐步形成“演示态产品”和“真实生产能力”两套事实口径，影响交付判断与问题定位。

### 13.3 Profile / Persona / Auth / Recommendation 身份主键体系仍需继续收敛

当前系统并存：

- user_id
- requester_id
- profile_id
- user_key
- member_id
- case_id

虽然共享领域层已做统一引用，但产品层的数据口径仍较复杂。这里的核心问题不是“字段数量多”，而是“同一用户、同一资料、同一业务对象”在不同系统中的身份语义还没有完全稳定。

对应风险包括：

- 跨系统联查、排错、审计成本高
- 用户身份、资料身份、业务对象身份容易混用
- 后续在推荐、撮合、关系、风控之间做状态回流时，容易出现错绑、漏绑或重复挂载

特别是身份主键与业务对象主键应继续分层收敛，否则系统规模一旦扩大，数据一致性与追责能力都会受到影响。

### 13.4 Gateway 承担职责偏重

Gateway 当前同时负责：

- 鉴权
- 路由
- 接口整形
- 连接池
- 限流
- 多业务域入口

如果这些职责继续集中在同一层，Gateway 很容易从“统一入口”逐渐演化成“隐式业务编排中心”。

主要风险包括：

- 网关层改动需要理解多个业务域，维护成本持续上升
- 鉴权、聚合、协议适配、业务编排混在一起后，接口边界会越来越模糊
- 一旦流量、团队规模或后台运营需求继续增长，网关会成为演进瓶颈

后续若继续扩展，需要更明确地区分 API Gateway、BFF、后台运营 API 与跨域聚合逻辑。

### 13.5 规则系统仍以代码常量为主

如搜索、推荐 gate、风险阈值、quiet hours 等多以代码和环境变量配置。短期看这能加快开发，但长期会让规则演进能力受限。

主要风险包括：

- 规则散落在代码与环境变量中，缺少统一事实来源
- 很难回溯某次推荐、拦截、降权或限制是由哪条规则触发
- 运营调参、灰度发布、A/B 实验、审计复盘都会变重

因此，这一问题不只是“运营是否可调”，更关系到系统的可解释性、可审计性与可持续迭代能力。

---

## 14. 未来 3-6 个月产品规划建议

### 14.1 第一阶段：把“发现 -> 推荐 -> 关系”做成完整闭环

建议优先级最高。

目标：

- 让 Discovery 的对话结果稳定沉淀为 persona
- 让 Discovery 中“满意结果”可一键创建 subscription
- 让推荐卡动作更顺畅地进入聊天、收藏、代理牵线

建议事项：

- 在 Discovery 中显式展示“已理解偏好”
- 增加“保存为长期留意”动作
- 推荐卡增加更明确的下一步 CTA
- 统一 candidate detail 的真实字段展示

### 14.2 第二阶段：把信任体系前置

当前安全能力很多，但对用户主路径的暴露还不够系统。

建议事项：

- 把认证进度前置到 onboarding 完成后的关键引导
- 在候选详情页展示更强的可信标签
- 把聊天/关系页中的风险提示产品化
- 把信任中心做成可持续运营的“资料健康度中心”

### 14.3 第三阶段：构建“红娘协作台”

从代码趋势看，本系统非常适合做“AI 红娘 + 人工运营”协同。

建议事项：

- 新增运营工作台
- 查看 discovery 会话、推荐原因、pair 状态、risk case
- 支持人工审核推荐、人工介入撮合 case
- 支持追踪 case 漏斗转化

### 14.4 第四阶段：深挖长期经营能力

建议事项：

- saved search 精细化订阅策略
- 用户状态变化触发重新推荐
- 基于反馈自动修正 persona 偏好
- 关系阶段性任务，如提醒回访、见面后反馈、冷却期重启

---

## 15. 未来 3-6 个月技术优化建议

### 15.1 建议一：统一“身份与资料主键模型”

目标：

- 明确 user / profile / requester / member 的职责边界
- 在跨系统事件和 API 中统一主引用格式

收益：

- 降低跨系统 join 难度
- 降低前端接入复杂度
- 降低 case / chat / recommendation 间的数据映射错误

### 15.2 建议二：将规则参数配置化

优先配置化的对象：

- recommendation gate 阈值
- pair score 阈值
- skip cooldown
- daily cap
- quiet hours
- verification 自动 triage 阈值

收益：

- 支持 A/B 调优
- 支持运营迭代
- 降低频繁改代码发版的成本

补充说明：

- recommendation 近期已完成一轮状态语义收敛，把 `delivery_status` 从混合流程字段收缩为推荐主状态字段
- 下一步更适合继续把 `final_review_status`、`user_review_status`、case 镜像字段与可配置规则平台对应起来，而不是再把更多决策语义堆回主状态字段

### 15.3 建议三：补强真实数据接入，减少前端 fallback

建议：

- candidate detail 全量切到真实接口字段
- relationships 与 chat 去掉环境变量强依赖的演示路径
- verification 前端支持真实媒体采集
- profile 页面接入真实偏好和认证项

### 15.4 建议四：统一事件与审计查询能力

当前事件能力已具雏形，建议继续建设：

- relation timeline 查询
- recommendation -> action -> case 转化视图
- member feedback -> persona patch 追踪
- 风险处理审计链路

### 15.5 建议五：抽象运营任务中心

把以下异步能力汇总为统一运维视角：

- async jobs
- outbox backlog
- review queues
- verification queues
- matchmaking stale cases

### 15.6 建议六：扩展测试策略

当前已有不少单测，但下一阶段应增加：

- 关键业务回归场景测试
- recommendation -> matchmaking -> chat 跨系统集成测试
- Gateway 端到端认证与权限测试
- Discovery Agent 决策回归集

---

## 16. 推荐的阶段性路线图

### 16.1 未来 1-2 个月

- 打通 Discovery 与 Persona 的稳定回写
- 完善推荐收件箱与候选详情真实数据
- 打通认证状态在 Profile / Trust Center / Candidate Detail 的一致展示
- 清理前端核心页中的 fallback 路径

### 16.2 未来 2-4 个月

- 上线运营协作后台最小版本
- recommendation 与 matchmaking 指标统一
- 建立规则参数配置化能力
- 强化真实认证采集链路

### 16.3 未来 4-6 个月

- 推出 AI 红娘协作流程
- 建立 case 漏斗分析与复盘
- 基于反馈与关系结果反哺推荐模型
- 将平台从“原型闭环”提升到“可持续运营的业务系统”

---

## 17. 结论

从当前代码看，`Her` 已经具备一个“认真关系平台”应有的核心骨架：

- 它有搜索与推荐引擎
- 有双边撮合状态机
- 有关系聊天域
- 有认证、审核与风控体系
- 有对话式发现页
- 有 persona 记忆底座
- 有异步任务、迁移与可观测性基础设施

这意味着项目已经跨过“想法验证”阶段，进入“产品闭环搭建完成、等待聚焦与收敛”的阶段。

最值得优先推进的方向不是继续横向加模块，而是把现有模块真正串成一条高转化、高信任、可运营的主链路：

- 发现用户
- 理解用户
- 找到候选
- 推动关系
- 建立信任
- 长期经营

如果后续沿着这条主线继续收敛，项目会比典型婚恋 Demo 更接近一套真正可运营的关系服务平台。
