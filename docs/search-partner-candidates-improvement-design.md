# search_partner_candidates 改进方案设计

> **核心思路**：硬约束筛选 → 直接返回原始数据给 Agent → Agent 自主分析判断

> **关键洞察**：离线生成的摘要会"失真"，应直接给 Agent 原始数据，让 Agent 自己分析。Agent 会自己找到分析方法（如 grep 关键词频率、语气分析等），比预设的摘要更准确。

---

## 1. 背景

### 1.1 当前实现的问题

当前 `search_partner_candidates` 的核心矛盾：

**Agent 能理解用户意图，但查询层无法表达**

```
用户说：         "不要绿茶的女生"
Agent 理解：     exclude_traits = ["绿茶"]
Agent 传 criteria： {"绿茶": False}
查询层收到：     ❌ "绿茶" 不是数据库字段 → 查不了
结果：          性格筛选失效
```

### 1.2 代码现状分析（基于实际代码审查）

#### 数据源使用情况

| 数据源 | 写入时机 | 搜索使用情况 | 问题 |
|--------|---------|-------------|------|
| **user_personas 表** | 会话结束后（可量化字段） | ✅ 已使用 | `criteria_compiler` 从此表加载 persona_row |
| **conversation_summaries 表** | 会话结束后（不可量化字段） | ❌ **完全未使用** | `load_traits_for_discovery()` 只加载原始测评数据，不加载摘要文本 |
| **Milvus 向量库** | 会话结束后（向量化） | ❌ **完全未集成** | `VectorStore.search_similar_users()` 已实现但未调用 |

#### 关键代码路径分析

**1. load_traits_for_discovery() 只加载原始测评数据**

```python
# 文件: partner_search/personality_traits_reader.py
# 加载的数据结构：
PersonalityTraitsContext:
  - mbti: {type_code, scores: {ei, sn, tf, jp}}
  - attachment: {type_code, anxiety, avoidance}
  - big_five: {scores: {openness, conscientiousness, ...}}
  - values: {value_type, top_values: [...]}
  - sternberg: {scores: {intimacy, passion, commitment}}

# ❌ 问题：不加载 conversation_summaries 的摘要文本
# conversation_summaries 表存储的内容：
#   - summary_key: "personality_traits"
#   - summary_text: "性格温柔、内向、稳重"
# 这些数据完全未加载，Agent 看不到
```

**2. 向量库已实现但未集成**

```python
# 文件: match_domain/vector_store.py
class VectorStore:
    def search_similar_users(
        self,
        user_vector: list[float],
        vector_type: str,  # personality_traits, values, partner_expectation...
        top_k: int = 50,
        similarity_threshold: float = 0.85,
    ) -> list[dict[str, Any]]:
        """搜索相似用户（带时间衰减）"""
        # ✅ 功能已实现：时间衰减配置、向量搜索
        # ❌ 问题：search_partner_candidates 完全未调用

# 向量类型配置（已实现）：
VECTOR_TYPES_CONFIG = {
    "personality_traits": {"decay_days": 365, "min_factor": 0.7},
    "values": {"decay_days": 365, "min_factor": 0.7},
    "partner_expectation": {"decay_days": 90, "min_factor": 0.5},
}
```

**3. 性格特质排序已移除（Agent Native 模式）**

```python
# 文件: service_integrations.py:523-592
# ✅ Agent Native 改进：移除性格特质增强逻辑
# Tool 层只返回原始性格特质数据，Agent 自主决定如何使用
# - 是否生成性格推荐理由？
# - 是否根据性格匹配度排序？
# - 这些决策在 Agent 层表达，不在 Tool 层硬编码

# 返回的 personality_trace 用于可观测性：
personality_trace = {
    "self_traits_available": bool(user_traits_dict),
    "candidate_traits_count": 0,
    "agent_native_mode": True,
    "note": "性格特质数据已返回，Agent 自主决定如何使用",
}
```

#### 根本原因：数据流未打通

```
会话结束后：
┌─────────────────────────────────────────────────────────────────┐
│ LLM提炼结构化摘要                                                │
│ {"personality_traits": "温柔、内向", "values": "重视家庭"}        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           │                               │
           ▼                               ▼
┌─────────────────────┐        ┌─────────────────────────────────┐
│ 可量化字段           │        │ 不可量化字段                      │
│ (mbti_type, city)   │        │ (personality_traits, values)     │
└──────────┬──────────┘        └────────────────┬────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────┐        ┌─────────────────────────────────┐
│ user_personas 表     │        │ conversation_summaries 表        │
│ ✅ 搜索已使用        │        │ ❌ 搜索完全未使用                 │
│                     │        │                                  │
│ criteria_compiler   │        │ load_traits_for_discovery()      │
│ 从此表加载          │        │ 只加载原始测评数据                │
│                     │        │ 不加载摘要文本                    │
└─────────────────────┘        └─────────────────────────────────┘
                                           │
                                           ▼
                               ┌─────────────────────────────────┐
                               │ Milvus 向量库                    │
                               │ ❌ 搜索完全未集成                 │
                               │                                 │
                               │ VectorStore.search_similar_users()│
                               │ 已实现但未调用                   │
                               └─────────────────────────────────┘
```

### 1.3 根因分析

| 问题 | 用户场景 | 当前实现缺陷 | 根因 |
|------|----------|-------------|------|
| **问题 1** | 性格关键词（温柔、绿茶） | 无法查询性格关键词 | 数据库缺少性格标签字段 |
| **问题 2** | 负面排除（不要绿茶） | `must_not_have_tags` 不适用性格 | 排除机制设计局限 |
| **问题 3** | 生活方式（能干家务） | 字段缺失或不支持查询 | 数据源+编译器局限 |
| **问题 4** | 模糊表达（靠谱、能过日子） | Agent 能理解但无法落地 | 理解层→查询层断层 |
| **问题 5** | 匹配兼容性（性格互补） | 是后计算，不是前筛选 | 搜索引擎设计局限 |
| **问题 6** | 相对条件（比我小5岁） | 需要特殊语法或预处理 | criteria_compiler 局限 |
| **问题 7** | 权重优先级（温柔最重要） | 所有条件等权重 | 搜索引擎设计局限 |
| **问题 8** | 放宽策略（没有人放宽年龄） | 需要多次搜索 | 缺少搜索策略设计 |
| **问题 9** | 翻译层缺失 | 关键词→数据字段无映射 | 架构设计缺失 |
| **问题 10** | 数据片面 | 数据库没记录"真诚"→ 认为不真诚 | 数据源局限 + 分析片面 |
| **问题 11** | **摘要文本未加载** | conversation_summaries 表数据未使用 | **数据流未打通** |
| **问题 12** | **向量库未集成** | Milvus 向量搜索未使用 | **数据流未打通** |

---

## 2. 用户搜索场景全景图

### 2.1 硬条件类（明确数字/选项）

用户表达：
- "25-30岁的"、"上海的"、"身高160-170的"
- "本科以上的"、"未婚的"、"月入1万以上的"
- "有房的"、"有车的"、"程序员的"
- "比我小5岁的"、"同龄人"
- "离异也可以"、"接受有孩子的"

### 2.2 性格类（关键词描述）

用户表达：
- "性格温柔的"、"性格开朗的"、"性格稳重的"
- "不要太强势的"、"不要太内向的"
- "不要绿茶的"、"不要矫情的"
- "成熟一点的"、"有趣一点的"、"有幽默感的"
- "懂事的"、"善解人意的"、"情商高的"

### 2.3 MBTI/依恋/价值观类

用户表达：
- "ISFJ型的"、"内向型的"、"外向型的"
- "安全型依恋的"、"不要太焦虑型的"
- "家庭导向的"、"事业导向的"
- "看重家庭的"、"看重真诚的"、"三观一致的"

### 2.4 生活方式类

用户表达：
- "愿意做家务的"、"能给我干家务的"、"家务一起分担的"
- "早睡早起的"、"作息规律的"
- "喜欢宅家的"、"喜欢户外的"、"爱运动的"

### 2.5 关系期望类

用户表达：
- "结婚导向的"、"认真恋爱的"、"想快点结婚的"
- "想要孩子的"、"不想要孩子的"
- "接受异地的"、"不接受异地的"

### 2.6 负面排除类

用户表达：
- "不要绿茶的女生"、"不要强势的"
- "不要异地"、"不要离异的"
- "不要程序员的"、"不要经常加班的"

### 2.7 模糊/口语化类

用户表达：
- "找个靠谱的"、"找个能过日子的"
- "找个有趣的灵魂"、"找个性格好的"

### 2.8 组合类

用户表达：
- "上海本地 + 25-30岁 + 性格温柔 + 结婚导向"
- "愿意做家务 + 早睡早起 + 结婚导向 + 未婚"
- "温柔 + 懂事 + 不要绿茶 + 上海"

---

## 3. 核心问题深度分析

### 3.1 关键词→数据库字段断层

**问题**：用户说"温柔"，数据库没有 `温柔` 字段

**当前 persona 数据结构**：
```python
persona = {
    "mbti": {"type_code": "ISFJ"},
    "attachment": {"type_code": "secure"},
    "big_five": {"scores": {"agreeableness": 0.8}},
    "values": {"value_type": "family_oriented", "top_values": ["家庭", "真诚"]}
}
```

**矛盾**：
- 用户表达是自然语言关键词（温柔、绿茶）
- 数据库字段是结构化维度（MBTI、依恋、大五人格）
- 两者之间没有桥梁

### 3.2 "绿茶"问题的特殊性

**为什么"绿茶"不能简单映射到数据库字段？**

