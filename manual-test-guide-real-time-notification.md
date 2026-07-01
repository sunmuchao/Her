# 手动测试指南：实时通知推送完整验证

## 测试准备

### 1. 确认修复已部署

检查以下文件的修改是否已部署：
- `external-systems/partner-matchmaking-system/matchmaking_system/proxy_intro_core.py`
- `external-systems/partner-http-gateway/gateway/proxy_intro_routes.py`

关键修改点：
```python
# proxy_intro_core.py: 类型转换
target_profile_id = str(case.get("candidate_id") or "")  # ✅ 字符串

# proxy_intro_routes.py: 推送顺序
# Step 2: timeline写入（先执行）
# Step 4: SSE推送（后执行）
```

### 2. 准备测试环境

**启动服务**：
```bash
# 1. 启动SSE Server
cd external-systems/sse-server
python -m sse_server

# 2. 启动HTTP Gateway
cd external-systems/partner-http-gateway
python -m gateway

# 3. 启动Discovery Service
cd external-systems/partner-discovery-system
python -m discovery_system

# 4. 启动Matchmaking Service
cd external-systems/partner-matchmaking-system
python -m matchmaking_system
```

**检查服务状态**：
```bash
curl http://localhost:8081/health  # SSE Server
curl http://localhost:8080/health  # HTTP Gateway
```

### 3. 准备测试用户

创建两个测试用户：
- **用户A**（发起方）：profile_id = 456
- **用户B**（接收方）：profile_id = 123

---

## 测试场景

### 场景1：用户在线，SSE连接正常（最理想情况）

**目标**：验证实时推送成功，B用户立即看到通知

#### 步骤：

1. **用户B打开Discovery页面**
   ```bash
   # 打开前端页面
   open http://localhost:3000/discovery?profile_id=123
   ```

2. **检查SSE连接建立**
   - 前端console查看：
     ```javascript
     console.log('[Discovery SSE] Connected:', event.data)
     ```
   - 后端日志查看：
     ```bash
     grep "[Discovery SSE] Connection request" logs/sse_server.log
     grep "profile=123" logs/sse_server.log
     ```
   - SSE Server统计：
     ```bash
     curl http://localhost:8081/stats
     # 应该看到 profile_id=123 在连接列表中
     ```

3. **用户A点击"愿意认识"**
   - 在用户A的推荐详情页点击"愿意认识"按钮
   - 或者直接调用API：
     ```bash
     curl -X POST http://localhost:8080/v1/proxy-intro/requests \
       -H "Content-Type: application/json" \
       -d '{
         "subscription_id": "subscription-456",
         "candidate_id": 123
       }'
     ```

4. **检查推送日志**
   ```bash
   # 检查推送顺序日志
   grep "【推送顺序优化】" logs/gateway.log

   # 检查SSE推送结果
   grep "[SSE Push]" logs/matchmaking.log | grep "profile=123"

   # 应该看到：
   # ✅ sent_count=1（推送成功）
   # ✅ online_sessions=['session-xxx']
   ```

5. **验证B用户页面**
   - **前端console检查**：
     ```javascript
     console.log('[Discovery SSE] 新推荐卡片:', data)
     ```
   - **页面显示**：应该立即显示"有人想认识你"卡片
   - **无需刷新页面**

#### 验证点：
- ✅ SSE连接建立成功（profile_id="123"字符串key）
- ✅ timeline写入成功（先执行）
- ✅ SSE推送成功（sent_count=1，后执行）
- ✅ B用户立即看到通知（实时推送生效）
- ✅ 推送顺序正确（timeline → SSE）
- ✅ 类型匹配成功（字符串key找到连接）

---

### 场景2：用户离线，无SSE连接（兜底测试）

**目标**：验证推送失败时，数据已写入，用户刷新后能看到

#### 步骤：

1. **用户B关闭Discovery页面**
   - 关闭浏览器标签页
   - 或者导航到其他页面

2. **检查SSE连接断开**
   ```bash
   curl http://localhost:8081/stats
   # 应该看不到 profile_id=123 在连接列表中
   ```

3. **用户A点击"愿意认识"**
   - 同场景1步骤3

4. **检查推送日志**
   ```bash
   # 检查SSE推送失败
   grep "[SSE Push]" logs/matchmaking.log | grep "profile=123"

   # 应该看到：
   # ⚠️ sent_count=0（推送失败，用户不在线）
   # ⚠️ online_sessions=[]
   # ✅ 【推送顺序优化】timeline已写入（数据持久化成功）
   ```

5. **用户B打开Discovery页面**
   - 打开页面：`http://localhost:3000/discovery?profile_id=123`
   - **不刷新页面**，直接打开

6. **验证B用户页面**
   - 应该立即显示"有人想认识你"卡片
   - 原因：timeline已写入数据库，页面打开时从数据库读取

