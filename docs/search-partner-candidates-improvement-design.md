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

### 5.1 search_partner_candidates（硬约束筛选）

```python
@function_tool
def search_partner_candidates(
    criteria_json: str,
    limit: int = 5,
) -> dict[str, Any]:
    """
    搜索候选人（硬约束筛选）。
    
    只负责：
    - 根据 criteria 进行硬约束筛选（年龄、城市、身高等）
    - 返回候选人的 ID + 基础信息
    
    不负责：
    - 性格关键词筛选（Agent 自主判断）
    - 软约束筛选（Agent 自主判断）
    
    参数：
    - criteria_json: 硬约束条件（JSON）
      支持的字段：age_min, age_max, cities, height_min, height_max,
                  education, marital_status, income, job, relationship_goal 等
    
    返回：
    - candidate_ids: 候选人 ID 列表
    - basic_info: 每个候选人的基础信息（年龄、城市、职业等）
    - total: 总候选人数量
    
    注意：
    - 这只是硬约束筛选结果，Agent 需要进一步判断
    - Agent 应该根据 basic_info 决定要不要深入分析
    """
    criteria = json.loads(criteria_json)
    normalized_limit = max(1, min(int(limit or 5), 50))  # 硬约束：最多返回 50 人
    
    # 执行硬约束筛选
    candidates = _search_by_hard_constraints(criteria, normalized_limit)
    
    # 返回 ID + 基础信息（不返回完整信息）
    return {
        "candidate_ids": [c["id"] for c in candidates],
        "basic_info": [
            {
                "id": c["id"],
                "age": c["age"],
                "city": c["city"],
                "job": c.get("job"),
                "education": c.get("education"),
                "relationship_goal": c.get("relationship_goal"),
            }
            for c in candidates
        ],
        "total": len(candidates),
        "has_more": len(candidates) >= normalized_limit,
    }
```

### 5.2 load_candidate_full_info（加载候选人完整信息）

```python
@function_tool
def load_candidate_full_info(
    candidate_id: int,
    info_types: list[str] = ["persona", "chat_summary"],
    detail_level: str = "medium",
) -> dict[str, Any]:
    """
    加载单个候选人的完整信息。
    
    Agent 决定：
    - 要看哪些类型的信息
    - 信息详细程度（summary/detail/full）
    - 用于深入判断候选人是否符合用户意图
    
    参数：
    - candidate_id: 候选人 ID
    - info_types: 信息类型列表（Agent 选择性加载）
      - "persona": 用户画像（MBTI、依恋、价值观等）
      - "chat_summary": 聊天记录摘要（最近 30 天的对话摘要）
      - "chat_detail": 聊天记录详细片段（关键对话片段）
      - "behavior": 操作行为记录（点赞、反馈、兴趣表达等）
      - "assessment": 测评回答内容（MBTI、依恋测评的回答）
      - "introduction": 自我介绍文本
    
    - detail_level: 信息详细程度
      - "summary": 概要（500 字以内）
      - "medium": 中等详细（1000 字以内）
      - "detail": 详细（完整内容，可能较长）
    
    返回：
    - candidate_id: 候选人 ID
    - info: 候选人信息（按 Agent 请求的类型和详细程度返回）
    
    注意：
    - Agent 应该根据 basic_info 先判断是否有潜力
    - 只对有潜力的候选人调用此工具
    - 避免对所有候选人都加载完整信息（性能问题）
    """
    info = {}
    
    # persona: 用户画像
    if "persona" in info_types:
        persona = load_persona_from_db(candidate_id)
        info["persona"] = {
            "mbti": persona.get("mbti"),
            "attachment": persona.get("attachment"),
            "big_five": persona.get("big_five"),
            "values": persona.get("values"),
        }
    
    # chat_summary: 聊天摘要
    if "chat_summary" in info_types:
        chat_records = load_chat_records(candidate_id, limit=50)
        summary = summarize_chat_content(chat_records, detail_level)
        info["chat_summary"] = summary
    
    # behavior: 行为记录
    if "behavior" in info_types:
        behaviors = load_behavior_records(candidate_id)
        info["behavior"] = behaviors
    
    # assessment: 测评回答
    if "assessment" in info_types:
        assessments = load_assessment_answers(candidate_id)
        info["assessment"] = assessments
    
    return {
        "candidate_id": candidate_id,
        "info": info,
        "loaded_types": info_types,
    }
```

### 5.3 submit_candidate_judgment（提交判断结果）

