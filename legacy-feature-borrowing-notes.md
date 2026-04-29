# 旧项目可借鉴功能整理

日期：2026-04-29

## 1. 先说结论

当前仓库已经具备两块很扎实的底座能力：

- `local-skills/partner-search/scripts/search_candidates.py`
  已经能做结构化筛选、双向条件校验、`fit/confidence/risk` 三段式打分、缺失字段提示、风险标记、敏感备注脱敏。
- `local-skills/persona-memory-sync/scripts/persona_memory_lib.py`
  已经把 `user_personas`、`user_persona_observations`、`profiles`、`public_*` 的边界拆清楚，能区分 `explicit / strong_inference / weak_inference`，也有 `matcher_*` 内部特征与公开渲染分层。

所以当前项目最缺的，不是“再做一个筛人脚本”，而是以下四类闭环能力：

1. 从“给某个人筛候选人”升级到“判断两个人到底配不配”的双人评估层
2. 从“用户来搜”升级到“系统主动发现 pair 并顺序征询”的主动撮合层
3. 从“资料完整度”升级到“可信度 / 核验度 / 风险度”的质量层
4. 从“筛完就结束”升级到“破冰、推进、提醒、约会、安全”的转化层

我的判断是：旧项目里最值得借的，不是整套前后端，而是它的 **评估模型、状态机、画像治理方法、转化闭环设计**。

## 2. 当前仓库已有能力边界

### 2.1 已有能力

- 候选人筛选与排序
  参考：`local-skills/partner-search/SKILL.md`、`local-skills/partner-search/scripts/search_candidates.py`
- 公开资料与内部匹配资料分层
  参考：`persona-memory-sync-plan.md`、`local-skills/persona-memory-sync/references/visibility-policy.md`
- Persona 长期记忆、证据审计、画像回写
  参考：`local-skills/persona-memory-sync/scripts/upsert_persona_memory.py`
- 内部匹配标签与公开安全文案转换
  参考：`local-skills/persona-memory-sync/references/public-rendering.md`
- 结构化画像补齐
  参考：`local-skills/partner-search/scripts/backfill_profile_enrichment.py`

### 2.2 当前明显缺口

- 没有统一的 “pair verdict / hard blockers / first contact side” 双人评估结果
- 没有主动撮合的状态机和征询记录
- 没有资料可信度、认证层级、信任徽章
- 没有从推荐到聊天再到约会的转化闭环
- 没有用户侧“为什么推荐 / 需要注意什么 / 下一步怎么推进”的完整交互承接

## 3. 最值得借的功能

## 3.1 P0：统一双人评估引擎

### 为什么值得借

当前 `partner-search` 更像是“按用户要求筛候选池”，但还没有一个真正独立的“双人评估裁判”。旧项目把这层拆得比较清楚：

- 候选召回是一层
- 双人评估是一层
- 是否推进又是另一层

这套拆法很适合当前仓库继续长大。

### 借过来后能解决什么

- 让当前的 `score / fit_score / confidence_score / risk_score` 再往上长一层 `pair_verdict`
- 输出更像红娘判断的结果：
  - 是否建议推进
  - 主要匹配原因
  - 主要硬冲突
  - 先联系谁更合适
- 为后续主动撮合、提醒、预沟通提供统一真相源

### 建议借法

- 保留当前 `partner-search` 作为第一层召回
- 新增第二层 `pair_evaluator`
- 第二层专门输出：
  - `verdict`
  - `hard_blockers`
  - `why_match`
  - `why_not_match`
  - `first_contact_side`

### 旧项目参考

- `../ai_incubation_platform/Her/docs/AI_MATCHMAKER_TRIGGER_AND_JUDGMENT_DESIGN.md`
- `../ai_incubation_platform/Her/docs/CURRENT_MATCHING_MAIN_FLOW.md`
- `../ai_incubation_platform/Her/src/services/shared_matchmaking_service.py`
- `../ai_incubation_platform/Her/deerflow/backend/packages/harness/deerflow/community/her_tools/shared_matchmaking_engine.py`

## 3.2 P0：主动红娘撮合状态机

### 为什么值得借

当前仓库已经有画像和筛人，但还是“等用户来搜”。旧项目最有产品差异化的一点，是把 AI 红娘做成：

- 先发现潜在 pair
- 只先问一侧
- 一侧同意后再问另一侧
- 任一方明确拒绝后永久不再推

这比简单地“推荐列表 + 用户自己点”更像真正的红娘工作流。

### 借过来后能解决什么

