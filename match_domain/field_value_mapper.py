"""字段值映射器 - 统一处理中英文值的映射

架构原则：
- 用户层：使用中文显示值（体验优先）
- 数据库层：使用英文标准值（国际化、易维护）
- 映射层：统一处理转换和校验

使用示例：
    # 写入数据库前（中文 → 英文）
    db_value = FieldValueMapper.to_db_value('gender', '男')  # 返回 'male'

    # 读取展示时（英文 → 中文）
    display_value = FieldValueMapper.to_display_value('gender', 'male')  # 返回 '男'

    # 校验字段值
    is_valid = FieldValueMapper.validate('gender', 'male')  # 返回 True

    # 规范化整条记录
    normalized = FieldValueMapper.normalize_record(
        {'gender': '男', 'marital_status': '未婚'},
        direction='display_to_db'
    )
    # 返回 {'gender': 'male', 'marital_status': 'never_married'}
"""

from typing import Any, Dict, Optional


class FieldValueMapper:
    """字段值映射器

    负责：
    1. 显示值（中文）→ 数据库值（英文）
    2. 数据库值（英文）→ 显示值（中文）
    3. 字段值校验
    """

    # 字段值映射表
    FIELD_VALUE_MAPS = {
        "gender": {
            "db_to_display": {
                "male": "男",
                "female": "女",
            },
            "display_to_db": {
                "男": "male",
                "女": "female",
                "male": "male",  # 兼容英文输入
                "female": "female",
            },
            "valid_db_values": ["male", "female"],
        },
        "marital_status": {
            "db_to_display": {
                "never_married": "未婚",
                "divorced_no_kids": "离异未育",
                "divorced_with_kids": "离异已育",
            },
            "display_to_db": {
                "未婚": "never_married",
                "离异未育": "divorced_no_kids",
                "离异无孩": "divorced_no_kids",  # 别名
                "离异已育": "divorced_with_kids",
                "离异有孩": "divorced_with_kids",  # 别名
                "never_married": "never_married",  # 兼容英文输入
                "divorced_no_kids": "divorced_no_kids",
                "divorced_with_kids": "divorced_with_kids",
            },
            "valid_db_values": ["never_married", "divorced_no_kids", "divorced_with_kids"],
        },
        "relationship_goal": {
            "db_to_display": {
                "marriage": "结婚导向",
                "dating": "认真恋爱",
                "casual": "随意",
            },
            "display_to_db": {
                "结婚导向": "marriage",
                "结婚": "marriage",  # 别名
                "认真恋爱": "dating",
                "恋爱": "dating",  # 别名
                "认真相处": "dating",  # 别名
                "随意": "casual",
                "marriage": "marriage",  # 兼容英文输入
                "dating": "dating",
                "casual": "casual",
            },
            "valid_db_values": ["marriage", "dating", "casual"],
        },
        "sexual_orientation": {
            "db_to_display": {
                "like_male": "喜欢男性",
                "like_female": "喜欢女性",
                "heterosexual": "异性恋",
                "homosexual": "同性恋",
                "bisexual": "双性恋",
            },
            "display_to_db": {
                "喜欢男性": "like_male",
                "恋男": "like_male",  # 别名
                "喜欢女性": "like_female",
                "恋女": "like_female",  # 别名
                "异性恋": "heterosexual",
                "同性恋": "homosexual",
                "双性恋": "bisexual",
                "like_male": "like_male",  # 兼容英文输入
                "like_female": "like_female",
                "heterosexual": "heterosexual",
                "homosexual": "homosexual",
                "bisexual": "bisexual",
            },
            "valid_db_values": ["like_male", "like_female", "heterosexual", "homosexual", "bisexual"],
        },
        "profile_status": {
            "db_to_display": {
                "active": "活跃",
                "paused": "暂停",
                "matched": "已匹配",
                "archived": "已归档",
            },
            "display_to_db": {
                "活跃": "active",
                "暂停": "paused",
                "已匹配": "matched",
                "已归档": "archived",
                "active": "active",  # 兼容英文输入
                "paused": "paused",
                "matched": "matched",
                "archived": "archived",
            },
            "valid_db_values": ["active", "paused", "matched", "archived"],
        },
    }

    @classmethod
    def to_db_value(cls, field: str, display_value: Any) -> Optional[str]:
        """将显示值转换为数据库值

        Args:
            field: 字段名
            display_value: 显示值（中文或英文）

        Returns:
            数据库标准值（英文），如果无法映射则返回None
        """
        if field not in cls.FIELD_VALUE_MAPS:
            # 不在映射表中的字段，直接返回原值
            return str(display_value).strip() if display_value else None

        field_map = cls.FIELD_VALUE_MAPS[field]
        display_to_db = field_map.get("display_to_db", {})

        # 统一转为字符串处理
        value_str = str(display_value).strip() if display_value else None
        if not value_str:
            return None

        return display_to_db.get(value_str)

    @classmethod
    def to_display_value(cls, field: str, db_value: Any) -> Optional[str]:
        """将数据库值转换为显示值

        Args:
            field: 字段名
            db_value: 数据库值（英文）

        Returns:
            显示值（中文），如果无法映射则返回原值
        """
        if field not in cls.FIELD_VALUE_MAPS:
            # 不在映射表中的字段，直接返回原值
            return str(db_value).strip() if db_value else None

        field_map = cls.FIELD_VALUE_MAPS[field]
        db_to_display = field_map.get("db_to_display", {})

        # 统一转为字符串处理
        value_str = str(db_value).strip() if db_value else None
        if not value_str:
            return None

        # 如果映射表中有，返回映射值；否则返回原值
        return db_to_display.get(value_str, db_value)

    @classmethod
    def validate(cls, field: str, value: Any) -> bool:
        """校验字段值是否合法

        Args:
            field: 字段名
            value: 字段值

        Returns:
            True 如果值合法，False 如果不合法
        """
        if field not in cls.FIELD_VALUE_MAPS:
            # 不在映射表中的字段，默认合法
            return True

        field_map = cls.FIELD_VALUE_MAPS[field]
        valid_db_values = field_map.get("valid_db_values", [])

        # 尝试转换为数据库值
        db_value = cls.to_db_value(field, value)

        return db_value in valid_db_values if db_value else False

    @classmethod
    def normalize_record(
        cls, record: Dict[str, Any], direction: str = "display_to_db"
    ) -> Dict[str, Any]:
        """规范化整条记录

        Args:
            record: 原始记录
            direction: 转换方向
                - "display_to_db": 显示值 → 数据库值（用于写入数据库）
                - "db_to_display": 数据库值 → 显示值（用于前端展示）

        Returns:
            规范化后的记录
        """
        normalized = dict(record)

        for field in cls.FIELD_VALUE_MAPS.keys():
            if field in normalized and normalized[field] is not None:
                if direction == "display_to_db":
                    normalized[field] = cls.to_db_value(field, normalized[field])
                elif direction == "db_to_display":
                    normalized[field] = cls.to_display_value(field, normalized[field])

        return normalized

    @classmethod
    def get_valid_db_values(cls, field: str) -> list[str]:
        """获取字段的合法数据库值列表

        Args:
            field: 字段名

        Returns:
            合法值列表
        """
        if field not in cls.FIELD_VALUE_MAPS:
            return []

        return cls.FIELD_VALUE_MAPS[field].get("valid_db_values", [])


# 导出公共API
__all__ = ["FieldValueMapper"]