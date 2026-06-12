"""通用查询构建器：自动处理所有 criteria 参数

设计理念：
- 不再硬编码"只处理某些字段"
- 遍历所有 Agent 传入的参数，自动构建查询条件
- 通过 FieldMapper 翻译参数名和查询类型
"""

from __future__ import annotations

from typing import Any

from .field_mapper import (
    FieldMapper,
    QUERY_TYPE_EXACT,
    QUERY_TYPE_IN,
    QUERY_TYPE_NOT_IN,
    QUERY_TYPE_RANGE_MIN,
    QUERY_TYPE_RANGE_MAX,
    QUERY_TYPE_LIKE,
)


class UniversalQueryBuilder:
    """通用查询构建器

    职责：
    1. 遍历所有 criteria 参数
    2. 通过 FieldMapper 获取字段名和查询类型
    3. 自动构建 SQL WHERE 子句和参数
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
            allow_missing: 是否允许参数缺失（空值）

        Returns:
            是否成功添加条件
        """
        # 空值处理：跳过
        if value is None or value == "" or value == []:
            return False

        # 获取映射信息
        field_name = self.mapper.get_field(param_name)
        if field_name is None:
            # 字段不存在于数据库，优雅降级：跳过
            return False

        query_type = self.mapper.get_query_type(param_name)

        # 根据查询类型构建条件
        if query_type == QUERY_TYPE_EXACT:
            self._add_exact(field_name, value)
        elif query_type == QUERY_TYPE_IN:
            self._add_in(field_name, value)
        elif query_type == QUERY_TYPE_NOT_IN:
            self._add_not_in(field_name, value)
        elif query_type == QUERY_TYPE_RANGE_MIN:
            self._add_range_min(field_name, value)
        elif query_type == QUERY_TYPE_RANGE_MAX:
            self._add_range_max(field_name, value)
        elif query_type == QUERY_TYPE_LIKE:
            self._add_like(field_name, value)
        else:
            # 未知的查询类型，默认精确匹配
            self._add_exact(field_name, value)

        return True

    def _add_exact(self, field: str, value: Any):
        """精确匹配：WHERE field = value"""
        param_key = self._next_param_key()
        self.conditions.append(f"{field} = :{param_key}")
        self.params[param_key] = value

    def _add_in(self, field: str, value: Any):
        """列表匹配：WHERE field IN (values)"""
        # 确保 value 是列表
        if not isinstance(value, (list, tuple, set)):
            value = [value]

        # 为每个值生成参数
        param_keys = []
        for item in value:
            param_key = self._next_param_key()
            self.params[param_key] = item
            param_keys.append(param_key)

        # 构建 IN 条件
        placeholders = ", ".join(f":{k}" for k in param_keys)
        self.conditions.append(f"{field} IN ({placeholders})")

    def _add_not_in(self, field: str, value: Any):
        """排除列表：WHERE field NOT IN (values)"""
        # 确保 value 是列表
        if not isinstance(value, (list, tuple, set)):
            value = [value]

        # 为每个值生成参数
        param_keys = []
        for item in value:
            param_key = self._next_param_key()
            self.params[param_key] = item
            param_keys.append(param_key)

        # 构建 NOT IN 条件
        placeholders = ", ".join(f":{k}" for k in param_keys)
        self.conditions.append(f"{field} NOT IN ({placeholders})")

    def _add_range_min(self, field: str, value: Any):
        """范围下限：WHERE field >= value"""
        param_key = self._next_param_key()
        self.conditions.append(f"{field} >= :{param_key}")
        self.params[param_key] = value

    def _add_range_max(self, field: str, value: Any):
        """范围上限：WHERE field <= value"""
        param_key = self._next_param_key()
        self.conditions.append(f"{field} <= :{param_key}")
        self.params[param_key] = value

    def _add_like(self, field: str, value: str):
        """模糊匹配：WHERE field LIKE %value%"""
        param_key = self._next_param_key()
        self.conditions.append(f"{field} LIKE :{param_key}")
        self.params[param_key] = f"%{value}%"

    def _next_param_key(self) -> str:
        """生成下一个参数键名"""
        return f"param_{len(self.params)}"

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
            参数字典，用于 SQL 执行
        """
        return self.params.copy()

    def clear(self):
        """清空所有条件"""
        self.conditions = []
        self.params = {}

    def process_criteria(
        self,
        criteria: dict[str, Any],
        *,
        required_fields: list[str] = None,
        ignored_fields: list[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        """处理整个 criteria

        Args:
            criteria: 所有搜索参数
            required_fields: 必须存在的字段列表（可选）
            ignored_fields: 需要忽略的字段列表（可选）

        Returns:
            (where_clause, params)
        """
        self.clear()

        # 检查必需字段
        if required_fields:
            for field in required_fields:
                if field not in criteria or self._is_empty(criteria[field]):
                    raise ValueError(f"Required field '{field}' is missing or empty")

        # 默认忽略的字段（不属于搜索条件）
        default_ignored = {"limit", "offset", "order_by", "source", "table_name"}
        all_ignored = set(ignored_fields or []) | default_ignored

        # 遍历所有参数，自动添加条件
        for param_name, value in criteria.items():
            # 跳过忽略的字段
            if param_name in all_ignored:
                continue

            # 添加条件
            self.add_condition(param_name, value, allow_missing=True)

        return self.build_where_clause(), self.get_params()

    def _is_empty(self, value: Any) -> bool:
        """检查值是否为空"""
        return value is None or value == "" or value == []

    def get_debug_info(self) -> dict[str, Any]:
        """获取调试信息

        Returns:
            {'conditions': [...], 'params': {...}}
        """
        return {
            "conditions": self.conditions.copy(),
            "params": self.params.copy(),
        }


def build_search_query(
    criteria: dict[str, Any],
    *,
    mapper: FieldMapper = None,
    required_fields: list[str] = None,
) -> tuple[str, dict[str, Any]]:
    """便捷函数：构建搜索查询

    Args:
        criteria: 所有搜索参数
        mapper: 字段映射器（可选）
        required_fields: 必须存在的字段（可选）

    Returns:
        (where_clause, params)
    """
    builder = UniversalQueryBuilder(mapper=mapper)
    return builder.process_criteria(criteria, required_fields=required_fields)