#### 验证点：
- ✅ SSE推送失败（sent_count=0，用户不在线）
- ✅ timeline写入成功（数据持久化）
- ✅ B用户刷新页面后能看到通知
- ✅ 兜底机制生效（用户打开页面时读取timeline）

---

### 场景3：用户刷新页面时推送（边界情况）

**目标**：验证刷新间隙期推送的处理

#### 步骤：

1. **用户B打开Discovery页面**
   - 建立SSE连接（profile_id="123")

2. **准备刷新页面**
   - 但不要立即刷新

3. **用户A点击"愿意认识"**
   - 在用户B刷新页面的瞬间点击

4. **检查推送日志**
   ```bash
   grep "[SSE Push]" logs/matchmaking.log | grep "profile=123"
   # 可能看到：
   # - sent_count=1（推送成功，连接还没断开）
   # - 或 sent_count=0（推送失败，连接已断开）
   ```

5. **用户B刷新页面**
   - 刷新浏览器

6. **验证B用户页面**
   - 无论推送是否成功，刷新后都应该看到"有人想认识你"卡片
   - 原因：timeline已写入数据库

#### 验证点：
- ✅ timeline写入成功（总是成功）
- ✅ SSE推送可能成功或失败（取决于时机）
- ✅ 用户刷新后总能看到通知（数据已持久化）

---

### 场景4：多标签页场景（复杂情况）

**目标**：验证用户打开多个Discovery页面的处理

#### 步骤：

1. **用户B打开多个Discovery标签页**
   ```bash
   # 标签页1
   open http://localhost:3000/discovery?profile_id=123&session=session-1

   # 标签页2
   open http://localhost:3000/discovery?profile_id=123&session=session-2
   ```

2. **检查SSE连接**
   ```bash
   curl http://localhost:8081/stats
   # 注意：当前实现只支持一个连接，旧连接会被替换
   # 应该只看到一个 profile_id=123 的连接
   ```

3. **用户A点击"愿意认识"**

4. **检查推送结果**
   - 只有最新的标签页能收到推送（sent_count=1）
   - 其他标签页看不到实时通知

5. **验证所有标签页**
   - 刷新所有标签页，都应该看到"有人想认识你"卡片
   - 原因：timeline已写入数据库

#### 验证点：
- ⚠️ SSE连接管理限制（每个用户只能有一个连接）
- ✅ timeline写入成功（数据持久化）
- ✅ 所有标签页刷新后都能看到通知

---

## 自动化验证

### 运行端到端测试脚本

```bash
cd scripts
python test_real_time_notification_e2e.py
```

**检查测试结果**：
```bash
cat test_real_time_notification_e2e_results.json
```

**预期结果**：
- ✅ 所有测试通过（passed=7, failed=0）
- ✅ 类型转换验证通过
- ✅ 推送顺序验证通过
- ✅ SSE推送结果验证通过
- ✅ 字典key匹配验证通过
- ✅ 完整流程验证通过

---

## 日志分析

### 关键日志点

#### 1. 类型转换日志
```bash
grep "类型转换" logs/*.log
grep "profile_id.*字符串" logs/*.log
```

#### 2. 推送顺序日志
```bash
grep "【推送顺序优化】" logs/*.log
```

**预期输出**：
```
【推送顺序优化】timeline已写入: case_id=xxx
【推送顺序优化】SSE通知已发送: case_id=xxx
```

#### 3. SSE推送结果日志
```bash
grep "[SSE Push]" logs/*.log | grep "sent_count"
```

**预期输出**：
```
[SSE Push] 推送完成: sent_count=1, online_sessions=['session-xxx']
[SSE Push] 用户不在线，推送失败: sent_count=0
```

#### 4. timeline写入日志
```bash
grep "【推送成功】" logs/*.log
```

**预期输出**：
```
【推送成功】timeline已更新: session_id=xxx
【推送成功】案件已标记: case_id=xxx, discovery_pushed=True
```

### 日志分析脚本

```bash
#!/bin/bash
# 分析推送成功率

echo "=== 推送成功率分析 ==="

# SSE推送成功次数
success=$(grep "sent_count=1" logs/*.log | wc -l)
echo "SSE推送成功次数: $success"

# SSE推送失败次数
failure=$(grep "sent_count=0" logs/*.log | wc -l)
echo "SSE推送失败次数: $failure"

# 计算成功率
if [ $success -gt 0 ] || [ $failure -gt 0 ]; then
  total=$((success + failure))
  rate=$((success * 100 / total))
  echo "推送成功率: $rate%"
else
  echo "未找到推送日志"
fi

echo "=== timeline写入成功率 ==="

# timeline写入成功次数
timeline_success=$(grep "【推送成功】timeline已更新" logs/*.log | wc -l)
echo "timeline写入成功次数: $timeline_success"

# timeline写入失败次数
timeline_failure=$(grep "【推送失败】" logs/*.log | wc -l)
echo "timeline写入失败次数: $timeline_failure"

if [ $timeline_success -gt 0 ] || [ $timeline_failure -gt 0 ]; then
  timeline_total=$((timeline_success + timeline_failure))
  timeline_rate=$((timeline_success * 100 / timeline_total))
  echo "timeline写入成功率: $timeline_rate%"
else
  echo "未找到timeline日志"
fi
```

