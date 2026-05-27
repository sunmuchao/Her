"""Add profiles.sexual_orientation and expand persona observation source_type enum."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


def _profile_table(context: MigrationContext) -> str:
    return str(context.options.get("profile_table") or "profiles")


def _apply(conn: Any, context: MigrationContext) -> None:
    table = _profile_table(context)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'sexual_orientation'
            """,
            (table,),
        )
        row = cursor.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if int(cnt or 0) == 0:
            cursor.execute(
                f"""
                ALTER TABLE `{table}`
                ADD COLUMN sexual_orientation VARCHAR(16) DEFAULT NULL
                COMMENT 'like_male|like_female|both'
                AFTER gender
                """
            )

        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'user_persona_observations'
            LIMIT 1
            """
        )
        if cursor.fetchone() is not None:
            cursor.execute(
                """
                ALTER TABLE user_persona_observations
                MODIFY COLUMN source_type ENUM(
                    'explicit',
                    'strong_inference',
                    'weak_inference',
                    'profile_form',
                    'explicit_confirmation'
                ) NOT NULL
                """
            )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    table = _profile_table(context)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'sexual_orientation'
            LIMIT 1
            """,
            (table,),
        )
        if cursor.fetchone() is None:
            issues["missing_columns"].append(f"{table}.sexual_orientation")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0005_onboarding_profile_fields",
    description="Add profiles.sexual_orientation and persona observation source_type values",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
