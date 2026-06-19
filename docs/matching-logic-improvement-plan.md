# 匹配逻辑改进方案

## 1. 背景

当前系统的匹配逻辑整体偏“硬筛选”。

这会导致一个明显问题：

- 某些本来只是“偏好不完全命中”的候选人，会被直接过滤掉
- 结果页经常出现“没有匹配”
- 但实际并不是没有候选人，而是规则把人筛没了

典型例子：

- A 用户收入 `100w/年`
- B 用户期望收入区间 `30w-50w/年`

当前逻辑会认为：

- A 的收入不在 B 的期望区间内
- 因此 A 不符合 B 的 reciprocal 收入偏好
- 如果这条规则被按 hard 处理，A 会被直接过滤

这在业务上不合理。

因为：

- `低于下限` 往往代表确实不满足
- `高于上限` 不一定代表不满足
- 很多用户写区间时，本意是“希望对方至少在这个生活阶段”，而不是“绝对不能高于这个数”


## 2. 当前代码链路

当前匹配主链路如下：

1. 请求条件进入 `partner_search`
2. 对请求条件和 `self_profile` 做标准化
3. 在 MySQL 层先做一轮预筛
4. 对每个候选人执行 `evaluate_candidate`
5. 在 `evaluate_candidate` 内执行 reciprocal 反向匹配
6. 对通过的人再做打分、排序、补充风险提示
7. 如果严格条件下无人通过，再走 no-match fallback

核心代码位置：

- 入口与字段别名：
  [partner_search/search_candidates.py](/Users/sunmuchao/Downloads/Her/partner_search/search_candidates.py)
- 条件归一化：
  [partner_search/search_profile_context.py](/Users/sunmuchao/Downloads/Her/partner_search/search_profile_context.py)
- 数据加载与 MySQL 预筛：
  [partner_search/search_sources.py](/Users/sunmuchao/Downloads/Her/partner_search/search_sources.py)
- 主匹配逻辑：
  [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)
