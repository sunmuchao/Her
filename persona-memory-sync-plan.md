# Persona Memory Sync 方案设计

## 1. 背景

当前系统已经有相亲候选库，核心数据在 MySQL 的 `profiles` 和 `profile_photos` 两张表里。

新增需求不是“再做一次筛人”，而是给红娘系统增加一层长期记忆和画像演化能力：

- 只要在聊天里越来越了解用户本人
- 只要逐渐确认用户喜欢什么类型的人
- 这些理解就应该沉淀到数据库
- `partner-search` 后续要直接用这些画像做更深的匹配
- 同时又不能把内部判断原样暴露给别人

这里真正的矛盾不是“要不要写进 `profiles`”，而是：

- 如果 `profiles` 不完整，匹配会浅、会不准
- 如果 `profiles` 太原始，又会有隐私和冒犯问题

所以必须把“完整存储”和“对外展示”拆开。

## 2. 核心结论

这套系统应该遵循下面这条总原则：

`profiles 存完整内部匹配画像，展示层只输出经过白名单筛选和文案转译的公开版本。`

更具体地说：

- `user_personas` 负责保存用户在聊天中的长期主画像
- `user_persona_observations` 负责保存每次新增理解的证据和变更日志
- `profiles` 负责保存可供 `partner-search` 深度使用的完整内部匹配画像
- `public_profile_view` 或等价的公开渲染层负责控制别人最终看到什么

因此，`profiles` 不应该再被定义成“前台公开资料表”，而应该被定义成：

`内部完整匹配画像底座`

## 3. 方案目标

### 3.1 业务目标

系统需要同时满足四件事：

1. 自动记住用户的基础资料
2. 自动记住用户的择偶硬条件和长期偏好
3. 让 `partner-search` 能基于更完整的画像做深度匹配
4. 让用户之间看到的资料仍然体面、克制、不过界

### 3.2 技术目标

系统需要具备：

- 可追溯
- 可回滚
- 可分级可见
- 可把“明确表达”和“系统推断”区分开
- 可把“内部匹配特征”和“公开展示文案”区分开

### 3.3 明确要避免的问题

这套机制必须避免：

- 把推断当成事实直接覆盖
- 把内部标签原样暴露给外部
- 让 `partner-search` 只能读到浅层公开文案
- 用户后续改口时无法回溯来源
- `profiles` 变成既不完整又不安全的折中产物

## 4. 架构总览

推荐采用五层模型：

1. 对话与反馈层
   用户聊天、筛人指令、对候选人的评价、连续偏好反馈。
2. `user_persona_observations`
   记录每次新增信息、推断、证据和是否应用。
3. `user_personas`
   记录用户主画像，是会话长期记忆的真源。
4. `profiles`
   记录完整内部匹配画像，是 `partner-search` 的深度匹配底座。
5. `public_profile_view`
   记录或生成面向他人的公开展示版本。

推荐的数据流如下：

`对话/反馈 -> observations -> user_personas -> profiles -> public_profile_view`

这里最关键的边界是：

- `partner-search` 读 `profiles`
- 用户前台界面读 `public_profile_view`
- 不允许前台界面直接原样读取 `profiles`

## 5. 每一层分别做什么

## 5.1 对话与反馈层

这是原始输入来源，主要包括：

- 用户明确介绍自己
- 用户明确说择偶要求
- 用户连续否掉某类候选人
- 用户对推荐结果做细化反馈
- 红娘系统在多轮对话后形成的高置信总结

这是唯一会不断产生新画像信号的地方。

## 5.2 user_persona_observations

这是“增量证据表”。

它记录的是：

- 哪个字段发生了新理解
- 新理解是什么
- 是用户明确说的，还是系统推断的
- 置信度是多少
- 有没有真正写入主画像
- 有没有真正同步进 `profiles`

这个表的价值不在筛人，而在：

- 审计
- 回滚
- 调试
- 追溯

一句话理解：

`observations 是红娘每次做的笔记。`

## 5.3 user_personas

这是“用户主画像表”。

它的职责是：

- 保存当前对用户最稳定的理解
- 支撑后续会话不需要每次重输
- 作为专属于该用户的长期画像真源

这里适合存：

- 基础条件
- 择偶结构条件
- 偏好标签
- 雷点标签
- 内部总结
- 公开总结草稿

一句话理解：

`user_personas 是红娘真正记住的你。`

## 5.4 profiles

