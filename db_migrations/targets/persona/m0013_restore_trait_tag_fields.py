"""Restore preferred_traits and disliked_traits fields to persona table.

Architecture clarification:
- Tags are quantifiable fields (per architecture principle: "numeric ranges, enums, booleans, locations, tags")
- preferred_traits and disliked_traits are tag arrays, should be classified as quantifiable
- Business logic still depends on these fields (reciprocal_preferences, profile editing)
- m0009 classification was incorrect: these are tags, not non-quantifiable subjective descriptions

This migration reverses part of m0009 for these two specific fields.
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


RESTORED_FIELDS = [
    ("preferred_traits", "JSON", "NULL COMMENT '偏好性格特质标签（可量化标签数组）'"),
    ("disliked_traits", "JSON", "NULL COMMENT '不喜欢性格特质标签（可量化标签数组）'"),
]


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Restore preferred_traits and disliked_traits fields."""
    persona_table = _persona_table(context)

    with conn.cursor() as cursor:
        for column_name, column_type, column_options in RESTORED_FIELDS:
            # Check if column already exists
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
            if cursor.fetchone() is not None:
                # Column already exists, skip
                continue

            # Add the column
            cursor.execute(
                f"ALTER TABLE `{persona_table}` "
                f"ADD COLUMN `{column_name}` {column_type} {column_options}"
            )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    """Validate that fields have been restored."""
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    persona_table = _persona_table(context)

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
            (persona_table,),
        )
        if cursor.fetchone() is None:
            issues["missing_tables"].append(persona_table)
            return issues

        # Check that restored fields exist
        for column_name, _, _ in RESTORED_FIELDS:
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
                issues["missing_columns"].append(f"{persona_table}.{column_name}:should_be_restored")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0013_restore_trait_tag_fields",
    description="Restore preferred_traits and disliked_traits fields (architecture clarification: tags are quantifiable)",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)