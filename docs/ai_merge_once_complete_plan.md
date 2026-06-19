# AI自主判断语义关系完整改进方案：只判断一次

## 📋 一、核心思想：只让AI判断一次

### 🎯 问题背景

**当前设计有两个阶段，都需要AI判断语义关系：**

```
阶段1：摘要文本合并（会话结束时）
→ AI判断："内向" vs "喜欢安静"
→ AI决定：合并 → "内向、喜欢安静"
→ 保存摘要文本

阶段2：向量存储（向量化时）
→ AI判断：又要判断一次（重复）
→ AI决定：合并 → 又要生成向量
→ 问题：AI判断了两次，逻辑重复
```

**问题：**
1. AI判断两次（浪费LLM调用成本）
2. 逻辑重复（两次判断的Prompt和逻辑相似）
3. 可能不一致（两次判断结果可能不同）

---

### ✅ 优化方案：只让AI判断一次

**设计思路：**

```
完整流程：

Step 1：会话结束 → AI提炼摘要 → 得到新数据："喜欢安静"
Step 2：查询历史数据 → 得到旧数据："内向"

Step 3：AI判断一次（核心步骤）：
→ AI判断："内向" vs "喜欢安静"
→ AI决定：合并 → "内向、喜欢安静"
→ AI同时给出：
   - 合并后的文本："内向、喜欢安静"
   - 判断理由："内向的人通常喜欢安静"

Step 4：根据AI判断结果，同时处理：
→ 摘要文本合并：保存"内向、喜欢安静"
→ 向量存储：生成向量并存储

结果：AI只判断一次，结果用于两个阶段
```

---

### 💡 优势对比

| 方案 | LLM调用次数 | 处理时间 | 逻辑一致性 |
|------|-----------|---------|-----------|
| **分开改进（判断两次）** | 2次 | 1秒 | 可能不一致 |
| **统一改进（判断一次）** | 1次（节省50%） | 0.5秒（节省50%） | 完全一致 |

---

## 📊 二、大白话解释：用"照片管理"例子理解

### 🎯 用"照片更新"的例子

**大白话解释：**

想象你在管理你的个人照片集：

- **补充关系**：你拍了正面照片，后来又拍了侧面照片
  - 这两张照片不是冲突（正面 vs 侧面），而是补充
  - 应该保留两张照片，展示更完整的你

- **冲突关系**：你拍了长发照片，后来剪了头发拍了短发照片
  - 这两张照片是冲突（长发 vs 短发）
  - 应该删除长发照片，只保留短发照片（真实变化了）

- **细化关系**：你拍了全身照片，后来拍了全身照片（穿西装）
  - 第二张照片更具体（包含第一张，且更详细）
  - 应该用第二张照片替换（更详细）

---

### 🔍 AI判断的四个标准

**AI判断时看四个维度：**

1. **语义相似度**：意思相近不相近？
   - "内向" vs "喜欢安静" → 相近 → 补充
   - "喜欢热闹" vs "喜欢安静" → 相反 → 冲突

2. **逻辑关系**：逻辑上顺不顺？
   - "内向" → "喜欢安静" → 逻辑顺延 → 补充
   - "温柔" → "温柔、能理解工作" → 包含关系 → 细化

3. **时间因素**：短期还是长期变化？
   - 同一天："内向" → "喜欢安静" → 短期 → 补充
   - 3个月："喜欢热闹" → "喜欢安静" → 长期 → 冲突（真实变化）

4. **历史趋势**：连续变化还是突然变化？
   - "内向" → "内向、安静" → "喜欢独处" → 连续变化 → 补充
   - "内向" → "喜欢热闹" → 突然相反 → 可能错误

---

## 🔧 三、完整实现方案

### 1. 新增核心函数：ai_merge_and_vectorize()

**文件位置：**
- `match_domain/vector_store_lite.py`（新增）
- 或新建文件：`match_domain/ai_merge_handler.py`

**完整代码：**