- reciprocal 反向偏好判断：
  [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- 无匹配诊断与 fallback：
  [partner_search/search_no_match.py](/Users/sunmuchao/Downloads/Her/partner_search/search_no_match.py)


## 3. 当前使用到的数据库字段

### 3.1 profiles 表中的基础资料字段

匹配引擎当前会读取如下核心字段：

- 基础条件：
  `gender age city district settlement_city height education job income_range income_min_wan income_max_wan relationship_goal`
- 生活与婚恋条件：
  `smoking drinking long_distance housing_status car_status marital_status has_children want_children marriage_timeline`
- reciprocal 接受度：
  `accept_long_distance accept_smoking accept_drinking accept_marital_status accept_partner_children`
- 可信度字段：
  `profile_status last_active_at verified_level photo_verification_level`
- 解释性/排序信号：
  `personality values lifestyle hobbies life_routine communication_style dating_pace expression_style relationship_capacity interaction_comfort patience_level life_texture career_intensity exercise_habit growth_signal warmth_style aesthetic_expression conversation_resonance personal_presence lightness_humor consumption_attitude chat_texture commitment_clarity relationship_execution blended_family_readiness`

字段投影定义见：

- [partner_search/search_sources.py](/Users/sunmuchao/Downloads/Her/partner_search/search_sources.py)


### 3.2 旧版 reciprocal 偏好字段

当前 reciprocal 判断仍直接依赖以下旧字段：

- `preferred_age_min`
- `preferred_age_max`
- `preferred_cities`
- `preferred_height_min`
- `preferred_height_max`
- `preferred_age_strictness`
- `preferred_height_strictness`
- `preferred_education_min`
- `preferred_education_strictness`
- `preferred_income_min_wan`
- `preferred_income_max_wan`
- `preferred_income_strictness`


### 3.3 persona 表中的新偏好字段

系统已经在逐步把偏好字段迁移到 persona / collected 层。

主要映射关系如下：

- `target_age_min -> preferred_age_min`
- `target_age_max -> preferred_age_max`
- `target_cities -> preferred_cities`
- `target_height_min -> preferred_height_min`
- `target_height_max -> preferred_height_max`
- `target_education_min -> preferred_education_min`
- `target_income_min_wan -> preferred_income_min_wan`
- `target_income_max_wan -> preferred_income_max_wan`
- `target_marital_statuses -> accept_marital_status`
- `target_accept_partner_children -> accept_partner_children`
- `target_accept_long_distance -> accept_long_distance`

映射与补齐逻辑见：

- [match_domain/deprecated_profile_columns.py](/Users/sunmuchao/Downloads/Her/match_domain/deprecated_profile_columns.py)
- [match_domain/reciprocal_preferences.py](/Users/sunmuchao/Downloads/Her/match_domain/reciprocal_preferences.py)

说明：

- 旧的 `profiles` 偏好字段已经被视为待废弃字段
- 未来偏好语义应以 persona 层为准，而不是继续依赖 `profiles` 上的旧列


## 4. 当前逻辑存在的问题

### 4.1 系统以“过滤优先”而不是“排序优先”

当前逻辑不是先把候选人都保留下来，再通过分数排序。

相反，流程是：

- 先过滤
- 再对幸存候选人排序

这会导致很多“可聊但不完美”的人根本进不到结果集。


### 4.2 reciprocal strictness 默认值过硬

当前 `normalize_strictness_state()` 的默认逻辑是：

- 严格度字段为空时，默认返回 `hard`

代码位置：

- [partner_search/search_inputs.py](/Users/sunmuchao/Downloads/Her/partner_search/search_inputs.py)

影响字段：

- 年龄
- 身高
- 学历
- 收入

这意味着：

- 只要数据库里没有明确写“可放宽”或“参考”
- 系统就会把这些区间偏好当成硬规则

这是当前匹配过于僵硬的根源之一。


### 4.3 收入区间逻辑把“低于下限”和“高于上限”混为一谈

当前 reciprocal 收入逻辑使用 `income_range_overlaps()`：

- 只要收入区间不重叠，就视为 `False`

代码位置：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)

当前效果：

- 候选人收入低于对方下限 -> 不匹配
- 候选人收入高于对方上限 -> 不匹配

业务问题：

- 这两种情况语义不同
- 但代码里被同等对待


### 4.4 高于上限不应默认等于“不接受”

例如：

- 对方写 `30w-50w`
- 候选人为 `100w`

当前逻辑容易解释为：

- “对方不要收入高的人”

但现实通常更接近：

- “对方期望的是这个生活阶段的人”
- “不是严格排斥更高收入的人”

所以：

- `高于上限` 不应默认走硬过滤链路


### 4.5 fallback 太晚

当前逻辑中，只有在严格条件完全没人通过时，才会从 fallback 模式中放出“放宽后可聊对象”。

代码位置：

- [partner_search/search_no_match.py](/Users/sunmuchao/Downloads/Her/partner_search/search_no_match.py)

问题：

- 正常结果页中看不到这些“可聊但不完全命中”的对象
- 用户只会频繁看到“无匹配”


### 4.6 reciprocal 规则缺少层级

当前 reciprocal 判断基本只有两种结果：

- 直接失败
- 通过但打风险标记

缺少中间层：

- 允许保留，但明显降权

这导致系统在“硬筛”和“放过”之间缺少缓冲区。


## 5. 改造目标

本次匹配逻辑改造目标如下：

1. 从“过度硬筛”改成“硬筛 + 软扣分 + 风险提示”的分层模式
2. 减少“假无匹配”
3. 提高结果池容量
4. 让 reciprocal 偏好更接近真实用户语义
5. 让收入、学历、身高等区间类条件更合理
6. 逐步把旧 profile 偏好语义迁移到 persona 偏好语义


## 6. 新的规则设计

### 6.1 条件分层

建议将匹配条件分成四类。

