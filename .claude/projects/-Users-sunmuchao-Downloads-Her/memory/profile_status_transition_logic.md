---
name: profile-status-transition-logic
description: 档案状态（profile_status）转换逻辑梳理：active、matched、paused、archived四种状态的定义、转换机制和业务场景
metadata:
  type: project
---

# 档案状态转换逻辑

## 状态定义

**profile_status** 是用户档案的整体状态，表示用户是否想找对象。

### 四种状态

| 状态 | 中文 | 含义 | 搜索可见性 |
|------|------|------|------------|
| active | 活跃 | 正在找对象 | ✅ 默认搜索包含 |
| matched | 已匹配 | 已经有对象了 | ❌ 不参与搜索 |
| paused | 暂停 | 暂时不想找 | ❌ 不参与搜索 |
| archived | 归档 | 不再找对象了 | ❌ 不参与搜索 |

---

## 状态转换逻辑

### ⚠️ 重要发现

**代码中没有自动状态转换逻辑！**

profile_status 主要依赖用户手动操作，不是系统自动管理的事件状态。

---

### 转换路径

```
注册 → active（默认）
          ↓
    [用户点击暂停] → paused
          ↓
    [用户点击恢复] → active
          
    [用户匹配成功] → matched（推测需手动）
          ↓
    [匹配关系结束] → active
          
    [长期不登录] → archived（推测）
          
    [违规被封] → archived（管理员操作）
```

---

### 各状态详细转换

#### ✅ active（活跃）

**何时设置**
- 用户注册时自动设置为 active（代码：profile_service/api.py:899）
- 用户恢复档案时手动改为 active
- 匹配关系结束后用户改为 active

**何时退出**
- 用户点击"暂停" → 变成 paused
- 用户匹配成功 → 变成 matched（推测需要手动或自动）
- 用户长期不来 → 变成 archived（推测）

---

#### ✅ matched（已匹配）

**何时设置**
- 用户和某人匹配成功后改为 matched
- **注意**：代码中没有找到自动转换逻辑，可能是手动操作

**何时退出**
- 匹配关系结束（分手/取消）→ 改回 active

---

#### ✅ paused（暂停）

**何时设置**
- 用户点击"暂停档案"按钮
- 用户工作忙、心情不好、不想找对象时手动暂停

**何时退出**
- 用户点击"恢复档案" → 改回 active

---

#### ✅ archived（归档）

**何时设置**
- 用户注销账号
- 用户长期不登录（推测：超过90天/180天）
- 用户违规被封禁

**何时退出**
- 通常不会退出归档状态
- 归档是最终状态，数据保留但不再展示

---

## 两套不同的状态系统

### RelationStatus（推荐关系状态）- 有复杂转换逻辑

**位置**：match_domain/model.py, match_domain/ledger.py

**定义**：用户A对用户B的态度

**状态流转**：
```
NEW → RECOMMENDED → SAVED/SKIPPED → COOLING → 
PROXY_INTRO_ACTIVE → MATCHED → CLOSED
```

**转换逻辑**：明确的事件驱动转换
- 系统推荐候选人 → RECOMMENDED
- 用户保存候选人 → SAVED
- 用户跳过候选人 → SKIPPED
- 冷却期 → COOLING
- 红娘介入 → PROXY_INTRO_ACTIVE
- 双向匹配成功 → MATCHED
- 关系结束 → CLOSED

**代码位置**：ledger.py:15-43 (relation_status_from_row_snapshot函数)

---

### profile_status（档案状态）- 没有复杂转换逻辑

**位置**：数据库字段

**定义**：用户自己的整体状态

**状态**：active, matched, paused, archived

**转换逻辑**：主要依赖用户手动操作
- 没有明确的事件驱动转换逻辑
- 没有自动归档的定时任务
- 没有匹配成功后自动更新为 matched 的逻辑

**代码位置**：
- 创建时默认为 active：profile_service/api.py:899
- 搜索时默认只查找 active：search_sources.py:295
- 状态优先级排序：search_candidates.py:441-445

---

## 实际业务场景

### 场景1：新用户注册
用户填写资料 → profile_status 默认为 active  
→ 系统开始推荐用户给别人

