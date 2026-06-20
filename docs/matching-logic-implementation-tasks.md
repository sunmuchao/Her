# 匹配逻辑改进落地任务拆分

## 1. 目标

将 [matching-logic-improvement-plan.md](/Users/sunmuchao/Downloads/Her/docs/matching-logic-improvement-plan.md) 拆分为可执行、可排期、可验收的落地任务。

本任务拆分遵循两个原则：

1. 先止血，再标准化，再升级数据模型
2. 每一阶段都能独立上线，并带来可观察收益


## 2. 任务分期

建议拆成 4 期：

1. P0：规则止血
2. P1：匹配引擎标准化
3. P2：结果展示与 fallback 升级
4. P3：数据模型升级与偏好体系重构


## 3. P0：规则止血

目标：

- 先解决“高收入被误杀”
- 减少“无匹配”空结果
- 不改大结构，优先修正最不合理规则

### Task P0-1：梳理当前 reciprocal 区间判断点

内容：

- 找出年龄、身高、学历、收入的 reciprocal 判断入口
- 确认哪些字段当前会因 strictness 为空而默认走 `hard`
- 输出一份当前行为对照表

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- [partner_search/search_inputs.py](/Users/sunmuchao/Downloads/Her/partner_search/search_inputs.py)

交付物：

- 一份当前 reciprocal 行为矩阵

验收标准：

- 明确列出年龄、身高、学历、收入在 `hard/soft/reference/空值` 下的行为


### Task P0-2：收入规则改为分方向判断

内容：

- 将收入判断从“区间是否重叠”改成：
  - `below_min`
  - `within_band`
  - `above_max`
  - `unknown`
- 不再把 `above_max` 和 `below_min` 视为同一种失败

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)

交付物：

- 新的收入边界判定函数
- reciprocal 收入逻辑切换到新判定函数

验收标准：

- `100w` 对 `30w-50w` 不再落入“和低于下限同等处理”


### Task P0-3：收入 `above_max` 取消默认硬过滤

内容：

- 修改 reciprocal 收入逻辑
- `above_max` 不再默认 `return fail(...)`
- 改为：
  - 打风险标记
  - 扣分
  - 保留进入排序结果

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)

交付物：

- 新的 reciprocal 收入失败判定策略

验收标准：

- 高于收入上限的候选人仍能进入结果集
- 且会带有明确风险标记


### Task P0-4：收入 strictness 空值改为按 `soft` 处理

内容：

- 不改全局 strictness 默认值
- 只对收入字段做单独策略
- 当 `preferred_income_strictness` 为空时：
  - 默认按 `soft`
  - 不再默认按 `hard`

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)

交付物：

- 收入字段特化 strictness 策略

验收标准：

- 未配置 strictness 的收入区间，不再直接造成 hard reject


### Task P0-5：补齐回归测试

内容：

- 增加收入 reciprocal 相关单测
- 覆盖以下场景：
  - 低于下限
  - 命中区间
  - 高于上限
  - strictness 为 hard
  - strictness 为空

建议测试位置：

- `tests/`
- `local-skills/partner-search/tests/`

交付物：

- 新增测试文件或扩展现有测试

验收标准：

- 新规则有自动化测试覆盖
- 旧问题可稳定复现并验证已修复


## 4. P1：匹配引擎标准化

目标：

- 不只修收入
- 统一各类区间字段的判断方式
- 把规则从“散点逻辑”收敛成统一框架

### Task P1-1：抽象区间边界判定工具

内容：

- 为年龄、身高、收入抽象统一边界判断函数
- 输出统一结果：
  - `below_min`
  - `within_range`
  - `above_max`
  - `unknown`

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- 也可新建 helper 模块

交付物：

- 通用边界判断工具函数

验收标准：

- 年龄、身高、收入不再各自维护重复边界逻辑


### Task P1-2：为不同字段定义独立策略矩阵

内容：

- 不再让年龄、身高、学历、收入共用同一套 strictness 语义
- 为每个字段定义：
  - 哪种情况可 hard reject
  - 哪种情况应 soft penalty
  - 哪种情况只做提醒

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)