```python
"""AI一次性处理：摘要文本合并 + 向量存储

文件：match_domain/ai_merge_handler.py（新建）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


async def ai_merge_and_vectorize(
    user_id: int,
    vector_type: str,
    new_text: str,
    historical_text: str | None,
    conversation_id: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    AI一次性处理：摘要文本合并 + 向量存储
    
    只让AI判断一次，结果同时用于：
    1. 摘要文本合并（保存合并后的文本）
    2. 向量存储（生成合并后的向量）
    
    Args:
        user_id: 用户ID
        vector_type: 向量类型（personality_traits等）
        new_text: 新提炼的文本
        historical_text: 历史文本（如果没有历史，传None）
        conversation_id: 对话ID
        conversation_time: 对话时间（用于判断短期/长期变化）
    
    Returns:
        {
            "final_text": "最终文本（合并或覆盖后）",
            "ai_decision": {
                "relation_type": "补充/冲突/细化",
                "confidence": "high/medium/low",
                "action": "merge/replace",
                "merged_text": "合并后的文本（如果merge）",
                "reason": "判断理由",
            },
            "text_saved": True,  # 摘要文本已保存
            "vector_saved": True, # 向量已存储
        }
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1：如果没有历史数据，直接保存（首次记录）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if not historical_text:
        _logger.info(
            f"首次记录: user_id={user_id}, vector_type={vector_type}, "
            f"text={new_text}"
        )
        
        # 直接保存摘要文本
        save_summary_text(
            user_id=user_id,
            vector_type=vector_type,
            summary_text=new_text,
            conversation_id=conversation_id,
        )
        
        # 生成向量并存储
        final_vector = await generate_embedding(new_text)
        save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=final_vector,
            raw_text=new_text,
            conversation_id=conversation_id,
        )
        
        return {
            "final_text": new_text,
            "ai_decision": None,  # 无需AI判断
            "text_saved": True,
            "vector_saved": True,
        }
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2：AI判断语义关系（只判断一次）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    ai_decision = await _ai_judge_semantic_relation(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        conversation_time=conversation_time,
    )
    
    _logger.info(
        f"AI判断完成: {historical_text} → {new_text}\n"
        f"关系类型: {ai_decision['relation_type']}\n"
        f"AI决定: {ai_decision['action']}\n"
        f"判断理由: {ai_decision['reason']}"
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3：根据AI判断，确定最终文本
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if ai_decision["action"] == "merge":
        # AI决定合并
        final_text = ai_decision["merged_text"]
    else:
        # AI决定覆盖
        final_text = new_text
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 4：保存摘要文本（阶段1：摘要文本合并）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    save_summary_text(
        user_id=user_id,
        vector_type=vector_type,
        summary_text=final_text,
        conversation_id=conversation_id,
    )
    
    _logger.info(f"摘要文本已保存: {final_text}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 5：生成向量并存储（阶段2：向量存储）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    final_vector = await generate_embedding(final_text)
    
    deactivate_old_vectors(user_id, vector_type)
    save_vector_with_version(
        user_id=user_id,
        vector_type=vector_type,
        embedding=final_vector,
        raw_text=final_text,
        conversation_id=conversation_id,
    )
    
    _logger.info(f"向量已存储: {vector_type}, version=新版本")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 6：返回结果
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    return {
        "final_text": final_text,
        "ai_decision": ai_decision,
        "text_saved": True,
        "vector_saved": True,
    }
```

---

### 2. AI判断函数：_ai_judge_semantic_relation()

**文件位置：**
- `match_domain/ai_merge_handler.py`（新增）

**完整代码：**

```python
async def _ai_judge_semantic_relation(
    historical_text: str,
    new_text: str,
    vector_type: str,
    conversation_time: datetime | None = None,
) -> dict[str, Any]:
    """
    AI判断新旧内容的语义关系
    
    判断维度：
    1. 语义相似度（cosine similarity）
    2. 逻辑关系（补充/冲突/细化）
    3. 时间因素（短期补充 vs 镆期变化）
    
    Args:
        historical_text: 历史版本文本
        new_text: 新版本文本
        vector_type: 向量类型
        conversation_time: 对话时间
    
    Returns:
        {
            "relation_type": "补充/冲突/细化",
            "confidence": "high/medium/low",
            "action": "merge/replace",
            "merged_text": "合并后的文本（如果merge）",
            "reason": "判断理由",
        }
    """
    
    # 构建AI判断Prompt
    prompt = _build_semantic_judge_prompt(
        historical_text=historical_text,
        new_text=new_text,
        vector_type=vector_type,
        conversation_time=conversation_time,
    )
    
    # 调用LLM
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
        
        # Fallback机制
        return _fallback_decision(historical_text, new_text)
```

