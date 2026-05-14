# 第18部分改进方案（基于 2026-05-09 live 验证）

本文档不是泛泛而谈的“优化建议”，而是基于这次 live 验证后的实际结论，整理一份更可执行的改进方案。

目标只有一个：

- 让红娘 C 从“能在部分场景给建议”，升级到“更稳定地具备第 18 部分能力”。

---

## 1. 先说结论

当前最该做的，不是继续把 prompt 写得更花，而是把红娘 C 从一个“通用建议器”拆成三个明确阶段：

- `聊天前准备`
- `聊天中判断`
- `聊天后复盘`

大白话就是：

- 现在它最大的问题，不是一句话说得不够漂亮
- 而是职责还没拆清楚，入口也没拆清楚，结果更没存清楚

所以改进顺序建议是：

1. 先补 `聊后复盘 + 三分流 + 结构化存储`
2. 再补 `聊天前准备`
3. 再补 `聊天中更细的状态判断和退后策略`
4. 最后补 `经验沉淀 + 回归评测`

---

## 2. 改进原则

### 2.1 不要只改 prompt

当前运行时约束还很通用，`assistant_runtime.py` 里只是要求“判断要不要回、回哪个渠道、给简短建议”，见：

- [assistant_runtime.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_runtime.py:326)

这会导致：

- 它能给建议
- 但不等于它天然知道自己现在是在“聊天前”“聊天中”还是“聊天后”

所以：

- `prompt 要改`
- 但 `入口、结构、存储、评测` 更要改

### 2.2 不要推翻现有聊天中链路

当前系统已经有一套能跑的聊天中链路：

- `assistant_context.py`
- `assistant_runtime.py`
- `assistant_orchestrator.py`
- `assistant_sessions.py`

这套链路现在至少已经能做：

- 中途介入
- 节奏提醒
- 风险提醒

所以不建议：

- 直接把现有链路推翻重写

更合适的是：

- 保住现有聊天中能力
- 在它外面补 `聊天前` 和 `聊天后` 独立入口
- 再把三段串起来

### 2.3 先做结构化结果，再做自动触发

如果连结果都没有结构化，后面就没法判断到底有没有做好。

所以顺序要是：

1. 先支持手动触发
2. 先产出结构化结果
3. 再做自动弹出、自动介入和自动时机判断

---

## 3. 优先级总表

| 优先级 | 改进项 | 为什么先做 |
|---|---|---|
| `P0` | 聊后复盘入口 + `推进/澄清/结束` 三分流 + 结果存储 | 这是当前最大缺口，也是第 18 部分最关键的闭环 |
| `P0` | 阶段模型与统一输出 schema | 不先拆阶段，后面所有能力都会继续混在一起 |
| `P1` | 聊天前准备器 | 这是 `18.2` 最大短板，且对体验提升最直接 |
| `P1` | 聊天中状态细分 + 退后策略 | 这是 `18.3` 从“能用”到“成熟”的关键 |
| `P2` | 经验沉淀与回归评测 | 没有沉淀和回归，后面会一直靠感觉调 |

---

## 4. 具体方案

## 4.1 Phase 1：先把“阶段”和“结果”做实

### 4.1.1 增加阶段概念

要解决的问题：

- 红娘 C 现在更像一个统一入口的建议器
- 没有正式区分 `聊天前 / 聊天中 / 聊天后`

建议做法：

- 给红娘 C 的调用显式加阶段字段：
  - `pre_chat`
  - `in_chat`
  - `post_chat`
- 每次运行都带上阶段
- 不同阶段使用不同的 system instruction 包

建议修改模块：

- [assistant_runtime.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_runtime.py:326)
- [assistant_orchestrator.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_orchestrator.py:72)
- [assistant_sessions.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_sessions.py:431)

验收标准：

- 每次红娘 C 输出都能明确知道自己属于哪个阶段
- 不再用同一套泛化 prompt 处理三种完全不同的职责

### 4.1.2 增加结构化结果表

要解决的问题：

- 现在结果主要留在自然语言里
- session state 里也主要只有 `last_reason_codes`
- 聊后没有正式的结构化结果沉淀

当前代码现状可见：

- [assistant_sessions.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_sessions.py:447)

建议做法：

- 新增一张结果表，例如 `chat_assistant_stage_results`
- 每条结果至少存：
  - `case_id`
  - `session_id`
  - `stage`
  - `owner_user_id`
  - `decision_type`
  - `summary_text`
  - `evidence_json`
  - `result_json`
  - `created_at`

其中：

- `decision_type` 在 `post_chat` 阶段至少支持：
  - `advance`
  - `clarify`
  - `end`

验收标准：

- 不再只靠消息文本回看结论
- 同一个 case 可以查到最近一次聊天前准备结果和聊天后复盘结果

### 4.1.3 timeline 返回阶段结果

要解决的问题：

- 现在 timeline 只返回消息和 thread summary
- 还看不到准备结论和复盘结论

当前代码现状可见：

- [timeline.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/timeline.py:11)