这里是这次方案最重要的修正。

`profiles` 不再定义为公开展示层，而定义为：

`所有用户的内部完整匹配画像底座`

`partner-search` 未来应该直接读这里做深度匹配，因此 `profiles` 必须足够完整。

完整不代表要把冒犯性词汇原样写进去，而是要把“可计算、可比较、可筛选”的内部特征写进去。

一句话理解：

`profiles 是给匹配引擎和红娘后台看的，不是给用户 UI 直出的。`

## 5.5 public_profile_view

这是公开展示层。

它不一定必须是一张真实的物理表，也可以是：

- SQL VIEW
- 应用层渲染器
- API 序列化白名单
- 同步生成的公开缓存字段

它的职责只有一个：

`确保别人看到的是体面、脱敏、可公开的信息，而不是内部完整画像。`

一句话理解：

`public_profile_view 是别人最终看到的你。`

## 6. 为什么这样拆能解决矛盾

用户真正要的是两件事同时成立：

1. 匹配要深，不能只靠公开资料浅匹配
2. 公开展示要安全，不能暴露内部判断

如果只保留 `profiles` 一层，会出现两种坏结果：

- 存浅了：匹配不准
- 存深了：展示越界

所以正确做法一定是：

- `profiles` 深
- `public_profile_view` 克制

换句话说：

`可以完整存，但不能原样显示。`

## 7. 字段可见性分级

建议把所有画像字段分成三类，而不是简单分成“公开/不公开”。

### 7.1 public

这类字段允许进入公开展示层。

例如：

- 年龄
- 城市
- 学历
- 工作
- 身高
- 恋爱目标
- 经转译后的偏好总结

### 7.2 match_only

这类字段只给 `partner-search` 和红娘后台使用，不给普通用户看。

例如：

- 硬雷点
- 强偏好
- 风险特征
- 关系边界偏好
- 物质期待敏感度
- 沟通直接度偏好
- 暧昧容忍度

### 7.3 private_audit

这类字段只用于审计和回溯，不参与公开展示，也不建议参与直接匹配。

例如：

- 原始证据文本
- 会话片段摘要
- 推断来源
- 置信度
- 应用日志

### 7.4 存储位置建议

- `public`：可以存在 `profiles`，也可以投影到 `public_profile_view`
- `match_only`：必须存在 `profiles`
- `private_audit`：优先存在 `user_persona_observations`

## 8. “绿茶”“拜金”这类表达怎么处理

这是系统设计里必须单独说明的一部分。

像下面这些词：

- 绿茶
- 拜金
- 冷暴力
- 暧昧不清

都不建议作为最终内部字段直接存储，更不应该原样公开。

原因有三个：

1. 主观性强
2. 攻击性强
3. 不利于算法和后续维护

正确做法是：

`把带情绪色彩的词，转成中性、结构化、可计算的内部特征。`

### 8.1 归一化示例

| 原始说法 | 内部结构化特征 | 对外公开表达 |
| --- | --- | --- |
| 绿茶 | `boundary_clarity_risk=high`、`multi_thread_ambiguity_risk=high`、`attention_seeking_tendency=high` | 关系边界需要进一步确认 |
| 拜金 | `material_expectation_level=high`、`spending_values_mismatch_risk=high` | 消费观建议重点确认 |
| 冷暴力 | `communication_shutdown_risk=high`、`conflict_repair_capacity=low` | 沟通方式建议重点确认 |
| 暧昧不清 | `commitment_clarity=low`、`ambiguity_risk=high` | 认真交往意愿需进一步确认 |

### 8.2 设计原则

内部结构化特征要满足：

- 中性
- 可比较
- 可筛选
- 可被匹配引擎使用
- 不直接构成人身攻击

### 8.3 公开层原则

公开层永远不要出现：

- “她是绿茶”
- “她拜金”
- “她有问题”

公开层应该输出类似：

- 关系边界需要确认
- 沟通模式建议重点确认
- 消费观需要进一步了解

## 9. 新 Skill 的定位

建议新增一个独立 skill，名称建议：

`persona-memory-sync`

### 9.1 核心职责

这个 skill 负责：

- 从对话中识别画像信号
- 判断是明确表达还是推断
- 记录 observation
- 更新 `user_personas`
- 将主画像同步到 `profiles`
- 生成公开展示层需要的安全文案或渲染数据

### 9.2 不负责的事情

这个 skill 不负责：

