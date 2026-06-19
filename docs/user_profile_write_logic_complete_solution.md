# 用户画像写入逻辑完整方案

## 一、方案概述

### 核心设计理念：红娘匹配类比（修正版）

> **就像真实红娘帮人匹配对象：**
> 1. 先让用户填基本信息（姓名、年龄、学历）→ 硬筛选
> 2. 聊天中整理结构化数据（INTJ人格、不抽烟）→ 软筛选
> 3. **会话结束后提炼摘要并向量化（性格温柔、重视家庭）→ 语义搜索**
> 4. 保留完整聊天记录（微信记录）→ 兜底查询

**关键修正**：
- 主观描述（性格温柔、重视家庭）必须先经过 LLM 提炼才能存在
- 向量化的输入是"会话摘要"，不是"实时对话 patch"
- 摘要和向量是同一流程的两个输出，不是两个独立流程

### 五层存储架构

```
┌─────────────────────────────────────────────────────────────┐
│  第1层：profile_part（硬筛选）                              │
│  存储位置：MySQL profiles 表                                │
│  特点：需要用户确认后生效                                    │
│  用途：用户真实身份信息                                      │
│  例子：年龄、城市、学历、婚姻状况                            │
│  搜索方式：SQL WHERE age BETWEEN 26 AND 30                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第2层：persona_part（软筛选 - 结构化数据）                 │
│  存储位置：persona-memory-sync 服务                         │
│  特点：直接写入，不需要确认                                  │
│  用途：可量化、无歧义的用户特质和择偶偏好                    │
│  例子：INTJ人格、不抽烟、早睡早起、喜欢内向的人              │
│  搜索方式：SQL WHERE mbti_type = 'INTJ'                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第3层：vector_part（语义搜索 - 向量化数据）【修正】         │
│  存储位置：向量数据库（Milvus/Pinecone）                     │
│  特点：会话结束后 LLM 提炼，自动向量化                       │
│  数据来源：Layer 4 摘要（不是实时对话 patch）                │
│  用途：主观描述、价值观、性格特质的向量表示                  │
│  例子：性格温柔、重视家庭、能理解工作忙碌                    │
│  搜索方式：向量相似度搜索 cosine_similarity > 0.85          │
│  版本管理：vector_version + create_time + is_active         │
│  时间衰减：age_days > 30 → decay_factor = 0.7              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第4层：session_summary（摘要筛选 - 展示文本）              │
│  存储位置：MySQL session_summaries 表                       │
│  特点：LLM生成，每次会话后提炼                              │
│  用途：给人看的摘要，辅助决策                                │
│  例子：最近压力大、父母催婚、性格温柔                        │
│  搜索方式：给人读，不用于机器搜索                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  第5层：agent_session（聊天记录兜底）                       │
│  存储位置：MySQL agent_session_store                        │
│  特点：系统自动记录所有对话                                  │
│  用途：完整对话内容，最后兜底                                │
│  例子：所有 messages（用户说的每一句话）                     │
│  搜索方式：RAG 检索                                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  特殊层：search_part（本轮对话记忆防丢失）                  │
│  存储位置：session.state["working_criteria"]                │
│  特点：本轮对话内有效                                        │
│  用途：防止 Agent 记忆缺失，记录本轮搜索条件                  │
│  例子：本轮说的"帮我搜北京、26-30岁"                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、结构化数据提取方案

### 2.1 核心原则：只有可量化、无歧义的才记结构化数据

#### 可量化判断标准

| 字段类型 | 是否可量化 | 判断标准 | 例子 |
|---------|-----------|---------|------|
| **数值范围** | ✅ 可量化 | 明确的数字范围 | 年龄26-30、身高170-180、收入10-20万 |
| **枚举类型** | ✅ 可量化 | 明确的有限选项 | MBTI（16种）、婚姻状态（已婚/未婚/离异） |
| **布尔值** | ✅ 可量化 | 明确的是/否 | 是否抽烟、是否有孩子、是否喝酒 |
| **地理位置** | ✅ 可量化 | 明确的城市/区县 | 北京、上海、朝阳区 |
| **学历等级** | ✅ 可量化 | 明确的学历层次 | 硕士、本科、大专 |
| **主观描述** | ❌ 有歧义 | 每个人理解不同 | 性格温柔、重视家庭、有责任心 |
| **程度描述** | ❌ 有歧义 | 量化标准不明确 | 最近压力大、偶尔喝酒、经常加班 |
| **情感状态** | ❌ 有歧义 | 主观感受 | 父母催婚压力、工作焦虑 |

---

#### 可量化字段白名单

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

---

### 2.2 提取流程：三层判断

```
┌─────────────────────────────────────────────────────────────┐
│  第1层：Agent 自主判断（主要）                               │
│                                                             │
│  Agent 在 System Prompt 中学习判断标准：                    │
│  - 用户说"我是INTJ人格" → Agent判断可量化 → 传 mbti_type   │
│  - 用户说"我性格温柔" → Agent判断有歧义 → 传到摘要          │
│                                                             │
│  优势：灵活、智能                                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第2层：split_persona_patch 分流（次要）                     │
│                                                             │
│  工具层根据字段名分流：                                      │
│  - mbti_type → persona_part（结构化数据）                   │
│  - personality_traits ❌ 不在 QUANTIFIABLE_FIELDS → 摘要   │
│                                                             │
│  优势：确定性、纠正Agent错误                                 │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第3层：sync_requester_persona_memory 写入（兜底）          │
│                                                             │
│  服务层最终判断：                                            │
│  - 检查字段是否在 QUANTIFIABLE_FIELDS                       │
│  - 如果不在，写入摘要而非结构化数据                          │
│                                                             │
│  优势：最后兜底，防止错误写入                                │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.3 Agent System Prompt 设计

```python
# Agent 的 System Prompt（核心部分）

"""
当用户说出以下类型的信息时，提取为结构化数据：

✅ 可量化、无歧义（提取为结构化数据）：
- 年龄、身高、收入（数值范围）
  - 用户说："我28岁" → age: 28
  - 用户说："喜欢26-30岁" → age_min: 26, age_max: 30

- MBTI类型、婚姻状态（枚举类型）
  - 用户说："我是INTJ" → mbti_type: "INTJ"
  - 用户说："我未婚" → marital_status: "未婚"

- 是否抽烟、是否有孩子（布尔值）
  - 用户说："我不抽烟" → smoking: false
  - 用户说："我有孩子" → has_children: true

- 城市、学历（明确选项）
  - 用户说："我在北京" → city: "北京"
  - 用户说："我硕士" → education: "硕士"

❌ 有歧义、主观描述（不记结构化数据，让系统记到摘要）：
- 性格温柔、重视家庭（主观描述）
- 最近压力大、偶尔喝酒（程度描述）
- 父母催婚、工作焦虑（情感状态）

这些不要提取为结构化数据，让系统自动生成摘要。
"""
```

---

### 2.5 工具层分流逻辑改进（修正版）

