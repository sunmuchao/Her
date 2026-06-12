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

### 1.2 根因分析

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

## 4. 改进方案设计

### 4.1 核心思路

```
用户说："不要绿茶的女生，25-30岁，上海"

Step 1: 硬约束筛选 + 直接返回完整信息
        → criteria = {"age_min": 25, "age_max": 30, "cities": ["上海"]}
        → SQL WHERE 子句查询
        → 返回候选人大池子（20-50 人）
        → 直接返回完整信息（persona + 原始聊天记录）
        → 不做离线摘要预处理

Step 2: Agent 自主分析判断（纯思考，不调用工具）
        → Agent 读每个候选人的 persona + 聊天记录
        → Agent 自己决定分析方法（如 grep 关键词频率、语气分析）
        → Agent 自己判断："这个人'你好棒'出现 5 次，过于迎合" → exclude
        → Agent 自己判断："这个人说话直接，有自己的观点" → pass

Step 3: Agent 直接在 decision 中返回结果
        → 不需要 submit 工具
        → 直接通过 decision.selected_candidates 返回判断结果
        → 利用现有架构，不新增状态管理工具
```

### 4.2 核心原则

| 原则 | 描述 | 原因 |
|------|------|------|
| **给 Agent 原始数据** | 直接返回 persona + 聊天记录，不做预处理 | 离线摘要会失真，Agent 应基于一手信息判断 |
| **Agent 自己分析** | Agent 自己决定分析方法（grep、频率统计、语气分析） | Agent 比预设规则更智能，能找到更准确的分析策略 |
| **判断不调用工具** | Agent 判断是纯思考，直接在 decision 中返回结果 | 避免 submit 工具打断思考，减少工具调用次数 |
| **利用现有架构** | 用 decision.selected_candidates 表达判断结果 | 不新增状态管理工具，与现有代码兼容 |

### 4.3 为什么不用离线摘要？

**离线摘要的问题：**

```
假设候选人 A 的聊天记录：

[第1天] 女：你真棒！辛苦了～
[第5天] 女：你好厉害！你是最棒的！
[第10天] 女：你真好！和你在一起真开心～
[第15天] 女：你最好了～我会想你的～

离线生成的摘要可能写成：
"对话氛围良好，女方表达关心和鼓励，互动积极。"

问题：
1. 摘要把"你真棒"、"你好厉害"总结成"表达关心"
2. 丢失了关键信息：这些话出现的频率和上下文
3. Agent 读摘要只能看到"氛围良好"，判断不出"绿茶"
4. 摘要的判断标准是预设的，无法根据用户具体需求调整

正确做法：给 Agent 原始聊天记录
Agent 自己分析：
"统计'你真棒'出现 5 次，'你好厉害'出现 3 次
 这些话密集出现，都是高度赞扬
 且都是在回应日常分享时使用，没有自己的观点
 结合 persona（焦虑型依恋）判断：有绿茶特征"
```

### 4.4 Agent 可能的分析策略

Agent 不需要我们预设分析工具，Agent 会自己找到分析方法：

| 分析策略 | Agent 可能的做法 | 适用场景 |
|---------|-----------------|---------|
| **关键词频率统计** | grep "你好棒"、"你好厉害" 出现次数 | 判断"绿茶"、"讨好型" |
| **语气分析** | 分析对话语气是真诚鼓励还是过度迎合 | 判断性格特质 |
| **对比分析** | 对比不同话题的回应方式 | 判断是否有自己的观点 |
| **时间分布分析** | 看关键词是否密集出现在特定时间段 | 判断行为模式 |
| **自我观点检测** | 检查是否表达自己的观点还是只讨好 | 判断"真诚"、"独立" |
| **结合 persona 综合** | 结合 MBTI、依恋类型判断性格倾向 | 综合判断 |

---

## 5. 工具设计

### 5.1 设计原则

| 原则 | 描述 |
|------|------|
| **工具只返回原始数据** | 不做预处理、不做摘要、不给 Agent 二手信息 |
| **工具不管理状态** | 不需要 submit/get 工具，用 decision 结构表达结果 |
| **工具调用最少化** | 一次调用返回所有信息，避免多次调用打断 Agent 思考 |

### 5.2 search_partner_candidates（硬约束筛选 + 直接返回完整信息）