- 从“用户驱动搜索”升级到“系统驱动撮合”
- 把当前 Persona 和记忆能力真正用在长期撮合上
- 形成可追踪的 pair 状态，而不是一次性排序结果

### 建议借法

- 先不要照搬整套服务层
- 先抽最小状态机：
  - `discovered`
  - `first_side_pending`
  - `first_side_rejected`
  - `second_side_pending`
  - `mutual_interest`
  - `closed`
- 配一张 pair 表 + 一张 outreach / response 记录表就够了

### 旧项目参考

- `../ai_incubation_platform/Her/docs/AI_MATCHMAKER_PRODUCT_PLAN.md`
- `../ai_incubation_platform/Her/src/api/ai_matchmaker.py`
- `../ai_incubation_platform/Her/src/services/ai_matchmaker_service.py`
- `../ai_incubation_platform/Her/src/db/models/matchmaker.py`

## 3.3 P0：资料可信度与认证体系

### 为什么值得借

当前仓库已经有 `confidence_score`，但它更偏“资料完整度 / 可判断度”，还不是“这个人靠不靠谱”。旧项目把可信度拆成：

- 身份验证
- 交叉验证
- 行为一致性
- 社交背书

这个思路很适合补到当前项目里。

### 借过来后能解决什么

- 推荐结果不只看“像不像”，还看“敢不敢推”
- 把 `verified_level` 从简单字段升级为真实的质量信号
- 给搜索结果和排序一个更强的风控维度

### 建议借法

- 先做轻量版，不必一次做完所有认证
- 第一阶段先补：
  - `profile_confidence`
  - `confidence_level`
  - `verification_recommendations`
  - `public trust summary`
- 排序里把“匹配度”和“可信度”明确拆开

### 旧项目参考

- `../ai_incubation_platform/Her/docs/PROFILE_CONFIDENCE_ARCHITECTURE.md`
- `../ai_incubation_platform/Her/src/api/profile_confidence.py`
- `../ai_incubation_platform/Her/src/api/identity_verification.py`
- `../ai_incubation_platform/Her/src/api/verification_badges.py`
- `../ai_incubation_platform/Her/src/agent/skills/trust_analyzer_skill.py`

## 3.4 P0-P1：对话式深度校准入口

### 为什么值得借

当前仓库已经能存 Persona，但更像后台能力，还缺一个“怎么自然把这些信息问出来”的用户入口。旧项目在这块的经验很值得借：

- 不做大问卷
- 先 3 个低敏关键问题
- 先让用户看到“为什么要问”
- 先证明价值，再逐步加深

### 借过来后能解决什么

- 提升 Persona 输入质量
- 减少用户防御感
- 让 `partner-search` 更早拿到有用约束

### 建议借法

- 如果后面要做聊天入口，先借它的问法，不要先借完整 UI
- 最小版本只要：
  - 城市
  - 关系目标
  - 最想避开什么人
- 有了这 3 个信号就能先跑首轮筛选

### 旧项目参考

- `../ai_incubation_platform/Her/docs/HOMEPAGE_CONVERSATIONAL_DEEP_MATCH_PRD.md`
- `../ai_incubation_platform/Her/docs/FIRST_VISIT_EXPERIENCE_REDESIGN_PRD.md`
- `../ai_incubation_platform/Her/docs/LIGHT_REGISTRATION_MINIMAL_CALIBRATION_PRD.md`
- `../ai_incubation_platform/Her/docs/CURRENT_PROFILE_MAIN_FLOW.md`

## 3.5 P1：推荐后的互动闭环

### 为什么值得借

当前项目做到“筛出来谁更合适”已经不错，但还没有“用户怎么表达兴趣、怎么进入关系、怎么减少消息石沉大海”的后续机制。旧项目这部分做得比较完整：

- `swipe`
- `who likes me`
- `your turn`
- 关系时间线

### 借过来后能解决什么

- 从“推荐工具”变成“撮合产品”
- 能记录用户真实反馈，而不是只有搜索条件
- 为 Persona 和记忆更新提供更强的行为信号

### 建议借法

- 第一阶段不用照搬交互形式
- 先抽出最小动作集合：
  - `interested`
  - `pass`
  - `not now`
  - `reply pending`
- 再补一个待回复提醒机制

### 旧项目参考

- `../ai_incubation_platform/Her/src/api/swipe.py`
- `../ai_incubation_platform/Her/src/api/who_likes_me.py`
- `../ai_incubation_platform/Her/src/api/your_turn.py`
- `../ai_incubation_platform/Her/src/api/relationship.py`

## 3.6 P1：AI 预沟通与破冰辅助

### 为什么值得借