```python
# profile_write_guard.py 改进

def split_persona_patch(patch: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """分流逻辑：只处理可量化字段

    关键修正：
    - 移除 vector_part 和 summary_part
    - 主观字段不在实时对话 patch 中
    - 主观字段需要 LLM 会话结束后提炼
    """

    profile_part: dict[str, Any] = {}
    persona_part: dict[str, Any] = {}

    for raw_key, value in dict(patch or {}).items():
        key = str(raw_key or "").strip()
        if not key or value in (None, "", [], {}):
            continue

        # 第1层：特殊标识符
        if key in {"profile_id", "user_key"}:
            persona_part[key] = value
            continue

        # 第2层：profile 字段
        if key in _WRITABLE_PROFILE_COLUMNS:
            profile_part[key] = value
            continue

        # 第3层：self_ 字段映射
        if key in _PERSONA_SELF_TO_PROFILE:
            profile_part[_PERSONA_SELF_TO_PROFILE[key]] = value
            continue

        # 第4层：可量化判断
        if key in QUANTIFIABLE_FIELDS:
            persona_part[key] = value  # 可量化 → persona_part
            continue

        # 第5层：target_ 前缀（择偶偏好）
        if key.startswith("target_"):
            # 检查是否可量化
            target_key = key.replace("target_", "")
            if target_key in QUANTIFIABLE_FIELDS:
                persona_part[key] = value  # 可量化的择偶偏好
            # 不可量化的择偶偏好 → 不处理，让聊天记录自然存储
            continue

        # 第6层：兜底 → 不处理
        # 主观描述字段不在实时对话 patch 中
        # 它们需要 LLM 会话结束后提炼
        # 不做任何分流，让聊天记录自然存储

    return profile_part, persona_part


# 移除 VECTORIZE_FIELDS
# 因为主观字段不在实时对话 patch 中
# VECTORIZE_FIELDS 在会话结束后的 LLM 提炼流程中使用
```

---

## 三、摘要生成和存储方案

### 3.1 摘要的作用：节省 token

#### token 消耗对比

| 存储方式 | 内容大小 | token消耗 | 读取成本 |
|---------|---------|----------|---------|
| **结构化数据** | 几个字段 | 几十 token | 极低 |
| **摘要** | 100-200字 | 几百 token | 低 |
| **聊天记录** | 几百条对话 | 几千 token | 高 |

**节省效果：**
> 结构化数据 + 摘要 ≈ 几百 token
> 聊天记录 ≈ 几千 token
> **节省90%的 token**

---

### 3.2 摘要的内容：会话提炼

#### 摘要应该包含的内容

```python
# 摘要内容结构
session_summary = {
    # 主观描述（性格、价值观）
    "personality_traits": "性格温柔、有责任心",

    # 情感状态（压力、焦虑）
    "emotional_state": "最近工作压力大、父母催婚压力大",

    # 生活状态（工作、家庭）
    "life_status": "每天加班到很晚、每周父母打电话催婚",

    # 择偶期望（主观要求）
    "partner_expectation": "希望找一个能理解工作忙碌的人、重视家庭的人",

    # 其他重要信息
    "other_info": "喜欢看电影、偶尔运动",
}
```

#### 摘要示例

**会话内容：**
```
用户："我最近工作压力很大，每天加班到很晚"
用户："父母总是催婚，每周都打电话问"
用户："我希望找一个能理解我工作忙的人"
用户："我性格温柔，重视家庭"
```

**LLM 生成的摘要：**
```
用户最近工作压力大，每天加班，父母催婚压力大。
性格温柔，重视家庭。
希望找一个能理解工作忙碌、重视家庭的伴侣。
```

---

### 3.3 摘要生成时机

```python
# 会话结束判断逻辑

def detect_session_end(messages: list[dict]) -> bool:
    """判断会话是否结束"""

    # 用户明确结束
    end_keywords = ["好的，谢谢", "没事了", "就这样", "再见"]
    last_user_message = messages[-1]["content"]
    if any(keyword in last_user_message for keyword in end_keywords):
        return True

    # 用户长时间无回复（超过30分钟）
    last_message_time = messages[-1]["timestamp"]
    current_time = datetime.now()
    if (current_time - last_message_time).seconds > 1800:
        return True

    # Agent 主动结束（返回了最终推荐）
    if messages[-1]["role"] == "assistant" and "推荐" in messages[-1]["content"]:
        return True

    return False
```

---

### 3.4 摘要生成流程

```python
# 每次会话结束后调用 LLM 生成摘要

async def generate_session_summary(session_id: str, messages: list[dict]) -> str:
    """生成会话摘要"""

    # 构造 Prompt
    prompt = f"""
请根据以下对话内容，生成会话摘要（100-200字）：

对话内容：
{format_messages(messages)}

要求：
1. 提炼用户特质（性格、价值观、生活习惯）
2. 提炼情感状态（压力、焦虑、期待）
3. 提炼择偶期望（希望找什么样的人）
4. 提炼生活状态（工作、家庭、社交）
5. 摘要长度：100-200字
6. 使用简洁、客观的语言

示例：
用户最近工作压力大，每天加班，父母催婚压力大。
性格温柔，重视家庭。
希望找一个能理解工作忙碌、重视家庭的伴侣。
"""

    # 调用 LLM
    summary = await call_llm(prompt)

    return summary


def format_messages(messages: list[dict]) -> str:
    """格式化对话内容"""
    formatted = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        formatted.append(f"{role}: {content}")
    return "\n".join(formatted)
```

---

### 3.5 会话结束处理流程（修正版）

#### 关键修正：摘要和向量是同一流程的两个输出

```
┌─────────────────────────────────────────────────────────────┐
│  会话结束处理流程                                            │
│                                                             │
│  Step 1：LLM 提炼结构化摘要（从聊天记录）                     │
│      ↓                                                      │
│  Step 2：同时写入两层                                        │
│  ├─ Layer 4：摘要文本 → session_summaries 表               │
│  └─ Layer 3：向量化数据 → vector_store                     │
│      ↓                                                      │
│  Step 3：向量版本管理                                        │
│  ├─ 查询当前版本：vector_version = 1                        │
│  ├─ 软删除旧版本：is_active = false                         │
│  └─ 插入新版本：vector_version = 2, is_active = true       │
│                                                             │
│  关键点：                                                    │
│  - Layer 3 的输入是 Layer 4 的摘要                          │
│  - 摘要和向量是同一流程的两个输出                            │
│  - 不是两个独立的写入管道                                    │
└─────────────────────────────────────────────────────────────┘
```

---

#### 代码实现

