# 主动通知、系统撮合、代荐给对方的完整方案

## 1. 一句话定义

把当前的 `partner-search` 从“帮你搜人”升级成“会持续帮你盯人、帮你探口风、也能替你开口的中间人系统”。

这不是 3 个互相独立的功能，而是 1 套统一能力的 3 个入口：

- `持续关注`：现在没找到合适的人，先进入后台持续扫描，有结果再通知。
- `系统主动撮合`：系统发现 A 和 B 匹配度高，按授权规则主动去问双方意愿。
- `代我推荐给对方`：用户自己看上了某个人，但不好意思直接开口，让系统先去替他表达意向。

## 2. 设计目标

### 2.1 用户想得到的结果

- 没找到合适的人时，不是结束，而是“进入持续关注”。
- 找到合适的人时，不只是给名单，还能推动下一步。
- 用户不好意思主动时，系统可以充当缓冲层。
- 在没有双方同意前，不暴露敏感信息，不让人有被冒犯的感觉。

### 2.2 产品原则

- 同一套匹配引擎服务 3 个入口，避免逻辑分叉。
- 联系对方前必须有明确授权，或者双方都提前开了自动撮合授权。
- 未确认前只发脱敏信息，不直接暴露联系方式、工作单位、住址等。
- 避免重复打扰，同一对人必须做去重、冷却、频控。
- 先“问愿不愿意了解”，后“开放更多资料”，最后才“进入建联”。

## 3. 这 3 个功能怎么统一

可以把整个系统理解成 4 步：

1. `找`
   系统持续扫描资料库，判断谁和谁可能合适。
2. `提醒`
   如果当前没有合适对象，就记住你的条件，之后有结果主动通知。
3. `探`
   如果系统发现高匹配，或者用户自己点了“帮我去问”，就先去探对方口风。
4. `连`
   只有双方都愿意，才进入交换更多资料、开放聊天或人工牵线。

所以：

- 功能 1 负责 `找 + 提醒`
- 功能 2 负责 `找 + 探`
- 功能 3 负责 `用户触发的探`

重复的不是业务目标，而是底层能力：

- 匹配评分
- 状态流转
- 询问意愿
- 通知发送
- 去重和冷却
- 脱敏和隐私控制

## 4. 参与角色

- `用户 A`
  需要找对象的人。
- `用户 B`
  被推荐或被询问的人。
- `系统`
  负责匹配、提醒、询问意愿、推进状态。
- `运营/人工红娘`
  初期可以审核高风险个案、处理投诉、介入复杂情况。

## 5. 三个功能的清晰定义

### 5.1 功能一：持续关注

场景：

- 用户当前查了一轮，没有找到满意对象。
- 系统回应：“暂时没有符合你当前条件的人，我已经开始持续关注，有新合适对象会通知你。”

系统动作：

- 记录用户当前筛选条件。
- 创建一条 `持续关注订阅`。
- 后台定时扫描新资料、资料更新、活跃度变化。
- 一旦出现合适对象，触发通知。

### 5.2 功能二：系统主动撮合

场景：

- 系统在后台发现 A 和 B 很匹配。
- 且 A、B 都提前授权过“允许系统主动帮我问意愿”。

系统动作：

- 创建一条 `系统撮合案件`。
- 先按策略询问一侧，再询问另一侧。
- 两边都同意，才进入建联。

注意：

- 不建议一上来把双方都同时惊动。
- 默认采用 `顺序询问`，减少无效打扰。

### 5.3 功能三：代我推荐给对方

场景：

- A 看到了系统推荐的 B。
- A 觉得满意，但不好意思主动发起。
- A 点击“你先替我去问问她/他愿不愿意了解我”。

系统动作：

- 创建一条 `用户发起代荐案件`。
- 系统向 B 发一条脱敏介绍。
- B 同意后，再开放更多信息或进入聊天。

## 6. 推荐的统一状态机

建议围绕 `match_case` 做统一状态机，不要给 3 个功能各写一套。

### 6.1 顶层状态

- `watching`
  用户已进入持续关注。
- `candidate_found`
  后台发现候选人，但还没触发下一步动作。
- `notified`
  已通知用户“出现了合适候选”。
- `awaiting_requester_decision`
  等待发起方决定要不要进一步推进。