1. **主观判断**：绿茶是主观评价，不是客观属性
2. **多维度组合**：绿茶 = 不真诚 + 表里不一 + 过于迎合 + 善于伪装
3. **数据片面**：数据库没记录"真诚"→ 就认为该用户不真诚 → 判断片面

**正确理解**：
- 用户说"不要绿茶"，意思是排除某种性格组合的人
- Agent 需要从候选人的多维度信息中判断（聊天、画像、行为）
- 不是查数据库字段，而是**Agent 语义理解判断**

---

## 4. 改进方案设计（Agent Native 架构）

### 4.1 核心思路：Agent先判断，串行筛选

**核心原则**：Agent是决策大脑，自己判断用户需求能否映射到结构化字段，不需要Prompt指导。

```
用户说："我想找温柔的，北京的，25-30岁，不要绿茶的"

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Agent 先判断能否映射到结构化字段                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 思考（不需要Prompt指导，Agent自己有足够的知识）：           │
│                                                                 │
│ "北京的" → profile.city → ✅ 能映射                             │
│ "25-30岁" → profile.age → ✅ 能映射                             │
│ "温柔的" → persona.mbti？→ Agent知道：温柔的人通常内向、友善      │
│   → 可能是ISFJ、INFJ → ✅ 能映射                                 │
│                                                                 │
│ "不要绿茶的" → 结构化字段？→ Agent知道：绿茶=表里不一+心机重+双标 │
│   → 数据库没有这些字段 → ❌ 不能映射                             │
│   → 需要向量库查询                                               │
│                                                                 │
│ 判断结果：                                                       │
│ - 能映射的部分：城市、年龄、MBTI → 结构化查询                    │
│ - 不能映射的部分：绿茶 → 需要向量库查询                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: 结构化查询（profile + persona 表）                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 构造查询条件（只包含能映射的部分）：                        │
│ criteria = {                                                    │
│   "cities": ["北京"],                                           │
│   "age_min": 25,                                                │
│   "age_max": 30,                                                │
│   "mbti_type": ["ISFJ", "INFJ"],  ← Agent自己知道映射关系        │
│ }                                                               │
│                                                                 │
│ 查询 profile + persona 表 → 返回候选人列表（50人）               │
│                                                                 │
│ **关键**：                                                       │
│ - 这50人是结构化查询的结果                                       │
│ - 但用户还有"不要绿茶"的需求，这50人里可能包含绿茶特征的人        │
│ - 需要继续向量库查询，进一步筛选                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: 向量库查询（在结构化查询结果之上进一步筛选）              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ **关键设计**：                                                   │
│ - 向量库自动理解语义，不需要手动拆解关键词                        │
│ - 用户说"不要绿茶" → 向量库自动理解：绿茶 ≈ 表里不一、心机重、双标│
│                                                                 │
│ 向量库查询步骤：                                                 │
│                                                                 │
│ 1. 直接搜索"绿茶"语义相似的候选人                                 │
│    - 输入：用户的"绿茶"需求（语义向量）                           │
│    - 向量库自动理解语义                                          │
│    - 不需要手动拆解"绿茶 = 表里不一 + 心机重 + 双标"              │
│                                                                 │
│ 2. 在这50人中搜索                                                │
│    - similarity_threshold = 0.85                                │
│    - 找出与"绿茶"语义相似度 > 0.85 的候选人                       │
│    - 这些候选人向量库判断有绿茶特征                               │
│                                                                 │
│ 3. 排除这些候选人                                                │
│    - 候选人A：相似度 0.92 → 排除                                 │
│    - 候选人B：相似度 0.78 → 保留                                 │
│    - 候选人C：相似度 0.85 → 排除                                 │
│                                                                 │
│ 返回：筛选后的候选人列表（30人）                                  │
│                                                                 │
│ **核心价值**：                                                   │
│ - 向量库本身就能理解语义，不需要手动拆解关键词                    │
│ - 向量库是在结构化查询的50人基础上进一步筛选                      │
│ - 不是"结构化查询没结果才用向量库"                               │
│ - 是"结构化查询 + 向量库查询 = 最终结果"                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Agent 自己判断（读取完整摘要信息）                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ **关键设计**：                                                   │
│ - ❌ 不需要先拆解"绿茶 = 表里不一+心机重+双标"再去搜索            │
│ - ❌ 不需要去摘要表搜索关键词                                     │
│ - ✅ Agent读取每个候选人的完整摘要信息，自己判断                  │
│ - ❌ 不需要读聊天记录                                             │
│                                                                 │
│ Agent 获取：                                                     │
│ - 这30人的完整摘要信息（从 conversation_summaries 加载）         │
│                                                                 │
│ Agent 判断：                                                     │
│                                                                 │
│ 候选人D的完整摘要：                                              │
│   - 性格标签：表里不一、善于伪装                                  │
│   - 沟通风格：双标、含蓄                                          │
│   - 价值观：不真诚                                                │
│   → Agent看完整个摘要，自己判断：有绿茶特征 → ❌ 排除             │
│                                                                 │
│ 候选人E的完整摘要：                                              │
│   - 性格标签：真诚、直接、有原则                                  │
│   - 沟通风格：直接                                                │
│   - 价值观：重视真诚                                              │
│   → Agent看完整个摘要，自己判断：没有绿茶特征 → ✅ 推荐           │
│                                                                 │
│ 返回最终推荐结果（比如5人）                                       │
│                                                                 │
│ **核心价值**：                                                   │
│ - Agent不需要读聊天记录，只用摘要表就够了                         │
│ - Agent读取完整摘要信息，自己判断是否满足用户需求                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 核心原则

| 原则 | 描述 | 原因 |
|------|------|------|
| **Agent先判断** | Agent自己判断用户需求能否映射到结构化字段 | Agent是决策大脑，不需要Prompt指导 |
| **结构化查询优先** | 能映射的部分先用结构化查询 | 效率最高，数据库有对应字段 |
| **向量库兜底** | 不能映射的部分用向量库语义搜索 | 向量库自动理解语义，不需要手动拆解关键词 |
| **串行筛选** | 结构化查询 → 向量库查询 → Agent判断 | 逐层收窄，不是并行查询 |
| **Agent读取完整摘要** | Agent读取完整摘要信息，自己判断 | 不需要读聊天记录，只用摘要表就够了 |
| **摘要表允许负面特征** | LLM提炼时，允许提炼负面特征（方案A） | Agent才能基于完整摘要判断绿茶特征 |

### 4.3 关键设计点

#### 4.3.1 Agent判断映射策略（不需要Prompt指导）

**Agent自己知道**：
- "北京的" → profile.city
- "温柔的" → persona.mbti（可能是ISFJ、INFJ）
- "绿茶" = 表里不一 + 暗地心机重 + 双标 → 没有对应结构化字段

**不需要Prompt告诉Agent**：
- ❌ Prompt不需要写："温柔映射到ISFJ"
- ❌ Prompt不需要写："绿茶映射到表里不一、心机重"
- ✅ Agent自己理解语义（因为Agent本身就有足够的知识）

#### 4.3.2 向量库语义搜索（不需要手动拆解关键词）

**向量库自动理解语义**：
- 用户说"不要绿茶" → 向量库自动理解：绿茶 ≈ 表里不一、心机重、双标
- 不需要手动拆解"绿茶 = 表里不一 + 心机重 + 双标"
- 不需要从摘要表搜索这些关键词

**就像**：你问智能助手"找绿茶风格的人"，助手自己知道绿茶是什么意思，不需要你告诉它。

#### 4.3.3 Agent读取完整摘要（不需要读聊天记录）

**Agent判断逻辑**：
- Agent读取每个候选人的完整摘要信息（性格标签、沟通风格、价值观）
- Agent自己判断这个人的摘要是否符合用户需求（比如"绿茶"特征）
- 不需要读聊天记录

**为什么不需要读聊天记录**：
- 摘要表已经包含完整的性格信息（正面 + 负面特征）
- Agent只需要看摘要，就能判断是否满足用户需求

#### 4.3.4 摘要表字段设计：方案A（允许提炼负面特征）

**现状**：LLM提炼时，倾向提炼正面特征（温柔、内向），避免负面评价。

**问题**：用户需求可能包含负面特征（绿茶、矫情），摘要表没有这些标签。

**方案A**：LLM提炼时，允许提炼负面特征

**改动**：
- 会话结束后的LLM提炼Prompt，允许提炼负面特征
- 不只是正面特征（温柔、内向），也提炼负面特征（表里不一、心机重、双标）

**收益**：
- 摘要表包含完整性格信息（正面 + 负面）
- Agent能基于完整摘要判断绿茶特征
- 不需要读聊天记录

---

## 5. 工具设计（Agent Native 架构）

### 5.1 设计原则

| 原则 | 描述 | 现状对比 |
|------|------|---------|
| **Agent先判断** | Agent自己判断用户需求能否映射到结构化字段 | ✅ 现有架构已支持：Agent Native 模式 |
| **结构化查询优先** | 能映射的部分先用结构化查询（profile + persona表） | ✅ 现有架构已支持：Layer 1 已实现 |
| **向量库兜底** | 不能映射的部分用向量库语义搜索 | ❌ 需要集成：VectorStore未调用 |
| **串行筛选** | 结构化查询 → 向量库查询 → Agent判断 | ❌ 需要实现：当前只有结构化查询 |
| **Agent读取完整摘要** | Agent读取完整摘要信息，自己判断 | ❌ 需要实现：conversation_summaries未加载 |
| **工具调用最少化** | 一次调用返回所有信息，避免多次调用打断 Agent 思考 | ✅ 现有架构已符合：ThreadPoolExecutor 并行加载 |

### 5.2 search_partner_candidates（改进设计）

#### 核心改进

**Agent Native 模式**：Agent先判断用户需求能否映射到结构化字段，然后决定查询策略。

```python
@function_tool
def search_partner_candidates(
    criteria_json: str,
    exclude_traits_json: str = "{}",
    limit: int = 20,
) -> dict[str, Any]:
    """
    搜索候选人（结构化查询 + 向量库查询）。

    核心设计（Agent Native）：
    - Agent先判断用户需求能否映射到结构化字段
    - 能映射的部分：结构化查询（profile + persona表）
    - 不能映射的部分：向量库语义搜索
    - 返回筛选后的候选人 + 完整摘要信息

    参数：
    - criteria_json: 结构化查询条件（Agent判断能映射的部分）
      支持的字段：age_min, age_max, cities, height_min, height_max,
                  education, marital_status, income, job, mbti_type 等

    - exclude_traits_json: 需要排除的特征（Agent判断不能映射的部分）
      示例：{"traits": ["绿茶"]}
      这些特征用向量库语义搜索排除

    - limit: 返回候选人数量（默认 20，最多 50）

    返回：
    - candidates: 候选人完整信息列表
      - id: 候选人 ID
      - basic_info: 基础信息（年龄、城市、职业等）
      - persona: 用户画像（MBTI、依恋、价值观）
      - summary: 完整摘要信息 ← 新增（从 conversation_summaries 加载）

    - total: 总候选人数量
    - has_more: 是否有更多候选人
    - vector_search_used: 是否使用了向量库查询

    注意：
    - Agent先判断能否映射到结构化字段（不需要Prompt指导）
    - 向量库自动理解语义，不需要手动拆解关键词
    - Agent读取完整摘要信息，自己判断
    """
    criteria = json.loads(criteria_json)
    exclude_traits = json.loads(exclude_traits_json)
    normalized_limit = max(1, min(int(limit or 20), 50))

    # Step 1: 结构化查询（profile + persona表）
    candidates = _search_by_structured_criteria(criteria, normalized_limit * 2)

    # Step 2: 向量库查询（如果需要）
    if exclude_traits.get("traits"):
        candidates = _vector_search_exclude(candidates, exclude_traits["traits"])

    # Step 3: 加载完整摘要信息
    enriched = []
    for c in candidates[:normalized_limit]:
        candidate_data = {
            "id": c["id"],
            "basic_info": {...},
            "persona": load_persona_from_db(c["id"]),  # ← 现有逻辑
            "summary": load_complete_summary(c["id"]),  # ← 新增：完整摘要信息
        }
        enriched.append(candidate_data)

    return {
        "candidates": enriched,
        "total": len(enriched),
        "has_more": len(candidates) >= normalized_limit,
        "vector_search_used": bool(exclude_traits.get("traits")),
    }
