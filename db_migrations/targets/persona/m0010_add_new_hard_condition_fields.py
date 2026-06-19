"""Add new hard condition fields to profiles table.

新增硬条件字段：
- hometown_city: 籍贯/家乡城市（相亲极其看重"是不是老乡"）
- weight: 体重（kg，配合身高计算 BMI 或判断身材）
- has_house: 房产情况（核心硬条件，需支持认证）
- has_car: 车产情况（核心硬条件）
- religion: 宗教信仰（某些信仰对结婚有决定性影响）
- is_only_child: 是否独生子女（部分家庭相亲关注点）

新增认证字段：
- house_verification_status: 房产认证状态（房产认证需要）

架构原则：所有硬条件字段都应该在 profiles 表中
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


# 新增硬条件字段定义
NEW_HARD_CONDITION_FIELDS = {
    "hometown_city": "VARCHAR(64) NULL COMMENT '籍贯/家乡城市（硬条件）'",
    "weight": "INT NULL COMMENT '体重（kg，硬条件）'",
    "has_house": "VARCHAR(32) NULL COMMENT '房产情况（硬条件）'",
    "has_car": "VARCHAR(32) NULL COMMENT '车产情况（硬条件）'",
    "religion": "VARCHAR(32) NULL COMMENT '宗教信仰（硬条件）'",
    "is_only_child": "TINYINT(1) NULL COMMENT '是否独生子女（硬条件）'",
}

# 新增认证字段定义
NEW_VERIFICATION_FIELDS = {
    "house_verification_status": "VARCHAR(32) NULL COMMENT '房产认证状态'",
}


def _profile_table(context: MigrationContext) -> str:
    return str(context.options.get("profile_table") or "profiles")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Add new hard condition fields to profiles table."""
    table = _profile_table(context)
    with conn.cursor() as cursor:
        # 添加硬条件字段
        for column_name, column_type in NEW_HARD_CONDITION_FIELDS.items():
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

        # 添加认证字段
        for column_name, column_type in NEW_VERIFICATION_FIELDS.items():
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
    """Validate that new hard condition fields have been added to profiles table."""
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    table = _profile_table(context)
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

        # Check that new hard condition fields are added
        for column_name in NEW_HARD_CONDITION_FIELDS:
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

        # Check that new verification fields are added
        for column_name in NEW_VERIFICATION_FIELDS:
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
    migration_id="0010_add_new_hard_condition_fields",
    description="Add new hard condition fields to profiles table (hometown_city, weight, has_house, has_car, religion, is_only_child)",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)