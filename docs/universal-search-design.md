# 搜索系统通用化改进方案

> **核心原则**：任何 Agent 传入的参数都应该被应用到搜索中
> 
> **创建日期**：2026-06-11
> 
> **状态**：待实施

---

## 一、当前问题分析

### 1.1 数据流现状

```
Agent 传参数 → criteria_compiler.py 分类 → search_sources.py 执行查询
     ↓              ↓                        ↓
  mbti_types    被扔进 soft_preferences    只看 hard_filters
     ↓              ↓                        ↓
  ✅ 正确        ⚠️ 不在 hard_keys          ❌ 完全忽略
```

### 1.2 问题案例

Agent 想搜索 "N系性格的候选人"，传了参数：

```json
{
  "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
}
```

但搜索结果全是 S系候选人（ESFJ、ISTJ、ESTJ、ISFJ），因为：
- `mbti_types` 不在 `hard_keys` 列表中
- 被归类为 `soft_preferences`
- 搜索层根本没有使用 `soft_preferences`
- 参数被完全丢弃

### 1.3 硬编码位置

| 文件 | 硬编码内容 | 影响 |
|------|-----------|------|
| `match_domain/criteria_compiler.py:201-213` | `hard_keys` 列表 | 决定哪些参数被"认真对待" |
| `partner_search/search_sources.py:275-321` | 固定字段处理逻辑 | 决定哪些参数被查询 |

---

## 二、改进目标

### 2.1 核心原则

**任何 Agent 传入的参数都应该被应用到搜索中**

这符合 **Agent Native 原则**：
- Agent 应该能自由表达搜索意图
- 工具应该执行 Agent 传的所有参数
- 不应该用代码限制 Agent 能说什么

### 2.2 具体目标

1. 移除 `hard_keys` 硬编码列表
2. 实现通用字段处理逻辑
3. 自动识别参数类型（精确匹配、范围、列表）
4. 建立参数名到数据库字段名的映射
5. 兼容现有字段，平滑迁移

---

## 三、改进方案

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     新增：FieldMapper                            │
│                     文件：match_domain/field_mapper.py           │
│                                                                 │
│  职责：参数名 → 数据库字段名映射                                   │
│                                                                 │
│  示例：                                                         │
│  cities → city                                                  │
│  age_min → age (>=)                                             │
│  mbti_types → mbti_type (IN)                                    │
│  exclude_mbti → mbti_type (NOT IN)                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     改进：UniversalQueryBuilder                  │
│           文件：match_domain/universal_query_builder.py          │
│                                                                 │
│  职责：遍历所有 criteria 参数，自动构建查询条件                     │
│                                                                 │
│  逻辑：                                                         │
│  for key, value in criteria.items():                            │
│      field_name = mapper.get_field(key)                         │
│      query_type = mapper.get_query_type(key)                    │
│      add_condition(field_name, query_type, value)               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     改进：search_sources.py                      │
│           文件：partner_search/search_sources.py                 │
│                                                                 │
│  变化：                                                         │
│  - 移除硬编码的字段处理（275-321行）                              │
│  - 改用 UniversalQueryBuilder                                   │
│  - 所有参数自动被处理                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.2 具体实现

#### Step 1：创建字段映射器

**文件**：`match_domain/field_mapper.py`

