# 未承接字段清单

本文档只统计当前“聊天结束摘要回填”链路中：

- 已经能被识别出来
- 但当前没有正式落到 `user_personas` / `conversation_summaries`
- 只能被标记、日志输出、或直接拦截丢弃

的字段。

## 当前未承接字段

### 1. `target_gender`

- 含义：目标对象性别
- 典型来源：
  - `找男生`
  - `希望找女性`
  - `男，28-35岁...`
- 当前识别方式：
  - 在 `partner_expectation` 中识别 `男 / 男生 / 男性 / 女 / 女生 / 女性`
- 当前状态：
  - **可识别**
  - **不写入 `user_personas`**
  - **不写入 `conversation_summaries`**
- 当前处理：
  - 进入 `unsupported_structured_fields`
  - 记录日志：`target_gender=male/female`
- 原因：
  - 当前这条链路被要求不写 `profiles`
  - 而 `target_gender` 在现有系统里更偏向硬条件侧，不在本轮允许写入范围内

### 2. `relationship_stage`

- 含义：关系阶段 / 关系目的
- 典型来源：
  - `先谈恋爱`
  - `以谈恋爱为目的`
  - `谈恋爱为目的`
- 当前识别方式：
  - 在 `partner_expectation` 中识别上述短语
- 当前状态：
  - **可识别**
  - **不写入 `user_personas`**
  - **不写入 `conversation_summaries`**
- 当前处理：
  - 进入 `unsupported_structured_fields`
  - 同时从摘要文本中剥离
- 原因：
  - 这类信息不属于高纯度非结构化摘要
  - 但当前也没有在这条回填链路中定义好的正式 persona 承接字段

### 3. `distance_scope`

- 含义：距离范围短语
- 典型来源：
  - `同城`
  - `同城优先`
  - `同城无锡`（其中城市会拆成 `target_cities=无锡`，`同城` 仍属于未承接残余语义）
- 当前识别方式：
  - 在 `partner_expectation` 中识别 `同城`
- 当前状态：
  - **部分可识别**
  - **不写入 `user_personas`**
  - **不写入 `conversation_summaries`**
- 当前处理：
  - `同城无锡` 里的 `无锡` 会尝试写 `target_cities`
  - `同城` 语义本身进入 `unsupported_structured_fields.distance_scope`
  - 同时从摘要中剥离
- 原因：
  - 当前没有单独的稳定字段承接“同城优先/同城限定”这类短语化距离语义
  - 现有 `target_accept_long_distance` 更偏“接受/不接受异地”，不是同一个层级

### 4. `self_plan`

- 含义：用户自己的职业/生活计划，不属于对对象的期待
- 典型来源：
  - `想换职业方向`
  - `想换工作`
  - `准备换工作`
  - `考虑换工作`
- 当前识别方式：
  - 在 `partner_expectation` 中识别这些 self 计划短语
- 当前状态：
  - **可识别**
  - **不写入 `user_personas`**
  - **不写入 `conversation_summaries`**
- 当前处理：
  - 进入 `unsupported_structured_fields.self_plan`
  - 从 `partner_expectation` 中剥离
  - 若摘要主体因此失真或只剩残壳，则整条摘要被拦截
- 原因：
  - 这类信息属于 self 状态，不是目标对象要求
  - 当前链路还没有单独的 self 侧计划字段承接

## 当前已承接、不是未承接字段的项

以下字段已经在本轮摘要回填链路里有承接，不属于“未承接字段清单”：

- `target_age_min`
- `target_age_max`
- `target_height_min`
- `target_height_max`
- `target_cities`
- `target_education_min`
- `target_income_min_wan`
- `target_income_max_wan`
- `target_marital_statuses`
- `target_accept_partner_children`
- `target_accept_long_distance`
- `target_marriage_timeline`
- `target_want_children`
- `self_personality_traits_json`（当前只承接合法 MBTI）

## 当前系统策略

对于“未承接字段”，当前统一策略是：

1. 尽量先识别出来
2. 从摘要文本中剥离
3. 放入 `unsupported_structured_fields`
4. 不写 persona
5. 不写摘要
6. 如果剥离后摘要里仍残留结构化痕迹，整条摘要直接拦截

## 后续可选动作

如果后续要把这些字段正式承接，需要逐项决定：

1. 是否允许写入 `user_personas`
2. 对应字段名是什么
3. 是否允许同步到其他条件编译链路
4. 是否属于硬条件、软条件、关系阶段、还是 self 状态

当前建议优先级：

1. `relationship_stage`
2. `distance_scope`
3. `target_gender`
4. `self_plan`
