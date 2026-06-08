# Her 系统文档

## 1. 文档说明

本文档基于当前代码仓库的实际实现生成，重点阅读了：

- 根目录关键配置：`pyproject.toml`、`docker-compose.yml`、`.env.example`
- Python 后端核心包：`match_domain/`、`partner_search/`、`persona_memory_sync/`、`profile_service/`、`relationship_ledger/`、`task_scheduler/`、`assessment/`
- 外部子系统：`external-systems/partner-http-gateway/`、`partner-recommendation-system/`、`partner-matchmaking-system/`、`partner-chat-system/`、`partner-discovery-system/`、`signaling-server/`
- 前端主应用：`frontend/her-app/app/`、`frontend/her-app/components/`、`frontend/her-app/lib/`

未参考仓库内已有 Markdown 文档，因此本文内容以代码实现为准。

## 2. 系统概览

### 2.1 一句话定义

Her 是一个面向婚恋/严肃关系场景的「AI 红娘 + 推荐 + 牵线 + 关系经营 + 认证风控」一体化系统。

### 2.2 当前系统形态

从代码看，项目并不是单一应用，而是一个多子系统单仓（monorepo）：

- 前端：Next.js 16 + React 19 的移动优先应用
- 网关层：Python WSGI Gateway，统一暴露 REST 和内部 JSON-RPC
- 领域层：推荐、牵线、聊天、发现、画像、关系账本、测评、认证、规则配置等多个子域
- 存储层：以 MySQL 为核心，按子系统拆分数据库
- 基础设施层：Docker Compose、本地 MinIO、任务调度器、异步作业、健康监控、信令服务

### 2.3 推断的产品愿景

基于代码实现，可以推断系统的产品愿景是：

1. 用 AI 和结构化规则替代传统低效、重人工的婚恋服务流程。
2. 把“找对象”从一次性推荐升级为持续经营的关系操作系统。
3. 在推荐效率之外，强调真实性、安全性、关系推进和结果闭环。
4. 同时服务 C 端用户与 B 端/运营侧红娘团队，形成“用户自助 + 红娘协同 + 系统自动化”的混合模式。

### 2.4 系统试图解决的核心痛点

#### 用户侧痛点

- 资料不完整，导致推荐质量差。
- 靠人工浏览候选人效率低，表达偏好成本高。
- 推荐不透明，不知道“为什么推荐这个人”。
- 牵线、聊天、推进关系分散在不同流程里，体验割裂。
- 婚恋场景高风险，缺乏可信认证和风险识别。

#### 平台/红娘侧痛点

- 推荐、撮合、跟进、催回复等流程高度依赖人工。
- 用户状态、推荐状态、案例状态、关系阶段缺乏统一账本。
- 缺少实验分桶、规则配置、决策回溯等可运营能力。
- 多服务异步链路复杂，需要统一监控、重试和健康治理。

## 3. 总体架构

### 3.1 架构分层

#### 1. 体验层

- `frontend/her-app`
- 提供移动端主流程、发现页、关系页、我的页、认证、聊天、运营工作台
- 通过 Next.js Route Handler 将浏览器请求转发到后端 Gateway

#### 2. 接入层

- `external-systems/partner-http-gateway/gateway`
- 统一鉴权、路由分发、连接池、角色权限、限流、Trace 注入
- 按 `public` / `ops` / `internal` 三种 surface 暴露不同能力

#### 3. 业务域层

- Discovery：发现式搜索和 AI 红娘会话
- Recommendation：订阅式推荐和卡片投递
- Matchmaking：匹配池、互选对、牵线 case
- Chat：线程消息、风险识别、助手消息、视频通话、认证通知
- Persona/Profile：画像、资料写入、资料采集层、标签和人格特征
- Assessment：MBTI/依恋/大五/斯滕伯格/价值观拍卖
- Verification：字段认证、活体视频认证、照片风险复核
- Relationship Ledger：跨域关系时间线与关系阶段投影
- Rule Config / Experiment：规则版本、分桶、决策追踪

#### 4. 基础能力层

- `task_scheduler`：周期任务调度
- `async_jobs`：异步任务队列
- `db_migrations`：按子系统管理迁移
- `observability`：健康信号、告警、指标

#### 5. 存储层

- MySQL 多库拆分：
  - `her_recommendation`
  - `her_matchmaking`
  - `her_chat`
  - `her_discovery`
  - `her_relationship_ledger`
  - 共享资料库 `her?table=profiles`
- MinIO：媒体文件存储