```python
"""通用字段映射器：参数名 → 数据库字段名 + 查询类型

核心职责：
1. 将 Agent 传入的参数名映射到数据库字段名
2. 确定每个参数的查询类型（精确匹配、范围、列表等）
3. 支持动态注册新字段
"""

from typing import Any

# 查询类型枚举
QUERY_TYPE_EXACT = "exact"          # 精确匹配：WHERE field = value
QUERY_TYPE_IN = "in"                # 列表匹配：WHERE field IN (values)
QUERY_TYPE_NOT_IN = "not_in"        # 排除列表：WHERE field NOT IN (values)
QUERY_TYPE_RANGE_MIN = "range_min"  # 范围下限：WHERE field >= value
QUERY_TYPE_RANGE_MAX = "range_max"  # 范围上限：WHERE field <= value
QUERY_TYPE_LIKE = "like"            # 模糊匹配：WHERE field LIKE value


# 字段映射表：参数名 → (数据库字段名, 查询类型)
#
# 设计说明：
# - 所有 Agent 可能传入的参数都应该在这里定义映射
# - 如果参数名和数据库字段名相同，可以省略映射（自动推断）
# - 新增字段只需要在这里添加一行
FIELD_MAPPING = {
    # === 基础字段 ===
    "gender": ("gender", QUERY_TYPE_EXACT),
    "cities": ("city", QUERY_TYPE_IN),
    "districts": ("district", QUERY_TYPE_IN),
    "settlement_cities": ("settlement_city", QUERY_TYPE_IN),
    "relationship_goals": ("relationship_goal", QUERY_TYPE_IN),
    
    # === 数值范围字段 ===
    # 自动识别：_min 后缀为范围下限，_max 后缀为范围上限
    "age_min": ("age", QUERY_TYPE_RANGE_MIN),
    "age_max": ("age", QUERY_TYPE_RANGE_MAX),
    "height_min": ("height", QUERY_TYPE_RANGE_MIN),
    "height_max": ("height", QUERY_TYPE_RANGE_MAX),
    
    # === 状态字段 ===
    "marital_statuses": ("marital_status", QUERY_TYPE_IN),
    "housing_statuses": ("housing_status", QUERY_TYPE_IN),
    "car_statuses": ("car_status", QUERY_TYPE_IN),
    "profile_statuses": ("profile_status", QUERY_TYPE_IN),
    "verified_levels": ("verified_level", QUERY_TYPE_IN),
    "photo_verification_levels": ("photo_verification_level", QUERY_TYPE_IN),
    
    # === MBTI 相关字段（新增）===
    # 支持按 MBTI 类型筛选
    "mbti_types": ("mbti_type", QUERY_TYPE_IN),
    # 说明：WHERE mbti_type IN ('INTP', 'INTJ', ...)
    
    # 支持排除某些 MBTI 类型
    "exclude_mbti": ("mbti_type", QUERY_TYPE_NOT_IN),
    # 说明：WHERE mbti_type NOT IN ('ESFJ', 'ISTJ', ...)
    
    # 支持按 MBTI 维度筛选（如筛选所有 N系）
    "mbti_preference": ("mbti_type", QUERY_TYPE_LIKE),
    # 说明：WHERE mbti_type LIKE '%N%'（筛选 N系）
    
    # === 依恋风格字段（新增）===
    "attachment_types": ("attachment_type", QUERY_TYPE_IN),
    "exclude_attachment": ("attachment_type", QUERY_TYPE_NOT_IN),
    
    # === 标签字段 ===
    "must_have": ("tags", QUERY_TYPE_IN),  # 注意：可能需要特殊处理 JSON 数组
    "must_not_have": ("tags", QUERY_TYPE_NOT_IN),
    
    # === 其他字段 ===
    "long_distance": ("accept_long_distance", QUERY_TYPE_EXACT),
    "accept_partner_children": ("accept_partner_children", QUERY_TYPE_EXACT),
    "want_children": ("want_children", QUERY_TYPE_EXACT),
    "marriage_timelines": ("marriage_timeline", QUERY_TYPE_IN),
    "smoking": ("smoking", QUERY_TYPE_EXACT),
    "drinking": ("drinking", QUERY_TYPE_EXACT),
}


class FieldMapper:
    """字段映射器
    
    使用方式：
    ```python
    mapper = FieldMapper()
    field = mapper.get_field("mbti_types")  # 返回 "mbti_type"
    query_type = mapper.get_query_type("mbti_types")  # 返回 "in"
    ```
    """
    
    def __init__(self, mapping: dict[str, tuple[str, str]] = None):
        self.mapping = mapping or FIELD_MAPPING
    
    def get_field(self, param_name: str) -> str | None:
        """获取数据库字段名
        
        Args:
            param_name: Agent 传入的参数名
            
        Returns:
            数据库字段名，如果未映射则尝试直接使用参数名
        """
        if param_name in self.mapping:
            return self.mapping[param_name][0]
        # 没有映射的字段，尝试直接使用参数名
        # 这样可以支持未来新增字段而不需要修改代码
        return param_name
    
    def get_query_type(self, param_name: str) -> str:
        """获取查询类型
        
        Args:
            param_name: Agent 传入的参数名
            
        Returns:
            查询类型（exact/in/not_in/range_min/range_max/like）
        """
        if param_name in self.mapping:
            return self.mapping[param_name][1]
        # 自动推断查询类型
        return self._infer_query_type(param_name)
    
    def _infer_query_type(self, param_name: str) -> str:
        """根据参数名自动推断查询类型
        
        推断规则：
        - _min 后缀 → 范围下限
        - _max 后缀 → 范围上限
        - exclude_ 前缀 → 排除列表
        - 其他 → 精确匹配
        """
        # _min 后缀 → 范围下限
        if param_name.endswith("_min"):
            return QUERY_TYPE_RANGE_MIN
        # _max 后缀 → 范围上限
        if param_name.endswith("_max"):
            return QUERY_TYPE_RANGE_MAX
        # exclude_ 前缀 → 排除列表
        if param_name.startswith("exclude_"):
            return QUERY_TYPE_NOT_IN
        # 默认：精确匹配
        return QUERY_TYPE_EXACT
    
    def register(self, param_name: str, field_name: str, query_type: str):
        """注册新字段映射
        
        用于动态添加新字段支持
        
        Args:
            param_name: Agent 传入的参数名
            field_name: 数据库字段名
            query_type: 查询类型
        """
        self.mapping[param_name] = (field_name, query_type)
    
    def get_all_mappings(self) -> dict[str, tuple[str, str]]:
        """获取所有字段映射（用于调试/展示）"""
        return dict(self.mapping)
```

