# 向量筛选 + Agent 自主判断落地方案

> **文档版本**: v2.0
> **更新日期**: 2026-06-22
> **适用范围**: 当前 Her 仓库现有 discovery + persona + summary + vector 能力
> **核心目标**: 不重造一套新画像管线，而是在现有能力上补齐数据覆盖、统一返回契约、约束 Agent 使用方式

---

## 一、问题背景

### 1. 用户侧现象

用户会提这类需求：

```text
我想找温柔、有上进心的
```

系统当前容易出现两个问题：

1. 向量筛选没有真正生效
2. Agent 推荐理由看起来像在猜，数据支撑不够扎实

典型日志现象：

```text
【向量筛选开始】candidate_count=50
【向量搜索完成】找到 0 个相似用户
【向量筛选完成】with_data_count=0 without_data_count=50
```

这说明不是“用户要求太抽象”，而是“候选人向量/摘要覆盖率不足，导致软匹配失效”。

---

### 2. 当前系统真实状态

当前系统并不是完全没有人格数据返回，而是已经有一部分能力：

1. `search_partner_candidates_with` 已经会返回候选人基础资料
2. 系统已经能加载 `personality_traits`
3. 系统已经能加载 `summary`
4. Agent 已经能看到部分性格信息

真正的问题是：

1. 候选人数据覆盖率不稳定
2. 返回字段结构分散，不够统一
3. Agent Prompt 没有明确规定“哪些字段可引用，缺失时怎么说”
4. 兜底策略没有定死，质量优先和结果数优先混在一起

---

### 3. 根因重写

原问题不是“完全缺少完整画像加载环节”，而是下面三件事同时存在：

#### 根因 1：向量/摘要数据覆盖不足

- 候选池里很多人没有可用向量
- `conversation_summaries` 或向量摘要字段不完整
- 结果是向量筛选阶段失效

#### 根因 2：候选人增强信息虽已存在，但消费契约不统一

当前候选结果里已经可能包含：

- `profile`
- `personality_traits`
- `personality_availability`
- `summary`
- `summary_meta`

但这些字段没有形成一个明确的“Agent 使用协议”。

#### 根因 3：Agent 被允许在数据不足时过度推理

比如只看到 MBTI code，就直接推断：

- “她天生温柔”
- “她很有事业心”

这会让推荐理由变成标签化表达，而不是基于真实候选数据的判断。

---

## 二、目标原则

### 1. 不重造 full_profile 管线

本方案明确不采用“新建 `_load_full_candidate_profiles`、单独组装 7 维大对象、再让 Agent 消费”的路线。

原因：

1. 当前仓库已经有 traits / summary / profile 加载能力
2. 再造一层会重复实现
3. 容易增加性能开销
4. 会放大测试回归范围

---

### 2. 目标不是“数据更多”，而是“数据更可用”

要达到的状态是：

1. 向量筛选尽量真的参与候选过滤
2. Agent 稳定拿到统一字段
3. Agent 只能基于有证据的数据说话
4. 数据缺失时要诚实，而不是编理由

---

### 3. 统一优先级

本方案选择：

**质量优先，但允许有限降级。**

解释如下：

1. 有人格测评或摘要数据的候选人，优先进入推荐主列表
2. 完全没有人格相关数据的候选人，不参与“性格型推荐理由”
3. 如果结果数明显不足，可以作为降级候选展示，但必须标记“人格数据不足，仅基于基础资料展示”

这样避免两个极端：

1. 全过滤，结果太少
2. 全放行，理由乱编

---

## 三、现有可复用能力梳理

### 1. 当前代码里已经有的能力

当前代码已经具备以下基础：

#### 候选搜索

- `discovery_system/service_integrations.py`
- `search_partner_candidates_with(...)`

负责：

1. 编译硬约束
2. 执行数据库搜索
3. 可选执行向量筛选
4. 对结果做人格特征增强
5. 对结果做摘要增强

#### 人格测评读取

- `partner_search/personality_traits_reader.py`

负责：

1. 从 `user_personas.self_personality_traits_json` 读取原始数据
2. 批量加载 `load_traits_for_profiles(...)`
3. 返回 `PersonalityTraitsContext`

#### 摘要读取

- `match_domain/summary_loader.py`

负责：

1. 从 `conversation_summaries` 读取摘要
2. 按向量类型聚合摘要
3. 返回 `summary` 和 `summary_meta`

---