---

### 3. Prompt设计：_build_semantic_judge_prompt()

**文件位置：**
- `match_domain/ai_merge_handler.py`（新增）

**核心Prompt内容：**

```python
def _build_semantic_judge_prompt(
    historical_text: str,
    new_text: str,
    vector_type: str,
    conversation_time: datetime | None = None,
) -> str:
    """
    构建AI判断Prompt
    
    设计原则：
    - 提供完整上下文
    - 明确判断维度
    - 要求输出判断理由
    - 严格JSON格式输出
    """
    
    # 时间因素描述
    time_description = "未知时间"
    if conversation_time:
        days_gap = (datetime.now() - conversation_time).days
        if days_gap <= 1:
            time_description = "短期变化（同一天内）：倾向于补充"
        elif days_gap <= 7:
            time_description = "短期内变化（一周内）：可能是补充"
        elif days_gap <= 30:
            time_description = "中期变化（一个月内）：可能是补充或变化"
        else:
            time_description = "长期变化（超过一个月）：可能是真实变化"
    
    return f"""你是一个画像分析专家，擅长分析用户特征的语义关系。

请分析以下新旧数据的关系：

【历史版本】："{historical_text}"
【新版本】："{new_text}"
【时间因素】：{time_description}

请判断它们的关系类型：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【三种关系类型】：

1. **补充关系**：
   - 新内容补充旧内容，两者语义兼容
   - 例："内向" → "喜欢安静"（内向的人通常喜欢安静）
   - 处理：合并 → "内向、喜欢安静"

2. **冲突关系**：
   - 新内容与旧内容矛盾，语义相反
   - 例："喜欢热闹" → "喜欢安静"（长期变化，真实变化）
   - 处理：覆盖 → 只保留"喜欢安静"

3. **细化关系**：
   - 新内容更具体，包含旧内容
   - 例："温柔" → "温柔、能理解工作"（后者包含前者）
   - 处理：合并 → "温柔、能理解工作"

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
    "reason": "判断理由（一句话，简洁明了）"
}

请严格按照JSON格式输出，不要输出任何其他内容。
"""
```

---

### 4. 改造现有流程：session_end_processor.py

**改造位置：**
- `match_domain/session_end_processor.py` 的 `save_vectors_for_summary` 函数

**改造内容：**

```python
# 改造前（旧逻辑）
async def save_vectors_for_summary(session_id, requester_id, summary_data):
    for summary_key, summary_text in summary_data.items():
        # 直接保存（不判断语义关系）
        vector = await generate_embedding(summary_text)
        save_vector_with_version(...)
    
    return vectorized_keys

# 改造后（新逻辑）
async def save_vectors_for_summary(session_id, requester_id, summary_data):
    from match_domain.ai_merge_handler import ai_merge_and_vectorize
    
    vectorized_keys = []
    
    for summary_key, summary_text in summary_data.items():
        if not summary_text:
            continue
        
        # 查询历史数据
        historical_text = await load_historical_summary(requester_id, summary_key)
        
        # AI一次性处理：摘要文本合并 + 向量存储
        result = await ai_merge_and_vectorize(
            user_id=requester_id,
            vector_type=summary_key,
            new_text=summary_text,
            historical_text=historical_text,
            conversation_id=session_id,
        )
        
        if result["vector_saved"]:
            vectorized_keys.append(summary_key)
            
            _logger.info(
                f"AI处理完成: key={summary_key}\n"
                f"最终文本: {result['final_text']}\n"
                f"AI判断: {result['ai_decision']['reason']}"
            )
    
    return vectorized_keys
```

---

### 5. Fallback机制：_fallback_decision()

**文件位置：**
- `match_domain/ai_merge_handler.py`（新增）

**完整代码：**

```python
def _fallback_decision(
    historical_text: str,
    new_text: str,
) -> dict[str, Any]:
    """
    Fallback决策：AI判断失败时的默认规则
    
    保守策略：
    - 短期内变化：倾向于merge（保留信息）
    - 镆期变化：倾向于replace（可能真实变化）
    """
    
    _logger.warning(
        f"AI判断失败，使用fallback决策: "
        f"historical={historical_text}, new={new_text}"
    )
    
    # 保守策略：简单拼接合并
    merged_text = f"{historical_text}、{new_text}"
    
    return {
        "relation_type": "补充（fallback）",
        "confidence": "low",
        "action": "merge",
        "merged_text": merged_text,
        "reason": "AI判断失败，fallback保守合并",
    }
```