#### A. 硬过滤条件

这类条件仍然可以直接过滤：

- 性别不匹配
- 婚况明确不接受
- 有孩子明确不接受
- 抽烟/喝酒明确不接受
- 异地明确不接受
- 年龄明显超出接受范围，且被明确标为硬条件


#### B. 强负向但不必直接过滤

这类条件建议默认保留候选人，但明显降权：

- 收入低于对方下限
- 学历低于对方明确底线
- 身高低于对方明确底线
- 城市不命中，但异地只是可协商


#### C. 轻负向或风险提示

这类条件不应直接过滤，只做轻扣分或提示：

- 收入高于对方上限
- 年龄略高于上限
- 身高高于上限
- 城市偏好未命中，但资料写了接受异地
- 婚史/孩子接受度偏保守但不是拒绝


#### D. 仅用于排序加分

这类条件不应承担过滤职责：

- preferred traits
- must_have_tags 中非硬性标签
- 生活感、审美、人物感、聊天温度、共鸣感等信号


## 7. 收入匹配规则的完整改造方案

这是本次最关键的一项。

### 7.1 当前收入规则

当前规则近似为：

- 候选收入和对方期望区间重叠 -> 命中
- 不重叠 -> 不命中
- 如果 strictness 是 hard -> 直接过滤
- 否则 -> 打风险标记


### 7.2 新的收入判定模型

收入区间判断应拆成四种结果：

- `unknown`
- `below_min`
- `within_band`
- `above_max`

不能再只用“重叠 / 不重叠”。


### 7.3 新的默认语义

收入区间默认应理解为“目标带”，而不是“封顶线”。

含义如下：

- `within_band`
  说明命中理想带，正常加分
- `below_min`
  说明生活阶段可能低于预期，属于明显负向
- `above_max`
  说明超出理想带，但不默认代表不接受
- `unknown`
  说明资料缺失，走信息缺失逻辑


### 7.4 收入规则建议

建议采用如下规则：

#### strictness = hard

- `below_min`：允许硬过滤
- `above_max`：不建议硬过滤，改为强扣分

#### strictness = soft

- `below_min`：中到强扣分
- `above_max`：轻扣分或仅提示

#### strictness = reference

- `below_min`：弱提示
- `above_max`：弱提示或不处理


### 7.5 最关键原则

无论 strictness 是否为空，以下原则都应成立：

- `高于上限` 不应默认进入硬过滤链路


### 7.6 strictness 默认值调整建议

当前空值默认 `hard`，不合理。

建议：

- 年龄、婚况、孩子、异地等可以继续保守
- 收入 strictness 默认值单独改为 `soft`

也就是说：

- strictness 默认策略不再一刀切全字段共用


## 8. 其他区间类条件的统一改造建议

建议把年龄、身高、收入统一为同一种边界模型：

- `below_min`
- `within_range`
- `above_max`

然后按字段分别定义策略。

### 8.1 年龄

- 低于下限：可 hard
- 高于上限：更适合 soft

### 8.2 身高

- 低于下限：可 soft/hard
- 高于上限：通常不应 hard

### 8.3 收入

- 低于下限：soft/hard
- 高于上限：只 soft/reference

### 8.4 学历

- 只处理“低于最低学历”
- 不需要“高于上限”概念


## 9. 结果集机制改造建议

### 9.1 当前问题

当前模式是：

- 严格规则过不了 -> 直接消失
- 只有 no-match 时才走 fallback


### 9.2 建议改成双池模型

建议在匹配阶段同时产出两个池子：

#### strict_pool

真正满足硬条件的候选人

#### compatible_pool

不满足部分软 reciprocal 条件，但仍然可聊的候选人


### 9.3 展示策略

建议：

- 默认优先展示 `strict_pool`
- 当 `strict_pool` 太少时，自动补入少量 `compatible_pool`
- 对兼容池候选人加明确标签

例如：

