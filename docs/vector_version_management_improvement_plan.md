# 画像向量版本管理改进方案：AI自主判断语义关系

## 📋 一、大白话解释：核心思想是什么？

### 🎯 用"照片更新"的例子来理解

想象你在更新你的个人照片：

**情况1：补充关系（应该保留所有照片）**
```
第1天：你拍了"正面照片"
第3天：你拍了"侧面照片"

AI判断：
→ 查询历史：有"正面照片"
→ 对比新内容："侧面照片"
→ AI推理：正面和侧面不是冲突，是补充（正面+侧面更全面）
→ AI决定：保留两张照片 → "正面照片、侧面照片"

结果：两张照片都保留，展示更完整的你
```

**情况2：冲突关系（应该替换旧照片）**
```
第1个月：你拍了"长发照片"
第3个月后：你拍了"短发照片"

AI判断：
→ 查询历史：有"长发照片"
→ 对比新内容："短发照片"
→ AI推理：长发和短发是冲突（你剪了头发，真实变化）
→ AI决定：删除旧照片 → 只保留"短发照片"

结果：旧照片删除，只保留最新照片（因为真实变化了）
```

**情况3：细化关系（应该用更具体的照片）**
```
第1天：你拍了"全身照片"
第3天：你拍了"全身照片（穿西装）"

AI判断：
→ 查询历史：有"全身照片"
→ 对比新内容："全身照片（穿西装）"
→ AI推理：新照片更具体（包含旧照片，且更详细）
→ AI决定：用新照片 → "全身照片（穿西装）"

结果：用更具体的照片替换
```

---

### 🔄 对比：当前设计 vs 改进设计

#### ❌ 当前设计（简单粗暴的"一刀切"）

```
代码里硬编码规则：

"性格特质" → 只保留最新版本（replace）
- 不管新内容是补充还是冲突
- 简单粗暴：直接删除旧版本

"择偶期望" → 保留所有版本（average）
- 不管新内容是补充还是冲突
- 简单粗暴：所有版本都保留

就像：
- 照片管理：要么只保留最新照片，要么保留所有照片
- 不管新照片是补充（侧面）还是冲突（短发）
```

**具体问题：**

| 例子 | 当前处理 | 实际应该怎么处理 |
|------|---------|---------------|
| "内向" → "喜欢安静" | 删除"内向"，只保留"喜欢安静" | **应该合并**：内向的人通常喜欢安静，是补充 |
| "喜欢热闹" → "喜欢安静" | 保留两个版本（average） | **应该覆盖**：完全相反，是冲突 |
| "温柔" → "温柔、能理解工作" | 删除"温柔" | **应该合并**：后者包含前者，是细化 |

---

#### ✅ 改进设计（AI自己判断）

```
AI自己判断：

每次更新时：
1. 查询历史版本
2. 对比新旧内容
3. AI判断语义关系（是补充？是冲突？是细化？）
4. AI决定操作（合并还是覆盖）
```

**AI判断的例子：**

| 例子 | AI判断 | AI决定 | 理由 |
|------|-------|--------|------|
| "内向" → "喜欢安静" | 补充关系 | 合并 → "内向、喜欢安静" | 内向的人通常喜欢安静，不冲突 |
| "喜欢热闹" → "喜欢安静"（3个月后） | 冲突关系 | 覆盖 → 只保留"喜欢安静" | 完全相反，真实变化（剪头发了） |
| "温柔" → "温柔、能理解工作" | 细化关系 | 合并 → "温柔、能理解工作" | 后者包含前者，更具体 |

---

### 🔍 AI判断的四个标准

**AI判断时看四个维度：**

#### 1. 语义相似度（意思相近不相近）
```
"内向" vs "喜欢安静" → 相似度高（内向→安静，意思相近） → 补充
"喜欢热闹" vs "喜欢安静" → 冲突（意思相反） → 冲突
```

