# Discovery 多会话功能 - 端到端测试指南

## 功能概述

用户可以在 Discovery（发现页）创建新会话，同时保留已记录的用户画像信息，并支持会话历史列表功能。

## 测试环境准备

### 1. 后端环境

```bash
# 启动后端服务
cd external-systems/partner-http-gateway
python -m pytest tests/test_discovery_routes_list_sessions.py -v

# 或启动完整服务
python gateway/app.py
```

### 2. 前端环境

```bash
# 启动前端开发服务器
cd frontend/her-app
npm run dev
```

---

## 手动测试场景

### 场景 1：新建会话按钮

**目标**：验证用户可以创建新会话

**步骤**：
1. 打开 Discovery 页面（发现页）
2. 观察 header 区域，确认存在两个新按钮：
   - "历史"按钮（时钟图标）
   - "新对话"按钮（加号图标 + 文字）
3. 点击"新对话"按钮
4. **预期结果**：
   - 页面刷新，timeline 清空（只有开场消息）
   - sessionId 更新（可以通过 URL ?session=xxx 验证）
   - 红娘（小雅）知道用户之前的画像偏好

**验证方式**：
```javascript
// 浏览器控制台检查
localStorage.getItem('her.discovery.session.10001')  // 应该是新 sessionId
```

---

### 场景 2：会话历史列表

**目标**：验证用户可以查看和切换历史会话

**步骤**：
1. 点击"历史"按钮
2. **预期结果**：弹出会话列表面板
3. 验证列表显示：
   - 当前活跃会话高亮（带"当前"标签）
   - 显示会话摘要（推荐人数、最后更新时间）
   - 底部有"新建会话"按钮
4. 点击任意历史会话
5. **预期结果**：
   - 面板关闭
   - 页面加载该会话的完整 timeline
   - localStorage 更新为该 sessionId

---

### 场景 3：画像信息保留

**目标**：验证新会话创建后画像不重置

**前置条件**：用户在旧会话中已表达偏好（如"我想要30岁以下的"）

**步骤**：
1. 在旧会话中告诉红娘："我想要30岁以下的"
2. 等待红娘回复并搜索
3. 点击"新对话"创建新会话
4. 在新会话中问红娘："还记得我之前说的年龄要求吗？"
5. **预期结果**：红娘能回答"是的，你之前说想要30岁以下的"

**验证方式**：
- 检查数据库 `user_personas` 表，确认画像数据存在
- 新会话的 `profile_id` 与旧会话相同，会加载相同画像

---

### 场景 4：多会话隔离

**目标**：验证不同会话的对话内容互相隔离

**步骤**：
1. 创建会话 A，发送消息："帮我找无锡的"
2. 记住会话 A 的 sessionId
3. 点击"新对话"创建会话 B
4. 发送消息："帮我找南京的"
5. 点击"历史"，切换回会话 A
6. **预期结果**：
   - 会话 A 的 timeline 显示"帮我找无锡的"相关对话
   - 不包含"帮我找南京的"内容
7. 切换回会话 B
8. **预期结果**：
   - 会话 B 的 timeline 显示"帮我找南京的"相关对话
   - 不包含"帮我找无锡的"内容

---

### 场景 5：URL 参数切换

**目标**：验证可以通过 URL 参数直接切换会话

**步骤**：
1. 创建多个会话，记住它们的 sessionId
2. 直接修改 URL：`?session=discovery-session-xxx`
3. **预期结果**：
   - 页面加载指定会话的内容
   - localStorage 同步更新

---

## 自动化测试

### 后端单元测试

```bash
cd external-systems/partner-discovery-system
python -m pytest tests/test_multi_session.py -v
```

**测试覆盖**：
- ✅ 存储层 `list_sessions_by_profile_id()` 方法
- ✅ Service 层 `list_sessions()` 方法
- ✅ 多会话创建
- ✅ 会话列表排序
- ✅ 画像保留机制

### API 端点测试

```bash
cd external-systems/partner-http-gateway
python -m pytest tests/test_discovery_routes_list_sessions.py -v
```

**测试覆盖**：
- ✅ GET /v1/discovery/sessions 响应格式
- ✅ limit 参数处理
- ✅ 路由分发逻辑

---

## 常见问题排查

### Q1: 点击"新对话"后 timeline 没有清空

**可能原因**：
- localStorage 没有正确更新
- 前端 Hook 的 createNewSession 函数未正确调用

**排查步骤**：
```javascript
// 检查 localStorage
console.log(localStorage.getItem('her.discovery.session.10001'))

// 检查 Hook 返回值
const { sessionId, createNewSession } = useDiscoverySession()
console.log('current sessionId:', sessionId)
```

### Q2: 历史列表为空

**可能原因**：
- 后端 API 未正确返回数据
- profile_id 不匹配

**排查步骤**：
```bash
# 直接调用 API
curl "http://localhost:5000/v1/discovery/sessions?profile_id=10001"
```

### Q3: 画像信息丢失

**可能原因**：
- `user_personas` 表数据不存在
- `load_persona_for_discovery()` 未被调用

**排查步骤**：
```sql
-- 检查数据库
SELECT * FROM user_personas WHERE profile_id = 10001;
```

---

## 验收标准

| 功能 | 验收标准 |
|------|---------|
| 新建会话按钮 | 点击后 timeline 清空，sessionId 更新 |
| 历史记录按钮 | 点击后显示会话列表面板 |
| 会话列表显示 | 当前会话高亮，显示摘要信息 |
| 会话切换 | 点击切换后 timeline 正确加载 |
| 画像保留 | 新会话中红娘知道旧会话表达的偏好 |
| 会话隔离 | 不同会话的对话内容不互相包含 |
| URL 参数 | ?session=xxx 可以直接切换会话 |

---

## 测试报告模板

```
测试日期：YYYY-MM-DD
测试人员：XXX
测试环境：前端版本 / 后端版本

场景 1：新建会话按钮
- 结果：✅ 通过 / ❌ 失败
- 备注：...

场景 2：会话历史列表
- 结果：✅ 通过 / ❌ 失败
- 备注：...

场景 3：画像信息保留
- 结果：✅ 通过 / ❌ 失败
- 备注：...

场景 4：多会话隔离
- 结果：✅ 通过 / ❌ 失败
- 备注：...

场景 5：URL 参数切换
- 结果：✅ 通过 / ❌ 失败
- 备注：...

总体评价：✅ 功能可用 / ❌ 需修复
```