```python
@function_tool
def search_partner_candidates(
    criteria_json: str,
    limit: int = 10,
    include_chat: bool = True,
    chat_days: int = 30,
) -> dict[str, Any]:
    """
    搜索候选人（硬约束筛选 + 直接返回完整信息）。
    
    核心设计：
    - 硬约束筛选：根据 criteria 进行数据库查询
    - 直接返回完整信息：persona + 原始聊天记录（不做摘要预处理）
    - Agent 自己分析：Agent 自己决定如何分析聊天记录
    
    参数：
    - criteria_json: 硬约束条件（JSON）
      支持的字段：age_min, age_max, cities, height_min, height_max,
                  education, marital_status, income, job, relationship_goal 等
    
    - limit: 返回候选人数量（默认 10，最多 20）
    
    - include_chat: 是否包含聊天记录（默认 True）
    
    - chat_days: 聊天记录时间范围（最近 N 天，默认 30 天）
    
    返回：
    - candidates: 候选人完整信息列表
      - id: 候选人 ID
      - basic_info: 基础信息（年龄、城市、职业等）
      - persona: 用户画像（MBTI、依恋、价值观、大五人格）
      - chat_records: 原始聊天记录（不做摘要预处理）
    
    - total: 总候选人数量
    - has_more: 是否有更多候选人
    
    注意：
    - 直接返回原始聊天记录，不做离线摘要预处理
    - Agent 自己决定如何分析聊天记录（grep 关键词、频率统计、语气分析等）
    - 判断结果通过 decision.selected_candidates 返回，不需要 submit 工具
    """
    criteria = json.loads(criteria_json)
    normalized_limit = max(1, min(int(limit or 10), 20))  # 硬约束：最多返回 20 人
    
    # 执行硬约束筛选
    candidates = _search_by_hard_constraints(criteria, normalized_limit)
    
    # 为每个候选人加载完整信息（不做摘要预处理）
    enriched = []
    for c in candidates:
        candidate_data = {
            "id": c["id"],
            "basic_info": {
                "age": c["age"],
                "city": c["city"],
                "job": c.get("job"),
                "education": c.get("education"),
                "relationship_goal": c.get("relationship_goal"),
                "marital_status": c.get("marital_status"),
                "height": c.get("height"),
            },
            "persona": load_persona_from_db(c["id"]),
        }
        
        # 直接返回原始聊天记录，不做摘要预处理
        if include_chat:
            chat_records = load_chat_records(c["id"], days=chat_days)
            candidate_data["chat_records"] = chat_records
        
        enriched.append(candidate_data)
    
    return {
        "candidates": enriched,
        "total": len(enriched),
        "has_more": len(candidates) >= normalized_limit,
    }
```

### 5.3 可选辅助工具：search_chat_keywords（帮助 Agent 快速定位）

**注意：这是可选辅助工具，Agent 可以选择用或不用。**

```python
@function_tool
def search_chat_keywords(
    candidate_id: int,
    keywords: list[str],
    chat_days: int = 30,
) -> dict[str, Any]:
    """
    搜索候选人聊天记录中的关键词。
    
    这是可选辅助工具，帮助 Agent 快速定位关键对话。
    Agent 也可以选择直接读完整聊天记录自己分析。
    
    参数：
    - candidate_id: 候选人 ID
    - keywords: 要搜索的关键词列表（如 ["你真棒", "你好厉害", "你最好了"]）
    - chat_days: 时间范围（最近 N 天）
    
    返回：
    - candidate_id: 候选人 ID
    - keyword_counts: 每个关键词的出现次数
    - matches: 匹配的对话片段列表（包含上下文）
    - total_matches: 总匹配次数
    
    用法示例：
    - Agent 判断"绿茶"时，可以先用此工具快速 grep "你真棒" 出现次数
    - 发现高频使用后，再决定要不要深入读完整聊天记录分析语气
    """
    chat_records = load_chat_records(candidate_id, days=chat_days)
    
    keyword_counts = {}
    matches = []
    
    for keyword in keywords:
        keyword_counts[keyword] = 0
        for record in chat_records:
            content = str(record.get("content") or "")
            if keyword in content:
                keyword_counts[keyword] += 1
                # 提取关键词周围的上下文
                context = extract_context(content, keyword, context_chars=50)
                matches.append({
                    "time": record.get("time"),
                    "keyword": keyword,
                    "context": context,
                    "full_content": content,
                })
    
    return {
        "candidate_id": candidate_id,
        "keyword_counts": keyword_counts,
        "matches": matches,
        "total_matches": sum(keyword_counts.values()),
    }
```