交付物：

- 字段级 reciprocal 策略矩阵

验收标准：

- 字段策略可以被清晰枚举和测试，而不是散落在分支里


### Task P1-3：将 reciprocal 结果从二元改为多层

内容：

- 当前 reciprocal 结果基本只有：
  - fail
  - pass
- 需要增加中间层语义，例如：
  - `pass`
  - `pass_with_penalty`
  - `pass_with_warning`
  - `reject`

涉及文件：

- [partner_search/search_reciprocal.py](/Users/sunmuchao/Downloads/Her/partner_search/search_reciprocal.py)
- [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)

交付物：

- 更细粒度的 reciprocal 结果结构

验收标准：

- 可区分“完全命中”和“可聊但有偏差”


### Task P1-4：统一 reciprocal 风险标记和扣分映射

内容：

- 清理现有风险标记
- 为每类 reciprocal 偏差定义固定 penalty
- 明确哪些标记只提示、哪些标记明显降权

涉及文件：

- [partner_search/search_candidates.py](/Users/sunmuchao/Downloads/Her/partner_search/search_candidates.py)

交付物：

- 统一的 reciprocal 风险标记字典
- 对应 penalty 规则

验收标准：

- 同一类偏差在不同入口不会出现不一致扣分


## 5. P2：结果展示与 fallback 升级

目标：

- 不再只在 no-match 时显示“放宽后可聊对象”
- 让兼容候选人进入正常结果体系

### Task P2-1：引入 strict_pool / compatible_pool 双池模型

内容：

- 将当前结果集拆成：
  - `strict_pool`
  - `compatible_pool`
- 兼容池包含：
  - 命中硬条件
  - 但存在软 reciprocal 偏差的候选人

涉及文件：

- [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)
- [partner_search/search_no_match.py](/Users/sunmuchao/Downloads/Her/partner_search/search_no_match.py)
- 结果输出相关代码

交付物：

- 双池结果结构

验收标准：

- 系统能区分严格匹配与兼容匹配


### Task P2-2：调整结果返回结构

内容：

- 为候选人结果增加结构化字段，例如：
  - `match_tier`
  - `compatibility_flags`
  - `fallback_reason`
  - `reciprocal_gap_summary`

涉及文件：

- [partner_search/search_matching.py](/Users/sunmuchao/Downloads/Her/partner_search/search_matching.py)
- 排序/输出层

交付物：

- 新的候选结果 schema

验收标准：

- 前端或调用方可以直接区分“严格命中”与“有偏差但可聊”


### Task P2-3：优化 no-match 解释文案

内容：

- 将当前 no-match 结果区分为：
  - 真无候选
  - 有候选但全被硬规则过滤
  - 有兼容候选但无严格候选

涉及文件：

- [partner_search/search_no_match.py](/Users/sunmuchao/Downloads/Her/partner_search/search_no_match.py)

交付物：

- 更准确的 no-match 文案

验收标准：

- 不再把“有兼容候选”的场景直接呈现为纯空结果


### Task P2-4：前端/调用方展示兼容标签

内容：

- 在候选卡片或结果解释中显示：
  - `对方收入预期与你不完全一致`
  - `对方城市偏好未命中，但资料写了接受异地`
  - `对方对子女接受度偏保守`

交付物：

- 前端文案与展示策略

验收标准：

- 用户能理解为什么这个人还会被推荐出来


## 6. P3：数据模型升级

目标：

- 让产品录入语义和匹配语义一致
- 逐步摆脱旧 `preferred_*` 字段的限制

### Task P3-1：设计 persona 偏好强度新字段

内容：

- 为收入偏好设计更明确的 persona 字段
- 候选方案示例：
  - `target_income_preference_mode`
  - `target_income_lower_bound_strength`
  - `target_income_upper_bound_strength`

涉及文件：

- persona schema
- migration
- profile/persona 编译逻辑

交付物：

- 字段设计文档
- migration 方案

验收标准：

- 能表达“理想区间”和“硬边界”不是一回事


### Task P3-2：支持只配置下限、不配置上限

内容：

- 更新录入和编译逻辑
- 支持：
  - 只有收入下限
  - 没有收入上限

