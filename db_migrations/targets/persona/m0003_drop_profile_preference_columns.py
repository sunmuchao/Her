"""Drop deprecated preference/matcher columns from profiles (§13.1.2 phase-4)."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope
from match_domain.deprecated_profile_columns import DEPRECATED_PROFILE_COLUMNS


def _profile_table(context: MigrationContext) -> str:
    return str(context.options.get("profile_table") or "profiles")


def _apply(conn: Any, context: MigrationContext) -> None:
    table = _profile_table(context)
    with conn.cursor() as cursor:
        for column in DEPRECATED_PROFILE_COLUMNS:
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
                continue
            cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


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

        for column in DEPRECATED_PROFILE_COLUMNS:
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
                issues["incompatible_columns"].append(f"{table}.{column}")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0003_drop_profile_preference_columns",
    description="Drop deprecated profiles preference/matcher columns",
    scope_fn=default_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