- 候选人搜索和排序
- 推荐结果解释
- 照片管理
- 直接给用户下结论式标签

### 9.3 与 `partner-search` 的关系

推荐职责拆分如下：

- `persona-memory-sync`：负责记住用户是谁、喜欢谁、怕什么
- `partner-search`：负责读 `profiles` 做匹配、排序和解释

实际工作流中可以采用：

1. 先由 `persona-memory-sync` 更新画像
2. 再由 `partner-search` 读取最新 `profiles`

## 10. 数据模型

## 10.1 总体结构

新增：

- `user_personas`
- `user_persona_observations`

保留并增强：

- `profiles`
- `profile_photos`

新增逻辑层：

- `public_profile_view`

## 10.2 user_personas

用途：

- 存用户长期主画像
- 存对话记忆层需要复用的结构化信息
- 存内部总结和公开总结草稿

建议字段如下。

### 标识字段

- `id`
- `user_key`
  - 业务唯一标识，例如 `sunmuchao`
- `display_name`
- `profile_id`
  - 绑定到 `profiles.id`

### 用户本人基础信息

- `self_gender`
- `self_age`
- `self_city`
- `self_district`
- `self_height`
- `self_education`
- `self_income_wan`
- `self_job`
- `self_marital_status`
- `self_has_children`
- `self_smoking`
- `self_drinking`
- `self_relationship_goal`

### 择偶结构条件

- `target_gender`
- `target_age_min`
- `target_age_max`
- `target_cities`
- `target_height_min`
- `target_height_max`
- `target_education_min`
- `target_income_min_wan`
- `target_income_max_wan`
- `target_marital_statuses`
- `target_accept_partner_children`
- `target_accept_long_distance`
- `target_want_children`
- `target_marriage_timeline`

### 偏好与雷点

- `must_have_tags`
- `must_not_have_tags`
- `preferred_traits`
- `disliked_traits`

### 内部与公开总结

- `persona_summary_internal`
- `preference_summary_internal`
- `public_profile_summary_draft`
- `public_preference_summary_draft`

### 元数据

- `last_confirmed_at`
- `last_inferred_at`
- `created_at`
- `updated_at`

## 10.3 user_persona_observations

用途：

- 记录每次新增画像证据
- 保证更新可追溯

建议字段：

- `id`
- `user_key`
- `persona_id`
- `field_name`
- `field_value`
- `source_type`
  - `explicit` / `strong_inference` / `weak_inference`
- `confidence_score`
- `evidence_text`
- `conversation_ref`
- `action_type`
  - `insert` / `update` / `skip`
- `applied_to_persona`
- `applied_to_profile`
- `created_at`

## 10.4 profiles

这里存所有用户的内部完整匹配画像。

`partner-search` 需要直接读这里做深度匹配，因此建议 `profiles` 包含两类信息：

1. 现有公开安全结构字段
2. 新增的内部匹配特征字段

### 现有字段继续保留

继续使用现有结构字段，例如：

- `gender`
- `age`
- `city`
- `district`
- `height`
- `education`
- `job`
- `income_range`
- `relationship_goal`
- `preferred_*`
- `personality`
- `values`
- `lifestyle`
- `notes`

### 建议新增的内部匹配字段

推荐增加以下字段，优先用 JSON；若环境不方便，可先用 TEXT 存 JSON 字符串。

- `matcher_traits_json`
  - 记录人物稳定特征，如沟通风格、边界感、关系投入、作息、情绪稳定优先级等
- `matcher_preferences_json`
  - 记录择偶偏好补充，如对沟通、消费观、关系推进方式的要求
- `matcher_risks_json`
  - 记录只供匹配使用的风险特征，如模糊边界风险、消费观风险、沟通停摆风险
- `matcher_summary_internal`
  - 给红娘后台和匹配逻辑参考的内部总结
- `public_personality`
  - 对外公开版的人设文案
- `public_values`
  - 对外公开版的价值观和择偶偏好文案
- `public_notes`
  - 对外公开版补充说明

### 角色分工

- `matcher_*` 字段：给 `partner-search` 和后台用
- `public_*` 字段：给公开展示层用

## 10.5 public_profile_view

建议把它定义为“公开读取边界”，不强制要求必须是一张实体表。

推荐实现方式可选：

1. SQL VIEW
2. API 序列化白名单
3. 渲染函数 `render_public_profile(profile)`
4. 同步生成到缓存表