### 5.4 判断结果表达：利用现有 decision 结构

**不需要新增 submit/get 工具，直接利用现有架构。**

```python
# 现有架构已经支持：DiscoveryDecision

@dataclass
class DiscoveryDecision:
    phase: str  # "results_shown" / "no_result" / "collecting_preferences"
    assistant_message: str  # Agent 给用户的回复
    criteria_labels: list[str]  # 提取的条件标签
    selected_candidates: list[DiscoveryCandidateSelection]  # 判断结果
    suggested_actions: list[DiscoveryActionSuggestion]  # 建议操作

@dataclass
class DiscoveryCandidateSelection:
    profile_id: int  # 候选人 ID
    reason_summary: str  # Agent 判断的理由

# Agent 用法：
# Agent 在思考中完成判断，直接在 decision 中返回结果
# 不需要调用 submit 工具

decision = DiscoveryDecision(
    phase="results_shown",
    assistant_message="给你推荐这5位，性格都比较真诚直接...",
    selected_candidates=[
        DiscoveryCandidateSelection(
            profile_id=101,
            reason_summary="说话有自己的观点，不迎合讨好",
        ),
        DiscoveryCandidateSelection(
            profile_id=103,
            reason_summary="'你真棒'只出现1次，频率正常，性格真诚",
        ),
        # Agent 判断排除的候选人不会出现在这里
    ],
)
```

### 5.5 工具调用对比

| 方案 | 工具调用次数 | 问题 |
|------|-------------|------|
| **旧方案（离线摘要 + submit）** | 40-60 次/20人 | 工具调用过多，Agent 思考被打断 |
| **新方案（直接返回原始数据）** | 1-2 次/20人 | Agent 一次获取信息，一次思考完成判断 |

```
旧方案：
- search_partner_candidates: 1 次（只返回 ID）
- load_candidate_full_info: 20 次（每人 1 次）
- submit_candidate_judgment: 20 次（每人 1 次）
- get_filtered_candidates: 1 次
总计：42 次

新方案：
- search_partner_candidates: 1 次（返回完整信息）
- search_chat_keywords: 可选，Agent 决定要不要用
总计：1-2 次
```

---

## 6. Agent 执行流程

### 6.1 典型场景流程