涉及文件：

- persona 写入逻辑
- compiled criteria 构建逻辑

交付物：

- 新的偏好录入支持

验收标准：

- 用户可以表达“至少达到某阶段”，而不是被迫填写上限


### Task P3-3：区分理想偏好与可接受范围

内容：

- 将“理想值”和“可接受值”拆层
- 可先从收入开始，后续扩展到年龄、身高、城市

交付物：

- 新偏好模型设计

验收标准：

- 一个字段不再同时承担“理想偏好”和“硬边界”两个职责


### Task P3-4：重写 legacy reciprocal 映射策略

内容：

- 当前 reciprocal 仍依赖旧 `preferred_*` 语义
- 需要逐步改为：
  - persona 原生字段直接参与 reciprocal
  - legacy 映射仅做兼容过渡

涉及文件：

- [match_domain/deprecated_profile_columns.py](/Users/sunmuchao/Downloads/Her/match_domain/deprecated_profile_columns.py)
- [match_domain/reciprocal_preferences.py](/Users/sunmuchao/Downloads/Her/match_domain/reciprocal_preferences.py)

交付物：

- 新旧字段兼容策略

验收标准：

- reciprocal 逻辑不再被旧 profile 偏好字段绑定


## 7. 产品任务

### Task PRD-1：明确哪些条件属于硬条件

内容：

- 与产品确认：
  - 性别
  - 婚况
  - 孩子
  - 异地
  - 抽烟喝酒
  - 年龄
  - 收入
  - 学历
  - 身高
  中哪些字段默认硬、哪些默认软

交付物：

- 字段分层规则表

验收标准：

- 研发实现不再依赖猜测业务语义


### Task PRD-2：定义“可聊对象”的产品语义

内容：

- 明确以下问题：
  - 什么叫“兼容候选”
  - 是否允许默认混入结果
  - 兼容候选显示比例是多少
  - 兼容候选如何打标签

交付物：

- 兼容候选产品规则

验收标准：

- 前后端对结果结构和展示一致理解


## 8. 测试任务

### Task QA-1：构建区间类回归用例集

内容：

- 为年龄、身高、收入建立回归测试矩阵
- 每个字段覆盖：
  - 低于下限
  - 命中区间
  - 高于上限
  - strictness = hard
  - strictness = soft
  - strictness = reference
  - strictness 为空

交付物：

- 区间规则测试集

验收标准：

- 区间逻辑改造后不引入回归


### Task QA-2：构建真实业务场景样例

内容：

- 构造典型业务样例：
  - 高收入 vs 低上限
  - 异地可协商
  - 婚史谨慎接受
  - 子女情况未知
- 验证最终结果是否符合业务预期

交付物：

- 业务场景验收样例

验收标准：

- 规则结果可被产品和运营直观验收


## 9. 推荐排期

建议排期如下：

### 第一周

- P0-1
- P0-2
- P0-3
- P0-4
- P0-5

目标：

- 快速止血


### 第二周

- P1-1
- P1-2
- P1-3
- P1-4

目标：

- 把 reciprocal 区间规则收敛成统一框架


### 第三周

- P2-1
- P2-2
- P2-3
- P2-4

目标：

- 让“兼容候选”真正进入常规结果体系


### 第四周及以后

- P3-1
- P3-2
- P3-3
- P3-4

目标：

- 完成偏好数据模型升级


## 10. 最小可上线版本

如果资源有限，最小可上线版本建议只做以下 5 个任务：

1. P0-2：收入分方向判断
2. P0-3：高于上限取消默认硬过滤
3. P0-4：收入 strictness 空值按 soft
4. P0-5：补回归测试
5. P2-3：优化 no-match 文案

这 5 项可以最小成本解决当前最明显的问题。


## 11. 结论

本次改造不建议一次性大改。

更合适的推进方式是：

1. 先修最不合理的收入硬筛问题
2. 再统一 reciprocal 区间规则
3. 再把“兼容候选”正式纳入结果体系
4. 最后再升级 persona 偏好模型

这样每一阶段都可独立交付，也更容易控制风险。
