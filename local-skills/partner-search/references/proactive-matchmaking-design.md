# 主动通知、代为开口、系统撮合的最小可落地方案

## 1. 先说结论

这件事的正确理解不是：

- 一次性做 3 个大功能

而是：

- 先把“还在找对象的人”管理好
- 再把“系统发现的新候选”沉淀下来
- 再决定“怎么提醒”
- 最后才处理“要不要代为开口”

完整链路可以这样理解：

`找对象状态 -> 候选发现 -> 推荐通知 -> 用户决策 -> 代问 -> 建联`

但第一阶段不要把整条链一次做完。

当前代码库下，更合理的上线顺序是：

1. 先做 `持续留意 + 新候选提醒`
2. 再做 `用户点一下，系统替你去问`
3. 最后再做 `系统自动撮合`

这是更稳的解法，也更符合当前 `partner-search` 的代码能力。

## 2. 为什么原方案不算最优

原方案的大方向是对的，问题主要不在业务理解，而在落地方式太重。

最关键的 4 个问题：

- 现在的 `search_candidates.py` 更像“帮 A 找候选人”，不是天然的“全库两两撮合引擎”
- 如果一上来就全量扫库、生成所有候选对，数据量和通知量会很快失控
- 状态和偏好被拆进太多表，第一版就会出现重复 source of truth
- 代问、强提醒、自动撮合都一起上，排障会很痛苦

所以第一版应该追求：

- 业务上闭环
- 技术上简单
- 后续能扩

而不是设计上看起来最完整。

## 3. 当前代码库下的正确边界

### 3.1 `partner-search skill` 做什么

- 理解自然语言
- 整理查询条件
- 调用搜索/匹配代码
- 解释结果

### 3.2 `search_candidates.py` 做什么

- 按单个用户视角筛候选
- 做结构化过滤
- 做双向硬冲突判断
- 产出 `score / fit_score / confidence_score / risk_score`

### 3.3 `search_candidates.py` 不该被当成什么

它不该被直接当成：

- 全库离线撮合器
- 无上限的 pair builder
- 一条 `candidate_pair` 只存一套分数的对称匹配器

原因很简单：

- `A -> B` 的分数不一定等于 `B -> A`
- A 觉得很合适，不代表 B 也一样觉得合适
- 现在的 scorer 本质上仍是“以某个请求方为中心”的

所以后续如果要落表存 `candidate_pair`，不能只存一套统一分数。

## 4. 推荐的产品链路

### 4.1 第一阶段：持续留意 + 新候选提醒

目标：

- 用户不用反复来问
- 系统一旦发现更好的新候选，就主动提醒

这一阶段只做：

- 用户处于“正在找对象”状态
- 系统持续为她刷新候选
- 有新候选时发站内推荐
- 用户可以跳过、收藏、自己去打招呼

这一阶段先不做：

- 系统代为问对方
- 系统自动两边推进
- 默认站外强触达

### 4.2 第二阶段：用户发起代问

目标：

- 用户看到候选，但不好意思主动开口
- 可以点一下，让系统代为去问

这一阶段新增：

- `match_case`
- 脱敏问询
- 对方的 `yes / no / later`

### 4.3 第三阶段：系统自动撮合

目标：

- 仅针对明确授权的用户
- 在命中高匹配时，系统主动推进

这一阶段最敏感，必须最后做。

## 5. 最小可落地架构

```text
profiles
   +
profile_match_preferences
   |
   v
refresh_candidates_for_profile(profile_id)
   |
   v
candidate_pairs
   |
   v
站内推荐卡片
   |
   +--> 跳过 / 收藏 / 自己打招呼
   |
   +--> 第二阶段再接：替我去问
```

这里最重要的原则只有 3 条：

- 第一阶段先把“推荐”跑顺
- 第二阶段再把“代问”接上
- 第三阶段才做“自动撮合”

## 6. 数据设计建议

第一阶段不建议直接上 6 张表。

更合理的是：

- 第一阶段：`1 到 3` 张新表
- 第二阶段：再补 `match_cases`
- 第三阶段：再补更细的触达审计