用户说："不要绿茶的女生，25-30岁，上海"

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: 获取候选人完整信息（一次调用）                           │
├─────────────────────────────────────────────────────────────────┤
│ Agent 调用：search_partner_candidates                           │
│ 参数：criteria_json = {"age_min": 25, "age_max": 30,            │
│                       "cities": ["上海"]}                       │
│       include_chat = True                                       │
│       chat_days = 30                                            │
│                                                                 │
│ 返回：candidates = [                                            │
│   {                                                             │
│     "id": 101,                                                  │
│     "basic_info": {"age": 28, "city": "上海", "job": "财务"},   │
│     "persona": {                                                │
│       "attachment": {"type_code": "secure"},                    │
│       "mbti": {"type_code": "ISFJ"},                            │
│     },                                                          │
│     "chat_records": [                                           │
│       {"time": "第1天", "content": "你真棒！辛苦了～"},          │
│       {"time": "第5天", "content": "你觉得这个怎么样？"},        │
│       {"time": "第10天", "content": "我最近在看..."},           │
│       ...                                                       │
│     ],                                                          │
│   },                                                            │
│   {                                                             │
│     "id": 102,                                                  │
│     "basic_info": {"age": 29, "city": "上海", "job": "销售"},   │
│     "persona": {                                                │
│       "attachment": {"type_code": "anxious"},                   │
│     },                                                          │
│     "chat_records": [                                           │
│       {"time": "第1天", "content": "你真棒！你是最棒的！"},      │
│       {"time": "第3天", "content": "你好厉害！你太厉害了！"},    │
│       {"time": "第5天", "content": "你最好了～我会想你的～"},    │
│       {"time": "第7天", "content": "你真棒！"},                  │
│       {"time": "第10天", "content": "你好厉害！你是最棒的！"},   │
│       ...                                                       │
│     ],                                                          │
│   },                                                            │
│   ... (共20人，每人都有 persona + 原始聊天记录)                  │
│ ]                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Agent 自主分析判断（纯思考，不调用工具）                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 读候选人 101：                                            │
│ - persona: 安全型依恋（稳定）                                   │
│ - chat_records: 读完整聊天记录                                  │
│   Agent 自己分析：                                              │
│   - "你真棒"只出现1次，频率正常                                 │
│   - 有主动分享生活，有自己的观点                                │
│   - 语气是真诚鼓励，不是过度迎合                                │
│ - 判断：✅ 这个人真诚，不像绿茶                                 │
│                                                                 │
│ Agent 读候选人 102：                                            │
│ - persona: 焦虑型依恋（可能不够稳定）                           │
│ - chat_records: 读完整聊天记录                                  │
│   Agent 自己分析：                                              │
│   - grep "你真棒"、"你好厉害"、"你最好了"                       │
│   - 发现：'你真棒'出现5次，'你好厉害'出现3次，'你最好了'出现2次 │
│   - 10天内出现10次高度赞扬，频率明显过高                        │
│   - 都是回应日常分享，没有自己的观点                            │
│   - 语气是过度迎合讨好，不是真诚鼓励                            │
│ - 判断：❌ 这个人过于迎合，有绿茶特征                           │
│                                                                 │
│ Agent 继续读剩下 18 个人...                                     │
│                                                                 │
│ Agent 最终判断：                                                │
│ - 通过：[101, 103, 105, 108, 112, 116]                          │
│ - 排除：[102, 106, 109, ...]（过于迎合或性格不符）              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Agent 直接在 decision 中返回结果                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 返回（不需要调用 submit 工具）：                          │
│                                                                 │
│ DiscoveryDecision(                                              │
│     phase="results_shown",                                      │
│     assistant_message="给你推荐这5位，性格都比较真诚直接...",   │
│     selected_candidates=[                                       │
│         DiscoveryCandidateSelection(                            │
│             profile_id=101,                                     │
│             reason_summary="说话有自己的观点，不迎合讨好",      │
│         ),                                                      │
│         DiscoveryCandidateSelection(                            │
│             profile_id=103,                                     │
│             reason_summary="'你真棒'只出现1次，频率正常",       │
│         ),                                                      │
│         DiscoveryCandidateSelection(                            │
│             profile_id=105,                                     │
│             reason_summary="性格安全型依恋，稳定真诚",          │
│         ),                                                      │
│         ...                                                     │
│     ],                                                          │
│ )                                                               │
│                                                                 │
│ 完成！不需要 submit/get 工具                                    │
│ 总工具调用次数：1 次                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Agent 可选使用辅助工具

**Agent 可以选择用或不用 search_chat_keywords 工具。**