### 3.2 运行时拓扑

从 `docker-compose.yml` 看，默认本地栈包含：

- `mysql`
- `bootstrap`
- `gateway-public`
- `gateway-ops`
- `gateway-internal`
- `scheduler`
- `signaling-server`
- `minio`
- `frontend`（可选 profile）

这说明系统已经具备较清晰的本地联调与准生产式拆分。

### 3.3 网关职责

Gateway 是整个系统的统一入口，核心职责包括：

- 加载根目录 `.env`
- 管理 recommendation / matchmaking / chat / ledger 数据库连接池
- 暴露 `/health`
- 按 route dispatcher 分发到各业务域
- 统一 REST 和 JSON-RPC 调用
- 从 Chat 子系统会话中解析登录态 principal
- 注入 trace_id、actor context、审计信息

### 3.4 Surface 设计

系统显式区分三类对外能力：

- `public`
  - 主要给前端 C 端使用
  - 允许 `/v1/...` 业务接口
- `ops`
  - 给运营/风控后台使用
  - 允许 `/v1/ops/...`
- `internal`
  - 给内部脚本和 JSON-RPC 调用
  - 支持 `/jsonrpc`

这是比较成熟的 API 面治理方式。

## 4. 核心数据与状态模型

### 4.1 资料与画像

系统存在两层用户数据：

- 基础资料层
  - 共享 MySQL `profiles` 表及关联照片表
  - 由 `profile_service` 统一读取和写回
- Persona/Collected 层
  - 记录用户显式表达、测评结果、偏好、证据来源、结构化 observation
  - 为推荐、发现、匹配提供更高质量的搜索输入

### 4.2 推荐、牵线、关系三层状态

从 `match_domain/boundary.py` 可见，系统有明确的状态边界：

- Recommendation 负责推荐投递类状态
- Matchmaking 负责 case 生命周期
- Relationship Ledger 负责跨域统一关系投影

这说明项目已经从“单表堆状态”演进到“分层状态治理”。

### 4.3 关系账本

`relationship_ledger` 会把推荐、牵线、聊天等 canonical event 汇聚成：

- `match_relations`
- `match_relation_cases`
- `match_relation_events`

最终形成：

- 关系状态
- 当前阶段
- 活跃 case
- 最近聊天线程
- 事件时间线

这是全系统最关键的“统一真相层”之一。

## 5. 已实现功能清单

## 5.1 用户登录与账户体系

### 已实现能力

- 手机号短信发送验证码
- 手机号验证码登录
- 微信登录
- 一键登录 create / verify
- 登录态持久化
- token 刷新
- 登录后 onboarding 状态检查
- 退出登录
- 微信绑定手机号
- 账号找回流程

### 关键交互逻辑

1. 前端欢迎页支持一键登录、微信登录、手机号登录三入口。
2. 验证成功后，通过 Next.js `/api/auth/session` 将 `access_token` 写入 HttpOnly Cookie。
3. 前端经 `/api/gateway/...` 代理请求后端，自动透传 Cookie 中的 token。
4. 网关通过 Chat 子系统的 auth session 反查 principal。
5. 若用户未完成 onboarding，则前端 guard 将其导向资料填写页。

## 5.2 新用户 onboarding 与资料完善

### 已实现能力

- 新用户欢迎页
- onboarding 表单
- onboarding 数据读写
- 资料采集层查询
- 资料标签编辑
- 编辑资料页

### 业务意义

系统非常重视“可用于搜索和推荐的结构化资料”，并不把 onboarding 当成一次性表单，而是整个后续推荐与发现链路的输入基础。

## 5.3 AI 红娘发现页

### 已实现能力

- 创建 discovery session
- 多轮会话式偏好收集
- session view 获取
- turn 提交
- AI 建议 action
- 候选人卡片结果组
- 对候选人表达兴趣
- profile update prompt 确认/拒绝
- 发现页支持语音输入
- 可插入心理测评和价值观拍卖卡片

### 核心交互逻辑

1. 用户进入发现页时创建 `discovery session`。
2. Discovery 可走两种模式：
   - `profile_first`
   - `agent`
3. 系统根据资料、偏好、历史上下文和工具调用结果，生成会话 view：
   - timeline
   - criteria chips
   - suggested actions
   - composer 提示语
4. 当 AI 认为资料缺失时，会生成 `profile_update_prompt`，用户可确认或拒绝写回。
5. 当 AI 认为适合进入测评或价值观模块时，会通过 suggested actions 触发对应流程。
6. 用户对候选人表达兴趣后，可进入推荐/牵线后续链路。