```python
# 会话结束时的处理流程

async def process_session_end(session: StoredSession) -> None:
    """会话结束时：生成摘要 + 向量化"""

    # Step 1：LLM 提炼结构化摘要（从聊天记录）
    summary_data = await generate_structured_summary(session.messages)
    # summary_data = {
    #     personality_traits: "性格温柔",
    #     values: "重视家庭",
    #     partner_expectation: "能理解工作忙碌",
    #     life_attitude: "追求稳定",
    #     emotional_needs: "需要理解和支持"
    # }

    # Step 2：同时写入两层（摘要文本 + 向量化）
    for key, value in summary_data.items():
        if isinstance(value, str) and value.strip():
            # 写入 Layer 4：摘要文本
            await save_session_summary_text(
                user_id=session.requester_id,
                session_id=session.session_id,
                key=key,
                text=value
            )

            # 写入 Layer 3：向量化数据
            embedding = await generate_embedding(value)
            await save_vector_with_version(
                user_id=session.requester_id,
                vector_type=key,
                embedding=embedding,
                raw_text=value,
                session_id=session.session_id
            )


async def generate_structured_summary(messages: list[dict]) -> dict[str, str]:
    """LLM 提炼结构化摘要

    关键修正：
    - 输入是聊天记录，不是实时 patch
    - 输出是结构化的字典，不是一段文本
    - 每个字段对应一个向量类型
    """
    prompt = """
请根据以下对话内容，提炼用户的结构化特征：

对话内容：
{format_messages(messages)}

要求：
1. 提炼性格特质（personality_traits）：如"性格温柔、内向"
2. 提炼价值观（values）：如"重视家庭、重视事业"
3. 提炼择偶期望（partner_expectation）：如"希望找个能理解工作忙碌的人"
4. 提炼生活态度（life_attitude）：如"追求稳定、重视生活质量"
5. 提炼情感需求（emotional_needs）：如"需要理解和支持"

输出格式（JSON）：
{
    "personality_traits": "性格温柔、内向",
    "values": "重视家庭、重视事业",
    "partner_expectation": "希望找个能理解工作忙碌的人",
    "life_attitude": "追求稳定、重视生活质量",
    "emotional_needs": "需要理解和支持"
}

注意：
- 如果某字段无法提炼，输出空字符串 ""
- 使用简洁、客观的语言
- 每个字段长度不超过 50 字
"""
    summary_data = await call_llm_json(prompt)
    return summary_data


async def save_session_summary_text(
    user_id: int,
    session_id: str,
    key: str,
    text: str
) -> None:
    """存储摘要文本"""
    # 存入 session_summaries 表
    # 每个字段一条记录
    await db.execute(
        """
        INSERT INTO session_summaries
        (session_id, requester_id, summary_key, summary_text, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, user_id, key, text, datetime.now())
    )
```

---

### 3.6 摘要存储方案

#### 数据库表设计

```sql
-- MySQL 表：session_summaries
CREATE TABLE session_summaries (
    summary_id INT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(50) NOT NULL,
    requester_id INT NOT NULL,
    profile_id INT NOT NULL,
    summary TEXT NOT NULL,  -- 摘要内容（100-200字）
    created_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_session_id (session_id),
    INDEX idx_requester_id (requester_id),
    INDEX idx_profile_id (profile_id)
);
```

---

#### 存储流程（修正版）

```python
# sync_requester_persona_memory 改进（实时对话阶段）

def sync_requester_persona_memory(
    session: StoredSession,
    *,
    patch: dict[str, Any],
    now: datetime | None = None,
    load_persona_memory: Callable[..., dict[str, Any]] | None = None,
    storage: Any | None = None,
    load_profile: Callable[..., Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """实时对话阶段：只处理可量化字段"""

    normalized_patch = dict(patch or {})

    # 分流：profile_part, persona_part
    profile_part, persona_part = split_persona_patch(normalized_patch)

    # 处理 profile_part（资料变更）
    if profile_part:
        # 生成变更提议，等待用户确认
        ...

    # 处理 persona_part（结构化数据）
    if persona_part:
        # 写入 persona-memory-sync 服务
        ...

    # 不处理主观字段（不在实时 patch 中）
    # 它们需要 LLM 会话结束后提炼

    return {
        "synced": True,
        "profile_part": profile_part,
        "persona_part": persona_part,
        ...
    }
```

---

### 3.6 摘要读取优先级

```python
# Agent 需要了解用户时的读取顺序

async def load_user_context(user_id: int, session_id: str) -> dict:
    """加载用户上下文"""

    # 第1步：读结构化数据（几十token）
    persona_data = load_persona_memory(user_id)

    # 第2步：读摘要（几百token）
    summaries = load_session_summaries(user_id)
    # 聚合所有摘要
    aggregated_summary = aggregate_summaries(summaries)

    # 第3步：读聊天记录（几千token，最后兜底）
    # 只有当结构化数据+摘要都不够时才读取
    if need_more_details(persona_data, aggregated_summary):
        chat_history = load_chat_history(session_id)

    return {
        "persona_data": persona_data,       # 结构化数据
        "summary": aggregated_summary,      # 摘要
        "chat_history": chat_history,       # 聊天记录（可选）
    }
```

---

## 四、聊天记录存储方案

### 4.1 现有系统已存储聊天记录

#### 存储位置

**文件**：[agent_session_store.py](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)

**存储方式**：
- ✅ InMemoryDiscoveryAgentSessionStore（内存存储）
- ✅ MySQLDiscoveryAgentSessionStore（MySQL持久化）

---

#### 存储内容

```python
# 每个 session 存储的内容
class InMemoryDiscoveryAgentSession:
    session_id: str          # 会话ID
    messages: list[dict]     # 所有对话历史

    # 方法
    async def get_items(limit: int | None = None) -> list[dict]:
        """获取对话历史，可限制条数"""

    async def add_items(items: list[dict]) -> None:
        """添加新的对话历史"""
```

---

#### 对话历史条数限制

```python
# 环境变量配置
HER_DISCOVERY_AGENT_SESSION_LIMIT = 80  # 默认保留80条对话

# 如果设置为 "unlimited" 或 "0"，则不限制
```

---

### 4.2 聊天记录的作用：兜底查询

#### 查询场景

```python
# 当结构化数据+摘要都无法满足时，查聊天记录

场景1：摘要写"不喜欢抽烟"，但用户实际说"可以接受偶尔抽烟"
→ 查聊天记录找到细节："讨厌抽烟，但可以接受偶尔抽烟"

场景2：摘要写"重视家庭"，但用户说具体要求"希望对方周末能陪家人"
→ 查聊天记录找到细节："希望对方周末能陪家人"

场景3：摘要没写用户对异地恋的态度
→ 查聊天记录找到："可以接受异地，但希望每月见面一次"
```

---

#### 查询方式：RAG 检索

```python
# 使用 RAG 从聊天记录中检索相关信息

async def search_chat_history(session_id: str, query: str) -> str:
    """从聊天记录中检索相关信息"""

    # 加载聊天记录
    messages = await load_chat_history(session_id)

    # RAG 检索
    relevant_messages = rag_search(messages, query)

    # 提取相关内容
    relevant_content = extract_relevant_content(relevant_messages)

    return relevant_content


# 示例
query = "用户对抽烟的态度是什么？"
result = await search_chat_history(session_id, query)
# 返回："讨厌抽烟，但可以接受偶尔抽烟"
```

---

## 五、search_part 的作用

### 5.1 核心作用：防止本轮对话 Agent 记忆缺失

#### 问题场景

```python
# 本轮对话（Agent 记忆可能缺失）

第1轮：用户说"帮我搜北京的"
→ Agent 记住："北京"（但可能在80条限制中被丢弃）

第5轮：用户说"26-30岁"
→ Agent 记住："26-30岁"

第10轮：用户说"改成上海的"
→ Agent 可能忘记第1轮说的"北京"
→ 但 search_part 还在：{cities: ["上海"], age_min: 26, age_max: 30}
```

---

### 5.2 search_part 的生命周期

