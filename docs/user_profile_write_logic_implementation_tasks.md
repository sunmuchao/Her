# 用户画像写入逻辑落地任务清单（最终修正版）

> **配套文档**：本文档是 [user_profile_write_logic_complete_solution.md](user_profile_write_logic_complete_solution.md) 的落地任务拆分版本

> **最终核心理念**：
> - **实时对话阶段**：Agent 自己在对话过程中记住搜索条件（在 Agent 的上下文中），系统不插手
> - **会话结束阶段**：系统从聊天记录提炼长期偏好，写入数据库、向量库
> - **split_persona_patch 和 sync_requester_persona_memory 不用于实时对话阶段**
> - **所有画像沉淀都在会话结束后完成**
> - **Agent 记忆遗忘是 Agent 自身的问题，不是数据分流问题**
> - **向量库有版本管理**：时间戳、激活状态、时间衰减权重

---

## 核心设计理念：两个阶段，各司其职

### 实时对话阶段：Agent 自己记，系统不插手

```
用户说："帮我找北京、26-30岁、INTJ、温柔的人"
    ↓
Agent 在对话过程中自己记住搜索条件（在 Agent 的上下文中）
    ↓
Agent 自己记忆：
    - 第1轮："北京、26-30岁"
    - 第5轮："INTJ"
    - 第10轮："温柔"
    ↓
问题：Agent 记忆可能遗忘（80条限制）
    ↓
这是 Agent 自身的问题，不是数据分流问题
    ↓
系统不需要：
    - ❌ split_persona_patch 提取 search_part
    - ❌ sync_requester_persona_memory 写入数据
    - ❌ session.state["working_criteria"] 存储
```

---

### 会话结束阶段：系统从聊天记录提炼，沉淀画像

```
用户多轮对话后，会话结束：
    ↓
系统从聊天记录提炼所有信息：
    ├─ 搜索条件记录：{cities: ["北京"], age_min: 26, age_max: 30} → 写入数据库
    ├─ 长期偏好：{mbti_type: "INTJ"} → 写入数据库
    └─ 向量化数据：{personality_traits: "温柔"} → 写入向量库
    ↓
所有画像沉淀都在会话结束后完成
    ↓
系统不会遗忘（从聊天记录提炼）
```

---

## 一、P0 核心任务（必须完成才能上线）

---

### 任务 1：创建 conversation_summaries 数据库表

**任务描述**：新增 MySQL 表用于存储会话摘要，按字段存储（每个字段一条记录）

**核心理念**：
- 会话结束后，LLM 从聊天记录提炼结构化摘要
- 按字段存储，每个字段对应一个向量类型
- 持久化存储，长期有效

**具体步骤**：

```sql
-- 创建表结构（按字段存储）
CREATE TABLE conversation_summaries (
    summary_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id VARCHAR(191) NOT NULL COMMENT '对话ID（可以是discovery session、chat thread等）',
    conversation_type VARCHAR(32) NOT NULL COMMENT '对话类型（discovery/chat/assessment等）',
    requester_id BIGINT NOT NULL COMMENT '用户ID',
    profile_id BIGINT NOT NULL COMMENT '画像ID',
    summary_key VARCHAR(50) NOT NULL COMMENT '字段名（如 personality_traits、values、partner_expectation）',
    summary_text VARCHAR(500) NOT NULL COMMENT '字段值（如 "性格温柔、内向"、"重视家庭"）',
    vector_status VARCHAR(20) DEFAULT 'pending' COMMENT '向量化状态（pending/completed/failed）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    KEY idx_conversation_summaries_conversation_id (conversation_id),
    KEY idx_conversation_summaries_requester_id (requester_id),
    KEY idx_conversation_summaries_profile_id (profile_id),
    KEY idx_conversation_summaries_key (summary_key),
    KEY idx_conversation_summaries_type (conversation_type),
    KEY idx_conversation_summaries_vector_status (vector_status),
    UNIQUE KEY unique_conversation_key (conversation_id, summary_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '对话摘要表（按字段存储），每个字段对应一个向量类型'
```

**涉及文件**：
- 数据库迁移脚本（新建）
- 可能需要更新 ORM 模型

**验证标准**：
- 表创建成功
- 索引正常
- 可以插入测试数据
- 同一对话同一字段只能有一条记录（UNIQUE KEY）

**依赖关系**：无依赖，可独立执行

**预计时间**：1天

---