### 特点

- 发现页不是纯搜索框，而是“AI 红娘会话 + 搜索工具 + 资料回填”的复合体验。
- Discovery 子系统已有 session、turn、view snapshot、tool call audit、trace columns、profile update request 等持久化结构，成熟度较高。

## 5.4 搜索与候选人匹配

### 已实现能力

- 统一 partner_search 搜索
- reciprocal preferences 双向偏好
- search visibility gate
- search scoring config
- onboarding 默认搜索条件
- candidate detail 详情拉取
- 搜索快照持久化
- 缓存 TTL 与最大条数配置

### 核心逻辑

- 不只是按用户输入搜人，还会结合：
  - self profile
  - reciprocal preference
  - trust / moderation 条件
  - scoring 配置
  - visibility gate

这是一个“可配置、可解释、可沉淀快照”的搜索层，而不是简单 SQL 过滤。

## 5.5 订阅式推荐与推荐来信

### 已实现能力

- 创建 recommendation subscription
- refresh due subscriptions
- 推荐卡片投递
- 标记卡片已读
- 推荐动作记录：保存、跳过、直接打招呼等
- 用户 review 记录
- conversion view 查询
- 推荐决策 trace
- in-app delivery 和 quiet hours 判断

### 核心交互逻辑

1. Discovery 或显式操作可把搜索条件保存为 recommendation subscription。
2. Scheduler 定期刷新到期订阅。
3. 推荐子系统执行搜索、落库 recommendation、生成站内卡片。
4. 用户在“推荐来信”中浏览卡片，并进行保存、跳过、触发牵线等动作。
5. 系统统计转化表现，为后续规则优化和人工干预提供依据。

## 5.6 牵线与 Matchmaking

### 已实现能力

- 匹配池成员管理
- active pool refresh
- mutual pair build
- open match cases
- close stale / timeout cases
- proxy intro request
- 我的 proxy intro case 列表
- case 反馈回写
- 通过 case 打开聊天

### 核心交互逻辑

1. 用户可进入匹配池。
2. 系统基于搜索与规则构建 mutual pairs。
3. 对符合条件的 pair 打开 `match_case` 或 `proxy_intro_case`。
4. 用户可对红娘牵线进行接受/拒绝反馈。
5. 成功进入后可打开聊天线程。

### 特点

- 系统同时支持“推荐卡片流”和“红娘牵线 case 流”。
- `HER_PROXY_INTRO_STORAGE=matchmaking` 表示牵线 case 已收敛到 matchmaking 域管理。

## 5.7 关系页与关系经营

### 已实现能力

- 读取我的关系列表
- 读取 cross-domain timeline
- 读取 case conversation timeline
- 展示 active relationship 和 pending intro
- 未读消息汇总
- 小雅复盘面板
- 从关系页直接接受/拒绝牵线、进入聊天、查看对方详情

### 核心交互逻辑

关系页并非单纯聊天列表，而是“关系经营工作台”：

- 上层是关系状态和阶段
- 中层是 case 进展
- 下层是多会话消息和助手复盘

这说明产品目标不是撮合即止，而是持续推进关系转化。

## 5.8 聊天系统

### 已实现能力

- chat thread 创建
- message 发送与分页读取
- 可见性控制：dyadic / owner_only / system
- 私信与主群会话
- assistant context / runtime / orchestrator
- persona sync job
- message risk signal 捕获
- maintenance job
- outbox worker

### 核心交互逻辑

1. 牵线 case 可生成聊天线程。
2. 用户消息进入风控校验后写入消息表。
3. 系统会同步写出事件到 outbox，并镜像到 relationship ledger。
4. assistant 可在独立会话或辅助上下文里参与。
5. 聊天维持与推荐、牵线、关系账本的状态一致性。

## 5.9 聊天风控与信任中心

### 已实现能力

- Trust Hub
- 风险案例列表
- 风险案例批量复核
- 风险信号列表
- fraud network 图谱
- fraud observations 提交
- fraud evaluate
- 风险申诉
- 周报 dashboard
- meeting feedback
- chat reports

### 判断

这一部分代码量和接口完整度较高，说明平台已经把“婚恋安全”作为一级能力建设，而不是后补模块。

## 5.10 视频通话与信令

### 已实现能力

- 独立 signaling server
- call session 创建接口 `/v2/call/sessions`
- 前端视频通话弹层