```
┌─────────────────────────────────────────────────────────────────┐
│ 可选 Step: Agent 使用辅助工具快速定位                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Agent 思考："20个人的聊天记录太长，我先快速扫描一下"            │
│                                                                 │
│ Agent 调用：search_chat_keywords                                │
│ 参数：candidate_id=102                                          │
│       keywords=["你真棒", "你好厉害", "你最好了"]               │
│                                                                 │
│ 返回：keyword_counts = {                                        │
│         "你真棒": 5,                                            │
│         "你好厉害": 3,                                          │
│         "你最好了": 2                                           │
│       }                                                         │
│       total_matches = 10                                        │
│                                                                 │
│ Agent 判断："10天内出现10次高度赞扬，频率明显过高"              │
│ Agent 决定："深入读完整聊天记录分析语气"                        │
│ Agent 最终判断："过度迎合，有绿茶特征"                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Agent 决策要点

| 决策点 | Agent 责任 | 示例 |
|--------|-----------|------|
| **分析方法** | Agent 自己决定如何分析 | grep 关键词频率、语气分析、对比分析 |
| **分析深度** | Agent 自己决定深入程度 | 先快速扫描，发现有问题的再深入看 |
| **判断标准** | Agent 根据用户需求调整 | 用户说"不要绿茶"→判断"过度迎合" |
| **判断结果** | Agent 直接在 decision 中返回 | 不需要 submit 工具 |
| **推荐理由** | Agent 自己提供解释 | "这个人说话有自己的观点，不迎合讨好" |

### 6.4 与旧方案对比

| 维度 | 旧方案（离线摘要 + submit） | 新方案（原始数据 + decision） |
|------|---------------------------|------------------------------|
| 工具调用次数 | **42 次** | **1 次** |
| Agent 思考被打断 | **40 次** | **0 次** |
| 数据形态 | 二手信息（摘要） | 一手信息（原始数据） |
| 判断准确性 | 可能失真（摘要丢失细节） | 准确（Agent 自己分析） |
| Agent 自主权 | 低（依赖摘要） | 高（自己分析原始数据） |

---

## 7. 数据源设计

### 7.1 候选人信息类型

| 信息类型 | 数据来源 | 内容描述 | 用途 |
|---------|----------|----------|------|
| **persona** | persona 表 | MBTI、依恋、价值观、大五人格 | 性格特质判断 |
| **chat_records** | chat_history 表 | 原始聊天记录（不做摘要预处理） | Agent 自己分析行为模式 |
| **behavior** | behavior_log 表 | 操作记录（点赞、反馈、兴趣表达） | 活跃度、诚意判断 |
| **assessment** | assessment 表 | 测评回答内容 | 深度性格分析 |
| **introduction** | profile 表 | 自我介绍文本 | 第一印象判断 |

### 7.2 聊天记录加载逻辑

```python
def load_chat_records(profile_id: int, days: int = 30) -> list[dict]:
    """
    加载候选人的原始聊天记录。
    
    核心原则：
    - 直接返回原始聊天记录，不做摘要预处理
    - Agent 自己决定如何分析（grep 关键词、频率统计、语气分析等）
    - 不预设判断标准，Agent 根据用户需求调整
    
    参数：
    - profile_id: 候选人 ID
    - days: 时间范围（最近 N 天，默认 30 天）
    
    返回：
    - chat_records: 原始聊天记录列表
      - time: 对话时间
      - content: 对话内容
      - direction: 方向（发送/接收）
    
    注意：
    - 不做离线摘要预处理，避免信息失真
    - Agent 直接读原始数据自己分析
    """
    # 直接查询原始聊天记录
    records = query_chat_history(profile_id, days=days)
    
    # 返回原始数据，不做任何预处理
    return [
        {
            "time": r["created_at"],
            "content": r["content"],
            "direction": r["direction"],
        }
        for r in records
    ]
```

### 7.3 为什么不用离线摘要？

**离线摘要的问题：**

| 问题 | 描述 | 影响 |
|------|------|------|
| **信息失真** | 摘要把"你真棒"总结成"表达关心"，丢失频率和语气 | Agent 判断不准确 |
| **预设标准** | 摘要生成时用的是预设判断标准，无法根据用户需求调整 | 无法满足"不要绿茶"等个性化需求 |
| **二手信息** | Agent 只能基于别人（摘要 AI）的解读做判断 | Agent 自主权降低 |
| **丢失细节** | 关键词频率、上下文、时间分布等细节被丢失 | 无法做精细分析 |

**正确做法：直接给 Agent 原始数据**

| 优势 | 描述 |
|------|------|
| **一手信息** | Agent 基于原始数据自己分析，不失真 |
| **灵活分析** | Agent 自己决定分析方法（grep、频率统计、语气分析） |
| **个性化标准** | Agent 根据用户具体需求调整判断标准 |
| **保留细节** | 关键词频率、上下文、时间分布等完整保留 |

### 7.4 隐私处理

| 信息类型 | 隐私处理 | 原因 |
|---------|---------|------|
| persona | 无需处理 | 用户知道会用于匹配 |
| chat_records | 只返回摘要级信息（时间+内容，不含敏感个人信息） | 保护隐私 |
| behavior | 只返回操作摘要 | 减少信息量 |
| assessment | 只返回回答摘要 | 保护测评隐私 |

**注意：这里说的"摘要"是指隐私脱敏，不是离线生成的性格判断摘要。**

---

## 8. 性能优化

### 8.1 信息量重新评估

**文档旧方案的担忧：**

```
假设硬约束返回 20 人：
方案 A（不合理）：全部加载完整信息
→ 20人 × 50条聊天 × 500字 = 500,000 字
→ Token 爆炸，性能不可接受
```

**这个担忧可能不成立：**

| 因素 | 分析 |
|------|------|
| **现代 LLM 能力** | Claude Opus/Sonnet 可以处理 200K+ tokens |
| **Agent 会自己筛选** | Agent 先快速扫描，发现有问题的再深入看 |
| **一次调用更省 Token** | 旧方案 42 次工具调用，每次都要重新加载 prompt |

**实际 Token 消耗对比：**

| 方案 | 工具调用次数 | Token 消耗（估算） |
|------|-------------|-------------------|
| **旧方案（离线摘要 + submit）** | 42 次 | 每次调用重新加载 prompt → ~60,000 tokens |
| **新方案（原始数据 + decision）** | 1 次 | 一次加载 prompt + 数据 → ~40,000 tokens |

**结论：新方案反而更省 Token，因为避免了多次工具调用的 prompt 重复加载。**

### 8.2 Agent 自主优化策略

Agent 不需要我们预设优化策略，Agent 会自己找到高效的分析方法：

```
Agent 思考："20个人的聊天记录太长，我先快速扫描：

