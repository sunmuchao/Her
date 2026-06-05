"""Add self_personality_traits_json column to user_personas table."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _apply(conn: Any, context: MigrationContext) -> None:
    table = _persona_table(context)
    with conn.cursor() as cursor:
        # 检查字段是否已存在
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'self_personality_traits_json'
            """,
            (table,),
        )
        row = cursor.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]

        # 如果字段不存在，则添加
        if int(cnt or 0) == 0:
            cursor.execute(
                f"""
                ALTER TABLE `{table}`
                ADD COLUMN self_personality_traits_json TEXT DEFAULT NULL
                COMMENT '性格特质测评结果（JSON格式，包含大五人格、依恋风格等）'
                AFTER self_relationship_goal
                """
            )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    table = _persona_table(context)
    with conn.cursor() as cursor:
        # 验证字段是否存在
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'self_personality_traits_json'
            LIMIT 1
            """,
            (table,),
        )
        if cursor.fetchone() is None:
            issues["missing_columns"].append(f"{table}.self_personality_traits_json")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0006_add_personality_traits_json",
    description="Add self_personality_traits_json column to user_personas for storing personality assessment results",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
