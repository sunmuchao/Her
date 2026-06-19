# sync_requester_persona_memory 分流逻辑问题分析与改进方案

## 一、问题总结

通过测试实验验证，发现以下问题：

### ✅ 问题1（已验证）：city/cities 处理不一致

**问题描述**：
- `split_persona_patch`：`city` → `search_part`（保持原样）
- `merge_working_criteria`：`city` → `cities`（转换成数组）
- 合并时不清理旧的 `city` 字段，导致两个字段同时存在

**实验验证**：
```python
# 场景1：用户第一次传入 city
结果：{'cities': ['北京'], 'city': '北京'}  ← city 没被清理

# 场景2：用户第二次传入 cities（不同的值）
结果：{'cities': ['上海'], 'city': '北京'}  ← 旧的 city 还存在

# 场景3：用户同时传入 city 和 cities
结果：{'city': '北京', 'cities': ['上海']}  ← 两个字段都存在
```

**影响**：
- 数据结构不一致
- 下游查询构建器可能混淆
- 搜索可能用错条件

---

### ✅ 问题2（已纠正）：长期偏好和搜索指令都要写入

**我之前的误判**：
- 误以为 `personality_traits` 在黑名单，不能参与搜索
- 误以为长期偏好（`target_cities`）和搜索指令（`cities`）冲突

**实际设计意图**：
- `personality_traits` 不在黑名单，可以正常分流到 `search_part`
- 用户说"我想找北京的" → **同时触发两个动作**：
  - 长期偏好：`target_cities: ["北京"]` → persona_part（长期记忆）
  - 当前搜索：`cities: ["北京"]` → search_part（立即搜索）
- **这是合理的设计，不是问题！**

**实验验证**：
```python
is_search_criteria_key("personality_traits") → True  ← 不在黑名单
split_persona_patch({"personality_traits": ["内向"]}) → search_part ← 正常分流
```

**结论**：这不是 BUG，是我理解偏差。

---

### ✅ 问题3（已展开）：分流逻辑设计理念

**分流逻辑的6个判断分支**：

| 优先级 | 判断条件 | 分流目标 | 设计意图 |
|--------|---------|---------|---------|
| 1 | `profile_id/user_key` | persona_part | 数据归属标识符 |
| 2 | `_WRITABLE_PROFILE_COLUMNS` | profile_part | 可直接写入的字段 |
| 3 | `_PERSONA_SELF_TO_PROFILE` | profile_part | self_ 字段映射 |
| 4 | `is_search_criteria_key()` | search_part | 搜索条件（黑名单排除） |
| 5 | `COLLECTED_PERSONA_FIELDS` 或 `target_/self_` | persona_part | 偏好白名单 |
| 6 | 兜底 | persona_part | 所有其他字段 |

**核心设计理念**：三层分离架构
- `profile_part`：用户资料层（需要确认）
- `persona_part`：偏好画像层（直接写入）
- `search_part`：搜索条件层（黑名单排除）

**Agent Native 原则**：
- Prompt 表达字段语义
- Agent 自主判断意图
- 工具层只做数据分流（不做业务判断）

---

### ✅ 问题4（确认重复）：和问题1相同

问题4描述的"数据结构不干净"本质上是问题1的表现形式，已合并处理。

---

## 二、改进方案

### 修复问题1：统一 city/cities 处理

**修复代码（已应用到 profile_write_guard.py）**：

```python
def merge_working_criteria(
    session_state: Mapping[str, Any] | None,
    criteria: Mapping[str, Any] | None,
) -> dict[str, Any]:
    working = dict((session_state or {}).get("working_criteria") or {})
    incoming = dict(criteria or {})

    # ✅ 修复：如果用户传了 cities，就清理旧的 city 字段
    if "cities" in incoming:
        working.pop("city", None)

    for key, value in incoming.items():
        if is_search_criteria_key(key) and value not in (None, "", [], {}):
            if key == "city" and "cities" not in incoming:
                working["cities"] = [value] if not isinstance(value, list) else value
            else:
                working[key] = value

    merged = dict(working)
    merged.update(incoming)

    # ✅ 修复：确保最终结果中 city 字段被清理
    if "cities" in merged:
        merged.pop("city", None)

    if "city" in merged and "cities" not in merged:
        city = merged.pop("city", None)
        if city not in (None, "", [], {}):
            merged["cities"] = [city] if not isinstance(city, list) else city

    return merged
```