---

#### Step 2：创建通用查询构建器

**文件**：`match_domain/universal_query_builder.py`

```python
"""通用查询构建器：自动处理所有 criteria 参数

核心职责：
1. 遍历 Agent 传入的所有参数
2. 根据字段映射自动构建 SQL WHERE 条件
3. 支持多种查询类型（精确、范围、列表、排除）
"""

from typing import Any
from .field_mapper import FieldMapper, QUERY_TYPE_IN, QUERY_TYPE_NOT_IN


class UniversalQueryBuilder:
    """通用查询构建器
    
    使用方式：
    ```python
    builder = UniversalQueryBuilder()
    criteria = {"cities": ["无锡"], "mbti_types": ["INTP", "INTJ"]}
    where_clause, params = builder.process_criteria(criteria)
    # where_clause: "WHERE city IN (...) AND mbti_type IN (...)"
    # params: {"param_0": "无锡", "param_1": "INTP", "param_2": "INTJ"}
    ```
    """
    
    def __init__(self, mapper: FieldMapper = None):
        self.mapper = mapper or FieldMapper()
        self.conditions: list[str] = []
        self.params: dict[str, Any] = {}
    
    def add_condition(
        self,
        param_name: str,
        value: Any,
        *,
        allow_missing: bool = True,
    ) -> bool:
        """添加查询条件
        
        Args:
            param_name: 参数名（如 "cities", "mbti_types"）
            value: 参数值
            allow_missing: 是否允许参数缺失
        
        Returns:
            是否成功添加条件
        """
        # 空值处理
        if value is None or value == "" or value == []:
            if not allow_missing:
                raise ValueError(f"Required parameter {param_name} is missing")
            return False
        
        # 获取映射信息
        field_name = self.mapper.get_field(param_name)
        if field_name is None:
            # 字段不存在于数据库，优雅降级
            # 不抛异常，只是不添加条件
            return False
        
        query_type = self.mapper.get_query_type(param_name)
        
        # 根据查询类型构建条件
        if query_type == "exact":
            self._add_exact(field_name, value)
        elif query_type == "in":
            self._add_in(field_name, value)
        elif query_type == "not_in":
            self._add_not_in(field_name, value)
        elif query_type == "range_min":
            self._add_range_min(field_name, value)
        elif query_type == "range_max":
            self._add_range_max(field_name, value)
        elif query_type == "like":
            self._add_like(field_name, value)
        else:
            # 默认精确匹配
            self._add_exact(field_name, value)
        
        return True
    
    def _add_exact(self, field: str, value: Any):
        """精确匹配：WHERE field = value"""
        param_key = f"param_{len(self.params)}"
        self.conditions.append(f"{field} = :{param_key}")
        self.params[param_key] = value
    
    def _add_in(self, field: str, value: list):
        """列表匹配：WHERE field IN (values)"""
        if not isinstance(value, (list, tuple)):
            value = [value]
        param_keys = []
        for item in value:
            param_key = f"param_{len(self.params)}"
            self.params[param_key] = item
            param_keys.append(param_key)
        placeholders = ",".join(f":{k}" for k in param_keys)
        self.conditions.append(f"{field} IN ({placeholders})")
    
    def _add_not_in(self, field: str, value: list):
        """排除列表：WHERE field NOT IN (values)"""
        if not isinstance(value, (list, tuple)):
            value = [value]
        param_keys = []
        for item in value:
            param_key = f"param_{len(self.params)}"
            self.params[param_key] = item
            param_keys.append(param_key)
        placeholders = ",".join(f":{k}" for k in param_keys)
        self.conditions.append(f"{field} NOT IN ({placeholders})")
    
    def _add_range_min(self, field: str, value: Any):
        """范围下限：WHERE field >= value"""
        param_key = f"param_{len(self.params)}"
        self.conditions.append(f"{field} >= :{param_key}")
        self.params[param_key] = value
    
    def _add_range_max(self, field: str, value: Any):
        """范围上限：WHERE field <= value"""
        param_key = f"param_{len(self.params)}"
        self.conditions.append(f"{field} <= :{param_key}")
        self.params[param_key] = value
    
    def _add_like(self, field: str, value: str):
        """模糊匹配：WHERE field LIKE value"""
        param_key = f"param_{len(self.params)}"
        self.conditions.append(f"{field} LIKE :{param_key}")
        self.params[param_key] = f"%{value}%"
    
    def build_where_clause(self) -> str:
        """构建 WHERE 子句
        
        Returns:
            WHERE 子句字符串，如果没有条件则返回空字符串
        """
        if not self.conditions:
            return ""
        return "WHERE " + " AND ".join(self.conditions)
    
    def get_params(self) -> dict[str, Any]:
        """获取查询参数
        
        Returns:
            参数字典，用于 SQL 执行时的参数绑定
        """
        return self.params
    
    def clear(self):
        """清空条件（用于重新构建新查询）"""
        self.conditions = []
        self.params = {}
    
    def process_criteria(
        self,
        criteria: dict[str, Any],
        *,
        required_fields: list[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        """处理整个 criteria
        
        这是主要入口方法，遍历所有参数自动构建查询
        
        Args:
            criteria: 所有搜索参数
            required_fields: 必须存在的字段列表（可选）
        
        Returns:
            (where_clause, params) 元组
        
        Raises:
            ValueError: 如果必需字段缺失
        """
        self.clear()
        
        # 检查必需字段
        if required_fields:
            for field in required_fields:
                if field not in criteria or criteria[field] is None:
                    raise ValueError(f"Required field '{field}' is missing")
        
        # 遍历所有参数，自动添加条件
        for param_name, value in criteria.items():
            self.add_condition(param_name, value, allow_missing=True)
        
        return self.build_where_clause(), self.get_params()
    
    def get_debug_info(self) -> dict[str, Any]:
        """获取调试信息（用于日志/排查）"""
        return {
            "conditions": self.conditions,
            "params": self.params,
            "condition_count": len(self.conditions),
        }
```

