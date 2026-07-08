---
name: user-behavior-data-ai-native-refactor-plan
description: 用户交互行为数据收集与利用的AI Native完整改造方案
metadata:
  type: project
---

# 用户交互行为数据 AI Native 完整改造方案

> **核心原则**：从"硬编码规则 + AI调用"转向"AI作为决策引擎 + 工具执行"
>
> **改造目标**：让系统从"记账员"变成"聪明助手"，真正理解用户意图，主动优化推荐

---

## 一、现状分析

### 1.1 当前系统收集的数据

| 数据类型 | 收集内容 | 存储位置 |
|---------|---------|---------|
| 前端交互行为 | 详情页停留时长、卡片可见时长、照片滑动次数、重复查看次数 | appearance_feedback_events.metadata_json |
| 业务行为事件 | 表达兴趣、保存、直接打招呼、聊天互动、跳过、不喜欢 | appearance_feedback_events.event_type |
| 系统行为追踪 | 搜索条件、推荐动作、会话状态 | discovery_search_runs, recommendation_actions |
| 外观偏好数据 | 风格标签频率、风格权重映射、偏好总结 | user_appearance_preferences |
| 向量数据 | 外观偏好向量、人脸向量、风格向量 | Milvus Lite |

### 1.2 当前数据利用链路

```
前端用户交互 → 记录行为事件 → MySQL存储 → 统计频率 →
生成偏好总结 → 向量库同步 → 推荐算法使用 → 个性化推荐
```

