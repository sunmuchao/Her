# 会话摘要增量更新完整方案

> **核心思路**：创建新会话或切换会话时，检查上一个会话是否有新增内容，如果有则只处理新增部分，增量合并到现有摘要。

---

## 📋 方案概览

| 组件 | 修改内容 | 目的 |
|------|---------|------|
| **数据库** | 添加 `processed_at` 字段 | 记录上次处理时间 |
| **触发逻辑** | 检查 `updated_at > processed_at` | 判断是否有新增内容 |
| **加载逻辑** | 只加载 `created_at > processed_at` 的消息 | 增量加载，避免重复处理 |
| **处理逻辑** | 传入 `processed_at` 参数 | 支持增量处理 |
| **更新逻辑** | 处理完成后更新 `processed_at` | 记录本次处理位置 |
| **触发时机** | `create_session` + `session_restore` | 两个时机都触发 |

---

## 🛠️ 实施步骤

### Step 1：数据库修改

#### 1.1 修改 StoredSession 数据类

**文件**：`external-systems/partner-discovery-system/discovery_system/storage.py`

```python
@dataclass
class StoredSession:
    session_id: str
    requester_id: int
    profile_id: int
    status: str
    phase: str
    created_at: datetime
    updated_at: datetime
    view: dict[str, Any]
    visible_action_ids: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    processed_at: datetime | None = None  # ✅ 新增：记录上次处理时间
```

#### 1.2 创建数据库迁移脚本

**文件**：`db_migrations/targets/discovery/m0009_add_processed_at.py`

```python
"""添加 processed_at 字段到 discovery_agent_sessions 表"""

def upgrade(conn):
    conn.execute(
        """
        ALTER TABLE discovery_agent_sessions
        ADD COLUMN processed_at DATETIME NULL
        COMMENT '上次处理摘要的时间，记录会话的 updated_at'
        """
    )
    conn.commit()

def downgrade(conn):
    conn.execute(
        """
        ALTER TABLE discovery_agent_sessions
        DROP COLUMN processed_at
        """
    )
    conn.commit()
```

#### 1.3 修改 MySQLDiscoveryStorage.save_session

**文件**：`external-systems/partner-discovery-system/discovery_system/storage.py`

在 `MySQLDiscoveryStorage.save_session` 方法中：

```python
def save_session(self, session: StoredSession) -> None:
    conn = self._open()
    try:
        state_json = json_dumps({...})
        conn.execute(
            """
            INSERT INTO discovery_agent_sessions (
                session_id, requester_id, profile_id, status, phase,
                state_json, latest_view_json, created_at, updated_at,
                processed_at  # ✅ 新增
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                requester_id = VALUES(requester_id),
                profile_id = VALUES(profile_id),
                status = VALUES(status),
                phase = VALUES(phase),
                state_json = VALUES(state_json),
                latest_view_json = VALUES(latest_view_json),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at),
                processed_at = VALUES(processed_at)  # ✅ 新增
            """,
            (
                session.session_id,
                int(session.requester_id),
                int(session.profile_id),
                session.status,
                session.phase,
                state_json,
                json_dumps(session.view),
                session.created_at,
                session.updated_at,
                session.processed_at,  # ✅ 新增
            ),
        )
        conn.commit()
    finally:
        conn.close()
```

#### 1.4 修改 MySQLDiscoveryStorage.get_session

在查询时读取 `processed_at`：

```python
def get_session(self, session_id: str) -> StoredSession | None:
    conn = self._open()
    try:
        row = row_to_dict(
            conn.execute(
                """
                SELECT session_id, requester_id, profile_id, status, phase,
                       state_json, latest_view_json, created_at, updated_at,
                       processed_at  # ✅ 新增
                FROM discovery_agent_sessions
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        )
    finally:
        conn.close()

    if row is None:
        return None

    return StoredSession(
        session_id=str(row["session_id"]),
        requester_id=int(row["requester_id"]),
        profile_id=int(row["profile_id"]),
        status=str(row["status"]),
        phase=str(row["phase"]),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
        view=dict(json_loads(str(row.get("latest_view_json") or "{}"), {}) or {}),
        visible_action_ids=[...],
        state=dict(...),
        processed_at=_parse_optional_datetime(row.get("processed_at")),  # ✅ 新增
    )
```

---

### Step 2：触发逻辑修改

**文件**：`match_domain/session_end_trigger.py`

**已完成**，核心逻辑：

```python
# 检查是否有新增内容
has_new_content = False
if previous_session.processed_at is None:
    # 第一次处理
    has_new_content = True
elif previous_session.updated_at > previous_session.processed_at:
    # 有新增内容
    has_new_content = True
else:
    # 无新增内容，跳过处理
    return None
```