```

#### 新增函数：_vector_search_exclude()

```python
def _vector_search_exclude(
    candidates: list[dict],
    exclude_traits: list[str],
    similarity_threshold: float = 0.85,
) -> list[dict]:
    """
    向量库语义搜索排除（Agent Native 模式）。

    核心设计：
    - 向量库自动理解语义，不需要手动拆解关键词
    - 用户说"不要绿茶" → 向量库自动理解：绿茶 ≈ 表里不一、心机重、双标
    - 在候选人列表中搜索相似度高的 → 排除

    参数：
    - candidates: 结构化查询返回的候选人列表
    - exclude_traits: 需要排除的特征列表（如 ["绿茶"]）
    - similarity_threshold: 相似度阈值（默认 0.85）

    返回：
    - filtered_candidates: 篮选后的候选人列表
    """
    from match_domain.vector_store import VectorStore

    vector_store = VectorStore()

    # 获取候选人的性格特质向量
    candidate_vectors = []
    for candidate in candidates:
        vector = vector_store.get_vector(
            user_id=candidate["id"],
            vector_type="personality_traits"
        )
        if vector:
            candidate_vectors.append({
                "id": candidate["id"],
                "vector": vector
            })

    # 搜索与exclude_traits相似度高的候选人
    # 向量库自动理解语义，不需要手动拆解关键词
    similar_users = vector_store.batch_search_similar(
        exclude_traits=exclude_traits,
        candidate_vectors=candidate_vectors,
        similarity_threshold=similarity_threshold,
    )

    # 排除相似度高的候选人
    exclude_ids = set([user["id"] for user in similar_users])
    filtered = [c for c in candidates if c["id"] not in exclude_ids]

    return filtered
```

#### 新增函数：load_complete_summary()

```python
def load_complete_summary(profile_id: int) -> dict[str, Any]:
    """
    加载完整摘要信息（Agent Native 模式）。

    核心设计：
    - 返回完整的摘要信息（性格标签、沟通风格、价值观等）
    - Agent读取完整摘要，自己判断是否满足用户需求
    - 不需要读聊天记录

    参数：
    - profile_id: 用户 ID

    返回：
    - summary: 完整摘要信息字典
      {
        "personality_traits": "性格温柔、内向、稳重",
        "communication_style": "沟通风格：直接、含蓄",
        "values": "价值观：重视家庭、真诚",
        "emotional_needs": "情感需求：需要理解和支持",
        "partner_expectation": "择偶期望：希望找个能理解工作忙碌的人",
        "life_attitude": "生活态度：追求稳定、重视生活质量",
      }

    注意：
    - 摘要信息包含正面 + 负面特征（方案A）
    - Agent读取完整摘要，自己判断是否有绿茶特征
    - 不需要去摘要表搜索关键词
    """
    from match_domain.conversation_summary_loader import query_conversation_summaries

    # 查询 conversation_summaries 表
    summaries = query_conversation_summaries(profile_id)

    # 组装完整摘要信息
    summary = {}
    for s in summaries:
        summary[s["summary_key"]] = s["summary_text"]

    return summary
```

### 5.3 Agent判断流程（不需要Prompt指导）

**Agent自己判断用户需求能否映射到结构化字段**：

```python
# Agent 思考过程（不需要Prompt指导）

用户说："我想找温柔的，北京的，25-30岁，不要绿茶的"

Agent 思考：
1. "北京的" → profile.city → ✅ 能映射
2. "25-30岁" → profile.age → ✅ 能映射
3. "温柔的" → persona.mbti？
   → Agent知道：温柔的人通常内向、友善
   → 可能是ISFJ、INFJ → ✅ 能映射
4. "不要绿茶的" → 结构化字段？
   → Agent知道：绿茶 = 表里不一 + 暗地心机重 + 双标
   → 数据库没有这些字段 → ❌ 不能映射

Agent 构造查询参数：
criteria_json = {
    "cities": ["北京"],
    "age_min": 25,
    "age_max": 30,
    "mbti_type": ["ISFJ", "INFJ"],
}
exclude_traits_json = {
    "traits": ["绿茶"],
}

Agent 调用工具：
search_partner_candidates(
    criteria_json=json.dumps(criteria_json),
    exclude_traits_json=json.dumps(exclude_traits_json),
    limit=20,
)
```

**关键**：
- Agent不需要Prompt指导映射策略
- Agent自己理解语义（温柔→ISFJ，绿茶→表里不一+心机重）
- Agent自己构造查询参数
    
    - total: 总候选人数量
    - has_more: 是否有更多候选人
    - preference_coverage: 摘要文本覆盖情况 ← 新增
      - covered_features: 摘要文本已覆盖的特征列表
      - uncovered_features: 摘要文本未覆盖的特征列表（需要 Agent 分析）
    
    注意：
    - 只返回基础信息 + 摘要文本标签，不返回聊天记录
    - Agent 需要聊天记录时，调用 load_candidate_chat_records
    - preference_coverage 告诉 Agent 还有哪些特征需要自己分析
    """
    criteria = json.loads(criteria_json)
    preferences = json.loads(preference_json)
    normalized_limit = max(1, min(int(limit or 20), 50))
    
    # Layer 1：硬约束筛选（现有逻辑）
    candidates = _search_by_hard_constraints(criteria, normalized_limit * 2)
    
    # Layer 2：摘要文本筛选（新增逻辑）
    if preferences:
        candidates = _filter_by_summary_tags(candidates, preferences)
    
    # 检查摘要文本覆盖情况
    preference_coverage = _check_summary_coverage(preferences)
    
    # 截取最终结果
    final_candidates = candidates[:normalized_limit]
    
    # 加载基础信息 + 摘要文本标签
    enriched = []
    for c in final_candidates:
        candidate_data = {
            "id": c["id"],
            "basic_info": {...},
            "persona": load_persona_from_db(c["id"]),  # ← 现有逻辑
            "summary_tags": load_summary_tags(c["id"]),  # ← 新增：从 conversation_summaries 加载
        }
        enriched.append(candidate_data)
    
    return {
        "candidates": enriched,
        "total": len(enriched),
        "has_more": len(candidates) >= normalized_limit,
        "preference_coverage": preference_coverage,
    }
```

#### 新增函数：load_summary_tags()

