# 聊天助手改进方案整理与落地任务拆解

本文档是对 [chat-assistant-improvement-plan.md](chat-assistant-improvement-plan.md) 的执行化整理，目标有两个：

- 先把原方案压缩成清晰的主线
- 再把主线拆成可排期、可开发、可验收的任务

---

## 1. 文档整理

### 1.1 这份方案其实分成两条线

**主线 A：线上聊天教练助手**

- 面向真实聊天用户
- 助手的职责是判断局势、给建议、提醒风险
- 助手不是代聊，不直接决定用户下一句怎么发

**主线 B：线下见面型红娘助手**

- 面向见面中和见面后的辅助判断
- 职责是破冰、观察、轻量回场、误会澄清、关系分流
- 这是后续扩展方向，不应和主线 A 混在同一阶段开发

当前应该优先落地的是**主线 A**。

### 1.2 主线 A 的一句话定义

把助手从“看到冷场就给点泛泛建议”，升级成“先判断局势，再给有分寸的方向性建议，并且能被正确评估”的聊天教练系统。

### 1.3 主线 A 的产品边界

- 助手是教练，不是嘴替。
- 助手可以影响用户，但不能控制用户。
- 助手输出的是建议，不是控制信号。
- 对真实产品，`interaction_mode` 只约束助手自己的建议输出，不约束用户回复。
- 对 `roleplay / 压测`，可以让模拟 agent 读取 `interaction_mode` 做离线实验，但这不代表线上产品会干预真人用户。

### 1.4 方案的核心判断模型

先判断局面属于哪一类：

- `communication_problem`
- `interest_unclear`
- `interest_low / boundary_risk`

再映射成四种处理模式：

- `repair`
- `probe_lightly`
- `hold`
- `none`

这套模式是整份方案的核心中轴，后续的提示、评测、压测、延迟治理都围绕它展开。

### 1.5 当前最主要的问题

- 该出手时出手太少，出手也偏晚
- 助手能指出问题，但建议不够具体，用户执行率不稳定
- 建议不够贴画像，容易泛化成通用聊天课
- 主对话生成还有解释腔、分析腔，不够像真人
- 系统分不清“不会聊”和“没兴趣”
- 提示链路太慢，真实产品里来不及用
- 评测口径太粗，容易把“没救活聊天”和“助手无效”混为一谈
- 真实产品里缺少“用户是否采纳建议”的评估
- `roleplay` 压测里缺少“模拟回复是否按模式输出”的单独评估

### 1.6 目标架构的本质

目标不是“做一个更会聊天的模型”，而是把系统拆成几层：

1. 看懂局势
2. 判定模式
3. 生成建议
4. 决定要不要提示
5. 评估建议有没有被采纳、局面有没有变好

对真实产品来说，最终落点是**建议层和评测层**。

对 `roleplay` 来说，额外还会有一个**模拟回复层**，用于离线验证策略是否可执行。

### 1.7 评测口径的真正变化

从过去的：

- 最后有没有聊成

改成后续的：

- 判得准不准
- 出手时机对不对
- 建议是否具体、可执行、符合人设
- 用户是否采纳
- 建议后 `1-3` 轮有没有局部改善
- 不该继续推进时，有没有做到体面止损

### 1.8 实施优先级结论

当前不应该先做“更多建议模板”，而应该先做下面四件事：

1. 把 `repair / probe_lightly / hold` 判准
2. 把助手输出改成可落库、可评测的结构化建议
3. 把延迟压到真实聊天可用
4. 把“建议质量”和“用户是否采纳”分开评估

人设化建议、口语自然度、提示触发优化，都应该放在这个基础之后。

---

## 2. 落地拆分原则

### 2.1 先做基础设施，再做效果优化

建议顺序：

1. 数据结构和评测字段
2. 模式判断和结构化输出
3. 延迟与链路埋点
4. 跟随度与局部恢复评估
5. 人设化与自然度优化
6. 提示触发策略
7. 线下见面型助手单独立项