旧项目不是停在“给你一张卡”，而是继续处理匹配后的冷启动问题。这对当前项目很有价值，因为很多匹配死在“第一句话”和“聊不下去”。

### 借过来后能解决什么

- 减少高质量匹配因为不会开口而流失
- 给当前系统补一个“从找到人到聊起来”的中间层

### 建议借法

- 不建议直接上“AI 替身先聊 50 句”的重版本
- 更适合先借轻量版：
  - 首句建议
  - 共同点破冰
  - 冷场提醒
  - 下一句建议

### 旧项目参考

- `../ai_incubation_platform/Her/src/agent/skills/precommunication_skill.py`
- `../ai_incubation_platform/Her/src/agent/skills/silence_breaker_skill.py`
- `../ai_incubation_platform/Her/src/agent/tools/icebreaker_tool.py`
- `../ai_incubation_platform/Her/src/agent/tools/followup_tool.py`

## 3.7 P1-P2：关系推进、约会策划、活动推荐

### 为什么值得借

如果当前项目未来目标不是“帮你找名单”，而是“帮你找到并推进关系”，那约会与推进能力迟早要补。旧项目在这块的结构是成体系的。

### 借过来后能解决什么

- 把匹配结果延伸到第一次见面
- 提供更真实的“撮合成功率”提升抓手

### 建议借法

- 先做静态建议版，不要先做复杂实时编排
- 可先补：
  - 约会地点推荐
  - 首次见面方案
  - 不同关系阶段的建议动作

### 旧项目参考

- `../ai_incubation_platform/Her/src/api/activities.py`
- `../ai_incubation_platform/Her/src/agent/skills/activity_director_skill.py`
- `../ai_incubation_platform/Her/src/agent/skills/date_planning_skill.py`
- `../ai_incubation_platform/Her/src/agent/skills/video_date_coach_skill.py`

## 3.8 P1-P2：安全守护与信任前置

### 为什么值得借

婚恋产品和一般推荐产品不一样，安全不是锦上添花，而是信任基础。旧项目在安全与信任方面的思路值得借，但不适合一开始全部照搬。

### 借过来后能解决什么

- 提升用户愿意相信推荐结果的意愿
- 给线下见面场景提供更明确的安全承诺

### 建议借法

- 先借“信任前置”和“安全提醒”
- 暂时不要先上重型实时监测
- 第一阶段适合做：
  - 公开可信度摘要
  - 见面前安全 checklist
  - 风险用户降权或限流

### 旧项目参考

- `../ai_incubation_platform/Her/src/agent/skills/safety_guardian_skill.py`
- `../ai_incubation_platform/Her/src/agent/skills/trust_analyzer_skill.py`
- `../ai_incubation_platform/Her/src/api/identity_verification.py`
- `../ai_incubation_platform/Her/src/api/profile_confidence.py`

## 4. 暂不建议直接照搬的部分

以下内容旧项目里有，但不建议当前仓库现阶段直接搬：

- 整套 DeerFlow 运行时和全量前后端
  当前仓库更适合先保持“技能 / 脚本 / 数据模型”路线，别一下变成重平台。
- 会员付费闭环
  现在太早，先把匹配质量和闭环打通更重要。
- 企业风控/绩效看板类能力
  `risk_control_skill.py` 更偏平台运营，不是当前仓库的核心产品价值。
- 过重的 AI 替身全自动流程
  例如预沟通 50 句这类重能力，适合在真实撮合闭环稳定后再上。

## 5. 推荐迁移顺序

## Phase 1：先补判断层和状态层

- 双人评估引擎
- 主动撮合 pair 状态机
- 轻量可信度/认证摘要

这个阶段做完，当前项目会从“高级筛人器”升级成“可推进的红娘引擎”。

## Phase 2：再补用户入口和反馈闭环

- 对话式 3 问首轮校准
- 推荐后的 `interested / pass / not now`
- 待回复提醒
- Persona 回写和行为反馈联动

这个阶段做完，系统会开始形成真实用户反馈闭环。

## Phase 3：最后补关系推进和安全能力

- 破冰建议
- 约会策划
- 活动推荐
- 安全提醒

这个阶段做完，产品才真正从“找人”走到“成局”。

## 6. 一句话判断

如果只选 3 个最值得马上借的点，我建议是：

1. 统一双人评估引擎
2. 主动撮合状态机
3. 可信度 / 认证摘要

因为这 3 个点最能直接放大当前仓库已经很强的 `partner-search + persona-memory-sync` 底座，而且不会把仓库一下拖进过重的全栈改造里。