### 6.1 `profile_match_preferences`

用途：

- 存“这个人现在还找不找对象”
- 存“她愿意接受什么级别的提醒”

建议字段：

- `profile_id`
- `search_status`
- `notify_level`
- `allow_offsite_contact`
- `auto_match_opt_in`
- `proxy_intro_opt_in`
- `quiet_hours_json`
- `last_recommended_at`
- `last_candidate_refresh_at`
- `created_at`
- `updated_at`

建议枚举：

- `search_status`: `active_searching`, `paused`, `matched`, `archived`
- `notify_level`: `default`, `priority`, `strong`

注意：

- `in_match_pool` 不要单独存
- `待匹配池` 应该是派生状态

派生规则：

- `profiles.profile_status = active`
- 且 `profile_match_preferences.search_status = active_searching`

满足这两个条件，才算在待匹配池里。

这样可以少一个重复状态源。

### 6.2 `candidate_pairs`

用途：

- 存系统发现过的候选组合
- 做去重
- 做通知顺序控制
- 做冷却

建议字段：

- `id`
- `left_profile_id`
- `right_profile_id`
- `score_left_to_right`
- `score_right_to_left`
- `pair_score`
- `pair_status`
- `primary_profile_id`
- `secondary_profile_id`
- `primary_notified_at`
- `secondary_notified_at`
- `cooldown_until`
- `reason_json`
- `last_scored_at`
- `created_at`
- `updated_at`

关键约束：

- `left_profile_id` / `right_profile_id` 固定按 id 大小存
- `(left_profile_id, right_profile_id)` 必须唯一

状态建议先收敛成 3 个：

- `active`
- `cooldown`
- `closed`

不要第一版就上太多中间态。

### 6.3 `candidate_actions`

用途：

- 记录用户对候选做过什么动作

建议字段：

- `id`
- `candidate_pair_id`
- `actor_profile_id`
- `action_type`
- `metadata_json`
- `created_at`

建议动作：

- `view`
- `skip`
- `save`
- `direct_greet`
- `request_proxy_intro`

### 6.4 `match_cases`

这张表放到第二阶段再上。

用途：

- 用户点“替我去问”后，正式进入代问流程

建议字段：

- `id`
- `candidate_pair_id`
- `initiator_profile_id`
- `receiver_profile_id`
- `status`
- `masked_summary_version`
- `closed_reason`
- `created_at`
- `updated_at`

建议状态：

- `pending_outreach`
- `awaiting_reply`
- `accepted`
- `declined`
- `timed_out`
- `closed`

### 6.5 `outreach_events`

不建议第一阶段就单独建。

只有当下面场景真的存在时，再补：

- 多渠道发送
- 发送失败重试
- 渠道审计
- 合规留痕

如果第一阶段只有站内消息，可以先复用现有消息表或应用日志。

## 7. 分数设计建议

`candidate_pair` 不要只存一套总分。

至少要有：

- `score_left_to_right`
- `score_right_to_left`

然后再派生一个 `pair_score` 用于排序。

更稳的做法是：

- `pair_score` 以较低的一侧为主

大白话就是：

- 只有 A 觉得合适，不算真合适
- A 和 B 都还可以，才算值得推荐的一对

如果只存一套总分，后面会出现两个问题：

- 解释不清为什么先通知 A 而不是 B
- 解释不清为什么这对人被认为“互相合适”

## 8. 候选生成策略

不要做“全量扫待匹配池，然后生成所有可能 pair”。

更推荐下面这种增量策略：

### 8.1 触发时机

- 新资料进入
- 资料更新
- 活跃度明显变化
- 用户明确改了择偶条件
- 每日或每几小时做小批量补刷

### 8.2 生成方式

以单个 `profile_id` 为中心：

1. 调用 `search_candidates.py`
2. 取前 `K` 个候选，例如 `20` 或 `50`
3. 写入或刷新这些人的 `candidate_pairs`
4. 只对“新进入高分带”的候选发推荐

这样做的好处：