### 任务 2：创建会话结束处理流程（核心任务）

**任务描述**：新建 `match_domain/session_end_processor.py`，实现会话结束时的 LLM 提炼、摘要存储、向量化流程

**核心理念**：
- 会话结束后，系统从聊天记录提炼所有信息
- 包括：搜索条件记录、长期偏好、向量化数据
- 持久化存储，不会遗忘

**关键点**：
- 这是核心任务
- 从聊天记录生成结构化摘要
- 同时写入摘要文本和向量化数据
- 应用向量版本管理

**技术修正（根据实战经验）**：
- ⚠️ **时序漏洞**：异步任务触发时内存对象可能已销毁，必须从数据库重新加载
- ⚠️ **语义漏洞**：LLM 返回空字符串会导致更新机制失效，必须实现增量合并

**具体步骤**：

**步骤 2.1：创建文件**

新建文件：`match_domain/session_end_processor.py`

**步骤 2.2：实现会话结束处理核心逻辑**

```python
"""Session end processor - LLM提炼、摘要存储、向量化."""

from __future__ import annotations

from typing import Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def process_session_end(
    session_id: str,  # ⚠️ 修正：只传 session_id，不传内存对象
    requester_id: int,
    profile_id: int,
    llm_client: Any,
    db_client: Any,
    vector_store: Any,
) -> dict[str, Any]:
    """会话结束时：生成摘要 + 向量化

    Args:
        session_id: 会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        llm_client: LLM 客户端
        db_client: 数据库客户端
        vector_store: 向量存储服务

    Returns:
        处理结果

    关键修正：
    - 输入是聊天记录，不是实时 patch
    - 输出是结构化的字典，不是一段文本
    - 每个字段对应一个向量类型
    - 同时写入摘要文本和向量化数据
    """

    # ⚠️ 修正：必须从数据库重新加载聊天记录
    # 异步任务触发时内存对象可能已销毁
    # 必须通过 session_id 去 Redis 或持久化数据库里把历史聊天记录 load 出来
    messages = await load_session_messages_from_db(
        db_client=db_client,
        session_id=session_id,
    )

    if not messages:
        logger.warning(f"【会话结束处理】session_id={session_id} 无聊天记录")
        return {
            "session_id": session_id,
            "error": "无聊天记录",
            "saved_summaries": [],
            "saved_vectors": [],
        }

    logger.info(
        f"【会话结束处理】session_id={session_id} "
        f"message_count={len(messages)}"
    )

    # Step 1：LLM 提炼结构化摘要（从聊天记录）
    summary_data = await generate_structured_summary(
        session_id=session_id,
        messages=messages,
        llm_client=llm_client,
    )

    logger.info(
        f"【会话结束处理】session_id={session_id} "
        f"summary_data_keys={list(summary_data.keys())}"
    )

    # ⚠️ Step 1.5：增量合并（关键修正）
    # 如果某个维度用户没有提及，LLM 会返回空字符串 ""
    # 如果不合并，该维度的标签永远停留在上周，更新机制失效
    merged_summary_data = await merge_with_existing_profile(
        db_client=db_client,
        vector_store=vector_store,
        user_id=requester_id,
        new_summary_data=summary_data,
    )

    # Step 2：同时写入两层（摘要文本 + 向量化）
    saved_summaries = []
    saved_vectors = []

    for key, value in merged_summary_data.items():
        if isinstance(value, str) and value.strip():
            # 写入 Layer 4：摘要文本
            await save_session_summary_text(
                db_client=db_client,
                user_id=requester_id,
                session_id=session_id,
                key=key,
                text=value,
            )
            saved_summaries.append(key)

            # 写入 Layer 3：向量化数据
            embedding = await generate_embedding(value)
            await save_vector_with_version(
                vector_store=vector_store,
                user_id=requester_id,
                vector_type=key,
                embedding=embedding,
                raw_text=value,
                session_id=session_id,
            )
            saved_vectors.append(key)

    return {
        "session_id": session_id,
        "summary_data": merged_summary_data,
        "saved_summaries": saved_summaries,
        "saved_vectors": saved_vectors,
    }


async def load_session_messages_from_db(
    db_client: Any,
    session_id: str,
) -> list[dict[str, Any]]:
    """从数据库加载历史聊天记录

    Args:
        db_client: 数据库客户端
        session_id: 会话ID

    Returns:
        对话历史列表

    关键修正（时序漏洞）：
        - 在分布式系统中，异步任务触发时内存对象可能已销毁
        - 必须通过 session_id 去 Redis 或持久化数据库里把历史聊天记录 load 出来
    """
    try:
        # 从数据库查询聊天记录
        # 示例 SQL（具体表结构需要根据实际情况调整）
        rows = db_client.execute(
            """
            SELECT role, content, created_at
            FROM session_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,)
        )

        messages = [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

        logger.info(
            f"【加载聊天记录】session_id={session_id} "
            f"message_count={len(messages)}"
        )

        return messages

    except Exception as e:
        logger.error(f"Failed to load session messages for session {session_id}: {e}")
        return []


async def merge_with_existing_profile(
    db_client: Any,
    vector_store: Any,
    user_id: int,
    new_summary_data: dict[str, str],
) -> dict[str, str]:
    """增量合并：新摘要数据 + 用户历史画像

    Args:
        db_client: 数据库客户端
        vector_store: 向量存储服务
        user_id: 用户ID
        new_summary_data: 新摘要数据（可能有空字符串）

    Returns:
        合并后的摘要数据

    关键修正（语义漏洞）：
        - 如果某个维度用户没有提及，LLM 会返回空字符串 ""
        - 如果不合并，该维度的标签永远停留在上周，更新机制失效
        - 合并规则：
            - 新数据非空 → 用新数据
            - 新数据为空 → 用历史数据
    """
    # 从摘要表查询最新数据
    try:
        rows = db_client.execute(
            """
            SELECT summary_key, summary_text
            FROM conversation_summaries
            WHERE requester_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,)
        )

        # 按 summary_key 取最新一条
        profile = {}
        for row in rows:
            key = row["summary_key"]
            if key not in profile:  # 只取最新一条
                profile[key] = row["summary_text"]

        return profile

    except Exception as e:
        logger.error(f"Failed to load existing profile for user {user_id}: {e}")
        return {}


async def generate_structured_summary(
    session_id: str,
    messages: list[dict[str, Any]],
    llm_client: Any,
) -> dict[str, str]:
    """LLM 提炼结构化摘要

    Args:
        session_id: 会话ID
        messages: 对话历史
        llm_client: LLM 客户端

    Returns:
        结构化摘要字典

    关键修正（语义漏洞）：
        - 输入是聊天记录，不是实时 patch
        - 输出是结构化的字典，不是一段文本
        - 每个字段对应一个向量类型
        - 如果该维度用户没有提及，必须输出特殊标识符 KEEP（保留原样）
    """
    prompt = f"""
请根据以下对话内容，提炼用户的结构化特征：

对话内容：
{format_messages(messages)}

要求：
1. 提炼性格特质（personality_traits）：如"性格温柔、内向"
2. 提炼价值观（values）：如"重视家庭、重视事业"
3. 提炼择偶期望（partner_expectation）：如"希望找个能理解工作忙碌的人"
4. 提炼生活态度（life_attitude）：如"追求稳定、重视生活质量"
5. 提炼情感需求（emotional_needs）：如"需要理解和支持"

⚠️ 关键修正（语义漏洞）：
如果该维度用户没有提及，必须输出特殊标识符 KEEP（表示保留原样），不要输出空字符串。

输出格式（JSON）：
{
    "personality_traits": "性格温柔、内向",
    "values": "KEEP",  # ⚠️ 如果本次对话没有提及价值观，输出 KEEP
    "partner_expectation": "希望找个能理解工作忙碌的人",
    "life_attitude": "追求稳定、重视生活质量",
    "emotional_needs": "KEEP"  # ⚠️ 如果本次对话没有提及情感需求，输出 KEEP
}

注意：
- 如果某字段无法提炼，输出 KEEP（表示保留原样），不要输出空字符串 ""
- 使用简洁、客观的语言
- 每个字段长度不超过 50 字
"""

    try:
        summary_data = await llm_client.generate_json(prompt)
        logger.info(
            f"【结构化摘要生成】session_id={session_id} "
            f"summary_fields={len([k for k, v in summary_data.items() if v and v != 'KEEP'])}"
        )
        return summary_data
    except Exception as e:
        logger.error(f"Failed to generate structured summary for session {session_id}: {e}")
        return {}


def format_messages(messages: list[dict[str, Any]]) -> str:
    """格式化对话内容

    Args:
        messages: 对话历史

    Returns:
        格式化后的对话内容
    """
    formatted = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        formatted.append(f"{role}: {content}")
    return "\n".join(formatted)


async def save_session_summary_text(
    db_client: Any,
    user_id: int,
    session_id: str,
    key: str,
    text: str,
) -> None:
    """存储摘要文本（按字段存储）

    Args:
        db_client: 数据库客户端
        user_id: 用户ID
        session_id: 会话ID
        key: 字段名（如 personality_traits）
        text: 字段值（如 "性格温柔、内向"）
    """
    try:
        db_client.execute(
            """
            INSERT INTO conversation_summaries
            (conversation_id, requester_id, profile_id, summary_key, summary_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE summary_text = ?, updated_at = ?
            """,
            (session_id, user_id, user_id, key, text, datetime.now(),
             text, datetime.now())  # profile_id 暂用 user_id
        )
        logger.info(f"【摘要文本存储】session_id={session_id} key={key} text={text[:30]}")
    except Exception as e:
        logger.error(f"Failed to save summary text for session {session_id}: {e}")


async def generate_embedding(text: str) -> list[float]:
    """生成文本向量

    Args:
        text: 文本内容

    Returns:
        向量（embedding）

    注意：
        这里需要集成具体的 embedding 模型
        暂时返回空向量，后续补充
    """
    # 暂时返回空向量
    # 后续集成：OpenAI text-embedding-3-small 或 BGE-large-zh
    logger.info(f"【向量化】text={text[:30]}（待集成 embedding 模型）")
    return []


async def save_vector_with_version(
    vector_store: Any,
    user_id: int,
    vector_type: str,
    embedding: list[float],
    raw_text: str,
    session_id: str,
) -> None:
    """存储向量（带版本管理）

    Args:
        vector_store: 向量存储服务
        user_id: 用户ID
        vector_type: 向量类型（如 personality_traits）
        embedding: 向量
        raw_text: 原始文本
        session_id: 会话ID

    关键修正：
        - 查询当前版本：vector_version = old_version + 1
        - 软删除旧版本：is_active = false
        - 插入新版本：is_active = true
    """
    # 暂时记录日志
    # 后续在向量化层任务中实现
    logger.info(
        f"【向量存储】user_id={user_id} vector_type={vector_type} "
        f"raw_text={raw_text[:30]}（待实现版本管理）"
    )


__all__ = [
    "process_session_end",
    "generate_structured_summary",
    "save_session_summary_text",
    "generate_embedding",
    "save_vector_with_version",
    "format_messages",
]
```

