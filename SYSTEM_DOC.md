# 系统文档

## 1. 项目定位

### Vision
本项目的目标不是单纯“搜人”，而是把婚恋场景里的显性条件、隐性偏好、敏感边界、长期记忆和人工介入串成一条可解释的撮合链路。

### 解决的核心痛点
- 资料分散，用户表达经常不完整，系统需要把口语化描述转成可执行条件。
- 单向匹配不够，真实关系还要校验“对方是否也能接受我”。
- 公开资料和内部记忆不能混写，敏感信息必须分层处理。
- 没有结果时不能直接放弃，需要有“继续留意”的空结果转化。
- 关系推进存在人工转介、收藏、跳过、冷却、超时等运营状态，必须可追踪。

### 当前成熟度判断
代码已经跑通核心闭环，但整体仍偏“脚本化 + MySQL/SQLite 混合 + JSON 状态驱动”。适合继续产品化，不适合直接视为完整服务化平台。

## 2. 架构总览

### 总体链路
`persona-memory-sync` -> `partner-search` -> `partner-recommendation-system` -> `proxy intro / in-app delivery` -> `matchmaking-system` -> `feedback -> persona-memory-sync`

### 分层说明
- 数据层以 MySQL 为主，承载 `profiles`、`user_personas`、`user_persona_observations` 和公开视图。
- 外围编排层使用 SQLite，分别记录 saved search、推荐、卡片、撮合 pair、case、反馈等状态。
- 检索层是纯 Python 评分/过滤引擎，既能 CLI 运行，也能被外部系统以 API 方式调用。
- 评测层独立存在，用于 persona 生成、抽取、审计和回归。

### 关键环境变量
- `PARTNER_SEARCH_MYSQL_SOURCE`
- `PERSONA_MEMORY_MYSQL_SOURCE`
- `OPENAI_MODEL`

### 主要数据表
- MySQL: `profiles`, `profile_photos`, `user_personas`, `user_persona_observations`, `public_profile_view`
- SQLite Phase 3/4: `saved_search_subscriptions`, `profile_recommendations`, `recommendation_actions`, `in_app_recommendation_cards`, `saved_search_runs`, `match_cases`, `match_case_events`, `match_case_outreach_attempts`
- SQLite Phase 5: `matchmaking_pool_members`, `matchmaking_edges`, `matchmaking_pairs`, `match_cases`, `match_case_events`, `matchmaking_feedback_events`

## 3. 核心模块

### 3.1 `partner-search`

核心文件：`local-skills/partner-search/scripts/search_candidates.py`

这个模块是整个系统的匹配底座，负责把 MySQL 资料源转成“可解释的候选人排序结果”。

已实现能力：
- MySQL DSN 解析、表自动识别、字段别名归一化。
- CLI 过滤条件构建，支持年龄、身高、城市、婚况、孩子、抽烟喝酒、活跃度、认证等级、照片数等条件。
- 自我画像上下文注入，支持 reciprocal matching。
- `must_have / must_not_have / prefer` 三层关键词策略。
- 候选人得分、置信度、风险分、匹配理由、补充问题、证据片段生成。
- 无结果时输出诊断、放宽建议和 fallback 候选。
- 结果多样性控制，避免同质化推荐。
- 输出 JSON / 文本两种格式，支持 source 红action。
- 照片预览回填。

核心交互逻辑：
- `search_profiles()` 是稳定 Python API，外部系统都走它。
- `evaluate_candidate()` 决定是否入选，并生成 score / risk / evidence。
- `evaluate_reciprocal_compatibility()` 会反向检查“对方是否接受我”的条件。
- `populate_no_match_details()` 负责空结果兜底。

### 3.2 `persona-memory-sync`

核心文件：`local-skills/persona-memory-sync/scripts/persona_memory_lib.py`

这个模块负责把聊天里提炼出的长期记忆写入 `user_personas`，再同步回 `profiles`，并生成公开安全版本。

已实现能力：
- `explicit / strong_inference / weak_inference` 三种写入来源。
- patch 归一化、合并、增量更新、观察日志落库。
- 软硬字段差异化处理，避免推断覆盖明确事实。
- 从语义中推断孩子、婚况、异地、城市偏好等细粒度意图。
- 生成 matcher 用的 JSON payload。
- 生成公开安全的 `public_*` 字段和 `public_profile_view`。
- 自动扩表、建表、维护公开视图。
- 基于 OpenAI 的 roleplay audit 与 review。

核心交互逻辑：
- `apply_persona_patch()` 同时写 persona、observation，必要时同步 profile。
- `sync_persona_profile()` 用 persona 回写内部 profile。
- `render_public_profile_result()` 负责预览或刷新公开资料。
- `build_profile_payload()` 是 persona -> profile 的主映射器。

### 3.3 `partner-recommendation-system`

核心文件：`external-systems/partner-recommendation-system/recommendation_system/service.py`

这个模块是 Phase 3/4 的外层运营系统，负责 saved search、推荐分发、用户动作、代理转介和空结果转化。

已实现能力：
- 创建 saved search subscription。
- 基于 persona profile + subscription overrides 编译有效检索条件。
- 定时刷新并写入 search run 和 recommendation 历史。
- `match_based` 与 `direct_greet_only` 两种推荐模式。
- 直聊门禁：follow-up、risk flags、缺失信息、分数阈值。
- in-app 卡片分发、quiet hours、daily cap、skip 冷却。
- 用户动作：save / skip / direct_greet。
- 空结果 opt-in：无匹配时引导用户继续订阅。
- proxy intro：代问、代开口、回复、超时、关闭。