- 不会 pair 爆炸
- 容易控制资源
- 容易解释为什么这次会通知

### 8.3 反向分数怎么补

如果 A 的刷新里发现了 B：

1. 先写入 `score_left_to_right`
2. 再同步或异步补 `score_right_to_left`
3. 等双向分数都齐了，再更新 `pair_score`

这比一上来强做全库双向全量计算更稳。

## 9. 推荐通知策略

### 9.1 第一阶段先只做站内

默认推荐先走：

- 对话内提醒
- 通知列表
- 站内推荐卡片

不要默认就上：

- 微信
- 短信
- 电话

### 9.2 强提醒只给明确授权的人

`strong` 的意思不是“你一定会被推荐更多次”，而是：

- 更及时
- 更高优先级
- 在明确授权后可以走站外渠道

### 9.3 不建议同时惊动两边

更稳的顺序是：

1. 先通知一方
2. 给 `12 到 24 小时` 的动作窗口
3. 没动作，再决定是否推给另一方
4. 如果对方先点了“替我去问”，再进入第二阶段

## 10. 用户动作处理

第一阶段推荐卡片建议直接给按钮：

- `跳过`
- `收藏`
- `我自己打招呼`
- `替我去问`（第二阶段开放）

动作后的处理建议：

- `跳过`
  - 写 `candidate_actions`
  - 进入冷却
- `收藏`
  - 写 `candidate_actions`
  - 暂不推进
- `我自己打招呼`
  - 写 `candidate_actions`
  - 结束本次系统推进
- `替我去问`
  - 第二阶段创建 `match_case`

## 11. 冷却和频控

这一块必须比原方案更硬。

建议第一版就明确下面规则：

- 每人每天主动推荐不超过 `1 到 3` 条
- 同一对人在冷却期内不重复推荐
- `skip` 后冷却 `30` 天起
- 无动作可设短冷却，例如 `7 到 14` 天

同时要有数据库级约束或幂等键，避免 job 重跑时重复发。

至少要做到：

- `candidate_pairs(left_profile_id, right_profile_id)` 唯一
- 活跃中的 `match_case` 对同一对人只能有一条
- 单次消息发送要有幂等 key

## 12. 隐私规则

在双方都没有明确同意前，只能发脱敏摘要。

可以发：

- 年龄段
- 城市
- 身高区间
- 学历层级
- 婚恋目标
- 系统总结的匹配理由
- 脱敏后的性格/生活方式摘要

不能发：

- 全名
- 联系方式
- 住址
- 公司名
- 学校名
- 原始备注全文
- 任何能直接定位到个人的信息

这点和当前 `search_candidates.py` 已有的敏感信息处理方向是一致的，应该继续保持。

## 13. 推荐的实施顺序

### 阶段 1：先把“持续留意 + 提醒”做稳

做这些：

- `profile_match_preferences`
- `candidate_pairs`
- `candidate_actions`
- 站内推荐卡片
- 增量刷新 job
- 冷却和频控

不做这些：

- `match_cases`
- 自动撮合
- 默认站外触达
- 独立 `outreach_events`

### 阶段 2：再补“替我去问”

新增：

- `match_cases`
- 脱敏代问流程
- `yes / no / later`
- 超时关闭

### 阶段 3：最后上“系统自动撮合”

前提：

- 双方都明确授权
- `pair_score` 达到高阈值
- 前两阶段数据证明流程稳定

## 14. 不建议做的事

第一版不建议：

- 全库两两全量撮合
- 一次性新增 6 张表
- 同时上线提醒、代问、自动撮合
- 把 `in_match_pool` 存成独立状态
- 把 `A -> B` 的分数当成整对人的唯一分数
- 默认给所有人开站外强触达

## 15. 一句话总结

最优解不是“先设计一个最完整的大系统”，而是：

“先把正在找对象的人持续管理起来，用现有搜索能力为单个用户增量刷新 top-K 候选，并用站内推荐把新候选稳定送达；等推荐闭环跑顺以后，再补系统代问，最后才做自动撮合。”