### 说明

该能力当前更像配套基础设施，产品上可能服务于关系推进和认证场景。

## 5.11 测评系统

### 已实现能力

- MBTI 16 型测评
- 依恋类型测评
- 大五人格测评
- 斯滕伯格爱情三角测评
- 测评解释卡
- 小雅解读消息
- 测评标签写回 persona

### 核心逻辑

- 测评结果不只是展示，而会进入 persona memory / profile enrichment。
- Discovery 可把测评作为会话内动作触发。

## 5.12 价值观拍卖

### 已实现能力

- 单人价值观拍卖流程
- 双人共同价值观拍卖流程
- lots 获取
- 出价提交
- 结果解读
- 历史记录
- 复用上一轮
- 双人状态检查

### 产品意义

这是系统里较有差异化的深度关系洞察模块，用于把“匹配理由”从表层资料推进到价值观层面。

## 5.13 资料认证与活体视频认证

### 已实现能力

- 资料字段认证策略查询
- 字段认证提交与列表
- 认证过期处理
- 活体视频 challenge 创建
- 活体视频请求与提交
- 认证通知列表
- 机器审核 + 人工复核状态机
- 语音挑战、动作挑战、音视频同步校验
- 审核通过/拒绝/补件/冻结/关闭

### 关键特征

- 认证不仅校验视频，还和照片风险、profile 更新、通知系统联动。
- 支持严重风险标记，如 deepfake、replay attack、identity swap。

## 5.14 照片风险与资料审核

### 已实现能力

- profile review risk cases
- photo risk runs
- review queue
- appeals
- 审核通知

这部分与活体认证共同组成“资料真实性治理”。

## 5.15 Persona Memory 与资料同步

### 已实现能力

- persona patch
- personality traits 查询
- synthetic personality traits
- public profile helper
- schema tools
- field normalization
- persona audit

### 作用

该模块把测评、对话、显式偏好、资料更新等信息沉淀为统一 persona 资产，为搜索、推荐、发现提供更稳态的用户表示。

## 5.16 规则配置、实验分桶与运营协作

### 已实现能力

- 活跃 rule config 查询
- 规则版本列表
- 创建规则版本
- 激活规则版本
- 创建 assignment
- experiment bucket member 管理
- recommendation decision trace
- async job dashboard
- recommendation override

### 产品意义

系统已经具备“在线规则治理 + 运营干预 + 实验分桶 + 决策回溯”的平台化能力，说明目标不是 demo，而是可持续调优的业务系统。

## 6. 前端应用结构

### 6.1 页面结构

前端采用单入口应用壳：

- 启动与登录流
- 主导航三 Tab：
  - 发现/红娘
  - 关系
  - 我的
- 二级页面：
  - 推荐来信
  - 候选人详情
  - 聊天
  - 认证
  - 资料编辑
  - 资料采集视图
  - 设置
  - 运营工作台

### 6.2 BFF 代理

前端并不直连后端：

- 浏览器 -> Next.js `/api/gateway/[...path]`
- Next.js -> Partner Gateway

好处：

- 隐藏真实网关地址
- 复用 Cookie 登录态
- 可在前端层统一处理 mock fallback 和上游不可用提示

## 7. 后端服务拆分

### 7.1 子系统清单

- `gateway`：统一接入层
- `recommendation_system`：推荐与站内投递
- `matchmaking_system`：牵线池、pair、case
- `chat_system`：聊天、助手、风控、认证、媒体
- `discovery_system`：发现页 AI 红娘会话
- `partner_search`：底层搜索引擎
- `profile_service`：资料读写统一接口
- `persona_memory_sync`：画像沉淀与同步
- `relationship_ledger`：跨域关系账本
- `assessment`：测评引擎
- `task_scheduler`：任务调度

### 7.2 共享域能力

`match_domain/` 承担了很多跨子系统的共享语义：

- case / relation / event 模型
- rule config
- outbox
- gate runner
- criteria compiler
- reciprocal preferences
- trust summary
- verification triage

这说明项目在做“多服务拆分”的同时，保留了统一的领域语言中心。

## 8. 数据库与迁移结构

### 8.1 迁移目标

已独立维护迁移的子系统有：

- `persona`
- `recommendation`
- `matchmaking`
- `chat`
- `discovery`
- `relationship_ledger`

### 8.2 迁移演进信号

从迁移命名可看到系统持续演进的重点：

