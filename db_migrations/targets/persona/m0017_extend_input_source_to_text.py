"""Extend input_source column in reference_face_search_jobs to TEXT type.

The input_source field stores the source URL or identifier for reference
face search jobs. URLs with query parameters or base64-encoded data can
exceed VARCHAR(255) limits, causing insertion failures.

This migration changes the column type to TEXT to accommodate longer URLs.

Note: This table is in the 'her' database, not 'persona'.
"""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import her_scope


def _apply(conn: Any, _context: MigrationContext) -> None:
    with conn.cursor() as cursor:
        # 检查表是否存在
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'reference_face_search_jobs'
            LIMIT 1
            """
        )
        if cursor.fetchone() is None:
            # 表不存在,跳过迁移
            return

        # 修改字段类型
        cursor.execute(
            """
            ALTER TABLE `reference_face_search_jobs`
            MODIFY COLUMN `input_source` TEXT DEFAULT NULL
            """
        )


def _validate(conn: Any, _context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
        "missing_indexes": [],
        "missing_unique_keys": [],
    }

    with conn.cursor() as cursor:
        # 检查表是否存在
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'reference_face_search_jobs'
            LIMIT 1
            """
        )
        if cursor.fetchone() is None:
            issues["missing_tables"].append("reference_face_search_jobs")
            return issues

        # 检查字段类型是否正确
        cursor.execute(
            """
            SELECT DATA_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'reference_face_search_jobs'
              AND COLUMN_NAME = 'input_source'
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            issues["missing_columns"].append("reference_face_search_jobs.input_source")
        elif row[0].lower() not in ("text", "blob"):
            issues["incompatible_columns"].append(
                f"reference_face_search_jobs.input_source is {row[0]}, expected TEXT"
            )

    return issues


MIGRATION = MigrationSpec(
    migration_id="0017_extend_input_source_to_text",
    description="Extend input_source column in reference_face_search_jobs to TEXT type",
    scope_fn=her_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)