#### 2. 逻辑关系（逻辑上顺不顺）
```
"内向" → "喜欢安静" → 逻辑顺延（内向的人→安静） → 补充
"温柔" → "温柔、能理解工作" → 包含关系（后者包含前者） → 细化
```

#### 3. 时间因素（时间间隔）
```
同一天内变化："内向" → "喜欢安静" → 短期 → 倾向于补充
3个月后变化："喜欢热闹" → "喜欢安静" → 长期 → 倾向于冲突（真实变化）
```

#### 4. 历史趋势（变化趋势）
```
连续变化："内向" → "内向、安静" → "喜欢独处" → 连续变化 → 补充
突然变化："内向" → "喜欢热闹" → 突然相反 → 可能测试或错误
```

---

### 💡 大白话总结

**一句话总结：**

> 从"简单粗暴的一刀切规则"  
> 到"AI智能判断该保留还是删除"

**大白话理解：**

- **当前**：代码规定"性格特质只能有一个版本"，不管新内容是补充还是冲突
- **改进**：AI自己看新旧内容是"补充"还是"冲突"，然后决定是"合并"还是"覆盖"

**例子对比：**

```
场景："内向" → "喜欢安静"（同一天内）

当前设计（replace策略）：
→ 删除"内向"，只保留"喜欢安静"
→ 问题：丢失了"内向"这个重要信息

改进设计（AI判断）：
→ 查历史："内向"
→ 对比新内容："喜欢安静"
→ AI判断：内向的人通常喜欢安静，是补充关系
→ AI决定：合并 → "内向、喜欢安静"
→ 结果：保留完整信息
```

---

## 📋 二、改进动机（技术层面）

### ❌ 当前设计的问题

**硬编码策略导致的局限性：**

```python
# 当前设计：硬编码策略
VECTOR_TYPES_CONFIG = {
    "personality_traits": {"update_policy": "replace"},  ← 问题1：可能丢失补充信息
    "values": {"update_policy": "replace"},              ← 问题2：无法处理细化关系
    "partner_expectation": {"update_policy": "average"}, ← 问题3：可能保留冲突信息
    "emotional_needs": {"update_policy": "average"},     ← 问题4：无法处理真实变化
}
```

**具体问题案例：**

| 问题类型 | 硬编码策略 | 实际情况 | 期望处理 |
|---------|-----------|---------|---------|
| **丢失补充信息** | personality_traits用replace | "内向" → "喜欢安静"（补充关系） | 应该合并："内向、喜欢安静" |
| **无法处理细化** | values用replace | "重视家庭" → "重视家庭、重视工作"（细化） | 应该合并："重视家庭、重视工作" |
| **保留冲突信息** | partner_expectation用average | "喜欢热闹" → "喜欢安静"（冲突） | 应该覆盖："喜欢安静"（真实变化） |
| **无法判断变化** | emotional_needs用average | "需要陪伴" → "需要独立"（变化） | 应该覆盖："需要独立"（真实变化） |

---

## 🎯 二、改进方案核心思想

### ✅ Agent Native架构原则

**从"规则驱动"到"语义驱动"：**

```
❌ 当前：硬编码规则（代码判断）
personality_traits → replace（死规则）
partner_expectation → average（死规则）

✅ 改进：AI自主判断（语义理解）
→ 查询历史："内向"
→ 对比新内容："喜欢安静"
→ AI推理：语义相似度0.85，逻辑上是补充关系
→ AI决定：merge → "内向、喜欢安静"
→ AI输出：判断理由"内向的人通常喜欢安静，这是补充"
```

**设计原则：**

1. ✅ AI根据语义关系自主判断（补充/冲突/细化）
2. ✅ AI输出判断理由（可解释）
3. ✅ AI考虑时间因素（短期补充vs长期变化）
4. ✅ 只有AI无法判断时，才fallback到默认规则
5. ❌ 禁止硬编码策略（replace/average）
6. ❌ 禁止代码判断（if field then policy）

---

## 📊 三、语义关系分类

### 🔍 三种语义关系