建议做法：

- `build_chat_timeline()` 里追加：
  - 最近一次 `pre_chat` 结果
  - 最近一次 `post_chat` 结果
  - 当前有效分流结论

验收标准：

- 前端或调试接口可以直接看到最近一次准备/复盘结果
- 不需要再去翻自然语言聊天记录找结论

---

## 4.2 Phase 2：补齐聊天后能力

### 4.2.1 先做独立“聊后复盘入口”

要解决的问题：

- 当前系统更擅长“聊天中出问题时介入”
- 不擅长“聊完以后专门复盘”

建议做法：

- 在服务层增加独立入口：
  - `run_post_chat_review(case_id, owner_user_id, ...)`
- 输入以最近一段 dyadic 聊天 + 用户私聊反馈为主
- 输出 owner-only 结果，不直接进主群

建议修改模块：

- [service.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/service.py:1)
- [assistant_context.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_context.py:19)
- 可新增 `post_chat_review.py`

验收标准：

- 用户不需要等聊天再次卡住，才能得到聊后判断
- 复盘和“中途救火”职责分开

### 4.2.2 把 `推进 / 澄清 / 结束` 做成正式结构化结果

要解决的问题：

- 当前红娘 C 有时能在自然语言里说“更适合澄清”
- 但这还不是正式产品能力

建议做法：

- `post_chat` 阶段输出统一 schema：
  - `decision_type`: `advance | clarify | end`
  - `confidence`
  - `primary_reason`
  - `evidence_signals`
  - `next_step_advice`
  - `avoid_list`

重点：

- `clarify` 必须单独立出来
- 不要让系统只会二选一：
  - 继续
  - 结束

验收标准：

- A04 / A04B / A05 / A05B 类 case 有稳定结构化输出
- 不再只是一段“我感觉更像……”的自然语言

### 4.2.3 单独做“误会澄清”模块

要解决的问题：

- 现在“误会”和“没兴趣”还容易混
- `clarify` 没有独立闭环

建议做法：

- 给 `clarify` 场景单独设计判断条件：
  - 双方仍有基本兴趣
  - 主要问题来自一句话没接住、节奏错位、表达偏差
  - 还没到边界冲突或明确无意愿
- 输出两层内容：
  - 为什么判 `clarify`
  - 怎么澄清更低压

验收标准：

- A03 / A04B 类 case 不再只是“继续追问更多背景”
- 能真正完成一次澄清型复盘

---

## 4.3 Phase 3：补齐聊天前能力

### 4.3.1 做画像切口提炼器

要解决的问题：

- 当前 `18.2` 最大问题不是不会提醒风险
- 而是不够会从这两个人身上提具体切口

建议做法：

- 基于现有 `get_profile_snapshot()` 拿到双方画像
- 先做一层规则化整理，提取：
  - 同城/异地
  - 工作节奏
  - 兴趣爱好
  - 生活方式
  - 明显差异点
- 再把这些整理结果喂给 LLM，而不是直接把大段原始画像扔进去

当前可复用模块：

- [assistant_context.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/assistant_context.py:238)

建议新增模块：

- `pre_chat_context.py`

验收标准：

- P01 输出里稳定出现 2 到 3 个真实切口
- 不再大量停留在“找共同点、轻松聊、问开放问题”这种泛化话术

### 4.3.2 做聊天前风险预判器

要解决的问题：

- 风险识别虽然已经有基础，但还不够系统

建议做法：

- 在 `pre_chat` 阶段单独输出：
  - 不建议先问什么
  - 为什么不建议
  - 如果用户执意想聊这个，应该延后到什么阶段

重点覆盖：

- 查户口
- 收入房产
- 婚期施压
- 前任细节
- 家庭催婚
- 高压力价值判断

验收标准：

- P02 / P04 自然版 case 也能稳定命中风险提醒
- 不依赖用户明确说“你别替我写话”

### 4.3.3 做开场策略卡，而不是代写开场白

要解决的问题：

- 当前开场建议还偶尔会滑向“我替你写一句”

建议做法：

- `pre_chat` 阶段默认输出结构改成：
  - `talking_hooks`
  - `opening_strategy`
  - `avoid_topics`
  - `expectation_calibration`
- 示例句只能作为“示意”，不能变成主体

验收标准：

- P03 稳定通过
- 红娘 C 的主输出是“方向和策略”，不是“成品代聊稿”

---

## 4.4 Phase 4：补齐聊天中的精细判断

### 4.4.1 增加互动状态分类

要解决的问题：

- 当前聊天中已经会提醒
- 但对状态分得还不够细

建议做法：

- 给 `in_chat` 增加更明确的状态标签，例如：
  - `smooth`
  - `fragile`
  - `cooling`
  - `misunderstanding`
  - `boundary_risk`
  - `low_interest`

目的不是让前端展示这些词，而是让内部决策更稳。

验收标准：

- M02 / M03 / M05 的判断差异更稳定
- 不再频繁把“没接住”误判成“没兴趣”

### 4.4.2 加入“适度退后”规则