- `awaiting_primary_intent`
  等待第一侧回答“愿不愿意了解”。
- `awaiting_secondary_intent`
  第一侧同意后，等待另一侧回答。
- `mutual_yes`
  双方都愿意。
- `declined`
  其中一方明确拒绝。
- `timed_out`
  超时未回复。
- `cooldown`
  进入冷却期，暂不重复触达。
- `closed`
  案件已完成、取消或失效。

### 6.2 三种入口怎么接到同一个状态机

#### 入口 A：持续关注

`no_match_now -> watching -> candidate_found -> notified -> awaiting_requester_decision`

后续用户可以：

- 忽略
- 收藏
- 让我继续关注
- 让我替你去问对方

#### 入口 B：系统主动撮合

`candidate_found -> awaiting_primary_intent -> awaiting_secondary_intent -> mutual_yes / declined / timed_out`

#### 入口 C：代我推荐给对方

`user_click_proxy_intro -> awaiting_secondary_intent -> mutual_yes / declined / timed_out`

## 7. 为什么系统主动撮合建议“顺序询问”

如果同时去问两个人，会有两个问题：

- 一方很快拒绝，另一方已经被无意义打扰了一次。
- 同一个匹配同时给两边都发“有人想认识你”，体验容易显得突兀。

更稳的方式是：

1. 系统先选一侧做 `primary_side`
2. 只告诉他/她：“发现一位高匹配对象，是否愿意让我继续帮你了解一下？”
3. 如果 `primary_side` 同意，再向另一侧发脱敏邀约
4. 两边都同意后，再进入下一阶段

`primary_side` 的选取可以按下面规则：

- 最近活跃者优先
- 最近明确在找对象的人优先
- 更高意向授权等级者优先
- 最近没有被系统打扰过的人优先

## 8. 匹配与触发规则

现有 [search_candidates.py](/Users/sunmuchao/Downloads/Her/local-skills/partner-search/scripts/search_candidates.py) 已经提供：

- 结构化筛选
- 双边条件判断
- `score`
- `fit_score`
- `confidence_score`
- `risk_score`
- 活跃度、认证度、资料完整度
- 互相匹配的基础能力

在此基础上增加一层 `触发规则`。

### 8.1 进入“持续关注”条件

- 当前查询结果为空，或者
- 当前结果存在，但用户明确说“都不太合适，继续帮我盯着”

### 8.2 进入“出现候选通知”条件

建议同时满足：

- `fit_score >= 70`
- `confidence_score >= 18`
- `risk_score <= 20`
- 对方 `profile_status = active`
- 对方 `last_active_at` 在最近 30 天内，或者最近有资料更新
- 同一候选人近期没有对同一用户重复通知

### 8.3 进入“系统主动撮合”条件

建议同时满足：

- 双方都开启 `允许系统主动询问意愿`
- 双方都不是 `paused` / `archived` 状态
- 双向匹配都过线
- `fit_score >= 80`
- `confidence_score >= 22`
- `risk_score <= 15`
- 至少一方最近主动表示过“愿意认识合适的人”
- 同一对人不在冷却期

### 8.4 进入“代我推荐给对方”条件

- 用户先看过推荐结果
- 用户主动点击“代我推荐给对方”
- 当前目标没有屏蔽该用户类型或该地区
- 同一对人在冷却期外

## 9. 用户设置建议

至少要有 4 个开关，不然行为会混乱：

- `持续关注并通知我`
- `允许系统发现高匹配时主动问我意愿`
- `允许系统在我同意的前提下代我去问对方`
- `允许系统在双方都满足规则时主动撮合`

还建议加 3 个细设置：

- 通知方式：站内信 / 微信 / 飞书 / 邮件 / 短信
- 打扰频率：实时 / 每天汇总 / 每周汇总
- 可见信息级别：仅看脱敏摘要 / 同意后再开放更多

## 10. 数据模型

建议新增 6 张表，复用现有 `profiles` 和 `profile_photos`。

### 10.1 `match_subscriptions`

用途：

- 记录“持续关注”订阅

关键字段：

- `id`
- `owner_profile_id`
- `criteria_json`
- `status`：`active` / `paused` / `closed`
- `notify_channel`
- `digest_mode`
- `last_scan_at`
- `last_notified_at`
- `created_at`
- `updated_at`