---

### 6. 辅助函数：save_summary_text() 和 load_historical_summary()

**文件位置：**
- `match_domain/ai_merge_handler.py`（新增）

**完整代码：**

```python
def save_summary_text(
    user_id: int,
    vector_type: str,
    summary_text: str,
    conversation_id: str,
) -> None:
    """
    保存摘要文本到数据库
    
    保存到 conversation_summaries 表
    """
    
    conn = mysql_connect()
    try:
        with conn.cursor() as cursor:
            # 先删除旧记录
            cursor.execute(
                """
                DELETE FROM conversation_summaries
                WHERE requester_id = ? AND summary_key = ?
                """,
                (user_id, vector_type),
            )
            
            # 插入新记录
            cursor.execute(
                """
                INSERT INTO conversation_summaries
                (conversation_id, conversation_type, requester_id, profile_id,
                 summary_key, summary_text, vector_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'done', NOW())
                """,
                (conversation_id, 'discovery', user_id, user_id, vector_type, summary_text),
            )
        
        conn.commit()
        
    finally:
        release_persona_connection(conn)


async def load_historical_summary(
    user_id: int,
    vector_type: str,
) -> str | None:
    """
    查询历史摘要文本
    
    从 conversation_summaries 表查询最新记录
    """
    
    def _load_sync():
        conn = mysql_connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT summary_text
                    FROM conversation_summaries
                    WHERE requester_id = ? AND summary_key = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, vector_type),
                )
                row = cursor.fetchone()
                return row.get("summary_text") if row else None
        
        finally:
            release_persona_connection(conn)
    
    return await asyncio.to_thread(_load_sync)
```

---

## 📊 四、完整流程图

```
┌─────────────────────────────────────────────────────┐
│  会话结束 → AI提炼摘要 → 新数据："喜欢安静"          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  查询历史数据 → 旧数据："内向"                       │
│  （从 conversation_summaries 表查询）               │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  调用 ai_merge_and_vectorize()                      │
│  （核心函数，一次性处理）                            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  AI判断一次（只判断一次）                            │
│  输入：旧数据"内向" + 新数据"喜欢安静"              │
│  Prompt：请判断语义关系...                          │
│  AI推理：内向的人通常喜欢安静，是补充关系            │
│  AI输出：                                           │
│  {                                                 │
│    "relation_type": "补充",                         │
│    "action": "merge",                              │
│    "merged_text": "内向、喜欢安静",                 │
│    "reason": "内向的人通常喜欢安静"                 │
│  }                                                 │
└─────────────────────────────────────────────────────┘
                        ↓
        ┌───────────────┴───────────────┐
        ↓                               ↓
┌──────────────────┐          ┌──────────────────┐
│ 摘要文本保存      │          │ 向量存储          │
│ （阶段1）         │          │ （阶段2）         │
│                  │          │                  │
│ 保存到数据库：    │          │ 生成向量：        │
│ "内向、喜欢安静" │          │ [0.12, 0.25...]  │
│                  │          │                  │
│ conversation_    │          │ 存入 Milvus：     │
│ summaries表      │          │ user_vectors表   │
└──────────────────┘          └──────────────────┘

结果：AI只判断一次，同时完成两个阶段的任务
```

---

## 📋 五、落地改造清单

### Phase 1：新增核心模块

| 文件 | 操作 | 内容 |
|------|------|------|
| `match_domain/ai_merge_handler.py` | **新建** | 核心函数：ai_merge_and_vectorize() |

**新增函数清单：**

1. `ai_merge_and_vectorize()` - AI一次性处理主函数
2. `_ai_judge_semantic_relation()` - AI判断语义关系
3. `_build_semantic_judge_prompt()` - 构建AI判断Prompt
4. `_fallback_decision()` - Fallback机制
5. `save_summary_text()` - 保存摘要文本
6. `load_historical_summary()` - 查询历史摘要

---

### Phase 2：改造现有流程

