# 用户画像写入逻辑完整方案（修正版 V2）

## 核心修正说明

> **V2 版本关键修正**：
> 1. **可量化字段**（INTJ、不抽烟、北京）→ 会结束后写入画像表（user_personas + user_persona_observations）
> 2. **不可量化字段**（性格温柔、重视家庭）→ 会结束后写入摘要表（conversation_summaries）+ 向量库（Milvus）
> 3. **profiles 表** → ❌ 不支持会话后写入，只允许用户在设置页手动编辑
> 4. **实时对话阶段** → 只记聊天内容，不写任何画像数据
> 5. **会话结束阶段** → LLM统一提炼，分流写入（可量化写画像，不可量化写摘要+向量）
> 6. **观察记录需求** → 只有 user_personas 和 profiles 需要观察记录，conversation_summaries 和 Milvus 不需要

---

## 一、核心设计理念（修正版 V2）

### 红娘匹配类比（修正版）

> **就像真实红娘帮人匹配对象：**
> 1. 先让用户填基本信息（姓名、年龄、学历）→ 硬筛选（profile_part）
> 2. 对话时只记聊天内容（不写画像）→ 记在小本本（agent_session_store）
> 3. **会话结束后提炼：**
>    - 可量化字段（INTJ、不抽烟）→ 写入标签卡（persona_part）
>    - 不可量化字段（性格温柔）→ 写入感觉本（vector_part）+ 日记摘要（session_summary）
> 4. 保留完整聊天记录（微信记录）→ 兜底查询（agent_session）

**关键修正（V2）**：
- ❌ 移除实时对话的画像写入（不分流 persona_part）
- ✅ 会结束后统一提炼（LLM 负责分流）
- ✅ 可量化字段写画像表（user_personas + user_persona_observations）
- ❌ **profiles 表不支持会话后写入**（只允许用户手动编辑）
- ✅ 不可量化字段只写摘要和向量（conversation_summaries、Milvus）

---

## 二、五层存储架构（修正版 V2）

```
┌─────────────────────────────────────────────────────────────┐
│  第1层：agent_session（聊天记录）                            │
│  存储位置：agent_session_store                               │
│  特点：实时记录所有对话                                       │
│  写入时机：对话过程中                                         │
│  用途：原始证据，LLM提炼的输入                                │
│  例子：所有 messages（用户说的每一句话）                      │
│                                                             │
│  关键设计：                                                  │
│  - 对话时只记聊天，不写任何画像数据                           │
│  - 这是LLM提炼的唯一输入                                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第2层：conversation_summaries（对话摘要 - 不可量化字段）    │
│  存储位置：MySQL conversation_summaries 表                   │
│  特点：LLM提炼，按字段存储                                    │
│  写入时机：会话结束后                                         │
│  用途：给人看的摘要，辅助决策                                  │
│  例子：personality_traits="性格温柔、内向"                   │
│                                                             │
│  关键修正（V2）：                                            │
│  - 只存储不可量化字段（主观描述）                             │
│  - 不存储可量化字段（INTJ、不抽烟等）                         │
│  - 可量化字段写画像表，不写摘要表                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第3层：Milvus向量库（向量化数据 - 不可量化字段）            │
│  存储位置：Milvus                                             │
│  特点：向量化，带版本管理                                      │
│  写入时机：会话结束后                                         │
│  用途：语义相似度搜索                                         │
│  例子：personality_traits → [0.85, 0.72, 0.91,...]          │
│                                                             │
│  关键修正（V2）：                                            │
│  - 只向量化不可量化字段（主观描述）                           │
│  - 不向量化可量化字段（INTJ、不抽烟等）                       │
│  - 可量化字段用SQL精确匹配，不需要向量                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第4层：user_persona_observations（观察记录 - 可量化字段）   │
│  存储位置：MySQL user_persona_observations 表                │
│  特点：支持溯源审计，置信度分级                                │
│  写入时机：会话结束后                                         │
│  用途：记录每次画像推断，可追溯                                │
│  例子：field_name="mbti_type", confidence_score=85           │
│                                                             │
│  关键修正（V2）：                                            │
│  - 只记录可量化字段的推断历史                                 │
│  - 不记录不可量化字段（主观描述不写观察记录）                 │
│  - 每条记录带session_id，支持溯源                             │
│                                                             │
│  为什么需要保留？                                            │
│  1. 溯源审计：可追溯到具体会话                                │
│  2. 置信度管理：区分手动编辑（100分）和LLM推断（85分）        │
│  3. 增量合并历史：记录变更历史，支持回滚                      │
│  4. 数据质量监控：观察推断准确性                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第5层：user_personas（画像表 - 可量化字段）                 │
│  存储位置：MySQL user_personas 表                            │
│  特点：长期记忆，增量合并                                      │
│  写入时机：会话结束后                                         │
│  用途：用户的长期画像（可量化字段）                            │
│  例子：mbti_type="INTJ", smoking=false                       │
│                                                             │
│  关键修正（V2）：                                            │
│  - 只存储可量化字段（INTJ、不抽烟、北京等）                   │
│  - 不存储不可量化字段（性格温柔等主观描述）                   │
│  - 用于SQL精确筛选                                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第6层：profiles（匹配画像表 - 可量化字段）                   │
│  存储位置：MySQL profiles 表                                  │
│  特点：匹配画像，公开展示                                      │
│  写入时机：❌ 不支持会话后写入，只允许用户手动编辑             │
│  用途：候选人匹配                                              │
│  例子：matcher_traits_json={"mbti_type": "INTJ"}            │
│                                                             │
│  关键修正（V2）：                                            │
│  - ❌ 不支持会话后自动写入（保护用户隐私和意愿）              │
│  - ✅ 只允许用户在设置页手动编辑                              │
│  - ✅ 保证数据都是用户确认过的（可信度最高）                  │
│  - ✅ 用于候选人搜索和匹配                                    │
│                                                             │
│  为什么不允许会话后写入？                                    │
│  1. 隐私保护：profiles是公开展示的，必须用户同意              │
│  2. 数据可信度：手动编辑的数据可信度最高                      │
│  3. 用户意愿：尊重用户对公开展示内容的控制权                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、数据流向设计（修正版 V2）

### 完整数据流向

```
【实时对话阶段】
用户说话："我是INTJ人格，性格温柔"
    ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent 接收并判断                                            │