### 10.2 `automation_preferences`

用途：

- 记录每个人对自动通知、自动撮合、代荐授权的设置

关键字段：

- `profile_id`
- `watch_enabled`
- `auto_match_opt_in`
- `proxy_intro_opt_in`
- `allow_profile_summary_share`
- `notify_channel_json`
- `quiet_hours_json`
- `created_at`
- `updated_at`

### 10.3 `match_candidates`

用途：

- 记录“系统发现过 A 和 B 可能匹配”

关键字段：

- `id`
- `left_profile_id`
- `right_profile_id`
- `detection_source`：`subscription` / `system_scan` / `manual_click`
- `score`
- `fit_score`
- `confidence_score`
- `risk_score`
- `match_reason_json`
- `detected_at`
- `expires_at`
- `dedupe_key`

说明：

- `left_profile_id` 和 `right_profile_id` 要按固定顺序存，避免 A-B 和 B-A 重复。

### 10.4 `match_cases`

用途：

- 真正的“案件表”，一个可推进的撮合流程就是一条 case

关键字段：

- `id`
- `candidate_id`
- `case_type`：`watch_notify` / `auto_match` / `proxy_intro`
- `requester_profile_id`
- `target_profile_id`
- `primary_side_profile_id`
- `secondary_side_profile_id`
- `status`
- `current_step`
- `masked_summary_version`
- `cooldown_until`
- `closed_reason`
- `created_at`
- `updated_at`

### 10.5 `match_outreach_events`

用途：

- 记录系统到底向谁发过什么消息、什么时候发的、结果是什么

关键字段：

- `id`
- `case_id`
- `receiver_profile_id`
- `channel`
- `event_type`：`notify_candidate` / `ask_intent` / `reminder` / `result`
- `payload_json`
- `delivery_status`
- `response_status`：`yes` / `no` / `timeout` / `ignored`
- `sent_at`
- `responded_at`

### 10.6 `match_case_audit_logs`

用途：

- 审计日志和问题排查

关键字段：

- `id`
- `case_id`
- `operator_type`：`system` / `user` / `ops`
- `operator_id`
- `action`
- `before_status`
- `after_status`
- `metadata_json`
- `created_at`

## 11. 后台任务设计

### 11.1 `subscription_scan_job`

作用：

- 扫描所有 `active` 的持续关注订阅
- 用订阅条件调用匹配引擎
- 找到新候选后生成 `match_candidates`
- 触发通知类 case

建议频率：

- 本地验证阶段：每 30 分钟
- 线上阶段：5 到 15 分钟

### 11.2 `profile_change_match_job`

作用：

- 当资料新增、更新、活跃度变化时，重新计算相关匹配

触发时机：

- 新资料导入
- 资料补全
- 认证等级提升
- 最近活跃时间刷新

### 11.3 `auto_match_job`

作用：

- 从高分候选池中筛出满足自动撮合条件的 pair
- 创建 `auto_match` 类型 case
- 发起第一侧意愿确认

### 11.4 `outreach_followup_job`

作用：

- 对未回复案件做提醒
- 对超时案件做关闭
- 对双方同意案件推进下一步

### 11.5 `cooldown_cleanup_job`

作用：

- 定时清理冷却期已结束的记录
- 允许未来重新进入候选池

## 12. 去重、频控和冷却规则

这是整个方案里最重要的风控层。

### 12.1 去重规则

- 同一对人只保留一个有效开放案件
- A-B 和 B-A 视为同一对
- 同一候选如果只是小幅分数变化，不重新通知
- 只有当资料发生明显变化时，才允许重新触发

### 12.2 建议冷却期

- 通知后无回复：`14 天`
- 明确拒绝：`30 到 60 天`
- 双方看过但都没动作：`14 天`
- 一次撮合已结束：`30 天`

### 12.3 频控规则

- 每人每天最多收到 `1~2` 条主动撮合类消息
- 每周最多收到 `3~5` 条系统主动撮合消息
- 通知类可以走汇总，不一定每次实时打扰

## 13. 隐私与安全规则

### 13.1 未同意前只能发什么

可以发：

- 年龄段
- 城市
- 身高区间
- 学历层级
- 恋爱/结婚目标
- 脱敏的人格摘要
- 系统总结的匹配原因

不能发：