| 关系类型 | 定义 | 判断依据 | 处理方式 | 示例 |
|---------|------|---------|---------|------|
| **补充关系**<br>(supplement) | 新内容补充旧内容，两者语义兼容 | - 语义相似度高（cosine>0.7）<br>- 逻辑上兼容（内向→安静）<br>- 短期内变化 | **合并**<br>合并文本 → 新向量<br>覆盖旧版本 | "内向" → "喜欢安静"<br>合并："内向、喜欢安静" |
| **冲突关系**<br>(conflict) | 新内容与旧内容矛盾，语义相反 | - 语义冲突度高<br>- 逻辑上相反（热闹→安静）<br>- 长期变化 | **覆盖**<br>新文本 → 新向量<br>软删除旧版本 | "喜欢热闹" → "喜欢安静"<br>覆盖："喜欢安静" |
| **细化关系**<br>(refinement) | 新内容更具体，包含旧内容 | - 新内容包含旧内容<br>- 细节更丰富<br>- 短期内变化 | **合并**<br>使用新文本（更具体）<br>覆盖旧版本 | "温柔" → "温柔、能理解工作"<br>使用："温柔、能理解工作" |

---

## 🔧 四、完整实现方案

### 1. 新增核心函数：smart_vector_update()

```python
"""智能向量更新：AI自主判断语义关系，决定合并或覆盖

文件：match_domain/vector_store_lite.py（新增）
"""

async def smart_vector_update(
    user_id: int,
    vector_type: str,
    new_text: str,
    conversation_id: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    AI自主判断的向量更新
    
    核心流程：
    1. 查询历史版本
    2. AI判断语义关系（补充/冲突/细化）
    3. 根据AI判断执行操作（merge/replace）
    4. 记录判断理由
    
    Args:
        user_id: 用户ID
        vector_type: 向量类型（personality_traits等）
        new_text: 新提炼的文本
        conversation_id: 对话ID
        conversation_time: 对话时间（用于判断短期/长期变化）
    
    Returns:
        {
            "action": "merge/replace",
            "merged_text": "合并后的文本（如果merge）",
            "final_text": "最终文本",
            "ai_decision": {...},
            "version": 新版本号
        }
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1：查询历史版本
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    historical_versions = get_historical_vectors_with_time(
        user_id=user_id,
        vector_type=vector_type,
        limit=3,  # 只取最近3个版本
    )
    
    if not historical_versions:
        # 没有历史版本，直接插入（首次记录）
        _logger.info(f"首次向量记录: user_id={user_id}, vector_type={vector_type}, text={new_text}")
        return _direct_save_vector(user_id, vector_type, new_text, conversation_id)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2：取最新版本的历史文本
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    latest_historical = historical_versions[0]
    historical_text = latest_historical["raw_text"]
    historical_time = latest_historical["create_time"]
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3：计算时间差距（判断短期/长期变化）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    current_time = conversation_time or datetime.now()
    time_gap_days = (current_time - historical_time).days
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4：AI判断语义关系
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    ai_decision = await _ai_judge_semantic_relation(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        time_gap_days=time_gap_days,
        historical_versions=historical_versions,  # 提供完整历史上下文
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 5：根据AI判断执行操作
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if ai_decision["action"] == "merge":
        # AI决定合并
        merged_text = ai_decision["merged_text"]
        merged_vector = await generate_embedding(merged_text)
        
        # 覆盖旧版本（用合并后的文本）
        deactivate_old_vectors(user_id, vector_type)
        result = save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=merged_vector,
            raw_text=merged_text,
            conversation_id=conversation_id,
        )
        
        _logger.info(
            f"AI决定合并: {historical_text} + {new_text} → {merged_text}\n"
            f"判断理由: {ai_decision['reason']}\n"
            f"置信度: {ai_decision['confidence']}"
        )
        
        return {
            "action": "merge",
            "merged_text": merged_text,
            "final_text": merged_text,
            "ai_decision": ai_decision,
            "version": result["version"],
        }
        
    else:
        # AI决定覆盖
        new_vector = await generate_embedding(new_text)
        
        deactivate_old_vectors(user_id, vector_type)
        result = save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=new_vector,
            raw_text=new_text,
            conversation_id=conversation_id,
        )
        
        _logger.info(
            f"AI决定覆盖: {historical_text} → {new_text}\n"
            f"判断理由: {ai_decision['reason']}\n"
            f"置信度: {ai_decision['confidence']}"
        )
        
        return {
            "action": "replace",
            "merged_text": None,
            "final_text": new_text,
            "ai_decision": ai_decision,
            "version": result["version"],
        }
```