```python
# 文件: match_domain/summary_tags_loader.py（新增）
def load_summary_tags(profile_id: int) -> dict[str, Any]:
    """
    从 conversation_summaries 表加载摘要文本标签。
    
    核心改进：
    - 打通数据流：conversation_summaries → 搜索流程
    - 返回结构化标签，便于筛选
    
    参数：
    - profile_id: 用户 ID
    
    返回：
    - summary_tags: 摘要文本标签字典
      {
        "性格标签": ["温柔", "内向", "稳重"],
        "沟通风格": ["直接", "含蓄"],
        "价值观": ["家庭导向", "真诚"],
        "情绪倾向": ["稳定"],
        "关系期望": ["结婚导向"],
        "生活方式": ["宅家", "规律作息"],
      }
    
    注意：
    - conversation_summaries 表结构：
      - summary_key: 字段名（如 "personality_traits"）
      - summary_text: 字段内容（如 "性格温柔、内向、稳重"）
    - 需要解析 summary_text，提取标签列表
    """
    # 查询 conversation_summaries 表
    summaries = query_conversation_summaries(profile_id)
    
    # 解析摘要文本，提取标签
    summary_tags = {}
    for summary in summaries:
        key = summary["summary_key"]
        text = summary["summary_text"]
        
        # 解析文本，提取标签列表
        # 例如："性格温柔、内向、稳重" → ["温柔", "内向", "稳重"]
        tags = _parse_summary_text(key, text)
        summary_tags[key] = tags
    
    return summary_tags


def _parse_summary_text(key: str, text: str) -> list[str]:
    """
    解析摘要文本，提取标签列表。
    
    核心思路：
    - 使用简单的分词逻辑（逗号、空格分隔）
    - 或调用 LLM 提取结构化标签
    
    示例：
    - "性格温柔、内向、稳重" → ["温柔", "内向", "稳重"]
    - "重视家庭、重视事业" → ["家庭导向", "事业导向"]
    """
    # 方案 A：简单分词（逗号、空格分隔）
    tags = text.replace("性格", "").replace("重视", "").split(",")
    tags = [tag.strip() for tag in tags if tag.strip()]
    
    # 方案 B：LLM 提取（可选）
    # prompt = f"请从以下文本中提取标签列表：{text}"
    # tags = call_llm_for_tags(prompt)
    
    return tags
```

#### 新增函数：_filter_by_summary_tags()

```python
def _filter_by_summary_tags(
    candidates: list[dict],
    preferences: dict,
) -> list[dict]:
    """
    摘要文本筛选（Layer 2）。
    
    核心思路：
    - 从 conversation_summaries 加载候选人的摘要标签
    - 匹配用户要求的 exclude/include 条件
    
    参数：
    - candidates: Layer 1 篮选后的候选人列表
    - preferences: 摘要文本筛选条件
      示例：{"性格标签": {"exclude": ["绿茶"]}}
    
    返回：
    - filtered_candidates: 篮选后的候选人列表
    """
    filtered = []
    for candidate in candidates:
        # 加载候选人的摘要标签
        summary_tags = load_summary_tags(candidate["id"])
        
        # 检查是否满足筛选条件
        pass_filter = True
        for feature, condition in preferences.items():
            if "exclude" in condition:
                # 排除条件：候选人的标签不能包含 exclude 列表中的标签
                candidate_tags = summary_tags.get(feature, [])
                exclude_tags = condition["exclude"]
                
                # 检查是否有排除标签
                for exclude_tag in exclude_tags:
                    if exclude_tag in candidate_tags:
                        pass_filter = False
                        break
        
        if pass_filter:
            filtered.append(candidate)
    
    return filtered
```

### 5.4 Agent最终判断流程

**Agent读取完整摘要信息，自己判断**：

```python
# Agent 思考过程（读取完整摘要，自己判断）

工具返回：
candidates = [
    {
        "id": 101,
        "basic_info": {...},
        "persona": {...},
        "summary": {
            "personality_traits": "性格温柔、内向、稳重",
            "communication_style": "沟通风格：直接、含蓄",
            "values": "价值观：重视家庭、真诚",
            ...
        },
    },
    {
        "id": 103,
        "basic_info": {...},
        "persona": {...},
        "summary": {
            "personality_traits": "性格表里不一、善于伪装",
            "communication_style": "沟通风格：双标、含蓄",
            "values": "价值观：不真诚",
            ...
        },
    },
    ...
]

Agent 判断：

候选人 101 的完整摘要：
- 性格：温柔、内向、稳重
- 沟通风格：直接、含蓄
- 价值观：重视家庭、真诚
→ Agent看完整个摘要，自己判断：没有绿茶特征 → ✅ 推荐

候选人 103 的完整摘要：
- 性格：表里不一、善于伪装
- 沟通风格：双标、含蓄
- 价值观：不真诚
→ Agent看完整个摘要，自己判断：有绿茶特征 → ❌ 排除

Agent 返回最终结果：
DiscoveryDecision(
    phase="results_shown",
    assistant_message="给你推荐这5位，性格都比较真诚...",
    selected_candidates=[
        DiscoveryCandidateSelection(
            profile_id=101,
            reason_summary="性格温柔、真诚，没有绿茶特征",
        ),
        ...
    ],
)
```

**关键**：
- Agent读取完整摘要信息，自己判断
- 不需要去摘要表搜索关键词
- 不需要读聊天记录

### 5.5 工具调用对比

| 方案 | 工具调用次数 | Agent 工作量 |
|------|-------------|-------------|
| **旧方案（需要读聊天记录）** | 3-4 次 | 大（需要读聊天记录分析） |
| **新方案（只读摘要表）** | 1-2 次 | 小（只读完整摘要判断） |

```
旧方案：
- search_partner_candidates: 1 次（结构化查询）
- load_candidate_chat_records: 1 次（加载聊天记录）
- Agent 分析聊天记录: 纯思考
总计：2 次工具调用 + 大量思考

新方案：
- search_partner_candidates: 1 次（结构化查询 + 向量库查询 + 加载完整摘要）
- Agent 判断: 纯思考（只读摘要）
总计：1 次工具调用 + 少量思考
```

---

## 6. Agent 执行流程

### 6.1 完整流程示例

用户说："我想找温柔的，北京的，25-30岁，不要绿茶的"

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Agent 先判断能否映射到结构化字段                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 思考（不需要Prompt指导）：                                  │
│                                                                 │
│ "北京的" → profile.city → ✅ 能映射                             │
│ "25-30岁" → profile.age → ✅ 能映射                             │
│ "温柔的" → persona.mbti？→ 可能是ISFJ、INFJ → ✅ 能映射          │
│ "不要绿茶的" → 结构化字段？→ ❌ 不能映射                         │
│                                                                 │
│ Agent 构造查询参数：                                             │
│ criteria_json = {                                               │
│     "cities": ["北京"],                                         │
│     "age_min": 25,                                              │
│     "age_max": 30,                                              │
│     "mbti_type": ["ISFJ", "INFJ"],                              │
│ }                                                               │
│ exclude_traits_json = {                                         │
│     "traits": ["绿茶"],                                         │
│ }                                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: 调用 search_partner_candidates 工具                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ 工具内部执行：                                                   │
│                                                                 │
│ 1. 结构化查询（profile + persona表）                             │
│    → 查询条件：北京、25-30岁、ISFJ/INFJ                          │
│    → 返回候选人列表（50人）                                      │
│                                                                 │
│ 2. 向量库查询（语义搜索排除）                                     │
│    → 搜索"绿茶"语义相似的候选人                                  │
│    → 向量库自动理解：绿茶 ≈ 表里不一、心机重、双标                │
│    → 找出相似度 > 0.85 的候选人 → 排除                           │
│    → 剩下候选人（30人）                                          │
│                                                                 │
│ 3. 加载完整摘要信息                                              │
│    → 从 conversation_summaries 加载每个候选人的完整摘要          │
│    → 返回30人的完整信息                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Agent 读取完整摘要，自己判断                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 判断：                                                     │
│                                                                 │
│ 候选人A的完整摘要：                                              │
│   - 性格：表里不一、善于伪装 → ❌ 排除                           │
│                                                                 │
│ 候选人B的完整摘要：                                              │
│   - 性格：温柔、内向、稳重 → ✅ 推荐                             │
│                                                                 │
│ 候选人C的完整摘要：                                              │
│   - 性格：真诚、直接、有原则 → ✅ 推荐                           │
│                                                                 │
│ ...                                                              │
│                                                                 │
│ Agent 返回最终推荐结果（5人）                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Agent 决策要点

| 决策点 | Agent 责任 | 示例 |
|--------|-----------|------|
| **判断能否映射** | Agent自己判断用户需求能否映射到结构化字段（不需要Prompt指导） | "温柔"→ISFJ，"绿茶"→不能映射 |
| **构造查询参数** | Agent自己构造结构化查询参数和排除特征 | criteria_json + exclude_traits_json |
| **向量库理解语义** | 向量库自动理解语义，不需要手动拆解关键词 | "绿茶"→向量库自动理解为表里不一+心机重 |
| **读取完整摘要** | Agent读取完整摘要信息，自己判断 | 查看性格标签、价值观、沟通风格等 |
| **判断结果** | Agent直接在 decision 中返回 | 推荐/排除 + 理由摘要 |

### 6.3 与旧方案对比

| 维度 | 旧方案（需要读聊天记录） | 新方案（只读摘要表） |
|------|------------------------|-------------------|
| 工具调用次数 | 2 次（搜索 + 加载聊天记录） | 1 次（搜索 + 向量库 + 加载摘要） |
| Agent 工作量 | 大（需要读聊天记录分析） | 小（只读完整摘要判断） |
| 数据量 | 大（聊天记录） | 小（摘要文本） |
| 灵活性 | 高（Agent 能分析任何特征） | 高（摘要表包含负面特征） |
| 效率 | 低（需要读聊天记录） | 高（只用摘要表） |

---