---

### Step 3：处理逻辑修改

**文件**：`match_domain/session_end_processor.py`

#### 3.1 修改 trigger_session_end_processing

```python
def trigger_session_end_processing(
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str = "discovery",
    *,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    processed_at: datetime | None = None,  # ✅ 新增
    storage: Any | None = None,
) -> threading.Thread:
    """触发会话结束处理（支持增量处理）"""

    async def _process():
        try:
            result = await process_session_end(
                session_id=session_id,
                requester_id=requester_id,
                profile_id=profile_id,
                conversation_type=conversation_type,
                dsn=dsn,
                llm_base_url=llm_base_url,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                processed_at=processed_at,  # ✅ 新增：传入 processed_at
                storage=storage,
            )

            # ✅ 新增：处理完成后更新 processed_at
            if result.get("success") and storage:
                session = storage.get_session(session_id)
                if session:
                    # 更新 processed_at 为会话的 updated_at
                    session.processed_at = session.updated_at
                    storage.save_session(session)
                    _logger.info(
                        f"更新 processed_at: session_id={session_id}, "
                        f"processed_at={session.processed_at}"
                    )

        except Exception as exc:
            _logger.error(f"处理会话 {session_id} 失败: {exc}")

    # 创建线程执行
    thread = threading.Thread(
        target=lambda: asyncio.run(_process()),
        name=f"session_end_{session_id}",
    )
    thread.start()
    return thread
```

#### 3.2 修改 process_session_end

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
    processed_at: datetime | None = None,  # ✅ 新增
    storage: Any | None = None,
) -> dict[str, Any]:
    """处理会话结束（支持增量处理）"""

    # Step 1：加载聊天记录（增量加载）
    messages = await load_session_messages_from_db(
        session_id,
        dsn=dsn,
        processed_at=processed_at,  # ✅ 新增：传入 processed_at
    )

    if not messages:
        _logger.warning(f"会话 {session_id} 没有新增聊天记录，跳过处理")
        return {
            "success": False,
            "error": "no_new_messages",
            "message": "会话没有新增聊天记录",
        }

    # Step 2-N：后续处理逻辑不变...
    # （LLM提炼、增量合并、写入向量库等）
```

#### 3.3 修改 load_session_messages_from_db

**已完成**，支持增量加载：

```python
async def load_session_messages_from_db(
    session_id: str,
    *,
    dsn: str | None = None,
    processed_at: datetime | None = None,  # ✅ 新增
) -> list[dict[str, Any]]:
    """从数据库加载聊天记录（支持增量加载）"""

    # 增量加载：只加载 created_at > processed_at 的消息
    if processed_at is not None:
        rows = conn.execute(
            """
            SELECT item_json, created_at
            FROM discovery_agent_session_memory_items
            WHERE session_id = ? AND created_at > ?
            ORDER BY item_id ASC
            """,
            (session_id, processed_at),
        ).fetchall()
    else:
        # 全量加载
        rows = conn.execute(
            """
            SELECT item_json
            FROM discovery_agent_session_memory_items
            WHERE session_id = ?
            ORDER BY item_id ASC
            """,
            (session_id,),
        ).fetchall()
```

---

### Step 4：触发时机

#### 4.1 创建新会话时触发

**文件**：`external-systems/partner-discovery-system/discovery_system/service.py`

**已修改**，在 `create_session` 方法中：

```python
# 创建会话后触发处理上一个会话
self._trigger_previous_session_processing(
    requester_id=requester_id,
    profile_id=profile_id,
    conversation_type="discovery",
    current_session_id=session.session_id,  # ✅ 传入新会话 ID，避免误处理
)
```

#### 4.2 切换会话时触发（新增）

**文件**：`external-systems/partner-discovery-system/discovery_system/service.py`

新增 `switch_session` 方法：

```python
def switch_session(
    self,
    *,
    from_session_id: str,  # ✅ 当前会话（切换前）
    to_session_id: str,    # ✅ 目标会话（切换后）
    requester_id: int,
    profile_id: int,
) -> dict[str, Any]:
    """切换会话：检查切换前的会话是否有新增内容

    Args:
        from_session_id: 当前会话ID（切换前的会话）
        to_session_id: 目标会话ID（切换后的会话）
        requester_id: 用户ID
        profile_id: 画像ID

    Returns:
        目标会话的数据
    """
    # Step 1：检查切换前的会话是否有新增内容
    self._trigger_session_processing_by_id(
        session_id=from_session_id,
        requester_id=requester_id,
        profile_id=profile_id,
        conversation_type="discovery",
    )

    # Step 2：返回目标会话的数据
    target_session = self.storage.get_session(to_session_id)
    if not target_session:
        raise ValueError(f"目标会话 {to_session_id} 不存在")

    return self._session_payload(target_session)