### 2.2 不要把真实产品和 roleplay 压测混成一套逻辑

产品逻辑关注：

- 助手怎么判断
- 助手怎么提示
- 用户有没有采纳

压测逻辑关注：

- 模拟 agent 是否按模式输出
- 离线评测能否稳定复现问题

同一个 `interaction_mode` 可以同时服务这两条线，但验收口径必须分开。

---

## 3. 具体落地任务

### T01：统一术语、字段和边界定义

- 优先级：`P0`
- 目标：把文档里的模式、字段、边界统一成一套实现语言，避免研发各自理解。
- 产出：
  - 明确 `mutual_intent_assessment`、`interaction_mode`、`follow_level`、`assistant_mode_compliance` 等字段定义
  - 明确“真实产品”和“roleplay 压测”的边界说明
  - 输出一版结构化字段说明，供后续代码和评测复用
- 主要文件：
  - [docs/chat-assistant-improvement-plan.md](/Users/sunmuchao/Downloads/Her/docs/chat-assistant-improvement-plan.md)
  - [docs/chat-assistant-improvement-task-breakdown.md](/Users/sunmuchao/Downloads/Her/docs/chat-assistant-improvement-task-breakdown.md)
  - 可选新增：`external-systems/partner-chat-system/chat_system/types.py`
- 依赖：无
- 完成标准：
  - 所有核心字段都有统一定义
  - 文档里不再出现“助手直接约束真实用户回复”的模糊表述

### T02：补齐 `StressBeat` 的弱标注字段

- 优先级：`P0`
- 目标：让压测场景天然带有可评测的 gold 元数据。
- 产出：
  - 为每个 `StressBeat` 增加 `severity`
  - 增加 `expected_problem_tags`
  - 增加 `suggested_strategy_tags`
  - 增加 `expected_need_rescue_after_turns`
  - 增加 `expected_mutual_intent_assessment`
  - 增加 `expected_interaction_mode`
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/scenario_stress.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/scenario_stress.py)
  - 相关测试：`external-systems/partner-chat-system/tests`
- 依赖：`T01`
- 完成标准：
  - 所有现有压力剧情都能导出上述元数据
  - 压测脚本可以读取这些字段，不再只依赖自然语言场景描述

### T03：定义每轮评测记录结构

- 优先级：`P0`
- 目标：把“一个可能需要救场的时刻”固化成结构化记录。
- 产出：
  - 每轮记录 schema
  - 至少包含 `turn_index`、`interaction_mode_gold/pred`、`follow_level`、`recovery_score_1to3_turns`、`graceful_exit_score`
  - 区分真实产品字段和 `roleplay` 专用字段
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
- 依赖：`T01`
- 完成标准：
  - 压测运行后能产出逐轮结构化记录
  - 字段不再散落在日志字符串中

### T04：实现一级轻判断模块

- 优先级：`P0`
- 目标：先把“什么时候该出手”做成快速、稳定的前置判断。
- 产出：
  - 基于规则的快路径
  - 小模型或轻判断逻辑
  - 输出 `need_rescue`、`problem_tags`、`interaction_mode`
- 主要文件：
  - 可新增：`external-systems/partner-chat-system/chat_system/mode_router.py`
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
- 依赖：`T02`、`T03`
- 完成标准：
  - 能区分 `repair / probe_lightly / hold / none`
  - 有规则覆盖一字回复、终结语、连续低投入、敏感话题等场景
  - 能单独统计轻判断耗时

### T05：改造 `assistant_llm.py` 为结构化建议输出

- 优先级：`P0`
- 目标：把助手从纯文本建议改成“结构化 JSON + 人类可读文案”。
- 产出：
  - 结构化字段输出
  - JSON 解析与校验
  - 安全 fallback
  - 禁止直接生成可原样直发的代写句
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
  - [external-systems/partner-chat-system/tests/test_assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_assistant_llm.py)