## 7. 数据源设计
                            │ Agent 最终判断：                   │
                            │ - 通过：[101, 105, 108, 112]       │
                            │ - 排除：[103, 106, ...]（矫情）    │
                            │                                     │
                            └─────────────────────────────────────┘
                                              ↓
                            ┌─────────────────────────────────────┐
                            │ Step 3: Agent 返回判断结果         │
                            ├─────────────────────────────────────┤
                            │                                     │
                            │ DiscoveryDecision(                  │
                            │   phase="results_shown",            │
                            │   assistant_message=                │
                            │     "给你推荐这4位，性格都比较...", │
                            │   selected_candidates=[             │
                            │     DiscoveryCandidateSelection(    │
                            │       profile_id=101,               │
                            │       reason_summary="              │
                            │         情绪稳定，不矫情",          │
                            │     ),                              │
                            │     ...                             │
                            │   ],                                │
                            │ )                                   │
                            │                                     │
                            │ 总工具调用次数：                    │
                            │ - 分支 A（偏好表全覆盖）：1 次      │
                            │ - 分支 B（有未覆盖）：2 次          │
                            │                                     │
                            └─────────────────────────────────────┘
```

### 6.2 不同场景的工具调用次数

| 场景 | preference_coverage | 工具调用次数 | Agent 工作量 |
|------|---------------------|-------------|-------------|
| **场景 1**：硬约束 + 偏好表全覆盖 | uncovered_features = [] | 1 次 | 最小（只读基础信息） |
| **场景 2**：硬约束 + 偏好表部分覆盖 | uncovered_features = ["矫情"] | 2 次 | 中等（只分析未覆盖特征） |
| **场景 3**：硬约束 + 偏好表全未覆盖 | uncovered_features = ["矫情", "靠谱"] | 2 次 | 较大（需分析多个特征） |
| **场景 4**：硬约束 + 无偏好表筛选 | preference_json = "{}" | 2 次 | 最大（所有特征都自己分析） |

**结论：偏好表能覆盖的特征越多，Agent 工作量越小，工具调用越少。**

### 6.3 Agent 决策要点

| 决策点 | Agent 责任 | 示例 |
|--------|-----------|------|
| **是否需要深度分析** | 根据 preference_coverage.uncovered_features 判断 | 有未覆盖特征才需要 |
| **分析哪些候选人** | 只分析需要深度分析的候选人 | 不是所有候选人都要读聊天记录 |
| **分析方法** | Agent 自己决定如何分析 | grep 关键词频率、语气分析 |
| **判断标准** | Agent 根据用户需求调整 | 用户说"不要矫情"→判断情绪化表达 |
| **判断结果** | Agent 直接在 decision 中返回 | 不需要 submit 工具 |

### 6.4 与旧方案对比

| 维度 | 旧方案（直接给原始数据） | 新方案（三层筛选） |
|------|------------------------|-------------------|
| 工具调用次数 | 1 次（但返回大量数据） | 1-2 次（按需获取） |
| Agent 工作量 | 最大（所有特征都自己分析） | 最小到中等（偏好表先筛） |
| 数据量 | 大（所有人都有聊天记录） | 小（只有需要的人才有） |
| 效率 | 低（Agent 要读所有人） | 高（能用偏好表的先筛） |
| 灵活性 | 高（Agent 能分析任何特征） | 高（偏好表没的仍能分析） |

---

## 7. 数据源设计

### 7.1 候选人信息类型

| 信息类型 | 数据来源 | 内容描述 | 用途 |
|---------|----------|----------|------|
| **basic_info** | profile 表 | 年龄、城市、职业、学历等 | Layer 1 硬约束筛选 |
| **persona** | persona 表 | MBTI、依恋、价值观、大五人格 | 性格特质参考 |
| **preference_tags** | preference 表 | 性格标签、沟通风格、价值观等 | **Layer 2 偏好表筛选** |
| **chat_records** | chat_history 表 | 脱敏后的原始聊天记录 | Layer 3 Agent 深度分析 |
| **behavior** | behavior_log 表 | 操作记录（点赞、反馈、兴趣表达） | 活跃度、诚意判断 |
| **assessment** | assessment 表 | 测评回答内容 | 深度性格分析 |
| **introduction** | profile 表 | 自我介绍文本 | 第一印象判断 |

### 7.2 偏好表设计（新增）

**偏好表是从聊天记录离线提取的特征表，用于 Layer 2 筛选。**

```python
# 偏好表结构示例
preference_table = {
    "profile_id": 101,
    "性格标签": ["温柔", "稳重", "内向"],      # 从聊天记录提取的性格特征
    "沟通风格": ["直接", "含蓄"],              # 沟通方式
    "价值观": ["家庭导向", "真诚"],            # 价值观倾向
    "情绪倾向": ["稳定", "焦虑"],              # 情绪状态
    "关系期望": ["结婚导向", "认真恋爱"],       # 关系目标
    "生活方式": ["宅家", "规律作息"],          # 生活习惯
    "更新时间": "2026-06-01",                  # 离线提取时间
}
```

**偏好表字段来源：**

| 字段 | 提取方式 | 更新频率 |
|------|---------|---------|
| 性格标签 | AI 分析聊天记录语气、关键词 | 每周更新 |
| 沟通风格 | 分析对话主动性、回应方式 | 每周更新 |
| 价值观 | 分析话题偏好、表达的观点 | 每两周更新 |
| 情绪倾向 | 分析情绪波动、情绪化表达频率 | 每周更新 |
| 关系期望 | 分析聊天中提到的期望 | 每两周更新 |
| 生活方式 | 分析作息、兴趣爱好相关话题 | 每周更新 |

**偏好表的优势：**

| 优势 | 描述 |
|------|------|
| **查询效率高** | 已经预处理好了，直接查询 |
| **省 Agent 工作量** | 能用偏好表的先筛，不需要 Agent 读聊天记录 |
| **覆盖常见特征** | 温柔、内向、稳重等常见性格特征都有 |
| **可扩展** | 可以根据用户反馈补充新字段 |

**偏好表的局限：**

| 局限 | 描述 |
|------|------|
| **字段有限** | 无法覆盖所有用户表达（如"矫情"、"靠谱"等口语化表达） |
| **可能滞后** | 离线提取，可能跟不上用户最新状态 |
| **预设标准** | 提取时用的是预设判断标准，无法个性化 |

**解决方案：偏好表覆盖不了的，让 Agent 自己分析（Layer 3）。**

### 7.3 聊天记录加载逻辑（Layer 3）

```python
def load_and_sanitize_chat_records(profile_id: int, days: int = 30) -> list[dict]:
    """
    加载候选人的聊天记录并脱敏（Layer 3 使用）。
    
    核心原则：
    - 只在偏好表无法覆盖特征时才加载
    - 先脱敏再交给 Agent
    - Agent 自己决定如何分析
    
    参数：
    - profile_id: 候选人 ID
    - days: 时间范围（最近 N 天，默认 30 天）
    
    返回：
    - chat_records: 脱敏后的聊天记录列表
      - time: 对话时间
      - content: 脱敏后的对话内容
      - direction: 方向（发送/接收）
    
    注意：
    - 不做离线摘要预处理，避免信息失真
    - 脱敏后再交给 Agent，保护隐私
    - Agent 只用于内部分析，不返回给用户
    """
    # 查询原始聊天记录
    records = query_chat_history(profile_id, days=days)
    
    # 脱敏处理
    sanitized_records = []
    for r in records:
        sanitized_content = sanitize_chat_record(r["content"])
        sanitized_records.append({
            "time": r["created_at"],
            "content": sanitized_content,
            "direction": r["direction"],
        })
    
    return sanitized_records