无论采用哪种实现，原则都一样：

- 公开层只读允许公开的字段
- 不允许把 `matcher_*` 原样透出
- 不允许把 observation 或原始推断证据透出

## 11. 更新来源与置信度分级

必须区分三种来源：

### 11.1 explicit

用户明确说过。

例如：

- 我 28 岁
- 我在无锡
- 我不接受异地
- 我最看重情绪稳定和消费观

### 11.2 strong_inference

用户没有逐字说，但多轮对话已经稳定体现，系统可以高置信总结。

例如：

- 连续多轮都因为暧昧、关系不清晰而否掉对象
- 连续多轮都把“沟通”和“消费观”放到前列

### 11.3 weak_inference

只有轻微迹象，不足以进入主画像。

例如：

- 单轮对某类职业稍有偏好
- 一次性情绪化吐槽

## 12. 合并策略

## 12.1 总体规则

系统每次识别到新的画像信号后，按下面顺序处理：

1. 先写 `user_persona_observations`
2. 判断来源类型和置信度
3. 决定是否写入 `user_personas`
4. 将需要同步的结构和特征写入 `profiles`
5. 生成或刷新公开层渲染内容

## 12.2 覆盖优先级

优先级从高到低：

1. 最新 `explicit`
2. 高置信 `strong_inference`
3. 低置信 `strong_inference`
4. `weak_inference`

### 具体规则

- 新的 `explicit` 可以覆盖旧的 `explicit`
- `strong_inference` 不能覆盖已有明确结构化硬字段
- `weak_inference` 只写 observation，不写主画像
- 标签类字段允许累积，但必须去重

## 12.3 硬字段和软字段分别处理

### 硬字段

例如：

- 年龄
- 城市
- 身高
- 学历
- 婚况
- 是否接受异地
- 是否接受对方有孩子

规则：

- 只有 `explicit` 才能直接覆盖
- 推断只能补充候选结论，不能直接改硬字段

### 软字段

例如：

- 看重沟通
- 讨厌暧昧
- 重视边界清晰
- 偏务实

规则：

- `strong_inference` 可以进入 `user_personas`
- 同时可以进入 `profiles.matcher_preferences_json`
- 公开展示时需要转译后才进入 `public_*`

## 13. user_personas 到 profiles 的同步逻辑

## 13.1 同步原则

`user_personas` 是会话长期记忆真源，`profiles` 是匹配底座。

因此同步不是简单复制，而是“按用途分发”：

- 结构化明确条件 -> `profiles` 标准字段
- 深度匹配特征 -> `profiles.matcher_*`
- 公开文案 -> `profiles.public_*`

## 13.2 结构化映射

### 用户本人信息

- `self_gender -> profiles.gender`
- `self_age -> profiles.age`
- `self_city -> profiles.city`
- `self_district -> profiles.district`
- `self_height -> profiles.height`
- `self_education -> profiles.education`
- `self_job -> profiles.job`
- `self_marital_status -> profiles.marital_status`
- `self_has_children -> profiles.has_children`
- `self_smoking -> profiles.smoking`
- `self_drinking -> profiles.drinking`
- `self_relationship_goal -> profiles.relationship_goal`

### 收入映射

- `self_income_wan` 需要转换为 `profiles.income_range`
- 例如：
  - 40 -> `36-45万/年`
  - 25 -> `20-30万/年`

### 择偶结构条件

- `target_age_min -> profiles.preferred_age_min`
- `target_age_max -> profiles.preferred_age_max`
- `target_cities -> profiles.preferred_cities`
- `target_height_min -> profiles.preferred_height_min`
- `target_height_max -> profiles.preferred_height_max`
- `target_education_min -> profiles.preferred_education_min`
- `target_income_min_wan -> profiles.preferred_income_min_wan`
- `target_income_max_wan -> profiles.preferred_income_max_wan`

## 13.3 匹配特征映射

下面这些更深的东西，不适合只靠公开字段表示，建议进入 `matcher_*`：

- 是否特别看重边界清晰
- 是否强烈排斥暧昧拉扯
- 是否对消费观不一致敏感
- 是否更偏好同城稳定推进
- 是否特别在意情绪稳定
- 是否偏好直接沟通

这些都适合被编码到：

- `matcher_traits_json`
- `matcher_preferences_json`
- `matcher_risks_json`

## 13.4 公开文案映射

公开展示不要直接使用原始标签，而是用渲染后的文案：

