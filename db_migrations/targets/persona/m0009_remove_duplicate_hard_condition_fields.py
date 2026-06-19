"""Remove duplicate hard condition fields and non-quantifiable fields from persona table (refactoring §13.1.2).

Architecture principle: Single Source of Truth + Quantifiable Fields Only
- Hard conditions (gender, age, city, smoking, drinking, target_gender, etc.) should only exist in profiles table
- Non-quantifiable fields (self_life_rhythm, preferred_traits, persona_summary_internal, etc.) should not exist in persona table
- Persona table should only contain quantifiable fields (numeric ranges, enums, booleans, locations, tags)

Deleted fields from persona table:
1. Hard condition fields (moved to profiles):
   - self_gender, self_age, self_city, self_district, self_height, self_education, self_income_wan, self_job
   - self_marital_status, self_has_children, self_children_count, self_children_living_with_self
   - self_smoking, self_drinking, self_relationship_goal
   - target_gender (期望对象性别)

2. Non-quantifiable fields (deleted, should be in vector/conversation_summaries):
   - self_life_rhythm, self_work_pattern, self_expression_style (主观描述)
   - preferred_traits, disliked_traits (性格特质偏好)
   - persona_summary_internal, preference_summary_internal (文本摘要)
   - public_profile_summary_draft, public_preference_summary_draft (文本摘要)
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


# Hard condition fields to remove from persona table (moved to profiles)
DELETED_PERSONA_HARD_CONDITION_FIELDS = [
    # Basic facts (hard conditions)
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    # Family facts (hard conditions)
    "self_marital_status",
    "self_has_children",
    "self_children_count",
    "self_children_living_with_self",
    # Lifestyle habits (hard conditions - user confirmed)
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
    # Search preference (hard condition)
    "target_gender",  # 期望对象性别 - 移动到 profiles 表
]

# Non-quantifiable fields to remove from persona table (deleted, not moved)
DELETED_PERSONA_NON_QUANTIFIABLE_FIELDS = [
    # Subjective descriptions (主观描述)
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
    # Personality trait preferences (性格特质偏好)
    "preferred_traits",
    "disliked_traits",
    # Text summaries (文本摘要 - should be in vector/conversation_summaries)
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
]


def _persona_table(context: MigrationContext) -> str:
    return str(context.options.get("persona_table") or "user_personas")


def _profile_table(context: MigrationContext) -> str:
    return str(context.options.get("profile_table") or "profiles")


def _apply(conn: Any, context: MigrationContext) -> None:
    """Remove duplicate hard condition fields and non-quantifiable fields from persona table."""
    persona_table = _persona_table(context)
    profile_table = _profile_table(context)

    with conn.cursor() as cursor:
        # Step 1: Add target_gender to profiles table (if not exists)
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'target_gender'
            LIMIT 1
            """,
            (profile_table,),
        )
        if cursor.fetchone() is None:
            # Add target_gender column to profiles table
            cursor.execute(
                f"ALTER TABLE `{profile_table}` "
                f"ADD COLUMN `target_gender` VARCHAR(8) NULL COMMENT '期望对象性别（硬条件）'"
            )

        # Step 2: Remove hard condition fields from persona table
        for column in DELETED_PERSONA_HARD_CONDITION_FIELDS:
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
                (persona_table, column),
            )
            if cursor.fetchone() is None:
                # Column doesn't exist, skip
                continue
            # Drop the column
            cursor.execute(f"ALTER TABLE `{persona_table}` DROP COLUMN `{column}`")

        # Step 3: Remove non-quantifiable fields from persona table
        for column in DELETED_PERSONA_NON_QUANTIFIABLE_FIELDS:
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
                (persona_table, column),
            )
            if cursor.fetchone() is None:
                # Column doesn't exist, skip
                continue
            # Drop the column
            cursor.execute(f"ALTER TABLE `{persona_table}` DROP COLUMN `{column}`")


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    """Validate that fields have been properly migrated."""
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    persona_table = _persona_table(context)
    profile_table = _profile_table(context)

    with conn.cursor() as cursor:
        # Check if tables exist
        for table in [persona_table, profile_table]:
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

        # Check that target_gender exists in profiles table
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'target_gender'
            LIMIT 1
            """,
            (profile_table,),
        )
        if cursor.fetchone() is None:
            issues["missing_columns"].append(f"{profile_table}.target_gender:should_be_added")

        # Check that hard condition fields are removed from persona table
        for column in DELETED_PERSONA_HARD_CONDITION_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column),
            )
            if cursor.fetchone() is not None:
                # Column still exists - incompatible
                issues["incompatible_columns"].append(f"{persona_table}.{column}:should_be_removed")

        # Check that non-quantifiable fields are removed from persona table
        for column in DELETED_PERSONA_NON_QUANTIFIABLE_FIELDS:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                (persona_table, column),
            )
            if cursor.fetchone() is not None:
                # Column still exists - incompatible
                issues["incompatible_columns"].append(f"{persona_table}.{column}:non_quantifiable_should_be_removed")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0009_remove_duplicate_hard_condition_fields",
    description="Remove duplicate hard condition fields and non-quantifiable fields from persona table (architecture refactoring)",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)