要解决的问题：

- 这是 `18.3` 当前最明显短板之一

建议做法：

- 在 `in_chat` 阶段明确写一条优先规则：
  - 当状态是 `smooth`
  - 且双方近几轮来回自然
  - 且没有风险信号
  - 优先返回 `should_reply=false` 或极轻量提醒

验收标准：

- M04 通过率明显提升
- 红娘 C 不再在没必要时强刷存在感

### 4.4.3 回场时先判断“误会”还是“低兴趣”

要解决的问题：

- 当前回场建议经常偏保守
- 但对问题本质拆得不够细

建议做法：

- `misunderstanding` 场景优先给：
  - 低压澄清
  - 别继续争论
  - 回到具体事实
- `low_interest` 场景优先给：
  - 降低投入
  - 停止追问态度
  - 观察是否还有双向性

验收标准：

- M05 / M06 / M07 的处理更区分场景
- 不再用一套“先放一放”包打天下

---

## 4.5 Phase 5：补齐经验沉淀和评测

### 4.5.1 经验沉淀不要再只靠 concat summary

当前代码现状是：

- `chat_thread_summaries` 主要还是最近消息拼接
- `summary_mode` 还是 `concat`

可见：

- [summaries.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/chat_system/summaries.py:20)

建议做法：

- 保留原来的消息拼接摘要，继续服务调试
- 但新增独立的“关系结果沉淀”层
- 失败原因至少支持结构化标签：
  - `opening_too_heavy`
  - `pace_mismatch`
  - `boundary_pressure`
  - `interest_low`
  - `misunderstanding`
  - `profile_mismatch`

验收标准：

- A06 从“不具备”提升到“至少部分具备”
- 能按 case 回看“为什么没聊成”

### 4.5.2 建立第 18 部分回归评测集

要解决的问题：

- 现在已经有 live case，但还缺常态化回归

建议做法：

- 把这次已经跑过的 case 固化成 smoke / regression 集：
  - `18.2`: P01-P04
  - `18.3`: M01-M07
  - `18.4`: A01-A06
- 每次改 prompt、改 schema、改策略后都回归

注意：

- `run_matchmaker_c_smoke.py --reset` 相关用例应串行执行，避免 MySQL deadlock

验收标准：

- 每次改完都能看到能力点是否前进、退步还是回归
- 不再靠人工主观感觉判断“好像更像红娘了”

---

## 5. 推荐落地顺序

如果只看“最短路径”，建议这样排：

1. `先补 post_chat 结构化复盘`
2. `再补 stage/result 存储和 timeline 展示`
3. `再补 pre_chat 切口提炼和风险预判`
4. `再补 in_chat 的状态分类和退后策略`
5. `最后补经验沉淀和持续回归`

原因很简单：

- `18.4` 现在缺口最大
- `18.2` 提升最容易被用户直接感知
- `18.3` 已经有基础，适合在后面做精修

---

## 6. 这一轮最不建议做的事

### 6.1 不建议只重写 prompt

因为这样最多只能把话说得更像红娘，但解决不了：

- 没有阶段
- 没有独立入口
- 没有结构化结果
- 没有经验沉淀

### 6.2 不建议把所有能力都塞进现有“聊天中救火”入口

因为这样只会让职责更混。

正确做法应该是：

- `pre_chat` 单独准备
- `in_chat` 单独判断
- `post_chat` 单独复盘

### 6.3 不建议一上来追求“全自动”

先把手动触发做稳，再做自动化。

否则会出现：

- 自动介入时机乱
- 结果不稳
- 调试也更困难

---

## 7. 最后一句话

这次 live 验证说明了一件事：

- 红娘 C 现在已经不是零能力
- 但它离“第 18 部分完整具备”差的，不主要是文风
- 而是 `阶段化能力`, `结构化结果`, `聊后闭环`, `经验沉淀`

所以这轮改进的核心，不是“把建议写得更像红娘”，而是：

- **把红娘这份工作真的拆出来、存下来、跑起来**

---

## 8. 相关文档

- 整体验证总结：
  - [chat-assistant-section18-overall-validation-summary-20260509.md](./chat-assistant-section18-overall-validation-summary-20260509.md)
- `18.2` 结论：
  - [chat-assistant-section18-current-validation-conclusion-20260509.md](./chat-assistant-section18-current-validation-conclusion-20260509.md)
- `18.3` 结论：
  - [chat-assistant-section18-in-chat-validation-conclusion-20260509.md](./chat-assistant-section18-in-chat-validation-conclusion-20260509.md)
- `18.4` 结论：
  - [chat-assistant-section18-post-chat-validation-conclusion-20260509.md](./chat-assistant-section18-post-chat-validation-conclusion-20260509.md)
- 更早的差距分析：
  - [chat-assistant-section18-gap-analysis.md](./chat-assistant-section18-gap-analysis.md)
- 更早的任务拆解：
  - [chat-assistant-section18-task-breakdown.md](./chat-assistant-section18-task-breakdown.md)