```python
@function_tool
def submit_candidate_judgment(
    candidate_id: int,
    pass_judgment: bool,
    reason: str = "",
    confidence: float = 0.8,
) -> dict[str, Any]:
    """
    提交 Agent 对单个候选人的判断结果。
    
    Agent 用法：
    1. 先调用 search_partner_candidates 获取候选人 ID
    2. 对需要深入分析的候选人调用 load_candidate_full_info
    3. Agent 自己分析判断（纯思考，不调用工具）
    4. 调用此工具提交判断结果
    
    参数：
    - candidate_id: 候选人 ID
    - pass_judgment: 是否通过筛选（True = 推荐，False = 排除）
    - reason: Agent 判断的理由（用于解释给用户）
    - confidence: Agent 判断的置信度（0.0-1.0）
    
    返回：
    - success: 提交成功
    - judgment: 判断结果记录
    
    注意：
    - Agent 判断是纯思考过程，此工具只是提交结果
    - Agent 应该记录判断理由，用于向用户解释推荐原因
    """
    return {
        "success": True,
        "judgment": {
            "candidate_id": candidate_id,
            "pass": pass_judgment,
            "reason": reason,
            "confidence": confidence,
        }
    }
```

### 5.4 get_filtered_candidates（获取筛选后的候选人）

```python
@function_tool
def get_filtered_candidates(
    limit: int = 5,
) -> dict[str, Any]:
    """
    获取 Agent 筛选后的最终候选人列表。
    
    Agent 用法：
    1. 完成对所有候选人的判断后调用
    2. 返回 pass_judgment=True 的候选人
    
    参数：
    - limit: 返回数量限制（最多 10 人）
    
    返回：
    - filtered_candidates: 筛选后的候选人列表（包含完整展示信息）
    - excluded_count: 排除的候选人数量
    - total_count: 总判断数量
    
    注意：
    - 如果筛选后没有人，Agent 应该向用户说明并建议放宽条件
    """
    # 从 session 中获取 Agent 提交的判断结果
    judgments = get_session_judgments()
    
    # 筛选 pass 的候选人
    passed = [j for j in judgments if j["pass"]]
    
    # 加载完整展示信息
    filtered = []
    for judgment in passed[:limit]:
        candidate = load_candidate_display_info(judgment["candidate_id"])
        candidate["agent_reason"] = judgment["reason"]
        filtered.append(candidate)
    
    return {
        "filtered_candidates": filtered,
        "excluded_count": len([j for j in judgments if not j["pass"]]),
        "total_count": len(judgments),
    }
```

---

## 6. Agent 执行流程

### 6.1 典型场景流程

用户说："不要绿茶的女生，25-30岁，上海"

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: 硬约束筛选                                              │
├─────────────────────────────────────────────────────────────────┤
│ Agent 调用：search_partner_candidates                           │
│ 参数：criteria_json = {"age_min": 25, "age_max": 30,            │
│                       "cities": ["上海"]}                       │
│ 返回：candidate_ids = [101, 102, 103, ..., 120]（20人）         │
│       basic_info = [{id:101, age:28, city:"上海", job:"财务"},..]│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Agent 选择性加载信息                                    │
├─────────────────────────────────────────────────────────────────┤
│ Agent 思考：                                                    │
│ "用户说不要绿茶，我需要看聊天记录判断                            │
│  先看 basic_info，101号看起来正常，深入看                        │
│  102号职业是销售，可能不太稳定，先排除                           │
│  103号年龄正好28，继续深入看"                                    │
│                                                                 │
│ Agent 调用：load_candidate_full_info                            │
│ 参数：candidate_id=101, info_types=["persona", "chat_summary"]  │
│ 返回：persona + chat_summary                                    │
│                                                                 │
│ Agent 调用：load_candidate_full_info                            │
│ 参数：candidate_id=103, info_types=["persona", "chat_summary"]  │
│ 返回：persona + chat_summary                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Agent 自主分析判断                                      │
├─────────────────────────────────────────────────────────────────┤
│ Agent 思考（纯思考，不调用工具）：                               │
│                                                                 │
│ 候选人 101：                                                    │
│ - persona: attachment_type = "secure"（安全型依恋）             │
│ - chat_summary: "对话中比较直接，不说讨好型的话"                 │
│ - 判断：这个人比较真诚，不像绿茶型 → pass                        │
│                                                                 │
│ 候选人 103：                                                    │
│ - persona: attachment_type = "anxious"（焦虑型依恋）            │
│ - chat_summary: "经常说'你真棒'、'你好厉害'、'你最好了'"         │
│ - 判断：这个人过于迎合，有绿茶特征 → exclude                     │
│                                                                 │
│ Agent 调用：submit_candidate_judgment                           │
│ 参数：candidate_id=101, pass=True, reason="性格真诚直接"        │
│                                                                 │
│ Agent 调用：submit_candidate_judgment                           │
│ 参数：candidate_id=103, pass=False, reason="过于迎合讨好"       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: 获取筛选结果                                            │
├─────────────────────────────────────────────────────────────────┤
│ Agent 调用：get_filtered_candidates                             │
│ 参数：limit=5                                                   │
│ 返回：filtered_candidates = [101, 105, 108, 112, 116]           │
│       （都是 Agent 判断通过的候选人）                            │
│                                                                 │
│ Agent 返回用户：                                                │
│ show_candidates 候选人列表                                      │
│ 推荐理由：Agent 根据判断结果向用户解释                           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Agent 决策要点