---

#### Step 3：修改 criteria_compiler.py

**文件**：`match_domain/criteria_compiler.py`

**改动位置**：第200-221行 `_split_criteria` 函数

```python
# === 改动前（硬编码）===
def _split_criteria(criteria: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    hard_keys = {
        "gender",
        "age_min",
        "age_max",
        "cities",
        # ... 更多硬编码
    }
    hard_filters: dict[str, Any] = {}
    soft_preferences: dict[str, Any] = {}
    for key, value in criteria.items():
        if key in hard_keys:
            hard_filters[key] = value
        else:
            soft_preferences[key] = value  # ← 被丢弃
    return hard_filters, soft_preferences


# === 改动后（通用）===
def _split_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    """改进：不再分割，直接返回所有 criteria
    
    设计说明：
    - 旧逻辑：分成 hard_filters 和 soft_preferences，后者被丢弃
    - 新逻辑：所有参数都应该被查询，不再区分
    
    Args:
        criteria: 所有搜索参数
        
    Returns:
        过滤后的 criteria（移除空值）
    """
    # 过滤空值，保留所有有效参数
    filtered = {
        key: value 
        for key, value in criteria.items()
        if value is not None and value != "" and value != []
    }
    return filtered


# === 同时修改 CompiledCriteria 类 ===
@dataclass
class CompiledCriteria:
    # 移除 hard_filters 和 soft_preferences
    # 改为单一的 criteria
    criteria: dict[str, Any] = field(default_factory=dict)
    self_profile: dict[str, Any] = field(default_factory=dict)
    source_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    criteria_hash: str = ""
    scene: str = ""
```