### 2. 当前最需要补的不是“新表”，而是“统一返回契约”

建议统一候选人的 Agent 可消费字段为：

```python
{
  "id": 6092,
  "name": "于若岚",
  "score": 130,
  "profile": {...},                      # 基础资料
  "personality_traits": {...},           # 原始测评数据
  "personality_availability": {...},     # 测评数据可用性
  "summary": {...},                      # conversation_summaries 聚合摘要
  "summary_meta": {...},                 # 摘要覆盖情况
  "candidate_context": {                 # 轻量统一上下文（新增）
    "has_traits": True,
    "has_summary": True,
    "evidence_level": "high",
    "allowed_reason_sources": [
      "profile",
      "personality_traits",
      "summary"
    ],
    "missing_dimensions": []
  }
}
```

这里的关键点不是字段更多，而是新增一个轻量 `candidate_context`，专门告诉 Agent：

1. 当前候选人有哪些证据
2. 哪些字段可以引用
3. 缺了哪些维度
4. 当前推荐理由可信度有多高

---

## 四、数据层方案

### 1. P0：先补覆盖率

最优先要做的是数据覆盖，不是接口美化。

#### 目标

确保候选池中的人格相关数据尽量可用：

1. `self_personality_traits_json` 有值
2. `conversation_summaries` 有关键摘要
3. 对应向量库可检索

#### 核心检查项

1. `user_personas.self_personality_traits_json` 覆盖率
2. `conversation_summaries.summary_key` 覆盖率
3. 向量库中各 `vector_type` 覆盖率

#### 验证重点

不是只看“库里总共有多少条向量”，而是看：

**进入 discovery 候选池的人里，有多少人有可用人格数据。**

---

### 2. 摘要字段分层

推荐按下面优先级使用摘要：

| 优先级 | 字段 | 用途 |
|---|---|---|
| P0 | `personality_traits` | 说明温柔、稳重、外向、细腻等人格描述 |
| P0 | `values` | 说明重视家庭、成长、事业、责任感 |
| P1 | `emotional_needs` | 说明相处中需要什么 |
| P1 | `life_attitude` | 说明生活节奏和长期关系观 |
| P2 | `partner_personality_preference` | 说明她喜欢什么样的人 |
| P2 | `partner_relationship_pacing` | 说明关系推进节奏 |
| P2 | `partner_lifestyle_preference` | 说明生活方式偏好 |

---

## 五、返回结构改造方案

### 1. 不引入 full_profile

不建议把结果改成：

```python
result["full_profile"] = {...7个维度大对象...}
```

原因：

1. 现有前端和测试更接近平铺结构
2. `view_models.py` 当前主要消费 `profile` 与增强字段
3. 大对象会提高测试和兼容成本

---

### 2. 推荐的返回结构

在现有结构基础上做轻量增强：

```python
{
  "has_match": True,
  "result_count": 5,
  "results": [
    {
      "id": 6092,
      "name": "于若岚",
      "score": 130,
      "profile": {
        "age": 27,
        "city": "无锡",
        "job": "产品经理",
        "education": "博士",
        "relationship_goal": "认真恋爱"
      },
      "personality_traits": {
        "mbti": {"type_code": "ISFP"},
        "attachment": {"type_code": "secure", "anxiety": 20, "avoidance": 25},
        "big_five": {"scores": {"agreeableness": 90, "conscientiousness": 80}},
        "values": {"value_type": "事业成就型", "top_values": ["事业成长", "稳定经营"]}
      },
      "personality_availability": {
        "has_mbti": True,
        "has_attachment": True,
        "has_big_five": True,
        "has_values": True,
        "overall_completeness": 0.8
      },
      "summary": {
        "personality_traits": "温和细腻，重视和谐，慢热但好相处",
        "values": "重视事业成长，也希望关系稳定",
        "emotional_needs": "需要理解和鼓励"
      },
      "summary_meta": {
        "field_count": 3,
        "completeness": 0.38,
        "has_data": True
      },
      "candidate_context": {
        "has_traits": True,
        "has_summary": True,
        "evidence_level": "high",
        "reason_mode": "rich_reasoning",
        "missing_dimensions": []
      }
    }
  ]
}
```

---

### 3. `candidate_context` 规则

新增统一规则：

#### `evidence_level`

- `high`: traits 和 summary 都有
- `medium`: 只有 traits 或只有 summary
- `low`: 只有基础 profile

