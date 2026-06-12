"""通用字段映射器：参数名 → 数据库字段名 + 查询类型

设计理念：
- Agent Native：任何 Agent 传入的参数都应该能被搜索
- 不再硬编码"只支持某些字段"，而是通过映射表自动处理
- 新增字段只需加一行映射，无需改多处代码
"""

from __future__ import annotations

from typing import Any


# 查询类型枚举
QUERY_TYPE_EXACT = "exact"          # 精确匹配：WHERE field = value
QUERY_TYPE_IN = "in"                # 列表匹配：WHERE field IN (values)
QUERY_TYPE_NOT_IN = "not_in"        # 排除列表：WHERE field NOT IN (values)
QUERY_TYPE_RANGE_MIN = "range_min"  # 范围下限：WHERE field >= value
QUERY_TYPE_RANGE_MAX = "range_max"  # 范围上限：WHERE field <= value
QUERY_TYPE_LIKE = "like"            # 模糊匹配：WHERE field LIKE value


# 字段映射表：参数名 → (数据库字段名, 查询类型)
FIELD_MAPPING = {
    # === 基础字段 ===
    "gender": ("gender", QUERY_TYPE_EXACT),
    "cities": ("city", QUERY_TYPE_IN),
    "districts": ("district", QUERY_TYPE_IN),
    "settlement_cities": ("settlement_city", QUERY_TYPE_IN),
    "relationship_goals": ("relationship_goal", QUERY_TYPE_IN),
    "relationship_goal": ("relationship_goal", QUERY_TYPE_EXACT),

    # === 数值范围字段 ===
    "age_min": ("age", QUERY_TYPE_RANGE_MIN),
    "age_max": ("age", QUERY_TYPE_RANGE_MAX),
    "height_min": ("height", QUERY_TYPE_RANGE_MIN),
    "height_max": ("height", QUERY_TYPE_RANGE_MAX),

    # === 状态字段 ===
    "marital_statuses": ("marital_status", QUERY_TYPE_IN),
    "marital_status": ("marital_status", QUERY_TYPE_EXACT),
    "housing_statuses": ("housing_status", QUERY_TYPE_IN),
    "car_statuses": ("car_status", QUERY_TYPE_IN),
    "profile_statuses": ("profile_status", QUERY_TYPE_IN),
    "verified_levels": ("verified_level", QUERY_TYPE_IN),
    "photo_verification_levels": ("photo_verification_level", QUERY_TYPE_IN),

    # === MBTI 相关字段（新增）===
    "mbti_types": ("mbti_type", QUERY_TYPE_IN),
    "exclude_mbti": ("mbti_type", QUERY_TYPE_NOT_IN),
    "exclude_mbti_types": ("mbti_type", QUERY_TYPE_NOT_IN),

    # === 其他字段 ===
    "long_distance": ("accept_long_distance", QUERY_TYPE_EXACT),
    "accept_partner_children": ("accept_partner_children", QUERY_TYPE_EXACT),
    "want_children": ("want_children", QUERY_TYPE_EXACT),
    "marriage_timelines": ("marriage_timeline", QUERY_TYPE_IN),
    "smoking": ("smoking", QUERY_TYPE_EXACT),
    "drinking": ("drinking", QUERY_TYPE_EXACT),
    "has_children": ("has_children", QUERY_TYPE_EXACT),
    "photo_count_min": ("photo_count", QUERY_TYPE_RANGE_MIN),
    "verified_level_min": ("verified_level", QUERY_TYPE_RANGE_MIN),
    "photo_verification_level_min": ("photo_verification_level", QUERY_TYPE_RANGE_MIN),

    # === 排除字段 ===
    "exclude_source_channels": ("source_channel", QUERY_TYPE_NOT_IN),
}


class FieldMapper:
    """字段映射器

    职责：
    1. 参数名 → 数据库字段名
    2. 参数名 → 查询类型
    3. 自动推断未映射参数的处理方式
    """

    def __init__(self, mapping: dict[str, tuple[str, str]] = None):
        self.mapping = mapping or FIELD_MAPPING.copy()

    def get_field(self, param_name: str) -> str | None:
        """获取数据库字段名

        Args:
            param_name: Agent 传入的参数名

        Returns:
            数据库字段名，如果找不到映射则返回参数名本身
        """
        if param_name in self.mapping:
            return self.mapping[param_name][0]
        # 没有映射的字段，尝试直接使用参数名（假设数据库字段名相同）
        return param_name

    def get_query_type(self, param_name: str) -> str:
        """获取查询类型

        Args:
            param_name: Agent 传入的参数名

        Returns:
            查询类型（exact, in, not_in, range_min, range_max, like）
        """
        if param_name in self.mapping:
            return self.mapping[param_name][1]
        # 没有映射的字段，自动推断查询类型
        return self._infer_query_type(param_name)

    def _infer_query_type(self, param_name: str) -> str:
        """根据参数名自动推断查询类型

        规则：
        - _min 后缀 → 范围下限（>=）
        - _max 后缀 → 范围上限（<=）
        - exclude_ 前缀 → 排除列表（NOT IN）
        - _statuses/_goals/_channels 等复数形式 → 列表（IN）
        - 其他 → 精确匹配（=）
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
        # 复数形式 → 列表查询
        plural_suffixes = ("_statuses", "_goals", "_channels", "_types", "_levels", "s")
        if any(param_name.endswith(suffix) for suffix in plural_suffixes):
            return QUERY_TYPE_IN
        # 默认：精确匹配
        return QUERY_TYPE_EXACT

    def register(self, param_name: str, field_name: str, query_type: str):
        """注册新字段映射

        Args:
            param_name: Agent 传入的参数名
            field_name: 数据库字段名
            query_type: 查询类型
        """
        self.mapping[param_name] = (field_name, query_type)

    def is_supported(self, param_name: str) -> bool:
        """检查参数是否被支持

        Args:
            param_name: 参数名

        Returns:
            是否有映射或能自动推断
        """
        return param_name in self.mapping or self._infer_query_type(param_name) is not None

    def get_all_supported_params(self) -> list[str]:
        """获取所有支持的参数名"""
        return list(self.mapping.keys())

    def get_mapping_info(self, param_name: str) -> dict[str, str] | None:
        """获取参数的完整映射信息

        Args:
            param_name: 参数名

        Returns:
            {'field': '...', 'query_type': '...'} 或 None
        """
        field = self.get_field(param_name)
        query_type = self.get_query_type(param_name)
        if field:
            return {"field": field, "query_type": query_type}
        return None