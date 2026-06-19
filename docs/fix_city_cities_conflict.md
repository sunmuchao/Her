# 修复记录：city/cities 字段冲突问题

## 修复日期
2026-06-13

## 修复问题
**问题1：city 和 cities 字段处理不一致**

### 问题表现
- 用户传入 `city: "北京"` → 结果：`{cities: ["北京"], city: "北京"}` ← city 没被清理
- 用户第二次传入 `cities: ["上海"]` → 结果：`{cities: ["上海"], city: "北京"}` ← 旧的 city 还存在
- 用户同时传入 `city` 和 `cities` → 结果：两个字段都存在

### 问题根因
`merge_working_criteria` 函数：
- 第209行：`merged.update(incoming)` 只覆盖，不清理旧字段
- 第210-213行：只有当 `cities` 不存在时才清理 `city`
- 导致新旧条件冲突，数据结构不一致

## 修复方案

### 修复代码
**文件**：[match_domain/profile_write_guard.py](../match_domain/profile_write_guard.py)

**修复点**：
1. 第204-205行：如果用户传了 `cities`，就清理旧的 `city` 字段
2. 第218-219行：最终返回前，确保 `city` 字段被清理

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

## 验证结果

### 测试场景
```python
场景1：用户第一次传入 city='北京'
结果：{'cities': ['北京']}  ← ✅ city 已清理

场景2：用户第二次传入 cities=['上海']
结果：{'cities': ['上海']}  ← ✅ city 已清理，cities 已更新

场景3：用户同时传入 city='北京' 和 cities=['上海']
结果：{'cities': ['上海']}  ← ✅ 只有一个字段

场景4：真实对话（逐步调整条件）
结果：{'cities': ['上海'], 'age_min': 26, 'age_max': 30}  ← ✅ city 已清理
```

### 测试文件
- [tests/test_merge_working_criteria_bug.py](../tests/test_merge_working_criteria_bug.py)
- [tests/test_merge_working_criteria_fix.py](../tests/test_merge_working_criteria_fix.py)

## 修复效果

### 修复前
```
❌ 场景1：{'cities': ['北京'], 'city': '北京'}
❌ 场景2：{'cities': ['上海'], 'city': '北京'}
❌ 场景3：{'city': '北京', 'cities': ['上海']}
❌ 场景4：city 像幽灵一直存在
```

### 修复后
```
✅ 场景1：{'cities': ['北京']}
✅ 场景2：{'cities': ['上海']}
✅ 场景3：{'cities': ['上海']}
✅ 场景4：{'cities': ['上海'], 'age_min': 26, 'age_max': 30}
```

## 相关文档

- [问题分析文档](sync_requester_persona_memory_issue_analysis.md)
- [分流逻辑设计讨论](split_persona_patch_design_discussion.py)

## 其他问题纠正

### 问题2纠正
**之前的误判**：以为长期偏好（`target_cities`）和搜索指令（`cities`）冲突

**正确理解**：
- 用户说"我想找北京的" → 同时触发：
  - 长期偏好：`target_cities: ["北京"]` → persona_part
  - 当前搜索：`cities: ["北京"]` → search_part
- **两个都写入，既记录偏好又立即执行，这是合理设计**

## 后续监控

### 监控指标
- 观察 `working_criteria` 中是否还有 `city` 字段残留
- 观察下游查询构建器是否仍有字段混淆
- 观察搜索结果是否符合用户最新条件

### 监控方式
- 日志分析：检查 `working_criteria` 数据结构
- 用户反馈：观察搜索结果是否符合预期
- 异常监控：观察是否有字段冲突错误日志