- 依赖：`T01`、`T04`
- 完成标准：
  - 输出稳定包含 `mutual_intent_assessment`、`interaction_mode`、`problem_tags`、`advice`、`avoid`
  - 非 `repair` 模式下会说明“为什么别硬推”
  - 测试能覆盖 schema 缺失、JSON 解析失败、fallback 生效

### T06：补齐服务层落库与埋点

- 优先级：`P0`
- 目标：把助手建议、延迟、采纳证据变成可追踪数据。
- 产出：
  - 保存结构化建议
  - 记录各阶段耗时
  - 保留 `follow_evidence`、`overpush_risk` 等字段入口
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/tests/test_chat_system.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_chat_system.py)
- 依赖：`T03`、`T05`
- 完成标准：
  - 结构化建议能持久化或稳定输出到结果对象
  - 能区分轻判断耗时和重建议耗时

### T07：实现用户采纳度评估

- 优先级：`P0`
- 目标：把“建议好不好”和“用户有没有照做”拆开。
- 产出：
  - `followed_assistant`
  - `follow_level = none | partial | strong`
  - `follow_evidence`
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py)
- 依赖：`T05`、`T06`
- 完成标准：
  - 能判断是否换到了建议话题类型
  - 能判断是否避免了明确禁止动作
  - 结果里能单独输出采纳率

### T08：实现局部恢复、止损与过推指标

- 优先级：`P0`
- 目标：让评测不再只看“整段聊没聊成”。
- 产出：
  - `recovery_score_1to3_turns`
  - `graceful_exit_score`
  - `overpush_risk_turns`
  - `clarified_low_interest_rate`
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py)
- 依赖：`T03`、`T07`
- 完成标准：
  - 报表里能区分“局部改善”和“体面止损”
  - `interest_low / boundary_risk` 场景可以单独统计是否被误推

### T09：实现 `roleplay` 模式对齐实验

- 优先级：`P1`
- 目标：只在离线压测里验证“模式建议是否可执行”。
- 产出：
  - 一个开关，控制模拟 agent 是否读取 `interaction_mode`
  - 一组对比结果：读模式 vs 不读模式
  - `simulated_reply_mode_alignment_rate`
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py)
- 依赖：`T04`、`T05`
- 完成标准：
  - 可以明确区分“真实产品建议边界”和“离线模拟约束实验”
  - 结果导出时带上实验开关状态

### T10：实现画像钩子排序与上下文裁剪

- 优先级：`P1`
- 目标：让建议更像这个人会真的聊出来的方向。
- 产出：
  - 安全裁剪的画像摘要
  - 双方交集钩子优先
  - 当前说话人真实生活钩子次优先
  - 通用低门槛话题兜底
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
  - 可选关联：`external-systems/partner-chat-system/tests/test_profile_loader.py`
- 依赖：`T05`
- 完成标准：
  - 输出中能记录 `profile_hooks_used`
  - 建议不再默认回退到电影、旅行、运动等泛话题

### T11：改造主对话口语自然度

- 优先级：`P1`
- 目标：降低解释腔、分析腔、模板腔。
- 产出：
  - 更新 `persona prompt`
  - 增加反例表达约束
  - 增加口语自然度评分
- 主要文件：
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/tests/test_dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_dyadic_roleplay.py)
- 依赖：无
- 完成标准：
  - 输出里能单独看到自然度评分
  - 典型分析腔句式被列入反例并能被压低

### T12：实现提示触发器与重复提示抑制