| 决策点 | Agent 责任 | 示例 |
|--------|-----------|------|
| **要不要深入看？** | Agent 根据 basic_info 判断 | 年龄职业正常→深入看，明显不符合→直接排除 |
| **看哪些信息？** | Agent 选择 info_types | 判断绿茶→看 persona + chat_summary |
| **怎么判断？** | Agent 语义理解 | 读聊天摘要→判断是否过于迎合 |
| **置信度多少？** | Agent 自我评估 | 信息充足→0.9，信息不足→0.6 |
| **如何解释？** | Agent 提供理由 | "这个人聊天过于迎合，有绿茶特征" |

---

## 7. 数据源设计

### 7.1 候选人信息类型

| 信息类型 | 数据来源 | 内容描述 | 用途 |
|---------|----------|----------|------|
| **persona** | persona 表 | MBTI、依恋、价值观、大五人格 | 性格特质判断 |
| **chat_summary** | chat_history 表 | 聊天记录摘要（AI 生成） | 行为模式判断 |
| **behavior** | behavior_log 表 | 操作记录（点赞、反馈、兴趣表达） | 活跃度、诚意判断 |
| **assessment** | assessment 表 | 测评回答内容 | 深度性格分析 |
| **introduction** | profile 表 | 自我介绍文本 | 第一印象判断 |

### 7.2 chat_summary 生成逻辑

```python
def summarize_chat_content(chat_records: list[dict], detail_level: str) -> str:
    """
    聊天记录摘要生成。
    
    输入：候选人最近 50 条聊天记录
    输出：500-1000 字摘要
    
    摘要内容：
    - 对话风格（直接/含蓄/讨好）
    - 常用表达方式
    - 典型对话片段（体现性格）
    - 对他人态度（真诚/敷衍）
    
    detail_level:
    - "summary": 概要（500字）
    - "medium": 中等（1000字，含关键对话片段）
    - "detail": 详细（完整对话，含时间线）
    """
    # 使用 AI 生成摘要
    summary = ai_summarize(chat_records, detail_level)
    return summary
```

### 7.3 隐私处理

| 信息类型 | 隐私处理 | 原因 |
|---------|---------|------|
| persona | 无需处理 | 用户知道会用于匹配 |
| chat_summary | 只摘要，不返回原文 | 保护隐私，减少信息量 |
| behavior | 只返回摘要 | 减少信息量 |
| assessment | 只返回摘要 | 保护测评隐私 |

---

## 8. 性能优化

### 8.1 信息量控制

```
假设硬约束返回 20 人：

方案 A（不合理）：全部加载完整信息
→ 20人 × 50条聊天 × 500字 = 500,000 字
→ Token 爆炸，性能不可接受

方案 B（推荐）：Agent 选择性加载
→ Agent 根据 basic_info 先排除 10 人
→ 只对 10 人调用 load_candidate_full_info
→ 每人只请求 persona + chat_summary（1000字）
→ 总信息量 = 10 × 1000 = 10,000 字
→ 可接受
```

### 8.2 分批处理策略

```python
# Agent Prompt 中引导：

"你应该分批处理候选人：
1. 先看 basic_info，排除明显不符合的
2. 只对有潜力的候选人深入分析
3. 每批处理 5-10 人，避免信息量过大
4. 如果筛选后不够 5 人，可以再加载更多候选人"
```

### 8.3 缓存策略

```python
# chat_summary 缓存：
# - 离线定期生成摘要，存入数据库
# - Agent 调用时直接读取，不实时生成

# persona 缓存：
# - persona 数据定期更新，Agent 调用时直接读取
```