- `profiles.public_personality`
- `profiles.public_values`
- `profiles.public_notes`

若还需要兼容旧逻辑，也可以把公开内容映射到原有：

- `personality`
- `values`
- `notes`

但前提是要明确：

`这些字段用于公开渲染时，必须已经是安全文案，不得再塞内部原始标签。`

## 14. public_profile_view 的生成规则

## 14.1 公开层的职责

公开层不负责保存完整事实，只负责：

- 读取允许公开的字段
- 对内部特征做文案转译
- 输出别人可看的版本

## 14.2 公开层读取规则

公开层只允许读取：

- `profiles` 里的基础安全字段
- `profiles.public_*`
- 必要时少量经明确批准的结构字段

公开层不允许读取：

- `matcher_traits_json`
- `matcher_preferences_json`
- `matcher_risks_json`
- `matcher_summary_internal`
- observations 原始证据

## 14.3 文案转译原则

公开文案必须：

- 自然
- 克制
- 不带攻击性
- 保留真实偏好
- 不暴露内部判断过程

### 示例

后台内部：

- `must_not_have = 冷暴力,暧昧不清,拜金`

公开文案：

- 希望关系边界清晰，沟通顺畅，消费观一致
- 不喜欢长期拉扯和高消耗型相处

## 15. partner-search 应该如何使用

`partner-search` 未来不应该只读浅层公开资料，而应该读：

- `profiles` 标准结构字段
- `profiles.matcher_traits_json`
- `profiles.matcher_preferences_json`
- `profiles.matcher_risks_json`
- `profiles.matcher_summary_internal`

这样它才能做更深的事情，例如：

- 不只是匹配年龄和城市
- 还能匹配沟通方式
- 还能匹配关系边界偏好
- 还能识别高冲突风险和高消耗风险
- 还能根据用户连续反馈修正偏好

而公开展示层只给用户看：

- 结构化公开信息
- 公开版性格和偏好文案
- 不带原始内部标签的风险提示

## 16. 访问边界

建议明确三类读取角色：

### 16.1 匹配引擎

可读：

- `profiles` 全部匹配字段
- 必要时读 `user_personas`

不可读：

- 无特殊需求时不读 observation 原始全文

### 16.2 红娘后台

可读：

- `profiles`
- `user_personas`
- `user_persona_observations`

用途：

- 审核
- 回滚
- 人工校正

### 16.3 普通用户前台

只可读：

- `public_profile_view`

不可读：

- `profiles` 原表
- `matcher_*`
- `observations`

这是整套方案防隐私越界的核心。

## 17. 当前用户案例

## 17.1 已明确表达的信息

以当前对话为例，已确认：

- 男
- 28 岁
- 无锡
- 178
- 211 本科
- 40w
- 未婚
- 无孩子
- 不抽烟
- 少喝酒
- 结婚导向

择偶条件：

- 找女生
- 24-30 岁
- 无锡
- 160+
- 本科及以上
- 未婚
- 不接受有孩子
- 不接受异地

明确偏好：

- 情绪稳定
- 愿意沟通
- 消费观正常

明确雷点：

- 抽烟
- 冷暴力
- 暧昧不清
- 绿茶
- 拜金

## 17.2 进入 user_personas 的内容

结构化字段直接进入主画像。

建议标签：

- `must_have_tags = 情绪稳定,愿意沟通,消费观正常`
- `must_not_have_tags = 抽烟,冷暴力,暧昧不清,绿茶,拜金`

建议内部总结：

- `persona_summary_internal`
  - 无锡本地，结婚导向，偏务实，倾向稳定清晰的长期关系
- `preference_summary_internal`
  - 看重情绪稳定、沟通和消费观，不接受异地、有孩子或长期暧昧拉扯型关系

## 17.3 同步到 profiles 的内部匹配特征

不建议把 `绿茶`、`拜金` 原样同步为标签，而建议转译为内部特征：

- `boundary_clarity_risk` 相关偏好阈值更严格
- `multi_thread_ambiguity_risk` 排斥度高
- `material_expectation_level` 敏感度高
- `communication_shutdown_risk` 容忍度低
- `emotional_stability_priority` 权重高
- `communication_directness_preference` 权重高

这些更适合存在：

- `matcher_preferences_json`
- `matcher_risks_json`
- `matcher_summary_internal`

## 17.4 对外公开版建议

公开版不建议出现原始雷点原话。

建议写法：