---

### 2. 新增AI判断函数：_ai_judge_semantic_relation()

```python
"""AI判断语义关系

文件：match_domain/vector_store_lite.py（新增）
"""

async def _ai_judge_semantic_relation(
    historical_text: str,
    new_text: str,
    vector_type: str,
    time_gap_days: int,
    historical_versions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    AI判断新旧内容的语义关系
    
    判断维度：
    1. 语义相似度（cosine similarity）
    2. 逻辑关系（补充/冲突/细化）
    3. 时间因素（短期补充 vs 长期变化）
    4. 历史趋势（连续变化 vs 突然变化）
    
    Args:
        historical_text: 历史版本文本
        new_text: 新版本文本
        vector_type: 向量类型
        time_gap_days: 时间差距（天）
        historical_versions: 历史版本列表（用于分析趋势）
    
    Returns:
        {
            "relation_type": "补充/冲突/细化",
            "confidence": "high/medium/low",
            "action": "merge/replace",
            "merged_text": "合并后的文本（如果merge）",
            "reason": "判断理由（一句话）",
            "analysis": {...}  # 详细分析
        }
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1：构建AI判断Prompt
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    prompt = _build_semantic_judge_prompt(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        time_gap_days=time_gap_days,
        historical_versions=historical_versions,
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2：调用LLM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    try:
        ai_response = await _call_llm_for_json(prompt)
        
        # 验证返回格式
        required_fields = ["relation_type", "confidence", "action", "reason"]
        if not all(field in ai_response for field in required_fields):
            raise ValueError(f"AI返回格式错误，缺少必要字段")
        
        # 如果action是merge，检查merged_text
        if ai_response["action"] == "merge" and "merged_text" not in ai_response:
            raise ValueError("AI决定merge但未提供merged_text")
        
        return ai_response
        
    except Exception as exc:
        _logger.error(f"AI判断失败: {exc}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Step 3：Fallback机制（AI判断失败时的默认规则）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return _fallback_decision(
            historical_text=historical_text,
            new_text=new_text,
            time_gap_days=time_gap_days,
        )
```

---

### 3. 新增Prompt设计：_build_semantic_judge_prompt()