快速扫描策略：
1. 每个人只看最近 10 条消息
2. grep 关键词：'你真棒'、'你好厉害'、'你最好了'
3. 发现候选人 102、106、109 有高频使用
4. 只深入看这 3 个人的完整聊天记录
5. 其他 17 个人快速判断为'无明显问题'

这样信息量从 500,000 字降到 ~50,000 字"
```

### 8.3 limit 参数控制

```python
def search_partner_candidates(
    criteria_json: str,
    limit: int = 10,  # 默认返回 10 人，最多 20 人
    ...
):
    """
    limit 参数控制：
    - 默认返回 10 人（足够用户选择，信息量可控）
    - 最多返回 20 人（避免信息量过大）
    - Agent 可以先搜 10 人，如果筛选后不够再搜下一批
    """
```

### 8.4 分批搜索策略

```python
# Agent Prompt 中引导：

"你应该分批搜索候选人：
1. 先搜索 10 人，判断筛选
2. 如果筛选后不够 5 人，再搜索下一批 10 人
3. 最多搜索 20 人（避免信息量过大）
4. 每批搜索时可以利用上批的判断经验提高效率"
```

### 8.5 缓存策略

```python
# persona 缓存：
# - persona 数据定期更新，Agent 调用时直接读取

# 聊天记录缓存：
# - 原始聊天记录不做预处理缓存
# - 直接查询数据库返回原始数据
# - 避免缓存"摘要"导致信息失真
```

---

## 9. 与现有架构的对比

### 9.1 核心差异

| 维度 | 现有方案 | 改进方案 |
|------|----------|----------|
| 决策位置 | 翻译层硬编码 | Agent 自主决策 |
| 信息来源 | 只看 persona 表字段 | 看候选人所有信息（persona + 原始聊天记录） |
| "绿茶"处理 | 映射到数据库字段（片面） | Agent 读原始聊天记录自己分析（全面） |
| 数据形态 | 离线摘要（二手信息） | 原始数据（一手信息） |
| 灵活性 | 固定规则 | Agent 根据语义理解，自己找分析方法 |
| 判断结果表达 | 无标准机制 | 利用现有 decision.selected_candidates |
| 工具调用次数 | N/A（无搜索） | 1 次（极简） |

### 9.2 Agent Native 程度提升

| 指标 | 现有方案 | 改进方案 |
|------|----------|----------|
| Agent 自主性 | 低（依赖翻译层） | 高（自主判断） |
| 决策权位置 | 查询层 | Agent 层 |
| 信息完整性 | 片面（只看字段） | 全面（看所有原始数据） |
| 智能程度 | 规则匹配 | Agent 自己分析原始数据 |
| 信息真实性 | 二手信息（可能失真） | 一手信息（不失真） |

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

## 10. 实施路径

### 10.1 Phase 1：工具层改造

| 改动 | 内容 | 工作量 |
|------|------|--------|
| search_partner_candidates | 改造为直接返回完整信息（persona + 原始聊天记录） | 中 |
| search_chat_keywords（可选） | 新增辅助工具帮助 Agent 快速 grep | 小 |

**注意：不需要新增 submit/get 工具，利用现有 decision 结构。**

### 10.2 Phase 2：数据源扩展

| 改动 | 内容 | 工作量 |
|------|------|--------|
| 聊天记录查询接口 | 直接查询原始聊天记录，不做摘要预处理 | 小 |
| persona 加载优化 | persona 数据定期更新，Agent 调用时直接读取 | 小 |

**注意：不需要离线生成 chat_summary 表。**

### 10.3 Phase 3：Agent Prompt 优化

| 改动 | 内容 | 工作量 |
|------|------|--------|
| SOUL.md 更新 | 添加工具使用指南、分析方法示例 | 小 |
| 分批搜索策略 | Prompt 中引导 Agent 分批搜索 | 小 |
| 分析策略示例 | 描述常见分析方法（grep 关键词、频率统计、语气分析） | 小 |

### 10.4 Phase 4：测试验证

| 测试 | 内容 | 工作量 |
|------|------|--------|
| 单场景测试 | 测试每个场景类型（"不要绿茶"、"性格温柔"等） | 中 |
| 组合场景测试 | 测试多条件组合 | 中 |
| 边界测试 | 测试性能、隐私边界 | 中 |
| Agent 行为验证 | 验证 Agent 分析策略合理性（是否真的 grep 关键词频率） | 中 |
| 准确性对比 | 对比"离线摘要判断"vs"原始数据判断"的准确性 | 中 |

---

## 11. 风险与缓解

### 11.1 性能风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 信息量过大 | 原始聊天记录可能较长 | Agent 自己筛选（先快速扫描，发现问题的再深入看） |
| Token 消耗 | 原始数据比摘要消耗更多 Token | limit 参数控制（默认 10 人，最多 20 人） |

**注意：新方案工具调用次数更少（1 次 vs 42 次），总 Token 消耗可能反而更低。**

### 11.2 隐私风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 聊天记录隐私 | 候选人不知道会被搜索 | 只返回摘要级信息（时间+内容，不含敏感个人信息） |
| 判断结果公开 | Agent 判断理由可能不当 | Agent 生成解释时要审慎 |

### 11.3 Agent 判断风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 判断不一致 | 不同 Agent 判断可能不同 | Prompt 中提供判断指南，但让 Agent 自己决定分析方法 |
| 判断偏差 | Agent 可能有偏见 | 人类审核 + 反馈修正 |
| 分析策略不够好 | Agent 可能用不够好的分析方法 | Prompt 中提供分析方法示例（grep 关键词、频率统计等） |

### 11.4 与旧方案对比（风险角度）

| 风险 | 旧方案（离线摘要） | 新方案（原始数据） |
|------|------------------|-------------------|
| 信息失真 | **高风险**（摘要丢失细节） | **低风险**（原始数据完整） |
| Token 消耗 | 中（多次工具调用） | 中（一次加载大量数据） |
| Agent 自主权 | 低（依赖摘要） | 高（自己分析） |
| 判断准确性 | 低（二手信息） | 高（一手信息） |

---

## 12. 总结

### 12.1 核心改进

**从"数据库字段查询 + 离线摘要"转向"Agent 直接分析原始数据"**

```
用户说："不要绿茶的女生"