```

### 7.4 偏好表 + Agent 分析的组合优势

**对比三种方案：**

| 方案 | 描述 | 问题 |
|------|------|------|
| **方案 A：只用偏好表** | 所有特征都从偏好表筛选 | 偏好表字段有限，无法覆盖"矫情"、"靠谱"等口语化表达 |
| **方案 B：只用 Agent 分析** | 所有特征都让 Agent 读聊天记录判断 | Agent 工作量大，效率低，Token 消耗高 |
| **方案 C：偏好表 + Agent 分析** | 偏好表先筛，覆盖不了的再让 Agent 分析 | **最优：效率高 + 灵活性高** |

**方案 C 的优势：**

| 优势 | 描述 |
|------|------|
| **效率最高** | 能用偏好表的先筛，省 Agent 工作量 |
| **灵活性最高** | 偏好表覆盖不了的，Agent 能自己分析 |
| **Token 消耗最小** | 只有需要深度分析的人才加载聊天记录 |
| **不失真** | Agent 分析时基于原始数据，不是二手摘要 |

### 7.5 隐私处理

#### 7.5.1 核心原则

| 原则 | 描述 |
|------|------|
| **候选人不知情** | 候选人不被告知聊天记录会被 AI 分析，避免心理负担 |
| **AI 内部处理** | 脱敏后的数据仅用于 AI 内部分析，不返回给用户 |
| **只返回判断结果** | AI 只返回判断结论（推荐/排除），不返回具体聊天内容或证据 |
| **脱敏后再读** | 聊天记录在交给 AI 之前，先做脱敏处理 |

#### 7.5.2 脱敏规则详解

| 数据类型 | 脱敏方法 | 示例 | 原因 |
|---------|---------|------|------|
| **手机号** | 保留前3后4，中间用*代替 | `138****5678` | 防止联系方式泄露 |
| **身份证号** | 保留前6后4，中间用*代替 | `3201**********1234` | 防止身份信息泄露 |
| **银行卡号** | 保留后4位，前面用*代替 | `****5678` | 防止金融信息泄露 |
| **地址** | 保留城市，具体地址用"某地"代替 | `上海市浦东新区某路某小区` → `上海市浦东新区某地` | 防止住址泄露 |
| **工作单位** | 保留行业，具体公司用"某公司"代替 | `阿里巴巴` → `互联网某公司` | 防止工作信息泄露 |
| **收入具体数字** | 转化为区间范围 | `月入15000` → `月入1-2万区间` | 防止收入信息精确泄露 |
| **真实姓名** | 用"候选人"代替 | `你好，我是张三` → `你好，我是候选人` | 防止姓名泄露 |
| **微信号/QQ号** | 完全移除 | `我的微信是abc123` → `我的微信是[已脱敏]` | 防止社交账号泄露 |
| **邮箱** | 保留域名，用户名用*代替 | `test@example.com` → `****@example.com` | 防止邮箱泄露 |
| **车牌号** | 保留省份，后面用*代替 | `沪A****56` | 防止车辆信息泄露 |

#### 7.5.3 脱敏时机与流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 聊天记录处理流程                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Step 1: 查询原始聊天记录                                        │
│         → 从数据库读取完整聊天记录                              │
│                                                                 │
│ Step 2: 脱敏处理（在交给 AI 之前）                              │
│         → 识别敏感信息（手机号、地址、身份证等）                │
│         → 按脱敏规则替换                                        │
│         → 保留对话语气、关键词频率、话题分布                    │
│                                                                 │
│ Step 3: 交给 Agent 分析                                         │
│         → Agent 读脱敏后的聊天记录                              │
│         → Agent 自己判断性格特征                                │
│                                                                 │
│ Step 4: 只返回判断结果                                          │
│         → Agent 返回判断结论（推荐/排除 + 理由摘要）            │
│         → 不返回具体聊天内容或证据                              │
│         → 用户看不到原始聊天记录                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 7.5.4 脱敏实现示例

```python
def sanitize_chat_record(content: str) -> str:
    """
    聊天记录脱敏处理。
    
    核心原则：
    - 移除/替换敏感个人信息
    - 保留对话语气、关键词频率、话题分布
    - Agent 能分析性格特征，但看不到具体隐私信息
    
    参数：
    - content: 原始聊天内容
    
    返回：
    - sanitized_content: 脱敏后的聊天内容
    """
    import re
    
    # 手机号脱敏：保留前3后4
    content = re.sub(
        r'1[3-9]\d{9}',
        lambda m: m.group()[:3] + '****' + m.group()[-4:],
        content
    )
    
    # 身份证号脱敏：保留前6后4
    content = re.sub(
        r'\d{17}[\dXx]',
        lambda m: m.group()[:6] + '********' + m.group()[-4:],
        content
    )
    
    # 地址脱敏：保留城市，具体地址替换
    content = re.sub(
        r'(上海市|北京市|深圳市|广州市|杭州市|成都市|南京市|武汉市|西安市|苏州市)[^\s]{5,}(路|街|弄|巷|号|楼|室|小区|大厦|花园)',
        lambda m: m.group(1) + '某地',
        content
    )
    
    # 银行卡号脱敏：保留后4位
    content = re.sub(
        r'\d{16,19}',
        lambda m: '****' + m.group()[-4:],
        content
    )
    
    # 收入脱敏：转化为区间
    content = re.sub(
        r'月入(\d{4,6})',
        lambda m: f'月入{int(m.group(1))/10000:.0f}-{int(m.group(1))/10000+1:.0f}万区间',
        content
    )
    
    # 微信号/QQ号脱敏：完全移除
    content = re.sub(
        r'(微信|qq|QQ|微信号|QQ号)[是为：:\s]*[\w\-]{5,20}',
        '[已脱敏]',
        content
    )
    
    # 邮箱脱敏：保留域名
    content = re.sub(
        r'[\w\.-]+@[\w\.-]+',
        lambda m: '****@' + m.group().split('@')[1],
        content
    )
    
    return content
```

#### 7.5.5 脱敏后的数据示例

```
原始聊天记录：
"你好，我是张三，今年28岁，在上海浦东新区张江高科技园区工作，
 我的手机是13812345678，月入15000，微信是zhangsan123，
 我们可以加个微信聊聊～"

脱敏后的聊天记录：
"你好，我是候选人，今年28岁，在上海某地工作，
 我的手机是138****5678，月入1-2万区间，微信是[已脱敏]，
 我们可以加个微信聊聊～"

Agent 分析时：
- 能看到语气："你好"、"我们可以聊聊" → 判断主动性
- 能看到频率："微信"出现2次 → 判断社交意愿
- 看不到隐私：手机号、地址、收入具体数字 → 保护隐私
```

#### 7.5.6 信息类型处理汇总

| 信息类型 | 隐私处理 | 返回给 Agent | 返回给用户 | 原因 |
|---------|---------|------------|-----------|------|
| **persona** | 无需脱敏 | 完整返回 | 不返回 | 用户知道会用于匹配，候选人画像不涉及具体隐私 |
| **chat_records** | 脱敏后返回 | 脱敏后的内容 | **不返回** | 保护候选人隐私，用户只能看到判断结果 |
| **behavior** | 只返回操作摘要 | 操作统计 | 不返回 | 减少信息量，不涉及隐私 |
| **assessment** | 只返回回答摘要 | 回答摘要 | 不返回 | 保护测评隐私 |
| **判断结果** | 无需脱敏 | N/A | 只返回结论 + 理由摘要 | 用户看不到具体证据，只知道判断结论 |

#### 7.5.7 隐私保护边界

| 保护对象 | 保护措施 |
|---------|---------|
| **候选人隐私** | 脱敏处理 + 候选人不知情 + 不返回具体聊天内容 |
| **用户隐私** | 用户搜索请求不透露给候选人 + 判断理由不透露给候选人 |
| **系统安全** | 脱敏规则硬编码执行，不依赖 Agent 判断 |

#### 7.5.8 用户协议表述建议

```
在用户协议/隐私政策中表述：

"系统会基于您和候选人的互动信息（包括性格画像、对话风格等）
 进行匹配推荐分析。我们会保护您和候选人的隐私信息，
 具体的联系方式、住址、收入等敏感信息不会被用于匹配分析。
 推荐结果仅反映性格匹配程度，不代表对候选人的任何评价。"

注意：
- 不明确说"聊天记录会被 AI 分析"，避免候选人心理负担
- 用"互动信息"、"对话风格"等模糊表述
- 强调隐私保护和性格匹配目的
```

**核心设计：候选人不知情，AI 内部处理，只返回判断结果。**

---

## 8. 性能优化

### 8.1 信息量对比（三层筛选 vs 直接加载）

```
假设用户说："不要绿茶的女生，不要矫情的，25-30岁，上海"

方案 A（直接加载聊天记录）：
→ 硬约束筛选：50人
→ 直接返回50人的 persona + 聊天记录
→ 50人 × 30天聊天 × 平均50条 × 平均100字 = 750,000 字
→ Token 爆炸

方案 B（三层筛选）：
→ Layer 1：硬约束筛选 → 50人
→ Layer 2：偏好表筛选（"绿茶"已筛掉）→ 30人
→ 返回30人的基础信息（不含聊天记录）→ ~15,000 字
→ preference_coverage.uncovered_features = ["矫情"]
→ Agent 决定：需要分析"矫情"
→ Layer 3：只加载需要深度分析的候选人聊天记录
→ 假设 Agent 只深入分析10人 → 10人 × 30天聊天 = 150,000 字
→ 总信息量：15,000 + 150,000 = 165,000 字
→ 比方案 A 省 5 倍
```

**关键：偏好表能覆盖的特征越多，信息量越小。**

### 8.2 Agent 自主优化策略

Agent 不需要我们预设优化策略，Agent 会自己找到高效的分析方法：

```
Agent 思考："30个人，偏好表已经筛掉了'绿茶'，只剩下'矫情'要自己分析"

Agent 策略：
1. 先看 persona：焦虑型依恋的人可能更情绪化 → 优先分析
2. 快速扫描聊天记录关键词："你是不是不爱我了"、"我哭了"
3. 发现候选人 103、106、109 有情绪化表达
4. 深入分析这3人的完整聊天记录
5. 其他27人快速判断为"无明显问题"

结果：
- 只深入分析3人 → 信息量最小
- 判断准确 → 基于一手信息
- 效率最高 → Agent 自己找最优策略
```

### 8.3 分层 limit 参数控制

```python
# Layer 1 + Layer 2 的 limit
def search_partner_candidates(
    criteria_json: str,
    preference_json: str = "{}",
    limit: int = 20,  # 默认返回 20 人，最多 50 人
):
    """
    limit 参数控制：
    - 默认返回 20 人（偏好表筛选后的结果）
    - 最多返回 50 人（避免基础信息过多）
    - Agent 可以先搜 20 人，如果筛选后不够再搜下一批
    """

# Layer 3 的 limit
def load_candidate_chat_records(
    candidate_ids: list[int],
    chat_days: int = 30,
):
    """
    只加载需要深度分析的候选人聊天记录
    Agent 自己决定要加载哪些人的聊天记录
    """
```

### 8.4 缓存策略

```python
# 偏好表缓存：
# - 偏好表数据定期更新（每周）
# - Agent 调用时直接读取缓存
# - 查询效率最高