#### `reason_mode`

- `rich_reasoning`: 可以生成较具体推荐理由
- `limited_reasoning`: 可以给有限理由，但必须明确“信息有限”
- `profile_only`: 不得输出性格结论，只能说基础资料匹配点

#### `missing_dimensions`

用于记录：

- `traits`
- `summary`
- `values`
- `attachment`
- `big_five`
- `emotional_needs`

让 Agent 知道自己哪些不能展开说。

---

## 六、兜底策略

### 1. 兜底原则

兜底不是“继续猜”，而是“降低表达强度”。

即：

1. 证据强，就具体说
2. 证据弱，就保守说
3. 没证据，就不说

---

### 2. 各场景处理

#### 场景 A：traits 和 summary 都有

处理方式：

- 正常推荐
- 可以引用人格、价值观、依恋、情感需求

#### 场景 B：只有 traits，没有 summary

处理方式：

- 可以做有限性格判断
- 允许引用 MBTI / attachment / values / big_five 原始数据
- 不允许把标签说得太满

Agent 语言要偏保守，例如：

- “从测评数据看，她偏温和稳定”
- 不要说“她一定很温柔”

#### 场景 C：只有 summary，没有 traits

处理方式：

- 可以引用摘要原文
- 但不要伪装成结构化测评结论

例如：

- “从摘要里看，她比较重视关系稳定和情绪支持”

#### 场景 D：traits 和 summary 都缺

处理方式：

- 不进入“性格推荐主理由”
- 如需要补足数量，可降级展示
- 推荐理由只能基于基础资料

例如：

- “年龄、城市、职业背景符合你的筛选，但人格信息暂不完整，建议先聊聊看”

---

### 3. 不再建议把解释模板放入向量存储层

如果确实需要少量模板兜底，应该放在 discovery 展示侧的独立模块，例如：

`discovery_system/personality_explanations.py`

不建议放入：

`match_domain/vector_store_lite.py`

因为存储层不应该承担文案解释职责。

---

## 七、具体实现方案

### 1. `service_integrations.py` 调整方向

核心思路：

1. 保留现有搜索主流程
2. 保留现有 `load_traits_for_profiles(...)`
3. 优先把摘要加载改成批量模式
4. 新增轻量 `candidate_context`
5. 不新增 full profile loader

---

### 2. 推荐改动点

#### 改动点 A：摘要加载从逐个改为批量

当前问题：

- 对每个 candidate 单独 `asyncio.run(load_complete_summary(...))`
- 容易有性能损耗
- 也会让同步/异步边界更脆

建议改成：

1. 收集候选 `candidate_ids`
2. 使用 `load_complete_summaries_batch(...)`
3. 一次性挂回每个 candidate

目标：

- 降低重复 IO
- 减少事件循环边界问题

---

#### 改动点 B：统一构造 `candidate_context`

新增一个纯同步 helper，例如：

```python
def _build_candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    traits = candidate.get("personality_traits") or {}
    summary = candidate.get("summary") or {}
    availability = candidate.get("personality_availability") or {}

    has_traits = bool(traits) and availability.get("overall_completeness", 0) > 0
    has_summary = bool(summary)
    missing_dimensions = []

    if not has_traits:
        missing_dimensions.append("traits")
    if not has_summary:
        missing_dimensions.append("summary")
    if has_traits and not traits.get("values"):
        missing_dimensions.append("values")
    if has_traits and not traits.get("attachment"):
        missing_dimensions.append("attachment")
    if has_traits and not traits.get("big_five"):
        missing_dimensions.append("big_five")
    if has_summary and not summary.get("emotional_needs"):
        missing_dimensions.append("emotional_needs")

    if has_traits and has_summary:
        evidence_level = "high"
        reason_mode = "rich_reasoning"
    elif has_traits or has_summary:
        evidence_level = "medium"
        reason_mode = "limited_reasoning"
    else:
        evidence_level = "low"
        reason_mode = "profile_only"

    return {
        "has_traits": has_traits,
        "has_summary": has_summary,
        "evidence_level": evidence_level,
        "reason_mode": reason_mode,
        "missing_dimensions": missing_dimensions,
    }
```

---

#### 改动点 C：保留原字段，避免前端和测试大改

保留：

- `profile`
- `personality_traits`
- `personality_availability`
- `summary`
- `summary_meta`

只新增：

- `candidate_context`

这样现有消费方不需要整体迁移。

---