```python
"""构建AI判断Prompt

文件：match_domain/vector_store_lite.py（新增）
"""

def _build_semantic_judge_prompt(
    historical_text: str,
    new_text: str,
    vector_type: str,
    time_gap_days: int,
    historical_versions: list[dict[str, Any]],
) -> str:
    """
    构建AI判断语义关系的Prompt
    
    设计原则：
    - 提供完整上下文（历史版本、时间差距）
    - 明确判断维度（语义、逻辑、时间、趋势）
    - 要求输出判断理由（可解释）
    - 严格JSON格式输出（结构化）
    """
    
    # 构建历史趋势描述
    trend_description = ""
    if len(historical_versions) > 1:
        trend_texts = [v["raw_text"] for v in historical_versions]
        trend_description = f"\n历史趋势：{trend_texts[::-1]}（按时间顺序）"
    
    # 时间因素描述
    time_description = ""
    if time_gap_days <= 1:
        time_description = "短期变化（同一天内）：倾向于补充或细化"
    elif time_gap_days <= 7:
        time_description = "短期内变化（一周内）：可能是补充或细化"
    elif time_gap_days <= 30:
        time_description = "中期变化（一个月内）：可能是补充或真实变化"
    else:
        time_description = "长期变化（超过一个月）：可能是真实变化（性格、价值观变化）"
    
    # 向量类型说明
    vector_type_description = {
        "personality_traits": "性格特质（通常稳定，短期变化多为补充/细化）",
        "values": "价值观（长期稳定，短期变化多为补充）",
        "partner_expectation": "择偶期望（可能变化，需根据时间判断）",
        "life_attitude": "生活态度（可能变化，需根据时间判断）",
        "emotional_needs": "情感需求（波动较大，需根据时间判断）",
    }.get(vector_type, "用户特征")
    
    return f"""你是一个画像分析专家，擅长分析用户特征的语义关系。

请分析以下新旧数据的关系：

【用户特征类型】：{vector_type_description}
【历史版本】："{historical_text}"
【新版本】："{new_text}"
【时间差距】：{time_gap_days}天（{time_description}）
{trend_description}

请从以下4个维度判断关系类型：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **语义相似度**：
   - 高相似度（概念相近）：可能细化或补充
   - 低相似度（概念不同）：可能补充
   - 冲突度（语义相反）：冲突关系
   
   示例：
   - "内向" vs "喜欢安静"：高相似度（内向的人通常喜欢安静）→ 补充
   - "温柔" vs "温柔、能理解工作"：高相似度（包含关系）→ 细化
   - "喜欢热闹" vs "喜欢安静"：冲突（语义相反）→ 冲突

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. **逻辑关系**：
   - 补充关系：新内容补充旧内容（两者兼容）
   - 冲突关系：新内容与旧内容矛盾（相反）
   - 细化关系：新内容更具体（包含旧内容）
   
   示例：
   - "内向" → "喜欢安静"：补充（内向→安静，逻辑顺延）
   - "温柔" → "温柔、能理解工作"：细化（"温柔、能理解工作"包含"温柔"）
   - "喜欢热闹" → "喜欢安静"：冲突（相反）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. **时间因素**：
   - 短期变化（同一对话session）：倾向于补充/细化
   - 中期变化（一周内）：可能是补充或细化
   - 长期变化（超过一个月）：可能是真实变化（冲突）
   
   示例：
   - 同session内："内向" → "喜欢安静" → 补充（短期内补充）
   - 3个月后："喜欢热闹" → "喜欢安静" → 冲突（真实变化）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. **历史趋势**：
   - 连续变化：可能是真实变化趋势
   - 突然变化：可能是补充或冲突
   
   示例：
   - 趋势："内向" → "内向、安静" → "喜欢独处" → 连续变化，真实趋势
   - 突然："内向" → "喜欢热闹" → 突然相反，可能是测试或错误

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【判断规则】：
1. 优先考虑语义相似度和逻辑关系
2. 时间因素作为辅助判断（短期倾向于补充，长期可能是真实变化）
3. 如果不确定，优先选择"补充"（保留信息）
4. 如果明确冲突，选择"冲突"（覆盖旧版本）

【输出格式】：
{
    "relation_type": "补充/冲突/细化",
    "confidence": "high/medium/low",
    "action": "merge/replace",
    "merged_text": "合并后的文本（如果action=merge，必须提供）",
    "reason": "判断理由（一句话，简洁明了）",
    "analysis": {
        "semantic_similarity": "high/medium/low/conflict",
        "logic_relation": "补充/冲突/细化",
        "time_factor": "短期/中期/长期",
        "trend_factor": "连续/突然"
    }
}

请严格按照JSON格式输出，不要输出任何其他内容。
"""
```

---

### 4. 改造现有函数：save_vectors_for_summary()