- 优先级：`P1`
- 目标：后台逐句看，前台只在还能明显帮助沟通时按趋势提醒。
- 产出：
  - 产品原则：**帮助沟通，不帮助硬撑**
  - 产品边界：
    - 只作用于系统主动提示，不影响用户主动询问助手
    - 只生成 `owner_only` 教练建议，不自动改写用户消息、不代发、不拦截发送
  - 实现铁律：
    - `repair`：顺水推舟。双方仍有沟通意愿但这轮卡住时，允许积极提醒，帮助把沟通拉顺。
    - `probe_lightly`：只轻扶，不猛推。看不清对方意愿时，只允许低压、低频提醒。
    - `hold`：见好就收。只做止损型轻提醒，不以“把聊天继续维持下去”为目标。
    - `normal`：别添乱。聊天本身顺的时候默认不提示。
  - 趋势状态器：记录上一模式、上次提示时点、持续未缓解轮数、风险等级、上次提示原因
  - 建议状态字段：`current_mode`、`previous_mode`、`same_mode_turns`、`unresolved_turns`、`risk_flags`、`last_hint_turn`、`last_hint_mode`、`last_hint_reason`、`last_hint_trigger_type`、`last_hint_follow_level`、`has_user_acted_since_last_hint`、`cooldown_until_turn`
  - 模式分层触发规则：`repair` 可相对积极提醒，`probe_lightly` 只做低频提醒，`hold` 默认只做止损型轻提醒
  - 首次触发规则：`normal -> repair`、`normal -> probe_lightly`、`probe_lightly -> hold`、`repair -> hold`、风险升级
  - 再触发规则：只有在再次提示仍有新增价值时才允许触发，例如沟通问题仍可修复但连续数轮未缓解、风险明显升级、冷却窗口后仍无改善
  - 重复提示抑制：刚提示过、状态未变、严重度未升高、用户还没来得及行动时不重复
  - `follow_level / follow_evidence` 只作为“提示是否仍有新增价值”的辅助信号，不作为监督用户是否听话的主目标
  - 建议提示事件字段：`turn_index`、`speaker`、`mode_before`、`mode_after`、`trigger_type`、`suppression_reason`、`hint_posted`、`risk_flags`、`last_hint_turn_gap`
  - `hint_trigger_rate`、`duplicate_hint_rate`、`mode_change_hint_rate`
- 主要文件：
  - 可新增：`external-systems/partner-chat-system/chat_system/trend_state.py`
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
  - [external-systems/partner-chat-system/tests/test_chat_system.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_chat_system.py)
  - [external-systems/partner-chat-system/tests/test_dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_dyadic_roleplay.py)
- 依赖：`T04`、`T05`
- 联动增强：`T07` 可提供 `follow_level` 作为辅助信号
- 建议实现步骤：
  1. 抽出 `trend_state.py`，实现状态更新、重复提示抑制、触发决策三个纯函数
  2. 在 `service.py` 中把主动提示入口改成“先更新趋势状态，再决定是否提示”
  3. 在 `dyadic_roleplay.py` 中复用同一套触发逻辑，输出 `trigger_type / suppression_reason / hint_posted`
  4. 在导出结果中增加 `hint_trigger_rate / duplicate_hint_rate / mode_change_hint_rate / hold_repeat_hint_rate`
  5. 补齐 `repair / probe_lightly / hold / normal` 四类回归测试
- 完成标准：
  - 没有新信息时不复读，但在“仍值得帮忙”的窗口里允许再次提示
  - 能区分首次触发、风险升级触发、持续未缓解但仍可修复的再触发
  - `hold` 场景默认不连续提示，除非风险继续升级或用户继续明显越界
  - `normal` 场景默认不打断，`repair` 场景提醒最积极，`probe_lightly` 次之，`hold` 最克制
  - 用户主动询问助手时，不受 `T12` 冷却和去重规则影响
  - 至少覆盖以下验收样例：
    - `normal -> repair` 触发一次；下一轮同模式默认不重复
    - `repair` 连续 `2` 轮未缓解、用户已行动、冷却结束后可再触发
    - `normal -> probe_lightly` 触发一次；相邻轮次默认不复读
    - 首次进入 `hold` 触发一次；稳定 `hold` 不重复；风险升级时可再触发
  - 能统计重复提示率

### T13：补齐运行脚本和导出报表