---

#### Step 4：修改 search_sources.py

**文件**：`partner_search/search_sources.py`

**改动位置**：第275-321行

```python
# === 改动前（硬编码 500+ 行）===
def build_search_conditions(criteria):
    """旧逻辑：硬编码处理每个字段"""
    conditions = []
    
    gender_values = expand_search_gender_values(criteria.get("gender"))
    add_numeric_bound("age", ">=", criteria.get("age_min"))
    add_numeric_bound("age", "<=", criteria.get("age_max"))
    add_in("city", criteria.get("cities"))
    add_in("relationship_goal", criteria.get("relationship_goals"))
    add_in("marital_status", criteria.get("marital_statuses"))
    # ... 50+ 行硬编码
    
    # ❌ 没有 mbti_types 的处理
    # ❌ 没有 exclude_mbti 的处理
    # ❌ 任何新字段都不支持
    
    return conditions


# === 改动后（通用 50 行）===
from match_domain.field_mapper import FieldMapper
from match_domain.universal_query_builder import UniversalQueryBuilder

# 全局映射器（可配置）
_field_mapper = FieldMapper()

def build_search_conditions(
    criteria: dict[str, Any],
    *,
    mapper: FieldMapper = None,
    required_fields: list[str] = None,
) -> tuple[str, dict[str, Any]]:
    """新逻辑：通用查询构建
    
    Args:
        criteria: 所有搜索参数
        mapper: 字段映射器（可选，默认使用全局映射器）
        required_fields: 必需字段列表
        
    Returns:
        (where_clause, params)
    """
    builder = UniversalQueryBuilder(mapper or _field_mapper)
    return builder.process_criteria(criteria, required_fields=required_fields)


def search_profiles(
    source: str,
    criteria: Mapping[str, Any],
    self_profile: Mapping[str, Any] | None = None,
    self_id: int | None = None,
    limit: int = 10,
    ...
) -> dict[str, Any]:
    """搜索候选人（改进版）
    
    Args:
        criteria: 所有搜索参数，现在支持任意字段
    """
    
    # === 使用通用查询构建器 ===
    where_clause, params = build_search_conditions(dict(criteria))
    
    # 构建 SQL
    sql = f"""
        SELECT * FROM profiles
        {where_clause}
        ORDER BY score DESC
        LIMIT :limit
    """
    params["limit"] = limit
    
    # 执行查询
    results = execute_sql_query(source, sql, params)
    
    # 返回结果
    return {
        "has_match": bool(results),
        "result_count": len(results),
        "results": results,
        "request_meta": {
            "criteria": criteria,
            "where_clause": where_clause,
            "query_params": params,
        },
    }
```

---

### 3.3 新增 MBTI 字段支持

#### 字段映射配置