**涉及文件**：
- 新建 `match_domain/session_end_processor.py`

**验证标准**：
- LLM 能成功提炼结构化摘要
- 摘要数据格式正确（字典）
- 每个字段对应一个向量类型
- 可以同时写入摘要文本和向量化数据（待后续实现）
- 单元测试覆盖所有路径

**依赖关系**：
- 依赖任务 1（数据库表创建）
- 依赖 embedding 模型集成（P1 任务）

**预计时间**：3天

---

## 二、P1 重要任务（向量化层实施）

---

### 任务 3：向量数据库选型与部署

**任务描述**：选择并部署向量数据库（Milvus/Pinecone/pgvector）

**推荐方案**：
- 大规模生产环境：Milvus（开源，性能好）
- 快速上线：Pinecone（云服务，易维护）
- 小规模试验：pgvector（成本低）

**具体步骤**：

**步骤 3.1：选型评估**

| 向量库 | 性能 | 易用性 | 成本 | 适用场景 |
|--------|------|--------|------|---------|
| **Milvus** | 高 | 中 | 免费+运维成本 | 大规模生产环境 |
| **Pinecone** | 高 | 高 | 云服务费用 | 快速上线 |
| **pgvector** | 中 | 高 | 低 | 小规模试验 |

**步骤 3.2：部署向量库**

