# 撮合关系总账与服务化改造方案

## 1. 文档目的

这份文档用于明确下一阶段改造的唯一目标、领域边界、数据真源、状态机、事件规范、服务接口和迁移顺序。

本次文档先行，测试先行，随后才开始实现落地。

## 2. 先说结论

当前系统最大的问题，不是「用了多种存储」本身（资料与业务状态本就可分库），而是：

- 同一段关系状态分散在多个模块
- 推荐、代理转介绍、双边撮合各有一套状态表达
- 核心能力以 Python import 方式耦合，不适合作为稳定服务边界

后续改造的核心原则只有一句话：

`所有模块只认一份关系总账，所有状态变化先记事件，再由事件投影出当前状态。`

## 3. 当前问题

### 3.1 状态真源分裂

目前存在三类状态真源（引擎均为 MySQL，但 **schema / 库彼此独立**，尚未统一成一份关系总账）：

- MySQL（资料域）：用户核心资料、画像、公开视图
- MySQL（推荐状态库，如 `her_recommendation`）：持续搜索、推荐、卡片、用户动作、代理转介绍 case
- MySQL（撮合状态库，如 `her_matchmaking`）：pool、edge、pair、case、反馈回流

这会导致：

- 推荐模块认为某候选人已经 `skip + cooling`
- 撮合模块仍可能认为双方 `eligible`
- 代理转介绍模块可能已经有活动 case

结果是：

- 同一对人，在不同模块里出现不一致状态
- 前端展示和运营判断都可能互相冲突

### 3.2 状态词汇不统一

现有状态分散在多处：

- 推荐侧：`pending_delivery`、`cooled_down`、`saved_by_user`、`escalated_to_case`
- 代理转介绍侧：`pending_outreach`、`awaiting_reply`、`accepted`、`declined`、`timed_out`
- 撮合侧：`eligible`、`blocked`、`cooling`、`case_opened`、`mutual_accept`、`needs_revalidation`

这些状态都在描述“关系推进”，但没有统一词表。

### 3.3 服务边界是假边界

现在虽然已经有 importable Python API，但本质还是进程内耦合：

- 推荐系统直接调用 `search_profiles()`
- 撮合系统直接调用 `search_profiles()`
- 撮合系统直接调用 `upsert_persona_memory()`

这适合同仓、单进程、脚本编排，不适合前端直接接入，也不适合真正服务化。

## 4. 改造目标

### 4.1 业务目标

- 所有模块对同一对人的状态认知一致
- “收藏 / 跳过 / 冷却中 / 转介绍中 / 撮合中”在全系统可追踪
- 用户反馈触发画像更新后，相关关系自动重评估
- 前端只面向稳定 API，不理解底层脚本和多库细节

### 4.2 技术目标

- MySQL 继续作为唯一持久化引擎；**统一关系总账与事件流水**也落在 MySQL（与现有资料库、推荐库、撮合库逐步收敛或双写迁移）
- 推荐 / 撮合的**现有业务表**退化为「过渡期写模型」，最终由总账 + 投影替代或直接对账合并
- 所有关系推进状态统一到事件驱动模型
- 搜索和画像更新能力提供正式服务接口
- 支持逐步迁移，不要求一次性重写

### 4.3 非目标

- 本阶段不重写 `partner-search` 评分逻辑
- 本阶段不重写 `persona-memory-sync` 的字段合并规则
- 本阶段不先引入 Kafka、Pulsar 等重型消息中间件
- 本阶段不先拆成很多微服务

## 5. 核心原则

### 5.1 一本总账，多种视图

后续系统采用：

- 一份关系总账
- 一份事件流水
- 多个读侧投影

也就是说：

- 真相只存一份
- 推荐中心、转介绍中心、撮合中心、前端列表，都是不同视图

### 5.2 事件优先

所有状态变化都先写事件，再由事件投影出当前状态。

不允许每个模块自己直接偷偷改出一套状态。

### 5.3 写模型和读模型分离

- 写：统一命令入口，写事件和聚合状态
- 读：为前端和运营提供不同查询视图

## 6. 领域模型

### 6.1 `ProfileRef`

统一表示一个用户或候选人在资料源中的身份。

字段建议：

- `source`
- `profile_id`
- `user_key`

用途：

- 统一推荐系统里的 `candidate_id`
- 统一撮合系统里的 `self_id`
- 为未来跨源检索保留空间

### 6.2 `Relation`

这是最核心的新聚合。

定义：

`一个 owner 对一个 target 的单边关系总账`

例如：

`小王 -> 小李`

`Relation` 承担：

- 是否发现过
- 是否推荐过
- 是否收藏过
- 是否跳过过
- 是否处于冷却
- 是否请求过代理转介绍
- 当前是否存在活动 case

这一步是必须的，因为很多业务状态发生在 `Pair` 和 `MatchCase` 之前。

### 6.3 `Pair`

定义：

`两条互为反向的 Relation 汇总出的双边关系`