- outbox retry / claim
- async_jobs
- auth tables
- tool_call_audit
- view_snapshots
- profile_update_requests
- criteria_snapshots
- gate mirror fields
- rule_config tables
- experiment bucket members

这反映出系统已从纯业务功能建设阶段进入“可观测、可治理、可追溯”的中后期工程阶段。

## 9. 异步任务、调度与可观测性

### 9.1 调度任务

调度器当前覆盖：

- recommendation async worker
- recommendation outbox worker
- recommendation refresh saved searches
- recommendation deliver cards
- proxy intro dispatch
- proxy intro timeout close
- matchmaking async worker
- matchmaking outbox worker
- matchmaking refresh pool
- matchmaking build pairs
- matchmaking open cases
- matchmaking close stale cases
- chat async worker
- chat maintenance
- chat outbox worker

### 9.2 可观测性

系统已有：

- async job backlog gauge
- queue depth gauge
- refresh failure alert
- past-deadline proxy case alert
- pool refresh gauge
- DB unreachable alert

说明系统具备基本生产运维意识。

## 10. 当前成熟度评估

### 10.1 总体判断

当前项目处于“高级原型到早期产品化平台”之间，后端成熟度明显高于前端。

### 10.2 成熟度依据

- 服务边界清晰，数据库按域拆分
- Gateway surface、角色权限、JSON-RPC/REST 分层明确
- 有迁移体系，而不是手工建表
- 有 scheduler、outbox、async job、health signal
- 有规则配置、实验分桶、决策 trace
- 有较完整的风控和认证体系
- 仓库可见测试用例约 49 个，覆盖主域能力

### 10.3 当前短板

- 前端仍偏单应用状态机式组织，页面复杂度较高
- Discovery、测评、价值观模块耦合在单页体验中，后续维护成本会升高
- 多子系统均使用 Python 直连 MySQL，读写边界虽清楚，但统一事件契约仍可继续强化
- 关系页、聊天页、候选人详情页仍存在较多前端聚合逻辑
- 运营工作台已具雏形，但还不是完整的后台产品

## 11. 未来 3-6 个月产品迭代建议

## 11.1 产品方向建议

### 方向一：把 Discovery 做成真正的“AI 红娘工作流”

建议补齐：

- 偏好澄清模板库
- 候选人理由可解释面板
- 不满意反馈闭环
- 自动生成下一轮搜索策略
- 从“给我换一批”到“为什么这批不合适”的学习闭环

建议把“换一批”定义为一个明确的反馈入口，而不是纯刷新动作。用户只说“换一批”时，系统应默认触发一次轻追问，顺手收集对上一批候选人的不满意原因，再据此调整下一轮搜索策略。目标不是增加交互负担，而是建立低成本、可持续的偏好学习闭环。

建议采用如下交互原则：

- 先答应“可以换”，不要让用户感觉被拦住
- 再顺手追问“这批主要哪里不对”，而不是抛开放式大题
- 追问必须非强制，用户不回答也要能继续换
- 优先提供 4-6 个口语化选项，降低表达成本
- 反馈结果直接沉淀到 working criteria / prefer / avoid 信号，驱动下一轮检索与排序

首版建议文案与选项：

- 文案示例：“可以，我先帮你换一批。顺便问一句，这批主要哪里不对？你点一下，我下轮会更准。”
- 选项示例：没感觉、太像工作搭子、太忙太卷、不够有生活感、太远了、条件不太合适

建议同步建立“反馈到搜索”的策略映射：

- “太远了” => 收紧城市范围或提高同城权重
- “太忙太卷” => 降低高强度职业、超长工时、强事业导向标签的权重
- “不够有生活感” => 提高兴趣爱好、休闲表达、生活方式相关画像信号权重
- “没感觉” => 强化人格特征、互动气质、价值观匹配解释，而不只看硬条件
- “条件不太合适” => 回退到条件澄清，确认是年龄、学历、收入还是婚恋目标问题

### 方向二：强化“关系经营”而非只做撮合

建议补齐：

- 关系阶段自动推进建议
- 聊天冷启动建议
- 破冰/跟进/见面后复盘模板
- 会面前后关键节点提醒
- 红娘侧 case SLA 和跟进面板

其中最关键的是“关系阶段自动推进建议”。系统不应只停留在“帮用户认识人”，而应持续判断一段关系当前处于什么阶段、卡在什么地方、下一步最值得做什么，再给出对应建议。否则聊天建议、提醒、红娘介入都会变成泛化模板，难以真正推动关系前进。

首版可采用的关系阶段模型：