│                                                             │
│  ❌ 不分流（不分 persona_part、profile_part）                │
│  ✅ 只记到 agent_session_store（聊天记录）                   │
│                                                             │
│  关键修正（V2）：                                            │
│  - 移除 sync_requester_persona_memory 实时写入              │
│  - 移除 split_persona_patch 实时分流                        │
│  - 所有画像数据都在会结束后统一处理                           │
└─────────────────────────────────────────────────────────────┘
    ↓
存储聊天记录：agent_session_store
    ↓
继续对话...

【会话结束阶段】
会话结束时
    ↓
┌─────────────────────────────────────────────────────────────┐
│  LLM 提炼：从聊天记录生成结构化摘要                          │
│                                                             │
│  输入：聊天记录（所有 messages）                             │
│  输出：结构化摘要                                            │
│    {                                                        │
│      // 可量化字段                                          │
│      mbti_type: "INTJ",                                     │
│      smoking: false,                                        │
│      city: "北京",                                          │
│                                                             │
│      // 不可量化字段                                         │
│      personality_traits: "性格温柔",                        │
│      values: "重视家庭",                                    │
│      partner_expectation: "能理解工作忙碌",                  │
│    }                                                        │
│                                                             │
│  关键设计（V2）：                                            │
│  - LLM 同时提炼可量化字段和不可量化字段                       │
│  - 不需要实时分流，LLM负责识别所有字段                        │
│  - LLM输出包含字段分类信息                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  分流写入（V2修正版）                                        │
│                                                             │
│  可量化字段处理：                                            │
│  ├─ user_persona_observations（观察记录）                   │
│  └─ user_personas（画像表）                                 │
│  ❌ profiles（不支持会话后写入）                             │
│                                                             │
│  不可量化字段处理：                                          │
│  ├─ conversation_summaries（摘要表）                        │
│  └─ Milvus（向量库）                                        │
│                                                             │
│  关键分流逻辑：                                              │
│  - mbti_type ∈ QUANTIFIABLE_FIELDS → 写画像表（不写profiles）│
│  - personality_traits ∉ QUANTIFIABLE_FIELDS → 写摘要+向量   │
│  - profiles 只允许用户手动编辑，不自动同步                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、可量化判断标准（V2修正版）

### 可量化字段白名单

```python
# 工具层兜底：硬编码的可量化字段列表
QUANTIFIABLE_FIELDS = frozenset({
    # 数值范围
    "age", "age_min", "age_max",
    "height", "height_min", "height_max",
    "income", "income_min", "income_max",

    # 枚举类型
    "mbti_type", "personality_type",
    "marital_status", "relationship_goal",
    "gender", "sexual_orientation",

    # 布尔值
    "has_children", "smoking", "drinking",
    "accept_partner_children", "accept_long_distance",

    # 地理位置
    "cities", "districts", "city", "district",

    # 学历等级
    "education", "education_min",

    # 标签（明确的标签体系）
    "must_have_tags", "must_not_have_tags",
})
```

### 可量化判断规则

