"""Add assessment_results table for completed assessment snapshots."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope


def _results_table(context: MigrationContext) -> str:
    return str(context.options.get("assessment_results_table") or "assessment_results")


def _apply(conn: Any, context: MigrationContext) -> None:
    table = _results_table(context)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{table}` (
              id BIGINT PRIMARY KEY AUTO_INCREMENT,
              user_key VARCHAR(64) NOT NULL,
              assessment_id VARCHAR(64) NOT NULL,
              assessment_type VARCHAR(32) NOT NULL,
              result_version VARCHAR(32) NOT NULL DEFAULT 'v1',
              summary_json JSON DEFAULT NULL,
              raw_result_json JSON NOT NULL,
              interpretation_json JSON DEFAULT NULL,
              source_channel VARCHAR(32) NOT NULL DEFAULT 'assessment',
              completed_at DATETIME NOT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uk_assessment_id (assessment_id),
              KEY idx_user_type_time (user_key, assessment_type, completed_at DESC)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """
        )


def _validate(conn: Any, context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }
    table = _results_table(context)
    with conn.cursor() as cursor:
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

        for column in (
            "user_key",
            "assessment_id",
            "assessment_type",
            "result_version",
            "summary_json",
            "raw_result_json",
            "interpretation_json",
            "source_channel",
            "completed_at",
            "created_at",
        ):
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
                issues["missing_columns"].append(f"{table}.{column}")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0007_add_assessment_results",
    description="Add assessment_results table for completed assessment snapshots",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