- 刚认识：已匹配或刚加上联系方式，互动浅，重点是破冰与建立初始好感
- 初步熟悉：已聊过几轮，双方有回应，重点是从闲聊转向更具体的话题和关系判断
- 准备见面：双方已有一定兴趣，重点是降低约见摩擦，确认时间、地点、节奏
- 见面后观察期：已经见过面，重点是会后跟进、态度表达、是否继续推进
- 稳定推进期：互动已形成习惯，重点是监测节奏、识别停滞、提示下一步升级动作

每个阶段都应绑定不同的系统能力：

- 刚认识 => 聊天冷启动建议、破冰话术、共同话题引导
- 初步熟悉 => 跟进建议、兴趣判断信号、是否适合转语音/见面的提示
- 准备见面 => 会面前提醒、轻量约会模板、确认细节清单
- 见面后观察期 => 复盘模板、见面后跟进提醒、继续/婉拒的表达建议
- 稳定推进期 => 关系节奏提醒、单边投入预警、红娘介入判断

关系阶段判断建议综合使用以下信号：

- 匹配后经过的时间
- 双方消息往返频率、连续性与中断时长
- 是否完成关键动作，如交换微信、语音、约见、见面后回访
- 用户显式反馈，如“聊得还行”“没感觉”“准备见面”
- 红娘人工标注与 case 备注

产品呈现上，建议系统始终回答三个问题：

- 你们现在到哪一步了
- 当前主要卡点是什么
- 下一步最值得做什么

红娘侧则需要配套 case SLA 与跟进面板，用于识别长时间无进展、关键节点未跟进、需要人工介入的关系 case，避免平台能力只停留在“撮合成功”而没有真正管理“关系推进成功”。

### 方向三：把信任与认证能力前置为增长卖点

建议补齐：

- 认证等级体系对推荐曝光和聊天权限的影响
- 用户可感知的“可信度说明”
- 照片/视频审核状态前台化
- 举报、申诉、处理结果透明化

### 方向四：打造运营中台

建议补齐：

- 推荐策略看板
- 转化漏斗看板
- rule config 可视化编辑器
- bucket/实验对照报表
- risk case 工作台

## 11.2 技术优化建议

### 建议一：收敛事件契约

当前多个子系统已通过 ledger 和 outbox 联动，下一步建议统一：

- canonical event schema
- event versioning
- 幂等键规范
- 子系统事件消费契约

目标是降低跨域状态偏差和补偿复杂度。

### 建议二：前端做领域拆分

建议把前端从当前页面聚合式结构继续拆成：

- auth domain
- discovery domain
- relationships domain
- profile domain
- trust/verification domain
- ops domain

并为每个域建立更稳定的 query hook、view model 和 action 层。

### 建议三：增强读模型

当前很多页面需要聚合多个接口，建议逐步建设专用读模型：

- 发现页聚合读模型
- 关系页聚合读模型
- 我的页聚合读模型
- 运营总览聚合读模型

这样能显著降低前端拼装复杂度和请求次数。

### 建议四：完善测试金字塔

建议未来增加：

- Gateway route contract tests
- 子系统事件一致性测试
- 关键 case 生命周期端到端测试
- Discovery session 回归测试
- 认证风控误杀/漏杀回归集

### 建议五：统一配置治理

当前 `.env.example` 已较完整，但环境变量数量很多。建议：

- 按子系统生成配置清单
- 引入启动时配置校验
- 区分 dev / staging / production 配置模板
- 对高风险开关增加默认保护

### 建议六：逐步提升运维可视化

建议增加：

- async job dashboard 前端化
- outbox backlog 面板
- trace 查询入口
- 关系账本修复工具
- 手动重放和补偿工具

## 12. 结论

Her 当前已经不是单点婚恋功能，而是一套围绕“发现对象、理解对象、建立关系、验证真实性、持续推进转化”的关系运营系统。

从代码实现看，项目最强的部分在后端领域建模，尤其是：

- Discovery 会话式发现
- Recommendation + Matchmaking 双引擎
- Relationship Ledger 统一关系账本
- Verification / Risk 安全体系
- Rule Config / Experiment / Ops 平台能力

未来 3-6 个月最值得投入的方向，不是继续横向堆新功能，而是把现有能力做成更闭环的三条主线：

1. AI 红娘发现闭环
2. 关系经营闭环
3. 运营优化闭环

如果这三条线打通，系统会从“功能很多的婚恋平台”升级为“可持续优化的婚恋关系操作系统”。