| 字段类型 | 是否可量化 | 判断标准 | 例子 | 写入位置 |
|---------|-----------|---------|------|---------|
| **数值范围** | ✅ 可量化 | 明确的数字范围 | 年龄26-30、身高170-180 | 画像表（user_personas） |
| **枚举类型** | ✅ 可量化 | 明确的有限选项 | MBTI（16种）、婚姻状态 | 画像表（user_personas） |
| **布尔值** | ✅ 可量化 | 明确的是/否 | 是否抽烟、是否有孩子 | 画像表（user_personas） |
| **地理位置** | ✅ 可量化 | 明确的城市/区县 | 北京、上海 | 画像表（user_personas） |
| **学历等级** | ✅ 可量化 | 明确的学历层次 | 硕士、本科 | 画像表（user_personas） |
| **主观描述** | ❌ 不可量化 | 每个人理解不同 | 性格温柔、重视家庭 | 摘要表+向量库 |
| **程度描述** | ❌ 不可量化 | 量化标准不明确 | 最近压力大、偶尔喝酒 | 摘要表+向量库 |
| **情感状态** | ❌ 不可量化 | 主观感受 | 父母催婚压力、工作焦虑 | 摘要表+向量库 |

---

## 五、会话结束处理流程（V2修正版）

### 流程图

```
┌─────────────────────────────────────────────────────────────┐
│  会话结束处理流程（V2修正版）                                │
│                                                             │
│  Step 1：加载聊天记录                                        │
│      ↓                                                      │
│  Step 2：LLM 提炼结构化摘要                                  │
│      ↓                                                      │
│  Step 3：分流判断                                            │
│  ├─ 可量化字段 → 写入画像表                                  │
│  └─ 不可量化字段 → 写入摘要表+向量库                         │
│      ↓                                                      │
│  Step 4：清空 working_criteria                              │
│                                                             │
│  关键修正（V2）：                                            │
│  - 可量化字段写 user_persona_observations + user_personas + profiles │
│  - 不可量化字段写 conversation_summaries + Milvus           │
│  - 不再写重复数据（避免架构冗余）                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、代码改动方案（V2修正版）

### 改动1：移除实时写入逻辑

**文件**：`external-systems/partner-discovery-system/discovery_system/service_integrations.py`

**改动内容**：
```python
# 完全移除 sync_requester_persona_memory 函数的实时调用
# 或者保持硬禁用状态（当前状态）

def sync_requester_persona_memory(...):
    """硬禁用：不执行任何写入逻辑
    
    禁用原因（V2修正）：
    - 所有画像数据在会结束后统一写入
    - 可量化字段写画像表
    - 不可量化字段写摘要+向量库
    """
    _logger.info("【硬禁用】sync_requester_persona_memory 已禁用，不执行任何写入逻辑")
    return {
        "synced": False,
        "error_code": "disabled_for_testing",
        "message": "所有画像数据在会结束后统一写入",
    }