**关键代码路径**：
- 行为质量判断：[appearance_features.py:3098-3107](match_domain/appearance_features.py#L3098-L3107)（硬编码阈值）
- 偏好权重计算：[appearance_features.py:2591-2770](match_domain/appearance_features.py#L2591-L2770)（统计频率）
- 用户阶段判断：[appearance_features.py:1147-1191](match_domain/appearance_features.py#L1147-L1191)（硬编码阈值）
- 事件权重映射：[profile_service/api.py:2118-2162](profile_service/api.py#L2118-L2162)（硬编码权重表）

---

## 二、问题诊断（AI Native视角）

### 2.1 五问法根因分析

```
问题现象：系统无法真正理解用户意图，推荐不够精准
├─ 为什么 1: 行为质量判断是硬编码阈值（8000ms → strong_interest）
│   → Agent无法根据上下文灵活判断
├─ 为什么 2: 偏好学习只统计频率，不理解偏好背后的原因
│   → Agent无法解释为什么推荐这个人
├─ 为什么 3: 用户阶段判断是硬编码阈值（20次 → high_confidence）
│   → Agent无法动态调整推荐策略
├─ 为什么 4: 事件权重是硬编码映射表（express_interest → 3.0）
│   → Agent无法根据上下文动态调整权重
└─ 为什么 5: 【根本原因】设计理念把Agent当成"规则执行器"，而非"决策引擎"
```

**根本对策**：移除硬编码规则，让AI从行为序列中理解用户意图，自主判断权重和策略。

### 2.2 Agent Native反模式识别

| 反模式 | 当前代码位置 | 问题 | 修复方向 |
|--------|-------------|------|---------|
| **硬编码阈值判断** | appearance_features.py:3098-3107 | Agent无法理解上下文 | AI分析行为序列判断意图 |
| **硬编码权重表** | profile_service/api.py:2118-2162 | Agent无法动态调整权重 | AI根据上下文自主决定权重 |
| **硬编码分级** | appearance_features.py:1147-1191 | Agent无法灵活判断 | AI动态判断置信度 |
| **统计频率无理解** | appearance_features.py:2591-2770 | Agent无法解释偏好原因 | AI分析偏好背后的原因 |

---

## 三、完整改造方案（分5个Phase）

### Phase 1：移除硬编码规则（核心改造）

**目标**：把所有硬编码阈值改为AI自主判断

#### 1.1 改造清单

| 改造项 | 当前代码 | AI Native改造 | 文件位置 |
|--------|---------|--------------|---------|
| 行为质量判断 | `if detail_ms >= 8000.0 → strong_interest` | AI分析行为序列判断意图 | appearance_features.py |
| 用户阶段判断 | `if total_count >= 20 → high_confidence` | AI动态判断置信度 | appearance_features.py |
| 事件权重映射 | `express_interest → 3.0` | AI根据上下文动态调整 | profile_service/api.py |
| 偏好权重计算 | 统计频率 | AI分析偏好原因 | appearance_features.py |

#### 1.2 具体代码改造

**改造1：行为意图分析替代硬编码阈值**

**旧代码（硬编码阈值）**：
```python
# 文件：appearance_features.py (行 3098-3107)
def classify_click_quality(
    detail_view_duration_ms: float,
    photo_swipe_count: int,
):
    if detail_ms >= 8000.0:
        quality = "strong_interest"  # ❌ 为什么是8000ms？
    elif detail_ms >= 3000.0:
        quality = "moderate_interest"
    else:
        quality = "quick_bounce"
    return quality
```

**新代码（AI分析行为序列）**：
```python
# 文件：appearance_features.py（新增函数）
async def analyze_user_intent_from_behavior_sequence(
    behaviors: list[dict],
    context: dict,
) -> dict:
    """
    AI从行为序列中理解用户真实意图（替代硬编码阈值）

    Args:
        behaviors: 完整行为序列，如：
            [
                {"action": "view_detail", "duration_ms": 5000, "photo_swipe": 2},
                {"action": "scroll_profile_section", "section": "hobbies"},
                {"action": "return_view", "delay_ms": 3600000},
            ]
        context: 上下文信息，如：
            {
                "user_persona": {...},
                "candidate_profile": {...},
                "scene": "discovery",
            }

    Returns:
        {
            "intent_type": "considering_match|quick_browse|searching_info|just_curious",
            "confidence": 0.85,
            "key_signals": ["长时间查看", "查看兴趣板块", "1小时后返回"],
            "quality_weight": 4.2,  # AI自主判断权重
            "reason": "用户查看兴趣板块且有返回行为，显示认真考虑",
        }
    """
    # 构建AI Prompt（遵循Agent Native原则：自然语言描述，而非规则表）
    prompt = f"""
你是一个用户行为分析专家，请从用户的行为序列中理解用户的真实意图。

用户行为序列：
{json.dumps(behaviors, ensure_ascii=False, indent=2)}

用户画像：{json.dumps(context.get('user_persona'), ensure_ascii=False)}
候选人画像：{json.dumps(context.get('candidate_profile'), ensure_ascii=False)}
场景：{context.get('scene', 'unknown')}

请分析用户的真实意图，输出JSON格式：
{
    "intent_type": "considering_match|quick_browse|searching_info|just_curious",
    "confidence": 0.0-1.0,
    "key_signals": ["行为信号1", "行为信号2"],
    "quality_weight": 0.0-6.0,
    "reason": "简要解释为什么得出这个结论"
}

判断标准（参考，不要硬套）：
- considering_match：查看时间长、滑动照片多、查看多个板块、有返回行为
- quick_browse：停留时间短、无滑动、无返回、直接跳出
- searching_info：查看特定板块（职业、兴趣）、停留时间中等
- just_curious：查看时间短但不是秒关、可能滑了1张照片、无深入行为

请根据完整行为序列灵活判断，不要机械套用单个阈值。
"""

    # 调用AI模型（使用结构化输出）
    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=USER_INTENT_SCHEMA,
        model="claude-sonnet-5",  # 需要强推理能力
    )

    return response


# Schema定义（遵循Agent Native原则：定义数据结构，不定义业务逻辑）
USER_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent_type": {
            "type": "string",
            "enum": ["considering_match", "quick_browse", "searching_info", "just_curious"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "key_signals": {"type": "array", "items": {"type": "string"}},
        "quality_weight": {"type": "number", "minimum": 0.0, "maximum": 6.0},
        "reason": {"type": "string"},
    },
    "required": ["intent_type", "confidence", "quality_weight"],
}
```

**改造2：偏好置信度动态判断替代硬编码分级**

**旧代码（硬编码阈值）**：
```python
# 文件：appearance_features.py (行 1147-1191)
def resolve_appearance_weight_strategy(user_appearance_preference):
    total_count = _preference_history_count(user_appearance_preference)

    # ❌ 硬编码阈值分级
    if total_count >= 20:
        user_stage = "high_preference_confidence"
    elif total_count >= 8:
        user_stage = "stable_preference"
    elif total_count >= 3:
        user_stage = "warming_up"
    else:
        user_stage = "new_user"

    # ❌ 硬编码权重调整
    if user_stage == "new_user":
        base_weight += 0.18
        preference_weight *= 0.45
    elif user_stage == "warming_up":
        base_weight += 0.08
        preference_weight *= 0.82
```

**新代码（AI动态判断）**：
```python
# 文件：appearance_features.py（新增函数）
async def determine_preference_confidence(
    user_history: dict,
    recent_pattern: dict,
) -> dict:
    """
    AI动态判断用户偏好的置信度（替代硬编码阈值）

    Args:
        user_history: 用户完整历史，如：
            {
                "total_events": 25,
                "positive_events": 18,
                "negative_events": 7,
                "time_span_days": 60,
            }
        recent_pattern: 最近行为模式，如：
            {
                "last_7_days": {
                    "positive_count": 5,
                    "positive_consistency": 0.85,  # 5次正向行为指向相似风格
                    "negative_scattered": true,  # 负向行为分散
                }
            }

    Returns:
        {
            "confidence_level": "stable_with_clear_pattern",
            "confidence_score": 0.85,
            "evidence": ["最近30天行为一致性高", "负向行为分散"],
            "recommendation_strategy": {
                "preference_weight": 0.72,  # AI动态决定
                "exploration_weight": 0.28,
            },
        }
    """
    prompt = f"""
你是一个用户偏好分析专家，请判断用户偏好的置信度。

用户历史数据：
{json.dumps(user_history, ensure_ascii=False, indent=2)}

最近7天行为模式：
{json.dumps(recent_pattern, ensure_ascii=False, indent=2)}

请判断用户偏好的置信度，输出JSON格式：
{
    "confidence_level": "new_user|warming_up|stable|stable_with_clear_pattern|high_confidence",
    "confidence_score": 0.0-1.0,
    "evidence": ["证据1", "证据2"],
    "recommendation_strategy": {
        "preference_weight": 0.0-1.0,  # 基于偏好推荐的比例
        "exploration_weight": 0.0-1.0,  # 探索新类型的比例
    },
    "reason": "简要解释"
}

判断标准（参考，不要硬套）：
- new_user：行为数据少于3次，无法判断偏好
- warming_up：行为数据3-8次，偏好开始显现但不稳定
- stable：行为数据8-20次，偏好基本稳定
- stable_with_clear_pattern：行为一致性高（正向行为集中，负向行为分散）
- high_confidence：行为数据超过20次且一致性很高

请根据完整数据灵活判断，不要机械套用阈值。
"""

    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=CONFIDENCE_SCHEMA,
        model="claude-sonnet-5",
    )

    return response


CONFIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "confidence_level": {
            "type": "string",
            "enum": ["new_user", "warming_up", "stable", "stable_with_clear_pattern", "high_confidence"],
        },
        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "recommendation_strategy": {
            "type": "object",
            "properties": {
                "preference_weight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "exploration_weight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["confidence_level", "confidence_score", "recommendation_strategy"],
}
```

**改造3：事件权重动态调整替代硬编码权重表**

**旧代码（硬编码权重表）**：
```python
# 文件：profile_service/api.py (行 2118-2162)
_DEFAULT_EVENT_WEIGHTS = {
    "express_interest": 3.0,  # ❌ 为什么是3.0？
    "save": 2.5,
    "direct_greet": 4.0,
    "chat_started": 4.5,
    "skip": -2.0,
}
```

**新代码（AI动态调整）**：
```python
# 文件：profile_service/api.py（新增函数）
async def determine_event_weight_from_context(
    event_type: str,
    metadata: dict,
    context: dict,
) -> dict:
    """
    AI根据上下文动态调整事件权重（替代硬编码权重表）

    Args:
        event_type: 事件类型，如："express_interest", "save", "chat_started"
        metadata: 行为元数据，如：
            {
                "detail_view_duration_ms": 5000,
                "photo_swipe_count": 2,
                "chat_message_count": 15,
            }
        context: 上下文信息，如：
            {
                "user_history": {...},
                "candidate_profile": {...},
                "scene": "recommendation",
            }

    Returns:
        {
            "event_weight": 4.2,  # AI动态决定权重
            "weight_reason": "用户表达兴趣前详细查看且有返回行为，显示真实兴趣",
            "confidence": 0.85,
        }
    """
    prompt = f"""
你是一个用户行为分析专家，请根据上下文判断事件的权重。

事件类型：{event_type}

行为元数据：
{json.dumps(metadata, ensure_ascii=False, indent=2)}

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

请判断这个事件的权重，输出JSON格式：
{
    "event_weight": -6.0到6.0,  # 正向事件正权重，负向事件负权重
    "weight_reason": "简要解释为什么给这个权重",
    "confidence": 0.0-1.0,
}

判断标准（参考，不要硬套）：
- express_interest：如果之前有详细查看、滑动照片、返回行为 → 权重更高（3.5-5.0）
- express_interest：如果之前是快速浏览 → 权重更低（1.5-2.5）
- chat_started：如果聊天消息多、话题丰富 → 权重更高（5.0-6.0）
- chat_started：如果只聊2句 → 权重更低（2.0-3.0）
- skip：如果之前看了很久才跳过 → 权重更负（-1.0到-2.0，可能只是在找信息）
- skip：如果秒跳 → 权重更负（-3.0到-4.0）

请根据完整上下文灵活判断，不要机械套用固定权重。
"""

    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=EVENT_WEIGHT_SCHEMA,
        model="claude-haiku-4-5",  # 权重判断可用轻量模型
    )

    return response


EVENT_WEIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_weight": {"type": "number", "minimum": -6.0, "maximum": 6.0},
        "weight_reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["event_weight", "weight_reason"],
}
```

---

### Phase 2：补充缺失数据收集

**目标**：收集系统当前遗漏的关键行为数据

#### 2.1 数据收集清单

| 补充项 | 收集内容 | 数据结构 | 利用场景 |
|--------|---------|---------|---------|
| **对话质量分析** | 消息数量、话题覆盖、情绪倾向、提问次数 | chat_metrics | 判断真实兴趣程度 |
| **搜索策略分析** | 搜索条件变化、重试模式、结果交互 | search_strategy | 优化搜索建议 |
| **候选人对比行为** | 对比维度、决策时长、犹豫模式 | comparison_session | 理解决策偏好 |
| **时间上下文** | 使用时段、使用场景、连续天数 | time_context | 个性化推荐时机 |
| **会话流失分析** | 会话中断点、中断原因、返回可能性 | session_quality | 优化交互流程 |

#### 2.2 数据库表结构扩展

**扩展1：appearance_feedback_events 表**

```python
# 文件：outer_system_mysql_schema.py
# 扩展 metadata_json 字段结构

metadata_json 结构扩展：
{
    # 原有字段
    "detail_view_duration_ms": float,
    "card_visible_duration_ms": float,
    "photo_swipe_count": int,
    "return_view_count": int,
    "quick_bounce": bool,

    # 新增字段（对话质量）
    "chat_metrics": {
        "message_count": int,  # 消息数量
        "avg_message_length": float,  # 平均消息长度（字符数）
        "response_speed_pattern": list[float],  # 回复速度模式（秒）
        "question_count": int,  # 提问次数（主动兴趣）
        "emoji_usage": dict,  # 表情符号使用频率
        "topic_coverage": list[str],  # 话题覆盖（职业、兴趣、生活）
        "chat_sentiment": float,  # 对话情绪倾向（-1到1）
        "chat_depth": str,  # # 聊天深度：surface/medium/deep
    },

    # 新增字段（对比行为）
    "comparison_session": {
        "compared_candidates": list[int],  # 对比的候选人ID列表
        "comparison_criteria": list[str],  # 对比维度（年龄、职业、外貌）
        "decision_time_ms": float,  # 决策时长
        "hesitation_pattern": str,  # # 犹豫模式：back_and_forth/long_pause/quick_decision
        "final_choice": int,  # 最终选择的候选人ID
    },

    # 新增字段（时间上下文）
    "time_context": {
        "hour_of_day": int,  # 时间段（0-23）
        "day_of_week": str,  # # 星期：monday/tuesday/...
        "usage_session": str,  # # 使用场景：morning_routine/break_time/evening_relax/late_night
        "consecutive_days": int,  # 连续使用天数
        "gap_days": int,  # 间隔天数（距离上次使用）
    },
}
```

**扩展2：discovery_search_runs 表**

```python
# 文件：outer_system_mysql_schema.py
# 扩展 discovery_search_runs 表结构

新增字段：
- ColumnDef("search_pattern", "VARCHAR(20)"),  # # 搜索模式：narrowing/broadening/experimenting
- ColumnDef("retry_count", "INT"),  # 重试次数（短时间内重新搜索）
- ColumnDef("result_interaction_ratio", "FLOAT"),  # 结果交互比例（跳过/查看比例）
- ColumnDef("search_goal", "VARCHAR(50)"),  # # 搜索目标：specific_type/diverse_options/check_availability

新增字段（搜索策略）：
- ColumnDef("criteria_changes_json", "LONGTEXT"),  # 搜索条件变化历史
```

**扩展3：新增 discovery_session_quality 表**

```python
# 文件：outer_system_mysql_schema.py
# 新增表：记录会话质量

discovery_session_quality_table = TableDef(
    name="discovery_session_quality",
    columns=(
        ColumnDef("session_id", "VARCHAR(191)", primary_key=True),
        ColumnDef("user_key", "VARCHAR(191)"),
        ColumnDef("profile_id", "BIGINT"),
        ColumnDef("turn_count", "INT"),  # 对话轮数
        ColumnDef("task_completion", "BOOLEAN"),  # 任务是否完成
        ColumnDef("drop_point", "VARCHAR(50)"),  # # 中断点：criteria_input/result_review/action_selection
        ColumnDef("drop_reason", "VARCHAR(50)"),  # # 中断原因：frustrated/bored/distracted/satisfied
        ColumnDef("return_likelihood", "FLOAT"),  # 返回可能性（0-1）
        ColumnDef("satisfaction_score", "FLOAT"),  # 满意度评分（0-5）
        ColumnDef("session_duration_ms", "BIGINT"),  # 会话总时长
        ColumnDef("created_at", "DATETIME"),
    ),
)
```

#### 2.3 前端埋点改动

**改动1：聊天页面埋点（ChatPage）**

```typescript
// 文件：frontend/her-app/components/her/chat-page.tsx

// 新增：聊天质量分析函数
function collectChatMetrics(chatHistory: ChatMessage[]) {
  const metrics = {
    message_count: chatHistory.length,
    avg_message_length: calculateAvgMessageLength(chatHistory),
    response_speed_pattern: calculateResponseSpeed(chatHistory),
    question_count: countQuestions(chatHistory),
    emoji_usage: analyzeEmojiUsage(chatHistory),
    topic_coverage: extractTopics(chatHistory),
    chat_sentiment: analyzeSentiment(chatHistory),
    chat_depth: determineChatDepth(chatHistory),
  };

  return metrics;
}

// 在发送消息、回复消息时触发埋点
const handleSendMessage = async (content: string) => {
  // ... 发送消息逻辑

  // 新增：埋点聊天质量数据
  const chatMetrics = collectChatMetrics(chatHistory);
  await api.recordChatMetrics({
    chat_id: currentChatId,
    metrics: chatMetrics,
  });
};
```

**改动2：发现页搜索埋点（DiscoveryPage）**

```typescript
// 文件：frontend/her-app/components/her/discovery-page.tsx

// 新增：搜索策略分析函数
function collectSearchStrategy(searchHistory: SearchRun[]) {
  const strategy = {
    search_pattern: detectSearchPattern(searchHistory),  # narrowing/broadening/experimenting
    retry_count: countRetries(searchHistory),
    result_interaction_ratio: calculateInteractionRatio(searchHistory),
    search_goal: detectSearchGoal(searchHistory),
    criteria_changes: extractCriteriaChanges(searchHistory),
  };

  return strategy;
}

// 在执行搜索时触发埋点
const handleSearch = async (criteria: SearchCriteria) => {
  // ... 搜索逻辑

  // 新增：埋点搜索策略数据
  const searchStrategy = collectSearchStrategy(searchHistory);
  await api.recordSearchStrategy({
    session_id: currentSessionId,
    strategy: searchStrategy,
  });
};
```

**改动3：候选人详情页对比埋点（CandidateDetailPage）**

```typescript
// 文件：frontend/her-app/components/her/candidate-detail-page.tsx

// 新增：对比行为记录
const comparisonSession = {
  compared_candidates: [],  # 用户查看的候选人ID列表
  comparison_criteria: [],  # 用户对比的维度
  start_time: Date.now(),
};

// 用户查看候选人时添加到对比列表
const handleViewCandidate = (candidateId: number) => {
  comparisonSession.compared_candidates.push(candidateId);

  // 记录对比维度（根据用户停留的板块）
  trackComparisonCriteria(candidateId);
};

// 用户做出最终选择时提交对比数据
const handleFinalChoice = (candidateId: number) => {
  comparisonSession.final_choice = candidateId;
  comparisonSession.decision_time_ms = Date.now() - comparisonSession.start_time;
  comparisonSession.hesitation_pattern = analyzeHesitation(comparisonSession);

  await api.recordComparison(comparisonSession);
};
```

---

### Phase 3：新增AI利用场景

**目标**：让AI主动利用行为数据做更聪明的事情

#### 3.1 AI利用场景清单

| 新增场景 | AI能力 | 价值 | 优先级 |
|---------|--------|------|--------|
| **行为序列预测** | 预测用户下一步行为 | 主动推荐、减少流失 | ⭐⭐⭐⭐⭐ |
| **行为异常检测** | 检测偏好突变、异常使用 | 主动理解用户、异常检测 | ⭐⭐⭐⭐ |
| **跨场景关联分析** | Discovery/Recommendation/Chat关联 | 优化场景策略 | ⭐⭐⭐ |
| **主动干预决策** | 判断是否需要主动帮助用户 | 提升用户体验 | ⭐⭐⭐⭐⭐ |
| **偏好原因分析** | 分析用户为什么喜欢某风格 | 推荐有解释、理解复杂偏好 | ⭐⭐⭐⭐ |

#### 3.2 具体AI场景实现

**场景1：行为序列预测**

```python
# 文件：match_domain/user_behavior_predictor.py（新文件）

async def predict_next_action_from_sequence(
    behavior_sequence: list[dict],
    context: dict,
) -> dict:
    """
    AI预测用户下一步行为（主动推荐）

    Args:
        behavior_sequence: 最近5-10个行为，如：
            [
                {"action": "search", "criteria": {"age": "25-30"}},
                {"action": "view_candidate", "candidate_id": 123, "duration": 5000},
                {"action": "skip", "reason": "location_mismatch"},
                {"action": "view_candidate", "candidate_id": 456, "duration": 3000},
            ]
        context: 用户画像、当前场景等

    Returns:
        {
            "predicted_action": "express_interest",  # 预测下一步表达兴趣
            "likelihood": 0.78,
            "reason": "用户已经查看2个候选人，跳过1个，查看时长递增",
            "suggestion": "这个候选人符合你的年龄要求且同城，可能感兴趣",
            "preemptive_action": "prepare_next_recommendation",  # 提前准备下一个推荐
        }
    """
    prompt = f"""
你是一个用户行为预测专家，请预测用户下一步可能做什么。

最近行为序列：
{json.dumps(behavior_sequence, ensure_ascii=False, indent=2)}

用户画像：{json.dumps(context.get('user_persona'), ensure_ascii=False)}
当前场景：{context.get('scene')}

请预测用户下一步行为，输出JSON格式：
{
    "predicted_action": "express_interest|skip|search|chat|exit",
    "likelihood": 0.0-1.0,
    "reason": "简要解释",
    "suggestion": "给用户的提示（可选）",
    "preemptive_action": "prepare_next_recommendation|send_hint|exit_flow",
}

请根据行为序列模式灵活预测。
"""

    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=PREDICTION_SCHEMA,
        model="claude-sonnet-5",
    )

    return response


# 集成到推荐流程（文件：discovery_system/service.py）
async def generate_recommendation_with_prediction(
    session: StoredSession,
    candidates: list[dict],
):
    # 1. 获取用户最近行为序列
    behavior_sequence = get_recent_behaviors(session)

    # 2. AI预测用户下一步行为
    prediction = await predict_next_action_from_sequence(
        behavior_sequence=behavior_sequence,
        context={"user_persona": session.user_persona, "scene": "discovery"},
    )

    # 3. 根据预测调整推荐策略
    if prediction["predicted_action"] == "express_interest":
        # 预测用户会表达兴趣，提前准备下一个推荐
        next_candidate = await prepare_next_recommendation(session)
        return {
            "current_recommendation": candidates[0],
            "prediction": prediction,
            "preemptive_action": {
                "type": "prepare_next",
                "next_candidate": next_candidate,
            },
        }
    elif prediction["predicted_action"] == "skip":
        # 预测用户会跳过，调整推荐策略
        return {
            "current_recommendation": candidates[0],
            "prediction": prediction,
            "suggestion": prediction.get("suggestion"),
        }
```

**场景2：行为异常检测**

```python
# 文件：match_domain/user_behavior_anomaly_detector.py（新文件）

async def detect_behavior_anomaly(
    recent_behaviors: list[dict],
    historical_pattern: dict,
) -> dict:
    """
    AI检测行为异常（偏好突变、异常使用）

    Args:
        recent_behaviors: 最近3天行为
        historical_pattern: 过去30天行为模式

    Returns:
        {
            "anomaly_detected": true,
            "anomaly_type": "preference_shift",  # 偏好突然变化
            "evidence": ["过去偏好'知性'风格，最近3天只看'活泼'风格"],
            "possible_reasons": ["用户在尝试新类型", "用户真实偏好发生变化"],
            "action_needed": "主动询问用户意图变化",
        }
    """
    prompt = f"""
你是一个用户行为异常检测专家，请判断用户行为是否有异常。

最近3天行为：
{json.dumps(recent_behaviors, ensure_ascii=False, indent=2)}

过去30天行为模式：
{json.dumps(historical_pattern, ensure_ascii=False, indent=2)}

请判断是否有异常，输出JSON格式：
{
    "anomaly_detected": true/false,
    "anomaly_type": "preference_shift|usage_change|abnormal_pattern",
    "evidence": ["证据1", "证据2"],
    "possible_reasons": ["原因1", "原因2"],
    "action_needed": "none|ask_user|adjust_strategy|alert_admin",
}

请灵活判断，不要机械套用阈值。
"""

    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=ANOMALY_SCHEMA,
        model="claude-sonnet-5",
    )

    return response


# 集成到偏好更新流程（文件：appearance_features.py）
async def build_style_preference_with_anomaly_check(
    user_key: str,
    profile_id: int,
):
    # 1. 获取历史行为数据
    historical_pattern = get_historical_pattern(user_key, profile_id)
    recent_behaviors = get_recent_behaviors(user_key, profile_id, days=3)

    # 2. AI检测异常
    anomaly = await detect_behavior_anomaly(
        recent_behaviors=recent_behaviors,
        historical_pattern=historical_pattern,
    )

    # 3. 如果检测到异常，主动询问用户
    if anomaly["anomaly_detected"]:
        return {
            "preference_updated": false,
            "anomaly": anomaly,
            "action": {
                "type": "ask_user",
                "message": f"检测到你的偏好可能有变化：{anomaly['evidence'][0]}。是否要调整偏好设置？",
            },
        }

    # 4. 无异常，正常更新偏好
    preference = await build_style_preference_from_feedback(user_key, profile_id)
    return preference
```

**场景3：主动干预决策**

```python
# 文件：match_domain/proactive_intervention_decider.py（新文件）

async def decide_proactive_intervention(
    user_behaviors: dict,
    current_context: dict,
) -> dict:
    """
    AI判断是否需要主动干预（帮助用户）

    Args:
        user_behaviors: 用户完整行为数据
        current_context: 当前上下文

    Returns:
        {
            "intervention_needed": true,
            "intervention_type": "preference_guidance",
            "reason": "用户连续5次跳过相似风格的候选人",
            "intervention_message": "你跳过了5位'知性'风格的候选人，是否要调整偏好设置？",
            "intervention_timing": "next_session_start",
        }
    """
    prompt = f"""
你是一个用户体验优化专家，请判断是否需要主动干预帮助用户。

用户行为数据：
{json.dumps(user_behaviors, ensure_ascii=False, indent=2)}

当前上下文：
{json.dumps(current_context, ensure_ascii=False, indent=2)}

请判断是否需要干预，输出JSON格式：
{
    "intervention_needed": true/false,
    "intervention_type": "preference_guidance|search_help|chat_encouragement|retention",
    "reason": "简要解释",
    "intervention_message": "给用户的消息",
    "intervention_timing": "immediate|next_action|next_session_start",
}

干预场景示例：
- preference_guidance：用户连续跳过相似风格的候选人，可能偏好设置不合理
- search_help：用户搜索很多次但都不满意，可能需要调整搜索策略
- chat_encouragement：用户开始聊天但只聊2句，可能需要鼓励
- retention：用户好久没用了，可能需要挽留

请灵活判断，不要机械套用规则。
"""

    response = await call_ai_model_with_schema(
        prompt=prompt,
        schema=INTERVENTION_SCHEMA,
        model="claude-sonnet-5",
    )

    return response


# 集成到系统（文件：discovery_system/service.py）
async def check_proactive_intervention(session: StoredSession):
    # 每次会话结束时检查是否需要主动干预
    user_behaviors = aggregate_user_behaviors(session)
    current_context = {
        "scene": "discovery",
        "session_duration": session.duration,
        "task_completed": session.task_completed,
    }

    intervention = await decide_proactive_intervention(
        user_behaviors=user_behaviors,
        current_context=current_context,
    )

    if intervention["intervention_needed"]:
        # 存储干预信息，下次会话开始时执行
        store_intervention_message(
            user_key=session.user_key,
            intervention=intervention,
        )
```

---

### Phase 4：数据库迁移与部署

**目标**：安全地实施改造，避免影响现有功能

#### 4.1 数据库迁移计划

**迁移1：扩展 metadata_json 字段**

```python
# 文件：db_migrations/targets/chat/m0008_extend_appearance_feedback_metadata.py

class Migration:
    """扩展 appearance_feedback_events 表的 metadata_json 字段"""

    def up(self):
        # 无需改变表结构（metadata_json 已经是 LONGTEXT）
        # 只需要更新前端埋点和后端API

        # 兼容性处理：新字段缺失时使用默认值
        # 前端埋点代码需要逐步上线，老数据不受影响

    def down(self):
        # 回滚：前端埋点恢复旧版本
        # 后端API忽略新字段
```

**迁移2：扩展 discovery_search_runs 表**

```python
# 文件：db_migrations/targets/chat/m0009_extend_discovery_search_runs.py

class Migration:
    """扩展 discovery_search_runs 表结构"""

    def up(self):
        # 添加新字段（nullable，不影响现有数据）
        ALTER_TABLE_ADD_COLUMNS(
            table="discovery_search_runs",
            columns=[
                ColumnDef("search_pattern", "VARCHAR(20)", nullable=True),
                ColumnDef("retry_count", "INT", nullable=True),
                ColumnDef("result_interaction_ratio", "FLOAT", nullable=True),
                ColumnDef("search_goal", "VARCHAR(50)", nullable=True),
                ColumnDef("criteria_changes_json", "LONGTEXT", nullable=True),
            ],
        )

    def down(self):
        ALTER_TABLE_DROP_COLUMNS(
            table="discovery_search_runs",
            columns=["search_pattern", "retry_count", "result_interaction_ratio", "search_goal", "criteria_changes_json"],
        )
```

**迁移3：新增 discovery_session_quality 表**

```python
# 文件：db_migrations/targets/chat/m0010_add_discovery_session_quality_table.py

class Migration:
    """新增 discovery_session_quality 表"""

    def up(self):
        CREATE_TABLE(
            table="discovery_session_quality",
            columns=[
                ColumnDef("session_id", "VARCHAR(191)", primary_key=True),
                ColumnDef("user_key", "VARCHAR(191)"),
                ColumnDef("profile_id", "BIGINT"),
                ColumnDef("turn_count", "INT"),
                ColumnDef("task_completion", "BOOLEAN"),
                ColumnDef("drop_point", "VARCHAR(50)", nullable=True),
                ColumnDef("drop_reason", "VARCHAR(50)", nullable=True),
                ColumnDef("return_likelihood", "FLOAT", nullable=True),
                ColumnDef("satisfaction_score", "FLOAT", nullable=True),
                ColumnDef("session_duration_ms", "BIGINT"),
                ColumnDef("created_at", "DATETIME"),
            ],
        )

    def down(self):
        DROP_TABLE("discovery_session_quality")
```

#### 4.2 灰度发布计划

**发布策略**：

| 阶段 | 发布内容 | 灰度比例 | 验证方式 | 回滚方案 |
|------|---------|---------|---------|---------|
| **Stage 1** | 前端埋点（补充新字段） | 10% | 验证新字段是否正确收集 | 前端关闭新埋点 |
| **Stage 2** | 后端API（接收新字段） | 30% | 验证数据是否正确存储 | API忽略新字段 |
| **Stage 3** | Phase 1改造（移除硬编码） | 50% | A/B测试：AI判断 vs 硬编码判断 | 回滚到硬编码逻辑 |
| **Stage 4** | Phase 3新增（AI场景） | 100% | 验证AI场景效果 | 关闭AI场景 |

**A/B测试方案**（Stage 3）：

```python
# 文件：task_scheduler/config.py

AI_NATIVE_BEHAVIOR_ANALYSIS_CONFIG = {
    "enabled": true,
    "gray_scale_ratio": 0.5,  # 50%用户使用新逻辑
    "fallback_to_hardcoded": true,  # 新逻辑失败时回退到硬编码
    "ab_test_groups": {
        "control": "hardcoded_threshold",  # 对照组：硬编码阈值
        "experiment": "ai_behavior_analysis",  # 实验组：AI分析
    },
    "metrics_to_track": [
        "recommendation_accuracy",  # 推荐准确率
        "user_engagement_rate",  # 用户互动率
        "match_success_rate",  # 匹配成功率
    ],
}
```

---

### Phase 5：效果监控与迭代优化

**目标**：持续监控改造效果，迭代优化

#### 5.1 监控指标设计

| 监控维度 | 指标 | 预期改进 | 监控方式 |
|---------|------|---------|---------|
| **推荐准确率** | 用户表达兴趣的比例 | 提升15-25% | A/B测试对比 |
| **用户互动率** | 用户查看详情、聊天的比例 | 提升10-20% | 行为事件统计 |
| **匹配成功率** | 双方表达兴趣的比例 | 提升10-15% | 匹配记录统计 |
| **用户满意度** | 用户反馈评分 | 提升0.3-0.5分 | 问卷调查 |
| **AI判断准确性** | AI判断与实际行为的一致性 | >85% | 离线验证 |
| **系统性能** | AI调用延迟、成本 | 延迟<500ms，成本可控 | 性能监控 |

#### 5.2 验证方案

**验证1：AI判断 vs 硬编码判断对比**

```python
# 文件：tests/test_ai_behavior_analysis.py

async def test_ai_intent_analysis_accuracy():
    """验证AI行为意图判断的准确性"""

    # 1. 准备测试数据（真实用户行为序列）
    test_cases = [
        {
            "behaviors": [
                {"action": "view_detail", "duration_ms": 8500},
                {"action": "swipe_photo", "count": 3},
                {"action": "scroll_section", "section": "hobbies"},
            ],
            "expected_intent": "considering_match",  # 人工标注的真实意图
            "expected_weight": 4.5,
        },
        {
            "behaviors": [
                {"action": "view_detail", "duration_ms": 1500},
                {"action": "exit", "delay_ms": 200},
            ],
            "expected_intent": "quick_browse",
            "expected_weight": 1.0,
        },
    ]

    # 2. AI判断
    ai_results = []
    for case in test_cases:
        result = await analyze_user_intent_from_behavior_sequence(
            behaviors=case["behaviors"],
            context={},
        )
        ai_results.append(result)

    # 3. 硬编码判断（对照组）
    hardcoded_results = []
    for case in test_cases:
        result = classify_click_quality_old(
            detail_view_duration_ms=case["behaviors"][0]["duration_ms"],
            photo_swipe_count=case["behaviors"][1].get("count", 0),
        )
        hardcoded_results.append(result)

    # 4. 对比准确性
    ai_accuracy = calculate_accuracy(ai_results, test_cases)
    hardcoded_accuracy = calculate_accuracy(hardcoded_results, test_cases)

    print(f"AI判断准确率: {ai_accuracy}%")
    print(f"硬编码判断准确率: {hardcoded_accuracy}%")
    print(f"AI相对提升: {ai_accuracy - hardcoded_accuracy}%")

    # 5. 验证AI准确率 > 硬编码准确率
    assert ai_accuracy > hardcoded_accuracy
    assert ai_accuracy > 85  # AI准确率应 > 85%
```

**验证2：推荐效果对比**

```python
# 文件：tests/test_recommendation_improvement.py

async def test_recommendation_accuracy_improvement():
    """验证推荐准确率提升"""

    # 1. A/B测试数据
    control_group = get_users_using_hardcoded_logic()  # 对照组
    experiment_group = get_users_using_ai_logic()  # 实验组

    # 2. 统计关键指标
    metrics = {
        "control": {
            "express_interest_rate": calculate_interest_rate(control_group),
            "match_rate": calculate_match_rate(control_group),
            "user_engagement": calculate_engagement(control_group),
        },
        "experiment": {
            "express_interest_rate": calculate_interest_rate(experiment_group),
            "match_rate": calculate_match_rate(experiment_group),
            "user_engagement": calculate_engagement(experiment_group),
        },
    }

    # 3. 计算提升比例
    improvement = {
        "express_interest_rate": metrics["experiment"]["express_interest_rate"] - metrics["control"]["express_interest_rate"],
        "match_rate": metrics["experiment"]["match_rate"] - metrics["control"]["match_rate"],
        "user_engagement": metrics["experiment"]["user_engagement"] - metrics["control"]["user_engagement"],
    }

    print(f"表达兴趣率提升: {improvement['express_interest_rate']}%")
    print(f"匹配成功率提升: {improvement['match_rate']}%")
    print(f"用户互动率提升: {improvement['user_engagement']}%")

    # 4. 验证提升 > 10%
    assert improvement["express_interest_rate"] > 10
    assert improvement["match_rate"] > 10
```

---

## 四、实施优先级与时间规划

### 4.1 优先级排序（按价值排序）

| 优先级 | Phase | 改造内容 | 预估工作量 | 价值 | 风险 |
|--------|-------|---------|-----------|------|------|
| **P0** | Phase 1 | 移除硬编码规则 | 3天 | ⭐⭐⭐⭐⭐ | 低（可回退） |
| **P1** | Phase 2 | 补充缺失数据收集 | 5天 | ⭐⭐⭐⭐ | 低（兼容性好） |
| **P2** | Phase 3 | 新增AI场景 | 7天 | ⭐⭐⭐⭐⭐ | 中（需验证） |
| **P3** | Phase 4 | 数据库迁移与部署 | 2天 | ⭐⭐⭐ | 低（标准流程） |
| **P4** | Phase 5 | 效果监控与迭代 | 3天 | ⭐⭐⭐⭐ | 低（持续优化） |

**总工作量：约20天**

### 4.2 实施时间规划

```
Week 1: Phase 1（移除硬编码规则） + Phase 2（补充数据收集）
Week 2: Phase 3（新增AI场景） + Phase 4（数据库迁移）
Week 3: Phase 5（效果监控） + 迭代优化
```

---

## 五、预期效果

### 5.1 系统能力提升

| 能力维度 | 当前状态 | 改造后状态 | 提升 |
|---------|---------|-----------|------|
| **行为理解** | 硬编码阈值判断（机械） | AI理解意图（灵活） | ⬆️⬆️⬆️ |
| **偏好学习** | 统计频率（无理解） | AI分析原因（深度理解） | ⬆️⬆️⬆️ |
| **推荐策略** | 硬编码分级（固定） | AI动态调整（灵活） | ⬆️⬆️ |
| **数据收集** | 基础行为（不完整） | 完整行为+上下文（全面） | ⬆️⬆️⬆️ |
| **主动能力** | 被动记录（无主动） | AI主动干预（智能） | ⬆️⬆️⬆️ |

### 5.2 业务指标提升（预期）

| 业务指标 | 当前基准 | 预期提升 | 验证方式 |
|---------|---------|---------|---------|
| **推荐准确率** | 用户表达兴趣比例15% | 提升20% → 18% | A/B测试 |
| **匹配成功率** | 双方表达兴趣比例8% | 提升15% → 9.2% | 匹配记录统计 |
| **用户互动率** | 用户查看详情比例40% | 提升10% → 44% | 行为事件统计 |
| **用户满意度** | 用户反馈评分3.8/5 | 提升0.5分 → 4.3/5 | 问卷调查 |
| **用户留存率** | 7日留存率60% | 提升5% → 63% | 留存分析 |

---

## 六、风险与应对

### 6.1 风险清单

| 风险类型 | 风险描述 | 严重程度 | 应对方案 |
|---------|---------|---------|---------|
| **AI判断不稳定** | AI判断可能与硬编码不一致，导致推荐混乱 | 中 | 灰度发布+A/B测试验证，回退机制 |
| **AI成本过高** | 每次行为都调用AI，可能成本过高 | 中 | 智能缓存+批量处理+轻量模型 |
| **数据收集过多** | 新增埋点可能影响性能或隐私 | 低 | 分步上线+性能监控+隐私合规 |
| **迁移失败** | 数据库迁移可能失败，影响服务 | 低 | 标准迁移流程+回滚预案 |
| **用户反感** | 主动干预可能被用户反感 | 中 | 干扰频率控制+用户反馈机制 |

### 6.2 应对方案

**应对1：AI判断不稳定**

```python
# 文件：match_domain/ai_behavior_analyzer.py

async def analyze_user_intent_with_fallback(
    behaviors: list[dict],
    context: dict,
) -> dict:
    """AI判断 + 回退机制"""

    try:
        # 1. 尝试AI判断
        ai_result = await analyze_user_intent_from_behavior_sequence(
            behaviors=behaviors,
            context=context,
        )

        # 2. 验证AI结果合理性
        if validate_ai_result(ai_result):
            return ai_result
        else:
            # AI结果不合理，回退到硬编码
            return classify_click_quality_old(
                detail_view_duration_ms=behaviors[0].get("duration_ms", 0),
                photo_swipe_count=behaviors[1].get("count", 0),
            )

    except Exception as e:
        # AI调用失败，回退到硬编码
        logger.error(f"AI分析失败，回退到硬编码: {e}")
        return classify_click_quality_old(...)
```

**应对2：AI成本过高**

```python
# 文件：match_domain/ai_cost_optimizer.py

# 智能缓存：相同行为序列不重复调用AI
BEHAVIOR_ANALYSIS_CACHE = TTLCache(maxsize=1000, ttl=3600)

async def analyze_user_intent_with_cache(
    behaviors: list[dict],
    context: dict,
) -> dict:
    """AI判断 + 缓存优化"""

    # 1. 检查缓存
    cache_key = hash_behaviors(behaviors)
    if cache_key in BEHAVIOR_ANALYSIS_CACHE:
        return BEHAVIOR_ANALYSIS_CACHE[cache_key]

    # 2. 调用AI
    result = await analyze_user_intent_from_behavior_sequence(behaviors, context)

    # 3. 存入缓存
    BEHAVIOR_ANALYSIS_CACHE[cache_key] = result

    return result


# 批量处理：多个行为序列批量调用AI
async def batch_analyze_user_intents(
    behavior_sequences: list[list[dict]],
) -> list[dict]:
    """批量AI判断（节省成本）"""
    # 使用批量API调用，减少请求次数
    batch_results = await call_ai_model_batch(
        prompts=[build_prompt(behaviors) for behaviors in behavior_sequences],
        model="claude-haiku-4-5",  # 批量处理用轻量模型
    )
    return batch_results
```

---

## 七、总结

### 7.1 核心改造原则

**遵循AI Native架构**：
- ✅ 移除硬编码规则，让AI自主判断
- ✅ 补充完整数据，让AI有足够信息决策
- ✅ 新增AI场景，让AI主动优化推荐
- ✅ 灰度发布验证，确保改造效果
- ✅ 持续监控迭代，持续优化系统

**避免反模式**：
- ❌ 不要保留硬编码阈值（AI Native原则）
- ❌ 不要让工具包含业务逻辑（职责分离）
- ❌ 不要硬编码触发词映射表（自然语言交互）
- ❌ 不要输出固定模板（AI动态生成）

### 7.2 改造后的系统架构

```
用户交互行为（完整收集）
    ↓
AI分析行为序列（理解意图）
    ↓
AI判断行为权重（动态调整）
    ↓
AI判断偏好置信度（灵活判断）
    ↓
AI分析偏好原因（深度理解）
    ↓
AI预测下一步行为（主动推荐）
    ↓
AI检测行为异常（主动干预）
    ↓
AI决定是否干预（主动帮助）
    ↓
推荐算法（AI驱动）
    ↓
个性化推荐（精准匹配）
```

### 7.3 最终目标

**让系统从"记账员"变成"聪明助手"**：
- 真正理解用户意图（而非机械判断）
- 深度分析偏好原因（而非统计频率）
- 主动预测用户需求（而非被动响应）
- 主动帮助用户解决问题（而非只记录）

---

**文档版本**：v1.0
**创建时间**：2026-07-08
**预计实施周期**：3周
**预期效果**：推荐准确率提升20%，匹配成功率提升15%