- `public_personality`
  - 无锡本地，生活方式稳定，认真以结婚为导向
- `public_values`
  - 看重情绪稳定、沟通顺畅和消费观一致，希望关系清晰、认真推进
- `public_notes`
  - 更适合同城稳定发展的关系，不喜欢长期暧昧和高消耗型相处

## 18. 技术实现建议

## 18.1 Skill 目录结构

建议新增：

```text
local-skills/
  persona-memory-sync/
    SKILL.md
    agents/
      openai.yaml
    scripts/
      ensure_persona_tables.py
      upsert_persona_memory.py
      sync_persona_to_profile.py
      render_public_profile.py
    references/
      schema.md
      merge-rules.md
      public-rendering.md
      visibility-policy.md
```

## 18.2 脚本职责

### `ensure_persona_tables.py`

负责：

- 创建 `user_personas`
- 创建 `user_persona_observations`
- 必要时对 `profiles` 做增量字段补齐

### `upsert_persona_memory.py`

负责：

- 接收结构化画像 patch
- 先写 observation
- 再合并进 `user_personas`

### `sync_persona_to_profile.py`

负责：

- 从 `user_personas` 同步结构化字段到 `profiles`
- 写入 `matcher_*`
- 写入 `matcher_summary_internal`

### `render_public_profile.py`

负责：

- 根据 `profiles` 的内部数据生成 `public_*`
- 或生成 `public_profile_view` 需要的数据

## 18.3 推荐工作流

推荐工作流如下：

1. 从对话中抽取画像信号
2. 写入 `user_persona_observations`
3. 合并进 `user_personas`
4. 同步到 `profiles`
5. 渲染公开版
6. `partner-search` 读取 `profiles`
7. 前台读取 `public_profile_view`

## 19. SQL 设计建议

以下为建议方向，不要求第一版完全一致。

## 19.1 user_personas