---

## 验证检查清单

### ✅ 修复验证清单

- [ ] **类型转换验证**
  - [ ] `target_profile_id` 是字符串类型
  - [ ] `source_profile_id` 是字符串类型
  - [ ] payload中所有ID字段都是字符串

- [ ] **推送顺序验证**
  - [ ] timeline写入在SSE推送之前
  - [ ] 日志显示"【推送顺序优化】timeline已写入"
  - [ ] 日志显示"【推送顺序优化】SSE通知已发送"

- [ ] **SSE推送验证**
  - [ ] 用户在线时sent_count=1
  - [ ] 用户离线时sent_count=0
  - [ ] 日志记录online_sessions列表

- [ ] **数据持久化验证**
  - [ ] timeline写入总是成功
  - [ ] 用户刷新页面后能看到通知
  - [ ] 兜底机制生效

- [ ] **前端监听验证**
  - [ ] SSE连接建立成功
  - [ ] 收到new_recommendation事件
  - [ ] 自动调用fetchRecommendationCards

- [ ] **字典key匹配验证**
  - [ ] SSE连接key是字符串类型
  - [ ] 推送payload中profile_id是字符串类型
  - [ ] 字典查找成功（sent_count>0）

---

## 常见问题排查

### 问题1：SSE推送总是失败（sent_count=0）

**排查步骤**：
1. 检查SSE连接是否建立：
   ```bash
   curl http://localhost:8081/stats
   ```

2. 检查profile_id类型：
   ```bash
   grep "profile_id.*123" logs/*.log
   # 应该看到字符串 "123"，不是数字 123
   ```

3. 检查SSE Server URL配置：
   ```bash
   grep "SSE_SERVER_URL" logs/*.log
   ```

### 问题2：用户刷新页面后看不到通知

**排查步骤**：
1. 检查timeline是否写入：
   ```bash
   grep "【推送成功】timeline已更新" logs/*.log
   ```

2. 检查案件是否标记：
   ```bash
   grep "discovery_pushed=True" logs/*.log
   ```

3. 检查兜底机制：
   ```bash
   grep "_check_and_push_proxy_intro_cases" logs/*.log
   ```

### 问题3：多标签页只有最新标签页收到通知

**原因**：当前实现限制每个用户只能有一个SSE连接

**排查**：
```bash
curl http://localhost:8081/stats
# 应该只看到一个 profile_id=123 的连接
```

**临时方案**：刷新其他标签页（从数据库读取timeline）

---

## 测试总结

### 预期结果

| 场景 | SSE推送 | timeline写入 | 用户可见性 |
|------|---------|-------------|-----------|
| 用户在线 | ✅ 成功（sent_count=1） | ✅ 成功 | ✅ 立即看到（无需刷新） |
| 用户离线 | ❌ 失败（sent_count=0） | ✅ 成功 | ✅ 刷新后看到 |
| 刷新间隙 | 可能成功或失败 | ✅ 成功 | ✅ 刷新后看到 |
| 多标签页 | 只有最新标签收到 | ✅ 成功 | ✅ 所有标签刷新后看到 |

### 核心改进

**修复前**：
- SSE推送失败 → 用户看不到 → 必须刷新页面

**修复后**：
- SSE推送成功 → 用户立即看到（实时通知）
- SSE推送失败 → 用户刷新后看到（数据持久化）

**用户体验提升**：
- 从"推送失败就看不到"变为"推送失败也能看到（刷新页面）"

---

## 附录：测试数据准备

### 创建测试用户

```python
# 使用Python脚本创建测试用户
from datetime import datetime
import json

# 用户A（发起方）
user_a = {
    "profile_id": 456,
    "name": "测试用户A",
    "age": 25,
    "city": "北京",
    "gender": "male",
}

# 用户B（接收方）
user_b = {
    "profile_id": 123,
    "name": "测试用户B",
    "age": 23,
    "city": "上海",
    "gender": "female",
}

# 保存到数据库
# ...（根据实际数据库操作）
```

### 创建测试推荐

```python
# 创建推荐关系
recommendation = {
    "subscription_id": "subscription-456",
    "requester_id": 456,  # 用户A
    "candidate_id": 123,  # 用户B
    "recommendation_id": "rec-001",
}

# 保存到数据库
# ...（根据实际数据库操作）
```

---

## 结语

通过本测试指南，你可以完整验证实时通知推送的所有场景。如果遇到问题，请参考常见问题排查章节，或者查看详细的端到端测试脚本。

测试完成后，请将测试结果保存到JSON文件，以便后续分析和优化。