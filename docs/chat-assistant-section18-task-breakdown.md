# 第18部分任务拆解（基于当前 AI 助手能力）

本文档把 [`chat-assistant-improvement-plan.md`](./chat-assistant-improvement-plan.md) 第 18 部分拆成具体任务，并以当前系统真实能力为前提来排优先级。

当前助手的现实定位是：

- 一个**聊天中回温教练**
- 主要处理 `communication_problem -> repair`
- 不负责完整的“推进 / 澄清 / 结束”关系分流

因此，第 18 部分的落地方式不应该是“直接把现有回温链路改成全能助手”，而应该是：

1. 保住现有回温能力
2. 新增聊天前能力
3. 新增聊天后能力
4. 最后再把它们串成全流程助手

---

## 1. 拆分原则

### 1.1 不要直接推翻当前回温链路

当前 `mode_router + proactive hint + assistant_query` 已经形成了“聊天中回温”闭环。

第 18 部分新增能力时，优先原则是：

- 不破坏当前 `repair / none` 主链路
- 不强行把“聊天前 / 聊天后”逻辑塞进当前 `mode_router`
- 不把“关系分流”一步到位压到当前回温判断里

### 1.2 先做阶段化入口，再做阶段化智能

先让系统明确知道自己正在处理的是：

- `pre_chat`
- `in_chat`
- `post_chat`

再分别为三个阶段补能力。

### 1.3 先做结构化结果，再做自动化触发

建议顺序是：

1. 先支持手动触发
2. 先输出结构化结论
3. 结论稳定后，再做自动弹出和自动时机判断

---

## 2. 分阶段任务总览

### Phase A：补齐阶段化骨架

- `S18-T01` 定义阶段模型与结构化字段
- `S18-T02` 增加聊天前 / 聊天后服务入口
- `S18-T03` 增加阶段化结果存储与时间线返回

### Phase B：补齐聊天前能力

- `S18-T04` 实现聊天前上下文整理器
- `S18-T05` 实现开场建议生成器
- `S18-T06` 实现开场风险预判器

### Phase C：补齐聊天后能力

- `S18-T07` 实现聊后复盘入口
- `S18-T08` 实现推进 / 澄清 / 结束三分流判断
- `S18-T09` 实现澄清建议模块

### Phase D：补齐经验沉淀与评估

- `S18-T10` 实现结构化失败原因沉淀
- `S18-T11` 实现第 18 部分专属指标
- `S18-T12` 实现自动触发策略

---

## 3. 具体任务

### S18-T01：定义阶段模型与结构化字段

- 优先级：`P0`
- 目标：让系统正式拥有“聊天前 / 聊天中 / 聊天后”的概念。
- 产出：
  - 增加阶段字段，例如 `assistant_stage`
  - 明确三个阶段：`pre_chat`、`in_chat`、`post_chat`
  - 定义第 18 部分新增结构化字段
  - 定义聊后分流结果字段：`advance`、`clarify`、`end`
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/assistant_contract.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_contract.py)
  - [docs/chat-assistant-improvement-plan.md](/Users/sunmuchao/Downloads/Her/docs/chat-assistant-improvement-plan.md)
  - [docs/chat-assistant-section18-gap-analysis.md](/Users/sunmuchao/Downloads/Her/docs/chat-assistant-section18-gap-analysis.md)
- 完成标准：
  - 文档和代码使用同一套阶段术语
  - 能明确区分“回温建议字段”和“聊后复盘字段”

### S18-T02：增加聊天前 / 聊天后服务入口

- 优先级：`P0`
- 目标：让第 18 部分能力有独立入口，而不是全部复用 `assistant_query`。
- 产出：
  - 新增“聊天前准备”服务入口
  - 新增“聊天后复盘”服务入口
  - 保留现有 `assistant_query` / `assistant_proactive_hint` 作为聊天中入口
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/__init__.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/__init__.py)
- 完成标准：
  - 能独立调用“聊天前准备”
  - 能独立调用“聊天后复盘”
  - 不需要伪造一段进行中的 dyadic 对话才能触发这两类能力

### S18-T03：增加阶段化结果存储与时间线返回

- 优先级：`P0`
- 目标：让“准备结果”和“复盘结果”能被存下来，而不是只出现在临时响应里。
- 产出：
  - 新增阶段化结果落库结构
  - `timeline` 能返回最近一次聊天前准备结果
  - `timeline` 能返回最近一次聊天后复盘结果
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/timeline.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/timeline.py)
  - 可新增：`chat_assistant_stage_results` 表或等价存储结构
- 完成标准：
  - 结果不是只存在日志或一次性响应里
  - 同一个 case 能看到最近的准备 / 复盘结论

### S18-T04：实现聊天前上下文整理器

- 优先级：`P1`
- 目标：在开聊前，把双方画像和必要背景整理成可用于建议的输入。
- 产出：
  - 提炼共同点
  - 提炼低门槛开场钩子
  - 提炼明显风险点
  - 过滤不适合作为开场的话题
- 建议文件：
  - 可新增：`external-systems/partner-chat-system/chat_system/pre_chat_context.py`
  - [external-systems/partner-chat-system/chat_system/profile_loader.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/profile_loader.py)
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
- 完成标准：
  - 聊天前输入不再只是“双方画像原文”
  - 能稳定提炼出 2 到 3 个自然开场方向

### S18-T05：实现开场建议生成器