- `对方收入预期与你不完全一致`
- `对方城市偏好未命中，但资料写了接受异地`
- `对方对子女接受度偏保守，建议先确认`


### 9.4 目标效果

这样可以避免用户频繁看到：

- “没有匹配”

改成：

- “完全匹配的人少，但有一些可聊对象”


## 10. 数据模型改造建议

### 10.1 persona 层增加更明确的偏好强度字段

当前收入偏好字段只有：

- `target_income_min_wan`
- `target_income_max_wan`
- `preferred_income_strictness`（旧语义）

建议未来改成 persona 原生字段，例如：

- `target_income_preference_mode`

候选值：

- `hard_min`
- `target_band`
- `reference`

或者进一步拆成：

- `target_income_lower_bound_strength`
- `target_income_upper_bound_strength`


### 10.2 支持只设置收入下限

很多用户实际语义是：

- 至少到这个生活阶段

并不是：

- 绝对不能高于某个上限

因此系统应支持：

- 只填最低收入
- 上限可为空


### 10.3 区分“理想值”和“可接受范围”

建议未来将偏好拆成两层：

- `ideal_income_band`
- `acceptable_income_min`
- `acceptable_income_max`

同理也可扩展到年龄、身高、城市。

这样可以避免一个区间同时承担：

- 理想偏好
- 硬边界

这两种不同职责。


## 11. 代码改造建议

### 11.1 第一阶段：止血

目标：

- 优先解决收入高于上限被错杀的问题
- 降低“无匹配”发生率

建议改动：

- 修改 [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
  - 将收入判断从“是否重叠”改成“低于下限 / 命中 / 高于上限”
  - `高于上限` 不再走硬过滤
- 修改 [partner_search/search_no_match.py](/Users/sunmuchao/Downloads/Her/partner_search/search_no_match.py)
  - 让 no-match 解释更清楚地区分“硬不匹配”和“可放宽对象”
- 增加回归测试


### 11.2 第二阶段：规则标准化

目标：

- 统一 reciprocal 各区间字段的边界判断逻辑

建议改动：

- 为年龄、身高、收入引入统一边界判定函数
- 将 strictness 默认值按字段拆分，而不是全局共用
- 将 reciprocal 结果从二元结构扩展为多层结构


### 11.3 第三阶段：数据模型升级

目标：

- 让录入端语义与匹配引擎语义一致

建议改动：

- 在 persona 层增加更明确的偏好强度字段
- 逐步弱化旧 `preferred_*` 字段
- 更新 profile -> persona -> reciprocal 的映射逻辑


## 12. 推荐落地策略

如果只做一轮务实改造，建议优先落以下规则：

1. 收入高于对方上限：
   不再硬过滤
2. 收入低于对方下限：
   默认软扣分，只有明确 `hard` 才过滤
3. 收入 strictness 空值：
   默认按 `soft` 处理
4. fallback：
   不再只在 no-match 场景出现，应逐步纳入常规结果池
5. 结果展示：
   对“可聊但不完全命中”的候选人加明确标签和风险说明


## 13. 预期收益

本方案落地后，预期会带来以下收益：

1. 结果池更大
2. “假无匹配”明显减少
3. reciprocal 逻辑更符合真实相亲语义
4. 用户能看到更多“可聊对象”，而不是频繁空结果
5. 后续可以更平滑地从旧 profile 偏好迁移到 persona 偏好体系


## 14. 结论

当前系统的主要问题不是“不会排序”，而是“过滤过早、过滤过硬”。

尤其是收入区间：

- 现有逻辑把“高于上限”和“低于下限”都当成同一种不匹配
- 这会错误淘汰大量本可进入候选池的对象

因此，匹配逻辑应从“统一硬筛”升级为：

- 硬过滤
- 软扣分
- 风险提示
- fallback 候选池

其中最优先的一步是：

- 将收入从“默认硬筛条件”改造为“默认软约束条件”

这项改造可以作为整个匹配逻辑升级的第一步。