**验证结果（已修复）**：

```python
场景1：用户第一次传入 city='北京'
结果：{'cities': ['北京']}  ← ✅ city 已清理（修复前：city 也存在）

场景2：用户第二次传入 cities=['上海']
结果：{'cities': ['上海']}  ← ✅ city 已清理，cities 已更新（修复前：旧的 city 还存在）

场景3：用户同时传入 city='北京' 和 cities=['上海']
结果：{'cities': ['上海']}  ← ✅ 只有一个字段（修复前：两个字段都存在）

场景4：真实对话
结果：{'cities': ['上海'], 'age_min': 26, 'age_max': 30}  ← ✅ city 已清理（修复前：city 像幽灵一直存在）
```

**修复状态**：
- ✅ 已应用到 [profile_write_guard.py](match_domain/profile_write_guard.py)
- ✅ 所有测试场景验证通过
- ✅ 数据结构一致，不再有 city/cities 冲突

---

## 三、大白话总结

### 核心问题：city 和 cities 打架

**就像新旧票都在口袋里：**
- 用户说"帮我搜北京的" → 系统拿了两张票：`city="北京"` 和 `cities=["北京"]`
- 用户说"改成上海的" → 系统拿了三张票：`city="北京"`、旧的 `cities=["北京"]`、新的 `cities=["上海"]`
- **容易搞混，不知道用哪张票搜索**

### 修复方案：换新票扔旧票（已实施）

**修复前（有 BUG）：**
- 用户说"帮我搜北京的" → 系统拿了两张票：`city="北京"` 和 `cities=["北京"]`
- 用户说"改成上海的" → 系统拿了三张票：`city="北京"`、旧的 `cities=["北京"]`、新的 `cities=["上海"]`
- **容易搞混，不知道用哪张票搜索**

**修复后（已修复）：**
- 用户说"帮我搜北京的" → 只拿一张票：`cities=["北京"]`（city 已扔掉）
- 用户说"改成上海的" → 只拿一张票：`cities=["上海"]`（旧的已扔掉）
- **口袋里永远只有一张票，不会搞混**

**修复状态**：✅ 已应用到代码，所有测试通过

---

## 四、Agent Native 设计理念

### 为什么分流逻辑这么复杂？

**传统设计**：代码硬编码字段映射
- `city` → 搜索条件
- `target_cities` → 偏好
- 规则引擎决定

**Agent Native 设计**：Prompt 表达，Agent 自主判断
- 用户说"帮我搜北京的" → Agent 用 `cities`
- 用户说"我长期偏好北京" → Agent 用 `target_cities`
- 工具层只做分流，不判断意图

**优势**：
- 更灵活的意图理解
- 支持非标准字段（如"我喜欢吃辣"）
- Agent 自主决策

---

## 五、修复完成状态

| 任务 | 状态 | 说明 |
|------|------|------|
| ✅ **修复 merge_working_criteria** | 已完成 | 已应用到 [profile_write_guard.py](match_domain/profile_write_guard.py) |
| ✅ **补充文档** | 已完成 | 已说明分流逻辑的优先级和设计意图 |
| ✅ **测试验证** | 已完成 | 所有测试场景验证通过 |
| 🔄 **监控观察** | 待部署 | 部署后观察 city/cities 冲突是否消失 |

**修复总结**：
- ✅ 问题1（city/cities 不一致）：已修复并验证通过
- ✅ 问题2（长期偏好和搜索指令）：不是问题，是合理设计
- ✅ 问题3（分流逻辑）：已补充文档说明
- ✅ 问题4（数据结构不干净）：和问题1重复，已合并处理