```
┌─────────────────────────────────────────────────────────────┐
│  search_part 的生命周期                                      │
│                                                             │
│  创建时机：用户说出搜索条件时                                 │
│  - 用户说"帮我搜北京" → search_part: {cities: ["北京"]}    │
│                                                             │
│  更新时机：用户调整搜索条件时                                 │
│  - 用户说"改成上海" → search_part: {cities: ["上海"]}      │
│                                                             │
│  累积时机：用户逐步添加条件时                                 │
│  - 用户说"26-30岁" → search_part: {cities: ["上海"],       │
│                                     age_min: 26, age_max: 30}│
│                                                             │
│  失效时机：本轮对话结束时                                     │
│  - 会话结束后，search_part 清空                              │
│                                                             │
│  作用：防止 Agent 记忆缺失                                   │
│  - Agent 可以随时读取 search_part 知道当前搜索条件           │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.3 search_part vs persona_part 的区别

| 维度 | search_part | persona_part |
|------|-------------|--------------|
| **生命周期** | 本轮对话内有效 | 长期有效 |
| **存储位置** | session.state（临时） | persona-memory-sync（持久） |
| **作用** | 防止本轮记忆缺失 | 记长期偏好 |
| **优先级** | 当前意图优先 | 长期偏好次级 |
| **例子** | "帮我搜北京"（本次） | "我偏好北京"（长期） |

---

### 5.4 大白话类比

> **search_part = 红娘的小本本**
> - 红娘和用户聊天时，随手记下"这次要找北京、26-30岁的"
> - 如果红娘短期记忆忘了（可能聊天内容太多），可以看小本本
> - 聊天结束后，小本本扔掉（下次聊天重新记）

> **persona_part = 红娘的日记本**
> - 红娘记住"用户长期偏好北京、喜欢内向的人"
> - 下次用户再来，红娘还记得这些长期偏好
> - 日记本永久保存

---

## 六、整体架构设计

### 6.1 数据流向（修正版）

```
【实时对话阶段】
用户说话："我平时工作挺忙的"
    ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent 接收并判断                                            │
│                                                             │
│  - 判断是否可量化 → 提取为结构化数据                          │
│  - 判断是否主观描述 → 不分流，记到聊天记录                    │
│  - 判断是否是搜索条件 → 记到 search_part                     │
│                                                             │
│  关键修正：                                                  │
│  - 主观描述（工作忙）不在实时 patch 中                        │
│  - 这些字段必须先经过 LLM 提炼才能存在                        │
│  - split_persona_patch 只处理可量化字段                       │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  sync_requester_persona_memory（实时对话）                  │
│                                                             │
│  分流：split_persona_patch                                   │
│  ├─ profile_part → profiles 表（需要确认）                  │
│  ├─ persona_part → persona-memory-sync（结构化数据）        │
│  └─ search_part → session.state（本轮搜索条件）             │
│                                                             │
│  不处理：                                                    │
│  ├─ vector_part（主观字段不在实时 patch 中）                │
│  └─ summary_part（主观字段不在实时 patch 中）               │
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
│      personality_traits: "性格温柔",                        │
│      values: "重视家庭",                                    │
│      partner_expectation: "能理解工作忙碌"                  │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  同时写入两层（摘要文本 + 向量化数据）                       │
│                                                             │
│  ├─ Layer 4：摘要文本 → session_summaries 表               │
│  └─ Layer 3：向量化数据 → vector_store                     │
│      ├─ 向量化：embedding = encode(raw_text)                │
│      ├─ 版本管理：vector_version = old_version + 1        │
│      ├─ 软删除旧版本：is_active = false                     │
│      └─ 插入新版本：is_active = true                        │
└─────────────────────────────────────────────────────────────┘
    ↓
清空 search_part
```

---

### 6.2 匹配优先级

```
┌─────────────────────────────────────────────────────────────┐
│  第1层：硬筛选（profile_part）                              │
│                                                             │
│  查询：SQL WHERE age BETWEEN 26 AND 30 AND city = "北京"    │
│  优先级：最高（硬条件必须满足）                               │
│  token消耗：几十 token                                       │
│  结果：100个候选人                                           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第2层：软筛选（persona_part - 结构化数据）                 │
│                                                             │
│  查询：性格匹配算法、标签匹配                                 │
│  优先级：高（软条件尽量满足）                                 │
│  token消耗：几十 token                                       │
│  结果：30个候选人                                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第3层：向量筛选（vector_part - 向量化数据）【修正】         │
│                                                             │
│  查询：向量相似度搜索                                         │
│  优先级：中高（语义匹配）                                     │
│  token消耗：0 token（向量搜索不需要 token）                  │
│  搜索速度：毫秒级（搜索1000个向量只需几毫秒）                 │
│                                                             │
│  关键修正：                                                  │
│  - 只搜索激活版本：is_active == true                         │
│  - 应用时间衰减：age_days > 30 → decay_factor = 0.7        │
│  - 避免多值冲突：不会同时被当成内向和外向                     │
│                                                             │
│  示例：                                                      │
│  用户A说："希望找个温柔、重视家庭的人"                       │
│  → 向量化：embedding_vector = [0.85, 0.72, 0.91,...]       │
│  → 在向量库中搜索相似向量                                    │
│  → expr: is_active == true（只搜索激活版本）                │
│  → 时间衰减：age_days > 30 → similarity *= decay_factor    │
│  → 找到：                                                    │
│    - 用户B：性格温和（similarity=0.89, version=2, age=5天）│
│    - 用户C：重视家庭（similarity=0.87, version=3, age=10天）│
│                                                             │
│  结果：10个候选人                                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第4层：摘要筛选（session_summary）                         │
│                                                             │
│  查询：语义相似度匹配、价值观匹配                             │
│  优先级：中（补充匹配）                                       │
│  token消耗：几百 token                                       │
│  结果：10个候选人                                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  第5层：聊天记录兜底（agent_session）                       │
│                                                             │
│  查询：RAG 检索、全文检索                                     │
│  优先级：低（最后兜底）                                       │
│  token消耗：几千 token                                       │
│  结果：5个最终推荐                                           │
└─────────────────────────────────────────────────────────────┘

特殊情况：
┌─────────────────────────────────────────────────────────────┐
│  search_part（本轮对话临时覆盖）                             │
│                                                             │
│  作用：当前搜索条件优先于长期偏好                             │
│  例子：用户长期偏好北京，但本轮想搜上海                       │
│  → search_part: {cities: ["上海"]} 临时覆盖                 │
│  → persona_part: {target_cities: ["北京"]} 长期偏好保留     │
└─────────────────────────────────────────────────────────────┘
```

---

### 6.2.1 向量搜索示例流程（修正版）

```python
# 场景：用户A说"希望找个温柔、重视家庭的人"

async def search_with_vector(user_id: int, criteria: dict) -> list[dict]:
    """向量相似度搜索流程（修正版）

    关键修正：
    - 只搜索激活版本：is_active == true
    - 应用时间衰减：age_days > 30 → decay_factor = 0.7
    - 避免多值冲突：不会同时被当成内向和外向
    """

    # Step 1：精确过滤（第1+2层）
    candidates = await sql_filter(
        age_min=criteria.get("age_min", 26),
        age_max=criteria.get("age_max", 30),
        cities=criteria.get("cities", ["北京"]),
        education=criteria.get("education_min", "本科")
    )
    # 结果：1000个候选人

    # Step 2：向量相似度搜索（第3层-修正）
    if criteria.get("partner_expectation"):
        # 向量化择偶期望
        partner_vector = await generate_embedding(criteria["partner_expectation"])
        # "希望找个温柔、重视家庭的人" → [0.85, 0.72, 0.91,...]

        # 在向量库中搜索相似用户（修正版）
        similar_users = await search_similar_users(
            user_vector=partner_vector,
            vector_type="partner_expectation",
            top_k=100,
            similarity_threshold=0.85,
            time_decay_days=30  # 新增：时间衰减阈值
        )

        # 找到（修正版）：
        # - 用户B：性格温和（similarity=0.89, version=2, age=5天）
        # - 用户C：重视家庭（similarity=0.87, version=3, age=10天）
        # - 用户D：温柔、顾家（similarity=0.92, version=1, age=35天, decay_factor=0.7）

        # 合并结果
        candidates = [
            c for c in candidates
            if c["user_id"] in [u["user_id"] for u in similar_users]
        ]
    # 结果：50个候选人

    # Step 3：读摘要辅助决策（第4层）
    for candidate in candidates[:10]:
        summary = await load_session_summary(candidate["user_id"])
        candidate["summary"] = summary

    # Agent读摘要，判断是否匹配
    final_candidates = await agent_judge(candidates)

    return final_candidates