### 3. Agent Prompt 调整

Prompt 重点不是告诉 Agent “你拿到了完整画像”，而是告诉它：

1. 哪些字段能引用
2. 哪些字段只是辅助信息
3. 数据缺失时要怎么收口

推荐规则：

```markdown
候选人可能包含以下字段：
- profile：基础资料
- personality_traits：原始测评数据
- personality_availability：测评数据完整度
- summary：对话摘要/向量摘要
- summary_meta：摘要覆盖情况
- candidate_context：可用证据等级和理由生成模式

输出规则：
1. 优先基于 summary 和 personality_traits 生成推荐理由
2. 只有 profile 时，不要输出性格结论
3. 当 candidate_context.reason_mode = limited_reasoning 时，必须使用保守表达
4. 当 candidate_context.reason_mode = profile_only 时，只能说基础条件匹配，不能说“她温柔”“她有上进心”这类性格判断
5. 如果某维度缺失，要明确说“这部分信息暂不完整”
```

---

## 八、实施步骤

### Phase 1：补覆盖率

目标：

提升候选池中的人格数据可用率。

动作：

1. 统计 `user_personas.self_personality_traits_json` 覆盖率
2. 统计 `conversation_summaries` 关键 `summary_key` 覆盖率
3. 统计 discovery 候选池的有效人格数据命中率
4. 补全历史缺失数据

验收：

- discovery 候选池中，`traits 或 summary` 至少其一可用的候选人占比 > 90%

---

### Phase 2：返回契约收敛

目标：

让 Agent 始终看到结构稳定的候选增强数据。

动作：

1. 批量加载摘要
2. 统一挂载 `summary` / `summary_meta`
3. 新增 `candidate_context`
4. 保留兼容字段，不引入 `full_profile`

验收：

- 搜索返回中每个候选都包含稳定结构
- 测试桩同步更新

---

### Phase 3：Agent 使用约束

目标：

减少“看见一个 MBTI 就胡乱下结论”的情况。

动作：

1. 更新 Agent 指令
2. 增加保守表达约束
3. 补充低证据场景样例

验收：

- 人工抽样中，低证据候选不再出现过度人格判断

---

### Phase 4：监控与回归

目标：

持续知道系统是在“真改进”还是“表面改了字段”。

建议监控：

1. `candidate_traits_coverage`
2. `candidate_summary_coverage`
3. `candidate_high_evidence_ratio`
4. `vector_filter_effective_ratio`
5. `agent_overclaim_rate`

---

## 九、任务拆分清单

### Task 1：盘点 discovery 候选池的人格数据覆盖率

**目标**

先搞清楚问题到底有多严重，不凭感觉改。

**具体任务**

1. 统计 `user_personas.self_personality_traits_json` 覆盖率
2. 统计 `conversation_summaries` 关键摘要覆盖率
3. 统计 discovery 候选池中 `traits` 可用率
4. 统计 discovery 候选池中 `summary` 可用率
5. 统计 discovery 候选池中 `traits 或 summary` 至少其一可用率
6. 输出按城市、性别、候选来源的覆盖率分布

**产出物**

1. 覆盖率统计脚本
2. 覆盖率结果表
3. 问题样本清单

**完成标准**

1. 能明确回答“候选池里到底多少人没有人格证据”
2. 能识别缺失主要发生在哪些人群或链路

---

### Task 2：补全历史摘要和向量数据

**目标**

把当前候选池里缺失严重的人格摘要和向量先补上。

**具体任务**

1. 梳理需要回填的摘要类型
2. 编写摘要回填脚本
3. 编写向量补建脚本
4. 对历史用户批量执行回填
5. 校验回填后摘要和向量是否能被 discovery 命中

**产出物**

1. `scripts/backfill_candidate_summaries.py`
2. 回填执行记录
3. 回填后覆盖率对比结果

**完成标准**

1. 回填后候选池 `traits 或 summary` 至少其一可用率达到目标
2. 向量筛选不再大面积出现“候选人全无数据”

---

### Task 3：梳理并冻结候选人返回契约

**目标**

明确 discovery 返回给 Agent 和前端的字段规范，避免后续一边开发一边变。

**具体任务**

1. 确认保留字段：`profile`、`personality_traits`、`personality_availability`、`summary`、`summary_meta`
2. 定义新增字段 `candidate_context`
3. 定义 `candidate_context` 子字段含义
4. 定义高证据、中证据、低证据判定规则
5. 定义缺失维度编码规范

