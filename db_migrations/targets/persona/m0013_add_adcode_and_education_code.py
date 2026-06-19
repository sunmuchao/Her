"""Add adcode fields for geographical location optimization and education code for quantification.

架构优化：
1. 地理位置优化：
   - city_adcode、district_adcode、hometown_city_adcode (INT)：避免字符串重名，精准匹配
   - target_cities_adcodes、target_districts_adcodes、target_hometown_cities_adcodes (TEXT)：快速范围搜索

2. 学历量化优化：
   - target_education_min_code (INT)：1-专科，2-本科，3-硕士，4-博士
   - SQL 直接用 >= 筛选，高效且准确

优化效果：
- ✅ 避免"朝阳区"重名（北京朝阳区、长春朝阳区）
- ✅ INT 索引效率高，查询速度快
- ✅ 学历编码直接用 >= 筛选，避免字符串比对
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope, persona_scope


# Profiles 表新增地理位置编码字段
NEW_PROFILE_ADCODE_FIELDS = {
    "city_adcode": "INT NULL COMMENT '当前城市行政区划代码'",
    "district_adcode": "INT NULL COMMENT '当前区县行政区划代码'",
    "hometown_city_adcode": "INT NULL COMMENT '籍贯城市行政区划代码'",
}

# Persona 表新增地理位置编码字段
NEW_PERSONA_ADCODE_FIELDS = {
    "target_cities_adcodes": "TEXT COMMENT '目标城市编码列表'",
    "target_districts_adcodes": "TEXT COMMENT '目标区县编码列表'",
    "target_hometown_cities_adcodes": "TEXT COMMENT '期望对方家乡编码列表'",
}

# Persona 表新增学历编码字段
NEW_PERSONA_EDUCATION_CODE_FIELDS = {
    "target_education_min_code": "INT DEFAULT NULL COMMENT '目标学历下限编码（1-专科，2-本科，3-硕士，4-博士）'",
}


def _profile_table(context: MigrationContext) -> str:
    return str(context.options.get("profile_table") or "profiles")


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Add adcode and education code fields to profiles and persona tables."""
    profile_table = _profile_table(context)
    persona_table = _persona_table(context)

    with conn.cursor() as cursor:
        # 添加 Profiles 表的地理位置编码字段
        for column_name, column_type in NEW_PROFILE_ADCODE_FIELDS.items():
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (profile_table, column_name),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE `{profile_table}` ADD COLUMN `{column_name}` {column_type}"
                )

        # 添加 Persona 表的地理位置编码字段
        for column_name, column_type in NEW_PERSONA_ADCODE_FIELDS.items():
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column_name),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE `{persona_table}` ADD COLUMN `{column_name}` {column_type}"
                )

        # 添加 Persona 表的学历编码字段
        for column_name, column_type in NEW_PERSONA_EDUCATION_CODE_FIELDS.items():
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column_name),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE `{persona_table}` ADD COLUMN `{column_name}` {column_type}"
                )

        # 添加学历编码索引
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = 'idx_target_education_min_code'
            LIMIT 1
            """,
            (persona_table,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"ALTER TABLE `{persona_table}` ADD INDEX `idx_target_education_min_code` (`target_education_min_code`)"
            )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    """Validate that adcode and education code fields have been added."""
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    profile_table = _profile_table(context)
    persona_table = _persona_table(context)

    with conn.cursor() as cursor:
        # Check if tables exist
        for table in [profile_table, persona_table]:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                LIMIT 1
                """,
                (table,),
            )
            if cursor.fetchone() is None:
                issues["missing_tables"].append(table)

        if issues["missing_tables"]:
            return issues

        # Check that Profiles adcode fields are added
        for column_name in NEW_PROFILE_ADCODE_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (profile_table, column_name),
            )
            if cursor.fetchone() is None:
                issues["missing_columns"].append(f"{profile_table}.{column_name}:should_be_added")

        # Check that Persona adcode fields are added
        for column_name in NEW_PERSONA_ADCODE_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column_name),
            )
            if cursor.fetchone() is None:
                issues["missing_columns"].append(f"{persona_table}.{column_name}:should_be_added")

        # Check that Persona education code field is added
        for column_name in NEW_PERSONA_EDUCATION_CODE_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column_name),
            )
            if cursor.fetchone() is None:
                issues["missing_columns"].append(f"{persona_table}.{column_name}:should_be_added")

        # Check that education code index is added
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = 'idx_target_education_min_code'
            LIMIT 1
            """,
            (persona_table,),
        )
        if cursor.fetchone() is None:
            issues["missing_columns"].append(f"{persona_table}.idx_target_education_min_code:should_be_added")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0013_add_adcode_and_education_code",
    description="Add adcode fields for geographical optimization and education code for quantification",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)