- 全名
- 联系方式
- 住址
- 公司名
- 学校名
- 过细的家庭信息
- 原始备注全文

### 13.2 两阶段开放信息

第一阶段：

- 只给脱敏简介和匹配原因

第二阶段：

- 双方都同意后，才开放更完整的资料卡

第三阶段：

- 再进一步进入聊天、交换联系方式或人工建群

### 13.3 高风险场景

以下情况建议默认不全自动，进入人工审核：

- 离异带娃
- 对婚况或孩子接受度写得模糊
- 年龄、城市、婚恋目标冲突明显
- 备注里有高敏感内容
- 用户被投诉过“系统过度打扰”

## 14. 推荐文案

### 14.1 没找到人时

“这次还没有找到足够合适的人。我已经记下你的要求，接下来会继续帮你盯着。有新的高匹配对象出现时，我会主动通知你。”

### 14.2 发现新候选时

“我刚发现一位和你匹配度较高的人。先给你看脱敏摘要，如果你愿意，我可以继续帮你探一下对方的意愿。”

### 14.3 系统主动撮合时

“我最近发现一位和你匹配度较高的人。对方资料和你的要求比较接近。如果你愿意，我可以继续帮你了解一下对方是否也愿意认识你。”

### 14.4 代我推荐给对方时

“可以。我会先用脱敏方式把你的核心信息和兴趣传达给对方，只在对方愿意进一步了解时再推进下一步。”

### 14.5 一方拒绝时

“对方目前没有继续了解的意愿。我先不再打扰你们，后面如果出现新的合适对象，我会继续帮你留意。”

## 15. API 与交互建议

### 15.1 用户动作 API

- `POST /subscriptions/watch`
  创建持续关注订阅
- `POST /cases/proxy-intro`
  对某个推荐对象发起代荐
- `POST /cases/{id}/decision`
  用户对意愿询问回复 `yes` / `no`
- `POST /preferences/automation`
  更新自动撮合和通知设置

### 15.2 系统任务 API

- `POST /internal/jobs/subscription-scan`
- `POST /internal/jobs/auto-match`
- `POST /internal/jobs/follow-up`

## 16. 和当前代码库的落地关系

### 16.1 现有可直接复用的部分

[search_candidates.py](/Users/sunmuchao/Downloads/Her/local-skills/partner-search/scripts/search_candidates.py) 已经可以复用为匹配引擎：

- 复用条件解析
- 复用评分结果
- 复用活跃度与认证度判断
- 复用双向偏好校验
- 复用敏感信息遮罩逻辑

### 16.2 建议新增的代码模块

- `scripts/run_subscription_scan.py`
  扫描持续关注订阅并产生候选
- `scripts/run_auto_match.py`
  从高分候选中创建自动撮合案件
- `scripts/run_outreach_followup.py`
  处理提醒、超时、推进下一步
- `scripts/send_notifications.py`
  统一消息发送入口
- `references/proactive-matchmaking-design.md`
  当前这份设计文档

### 16.3 实现顺序建议

#### 第一阶段：先做“持续关注”

目标：

- 用户没找到人时，能进入后台订阅
- 后台发现新候选后能提醒

这是最容易落地、价值也最直接的一步。

#### 第二阶段：再做“代我推荐给对方”

目标：

- 用户能从推荐列表里点一个人
- 系统先替他去问对方

这一步的用户价值很高，而且比系统主动撮合更容易解释。

#### 第三阶段：最后做“系统主动撮合”

目标：

- 系统自己在后台发现高匹配 pair
- 只对已经明确授权的用户发起顺序询问

这一步最容易引发“被打扰”的感受，所以建议最后上线。

## 17. 关键指标

- 持续关注开通率
- 持续关注后首次命中时间
- 新候选通知点击率
- 代荐发起率
- 意愿确认回复率
- 双方都同意的比例
- 撮合后进入聊天的比例
- 用户投诉率
- 同一 pair 被重复打扰率

## 18. 最终建议

不要把这 3 个功能拆成 3 个独立系统，而是统一成一套：

- 1 个匹配引擎
- 1 套状态机
- 1 套通知与外呼模块
- 1 套去重和冷却规则
- 3 个触发入口

最适合的产品定义是：

`这是一个会持续帮你找、帮你试探意向、也能替你开口的 AI 红娘中间层。`