```python
# 在 field_mapper.py 的 FIELD_MAPPING 中新增

# === MBTI 相关字段 ===
"mbti_types": ("mbti_type", QUERY_TYPE_IN),
# 用途：筛选指定 MBTI 类型
# 示例：WHERE mbti_type IN ('INTP', 'INTJ', 'INFP', 'INFJ', 'ENTP', 'ENTJ', 'ENFP', 'ENFJ')

"exclude_mbti": ("mbti_type", QUERY_TYPE_NOT_IN),
# 用途：排除某些 MBTI 类型
# 示例：WHERE mbti_type NOT IN ('ESFJ', 'ISTJ', 'ESTJ', 'ISFJ')

"mbti_preference": ("mbti_type", QUERY_TYPE_LIKE),
# 用途：按 MBTI 维度筛选（如 N系/S系）
# 示例：WHERE mbti_type LIKE '%N%'（筛选所有 N系）
```

#### 数据库字段准备

```sql
-- 方案 A：直接在 profiles 表添加字段
ALTER TABLE profiles ADD COLUMN mbti_type VARCHAR(4);

-- 方案 B：使用现有的 personality_traits 表
-- 需要关联查询：
-- SELECT p.*, pt.mbti_type 
-- FROM profiles p 
-- LEFT JOIN personality_traits pt ON p.id = pt.profile_id
-- WHERE pt.mbti_type IN (...)

-- 数据初始化（如果需要）
UPDATE profiles SET mbti_type = personality_traits.mbti_type
FROM personality_traits 
WHERE profiles.id = personality_traits.profile_id;
```

---

## 四、迁移路径

### 4.1 平滑迁移策略

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1：并行运行（保持兼容）                                    │
│                                                                 │
│  - 新增 UniversalQueryBuilder                                   │
│  - search_sources.py 同时支持新旧逻辑                            │
│  - 通过配置开关 USE_UNIVERSAL_QUERY 控制                          │
│  - 默认关闭，先验证                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2：验证测试                                               │
│                                                                 │
│  - 单元测试验证新逻辑                                            │
│  - 对比新旧逻辑的结果一致性                                       │
│  - 在测试环境启用新逻辑                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3：渐进替换                                               │
│                                                                 │
│  - 在生产环境启用配置开关                                         │
│  - 监控查询性能和结果正确性                                       │
│  - 逐步迁移字段到新映射器                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4：完全替换                                               │
│                                                                 │
│  - 移除旧逻辑（硬编码部分）                                       │
│  - 移除 hard_keys 硬编码                                         │
│  - 移除 soft_preferences 概念                                    │
│  - 移除配置开关                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 配置开关

```python
# her_env.py 或 settings.py

# 是否使用通用查询构建器
HER_USE_UNIVERSAL_QUERY = env_first("HER_USE_UNIVERSAL_QUERY", "false").lower() == "true"

# 是否启用 MBTI 筛选（需要数据库字段支持）
HER_ENABLE_MBTI_FILTER = env_first("HER_ENABLE_MBTI_FILTER", "false").lower() == "true"
```

```python
# search_sources.py

def search_profiles(...):
    """支持新旧逻辑切换"""
    
    if HER_USE_UNIVERSAL_QUERY:
        # 新逻辑：通用查询
        where_clause, params = build_search_conditions(dict(criteria))
    else:
        # 旧逻辑：硬编码字段（保持兼容）
        where_clause, params = build_search_conditions_legacy(criteria)
    
    # 后续逻辑相同
    sql = f"SELECT * FROM profiles {where_clause} ..."
    return execute_query(sql, params)
```

---

## 五、测试验证

### 5.1 单元测试

**文件**：`tests/test_universal_search.py`