### 场景2：用户找到对象（推测）
用户和小红聊天 → 双方觉得不错 → 用户手动改为 matched  
→ 系统停止推荐（专注于当前对象）  
**注意**：可能需要双方都改为 matched 才生效

### 场景3：用户工作忙
用户点击"暂停档案"按钮 → profile_status 改为 paused  
→ 系统停止推荐，档案不展示  
→ 一个月后，用户点击"恢复档案" → 改回 active

### 场景4：用户半年不来
用户长期不登录 → 推测系统自动改为 archived  
→ 档案归档，不再展示  
**注意**：代码中没有找到自动归档逻辑，可能需要手动或定时任务

### 场景5：用户违规
管理员发现用户违规 → 手动改为 archived  
→ 用户被封禁

---

## 代码证据

### 1. 注册时默认为 active
```python
# 文件：profile_service/api.py:899
if schema.column_exists(raw_conn, source_table_name, "profile_status"):
    insert_fields["profile_status"] = "active"
```

### 2. 搜索时默认只查找 active
```python
# 文件：search_sources.py:295
add_in("profile_status", criteria.get("profile_statuses") or ["active"], allow_missing=True)
```

### 3. 状态优先级用于排序
```python
# 文件：search_candidates.py:441-445
PROFILE_STATUS_ORDER = {
    "archived": 0,  # 最低优先级
    "matched": 1,
    "paused": 2,
    "active": 3,    # 最高优先级
}
```

### 4. 状态显示（修改后）
```python
# 文件：search_matching.py:64-73, 1119-1120
PROFILE_STATUS_LABELS = {
    "active": "活跃",
    "matched": "已匹配",
    "paused": "暂停",
    "archived": "归档",
}

status_label = PROFILE_STATUS_LABELS.get(profile_status, profile_status)
reasons.append(f"状态 {status_label}")
```

---

## 缺少的功能

目前代码中缺少明确的 profile_status 状态转换逻辑：

1. ❌ 缺少：匹配成功后自动更新 profile_status 为 matched
2. ❌ 缺少：长期不活跃自动归档的定时任务
3. ❌ 缺少：匹配关系结束后恢复 profile_status 为 active
4. ❌ 缺少：用户手动暂停/恢复档案的前端接口

---

## 设计推测

profile_status 是用户的"意愿状态"，不是系统的"事件状态"：

1. **用户自主权**
   - 用户是否想找对象 → 用户自己决定
   - 用户暂时不想找 → 用户自己暂停
   - 用户已经找到 → 用户自己改为 matched

2. **简单设计，避免误操作**
   - 如果自动转换，可能用户只是工作忙，系统就改成 archived 了
   - 如果匹配成功自动改为 matched，用户可能还想继续看其他人

3. **给用户自主权**
   - 用户可以控制自己的档案状态
   - 不被系统强制改变状态

---

## 为什么要有这些状态？

### active（活跃）
正常的找对象状态，大家都在用 ✅  
系统默认只搜索 active 状态的用户

### matched（已匹配）
保护用户体验！
- 避免小明和小红正在聊，系统还推新人给他，显得不专一
- 避免别人看到小明的资料，但小明已经有对象了

### paused（暂停）
给用户选择权！
- 不是每个人天天都想找对象
- 可能今天心情不好、工作太忙、想休息
- 数据不会丢，想回来随时恢复

### archived（归档）
清理不活跃用户！
- 半年没登录的人，别占着推荐位置
- 让推荐池保持干净，只推荐真正想找对象的人

---

## 总结

profile_status（档案状态）的转换逻辑：

✅ **明确的逻辑**：
- 注册时默认为 active
- 用户可以手动暂停/恢复（前端操作）

⚠️ **缺少明确逻辑**：
- 匹配成功后自动改为 matched
- 长期不活跃自动归档
- 匹配关系结束后恢复为 active

**推测原因**：
- profile_status 是用户的意愿状态，不是事件状态
- 主要依赖用户手动操作，给用户自主权
- 可能是设计选择，也可能是功能待完善

**实际效果**：
- 系统默认只推荐 active 状态的用户
- 搜索算法中状态匹配成功后显示"状态 活跃"等中文标签
- 用户可以通过前端操作暂停/恢复档案