# 聊天记录：
# - 不做预处理缓存（避免信息失真）
# - 需要时才查询数据库
# - 查询后立即脱敏再交给 Agent
```

---

## 9. 与现有架构的对比

### 9.1 核心差异

| 维度 | 现有方案 | 改进方案（三层筛选） |
|------|----------|---------------------|
| 决策位置 | 翻译层硬编码 | Agent 自主决策（Layer 3） |
| 筛选方式 | 只用硬约束 | 硬约束 + 偏好表 + Agent 分析 |
| "绿茶"处理 | 映射到数据库字段（失败） | 偏好表筛选（成功）或 Agent 分析 |
| "矫情"处理 | 无法处理 | Agent 读聊天记录自己分析 |
| 数据形态 | 无聊天记录分析 | 脱敏后的原始数据（不失真） |
| 灵活性 | 固定规则 | Agent 根据语义理解自己分析 |
| 效率 | 低（只靠硬约束） | 高（偏好表先筛 + Agent 按需分析） |
| 工具调用次数 | N/A | 1-2 次 |

### 9.2 Agent Native 程度提升

| 指标 | 现有方案 | 改进方案 |
|------|----------|----------|
| Agent 自主性 | 低（依赖翻译层） | 高（Layer 3 自主判断） |
| 决策权位置 | 查询层 | Agent 层（Layer 3） |
| 信息完整性 | 片面（只看字段） | 全面（偏好表 + 原始数据） |
| 效率 | 低 | 高（三层筛选） |
| 灵活性 | 低（固定规则） | 高（偏好表 + Agent 分析） |

### 9.3 与现有代码架构兼容

**利用现有 decision 结构：**

```python
# 现有代码（service.py）已经支持：
def _apply_runtime_result(session, runtime_result, now):
    decision = runtime_result.decision
    
    # Agent 直接在 decision 中返回判断结果
    selected_candidates = decision.selected_candidates
    
    # 渲染候选人卡片
    for selection in selected_candidates:
        cards.append(build_candidate_card(candidate, selection.reason_summary))
```

**不需要新增 submit/get 工具，直接利用现有架构。**

---

## 10. 实施路径（Agent Native 架构）

### 10.1 优先级排序（基于新方案）

| 优先级 | 改动内容 | 工作量 | 收益 | 原因 |
|-------|---------|--------|------|------|
| **P0** | 向量库集成（语义搜索排除） | 中 | 高 | 核心改进：向量库自动理解语义，不需要手动拆解关键词 |
| **P1** | 加载完整摘要信息（conversation_summaries） | 小 | 高 | Agent读取完整摘要，自己判断 |
| **P2** | 摘要表允许负面特征（方案A） | 小 | 高 | 摘要表包含负面特征，Agent才能判断绿茶特征 |
| **P3** | Agent判断流程优化（不需要Prompt指导） | 小 | 中 | Agent自己判断能否映射到结构化字段 |

### 10.2 Phase 0：向量库集成（核心改进）

| 改动 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| 新增函数 | `_vector_search_exclude()` | `match_domain/vector_filter.py` | 中 |
| 修改函数 | `search_partner_candidates_with()` 集成向量库 | `service_integrations.py` | 中 |
| 新增方法 | `VectorStore.batch_search_similar()` | `match_domain/vector_store.py` | 小 |

**核心改动**：

```python
# 文件: match_domain/vector_filter.py
# 新增：向量库语义搜索排除
def _vector_search_exclude(
    candidates: list[dict],
    exclude_traits: list[str],
    similarity_threshold: float = 0.85,
) -> list[dict]:
    """
    向量库语义搜索排除（Agent Native 模式）。

    核心设计：
    - 向量库自动理解语义，不需要手动拆解关键词
    - 用户说"不要绿茶" → 向量库自动理解：绿茶 ≈ 表里不一、心机重、双标
    - 在候选人列表中搜索相似度高的 → 排除

    注意：
    - 不需要先从摘要表搜索关键词
    - 不需要手动拆解"绿茶 = 表里不一 + 心机重 + 双标"
    - 向量库本身就能理解语义
    """
    from match_domain.vector_store import VectorStore

    vector_store = VectorStore()

    # 获取候选人的性格特质向量
    candidate_vectors = []
    for candidate in candidates:
        vector = vector_store.get_vector(
            user_id=candidate["id"],
            vector_type="personality_traits"
        )
        if vector:
            candidate_vectors.append({
                "id": candidate["id"],
                "vector": vector
            })

    # 搜索与exclude_traits相似度高的候选人
    # 向量库自动理解语义
    similar_users = vector_store.batch_search_similar(
        exclude_traits=exclude_traits,
        candidate_vectors=candidate_vectors,
        similarity_threshold=similarity_threshold,
    )

    # 排除相似度高的候选人
    exclude_ids = set([user["id"] for user in similar_users])
    filtered = [c for c in candidates if c["id"] not in exclude_ids]

    return filtered
```

**收益**：
- 向量库自动理解语义，不需要手动拆解关键词
- 用户说"不要绿茶" → 向量库自动理解绿茶的含义 → 排除
- 真正的 Agent Native：不需要硬编码规则表

### 10.3 Phase 1：加载完整摘要信息

| 改动 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| 新增函数 | `load_complete_summary()` | `match_domain/conversation_summary_loader.py` | 小 |
| 修改函数 | `search_partner_candidates_with()` 加载完整摘要 | `service_integrations.py` | 小 |

**核心改动**：

```python
# 文件: match_domain/conversation_summary_loader.py
# 新增：加载完整摘要信息
def load_complete_summary(profile_id: int) -> dict[str, Any]:
    """
    加载完整摘要信息（Agent Native 模式）。

    核心设计：
    - 返回完整的摘要信息（性格标签、沟通风格、价值观等）
    - Agent读取完整摘要，自己判断是否满足用户需求
    - 不需要读聊天记录

    注意：
    - Agent不是去摘要表搜索关键词
    - Agent读取完整摘要，自己判断
    - 摘要信息包含正面 + 负面特征（方案A）
    """
    from match_domain.conversation_summary_loader import query_conversation_summaries

    # 查询 conversation_summaries 表
    summaries = query_conversation_summaries(profile_id)

    # 组装完整摘要信息
    summary = {}
    for s in summaries:
        summary[s["summary_key"]] = s["summary_text"]

    return summary
```

**收益**：
- Agent读取完整摘要，自己判断是否满足用户需求
- 不需要去摘要表搜索关键词
- 不需要读聊天记录

### 10.4 Phase 2：摘要表允许负面特征（方案A）

| 改动 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| 修改Prompt | 会话结束后的LLM提炼Prompt | `match_domain/session_end_processor.py` | 小 |
| 允许负面特征 | 不只是正面特征，也提炼负面特征 | `match_domain/session_end_processor.py` | 小 |

**核心改动**：

```python
# 文件: match_domain/session_end_processor.py
# 修改：generate_structured_summary() 的 Prompt

# 旧Prompt（只提炼正面特征）：
# "请从聊天记录中提炼性格特质：温柔、内向、稳重等"

# 新Prompt（允许提炼负面特征）：
# "请从聊天记录中提炼完整的性格特质：
#  - 正面特征：温柔、内向、稳重、真诚等
#  - 负面特征：表里不一、心机重、双标、过于迎合等
#  不要回避负面评价，客观提炼所有特征"
```

**收益**：
- 摘要表包含完整性格信息（正面 + 负面）
- Agent能基于完整摘要判断绿茶特征
- 不需要读聊天记录

### 10.5 Phase 3：工具设计优化

| 改动 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| 修改工具 | `search_partner_candidates()` 改为新设计 | `service_integrations.py` | 中 |
| 新增参数 | `exclude_traits_json` | `service_integrations.py` | 小 |

**核心改动**：

```python
# 文件: service_integrations.py
# 修改：search_partner_candidates_with()
def search_partner_candidates_with(
    criteria_json: str,
    exclude_traits_json: str = "{}",  # ← 新增参数
    limit: int = 20,
) -> dict[str, Any]:
    """
    搜索候选人（Agent Native 模式）。

    核心设计：
    - Agent先判断用户需求能否映射到结构化字段（不需要Prompt指导）
    - 能映射的部分：结构化查询（profile + persona表）
    - 不能映射的部分：向量库语义搜索
    - 返回完整摘要信息，Agent自己判断
    """
    criteria = json.loads(criteria_json)
    exclude_traits = json.loads(exclude_traits_json)

    # Step 1: 结构化查询（profile + persona表）
    candidates = _search_by_structured_criteria(criteria, limit * 2)

    # Step 2: 向量库查询（如果需要）
    if exclude_traits.get("traits"):
        candidates = _vector_search_exclude(candidates, exclude_traits["traits"])

    # Step 3: 加载完整摘要信息
    enriched = []
    for c in candidates[:limit]:
        candidate_data = {
            "id": c["id"],
            "basic_info": {...},
            "persona": load_persona_from_db(c["id"]),
            "summary": load_complete_summary(c["id"]),  # ← 新增：完整摘要
        }
        enriched.append(candidate_data)

    return {
        "candidates": enriched,
        "total": len(enriched),
        "has_more": len(candidates) >= limit,
        "vector_search_used": bool(exclude_traits.get("traits")),
    }
```

**收益**：
- 工具返回完整摘要信息，Agent自己判断
- 不需要多次工具调用
- Agent Native 模式：Agent是决策大脑

### 10.6 Phase 4：测试验证

| 测试 | 内容 | 工作量 |
|------|------|--------|
| 向量库语义搜索测试 | 验证向量库能否正确理解"绿茶"语义 | 中 |
| Agent判断流程测试 | 验证Agent能否正确判断用户需求能否映射 | 中 |
| 完整摘要加载测试 | 验证conversation_summaries数据加载是否正确 | 小 |
| Agent最终判断测试 | 验证Agent能否正确读取完整摘要并判断 | 中 |
| 性能测试 | 测试性能、向量库搜索效率 | 中 |
| 准确性对比 | 对比"只结构化查询"、"结构化+向量库"、"完整方案"的准确性 | 中 |
    """
    vector_store = VectorStore()

    filtered = []
    for candidate in candidates:
        # 获取候选人的性格特质向量
        candidate_vector = vector_store.get_vector(
            user_id=candidate["id"],
            vector_type="personality_traits"
        )

        # 计算相似度
        similarity = cosine_similarity(exclude_vector, candidate_vector)

        # 排除相似度高的用户
        if similarity < similarity_threshold:
            filtered.append(candidate)

    return filtered
```