```python
"""通用搜索系统测试"""

import pytest
from match_domain.field_mapper import FieldMapper, QUERY_TYPE_IN, QUERY_TYPE_NOT_IN
from match_domain.universal_query_builder import UniversalQueryBuilder


class TestFieldMapper:
    """字段映射器测试"""
    
    def test_get_field_mbti_types(self):
        """测试 MBTI 类型字段映射"""
        mapper = FieldMapper()
        field = mapper.get_field("mbti_types")
        assert field == "mbti_type"
    
    def test_get_query_type_mbti_types(self):
        """测试 MBTI 类型查询类型"""
        mapper = FieldMapper()
        query_type = mapper.get_query_type("mbti_types")
        assert query_type == QUERY_TYPE_IN
    
    def test_get_query_type_exclude_mbti(self):
        """测试排除 MBTI 查询类型"""
        mapper = FieldMapper()
        query_type = mapper.get_query_type("exclude_mbti")
        assert query_type == QUERY_TYPE_NOT_IN
    
    def test_infer_query_type_age_min(self):
        """测试自动推断：_min 后缀"""
        mapper = FieldMapper()
        query_type = mapper.get_query_type("some_field_min")
        assert query_type == "range_min"
    
    def test_infer_query_type_age_max(self):
        """测试自动推断：_max 后缀"""
        mapper = FieldMapper()
        query_type = mapper.get_query_type("some_field_max")
        assert query_type == "range_max"
    
    def test_infer_query_type_exclude(self):
        """测试自动推断：exclude_ 前缀"""
        mapper = FieldMapper()
        query_type = mapper.get_query_type("exclude_some_field")
        assert query_type == QUERY_TYPE_NOT_IN
    
    def test_register_new_field(self):
        """测试动态注册新字段"""
        mapper = FieldMapper()
        mapper.register("new_field", "db_column", "exact")
        
        assert mapper.get_field("new_field") == "db_column"
        assert mapper.get_query_type("new_field") == "exact"


class TestUniversalQueryBuilder:
    """通用查询构建器测试"""
    
    def test_process_mbti_types(self):
        """测试 MBTI 类型筛选"""
        builder = UniversalQueryBuilder()
        criteria = {
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 验证 WHERE 子句包含 mbti_type IN 条件
        assert "mbti_type IN" in where_clause
        
        # 验证参数包含所有 MBTI 类型
        assert "INTP" in params.values()
        assert "INTJ" in params.values()
        assert "ENFJ" in params.values()
    
    def test_process_exclude_mbti(self):
        """测试排除 MBTI 类型"""
        builder = UniversalQueryBuilder()
        criteria = {
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 验证 WHERE 子句包含 NOT IN 条件
        assert "mbti_type NOT IN" in where_clause
        
        # 验证参数包含所有排除的类型
        assert "ESFJ" in params.values()
        assert "ISTJ" in params.values()
    
    def test_process_mixed_criteria(self):
        """测试混合条件"""
        builder = UniversalQueryBuilder()
        criteria = {
            "cities": ["无锡", "上海"],
            "age_min": 26,
            "age_max": 36,
            "mbti_types": ["INTP", "INTJ"],
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 验证所有条件都被添加
        assert "city IN" in where_clause
        assert "age >= " in where_clause
        assert "age <= " in where_clause
        assert "mbti_type IN" in where_clause
        
        # 验证 AND 连接
        assert " AND " in where_clause
    
    def test_process_empty_criteria(self):
        """测试空条件"""
        builder = UniversalQueryBuilder()
        criteria = {}
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 空条件应该返回空 WHERE 子句
        assert where_clause == ""
        assert params == {}
    
    def test_process_null_values(self):
        """测试空值过滤"""
        builder = UniversalQueryBuilder()
        criteria = {
            "cities": ["无锡"],
            "mbti_types": None,  # 应被过滤
            "exclude_mbti": [],  # 应被过滤
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 只有有效条件被添加
        assert "city IN" in where_clause
        assert "mbti_type" not in where_clause
    
    def test_required_fields_missing(self):
        """测试必需字段缺失"""
        builder = UniversalQueryBuilder()
        criteria = {
            "cities": ["无锡"],
            # 缺少必需字段 gender
        }
        
        with pytest.raises(ValueError, match="Required field 'gender' is missing"):
            builder.process_criteria(criteria, required_fields=["gender"])
    
    def test_required_fields_present(self):
        """测试必需字段存在"""
        builder = UniversalQueryBuilder()
        criteria = {
            "gender": "female",
            "cities": ["无锡"],
        }
        
        where_clause, params = builder.process_criteria(criteria, required_fields=["gender"])
        
        # 应成功构建查询
        assert "gender =" in where_clause
        assert "city IN" in where_clause


class TestMBTISearch:
    """MBTI 搜索场景测试"""
    
    def test_n_series_search(self):
        """测试 N系（直觉型）搜索"""
        builder = UniversalQueryBuilder()
        criteria = {
            "mbti_types": ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # N系的 8 种类型都应该在参数中
        n_types = ["INTP", "INTJ", "INFP", "INFJ", "ENTP", "ENTJ", "ENFP", "ENFJ"]
        for mbti_type in n_types:
            assert mbti_type in params.values()
    
    def test_exclude_s_series(self):
        """测试排除 S系（实感型）"""
        builder = UniversalQueryBuilder()
        criteria = {
            "exclude_mbti": ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # S系的 4 种类型都应该在排除列表中
        s_types = ["ESFJ", "ISTJ", "ESTJ", "ISFJ"]
        for mbti_type in s_types:
            assert mbti_type in params.values()
    
    def test_combined_mbti_search(self):
        """测试组合 MBTI 搜索"""
        builder = UniversalQueryBuilder()
        criteria = {
            "cities": ["无锡"],
            "exclude_mbti": ["ESFJ", "ISTJ"],  # 排除 S系的一部分
            "mbti_types": ["INTP", "INTJ"],     # 指定想要的类型
        }
        
        where_clause, params = builder.process_criteria(criteria)
        
        # 应同时包含 IN 和 NOT IN
        assert "mbti_type IN" in where_clause
        assert "mbti_type NOT IN" in where_clause
```