例如：

- `小王 -> 小李`
- `小李 -> 小王`

如果满足双边条件，才会形成 `Pair`。

`Pair` 承担：

- 双边是否都合格
- 是否低于阈值
- 是否被某一侧阻断
- 是否处于 cooling
- 是否已经进入 case
- 是否需要重评估

### 6.4 `MatchCase`

定义：

`关系推进过程中的正式工单`

它统一承载两类流程：

- 代理转介绍 case
- 双边撮合 case

以后不要再保留“推荐侧一套 case、撮合侧一套 case”的双定义。

### 6.5 `PersonaUpdate`

画像更新不是关系状态本身，但它是重要上游事件源。

画像更新发生后：

- 写 persona 事件
- 找到相关 `Relation` / `Pair`
- 触发重评估

## 7. 统一状态机

### 7.1 Relation 状态

建议统一成下面几类主状态：

- `new`
- `recommended`
- `saved`
- `skipped`
- `cooling`
- `direct_greet_started`
- `request_proxy_intro`
- `proxy_intro_active`
- `closed`

附加字段：

- `cooldown_reason`
- `cooldown_until`
- `last_action_type`
- `active_case_id`

注意：

- `skip` 是动作
- `cooling` 是状态

不要把“动作名”和“状态名”混成一套枚举。

### 7.2 Pair 状态

建议统一为：

- `eligible`
- `below_threshold`
- `blocked`
- `cooling`
- `case_opened`
- `mutual_accept`
- `needs_revalidation`
- `stale`

### 7.3 MatchCase 状态

统一代理转介绍和撮合流程后，建议状态如下：

- `pending_contact`
- `awaiting_reply`
- `accepted`
- `declined`
- `timed_out`
- `closed`

通过字段区分不同流程：

- `case_type = proxy_intro`
- `case_type = matchmaking`

## 8. 事件流模型

### 8.1 事件总原则

所有业务动作都写入统一事件表。

每条事件都必须包含：

- `event_id`
- `event_type`
- `aggregate_type`
- `aggregate_id`
- `actor_type`
- `actor_id`
- `source_service`
- `correlation_id`
- `idempotency_key`
- `occurred_at`
- `payload_json`
- `version`

### 8.2 核心事件类型

#### Relation 事件

- `relation_discovered`
- `relation_recommended`
- `relation_saved`
- `relation_skipped`
- `relation_cooling_started`
- `relation_cooling_expired`
- `relation_direct_greet_started`
- `request_proxy_intro`
- `relation_proxy_intro_closed`

#### Pair 事件

- `pair_built`
- `pair_blocked`
- `pair_cooling_started`
- `pair_case_opened`
- `pair_mutual_accept`
- `pair_needs_revalidation`
- `pair_staled`

#### Case 事件

- `case_created`
- `case_contact_sent`
- `case_reply_accepted`
- `case_reply_declined`
- `case_timed_out`
- `case_closed`

#### Persona 事件

- `persona_patch_applied`
- `persona_profile_synced`
- `persona_feedback_recorded`

### 8.3 事件存储建议

第一阶段不要上消息队列，先用 MySQL 内表：

- `event_log`
- `outbox_events`

好处：

- 易于事务一致性
- 易于回放
- 易于调试
- 适合当前规模

## 9. 数据库改造方案

### 9.1 MySQL 作为唯一真源

新增表建议：

- `match_relations`
- `match_relation_events`
- `match_pairs`
- `match_pair_events`
- `match_cases`
- `match_case_events`
- `outbox_events`

### 9.2 与当前推荐 / 撮合 MySQL 库的关系

仓库现状：**推荐系统、撮合系统的业务状态已写入各自独立的 MySQL 库**（DSN 可配，分别见 `external-systems/partner-recommendation-system/README.md` 与 `external-systems/partner-matchmaking-system/README.md`）。这与本节规划的「统一 `match_relations` / `event_log` 总账」仍是两回事：前者是**分域业务表**，后者是**待建设的一账本多投影**。

过渡策略建议：

- Phase 2～4 新建总账/事件表后，与现有 `her_recommendation`、`her_matchmaking` 中表 **双写或对账迁移**，直到读侧完全切到统一投影。
- **SQLite** 不再作为运行态选项；若需极简本地 fixture，可用一次性 SQL 脚本或测试专用 MySQL 库（与生产 schema 对齐），不再维护双套存储语义。

### 9.3 主键建议

- `relation_id = hash(owner_profile_ref, target_profile_ref, relation_type)`
- `pair_key = stable_sort(profile_a, profile_b)`
- `case_id = 业务可读 UUID`

## 10. 服务边界

### 10.1 搜索服务

将 `search_profiles()` 封装为正式服务接口。

建议 REST：

- `POST /api/searches`

输入：

- `source`
- `criteria`
- `self_profile` 或 `self_id`
- `limit`

输出：

- `results`
- `matched_on`
- `risk_flags`
- `follow_up_questions`