核心交互逻辑：
- `refresh_subscription()` 拉起 partner-search，写入 `profile_recommendations`。
- `deliver_in_app_recommendations()` 把可发推荐变成卡片。
- `record_user_review()` 决定候选人是否值得直接打招呼。
- `create_match_case()` 把推荐提升为人工转介 case。
- `record_match_case_reply()` / `close_match_case()` / `close_timed_out_match_cases()` 维护转介状态机。

### 3.4 `partner-matchmaking-system`

核心文件：`external-systems/partner-matchmaking-system/matchmaking_system/service.py`

这个模块是 Phase 5 的双边撮合总控，更像“活跃会员池 + 双向边 + pair + case”的撮合引擎。

已实现能力：
- 维护 active pool member。
- 用 partner-search 计算单向 edge。
- 将双向 edge 合成为 pair。
- 基于 pair score、双方门槛、风险、活跃状态决定 pair 状态。
- 打开双向接触 case，走两段式确认。
- reply、decline、timeout、cooling、stale、revalidation。
- 用户反馈可自动触发 persona-memory 同步，并让相关 pair 重新评估。

核心交互逻辑：
- `refresh_pool_member()` 更新单向边。
- `build_mutual_pairs()` 汇总双向关系，生成 pair 状态。
- `open_match_cases()` 把 eligible pair 变成可接触 case。
- `record_case_reply()` 处理双方回复与冷却。
- `record_feedback()` 把反馈回流到 persona-memory，并触发 revalidation。

### 3.5 评测与审计工具

相关文件：
- `local-skills/persona-eval/*`
- `local-skills/persona-memory-sync/scripts/run_persona_memory_audit.py`
- `local-skills/partner-search/scripts/run_persona_regression.py`

这些工具负责：
- persona 对话回放与抽取评测。
- 搜索命令回归。
- 画像记忆准确率、隐私泄露、漂移分析。

## 4. 已实现功能清单

### 检索与匹配
- 支持多来源 MySQL 资料检索。
- 支持中文字段别名映射。
- 支持硬条件过滤与软偏好加分。
- 支持 reciprocal compatibility。
- 支持 no-match fallback 和诊断。
- 支持结果多样性与尾部低质裁剪。

### 画像与记忆
- 支持 explicit / inference / weak 三种记忆来源。
- 支持长期画像、偏好画像、公开画像三层内容。
- 支持敏感字段屏蔽与公开安全重写。
- 支持 profile 自动同步。

### 推荐运营
- 支持 saved search 订阅。
- 支持周期刷新、推荐历史、卡片分发。
- 支持收藏、跳过、直接打招呼、静默期。
- 支持空结果 opt-in 转化。

### 人工转介
- 支持 proxy intro case。
- 支持 outreach、reply、handoff、timeout、close。
- 支持状态追踪与事件日志。

### 双向撮合
- 支持活跃池、互相 edge、pair、case。
- 支持双向确认、冷却、重验证、反馈回流。

## 5. 主要业务流程

1. 用户对话或人工录入生成 persona patch，写入 `user_personas`，必要时同步到 `profiles`。
2. `partner-search` 读取 MySQL profile，计算候选人得分、风险与解释。
3. `partner-recommendation-system` 将搜索结果持久化为 recommendation，并在合适时发卡。
4. 用户可以收藏、跳过、直接打招呼，系统据此更新冷却和后续分发。
5. 如果需要代问，则创建 proxy intro case，进入两段式确认流程。
6. `matchmaking-system` 维护活跃池和双向 pair，持续推进两边都可接受的关系。
7. 用户反馈会反向触发 persona-memory 同步，并让相关 pair 重新评估。

## 6. 3-6 个月产品规划

### 0-3 个月
- 把“搜索、推荐、转介、撮合”统一成同一套状态枚举和事件规范。
- 给每个关键动作补齐可视化解释：为什么命中、为什么拒绝、为什么冷却。
- 做订阅中心和推荐中心的产品化界面，减少 CLI 依赖。
- 建立核心指标：命中率、转化率、主动打招呼率、代理转介成功率、冷却恢复率。

### 3-6 个月
- 引入更稳定的异步任务调度，替代脚本式轮询。
- 把推荐分数拆成可学习的特征层，逐步做排序校准。
- 建立 A/B 或 shadow 测试，验证规则改动对转化的影响。
- 增强隐私分层与字段级权限，避免公开文本泄露内部边界。
- 把 feedback -> persona-memory -> search -> pair 的闭环做成可回放事件流。

## 7. 技术优化建议

- 抽出统一的领域模型，减少 JSON blob 在多个系统间重复定义。
- 给 SQLite 状态机加迁移脚本和版本管理，降低 schema 漂移风险。
- 将 `partner-search` 的评分规则配置化，便于实验和调参。
- 对 `direct_greet`、`proxy_intro`、`pair` 状态机补充更严格的单元测试与回归集。
- 统一 MySQL / SQLite 的时区、时间戳和序列化格式。
- 增加 observability：每次搜索、推荐、发卡、转介都能定位输入输出。
- 为 persona audit 产出标准基准集，持续监控记忆漂移和隐私风险。

## 8. 结论

这个项目已经具备“长期画像 + 可解释搜索 + 主动推荐 + 人工转介 + 双边撮合 + 反馈回流”的完整闭环。下一阶段最值得做的不是再堆更多规则，而是把现有闭环产品化、指标化、可观测化。