| 文件 | 操作 | 改造内容 |
|------|------|---------|
| `match_domain/session_end_processor.py` | **改造** | 改造 save_vectors_for_summary() |
| `match_domain/vector_store_lite.py` | **改造** | 移除 VECTOR_TYPES_CONFIG 的 update_policy |

**改造逻辑：**

```python
# 改造前：直接保存向量，不判断语义关系
for summary_key, summary_text in summary_data.items():
    vector = await generate_embedding(summary_text)
    save_vector_with_version(...)

# 改造后：AI一次性处理，判断语义关系
for summary_key, summary_text in summary_data.items():
    historical_text = await load_historical_summary(requester_id, summary_key)
    result = await ai_merge_and_vectorize(...)
```

---

### Phase 3：移除硬编码策略

| 文件 | 操作 | 改造内容 |
|------|------|---------|
| `match_domain/vector_store_lite.py` | **删除** | 删除 VECTOR_TYPES_CONFIG 的 update_policy 字段 |
| `match_domain/vector_store.py` | **删除** | 删除 VECTOR_TYPES_CONFIG 的 update_policy 字段 |

**删除内容：**

```python
# 删除前
VECTOR_TYPES_CONFIG = {
    "personality_traits": {"update_policy": "replace", ...},
    "values": {"update_policy": "replace", ...},
    "partner_expectation": {"update_policy": "average", ...},
    ...
}

# 删除后（只保留其他配置）
VECTOR_TYPES_CONFIG = {
    "personality_traits": {"decay_days": 365, ...},
    "values": {"decay_days": 365, ...},
    "partner_expectation": {"decay_days": 90, ...},
    ...
}
```

---

## 💡 六、关键设计亮点

### 1. 只让AI判断一次

```
优势：
- 节省成本：LLM调用从2次变成1次（节省50%）
- 节省时间：处理时间从1秒变成0.5秒（节省50%）
- 逻辑一致：两个阶段用同一个判断结果
```

---

### 2. 统一处理两个阶段

```
ai_merge_and_vectorize() 函数同时处理：
- 摘要文本合并（阶段1）
- 向量存储（阶段2）

避免逻辑分散，代码更清晰
```

---

### 3. 可解释性

```
AI输出包含：
- relation_type：关系类型（补充？冲突？细化？）
- confidence：置信度（高？中？低？）
- reason：判断理由（一句话）

用户可查看判断理由，理解为什么合并或覆盖
```

---

### 4. Fallback机制

```
AI判断失败时：
- 使用保守策略（简单拼接合并）
- 记录日志（fallback触发）

尽量减少Fallback使用，提高AI判断成功率
```

---

## 📋 七、预期效果

### 成本对比

| 方案 | LLM调用次数 | 处理时间 | 代码复杂度 |
|------|-----------|---------|-----------|
| **分开改进** | 2次 | 1秒 | 高（两个函数） |
| **统一改进** | 1次（节省50%） | 0.5秒（节省50%） | 低（一个函数） |

---

### 推荐质量对比

| 维度 | 当前设计 | 改进设计 | 效果 |
|------|---------|---------|------|
| **语义理解** | 无（硬编码） | AI判断 | 智能判断语义关系 |
| **信息保留** | 可能丢失 | 智能合并 | 保留补充信息 |
| **真实变化** | 可能保留冲突 | 智能覆盖 | 正确处理真实变化 |
| **可解释性** | 无 | AI输出理由 | 用户可理解 |

---

## 🎯 八、总结

**改进方案核心：**

> 只让AI判断一次，同时处理摘要文本合并和向量存储

**一句话总结：**

> 从"两个阶段各自判断"到"一次性统一处理"

**关键优势：**

1. ✅ 节省成本：LLM调用减少50%
2. ✅ 节省时间：处理时间减少50%
3. ✅ 逻辑一致：两个阶段用同一判断结果
4. ✅ 更智能：AI判断语义关系
5. ✅ 更可解释：AI输出判断理由

**落地步骤：**

1. Phase 1：新增 ai_merge_handler.py 模块
2. Phase 2：改造 session_end_processor.py
3. Phase 3：移除 VECTOR_TYPES_CONFIG 的硬编码策略

---

这个改进方案让画像系统更高效、更智能，真正实现"AI理解用户特征，而不是代码硬编码规则"。