```python
"""改造：向量存储函数

文件：match_domain/session_end_processor.py（改造）

改造内容：
- 移除硬编码策略调用
- 改为调用smart_vector_update()
"""

async def save_vectors_for_summary(
    session_id: str,
    requester_id: int,
    summary_data: dict[str, str],
) -> list[str]:
    """
    将摘要数据向量化并存储
    
    改造点：
    - 移除 VECTOR_TYPES_CONFIG 的硬编码策略判断
    - 改为调用 smart_vector_update()（AI自主判断）
    """
    
    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import smart_vector_update  # ← 改造：导入新函数
    
    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    
    vectorized_keys: list[str] = []
    
    for summary_key, summary_text in summary_data.items():
        if not str(summary_text or "").strip():
            continue
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 改造：调用AI自主判断的向量更新
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        result = await smart_vector_update(
            user_id=requester_id,
            vector_type=summary_key,
            new_text=summary_text,
            conversation_id=session_id,
        )
        
        if result.get("version"):
            vectorized_keys.append(summary_key)
            
            # 记录AI判断结果（用于审计和可解释性）
            _logger.info(
                f"向量更新完成: key={summary_key}, "
                f"action={result['action']}, "
                f"final_text={result['final_text']}, "
                f"ai_reason={result['ai_decision']['reason']}"
            )
    
    return vectorized_keys
```

---

### 5. 新增辅助函数：Fallback机制

```python
"""Fallback机制：AI判断失败时的默认规则

文件：match_domain/vector_store_lite.py（新增）

设计原则：
- 尽量减少fallback使用（AI判断应该覆盖大部分场景）
- Fallback规则也应该智能（根据时间判断）
"""

def _fallback_decision(
    historical_text: str,
    new_text: str,
    time_gap_days: int,
) -> dict[str, Any]:
    """
    Fallback决策：AI判断失败时的默认规则
    
    默认规则（保守策略）：
    - 短期内变化（time_gap_days <= 7）：倾向于merge（保留信息）
    - 长期变化（time_gap_days > 30）：倾向于replace（可能真实变化）
    - 中期变化：简单字符串拼接合并
    
    Args:
        historical_text: 历史版本文本
        new_text: 新版本文本
        time_gap_days: 时间差距
    
    Returns:
        {
            "relation_type": "补充（fallback）",
            "confidence": "low",
            "action": "merge/replace",
            "merged_text": "合并文本（如果merge）",
            "reason": "fallback决策，AI判断失败"
        }
    """
    
    _logger.warning(
        f"AI判断失败，使用fallback决策: "
        f"historical={historical_text}, new={new_text}, time_gap={time_gap_days}天"
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Fallback规则（保守策略）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if time_gap_days <= 7:
        # 短期内变化：倾向于merge（保留信息）
        merged_text = f"{historical_text}、{new_text}"
        return {
            "relation_type": "补充（fallback）",
            "confidence": "low",
            "action": "merge",
            "merged_text": merged_text,
            "reason": f"短期内变化（{time_gap_days}天），fallback决策倾向于合并",
        }
        
    elif time_gap_days > 30:
        # 长期变化：倾向于replace（可能真实变化）
        return {
            "relation_type": "冲突（fallback）",
            "confidence": "low",
            "action": "replace",
            "merged_text": None,
            "reason": f"长期变化（{time_gap_days}天），fallback决策倾向于覆盖",
        }
        
    else:
        # 中期变化：保守策略，简单合并
        merged_text = f"{historical_text}、{new_text}"
        return {
            "relation_type": "补充（fallback）",
            "confidence": "low",
            "action": "merge",
            "merged_text": merged_text,
            "reason": f"中期变化（{time_gap_days}天），fallback决策保守合并",
        }
```

---

## 📊 五、完整例子演示

### 📋 例子1：补充关系（AI判断merge）