**产出物**

1. 候选人返回结构说明
2. 字段示例 JSON
3. 兼容性说明

**完成标准**

1. Agent、后端、前端对返回结构达成一致
2. 后续实现不再引入 `full_profile` 类大对象

---

### Task 4：把摘要加载改成批量模式

**目标**

减少逐候选摘要读取带来的性能损耗和异步边界风险。

**具体任务**

1. 检查 `summary_loader.py` 现有 batch 接口是否满足需求
2. 如果不满足，补齐批量接口能力
3. 在 `service_integrations.py` 中改为批量收集 candidate ids
4. 批量拉取 summaries
5. 按候选人回填 `summary` 和 `summary_meta`
6. 确认不改变原始候选顺序

**产出物**

1. 批量摘要加载代码
2. 性能对比结果
3. 顺序稳定性测试结果

**完成标准**

1. 候选增强逻辑中不再逐个 candidate 单独跑摘要加载
2. 返回顺序与原搜索结果一致

---

### Task 5：新增 `candidate_context` 构造逻辑

**目标**

给 Agent 一份明确的“证据说明书”。

**具体任务**

1. 实现 `_build_candidate_context(...)`
2. 计算 `has_traits`
3. 计算 `has_summary`
4. 计算 `evidence_level`
5. 计算 `reason_mode`
6. 计算 `missing_dimensions`
7. 把 `candidate_context` 挂载到每个 candidate

**产出物**

1. `candidate_context` 构造函数
2. 多场景样例数据

**完成标准**

1. 高、中、低证据候选都能被正确分类
2. Agent 可以直接根据 `reason_mode` 决定话术强度

---

### Task 6：明确降级展示策略

**目标**

把“无人格数据时到底展示不展示”说死，避免实现时反复摇摆。

**具体任务**

1. 明确主推荐列表准入规则
2. 明确降级候选何时允许展示
3. 明确降级候选展示文案
4. 明确是否单独打标“人格信息不足”
5. 明确前端和 Agent 对降级候选的处理方式

**产出物**

1. 降级策略说明
2. 示例推荐文案

**完成标准**

1. 产品和研发对降级逻辑达成一致
2. 文档中不再同时存在互相矛盾的准入规则

---

### Task 7：更新 Agent 指令，限制过度推理

**目标**

让 Agent 只在有证据时才输出人格判断。

**具体任务**

1. 更新 Agent 指令，说明各字段含义
2. 加入 `reason_mode` 使用规则
3. 明确 `profile_only` 场景禁止输出性格判断
4. 明确 `limited_reasoning` 场景必须使用保守措辞
5. 补充高、中、低证据三类示例

**产出物**

1. 更新后的 Agent 指令
2. Prompt 样例

**完成标准**

1. Agent 在低证据场景不再输出“她温柔”“她有上进心”这类定性结论
2. Agent 在高证据场景能输出更具体的理由

---

### Task 8：补测试，防止回归

**目标**

把这次改造变成可以长期维持的能力，而不是一次性改完就回退。

**具体任务**

1. 增加 traits 回传测试
2. 增加 summary 回传测试
3. 增加 `candidate_context` 判定测试
4. 增加 `rich_reasoning` / `limited_reasoning` / `profile_only` 场景测试
5. 增加返回顺序不变测试
6. 增加前端卡片兼容测试

**产出物**

1. 新增和更新的测试用例
2. 测试覆盖说明

**完成标准**

1. 关键场景均有自动化测试覆盖
2. discovery 现有主流程测试继续通过

---

### Task 9：上线监控与效果验证

**目标**

确认改造后的系统是真的更好，而不是只是多返回了几个字段。

**具体任务**

1. 增加 `candidate_traits_coverage` 监控
2. 增加 `candidate_summary_coverage` 监控
3. 增加 `candidate_high_evidence_ratio` 监控
4. 增加 `vector_filter_effective_ratio` 监控
5. 增加 `agent_overclaim_rate` 监控
6. 建立人工抽样评估机制

**产出物**

1. 指标定义文档
2. 监控面板
3. 人工抽样评估表

**完成标准**

1. 能持续看到覆盖率、推荐理由质量和向量筛选有效性
2. 能在效果变差时及时发现

---

### Task 10：灰度上线与复盘

**目标**

用低风险方式把方案推到线上，并在上线后确认效果。

**具体任务**

