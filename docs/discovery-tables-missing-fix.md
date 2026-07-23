# Discovery 表缺失问题修复记录

## 问题描述

**错误日志**：
```
2026-07-23 02:03:30,283 ERROR match_domain.session_end_processor 会话结束处理失败: session_id=discovery-session-e3a2950102f0, error=(1146, "Table 'her.discovery_agent_session_memory_items' doesn't exist")
```

## 根因分析

### 五问法

```
问题现象：会话结束处理失败，表不存在
├─ 为什么 1: 代码查询 her.discovery_agent_session_memory_items
├─ 为什么 2: session_end_processor 使用 HER_PERSONA_DB（her数据库）
├─ 为什么 3: discovery 表在 her_discovery 数据库，不在 her 数据库
├─ 为什么 4: 数据库架构设计时，discovery 独立一个数据库
└─ 为什么 5: 【根本原因】跨数据库查询场景未在 her 数据库创建视图/表

根本对策：在 her 数据库创建必要的 discovery 表
```

### 架构分析

**数据库分布**：
- `her`: 主数据库（profiles, user_personas 等）
- `her_discovery`: Discovery 独立数据库（discovery_agent_sessions 等）
- `her_auth`: 认证数据库
- `her_recommendation`: 推荐数据库

**问题**：
- `session_end_processor` 代码优先使用 `HER_PERSONA_DB`（指向 her）
- 但 discovery 表在 `her_discovery`
- 导致跨库查询失败

## 解决方案

### 方案选择

**方案1**：修改代码，让 discovery 查询只用 `PARTNER_DISCOVERY_DB`
- ❌ 缺点：需要修改多处代码，且 fallback 逻辑有其合理性

**方案2**：在 her 数据库创建必要的 discovery 表
- ✅ 优点：无需修改代码，保持架构清晰
- ✅ 优点：符合数据库分库设计，her 只存主数据

**选择方案2**：在 her 数据库创建必要的 discovery 表

### 实施步骤

#### 1. 创建 discovery_agent_session_memory_items 表

```sql
CREATE TABLE IF NOT EXISTS discovery_agent_session_memory_items (
    item_id BIGINT NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(191) NOT NULL,
    item_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (item_id),
    INDEX idx_discovery_agent_memory_session_item (session_id, item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 2. 创建 discovery_agent_sessions 表

```sql
CREATE TABLE IF NOT EXISTS discovery_agent_sessions (
    session_id VARCHAR(191) NOT NULL,
    requester_id BIGINT NOT NULL,
    profile_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    phase VARCHAR(64) NOT NULL,
    state_json LONGTEXT NOT NULL,
    latest_view_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (session_id),
    INDEX idx_discovery_sessions_requester_updated (requester_id, updated_at),
    INDEX idx_discovery_sessions_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 3. 执行迁移脚本

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3306 \
MYSQL_ROOT_PASSWORD='YOUR_PASSWORD' \
python scripts/manual_migrate_discovery_tables_to_her.py
```

## 验证结果

### 表结构验证

```bash
docker exec her-mysql-1 mysql -uroot -p'PASSWORD' her -e "
SHOW TABLES LIKE 'discovery_%';
DESC discovery_agent_sessions;
DESC discovery_agent_session_memory_items;
"
```

### 日志验证

观察 gateway-public-1 日志，确认不再出现：
- `"Table 'her.discovery_agent_session_memory_items' doesn't exist"`
- `"Table 'her.discovery_agent_sessions' doesn't exist"`

## 影响评估

### 功能影响
- ✅ 会话结束处理恢复正常
- ✅ 无活动会话清理恢复正常
- ✅ 用户画像更新恢复正常

### 数据影响
- ⚠️ **注意**：her 和 her_discovery 中的 discovery 表数据是独立的
- ⚠️ 历史会话数据在 her_discovery 中，her 中为空表
- ✅ 新会话数据会同时写入两个数据库（根据代码逻辑）

## 长期改进建议

### 1. 数据库架构优化

**方案A：跨库视图**
```sql
-- 在 her 数据库创建视图，指向 her_discovery
CREATE VIEW her.discovery_agent_sessions AS
SELECT * FROM her_discovery.discovery_agent_sessions;
```

**方案B：数据同步**
- 使用 CDC 工具同步 discovery 表数据
- 确保 her 和 her_discovery 数据一致

**方案C：统一数据库**
- 将 discovery 表合并到 her 数据库
- 简化跨库查询逻辑

### 2. 代码改进

**改进 session_end_processor 数据库连接逻辑**：
```python
# 明确使用 discovery 数据库
discovery_conn = connect_db(os.environ.get("PARTNER_DISCOVERY_DB"))
# 明确使用主数据库
main_conn = connect_db(os.environ.get("HER_PERSONA_DB"))
```

### 3. 迁移自动化

**添加到数据库迁移脚本**：
- 将 discovery 表创建逻辑加入迁移文件
- 确保新环境部署时自动创建这些表

## 相关文件

- [scripts/manual_migrate_discovery_tables_to_her.py](scripts/manual_migrate_discovery_tables_to_her.py) - 迁移脚本
- [match_domain/session_end_processor.py](match_domain/session_end_processor.py) - 会话结束处理器
- [outer_system_mysql_schema.py](outer_system_mysql_schema.py) - 表结构定义

## 检查清单

部署后检查：
- [ ] her 数据库中存在 discovery_agent_sessions 表
- [ ] her 数据库中存在 discovery_agent_session_memory_items 表
- [ ] 日志中不再出现 "Table doesn't exist" 错误
- [ ] 会话结束处理正常执行
- [ ] 用户画像更新正常

定期检查：
- [ ] 监控 her 和 her_discovery 数据一致性
- [ ] 检查跨库查询性能
- [ ] 评估数据同步方案可行性

## 总结

**问题**：跨数据库查询场景缺少必要的表定义  
**解决**：在 her 数据库创建 discovery 相关表  
**影响**：会话结束处理恢复正常，无副作用  
**预防**：添加迁移脚本，确保未来部署自动创建表