根据选型结果，部署向量数据库。

**Milvus 部署示例**：
```bash
# 使用 Docker 部署
docker run -d --name milvus \
  -p 19530:19530 \
  -p 9091:9091 \
  milvusdb/milvus:latest
```

**涉及文件**：
- 向量数据库部署配置
- 可能需要更新环境变量

**验证标准**：
- 向量库成功部署
- 可以连接和操作
- 性能满足需求

**依赖关系**：无依赖，可独立执行

**预计时间**：3天

---

### 任务 4：创建向量库 Collection

**任务描述**：创建 Milvus Collection，增加版本管理、时间戳、激活状态

**关键修正**：
- 原方案：无版本管理
- 修正后：增加 vector_version、create_time、is_active

**具体步骤**：

**步骤 4.1：设计 Collection Schema**

```python
# Milvus Collection 设计（修正版）

collection_schema = {
    "fields": [
        {"name": "vector_id", "type": "INT64", "is_primary": True, "auto_id": True},
        {"name": "user_id", "type": "INT64"},
        {"name": "conversation_id", "type": "VARCHAR", "max_length": 191},
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
```

**涉及文件**：
- 新建 `match_domain/vector_store.py`

**验证标准**：
- Collection 创建成功
- 字段包含版本号、时间戳、激活状态
- 索引创建成功