```python
# 场景：第1次对话 → 第2次对话（同一天）

# Step 1：查询历史版本
historical_versions = [
    {
        "raw_text": "内向",
        "create_time": "2024-01-15 10:00:00",
        "vector_version": 1,
    }
]

# Step 2：新提炼文本
new_text = "喜欢安静"

# Step 3：计算时间差距
time_gap_days = 0  # 同一天

# Step 4：AI判断（Prompt）
"""
【历史版本】："内向"
【新版本】："喜欢安静"
【时间差距】：0天（短期变化，同一天内）

请判断关系类型...
"""

# Step 5：AI输出
{
    "relation_type": "补充",
    "confidence": "high",
    "action": "merge",
    "merged_text": "内向、喜欢安静",
    "reason": "内向的人通常喜欢安静，逻辑上是补充关系",
    "analysis": {
        "semantic_similarity": "high",
        "logic_relation": "补充",
        "time_factor": "短期",
        "trend_factor": "连续"
    }
}

# Step 6：执行操作
→ deactivate_old_vectors(user_id, "personality_traits")
→ save_vector("内向、喜欢安静", [0.12, 0.25, ...], version=2)

# 结果：合并后的向量覆盖旧版本
```

---

### 📋 例子2：冲突关系（AI判断replace）

```python
# 场景：第1次对话 → 第2次对话（3个月后）

# Step 1：查询历史版本
historical_versions = [
    {
        "raw_text": "喜欢热闹",
        "create_time": "2024-01-15 10:00:00",
        "vector_version": 1,
    }
]

# Step 2：新提炼文本
new_text = "喜欢安静"

# Step 3：计算时间差距
time_gap_days = 90  # 3个月

# Step 4：AI判断（Prompt）
"""
【历史版本】："喜欢热闹"
【新版本】："喜欢安静"
【时间差距】：90天（长期变化，超过一个月）

请判断关系类型...
"""

# Step 5：AI输出
{
    "relation_type": "冲突",
    "confidence": "high",
    "action": "replace",
    "merged_text": null,
    "reason": "热闹和安静语义相反，长期变化表明真实性格变化",
    "analysis": {
        "semantic_similarity": "conflict",
        "logic_relation": "冲突",
        "time_factor": "长期",
        "trend_factor": "突然"
    }
}

# Step 6：执行操作
→ deactivate_old_vectors(user_id, "personality_traits")
→ save_vector("喜欢安静", [0.4, 0.6, ...], version=2)

# 结果：新向量覆盖旧版本（真实变化）
```

---

### 📋 例子3：细化关系（AI判断merge）

```python
# 场景：第1次对话 → 第2次对话（一周内）

# Step 1：查询历史版本
historical_versions = [
    {
        "raw_text": "温柔",
        "create_time": "2024-01-15 10:00:00",
        "vector_version": 1,
    }
]

# Step 2：新提炼文本
new_text = "温柔、能理解程序员的工作"

# Step 3：计算时间差距
time_gap_days = 3  # 3天后

# Step 4：AI判断（Prompt）
"""
【历史版本】："温柔"
【新版本】："温柔、能理解程序员的工作"
【时间差距】：3天（短期内变化）

请判断关系类型...
"""

# Step 5：AI输出
{
    "relation_type": "细化",
    "confidence": "high",
    "action": "merge",
    "merged_text": "温柔、能理解程序员的工作",  ← 使用新文本（更具体）
    "reason": "新内容包含旧内容，且更具体，是细化关系",
    "analysis": {
        "semantic_similarity": "high",
        "logic_relation": "细化",
        "time_factor": "短期",
        "trend_factor": "连续"
    }
}

# Step 6：执行操作
→ deactivate_old_vectors(user_id, "partner_expectation")
→ save_vector("温柔、能理解程序员的工作", [0.22, 0.45, ...], version=2)

# 结果：使用更具体的文本覆盖旧版本
```

---

## 🎯 六、改造对比表

| 维度 | 当前设计（硬编码策略） | 改进设计（AI自主判断） |
|------|---------------------|---------------------|
| **决策主体** | 规则引擎（代码硬编码） | LLM Agent（语义理解） |
| **灵活性** | 低（无法处理语义差异） | 高（根据实际语义判断） |
| **准确性** | 中（可能丢失补充信息或保留冲突信息） | 高（智能合并或覆盖） |
| **可解释性** | 低（为什么replace/average？） | 高（AI输出判断理由） |
| **时间因素** | 未考虑 | AI考虑短期补充vs长期变化 |
| **历史趋势** | 未考虑 | AI分析连续变化vs突然变化 |
| **维护成本** | 高（需人工调整策略） | 低（AI自主适应） |
| **Fallback机制** | 无 | 有（AI判断失败时的保守策略） |