### 5.2 集成测试

```python
# tests/test_search_integration.py

def test_search_with_mbti_filter():
    """测试实际搜索结果"""
    from partner_search import search_profiles
    
    criteria = {
        "cities": ["无锡"],
        "mbti_types": ["INTP", "INTJ", "INFP", "INFJ"],
    }
    
    result = search_profiles(
        source=source,
        criteria=criteria,
        limit=5,
    )
    
    # 验证结果都是 N系
    for candidate in result["results"]:
        mbti_type = candidate.get("mbti_type")
        assert mbti_type in ["INTP", "INTJ", "INFP", "INFJ"]
```

---

## 六、收益总结

### 6.1 对比表

| 维度 | 改进前 | 改进后 |
|------|-------|-------|
| **Agent 表达能力** | 只能用预设字段 | 任意字段都能搜索 ✅ |
| **新增字段成本** | 改 3 处代码（criteria_compiler + search_sources + 测试） | 加 1 行映射配置 ✅ |
| **代码维护** | 500+ 行硬编码逻辑 | 100 行通用逻辑 ✅ |
| **测试覆盖** | 每个字段单独测试 | 通用测试覆盖所有场景 ✅ |
| **符合 Agent Native** | ❌ 工具限制 Agent | ✅ 工具执行 Agent 意图 |
| **扩展性** | 低（每次新增都改核心代码） | 高（只需加映射） ✅ |

### 6.2 具体收益

1. **MBTI 筛选支持**：Agent 可以自由按性格类型筛选候选人
2. **未来扩展**：新增任何筛选维度（如依恋风格、价值观）只需加一行映射
3. **减少维护成本**：不再需要维护 500+ 行硬编码逻辑
4. **更符合 Agent Native**：工具不再限制 Agent 能说什么

---

## 七、文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `match_domain/field_mapper.py` | 新增 | 字段映射器 |
| `match_domain/universal_query_builder.py` | 新增 | 通用查询构建器 |
| `match_domain/criteria_compiler.py` | 修改 | 移除 hard_keys 硬编码 |
| `partner_search/search_sources.py` | 修改 | 使用通用查询 |
| `tests/test_universal_search.py` | 新增 | 单元测试 |
| `docs/universal-search-design.md` | 新增 | 本设计文档 |

---

## 八、参考资料

- Agent Native 原则：参见 `~/.claude/CLAUDE.md`
- 当前搜索逻辑：`match_domain/criteria_compiler.py:200-221`
- 搜索执行层：`partner_search/search_sources.py:275-321`