1. 确定灰度范围
2. 先在小流量下验证数据和文案行为
3. 对比灰度前后的推荐理由质量
4. 对比灰度前后的点击率和有效筛选率
5. 汇总异常案例
6. 产出复盘结论

**产出物**

1. 灰度方案
2. 灰度结果对比报告
3. 复盘文档

**完成标准**

1. 没有明显兼容问题
2. 推荐理由质量和筛选有效性达到预期

---

## 十、测试与回归要求

### 1. 需要重点补的测试

#### 服务层测试

验证：

1. traits 存在时正确回传
2. summary 存在时正确回传
3. `candidate_context` 判定正确
4. 批量摘要加载不改变原始候选顺序

#### Agent 行为测试

验证：

1. `rich_reasoning` 场景可输出具体理由
2. `limited_reasoning` 场景表达变保守
3. `profile_only` 场景不输出性格结论

#### 回归测试

验证：

1. 现有 candidate card 构建不崩
2. 现有前端字段兼容
3. 现有 `test_discovery_system.py` 相关断言继续成立

---

### 2. 明确不做的事情

为了控制范围，本轮不做：

1. 不新建 7 维 `full_profile`
2. 不重写整条 discovery 搜索链路
3. 不把人格解释模板塞进向量存储层
4. 不在 service 层重新做人设推理引擎

---

## 十一、风险与应对

### 风险 1：覆盖率补上前，向量筛选仍然收益有限

应对：

先做覆盖率统计，再评估向量阈值，而不是反过来调阈值掩盖缺数据问题。

---

### 风险 2：Agent 仍可能过度发挥

应对：

通过 `candidate_context.reason_mode` 硬约束表达边界，而不是只写模糊 Prompt。

---

### 风险 3：返回结构继续膨胀

应对：

新增字段控制在 `candidate_context` 一项，避免无限堆字段。

---

### 风险 4：同步代码继续堆 `asyncio.run`

应对：

优先把摘要改为批量入口，减少逐候选异步调用次数；后续如果 discovery 整体异步化，再统一处理事件循环边界。

---

## 十二、验收标准

### 数据验收

- [ ] discovery 候选池中 `traits 或 summary` 可用率 > 90%
- [ ] 关键摘要字段覆盖率满足要求
- [ ] 向量筛选不再大面积出现“50 人全无向量数据”

### 返回结构验收

- [ ] 每个候选稳定返回 `profile`
- [ ] 有人格数据时稳定返回 `personality_traits`
- [ ] 有摘要时稳定返回 `summary`
- [ ] 新增 `candidate_context` 字段

### Agent 验收

- [ ] 高证据候选能输出具体且可引用的数据型理由
- [ ] 中证据候选使用保守表述
- [ ] 低证据候选不再输出性格定性结论

### 回归验收

- [ ] 现有 discovery 测试通过
- [ ] 候选人卡片渲染兼容
- [ ] 返回顺序不因增强逻辑发生意外变化

---

## 十三、结论

这次改造的重点不是“把系统重建成一套超级完整画像平台”，而是三件更务实的事：

1. 先补数据覆盖率，让向量筛选不是空转
2. 统一候选增强字段，让 Agent 真正知道该看什么
3. 给 Agent 明确边界，让它在没证据时别乱下判断

一句话总结：

**不是重做一套 full_profile，而是把现有 `profile + personality_traits + summary` 这条链路做实、做稳、做可控。**

---

## 附录 A：建议改动文件

| 文件路径 | 改动内容 |
|---|---|
| `external-systems/partner-discovery-system/discovery_system/service_integrations.py` | 批量摘要加载，新增 `candidate_context`，收敛返回契约 |
| `external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md` 或对应 Agent 指令位置 | 增加证据等级和保守表达约束 |
| `match_domain/summary_loader.py` | 优先复用现有 batch 接口，必要时补性能优化 |
| `external-systems/partner-discovery-system/tests/test_discovery_system.py` | 增加 `candidate_context` 和低证据场景测试 |

---

## 附录 B：建议新增脚本

| 脚本路径 | 功能 |
|---|---|
| `scripts/check_candidate_traits_coverage.py` | 检查 discovery 候选池 traits 覆盖率 |
| `scripts/check_candidate_summary_coverage.py` | 检查 discovery 候选池 summary 覆盖率 |
| `scripts/backfill_candidate_summaries.py` | 回填关键摘要字段 |

---

**文档结束**