---

## 9. 与现有架构的对比

### 9.1 核心差异

| 维度 | 现有方案 | 改进方案 |
|------|----------|----------|
| 决策位置 | 翻译层硬编码 | Agent 自主决策 |
| 信息来源 | 只看 persona 表字段 | 看候选人所有信息 |
| "绿茶"处理 | 映射到数据库字段（片面） | Agent 读聊天判断（全面） |
| 灵活性 | 固定规则 | Agent 根据语义理解 |
| 性格关键词 | 无法查询 | Agent 自主判断 |

### 9.2 Agent Native 程度提升

| 指标 | 现有方案 | 改进方案 |
|------|----------|----------|
| Agent 自主性 | 低（依赖翻译层） | 高（自主判断） |
| 决策权位置 | 查询层 | Agent 层 |
| 信息完整性 | 片面（只看字段） | 全面（看所有信息） |
| 智能程度 | 规则匹配 | 语义理解 |

---

## 10. 实施路径

### 10.1 Phase 1：工具层改造

| 改动 | 内容 | 工作量 |
|------|------|--------|
| search_partner_candidates | 只返回 ID + basic_info | 小 |
| load_candidate_full_info | 新增工具 | 中 |
| submit_candidate_judgment | 新增工具 | 小 |
| get_filtered_candidates | 新增工具 | 小 |

### 10.2 Phase 2：数据源扩展

| 改动 | 内容 | 工作量 |
|------|------|--------|
| chat_summary 表 | 存储聊天摘要 | 中 |
| 离线摘要生成 | 定期生成摘要 | 中 |
| behavior 汇总 | 行为记录汇总 | 小 |

### 10.3 Phase 3：Agent Prompt 优化

| 改动 | 内容 | 工作量 |
|------|------|--------|
| SOUL.md 更新 | 添加工具使用指南 | 小 |
| 分批处理策略 | Prompt 中引导 Agent | 小 |
| 判断逻辑描述 | 描述常见关键词分析思路 | 小 |

### 10.4 Phase 4：测试验证

| 测试 | 内容 | 工作量 |
|------|------|--------|
| 单场景测试 | 测试每个场景类型 | 中 |
| 组合场景测试 | 测试多条件组合 | 中 |
| 边界测试 | 测试性能、隐私边界 | 中 |
| Agent 行为验证 | 验证 Agent 判断合理性 | 中 |

---

## 11. 风险与缓解

### 11.1 性能风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| Token 量过大 | Agent 处理信息量超限 | 分批处理 + 选择性加载 |
| LLM 调用过多 | 多候选人多次调用 | Agent 先筛选再深入 |
| 摘要生成耗时 | 实时生成摘要慢 | 离线预生成 |

### 11.2 隐私风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 聊天记录隐私 | 候选人不知道会被搜索 | 只返回摘要，不返回原文 |
| 判断结果公开 | Agent 判断理由可能不当 | Agent 生成解释时要审慎 |

### 11.3 Agent 判断风险

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 判断不一致 | 不同 Agent 判断可能不同 | Prompt 中提供判断指南 |
| 判断偏差 | Agent 可能有偏见 | 人类审核 + 反馈修正 |
| 信息不足误判 | 摘要可能丢失关键信息 | 允许 Agent 请求详细内容 |

---

## 12. 总结

### 12.1 核心改进

**从"数据库字段查询"转向"Agent 语义判断"**

```
用户说："不要绿茶的女生"

现有方案：
→ 翻译层映射：绿茶 → persona.绿茶字段（不存在）
→ 查询失败

改进方案：
→ 硬约束筛选：返回候选人大池子
→ Agent 读聊天摘要：判断是否过于迎合
→ Agent 自主判断：这个人有绿茶特征 → exclude
→ 筛选成功
```

### 12.2 关键价值

| 价值点 | 描述 |
|--------|------|
| **全面判断** | 不只看数据库字段，看候选人所有信息 |
| **Agent Native** | Agent 是真正的决策大脑 |
| **灵活智能** | 不硬编码规则，Agent 根据语义理解 |
| **可扩展** | 新增信息类型不影响核心逻辑 |

### 12.3 下一步

1. **确认方案**：与团队确认改进方案可行性
2. **工具设计**：详细设计新增工具参数和返回值
3. **数据源设计**：设计 chat_summary 存储和生成逻辑
4. **Agent Prompt**：更新 SOUL.md 添加工具使用指南
5. **测试验证**：设计测试场景验证 Agent 行为