async def search_similar_users(
    user_vector: list[float],
    vector_type: str,
    top_k: int = 50,
    similarity_threshold: float = 0.85,
    time_decay_days: int = 30  # 新增：时间衰减阈值
) -> list[dict]:
    """向量相似度搜索（修正版）

    关键修正：
    - 只搜索激活版本：expr: is_active == true
    - 应用时间衰减：age_days > 30 → decay_factor = 0.7
    - 返回版本信息：version, age_days, decay_factor
    """
    results = milvus_collection.search(
        data=[user_vector],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"ef": 64}},
        limit=top_k,
        expr=f"vector_type == '{vector_type}' AND is_active == true",  # 修正：只搜索激活版本
        output_fields=["user_id", "raw_text", "vector_version", "create_time"]
    )

    similar_users = []
    for hit in results[0]:
        if hit.distance >= similarity_threshold:
            # 时间衰减权重（新增）
            create_time = hit.entity.get("create_time")
            age_days = (datetime.now() - datetime.fromtimestamp(create_time)).days
            decay_factor = max(0.5, 1 - age_days / time_decay_days)  # 最低权重0.5

            similar_users.append({
                "user_id": hit.entity.get("user_id"),
                "raw_text": hit.entity.get("raw_text"),
                "similarity": hit.distance * decay_factor,  # 修正：应用时间衰减
                "version": hit.entity.get("vector_version"),  # 新增：版本号
                "age_days": age_days,  # 新增：天数
                "decay_factor": decay_factor  # 新增：衰减因子
            })

    return similar_users
```

---

### 6.3 token 节省效果

| 读取方式 | token消耗 | 节省比例 |
|---------|----------|---------|
| **只读聊天记录** | 几千 token | 0% |
| **结构化数据 + 摘要** | 几百 token | **节省90%** |
| **只读结构化数据** | 几十 token | **节省95%** |

---

## 七、实施方案

### 7.1 需要新增的功能

| 功能 | 状态 | 优先级 |
|------|------|--------|
| **可量化判断逻辑** | ❌ 需新增 | P0（核心） |
| **摘要生成（LLM）** | ❌ 需新增 | P0（核心） |
| **摘要存储表** | ❌ 需新增 | P0（核心） |
| **向量数据库** | ❌ 需新增 | P1（重要） |
| **向量化生成服务** | ❌ 需新增 | P1（重要） |
| **向量搜索接口** | ❌ 需新增 | P1（重要） |
| **Agent Prompt 改进** | ❌ 需新增 | P1（重要） |
| **split_persona_patch 改进** | ❌ 需改进 | P1（重要） |
| **聊天记录存储** | ✅ 已存在 | -（无需改动） |

---

### 7.2 数据库表新增

#### 表1：session_summaries（摘要存储）

```sql
-- 新增表：session_summaries
CREATE TABLE session_summaries (
    summary_id INT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(50) NOT NULL,
    requester_id INT NOT NULL,
    profile_id INT NOT NULL,
    summary TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_session_id (session_id),
    INDEX idx_requester_id (requester_id),
    INDEX idx_profile_id (profile_id)
);
```

#### 表2：vector_store（向量存储）（修正版）

```python
# Milvus Collection 设计（修正版）

collection_schema = {
    "fields": [
        {"name": "vector_id", "type": "INT64", "is_primary": True, "auto_id": True},
        {"name": "user_id", "type": "INT64"},
        {"name": "session_id", "type": "VARCHAR", "max_length": 50},
        {"name": "vector_type", "type": "VARCHAR", "max_length": 50},
        # vector_type 分类：
        # - personality_traits（性格特质）
        # - values（价值观）
        # - partner_expectation（择偶期望）
        # - life_attitude（生活态度）
        {"name": "vector_version", "type": "INT64"},  # 新增：版本号
        {"name": "embedding", "type": "FLOAT_VECTOR", "dim": 768},
        {"name": "raw_text", "type": "VARCHAR", "max_length": 500},
        {"name": "create_time", "type": "INT64"},  # 新增：创建时间戳
        {"name": "is_active", "type": "BOOL"},  # 新增：是否激活（用于软删除）
    ],
    "index": {
        "type": "HNSW",
        "metric": "COSINE",
        "params": {"M": 16, "efConstruction": 200}
    }
}

# 创建 Collection
milvus_client.create_collection(
    collection_name="user_vectors",
    schema=collection_schema
)


# 向量版本管理逻辑（新增）

async def save_vector_with_version(
    user_id: int,
    vector_type: str,
    embedding: list[float],
    raw_text: str,
    session_id: str
) -> None:
    """存储向量（带版本管理）

    关键修正：
    - 查询当前版本：vector_version = old_version + 1
    - 软删除旧版本：is_active = false
    - 插入新版本：is_active = true
    """

    # 查询当前用户的该类型向量版本
    current_version = await get_current_vector_version(user_id, vector_type)
    new_version = current_version + 1

    # 软删除旧版本向量
    await deactivate_old_vectors(user_id, vector_type)

    # 插入新版本向量
    milvus_collection.insert([
        {
            "user_id": user_id,
            "session_id": session_id,
            "vector_type": vector_type,
            "vector_version": new_version,
            "embedding": embedding,
            "raw_text": raw_text,
            "create_time": int(datetime.now().timestamp()),
            "is_active": True  # 新版本激活
        }
    ])


async def get_current_vector_version(user_id: int, vector_type: str) -> int:
    """查询当前版本号"""
    results = milvus_collection.query(
        expr=f"user_id == {user_id} AND vector_type == '{vector_type}'",
        output_fields=["vector_version"]
    )
    if results:
        return max([r["vector_version"] for r in results])
    return 0


async def deactivate_old_vectors(user_id: int, vector_type: str) -> None:
    """软删除旧版本向量"""
    milvus_collection.update(
        expr=f"user_id == {user_id} AND vector_type == '{vector_type}' AND is_active == true",
        data={"is_active": False}
    )
```

---

#### 表3：向量类型分类（新增）

```python
# 向量类型分类（新增）