- 优先级：`P1`
- 目标：让聊天前阶段能输出“怎么开始更自然”的建议。
- 产出：
  - 开场方向建议
  - 开场禁忌提醒
  - 第一轮节奏提醒
  - 期待校准提醒
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
  - 可新增：`external-systems/partner-chat-system/chat_system/pre_chat_llm.py`
- 完成标准：
  - 输出不是代写整句
  - 至少包含“可聊切口 + 避免事项 + 开场策略”
  - 结果更像“准备建议”，而不是“聊天中修复建议”

### S18-T06：实现开场风险预判器

- 优先级：`P1`
- 目标：在聊天前就识别容易出问题的话题和问法。
- 产出：
  - 查户口风险识别
  - 边界压力识别
  - 高门槛开场识别
  - 画像差异点预警
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/mode_router.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/mode_router.py)
  - 可新增：`external-systems/partner-chat-system/chat_system/pre_chat_rules.py`
- 完成标准：
  - 能在开聊前给出风险提醒
  - 这些提醒不依赖对方已经回过消息

### S18-T07：实现聊后复盘入口

- 优先级：`P0`
- 目标：让系统正式支持“聊完之后再看一遍”。
- 产出：
  - 手动触发的聊后复盘入口
  - 能读取最近一段 dyadic 对话
  - 能生成复盘型 owner-only 结果
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/summaries.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/summaries.py)
- 完成标准：
  - 用户不需要等聊天中再次卡住才能得到判断
  - 复盘入口和聊天中回温入口职责分开

### S18-T08：实现推进 / 澄清 / 结束三分流判断

- 优先级：`P0`
- 目标：把第 18 部分最核心的“关系分流”做成结构化输出。
- 产出：
  - 三类结果：`advance`、`clarify`、`end`
  - 每类结果对应的判断理由
  - 每类结果对应的低级别证据
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
  - 可新增：`external-systems/partner-chat-system/chat_system/post_chat_review.py`
  - [external-systems/partner-chat-system/chat_system/assistant_contract.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_contract.py)
- 完成标准：
  - 复盘结果不再只是一段自然语言建议
  - 能明确区分“还能推进”和“主要该澄清”

### S18-T09：实现澄清建议模块

- 优先级：`P1`
- 目标：把“误会但还有机会”做成独立能力，而不是混在 repair 里。
- 产出：
  - 澄清场景判定
  - 澄清目标说明
  - 下一步澄清建议
  - 澄清时避免事项
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/assistant_llm.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_llm.py)
  - 可新增：`external-systems/partner-chat-system/chat_system/clarify_strategy.py`
- 完成标准：
  - “澄清”不再只是文案描述
  - 能和“继续推进”明确区分开

### S18-T10：实现结构化失败原因沉淀

- 优先级：`P1`
- 目标：把“为什么没聊成”沉淀成可统计、可复用的数据。
- 产出：
  - 失败原因分类
  - 每次复盘输出 1 到 2 个主因
  - 支持后续统计高频失败原因
- 建议文件：
  - 可新增：`external-systems/partner-chat-system/chat_system/review_taxonomy.py`
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
  - [external-systems/partner-chat-system/chat_system/reporting.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/reporting.py)
- 完成标准：
  - 结果不只是“结束了”
  - 能知道是开场方式问题、节奏问题、误会问题还是低意愿问题

### S18-T11：实现第18部分专属指标

- 优先级：`P1`
- 目标：让第 18 部分能力可以被单独评估。
- 产出：
  - 开场自然度指标
  - 澄清成功率
  - 提前止损率
  - 聊后分流准确率
  - 用户是否觉得判断更准确的指标
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/reporting.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/reporting.py)
  - [external-systems/partner-chat-system/chat_system/dyadic_roleplay.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/dyadic_roleplay.py)
- 完成标准：
  - 第 18 部分能力有单独指标
  - 不再只看聊没聊成

### S18-T12：实现自动触发策略

- 优先级：`P2`
- 目标：在结构化结果稳定后，再补自动触发。
- 产出：
  - 聊天前自动建议触发规则
  - 聊天后自动复盘触发规则
  - 不打扰用户的节制策略
- 建议文件：
  - [external-systems/partner-chat-system/chat_system/trend_state.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/trend_state.py)
  - [external-systems/partner-chat-system/chat_system/service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py)
- 完成标准：
  - 自动触发不影响当前聊天中回温逻辑
  - 不会因为加了聊天前 / 聊天后能力导致提示泛滥

---

## 4. 推荐开发顺序

如果只按“先把第 18 部分做成最小可用版本”来看，建议顺序如下：

1. `S18-T01` 定义阶段字段和结构化结果
2. `S18-T02` 增加聊天前 / 聊天后入口
3. `S18-T07` 做聊后复盘入口
4. `S18-T08` 做推进 / 澄清 / 结束三分流
5. `S18-T04` + `S18-T05` 做聊天前准备能力
6. `S18-T09` 做澄清模块
7. `S18-T03` + `S18-T10` 做存储和经验沉淀
8. `S18-T11` + `S18-T12` 做指标和自动触发

---

## 5. 最小可用版本定义

第 18 部分最小可用版本，不要求一步到位做成“全自动全流程助手”，只要求做到：

- 用户可以手动触发一次“聊天前准备”
- 用户可以手动触发一次“聊天后复盘”
- 复盘结果能明确分成 `推进 / 澄清 / 结束`
- 结果可以被存下来并返回到时间线

做到这四件事，就说明第 18 部分已经从“文档想法”进入“产品能力”。

---

*文档版本：2026-05-07。若后续助手边界、阶段定义或现有回温链路发生变化，应同步更新本文档。*
