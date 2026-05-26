"""Add source_channel to persona observations."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


def _apply(conn: Any, _context: MigrationContext) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'user_persona_observations'
              AND COLUMN_NAME = 'source_channel'
            """
        )
        row = cursor.fetchone()
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if int(cnt or 0) == 0:
            cursor.execute(
                """
                ALTER TABLE user_persona_observations
                ADD COLUMN source_channel VARCHAR(64) DEFAULT NULL
                AFTER conversation_ref
                """
            )


def _validate(conn: Any, _context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'user_persona_observations'
              AND COLUMN_NAME = 'source_channel'
            LIMIT 1
            """
        )
        if cursor.fetchone() is None:
            issues["missing_columns"].append("user_persona_observations.source_channel")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0002_add_observation_source_channel",
    description="Add source_channel to user_persona_observations",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