VECTOR_TYPES = {
    # 可更新类型：新版本覆盖旧版本
    "personality_traits": {
        "update_policy": "replace",  # 新版本覆盖旧版本
        "decay_days": 30,  # 30天内的向量权重较高
        "description": "性格特质：如温柔、内向、开朗",
    },

    "values": {
        "update_policy": "replace",  # 新版本覆盖旧版本
        "decay_days": 60,  # 价值观相对稳定，60天衰减
        "description": "价值观：如重视家庭、重视事业",
    },

    # 累积类型：多版本向量平均
    "partner_expectation": {
        "update_policy": "average",  # 多版本向量平均
        "decay_days": 30,
        "description": "择偶期望：如希望找个温柔的人",
    },

    "life_attitude": {
        "update_policy": "replace",  # 新版本覆盖旧版本
        "decay_days": 30,
        "description": "生活态度：如追求稳定、重视生活质量",
    },

    "emotional_needs": {
        "update_policy": "average",  # 多版本向量平均
        "decay_days": 15,  # 情感需求变化快，15天衰减
        "description": "情感需求：如需要理解和支持",
    },
}


# 向量平均逻辑（用于累积类型）

async def get_average_vector(user_id: int, vector_type: str) -> list[float]:
    """获取用户的平均向量（累积类型）"""
    results = milvus_collection.query(
        expr=f"user_id == {user_id} AND vector_type == '{vector_type}' AND is_active == true",
        output_fields=["embedding", "create_time"]
    )

    if not results:
        return None

    # 计算加权平均（时间衰减权重）
    weighted_vectors = []
    total_weight = 0

    decay_days = VECTOR_TYPES[vector_type]["decay_days"]

    for r in results:
        create_time = r["create_time"]
        age_days = (datetime.now() - datetime.fromtimestamp(create_time)).days
        decay_factor = max(0.5, 1 - age_days / decay_days)

        weighted_vectors.append([v * decay_factor for v in r["embedding"]])
        total_weight += decay_factor

    # 平均向量
    average_vector = [sum(v) / total_weight for v in zip(*weighted_vectors)]

    return average_vector
```

---

### 7.3 代码改动清单（修正版）

#### 文件1：profile_write_guard.py（修正）

```python
# 新增：可量化字段白名单
QUANTIFIABLE_FIELDS = frozenset({
    "age", "age_min", "age_max",
    "height", "height_min", "height_max",
    "mbti_type", "personality_type",
    "marital_status", "has_children",
    "smoking", "drinking",
    "cities", "education",
    ...
})

# 移除：VECTORIZE_FIELDS（修正）
# 因为主观字段不在实时对话 patch 中
# VECTORIZE_FIELDS 在会话结束后的 LLM 提炼流程中使用

# 改进：split_persona_patch（修正版）
def split_persona_patch(...) -> tuple[dict, dict]:
    # 修正：移除 vector_part 和 summary_part
    # 只处理可量化字段
    # 主观字段不在实时对话 patch 中
    ...
```

---

#### 文件2：service_integrations.py（修正）

```python
# 改进：sync_requester_persona_memory（实时对话阶段）
def sync_requester_persona_memory(...):
    # 修正：分流 profile_part, persona_part（只有这两个）
    profile_part, persona_part = split_persona_patch(patch)

    # 处理 profile_part
    if profile_part:
        # 生成变更提议，等待用户确认
        ...

    # 处理 persona_part
    if persona_part:
        # 写入 persona-memory-sync 服务
        ...

    # 修正：不处理主观字段（不在实时 patch 中）
    # 主观字段需要 LLM 会话结束后提炼


# 新增：process_session_end（会话结束阶段）
async def process_session_end(session: StoredSession) -> None:
    """会话结束时：生成摘要 + 向量化

    关键修正：
    - 从聊天记录生成结构化摘要
    - 同时写入摘要文本和向量化数据
    - 应用向量版本管理
    """
    # LLM 提炼结构化摘要
    summary_data = await generate_structured_summary(session.messages)

    # 同时写入两层
    for key, value in summary_data.items():
        # 写入 Layer 4：摘要文本
        await save_session_summary_text(...)

        # 写入 Layer 3：向量化数据
        embedding = await generate_embedding(value)
        await save_vector_with_version(...)
    ...
```

---

#### 文件3：新增 session_summary_store.py

```python
# 新增：摘要存储服务
class SessionSummaryStore:
    def save_summary(self, session_id: str, summary: str) -> None:
        """存储摘要"""

    def load_summaries(self, requester_id: int) -> list[dict]:
        """加载用户所有摘要"""

    def aggregate_summaries(self, summaries: list[dict]) -> str:
        """聚合所有摘要"""
    ...
```

---

#### 文件4：新增 summary_generator.py（修正）

```python
# 新增：摘要生成服务（修正版）
async def generate_structured_summary(messages: list[dict]) -> dict[str, str]:
    """LLM 提炼结构化摘要（修正版）

    关键修正：
    - 输入是聊天记录，不是实时 patch
    - 输出是结构化的字典，不是一段文本
    - 每个字段对应一个向量类型
    """
    prompt = """
请根据以下对话内容，提炼用户的结构化特征：

对话内容：
{format_messages(messages)}

要求：
1. 提炼性格特质（personality_traits）
2. 提炼价值观（values）
3. 提炼择偶期望（partner_expectation）
4. 提炼生活态度（life_attitude）
5. 提炼情感需求（emotional_needs）

输出格式（JSON）：
{
    "personality_traits": "性格温柔、内向",
    "values": "重视家庭、重视事业",
    "partner_expectation": "希望找个能理解工作忙碌的人",
    "life_attitude": "追求稳定、重视生活质量",
    "emotional_needs": "需要理解和支持"
}
"""
    summary_data = await call_llm_json(prompt)
    return summary_data