旧方案（离线摘要）：
→ 翻译层映射：绿茶 → persona.绿茶字段（不存在）→ 失败
→ 或：离线摘要生成："对话氛围良好" → Agent 读摘要判断为"正常"→ 错误

新方案（原始数据）：
→ 硬约束筛选：返回候选人大池子（含 persona + 原始聊天记录）
→ Agent 自己分析：grep "你真棒"出现5次 → 频率过高 → 判断"有绿茶特征"
→ Agent 自己判断：这个人过度迎合 → exclude
→ 判断正确（基于一手信息）
```

### 12.2 关键价值

| 价值点 | 描述 |
|--------|------|
| **给 Agent 原始数据** | 不做离线摘要预处理，避免信息失真 |
| **Agent 自己分析** | Agent 自己决定分析方法（grep、频率统计、语气分析），比预设规则更准确 |
| **Agent Native 程度更高** | Agent 是真正的决策大脑，基于一手信息自主判断 |
| **工具调用极简** | 1 次调用返回所有信息，不需要 submit/get 工具 |
| **与现有架构兼容** | 利用 decision.selected_candidates 表达判断结果，不新增状态管理工具 |

### 12.3 下一步

1. **确认方案**：与团队确认改进方案可行性
2. **工具改造**：改造 search_partner_candidates 直接返回完整信息
3. **数据源设计**：设计原始聊天记录查询接口（不做摘要预处理）
4. **Agent Prompt**：更新 SOUL.md 添加分析方法示例（grep 关键词、频率统计、语气分析等）
5. **测试验证**：对比"离线摘要判断"vs"原始数据判断"的准确性