- 优先级：`P1`
- 目标：让压测结果可以直接看，不需要人工翻日志。
- 产出：
  - 识别准确率
  - 建议质量分
  - 用户采纳率
  - 局部恢复率
  - 延迟统计
  - `repair / probe_lightly / hold` 分布
- 主要文件：
  - [external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/scripts/run_dyadic_agent_roleplay.py)
  - [external-systems/partner-chat-system/scripts/export_chat_thread.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/scripts/export_chat_thread.py)
- 依赖：`T03`、`T06`、`T07`、`T08`
- 完成标准：
  - 跑完脚本后能直接看到关键指标
  - 导出结果能把主对话、助手建议、评测摘要分区展示

### T14：建立回归测试和验收基线

- 优先级：`P0`
- 目标：让后续改动不会把边界、时机或输出格式改坏。
- 产出：
  - 结构化输出测试
  - 模式判断测试
  - 采纳度评测测试
  - 延迟统计回归基线
- 主要文件：
  - [external-systems/partner-chat-system/tests/test_assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_assistant_llm.py)
  - [external-systems/partner-chat-system/tests/test_dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_dyadic_roleplay.py)
  - [external-systems/partner-chat-system/tests/test_chat_system.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_chat_system.py)
- 依赖：`T04`、`T05`、`T06`
- 完成标准：
  - 关键结构字段有测试
  - `repair / probe_lightly / hold` 至少各有回归样例
  - 明确代写违规率可被测试覆盖

### T15：线下见面型红娘助手单独立项

- 优先级：`P2`
- 目标：把第 18 节从“理念说明”变成独立需求，不与线上聊天教练混开发。
- 产出：
  - 单独 PRD 或设计文档
  - 见面中状态机
  - 见面后关系分流规则
  - 单独成功指标
- 主要文件：
  - 建议新增独立文档，不与当前聊天助手方案混写
- 依赖：无
- 完成标准：
  - 明确和线上聊天教练的职责分界
  - 排期上不占用当前主线 A 的 P0 / P1 资源

---

## 4. 建议排期

### 第一阶段：先把底盘搭起来

建议先做：

- `T01` 统一术语、字段和边界
- `T02` 补齐 `StressBeat` 弱标注
- `T03` 定义每轮评测记录结构
- `T04` 实现一级轻判断模块
- `T05` 结构化建议输出
- `T06` 服务层落库与埋点
- `T14` 回归测试和验收基线

阶段目标：

- 先把“判什么、怎么记、怎么测”做稳

### 第二阶段：把评测做对

建议再做：

- `T07` 用户采纳度评估
- `T08` 局部恢复、止损与过推指标
- `T13` 运行脚本和导出报表

阶段目标：

- 能分清“建议质量问题”与“用户没采纳”

### 第三阶段：把效果和体验做起来

建议再做：

- `T09` `roleplay` 模式对齐实验
- `T10` 画像钩子排序
- `T11` 口语自然度改造
- `T12` 提示触发器与重复提示抑制

阶段目标：

- 让建议更像人话、更像这个人、更像真实产品里的提示

### 第四阶段：单独推进线下红娘助手

建议最后做：

- `T15` 线下见面型红娘助手单独立项

阶段目标：

- 不让第二条产品线打乱当前聊天助手主线

---

## 5. 推荐的最小闭环

如果当前只做一个最小可落地版本，建议范围是：

- `T01` + `T02` + `T03` + `T04` + `T05` + `T06` + `T07` + `T08` + `T14`

做完这批之后，系统至少可以回答下面几个关键问题：

- 这轮到底该不该介入
- 该介入时应该给哪种模式的建议
- 建议有没有结构化输出
- 用户有没有采纳
- 采纳后局面有没有局部变好
- 不该救的时候有没有避免乱推

这才是后续继续打磨人设化、自然度和提示体验的基础。

---

*文档版本：2026-05-06。后续如果原方案文档继续变更，这份任务拆解也需要同步更新。*