```

---

#### 文件5：新增 vector_store.py（修正）

```python
# 新增：向量存储服务（修正版）
class VectorStore:
    def __init__(self, collection_name: str = "user_vectors"):
        self.collection = milvus_client.get_collection(collection_name)

    async def save_vector_with_version(
        self,
        user_id: int,
        vector_type: str,
        embedding: list[float],
        raw_text: str,
        session_id: str
    ) -> None:
        """存储向量（带版本管理）（修正版）

        关键修正：
        - 查询当前版本：vector_version = old_version + 1
        - 软删除旧版本：is_active = false
        - 插入新版本：is_active = true
        """
        # 查询当前版本
        current_version = await self.get_current_vector_version(user_id, vector_type)
        new_version = current_version + 1

        # 软删除旧版本
        await self.deactivate_old_vectors(user_id, vector_type)

        # 插入新版本
        self.collection.insert([
            {
                "user_id": user_id,
                "session_id": session_id,
                "vector_type": vector_type,
                "vector_version": new_version,  # 新增：版本号
                "embedding": embedding,
                "raw_text": raw_text,
                "create_time": int(datetime.now().timestamp()),  # 新增：时间戳
                "is_active": True  # 新增：激活状态
            }
        ])

    async def search_similar_users(
        self,
        user_vector: list[float],
        vector_type: str,
        top_k: int = 50,
        similarity_threshold: float = 0.85,
        time_decay_days: int = 30  # 新增：时间衰减阈值
    ) -> list[dict]:
        """向量相似度搜索（修正版）

        关键修正：
        - 只搜索激活版本：expr: is_active == true
        - 应用时间衰减：age_days > 30 → decay_factor = 0.7
        - 返回版本信息：version, age_days, decay_factor
        """
        results = self.collection.search(
            data=[user_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=f"vector_type == '{vector_type}' AND is_active == true",  # 修正：只搜索激活版本
            output_fields=["user_id", "raw_text", "vector_version", "create_time"]  # 修正：增加版本和时间
        )

        similar_users = []
        for hit in results[0]:
            if hit.distance >= similarity_threshold:
                # 时间衰减权重（新增）
                create_time = hit.entity.get("create_time")
                age_days = (datetime.now() - datetime.fromtimestamp(create_time)).days
                decay_factor = max(0.5, 1 - age_days / time_decay_days)

                similar_users.append({
                    "user_id": hit.entity.get("user_id"),
                    "raw_text": hit.entity.get("raw_text"),
                    "similarity": hit.distance * decay_factor,  # 修正：应用时间衰减
                    "version": hit.entity.get("vector_version"),  # 新增：版本号
                    "age_days": age_days,  # 新增：天数
                    "decay_factor": decay_factor  # 新增：衰减因子
                })

        return similar_users

    async def get_current_vector_version(self, user_id: int, vector_type: str) -> int:
        """查询当前版本号（新增）"""
        results = self.collection.query(
            expr=f"user_id == {user_id} AND vector_type == '{vector_type}'",
            output_fields=["vector_version"]
        )
        if results:
            return max([r["vector_version"] for r in results])
        return 0

    async def deactivate_old_vectors(self, user_id: int, vector_type: str) -> None:
        """软删除旧版本向量（新增）"""
        self.collection.update(
            expr=f"user_id == {user_id} AND vector_type == '{vector_type}' AND is_active == true",
            data={"is_active": False}
        )
    ...
```

---

#### 文件6：新增 embedding_service.py

```python
# 新增：向量化生成服务
class EmbeddingService:
    def __init__(self, model_name: str = "text-embedding-ada-002"):
        self.model = OpenAIEmbeddingModel(model_name)

    async def generate_embedding(self, text: str) -> list[float]:
        """生成文本向量"""
        # 清理文本
        cleaned_text = self._clean_text(text)

        # 生成向量
        embedding = await self.model.embed(cleaned_text)

        return embedding

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余空格
        # 移除特殊字符
        # 限制长度
        return text.strip()[:500]
    ...
```

---

### 7.4 embedding 模型选型

| 模型 | 维度 | 性能 | 成本 | 适用场景 |
|------|------|------|------|---------|
| **OpenAI text-embedding-ada-002** | 1536 | 高 | 中 | 英文场景，性能优先 |
| **OpenAI text-embedding-3-small** | 1536 | 高 | 低 | 英文场景，成本优先 |
| **OpenAI text-embedding-3-large** | 3072 | 最高 | 高 | 英文场景，最高质量 |
| **BGE-large-zh** | 1024 | 高 | 免费 | 中文场景，开源模型 |
| **M3E-base** | 768 | 中 | 免费 | 中文场景，轻量模型 |

**推荐方案**：
- 英文场景：text-embedding-3-small（成本低，性能好）
- 中文场景：BGE-large-zh（开源免费，性能好）
- 混合场景：text-embedding-3-small（支持多语言）

---

### 7.5 向量数据库选型

| 向量库 | 性能 | 易用性 | 成本 | 适用场景 |
|--------|------|--------|------|---------|
| **Milvus** | 高 | 中 | 免费+运维成本 | 大规模生产环境 |
| **Pinecone** | 高 | 高 | 云服务费用 | 快速上线，易维护 |
| **pgvector** | 中 | 高 | 低 | 小规模，已有 PostgreSQL |
| **Weaviate** | 高 | 中 | 免费+运维成本 | 开源，功能丰富 |

**推荐方案**：
- 大规模生产环境：Milvus（性能好，开源可控）
- 快速上线：Pinecone（云服务，易维护）
- 小规模试验：pgvector（成本低，简单）

---

## 八、大白话总结（修正版）

### 核心设计理念

> **就像真实红娘：**
> 1. 身份证（profile）：姓名、年龄、学历（硬筛选，必须核实）
> 2. 标签卡（persona）：INTJ、不抽烟、早睡早起（软筛选，可量化）
> 3. **感觉本（vector）：温柔、重视家庭（语义搜索，会话结束后提炼）【修正】**
> 4. 日记摘要（summary）：压力大、父母催婚（补充筛选，主观描述）
> 5. 微信记录（chat_history）：所有聊天内容（兜底查询）
> 6. 小本本（search_part）：这次要找北京、26-30岁（防记忆缺失）

**关键修正**：
- 主观描述（温柔、重视家庭）必须先经过 LLM 提炼才能存在
- 向量化的输入是"会话摘要"，不是"实时对话 patch"
- 摘要和向量是同一流程的两个输出，不是两个独立流程

---

### 修正后的流程（大白话）

> **实时对话阶段：**
> - 用户说："我平时工作挺忙的"
> - Agent 判断：不是可量化字段（年龄、MBTI），不分流
> - 记到聊天记录，继续对话
> - 红娘只记"基本信息"和"标签卡"

> **会话结束阶段：**
> - 红娘读聊天记录，提炼："这人性格温柔、重视家庭"
> - 同时写两本：
>   - 感觉本（向量）：把"温柔"变成向量，用于搜索
>   - 日记摘要（文本）：把"温柔"写成文字，给人看
> - 每次提炼都更新感觉本（旧感觉过期，新感觉激活）

---

### 各层的作用和区别（修正版）

> **结构化数据（persona_part）：**
> - 可量化、无歧义（INTJ、不抽烟、北京）
> - 存在 persona-memory-sync
> - 用于精确筛选（SQL WHERE）
> - **实时对话时写入**

> **向量化数据（vector_part）：【修正】**
> - 主观描述、价值观、性格特质（温柔、重视家庭）
> - 存在向量数据库（Milvus）
> - 用于语义相似度搜索（cosine similarity）
> - 搜索速度：毫秒级，比人工读摘要快100倍
> - **会话结束后写入**（不是实时对话时）
> - **有版本管理**：旧版本过期，新版本激活
> - **有时间衰减**：30天内的向量权重较高

> **摘要文本（session_summary）：**
> - 有歧义、主观描述（性格温柔、压力大）
> - 存在 session_summaries 表
> - 用于给人读，辅助决策
> - **会话结束后写入**（不是实时对话时）
> - **与向量化是同一流程的两个输出**

---

### 修正后的三个根本问题（大白话）

> **问题1：Layer 3 写入时"无米下锅"**
> - 原方案：实时对话时分流 personality_traits
> - 问题：用户说"我工作忙"，patch 里不会有 personality_traits
> - 修正：主观字段不在实时 patch 中，必须 LLM 会话结束后提炼

> **问题2：Layer 3 和 Layer 4 数据重叠**
> - 原方案：摘要和向量是两个独立流程
> - 问题：两层存了完全相同的内容，架构冗余
> - 修正：摘要和向量是同一流程的两个输出，不是两个独立流程

> **问题3：向量数据库多值覆盖和时间退化**
> - 原方案：每次 insert 新向量，没有版本管理
> - 问题：同一用户多条性格向量，会同时被当成内向和外向
> - 修正：增加版本号、时间戳、激活状态、时间衰减权重

---

### 向量化层的价值

> **为什么需要向量化层？**
> - 结构化数据：无法存储"温柔、重视家庭"（不可量化）
> - 摘要文本：存了但无法搜索（只是文本）
> - 向量化层：把"温柔"变成向量 [0.85, 0.72, 0.91,...]
> - 在向量库中搜索相似向量，找到"性格温和"的人

> **向量搜索 vs 人工读摘要：**
> - 人工读摘要：1000个候选人，需要几小时
> - 向量搜索：1000个候选人，只需几毫秒
> - **效率提升100倍以上**

---

### token 节省效果

> **读取优先级：**
> 1. 先读结构化数据（几十token）
> 2. 再做向量搜索（0 token，向量搜索不需要token）
> 3. 再读摘要（几百token）
> 4. 最后读聊天记录（几千token，兜底）

> **节省效果：**
> - 结构化数据 + 向量搜索 + 摘要 ≈ 几百token
> - 聊天记录 ≈ 几千token
> - **节省90%的token**

---

### search_part 的作用

> **防止本轮对话 Agent 记忆缺失：**
> - Agent 短期记忆可能缺失（80条限制）
> - search_part 记录本轮搜索条件
> - Agent 可以随时读取 search_part 知道当前搜索条件

---

## 九、下一步实施建议（修正版）

### Phase 1：基础架构（P0核心）

**时间预估：1-2周**

| 任务 | 优先级 | 预估时间 |
|------|--------|---------|
| 数据库表创建：session_summaries | P0 | 1天 |
| 可量化判断逻辑：QUANTIFIABLE_FIELDS | P0 | 2天 |
| **会话结束处理流程：generate_structured_summary** | P0 | 3天 |
| Agent Prompt 改进：告诉 Agent 如何判断 | P0 | 2天 |
| **split_persona_patch 改进：移除 VECTORIZE_FIELDS** | P0 | 1天 |
| 测试验证：验证 token 节省效果 | P0 | 1天 |

**关键修正**：
- split_persona_patch 只处理可量化字段，移除 VECTORIZE_FIELDS
- 新增会话结束处理流程：generate_structured_summary + 向量化

---

### Phase 2：向量化层（P1重要）

**时间预估：2-3周**

| 任务 | 优先级 | 预估时间 |
|------|--------|---------|
| 向量数据库选型与部署（Milvus/Pinecone） | P1 | 3天 |
| embedding 模型选型与集成 | P1 | 2天 |
| **向量库设计：增加版本管理、时间戳、激活状态** | P1 | 2天 |
| vector_store.py 开发：向量存储服务（修正版） | P1 | 3天 |
| embedding_service.py 开发：向量化生成服务 | P1 | 2天 |
| **save_vector_with_version 开发：版本管理逻辑** | P1 | 2天 |
| **search_similar_users 开发：时间衰减搜索** | P1 | 2天 |
| 搜索流程优化：SQL + 向量搜索 + 摘要 | P1 | 2天 |
| 相似度阈值调优：验证搜索准确率 | P1 | 2天 |

**关键修正**：
- 向量库增加版本号（vector_version）、时间戳（create_time）、激活状态（is_active）
- 搜索时只搜索激活版本（is_active == true）
- 应用时间衰减权重（age_days > 30 → decay_factor = 0.7）
| vector_store.py 开发：向量存储服务 | P1 | 3天 |
| embedding_service.py 开发：向量化生成服务 | P1 | 2天 |
| sync_requester_persona_memory 改进：增加向量化处理 | P1 | 2天 |
| 向量搜索接口开发：search_similar_users | P1 | 3天 |
| 搜索流程优化：SQL + 向量搜索 + 摘要 | P1 | 2天 |
| 相似度阈值调优：验证搜索准确率 | P1 | 2天 |

---

### Phase 3：搜索优化（P2优化）

**时间预估：1-2周**

| 任务 | 优先级 | 预估时间 |
|------|--------|---------|
| 精确过滤+向量搜索+摘要判断的组合搜索流程 | P2 | 3天 |
| 搜索性能优化：索引优化、缓存优化 | P2 | 2天 |
| 监控观察：观察匹配准确率提升 | P2 | 持续观察 |
| 用户反馈收集：收集用户满意度 | P2 | 持续收集 |

---

### 技术选型建议

**向量数据库**：
- 推荐：Milvus（开源，性能好，可控性强）
- 快速上线：Pinecone（云服务，易维护）
- 小规模试验：pgvector（成本低，简单）

**Embedding 模型**：
- 英文场景：text-embedding-3-small（成本低，性能好）
- 中文场景：BGE-large-zh（开源免费，性能好）
- 混合场景：text-embedding-3-small（支持多语言）

---

### 实施优先级说明

**为什么 Phase 1 先于 Phase 2？**
- Phase 1（基础架构）是核心功能，必须先完成
- Phase 2（向量化层）是增强功能，可以逐步添加
- 先验证基础架构是否工作正常，再增加向量化层

**为什么向量化层是 P1（重要）？**
- 解决"主观描述无法搜索"的关键问题
- 把红娘的"感觉"变成可量化的相似度搜索
- 搜索效率提升100倍以上
- 对匹配准确率有显著提升

---

### 实施注意事项

**向量数据库部署**：
- 需要考虑运维成本（Milvus 需要部署和维护）
- 需要考虑成本控制（Pinecone 云服务费用）
- 建议先用小规模试验（pgvector），验证后再大规模部署

**Embedding 模型选择**：
- 需要考虑语言场景（中文/英文/混合）
- 需要考虑成本（开源免费 vs 云服务费用）
- 需要考虑性能（向量维度、搜索速度）

**相似度阈值调优**：
- 初始值：cosine_similarity > 0.85
- 需要根据实际效果调优
- 太高会漏掉好的候选人，太低会增加噪音

---

### 验证指标（修正版）

**基础架构验证**：
- token 节省效果：是否节省90%的token
- 搜索准确率：是否找到正确的候选人
- 用户满意度：用户是否满意推荐结果

**向量化层验证（修正版）**：
- **时序正确性**：主观字段是否在会话结束后写入，而非实时对话时
- **数据一致性**：摘要和向量是否是同一流程的两个输出
- **版本管理正确性**：旧版本是否被软删除，新版本是否被激活
- 搜索效率：是否提升100倍以上
- 相似度准确率：是否找到语义相似的候选人
- **时间衰减效果**：30天内的向量权重是否高于30天外的向量
- 匹配准确率：是否显著提升匹配准确率

**三个根本问题验证**：
- 问题1验证：实时对话时，patch 中是否没有 personality_traits 等主观字段
- 问题2验证：摘要和向量是否同时写入，不是两个独立流程
- 问题3验证：同一用户是否只有一条激活的性格向量，不会同时被当成内向和外向
---

### 风险评估（修正版）

**技术风险**：
- 向量数据库运维复杂度：需要技术团队熟悉 Milvus
- Embedding 模型选择错误：可能影响搜索准确率
- 相似度阈值调优困难：可能需要多次迭代
- **版本管理复杂度**：需要正确处理软删除和版本更新逻辑
- **时间衰减调优**：需要根据实际效果调优衰减参数

**业务风险**：
- 用户隐私问题：向量数据是否涉及隐私
- 匹配准确率下降：向量化可能引入噪音
- 用户接受度：用户是否接受"机器感觉"
- **数据一致性问题**：摘要和向量可能出现"两张皮"（不一致）

**应对措施**：
- 先小规模试验，验证后再大规模部署
- 持续监控匹配准确率，及时调优
- 收集用户反馈，不断改进
- **验证三个根本问题是否解决**：
  - 时序正确性：主观字段是否在会话结束后写入
  - 数据一致性：摘要和向量是否同时写入
  - 版本管理正确性：同一用户是否只有一条激活向量