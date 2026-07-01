# 实时通知问题修复验证方案

## 问题背景
A用户点击"愿意认识"B用户后，B用户必须刷新页面才能看到通知。

## 根因分析（五问法）
```
问题现象：实时通知总是失败，sent_count = 0

├─ 为什么 1: broadcast_to_profile_discovery找不到连接？
│   → 检查：_profile_connections字典中没有对应的key
│
├─ 为什么 2: 字典中为什么没有key？
│   → 检查：用户B的SSE连接已经建立了，key应该在字典中
│
├─ 为什么 3: 为什么查找失败？
│   → 检查：字典查找是严格类型匹配，123 != "123"
│   → 发现：推送时发送的是int类型，连接管理使用的是str类型
│
├─ 为什么 4: 为什么会有类型不匹配？
│   → 推送端：case.get("candidate_id") 返回int（数据库字段）
│   → SSE连接端：request.query.get("profile_id") 返回str（URL参数）
│   → SSE Server：没有类型转换，直接使用data.get("profile_id")
│
└─ 为什么 5: 【根本原因】类型不一致导致字典查找失败
    → 推送payload: {"profile_id": 123} (int)
    → SSE连接key: "123" (str)
    → Python字典查找: dict.get(123) 找不到 "123"
    → 结果: sent_count = 0，推送失败
```

## 三层问题叠加
1. **SSE连接管理策略**：每个用户只能有一个连接，刷新页面时连接断开
2. **前端缓存策略**：依赖sessionId变化才重新获取数据，不感知数据库变化
3. **推送顺序问题**：SSE推送和数据库写入同时进行，但都没有触发前端更新

## 修复内容

### 修复1：类型不匹配问题（最严重）
**文件**: `proxy_intro_core.py:1082-1100`
**修改**:
```python
# ✅ 统一转换为字符串类型
target_profile_id = str(case.get("candidate_id") or "")
source_profile_id = str(case.get("requester_id") or "")

payload = {
    "profile_id": target_profile_id,  # ✅ 字符串类型
    "source_profile_id": source_profile_id,  # ✅ 字符串类型
}
```

### 修复2：调整推送顺序
**文件**: `proxy_intro_routes.py:366-429`
**新流程**:
```
Step 1: create_match_case（创建案件）
Step 2: _push_proxy_intro_to_discovery_timeline（写入数据库）
Step 3: dispatch_match_case_outreach（更新状态）
Step 4: _push_passive_recommendation_notification（推送SSE通知）
```

### 修复3：增强推送结果检查
**文件**: `proxy_intro_routes.py:151-365`
**修改**:
- 函数返回值从 `None` 改为 `bool`
- 记录详细的推送结果日志（sent_count、online_sessions）

### 修复4：增强日志记录
**文件**: `proxy_intro_core.py:1102-1125`
**新增**:
```python
result = response.json()
sent_count = result.get("pushed", 0)
online_sessions = result.get("online_sessions", [])
logger.info(
    f"[SSE Push] 推送完成: sent_count={sent_count}, online_sessions={online_sessions}"
)
```

## 验证步骤

### 1. 单元测试：类型匹配验证
```python
# 测试类型转换是否正确
def test_profile_id_type_conversion():
    case = {"candidate_id": 123, "requester_id": 456}
    target = str(case.get("candidate_id") or "")
    source = str(case.get("requester_id") or "")

    assert target == "123"  # 字符串
    assert source == "456"  # 字符串
    assert isinstance(target, str)
    assert isinstance(source, str)
```

### 2. 集成测试：完整推送流程验证

#### 场景1：用户在线，SSE连接正常
**步骤**:
1. 用户B打开Discovery页面，建立SSE连接
2. 检查SSE连接管理器：`_profile_connections["123"]` 应存在
3. 用户A点击"愿意认识"
4. 检查推送日志：
   - `[SSE Push] 推送完成: sent_count=1, online_sessions=[...]`
   - `【推送顺序优化】timeline已写入`
   - `【推送顺序优化】SSE通知已发送`
5. 检查用户B的Discovery页面：应该立即显示"有人想认识你"卡片

**预期结果**:
- ✅ SSE推送成功（sent_count = 1）
- ✅ timeline已更新
- ✅ 前端立即显示通知（无需刷新）

#### 场景2：用户离线，无SSE连接
**步骤**:
1. 用户B关闭Discovery页面
2. 检查SSE连接管理器：`_profile_connections` 应为空
3. 用户A点击"愿意认识"
4. 检查推送日志：
   - `[SSE Push] 用户不在线，推送失败: sent_count=0`
   - `【推送顺序优化】timeline已写入`