---

## 📋 七、实施步骤

### 🔄 Phase 1：架构改造（核心）

1. **新增函数**：
   - `smart_vector_update()`：AI自主判断的向量更新
   - `_ai_judge_semantic_relation()`：AI判断语义关系
   - `_build_semantic_judge_prompt()`：构建判断Prompt
   - `_fallback_decision()`：Fallback机制

2. **改造函数**：
   - `save_vectors_for_summary()`：改为调用smart_vector_update()

3. **移除硬编码**：
   - 移除 `VECTOR_TYPES_CONFIG` 的 `update_policy` 字段
   - 移除代码中的策略判断逻辑

### 🔄 Phase 2：测试验证

1. **单元测试**：
   - 测试补充关系案例（"内向" → "喜欢安静"）
   - 测试冲突关系案例（"喜欢热闹" → "喜欢安静"）
   - 测试细化关系案例（"温柔" → "温柔、能理解工作"）

2. **集成测试**：
   - 测试完整画像写入流程
   - 测试向量搜索流程

3. **A/B测试**：
   - 对比硬编码策略 vs AI自主判断的推荐质量

### 🔄 Phase 3：监控优化

1. **监控指标**：
   - AI判断成功率
   - Fallback触发率
   - 用户满意度（推荐质量）

2. **Prompt优化**：
   - 根据实际效果优化判断Prompt
   - 增加更多判断维度

3. **Fallback优化**：
   - 减少Fallback触发（提高AI判断成功率）
   - 优化Fallback规则

---

## 💡 八、关键设计亮点

### 1. **Agent Native架构**

```
✅ 正确设计：
- AI根据语义关系自主判断（补充/冲突/细化）
- AI输出判断理由（可解释）
- AI考虑时间因素和历史趋势
- 只有AI无法判断时，才fallback

❌ 禁止设计：
- 禁止硬编码策略（replace/average）
- 禁止代码判断（if field then policy）
```

### 2. **四维度判断**

```
AI判断时考虑四个维度：

1. 语义相似度：高/中/低/冲突
2. 逻辑关系：补充/冲突/细化
3. 时间因素：短期/中期/长期
4. 历史趋势：连续/突然

综合判断 → 输出决策（merge/replace）
```

### 3. **可解释性**

```
AI输出包含：
- relation_type：关系类型
- confidence：置信度
- reason：判断理由（一句话）
- analysis：详细分析（四个维度）

用户可查看判断理由，理解为什么合并或覆盖
```

### 4. **Fallback机制**

```
AI判断失败时：
- 短期内变化（<=7天）→ merge（保守策略，保留信息）
- 长期变化（>30天）→ replace（可能真实变化）
- 中期变化 → merge（保守策略）

尽量减少Fallback使用，提高AI判断成功率
```

---

## 📋 九、总结

**改进方案核心：**

> 从"硬编码策略"（replace/average）  
> 到"AI自主判断"（语义关系 → merge/replace）

**关键优势：**

1. ✅ 更灵活：根据实际语义判断，而不是死规则
2. ✅ 更准确：智能处理补充、冲突、细化关系
3. ✅ 更可解释：AI输出判断理由
4. ✅ 更智能：考虑时间因素和历史趋势
5. ✅ 更符合Agent Native原则：把决策权交给AI

**实施建议：**

- Phase 1：架构改造（新增核心函数，改造现有函数）
- Phase 2：测试验证（单元测试、集成测试、A/B测试）
- Phase 3：监控优化（监控指标、Prompt优化、Fallback优化）

这个改进方案让画像系统真正实现"AI理解用户特征，而不是代码硬编码规则"，大幅提升推荐质量和系统智能化程度。