```sql
CREATE TABLE user_personas (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(64) DEFAULT NULL,
  profile_id BIGINT DEFAULT NULL,

  self_gender VARCHAR(8) DEFAULT NULL,
  self_age INT DEFAULT NULL,
  self_city VARCHAR(64) DEFAULT NULL,
  self_district VARCHAR(64) DEFAULT NULL,
  self_height INT DEFAULT NULL,
  self_education VARCHAR(32) DEFAULT NULL,
  self_income_wan INT DEFAULT NULL,
  self_job VARCHAR(64) DEFAULT NULL,
  self_marital_status VARCHAR(32) DEFAULT NULL,
  self_has_children TINYINT(1) DEFAULT NULL,
  self_smoking VARCHAR(16) DEFAULT NULL,
  self_drinking VARCHAR(16) DEFAULT NULL,
  self_relationship_goal VARCHAR(32) DEFAULT NULL,

  target_gender VARCHAR(8) DEFAULT NULL,
  target_age_min INT DEFAULT NULL,
  target_age_max INT DEFAULT NULL,
  target_cities TEXT,
  target_height_min INT DEFAULT NULL,
  target_height_max INT DEFAULT NULL,
  target_education_min VARCHAR(32) DEFAULT NULL,
  target_income_min_wan INT DEFAULT NULL,
  target_income_max_wan INT DEFAULT NULL,
  target_marital_statuses TEXT,
  target_accept_partner_children VARCHAR(16) DEFAULT NULL,
  target_accept_long_distance VARCHAR(16) DEFAULT NULL,
  target_want_children VARCHAR(16) DEFAULT NULL,
  target_marriage_timeline VARCHAR(32) DEFAULT NULL,

  must_have_tags TEXT,
  must_not_have_tags TEXT,
  preferred_traits TEXT,
  disliked_traits TEXT,

  persona_summary_internal TEXT,
  preference_summary_internal TEXT,
  public_profile_summary_draft TEXT,
  public_preference_summary_draft TEXT,

  last_confirmed_at DATETIME DEFAULT NULL,
  last_inferred_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 19.2 user_persona_observations

```sql
CREATE TABLE user_persona_observations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL,
  persona_id BIGINT DEFAULT NULL,
  field_name VARCHAR(64) NOT NULL,
  field_value TEXT,
  source_type ENUM('explicit','strong_inference','weak_inference') NOT NULL,
  confidence_score INT DEFAULT NULL,
  evidence_text TEXT,
  conversation_ref VARCHAR(128) DEFAULT NULL,
  action_type ENUM('insert','update','skip') NOT NULL DEFAULT 'insert',
  applied_to_persona TINYINT(1) NOT NULL DEFAULT 0,
  applied_to_profile TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_user_persona_observations_user_key (user_key),
  KEY idx_user_persona_observations_persona_id (persona_id),
  KEY idx_user_persona_observations_field_name (field_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 19.3 profiles 增量字段建议

```sql
ALTER TABLE profiles
  ADD COLUMN matcher_traits_json JSON NULL,
  ADD COLUMN matcher_preferences_json JSON NULL,
  ADD COLUMN matcher_risks_json JSON NULL,
  ADD COLUMN matcher_summary_internal TEXT NULL,
  ADD COLUMN public_personality TEXT NULL,
  ADD COLUMN public_values TEXT NULL,
  ADD COLUMN public_notes TEXT NULL;
```

如果当前 MySQL 版本或迁移策略不方便使用 JSON，可先用 `TEXT` 存 JSON 字符串。

## 19.4 public_profile_view

如果采用 SQL VIEW，可参考：

```sql
CREATE VIEW public_profile_view AS
SELECT
  id,
  name,
  avatar_url,
  photo_count,
  gender,
  age,
  city,
  district,
  height,
  education,
  job,
  income_range,
  relationship_goal,
  public_personality AS personality,
  public_values AS values,
  public_notes AS notes
FROM profiles;
```

如果公开逻辑后续更复杂，也可以改成应用层渲染，而不是 SQL VIEW。

## 20. 风险与防护

## 20.1 风险一：推断过度

表现：

- 系统把一两句情绪化表达当成长期偏好

防护：

- 引入 `weak_inference`
- 不到阈值不进主画像

## 20.2 风险二：匹配太浅

表现：

- `profiles` 里只有公开资料，`partner-search` 读不到深层偏好

防护：

- 明确 `profiles` 是内部完整匹配底座
- 将深度特征写入 `matcher_*`

## 20.3 风险三：公开资料越界

表现：

- 把内部原始判断直接展示给用户

防护：

- 前台永远不直接读 `profiles` 原表
- 公开层只走 `public_profile_view`
- 原始负面词不允许直接上屏

## 20.4 风险四：覆盖用户明确表达

表现：

- 系统推断把结构化硬字段改掉

防护：

- 结构化硬字段只允许 `explicit` 覆盖

## 20.5 风险五：后续修正困难

表现：

- 不知道为什么某个字段变成现在这样

防护：

- 保留 `user_persona_observations`
- 每次更新记录 `source_type` 和 `evidence_text`

## 21. MVP 落地建议

第一版不需要一步做到最复杂，建议分三阶段。

## 21.1 第一阶段

- 建 `user_personas`
- 建 `user_persona_observations`
- 给 `profiles` 增加 `matcher_*` 和 `public_*`
- 支持显式字段写入
- 支持显式字段同步到 `profiles`

## 21.2 第二阶段

- 支持 `strong_inference`
- 支持负面原词到中性特征的归一化
- 支持公开文案自动生成
- 让 `partner-search` 读取 `matcher_*`

## 21.3 第三阶段

- 根据用户连续反馈自动修正画像
- 引入阈值和置信度衰减
- 支持更复杂的角色权限和公开策略

## 22. 推荐默认决策

如果要尽快进入实现，建议默认采用以下策略：

1. `user_personas` 作为会话长期记忆真源
2. `profiles` 作为内部完整匹配底座
3. `public_profile_view` 作为公开展示边界
4. `explicit` 可更新结构化硬字段并同步到 `profiles`
5. `strong_inference` 可进入主画像和 `profiles.matcher_*`
6. `weak_inference` 只进 observation
7. 任何攻击性原词都先转成中性结构化特征
8. 前台不允许直接读取 `profiles` 原始内部字段

## 23. 最终结论

这套方案的关键不是“多建一张表”，而是明确三件事：

1. `user_personas` 负责记住用户
2. `profiles` 负责完整匹配
3. `public_profile_view` 负责安全展示

正确的数据关系应该是：

`对话/反馈 -> observations -> user_personas -> profiles -> public_profile_view`

这样可以同时满足四个目标：

- 系统会越来越懂用户
- `partner-search` 能做更深的匹配
- 用户不需要反复重输条件
- 公开展示不会把内部判断直接暴露出去

这才是“完整画像要能用于匹配，但不能原样展示”的正确实现方式。