```

---

### 改动2：新增会结束后的分流写入逻辑

**文件**：`match_domain/session_end_processor.py`

**改动内容**：
```python
async def process_session_end(
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str = "discovery",
    *,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """会话结束时的处理流程（V2修正版：分流写入）"""
    
    try:
        # Step 1：从数据库加载聊天记录
        messages = await load_session_messages_from_db(session_id, dsn=dsn)
        if not messages:
            return {"success": False, "error": "no_messages"}
        
        # Step 2：LLM提炼结构化摘要
        summary_data = await generate_structured_summary(
            messages,
            requester_id=requester_id,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )
        
        if not summary_data:
            return {"success": False, "error": "llm_failed"}
        
        # Step 3：分流写入（V2修正版）
        
        # 分流：分离可量化字段和不可量化字段
        quantifiable_data, non_quantifiable_data = split_by_quantifiability(summary_data)
        
        # 处理可量化字段：写入画像表
        if quantifiable_data:
            persona_result = await save_quantifiable_to_persona_tables(
                user_key=str(requester_id),
                profile_id=profile_id,
                session_id=session_id,
                quantifiable_data=quantifiable_data,
                dsn=dsn,
            )
        else:
            persona_result = {"success": True, "message": "no_quantifiable_fields"}
        
        # 处理不可量化字段：写入摘要表+向量库
        if non_quantifiable_data:
            # 写入摘要表
            saved_keys = await save_session_summary_text(
                session_id=session_id,
                requester_id=requester_id,
                profile_id=profile_id,
                conversation_type=conversation_type,
                summary_data=non_quantifiable_data,  # 只写不可量化字段
                dsn=dsn,
            )
            
            # 写入向量库
            vectorized_keys = await save_vectors_for_summary(
                session_id=session_id,
                requester_id=requester_id,
                summary_data=non_quantifiable_data,  # 只向量化不可量化字段
            )
        else:
            saved_keys = []
            vectorized_keys = []
        
        # Step 4：清空 working_criteria
        await clear_working_criteria(session_id, dsn=dsn)
        
        return {
            "success": True,
            "quantifiable_data": quantifiable_data,
            "non_quantifiable_data": non_quantifiable_data,
            "persona_result": persona_result,
            "saved_keys": saved_keys,
            "vectorized_keys": vectorized_keys,
            "message_count": len(messages),
        }
        
    except Exception as exc:
        _logger.error(f"会话结束处理失败: session_id={session_id}, error={exc}")
        return {"success": False, "error": "exception", "message": str(exc)[:200]}
```

---

### 改动3：新增分流函数

**文件**：`match_domain/session_end_processor.py`

**改动内容**：
```python
def split_by_quantifiability(summary_data: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """分流：分离可量化字段和不可量化字段
    
    Args:
        summary_data: LLM提炼的结构化摘要
    
    Returns:
        (quantifiable_data, non_quantifiable_data)
        - quantifiable_data: 可量化字段（写画像表）
        - non_quantifiable_data: 不可量化字段（写摘要+向量库）
    
    例子：
        输入：{
            mbti_type: "INTJ",
            smoking: false,
            personality_traits: "性格温柔"
        }
        
        输出：
        quantifiable_data = {
            mbti_type: "INTJ",
            smoking: false
        }
        
        non_quantifiable_data = {
            personality_traits: "性格温柔"
        }
    """
    from profile_write_guard import QUANTIFIABLE_FIELDS
    
    quantifiable_data: dict[str, str] = {}
    non_quantifiable_data: dict[str, str] = {}
    
    for key, value in summary_data.items():
        if not str(value or "").strip():
            continue
        
        # 判断是否可量化
        if key in QUANTIFIABLE_FIELDS:
            quantifiable_data[key] = value
        else:
            non_quantifiable_data[key] = value
    
    _logger.info(
        f"分流完成: quantifiable_fields={list(quantifiable_data.keys())}, "
        f"non_quantifiable_fields={list(non_quantifiable_data.keys())}"
    )
    
    return quantifiable_data, non_quantifiable_data
```

---

### 改动4：新增可量化字段写入函数

**文件**：`match_domain/session_end_processor.py`

**改动内容**：
```python
async def save_quantifiable_to_persona_tables(
    user_key: str,
    profile_id: int,
    session_id: str,
    quantifiable_data: dict[str, str],
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    """将可量化字段写入画像表
    
    写入位置：
    - user_persona_observations（观察记录）
    - user_personas（画像表）
    ❌ profiles（不支持会话后写入）
    
    关键设计（V2）：
    - 只写入可量化字段
    - 不写入不可量化字段（主观描述不进画像表）
    - ❌ 不写入 profiles 表（只允许用户手动编辑）
    - 每条记录带session_id（支持溯源）
    
    Args:
        user_key: 用户标识
        profile_id: 画像ID
        session_id: 会话ID（用于溯源）
        quantifiable_data: 可量化字段数据
        dsn: 数据库连接字符串
    
    Returns:
        画像写入结果
    """
    from persona_memory_sync.persona_memory_lib import apply_persona_patch
    
    resolved_dsn = dsn or os.environ.get("HER_PERSONA_DB") or os.environ.get("PARTNER_DISCOVERY_DB") or ""
    
    if not resolved_dsn:
        _logger.warning("没有配置数据库连接，无法写入画像")
        return {"success": False, "error": "dsn_not_configured"}
    
    try:
        # 构造 evidence_text（记录溯源）
        evidence_text = f"会话结束后LLM提炼（session_id={session_id})"
        
        # 调用 apply_persona_patch 统一写入
        result = apply_persona_patch(
            source=resolved_dsn,
            user_key=user_key,
            source_type="strong_inference",  # 会结束后的推断
            source_channel="discovery_session_end",  # 来源标识
            normalized_patch=quantifiable_data,  # 只写可量化字段
            confidence_score=85,  # 会结束后LLM提炼的置信度
            evidence_text=evidence_text,
            conversation_ref=session_id,  # 溯源ID
            apply_scope="persona_only",  # ❌ 只写画像表，不写profiles
            sync_profile=False,  # ❌ 不同步到 profiles 表
        )
        
        _logger.info(
            f"可量化字段写入成功: user_key={user_key}, "
            f"applied_fields={result.get('applied_fields', [])}"
        )
        
        return {
            "success": True,
            "user_key": user_key,
            "applied_fields": result.get("applied_fields", []),
            "skipped_fields": result.get("skipped_fields", []),
            "synced_profile": False,  # ❌ 不同步到 profiles
        }
        
    except Exception as exc:
        _logger.error(f"可量化字段写入失败: user_key={user_key}, error={exc}")
        return {"success": False, "error": str(exc)[:200]}
```
        }
        
    except Exception as exc:
        _logger.error(f"可量化字段写入失败: user_key={user_key}, error={exc}")
        return {"success": False, "error": str(exc)[:200]}
```

---

### 改动5：改进LLM提炼Prompt

**文件**：`match_domain/session_end_processor.py`

**改动内容**：
```python
def _build_summary_prompt(formatted_messages: str) -> str:
    """构造LLM提炼摘要的Prompt（V2修正版：同时提炼可量化+不可量化字段）
    
    关键修正（V2）：
    - LLM同时提炼可量化字段（INTJ）和不可量化字段（性格温柔）
    - LLM输出包含所有字段，不分流
    - 会结束后由代码分流写入不同层
    """
    return f"""请根据以下对话内容，提炼用户的所有结构化特征。

对话内容：
{formatted_messages}

要求：
1. 提炼性格特质（personality_traits）：如"性格温柔、内向"
2. 提炼价值观（values）：如"重视家庭、重视事业"
3. 提炼择偶期望（partner_expectation）：如"希望找个能理解工作忙碌的人"
4. 提炼生活态度（life_attitude）：如"追求稳定、重视生活质量"
5. 提炼情感需求（emotional_needs）：如"需要理解和支持"
6. 提炼可量化字段（如果用户明确表达）：
   - mbti_type：如"INTJ"、"INFJ"
   - smoking：如"不抽烟"、"抽烟"
   - drinking：如"不喝酒"、"偶尔喝酒"
   - marital_status：如"未婚"、"已婚"
   - has_children：如"没有孩子"、"有孩子"
   - city：如"北京"、"上海"
   - education：如"硕士"、"本科"

⚠️ 重要规则：
- 如果该维度用户没有提及，输出空字符串 ""
- 如果用户明确表达了，使用简洁、客观的语言
- 每个字段长度不超过 50 字
- 不要添加对话中没有的信息
- 可量化字段必须是用户明确表达的（不要猜测）

输出格式（JSON）：
{
    "personality_traits": "性格温柔、内向",
    "values": "重视家庭、重视事业",
    "partner_expectation": "希望找个能理解工作忙碌的人",
    "life_attitude": "追求稳定、重视生活质量",
    "emotional_needs": "需要理解和支持",
    "mbti_type": "INTJ",
    "smoking": "不抽烟",
    "drinking": "偶尔喝酒",
    "marital_status": "未婚",
    "city": "北京",
    "education": "硕士"
}

请严格按照JSON格式输出，不要输出任何其他内容。"""
```

---

## 七、数据存储示例（V2修正版）

### 示例场景

**用户对话**：
```
用户："我是INTJ人格"
用户："我性格温柔，重视家庭"
用户："我希望找个能理解工作忙碌的人"
```

**会话结束后LLM提炼**：
```json
{
    "mbti_type": "INTJ",               // 可量化字段
    "smoking": "",                     // 用户未提及
    "personality_traits": "性格温柔",  // 不可量化字段
    "values": "重视家庭",              // 不可量化字段
    "partner_expectation": "能理解工作忙碌"  // 不可量化字段
}
```

**分流写入（V2修正版）**：

### 可量化字段写入（画像表）

**user_persona_observations 表**：
```sql
INSERT INTO user_persona_observations (
    user_key, persona_id, field_name, field_value, 
    source_type, confidence_score, evidence_text, conversation_ref,
    applied_to_persona, applied_to_profile
) VALUES (
    'user_123', 456, 'mbti_type', 'INTJ',
    'strong_inference', 85, 
    '会话结束后LLM提炼（session_id=discovery-session-007）',
    'discovery-session-007',
    true, true
);
```

**user_personas 表**：
```sql
UPDATE user_personas 
SET mbti_type = 'INTJ',
    last_inferred_at = NOW()
WHERE user_key = 'user_123';
```

**❌ profiles 表（不支持会话后写入）**：
```
// profiles 表只允许用户在设置页手动编辑
// 不支持会话后的自动写入
// 保证数据都是用户确认过的（可信度最高）
```

---

### 不可量化字段写入（摘要表+向量库）

**conversation_summaries 表**：
```sql
INSERT INTO conversation_summaries (
    conversation_id, conversation_type, requester_id, profile_id,
    summary_key, summary_text, vector_status
) VALUES (
    'discovery-session-007', 'discovery', 123, 456,
    'personality_traits', '性格温柔', 'pending'
);

INSERT INTO conversation_summaries (
    conversation_id, conversation_type, requester_id, profile_id,
    summary_key, summary_text, vector_status
) VALUES (
    'discovery-session-007', 'discovery', 123, 456,
    'values', '重视家庭', 'pending'
);

INSERT INTO conversation_summaries (
    conversation_id, conversation_type, requester_id, profile_id,
    summary_key, summary_text, vector_status
) VALUES (
    'discovery-session-007', 'discovery', 123, 456,
    'partner_expectation', '能理解工作忙碌', 'pending'
);
```

**Milvus 向量库**：
```python
# 向量化 personality_traits
embedding_personality = generate_embedding("性格温柔")
save_vector(
    user_id=123,
    vector_type="personality_traits",
    embedding=embedding_personality,
    raw_text="性格温柔",
    session_id="discovery-session-007"
)

# 向量化 values
embedding_values = generate_embedding("重视家庭")
save_vector(
    user_id=123,
    vector_type="values",
    embedding=embedding_values,
    raw_text="重视家庭",
    session_id="discovery-session-007"
)

# 向量化 partner_expectation
embedding_expectation = generate_embedding("能理解工作忙碌")
save_vector(
    user_id=123,
    vector_type="partner_expectation",
    embedding=embedding_expectation,
    raw_text="能理解工作忙碌",
    session_id="discovery-session-007"
)
```

---

## 八、user_persona_observations 的作用（V2修正版）

### 为什么需要保留？

**核心作用**：
1. **溯源审计**：可追溯到具体会话
2. **置信度管理**：区分手动编辑（100分）和LLM推断（85分）
3. **增量合并历史**：记录变更历史，支持回滚
4. **数据质量监控**：观察推断准确性

---

### 溯源审计示例

**场景**：用户质疑画像数据来源

```
用户问："为什么说我是INTJ？我没说过！"

系统查询 user_persona_observations：
SELECT * FROM user_persona_observations 
WHERE user_key = 'user_123' AND field_name = 'mbti_type';

结果：
{
    user_key: "user_123",
    field_name: "mbti_type",
    field_value: "INTJ",
    source_type: "strong_inference",
    confidence_score: 85,
    evidence_text: "会话结束后LLM提炼（session_id=discovery-session-007）",
    conversation_ref: "discovery-session-007",
    created_at: "2026-06-12 18:57:19"
}

系统回复：
"这是您在2026-06-12的对话中推断得出的，置信度85分。
对话记录可以通过 session_id=discovery-session-007 查看。
如果您认为是错误的，可以手动修正。"
```

---

### 置信度管理示例

**场景**：不同来源的置信度不同

```
来源类型            置信度   写入方式
手动编辑            100分    直接写入，覆盖历史
会结束后LLM推断     85分     增量合并，保留历史
强推断              80分     增量合并，保留历史
弱推断              60分     不写入，只记观察
```

**大白话类比**：
- 手动编辑 = 用户自己填身份证（最可信）
- 会结束后推断 = 红娘根据对话推断（可信度85分）
- 强推断 = 红娘根据行为推断（可信度80分）
- 弱推断 = 红娘猜测（可信度60分，不写入）

---

### 增量合并历史示例

**场景**：用户画像随时间变化

```
第1次会话：用户说"我是INTJ"
→ user_persona_observations 记录：mbti_type=INTJ, confidence=85

第2次会话：用户说"其实我是INFJ"
→ user_persona_observations 记录：mbti_type=INFJ, confidence=85

第3次会话：用户手动编辑"我是INFP"
→ user_persona_observations 记录：mbti_type=INFP, confidence=100

最终 user_personas：
mbti_type = INFP（置信度最高的）

历史记录可追溯：
SELECT * FROM user_persona_observations 
WHERE user_key = 'user_123' AND field_name = 'mbti_type'
ORDER BY created_at;

结果：
1. INTJ (85分, session-001)
2. INFJ (85分, session-002)
3. INFP (100分, manual_edit)
```

---

## 九、各表的观察记录需求分析（V2新增）

### 核心问题：哪些表需要观察记录？

| 表名 | 是否需要观察记录 | 原因 | 观察记录表名 |
|------|----------------|------|-------------|
| **user_personas** | ✅ 需要 | 溯源审计、置信度管理、增量合并历史 | user_persona_observations |
| **profiles** | ✅ 需要 | 溯源审计（只记录用户手动编辑） | profile_observations（或 user_persona_observations） |
| **conversation_summaries** | ❌ 不需要 | 数据来源单一，conversation_id 本身是溯源标识 | 无 |
| **Milvus 向量库** | ❌ 不需要 | 版本管理代替观察记录 | 无（版本管理已包含） |

---

### 详解：各表的观察记录需求

#### 1. user_personas 表：需要观察记录

**答案：需要！**

**原因**：
- user_persona_observations 是 user_personas 表的"变更历史表"
- 每次 user_personas 表的数据变更，都需要在 user_persona_observations 表记录一条
- 用于溯源审计、置信度管理、增量合并历史

**大白话类比**：
- user_personas = 身份证（最终画像）
- user_persona_observations = 变更日志（每次修改身份证的记录）
- 身份证是结果，变更日志是过程（都需要）

**写入时机**：
- 会结束后写入（LLM推断，置信度85分）
- 用户手动编辑（置信度100分）
- 测评结果（置信度90分）

---

#### 2. profiles 表：需要观察记录，但作用不同

**答案：需要，但作用不同！**

**原因**：
- profiles 表只允许用户手动编辑
- 每次用户修改 profiles 表，也需要记录变更历史
- 用于溯源审计（用户在什么时候修改了什么）

**但与会话推断不同**：
- profiles 表的观察记录只记录用户手动编辑
- 不记录会话推断（因为 profiles 不支持会话推断写入）

**大白话类比**：
- profiles = 公开展示的简历（用户自己编辑）
- profile_observations = 简历变更日志（每次修改简历的记录）
- 只记录用户手动修改，不记录AI推断

**写入时机**：
- ❌ 不支持会话后写入
- ✅ 只支持用户手动编辑（置信度100分）

---

#### 3. conversation_summaries 表：不需要观察记录

**答案：不需要！**

**原因**：
- conversation_summaries 表的数据来源单一：只有 LLM 提炼
- 不需要区分置信度（都是 LLM 提炼的）
- 不需要增量合并（每次会话都是新记录）
- conversation_id 字段本身就是溯源标识

**大白话类比**：
- conversation_summaries = 日记本（每次会话写一条）
- 每条日记都有日期和会话ID，本身就是完整的记录
- 不需要额外的观察记录表

**数据来源**：
- 会结束后 LLM 提炼（单一来源）
- conversation_id + summary_key 本身是唯一标识

---

#### 4. Milvus 向量库：不需要观察记录

**答案：不需要！版本管理代替观察记录！**

**原因**：
- Milvus 向量库已经有版本管理机制：
  - vector_version（版本号）
  - create_time（创建时间）
  - is_active（激活状态）
- 版本管理本身就是观察记录：
  - 可以查看历史版本（溯源）
  - 可以查看版本变更历史（增量合并）
  - 可以查看时间戳（置信度管理）

**大白话类比**：
- Milvus = 感觉本（每次更新都有版本号）
- 版本管理 = 感觉本的页码（第1页、第2页、第3页）
- 不需要额外的观察记录表（版本管理已经包含）

**版本管理机制**：
- vector_version：每次更新版本号递增
- create_time：记录创建时间
- is_active：软删除旧版本，激活新版本

---

### 观察记录需求对比（大白话类比）

> **就像真实红娘：**
> 
> **标签卡（user_personas）**：
> - 每次修改标签卡，都记在观察本上（user_persona_observations）
> - 可以追溯：第1次写INTJ，第2次改成INFJ，第3次用户手动改成INFP
> - 观察本记录每次变更的历史
> - ✅ 需要观察记录
> 
> **公开展示简历（profiles）**：
> - 用户在设置页自己编辑简历
> - 每次编辑都记在简历变更日志上（profile_observations）
> - 只记录用户手动修改，不记录AI推断
> - 保证简历都是用户确认过的（可信度最高）
> - ✅ 需要观察记录（但只记用户手动编辑）
> 
> **日记本（conversation_summaries）**：
> - 每次会话写一条日记
> - 每条日记都有日期和会话ID
> - 不需要额外的观察记录（日记本身就是完整记录）
> - ❌ 不需要观察记录
> 
> **感觉本（Milvus）**：
> - 每次更新都有版本号（第1页、第2页、第3页）
> - 不需要额外的观察记录（版本管理已经是观察记录）
> - 可以查看历史版本（溯源）
> - ❌ 不需要观察记录（版本管理代替）

---

### 一句话大白话总结

**只有 user_personas 和 profiles 需要观察记录表，用于溯源审计！**
- **conversation_summaries 不需要**（数据来源单一，本身是完整记录）
- **Milvus 不需要**（版本管理代替观察记录）

---

## 十、实施步骤（V2修正版）

### Phase 1：移除实时写入逻辑（1天）

**任务清单**：
- [x] 保持 `sync_requester_persona_memory` 硬禁用状态
- [ ] 移除 Agent 工具列表中的 `sync_requester_persona_memory` 调用
- [ ] 更新文档，说明实时对话不写画像

---

### Phase 2：新增会结束后的分流写入逻辑（3天）

**任务清单**：
- [ ] 在 `session_end_processor.py` 中新增 `split_by_quantifiability` 函数
- [ ] 在 `session_end_processor.py` 中新增 `save_quantifiable_to_persona_tables` 函数
- [ ] 在 `process_session_end` 中调用分流写入逻辑
- [ ] 改进 `_build_summary_prompt`，增加可量化字段的提炼
- [ ] 测试验证：会结束后是否分流写入

---

### Phase 3：测试验证（2天）

**测试场景1**：可量化字段
```
用户说："我是INTJ人格"
会结束 → LLM提炼 → mbti_type="INTJ" → 
写入：
  ├─ user_persona_observations（观察记录）
  └─ user_personas（画像表）
  
❌ 不写入 profiles（只允许用户手动编辑）
```

**测试场景2**：不可量化字段
```
用户说："我性格温柔"
会结束 → LLM提炼 → personality_traits="性格温柔" → 
写入：
  ├─ conversation_summaries（摘要表）
  └─ Milvus（向量库）
  
不写入：
  ├─ user_persona_observations（不写观察记录）
  ├─ user_personas（不写画像表）
  └─ profiles（不写匹配画像表）
```

**测试场景3**：混合字段
```
用户说："我是INTJ人格，性格温柔"
会结束 → LLM提炼 → 
  mbti_type="INTJ", personality_traits="性格温柔" → 
  
分流写入：
  mbti_type → 写画像表（user_persona_observations + user_personas）
  ❌ 不写 profiles（只允许用户手动编辑）
  personality_traits → 写摘要+向量（conversation_summaries + Milvus）
```

---

**验证指标**：
- ✅ user_persona_observations 表只有可量化字段（mbti_type、smoking等）
- ✅ user_personas 表只有可量化字段
- ❌ profiles 表不支持会话后写入（只允许用户手动编辑）
- ✅ conversation_summaries 表只有不可量化字段（personality_traits、values等）
- ✅ Milvus 只有不可量化字段的向量
- ✅ evidence_text 包含 session_id（支持溯源）
- ✅ 各表的观察记录需求正确（user_personas 和 profiles 需要观察记录）

---

## 十、大白话总结（V2修正版）

### 核心设计理念（V2）

> **就像真实红娘：**
> 1. 身份证（profile）：姓名、年龄、学历（硬筛选，必须核实）
> 2. 标签卡（persona）：INTJ、不抽烟、北京（软筛选，可量化）
> 3. **感觉本（vector）：温柔、重视家庭（语义搜索，不可量化）**
> 4. 日记摘要（summary）：压力大、父母催婚（给人看的摘要，不可量化）
> 5. 微信记录（chat_history）：所有聊天内容（兜底查询）
> 6. 观察记录（observations）：每次推断的历史（支持溯源审计）

**关键修正（V2）**：
- ❌ 移除实时对话的画像写入
- ✅ 会结束后统一提炼，分流写入
- ✅ 可量化字段写画像表（user_personas + user_persona_observations）
- ❌ **profiles 不支持会话后写入**（只允许用户手动编辑）
- ✅ 不可量化字段写摘要+向量（感觉本+日记）
- ✅ 只有 user_personas 和 profiles 需要观察记录

---

### 修正后的流程（大白话）

> **实时对话阶段：**
> - 用户说："我是INTJ人格，性格温柔"
> - 红娘只记在小本本（聊天记录）
> - 不写标签卡、不写感觉本
> - 继续对话...

> **会话结束阶段：**
> - 红娘读小本本，提炼："这人是INTJ，性格温柔"
> - 分流判断：
>   - INTJ是可量化字段 → 写标签卡（user_personas）+ 记观察本
>   - ❌ **不写简历（profiles，只允许用户手动编辑）**
>   - 性格温柔是不可量化字段 → 写感觉本（Milvus）+ 日记摘要
> - 每条记录都带会话ID（可溯源）

---

### 各层的作用和区别（V2修正版）

> **可量化字段（INTJ、不抽烟）：**
> - 存在画像表（user_personas）
> - ❌ **不存在 profiles（profiles 只允许用户手动编辑）**
> - 存在观察记录（user_persona_observations）
> - 用于精确筛选（SQL WHERE）
> - **会话结束后写入**
> - **有溯源审计（可追溯到具体会话）**

> **不可量化字段（性格温柔、重视家庭）：**
> - 存在摘要表（conversation_summaries）
> - 存在向量库（Milvus）
> - 用于语义相似度搜索（cosine similarity）
> - **会话结束后写入**
> - **不写画像表（不进 user_personas）**
> - ❌ **不写 profiles（profiles 只允许用户手动编辑）**
> - **不写观察记录（不进 user_persona_observations）**

> **观察记录（user_persona_observations）的作用：**
> - 记录可量化字段的推断历史
> - 支持溯源审计（可追溯到具体会话）
> - 置信度管理（区分手动编辑和LLM推断）
> - 增量合并历史（记录变更历史）
> - **只记录可量化字段，不记录不可量化字段**

> **profiles 表的作用：**
> - ❌ **不支持会话后写入（保护用户隐私和意愿）**
> - ✅ **只允许用户在设置页手动编辑**
> - ✅ **保证数据都是用户确认过的（可信度最高）**
> - ✅ **用于候选人搜索和匹配**

---

### 一句话大白话总结（V2）

**对话时只记聊天，会结束后统一提炼：**
- **可量化字段（INTJ）→ 写画像表（user_personas + user_persona_observations）**
- ❌ **不写 profiles（profiles 只允许用户手动编辑）**
- **不可量化字段（性格温柔）→ 写摘要+向量（conversation_summaries + Milvus）**
- **数据来源单一，逻辑简单，支持溯源，观察记录只记可量化字段！**

---

## 附录：关键代码文件清单（V2）

| 文件 | 改动类型 | 关键改动 |
|------|---------|---------|
| `service_integrations.py` | 移除实时写入 | 保持硬禁用状态 |
| `session_end_processor.py` | 新增分流逻辑 | `split_by_quantifiability` + `save_quantifiable_to_persona_tables` |
| `session_end_processor.py` | 改进Prompt | 同时提炼可量化+不可量化字段 |
| `profile_write_guard.py` | 保持不变 | `QUANTIFIABLE_FIELDS` 白名单 |
| `persona_memory_lib.py` | 保持不变 | `apply_persona_patch` 写入逻辑（apply_scope="persona_only"） |
| `schema_tools.py` | 保持不变 | 表结构定义 |

---

**文档版本**：V2（2026-06-16）
**核心修正**：分流写入，可量化写画像（不写profiles），不可量化写摘要+向量
**关键保留**：user_persona_observations 用于溯源审计（只记可量化字段）
**关键限制**：profiles 只允许用户手动编辑，不支持会话后写入