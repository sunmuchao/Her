"""Add new target preference fields to persona table.

新增可量化的搜索条件字段：
- target_hometown_cities: 期望对方家乡列表（地理位置）
- target_house_requirement: 对方房产要求（枚举类型）
- target_car_requirement: 对方车产要求（枚举类型）
- target_smoke_acceptance: 对方抽烟接受度（枚举类型）
- target_drink_acceptance: 对方喝酒接受度（枚举类型）
- target_weight_min: 目标体重下限（数值范围）
- target_weight_max: 目标体重上限（数值范围）

架构原则：persona 表只存放可量化的搜索条件
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


# 新增可量化搜索条件字段定义
NEW_TARGET_PREFERENCE_FIELDS = {
    "target_weight_min": "INT DEFAULT NULL COMMENT '目标体重下限（kg）'",
    "target_weight_max": "INT DEFAULT NULL COMMENT '目标体重上限（kg）'",
    "target_hometown_cities": "TEXT COMMENT '期望对方家乡列表'",
    "target_house_requirement": "VARCHAR(32) DEFAULT NULL COMMENT '对方房产要求'",
    "target_car_requirement": "VARCHAR(32) DEFAULT NULL COMMENT '对方车产要求'",
    "target_smoke_acceptance": "VARCHAR(32) DEFAULT NULL COMMENT '对方抽烟接受度'",
    "target_drink_acceptance": "VARCHAR(32) DEFAULT NULL COMMENT '对方喝酒接受度'",
}


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Add new target preference fields to persona table."""
    table = _persona_table(context)
    with conn.cursor() as cursor:
        for column_name, column_type in NEW_TARGET_PREFERENCE_FIELDS.items():
            # Check if column exists
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (table, column_name),
            )
            if cursor.fetchone() is not None:
                # Column already exists, skip
                continue
            # Add the column
            cursor.execute(
                f"ALTER TABLE `{table}` ADD COLUMN `{column_name}` {column_type}"
            )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    """Validate that new target preference fields have been added to persona table."""
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    table = _persona_table(context)
    with conn.cursor() as cursor:
        # Check if table exists
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
            return issues

        # Check that new fields are added
        for column_name in NEW_TARGET_PREFERENCE_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (table, column_name),
            )
            if cursor.fetchone() is None:
                # Column doesn't exist - missing
                issues["missing_columns"].append(f"{table}.{column_name}:should_be_added")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0011_add_new_target_preference_fields",
    description="Add new target preference fields to persona table (hometown_cities, house_requirement, car_requirement, smoke_acceptance, drink_acceptance, weight_min/max)",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)