5. 用户B打开Discovery页面
6. 检查兜底机制：`_check_and_push_proxy_intro_cases` 应跳过（已推送）
7. 检查timeline：应该显示"有人想认识你"卡片（从数据库读取）

**预期结果**:
- ✅ SSE推送失败（sent_count = 0）
- ✅ timeline已写入数据库
- ✅ 用户刷新页面后能看到通知

#### 场景3：用户刷新页面时推送
**步骤**:
1. 用户B打开Discovery页面，建立SSE连接（profile_id="123")
2. 用户B刷新页面（旧连接被删除，新连接建立）
3. 在刷新间隙期，用户A点击"愿意认识"
4. 检查推送日志：
   - 可能失败（sent_count = 0）或成功（sent_count = 1）
5. 无论推送是否成功，检查timeline是否已写入
6. 用户B页面刷新完成，检查是否显示通知

**预期结果**:
- ✅ timeline已写入（总是成功）
- ✅ 用户刷新后能看到通知

### 3. 日志分析验证

#### 检查关键日志点
```bash
# 检查推送流程日志
grep "【推送顺序优化】" logs/*.log

# 检查SSE推送结果
grep "[SSE Push]" logs/*.log | grep "sent_count"

# 检查类型转换
grep "profile_id.*str" logs/*.log
```

#### 验证日志内容
- ✅ `target_profile_id` 和 `source_profile_id` 都是字符串
- ✅ `sent_count` 有明确的数值（0或1）
- ✅ `online_sessions` 显示用户在线状态
- ✅ 推送顺序：timeline写入 → SSE通知发送

### 4. 前端监听验证

#### 检查SSE事件监听
```javascript
// 在前端console中检查
console.log('[Discovery SSE] Connected:', event.data)
console.log('[Discovery SSE] 新推荐卡片:', data)

// 检查事件处理
if (data.type === 'new_recommendation') {
  console.log('收到新推荐通知，开始刷新列表')
  fetchRecommendationCards(profileId)
}
```

#### 验证前端行为
- ✅ SSE连接建立成功
- ✅ 收到 `new_recommendation` 事件
- ✅ 自动调用 `fetchRecommendationCards`
- ✅ 无需刷新页面就能看到通知

## 回滚方案

如果修复后出现问题，可以回滚：

### 回滚修改
```bash
# 回滚proxy_intro_core.py
git checkout HEAD~1 external-systems/partner-matchmaking-system/matchmaking_system/proxy_intro_core.py

# 回滚proxy_intro_routes.py
git checkout HEAD~1 external-systems/partner-http-gateway/gateway/proxy_intro_routes.py
```

### 临时禁用新逻辑
如果需要快速禁用，可以在 `rest_proxy_intro_create_request` 中注释掉新逻辑：
```python
# # Step 2: 先推送被动推荐到discovery timeline（数据库写入）
# timeline_push_success = False
# try:
#     _push_proxy_intro_to_discovery_timeline(...)
# ...
```

## 监控指标

### 关键指标
1. **SSE推送成功率**: `sent_count > 0` 的比例
2. **timeline写入成功率**: `_push_proxy_intro_to_discovery_timeline` 返回True的比例
3. **用户刷新后可见性**: 用户刷新页面后是否能看到通知
4. **推送延迟**: 从A点击到B看到通知的时间

### 监控方法
```python
# 在日志中统计
import re

# 统计SSE推送成功和失败次数
success_count = len(re.findall(r'sent_count=[1-9]', logs))
failure_count = len(re.findall(r'sent_count=0', logs))

# 统计timeline写入成功率
timeline_success = len(re.findall(r'【推送成功】案件已标记', logs))
timeline_failure = len(re.findall(r'【推送失败】', logs))

print(f"SSE推送成功率: {success_count/(success_count+failure_count):.2%}")
print(f"Timeline写入成功率: {timeline_success/(timeline_success+timeline_failure):.2%}")
```

## 总结

通过修复类型不匹配、调整推送顺序、增强结果检查和日志记录，解决了实时通知总是失败的问题。现在：

1. **SSE推送可能成功或失败**（取决于用户是否在线）
2. **数据库总是先写入成功**（确保数据持久化）
3. **用户在线时能实时看到通知**（SSE推送成功）
4. **用户刷新页面后也能看到通知**（从数据库读取timeline）
5. **日志详细记录推送全链路**（便于诊断问题）

核心改进：从"推送失败就看不到"变为"推送失败也能看到（刷新页面）"，用户体验大幅提升。