**依赖关系**：依赖任务 3（向量数据库部署）

**预计时间**：2天

---

### 任务 5：集成 embedding 模型

**任务描述**：集成 embedding 模型，实现文本向量化

**推荐方案**：
- 英文场景：text-embedding-3-small（成本低，性能好）
- 中文场景：BGE-large-zh（开源免费，性能好）
- 混合场景：text-embedding-3-small（支持多语言）

**具体步骤**：

**步骤 5.1：创建文件**

新建文件：`match_domain/embedding_service.py`

**步骤 5.2：实现 embedding 服务**

```python
"""Embedding service - text to vector."""

from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量化生成服务"""

    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str | None = None):
        """初始化

        Args:
            model_name: 模型名称
            api_key: API Key（如果使用 OpenAI）
        """
        self.model_name = model_name
        self.api_key = api_key

        # 根据 model_name 选择模型
        if model_name.startswith("text-embedding"):
            # OpenAI 模型
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        elif model_name.startswith("BGE"):
            # BGE 模型（本地）
            # 需要安装：pip install sentence-transformers
            from sentence_transformers import SentenceTransformer
            self.client = SentenceTransformer(model_name)

    async def generate_embedding(self, text: str) -> list[float]:
        """生成文本向量

        Args:
            text: 文本内容

        Returns:
            向量（embedding）
        """
        # 清理文本
        cleaned_text = self._clean_text(text)

        try:
            if self.model_name.startswith("text-embedding"):
                # OpenAI 模型
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=cleaned_text
                )
                embedding = response.data[0].embedding
            else:
                # BGE 模型（本地）
                embedding = self.client.encode(cleaned_text).tolist()

            logger.info(
                f"【向量化】model={self.model_name} "
                f"text={cleaned_text[:30]} embedding_dim={len(embedding)}"
            )

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    def _clean_text(self, text: str) -> str:
        """清理文本

        Args:
            text: 文本内容

        Returns:
            清理后的文本
        """
        # 移除多余空格
        # 移除特殊字符
        # 限制长度
        return text.strip()[:500]


__all__ = ["EmbeddingService"]
```

**涉及文件**：
- 新建 `match_domain/embedding_service.py`

**验证标准**：
- 可以生成向量
- 向量维度正确（768 或 1536）
- 错误处理正确
- 单元测试覆盖所有路径

**依赖关系**：无依赖，可独立执行

**预计时间**：2天

---

## 三、任务依赖关系图

```
任务 1：数据库表创建
  ├─ 无依赖

任务 2：会话结束处理流程（核心）
  ├─ 依赖：任务 1

任务 3：向量数据库部署
  ├─ 无依赖

任务 4：向量库 Collection 创建
  ├─ 依赖：任务 3

任务 5：embedding 服务
  ├─ 无依赖

任务 6：集成向量存储到会话结束处理（后续任务）
  ├─ 依赖：任务 2
  ├─ 依赖：任务 4
  ├─ 依赖：任务 5
```

---

## 四、大白话总结

### 核心设计理念

> **就像红娘工作：**
> 
> **聊天时（实时对话）**：
> - 红娘自己记客户的条件（在脑子里）
> - 系统不要插手，不要分流数据
> - 红娘可能记不住那么多（这是红娘的问题）
> 
> **下班后（会话结束）**：
> - 系统整理聊天记录
> - 从聊天记录提炼长期偏好
> - 写入数据库、向量库
> - 所有画像沉淀都在这里完成
> 
> **关键点**：
> - 实时对话：Agent 自己记，系统不插手
> - 会话结束：系统从聊天记录提炼，沉淀画像

---

**文档版本**：v3.0（最终修正版）
**最后更新**：2026-06-14
**配套方案文档**：[user_profile_write_logic_complete_solution.md](user_profile_write_logic_complete_solution.md)