**收益**：
- 向量搜索能处理更复杂的语义匹配
- 例如"找个跟我很像的人"、"找个性格互补的人"

**问题**：
- 需要"绿茶"的向量表示（如何获取？）
- 向量搜索是"找相似"，反向过滤逻辑需要设计

### 10.5 Phase 3：Agent 深度分析（Layer 3）

| 改动 | 内容 | 文件 | 工作量 |
|------|------|------|--------|
| 新增工具 | `load_candidate_chat_records()` | `match_domain/chat_records_loader.py` | 小 |
| 脱敏处理 | `sanitize_chat_record()` | `match_domain/chat_sanitizer.py` | 小 |
| Agent Prompt | 添加三层筛选使用指南 | `SOUL.md` | 小 |

**核心改动**：

```python
# 文件: match_domain/chat_records_loader.py
# 新增：加载候选人聊天记录
@function_tool
def load_candidate_chat_records(
    candidate_ids: list[int],
    chat_days: int = 30,
) -> dict[str, Any]:
    """
    加载候选人聊天记录（用于 Agent 淡度分析）。

    核心设计：
    - 只加载需要深度分析的候选人的聊天记录
    - 聊天记录已脱敏处理
    - Agent 自己决定如何分析

    注意：
    - 只在 preference_coverage.uncovered_features 不为空时调用
    - Agent 自己决定分析方法（grep关键词、语气分析）
    """
    enriched = []
    for candidate_id in candidate_ids:
        # 加载聊天记录并脱敏
        chat_records = load_and_sanitize_chat_records(candidate_id, days=chat_days)
        enriched.append({
            "id": candidate_id,
            "chat_records": chat_records,
        })

    return {"candidates_chat": enriched}
```

**收益**：
- 处理口语化表达（"矫情"、"靠谱"、"能过日子"）
- Agent 基于一手信息判断，不失真
- 灵活性最高

### 10.6 Phase 4：Agent Prompt 优化

| 改动 | 内容 | 工作量 |
|------|------|--------|
| SOUL.md 更新 | 添加三层筛选使用指南、分析方法示例 | 小 |
| 分层搜索策略 | Prompt 中引导 Agent 根据 preference_coverage 决定是否深度分析 | 小 |
| 分析策略示例 | 描述常见分析方法（grep 关键词、频率统计、语气分析） | 小 |

**Prompt 改动示例**：

```markdown
# SOUL.md 新增内容

## 三层筛选策略

当用户搜索候选人时，使用以下策略：

### Layer 1 + Layer 2 篮选结果判断

search_partner_candidates 返回 preference_coverage：
- covered_features: 摘要文本已覆盖的特征（如 ["性格标签"]）
- uncovered_features: 摘要文本未覆盖的特征（如 ["矫情"]）

**决策规则**：
- 如果 uncovered_features 为空 → 不需要深度分析，直接推荐
- 如果 uncovered_features 不为空 → 需要深度分析

### Layer 3 深度分析策略

当 preference_coverage.uncovered_features 不为空时：

1. 调用 load_candidate_chat_records(candidate_ids) 加载聊天记录
2. 自己决定分析方法：
   - grep 关键词频率：统计"你好棒"、"你是不是不爱我了" 出现次数
   - 语气分析：判断是真诚鼓励还是过度迎合
   - 情绪波动检测：检测是否有频繁的情绪化表达
3. 返回判断结果（推荐/排除 + 理由摘要）

**注意**：
- 不需要分析所有人的聊天记录
- 优先分析 persona 可疑的人（如焦虑型依恋可能更情绪化）
- 只分析 uncovered_features 涉及的特征
```

### 10.7 Phase 5：测试验证

| 测试 | 内容 | 工作量 |
|------|------|--------|
| 数据流验证 | 验证 conversation_summaries 数据加载是否正确 | 小 |
| Layer 2 篮选验证 | 验证摘要文本筛选逻辑是否正确 | 中 |
| Agent 决策验证 | 验证 Agent 是否正确使用三层筛选策略 | 中 |
| 性能测试 | 测试性能、隐私边界、脱敏效果 | 中 |
| 准确性对比 | 对比"只用硬约束"、"Layer 2筛选"、"三层筛选"的准确性 | 中 |

---

## 11. 风险与缓解

### 11.1 性能风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 摘要文本解析慢 | 解析 summary_text 提取标签可能慢 | 使用简单分词逻辑（逗号分隔）或 LLM 异步提取 |
| Layer 2 篮选慢 | 需要加载所有候选人的摘要标签 | LRU 缓存优化（与 load_traits_for_discovery 相同） |
| Agent 分析过多 | preference_coverage.uncovered_features 很多 | Agent 自己优化策略（只分析可疑候选人） |
| Token 消耗 | Layer 3 加载聊天记录可能较长 | 分层加载，只加载需要的人 |

### 11.2 数据风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 摘要文本滞后 | conversation_summaries 是离线提取，可能滞后 | 定期更新（每周）+ Agent 深度分析兜底 |
| 摘要文本不准确 | LLM 提炼的摘要可能不准确 | Agent 深度分析验证 + 用户反馈修正 |
| 摘要文本字段不够 | 无法覆盖新出现的特征 | 持续扩充字段 + Agent 深度分析兜底 |

### 11.3 隐私风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 聊天记录隐私 | 候选人不知道会被分析 | 候选人不知情 + 脱敏处理 + 只返回判断结果 |
| 判断结果公开 | Agent 判断理由可能不当 | Agent 生成解释时要审慎 + 用户协议表述模糊化 |

### 11.4 Agent 判断风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 判断不一致 | 不同 Agent 判断可能不同 | 允许一定不一致 + Prompt 提供分析指南（不强制） |
| 判断偏差 | Agent 可能有偏见 | 伦理审查 + 判断依据标注 |
| 分析策略不够好 | Agent 可能用不够好的分析方法 | Prompt 提供分析方法示例（参考，不强制） |

### 11.5 向量搜索风险（可选）

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 向量表示缺失 | "绿茶"等口语化表达没有标准向量表示 | 使用摘要文本筛选兜底 + Agent 深度分析兜底 |
| 向量搜索反向逻辑复杂 | 向量搜索是"找相似"，反向过滤逻辑需要设计 | 设计相似度阈值 + 排除逻辑 |
| 向量维度不匹配 | 不同向量类型的维度可能不一致 | 统一使用 1024 维向量（text-embedding-v3） |

---

## 12. 总结

### 12.1 核心改进

**从"只靠硬约束"转向"三层筛选架构"**

```
用户说："不要绿茶的女生，不要矫情的，25-30岁，上海"

现有方案（只靠硬约束）：
→ 翻译层映射："绿茶" → 数据库字段（不存在）→ 失败
→ 只能靠年龄、城市筛选 → 无法满足性格需求

改进方案（三层筛选）：
→ Layer 1：硬约束筛选（年龄、城市）→ 50人
→ Layer 2：偏好表筛选（"绿茶"标签排除）→ 30人
→ Layer 3：Agent 自己分析（"矫情"偏好表没有）→ 最终推荐5人

结果：
- 能用偏好表的先筛（效率高）
- 偏好表覆盖不了的让 Agent 自己分析（灵活性高）
- Agent 基于一手信息判断（不失真）
```

### 12.2 关键价值

| 价值点 | 描述 |
|--------|------|
| **三层筛选，效率最高** | 硬约束 → 偏好表 → Agent 分析，逐层收窄 |
| **偏好表优先，省 Agent 工作量** | 能用预处理数据的先筛，不需要 Agent 读聊天记录 |
| **Agent 只处理无法预处理的部分** | 偏好表覆盖不了的特征才让 Agent 自己分析 |
| **给 Agent 原始数据，不失真** | 需要 Agent 分析时，返回脱敏后的原始数据 |
| **Agent 自己分析，灵活度高** | Agent 自己决定分析方法，比预设规则更智能 |
| **Agent Native 程度更高** | Agent 是真正的决策大脑（Layer 3），基于一手信息自主判断 |
| **工具调用极简** | 1-2 次调用，不需要 submit/get 工具 |
| **与现有架构兼容** | 利用 decision.selected_candidates 表达判断结果 |

### 12.3 下一步

1. **确认方案**：与团队确认三层筛选改进方案可行性
2. **偏好表设计**：设计偏好表字段和离线提取逻辑
3. **工具改造**：改造 search_partner_candidates 为 Layer 1 + Layer 2 筛选
4. **新增工具**：新增 load_candidate_chat_records 用于 Layer 3 深度分析
5. **脱敏处理**：实现聊天记录脱敏处理模块
6. **Agent Prompt**：更新 SOUL.md 添加三层筛选使用指南
7. **测试验证**：对比"只用偏好表"、"只用 Agent"、"三层筛选"的效率和准确性

| 改动 | 内容 | 工作量 |
|------|------|--------|
| 聊天记录查询接口 | 直接查询原始聊天记录，不做摘要预处理 | 小 |
| persona 加载优化 | persona 数据定期更新，Agent 调用时直接读取 | 小 |