def _trigger_session_processing_by_id(
    self,
    session_id: str,
    requester_id: int,
    profile_id: int,
    conversation_type: str = "discovery",
) -> None:
    """检查并处理指定会话的新增内容

    Args:
        session_id: 要检查的会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        conversation_type: 对话类型
    """
    import logging
    from match_domain.session_end_trigger import process_session_if_has_new_content

    _logger = logging.getLogger(__name__)

    try:
        task = process_session_if_has_new_content(
            session_id=session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            storage=self.storage,
            conversation_type=conversation_type,
        )

        if task:
            _logger.info(
                f"切换会话触发处理: session_id={session_id}, "
                f"requester_id={requester_id}, task_name={task.name}"
            )

    except Exception as exc:
        _logger.error(
            f"切换会话触发处理失败: session_id={session_id}, "
            f"requester_id={requester_id}, error={exc}"
        )
        # 不抛出异常，避免阻塞切换会话
```

#### 4.3 新增触发函数

**文件**：`match_domain/session_end_trigger.py`

新增 `process_session_if_has_new_content` 函数：

```python
def process_session_if_has_new_content(
    session_id: str,
    requester_id: int,
    profile_id: int,
    *,
    storage: Any,
    conversation_type: str = "discovery",
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> threading.Thread | None:
    """检查并处理指定会话的新增内容

    使用场景：
    - 切换会话时，检查切换前的会话是否有新增内容
    - 关闭会话时，检查关闭的会话是否有新增内容

    增量处理逻辑：
    - 检查会话是否有新增内容（updated_at > processed_at）
    - 如果有新增内容，只处理新增部分（不重复处理）
    - 处理完成后，更新 processed_at 为会话的 updated_at

    Args:
        session_id: 要检查的会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        storage: DiscoveryStorage 对象
        conversation_type: 对话类型
        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        threading.Thread 对象（如果有新增内容）
    """
    from match_domain.session_end_processor import trigger_session_end_processing

    try:
        # 获取会话
        session = storage.get_session(session_id)
        if not session:
            _logger.warning(f"会话 {session_id} 不存在，跳过处理")
            return None

        # ✅ 检查是否有新增内容
        has_new_content = False
        if session.processed_at is None:
            # 第一次处理：processed_at 为空，说明从未处理过
            has_new_content = True
            _logger.info(
                f"会话 {session_id} 从未处理过，需要处理全部内容"
            )
        elif session.updated_at > session.processed_at:
            # 有新增内容：updated_at > processed_at
            has_new_content = True
            _logger.info(
                f"会话 {session_id} 有新增内容 "
                f"(updated_at={session.updated_at}, "
                f"processed_at={session.processed_at})"
            )
        else:
            # 无新增内容：updated_at <= processed_at
            _logger.info(
                f"会话 {session_id} 无新增内容，跳过处理 "
                f"(updated_at={session.updated_at}, "
                f"processed_at={session.processed_at})"
            )
            return None

        if not has_new_content:
            return None

        _logger.info(
            f"切换会话触发处理: "
            f"session_id={session_id}, "
            f"requester_id={requester_id}, "
            f"has_new_content={has_new_content}"
        )

        # 异步触发处理
        task = trigger_session_end_processing(
            session_id=session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type=conversation_type,
            dsn=dsn,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            # ✅ 传入 processed_at，用于增量处理
            processed_at=session.processed_at,
            # ✅ 传入 storage，用于处理完成后更新 processed_at
            storage=storage,
        )

        return task

    except Exception as exc:
        _logger.error(f"处理会话 {session_id} 失败: requester_id={requester_id}, error={exc}")
        return None
```

---

### Step 5：增量合并逻辑

**文件**：`match_domain/session_end_processor.py`

已有 `merge_with_existing_profile` 函数，需要确保增量合并逻辑正确：

```python
def merge_with_existing_profile(
    new_summary: dict[str, Any],
    existing_data: dict[str, Any],
) -> dict[str, Any]:
    """增量合并：新摘要覆盖旧摘要中的对应字段，未提到的字段保留"""

    merged = deepcopy(existing_data)

    for key, value in new_summary.items():
        if value:  # 只合并有值的字段
            merged[key] = value

    return merged
```

---

## 📊 完整流程图

```
【场景1：创建新会话】

用户在会话A对话 → 用户创建新会话B
    ↓
查询用户最新的 active 会话（排除新会话ID）
    ↓
找到会话A（上一个会话）
    ↓
检查会话A是否有新增内容（updated_at > processed_at？）
    ↓ 是
处理会话A的新增内容
    ↓
更新会话A的 processed_at = updated_at
    ↓
完成（用户进入新会话B）

---

【场景2：切换历史会话】

用户在会话A对话 → 用户切换到历史会话B
    ↓
前端调用 switch_session API（传入 from_session_id=A, to_session_id=B）
    ↓
后端检查会话A是否有新增内容（updated_at > processed_at？）
    ↓ 是
处理会话A的新增内容
    ↓
更新会话A的 processed_at = updated_at
    ↓
返回会话B的数据（用户进入会话B）

---

【场景3：关闭会话】

用户在会话A对话 → 用户关闭会话A，退出发现页
    ↓
前端调用 close_session API（传入 session_id=A）
    ↓
后端检查会话A是否有新增内容（updated_at > processed_at？）
    ↓ 是
处理会话A的新增内容
    ↓
更新会话A的 processed_at = updated_at
    ↓
更新会话A的状态为 closed
    ↓
完成（用户退出发现页）

---

【场景4：恢复会话】

用户在会话列表页 → 用户恢复历史会话A
    ↓
前端调用 restore_session API（传入 to_session_id=A）
    ↓
❌ 这个场景没有"切换前的会话"，不需要处理
    ↓
返回会话A的数据（用户进入会话A）
```

---

## 🎯 测试验证

### 测试场景

| 场景 | 输入 | 预期结果 |
|------|------|---------|
| **场景1**：第一次处理 | processed_at = None | 全量加载，处理全部内容 |
| **场景2**：有新增内容 | updated_at > processed_at | 增量加载，只处理新增部分 |
| **场景3**：无新增内容 | updated_at <= processed_at | 跳过处理 |
| **场景4**：用户回到旧会话继续对话 | 旧会话 updated_at 更新 | 下次创建新会话时检测到新增内容 |
| **场景5**：连续创建多个空会话 | 无新增内容 | 不处理，不浪费资源 |

---

## 📌 注意事项

1. **processed_at 记录的是会话的 updated_at**，而不是处理时间，这样可以确保下次检查时能正确识别新增内容。

2. **增量加载使用 created_at > processed_at**，这样可以确保只加载新增的消息。

3. **processed_at 在处理完成后立即更新**，避免重复处理。

4. **数据库迁移需要先执行**，否则代码会报错。

---

## 🚀 实施优先级

| 优先级 | 步骤 | 原因 |
|--------|------|------|
| **P0 最高** | 数据库字段添加 + 迁移 | 其他步骤依赖此字段 |
| **P0 最高** | 触发逻辑检查新增内容 | 核心功能：判断要不要处理 |
| **P0 最高** | 加载逻辑增量加载 | 核心功能：增量处理，不重复 |
| **P1 高** | 处理完后更新 processed_at | 避免下次重复处理 |
| **P1 高** | 创建新会话时触发 | 主要触发时机 |
| **P1 高** | 切换会话时触发 | 补充触发时机（用户提出的场景）|
| **P2 中** | 关闭会话时触发 | 补充触发时机 |
| **P2 中** | 测试验证 | 确保功能正确 |

---

## 📌 关键设计决策

### 决策1：如何知道"切换前的会话"

**方案A（推荐）**：前端明确告诉后端
- 前端传入：`from_session_id`（当前会话）、`to_session_id`（目标会话）
- 后端检查：`from_session_id` 是否有新增内容
- 优点：实现简单，不需要额外存储

**方案B**：后端记录用户当前会话
- 在 `user_profiles` 或 `session` 表中记录：`current_session_id`
- 切换会话时，后端查询：`current_session_id`
- 缺点：需要额外存储，可能有数据不一致风险

**结论**：采用方案A，前端传入 `from_session_id`

---

### 决策2：API设计

**新增API：switch_session**

```python
POST /v1/discovery/sessions/switch
{
  "from_session_id": "session-A",  # 当前会话（切换前）
  "to_session_id": "session-B"     # 目标会话（切换后）
}

Response:
{
  "session": {...},  # 会话B的数据
  "view": {...}      # 会话B的视图
}
```

**修改API：create_session**

保持不变，系统自动查询上一个会话

**新增API：close_session**

```python
POST /v1/discovery/sessions/close
{
  "session_id": "session-A"  # 要关闭的会话ID
}

Response:
{
  "success": true,
  "processing_triggered": true  # 是否触发了处理
}
```