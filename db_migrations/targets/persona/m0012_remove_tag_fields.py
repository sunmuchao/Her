"""Remove must_have_tags and must_not_have_tags fields from persona table.

删除字段：
- must_have_tags: 硬偏好标签（必选项）
- must_not_have_tags: 明确排斥标签

架构原则：简化 persona 表字段，只保留核心可量化搜索条件
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


# 要删除的标签字段
DELETED_TAG_FIELDS = [
    "must_have_tags",
    "must_not_have_tags",
]


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Remove must_have_tags and must_not_have_tags from persona table."""
    table = _persona_table(context)
    with conn.cursor() as cursor:
        for column in DELETED_TAG_FIELDS:
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
                (table, column),
            )
            if cursor.fetchone() is None:
                # Column doesn't exist, skip
                continue
            # Drop the column
            cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    """Validate that tag fields have been removed from persona table."""
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

        # Check that tag fields are removed
        for column in DELETED_TAG_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (table, column),
            )
            if cursor.fetchone() is not None:
                # Column still exists - incompatible
                issues["incompatible_columns"].append(f"{table}.{column}:should_be_removed")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0012_remove_tag_fields",
    description="Remove must_have_tags and must_not_have_tags from persona table",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)