### 10.2 画像服务

不要直接把底层 `apply_persona_patch()` 暴露给前端。

正式接口应该包在更稳定的命令层：

- `POST /api/persona-patches`
- `POST /api/persona-sync`
- `POST /api/public-profiles/render`

### 10.3 关系写接口

统一所有“按钮动作”和“流程推进”入口：

- `POST /api/relations/{relation_id}/save`
- `POST /api/relations/{relation_id}/skip`
- `POST /api/relations/{relation_id}/request-proxy-intro`
- `POST /api/cases/{case_id}/reply`
- `POST /api/pairs/{pair_key}/revalidate`

### 10.4 读接口

前端只读投影接口，不读底层真源表：

- `GET /api/recommendations`
- `GET /api/relations`
- `GET /api/pairs`
- `GET /api/cases`
- `GET /api/timeline/{aggregate_id}`

## 11. Agent / Skill / Python API / 服务 API 的关系

这四层不冲突，职责如下：

- `skill`：给 agent 的能力包装
- `Python API`：单进程内部复用接口
- `服务 API`：跨进程、跨服务、给前端和独立 worker 使用的正式边界

迁移目标不是删除 skill，而是：

- 外部系统和前端走服务 API
- skill 可以继续保留
- skill 底层未来可从“本地 import”切到“远程 API”

## 12. 落地顺序

### Phase 0：方案与测试先行

- 写清文档
- 先补全测试
- 不急着动实现

### Phase 1：状态词汇冻结

- 统一所有状态枚举
- 统一 `cooldown_reason` / `cooldown_until`
- 明确各状态转移约束

### Phase 2：MySQL 增加关系总账和事件表

- 新建聚合表
- 新建事件表
- 新建 outbox 表

### Phase 3：旧系统开始双写事件

- 推荐系统写现有 MySQL 业务表，同时写统一事件（总账 / `event_log`）
- 撮合系统写现有 MySQL 业务表，同时写统一事件
- 先不切读流量

### Phase 4：建立读投影

- 推荐中心投影
- 转介绍中心投影
- 撮合中心投影
- 时间线投影

### Phase 5：切换读真源

- 前端只读统一投影
- 运营只看统一 timeline
- 各子系统原有 MySQL 业务表仅作过渡写模型或降级只读，直至完全由总账投影替代

### Phase 6：切换写入口

- 上层业务不再直接 import 其他模块
- 改为调用正式服务 API

## 13. 测试策略

### 13.1 测试先行原则

在实现统一总账前，先补齐完整测试，目标是：

- 固定现有业务语义
- 防止重构破坏关键行为
- 为未来统一状态机提供验收标准

### 13.2 必补场景

#### 推荐相关

- 推荐发现候选人
- 用户跳过后进入冷却
- 冷却未过期不得重复投放
- 冷却到期后可再次进入推荐
- 用户保存后不应进入负向冷却

#### 代理转介绍相关

- 请求代理转介绍后创建活动 case
- 接受、拒绝、超时分别如何回写关系状态
- 拒绝和超时进入冷却
- 活动 case 未结束前不得重复创建

#### 撮合相关

- 双边 edge 汇总生成 pair
- 一侧拒绝后 pair 进入 cooling
- cooling 未过期前不得再次开 case
- 反馈回流后 pair 进入 needs_revalidation

#### 画像回流相关

- 反馈写 persona 后应触发相关关系重评估
- 重评估期间活动 case 应被关闭或冻结

### 13.3 测试分层

- 单元测试：状态转移、事件生成、命令校验
- 集成测试：推荐、转介绍、撮合、反馈的跨模块联动
- 迁移测试：旧数据回填到新总账后状态是否等价

## 14. 风险与控制

### 14.1 最大风险

- 旧系统和新总账双写期间出现不一致

控制方式：

- 所有写操作带 `idempotency_key`
- 每次重要动作生成 timeline
- 做旧表和新表状态对账脚本

### 14.2 第二风险

- 只包 HTTP 接口，但仍保留多真源状态

控制方式：

- 必须先统一总账，再推进服务化读写切换

### 14.3 第三风险

- 过早上复杂消息中间件，放大排障成本

控制方式：

- 第一阶段只用 MySQL event log + outbox

## 15. 验收标准

当下面条件全部成立时，认为改造成功：

- 任意一对人，所有模块看到的状态一致
- “跳过 / 冷却中 / 转介绍中 / 撮合中”都可从统一 timeline 回放
- 用户反馈引起的画像变化能触发自动重评估
- 前端不再依赖本地脚本或「分库零散业务表」作为最终真源（以统一 timeline / 总账投影为准）
- 推荐和撮合不再通过 `sys.path + import` 强耦合调用

## 16. 本轮工作边界

本轮只做两件事：

- 把完整方案写入文档
- 先补全测试用例

后续实现严格按照：

`文档 -> 测试 -> 实现`

的顺序推进。
