"""Add retry/state fields and version snapshots for photo feature analysis."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


PHOTO_FEATURES_TABLE = "profile_photo_features"
PHOTO_FEATURE_VERSIONS_TABLE = "profile_photo_feature_versions"


def _table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: Any, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor: Any, table_name: str, index_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table_name, index_name),
    )
    return cursor.fetchone() is not None


def _apply(conn: Any, _context: MigrationContext) -> None:
    with conn.cursor() as cursor:
        if _table_exists(cursor, PHOTO_FEATURES_TABLE):
            if not _column_exists(cursor, PHOTO_FEATURES_TABLE, "retry_count"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{PHOTO_FEATURES_TABLE}`
                    ADD COLUMN `retry_count` INT NOT NULL DEFAULT 0
                    AFTER `last_error`
                    """
                )
            if not _column_exists(cursor, PHOTO_FEATURES_TABLE, "last_transition_at"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{PHOTO_FEATURES_TABLE}`
                    ADD COLUMN `last_transition_at` DATETIME DEFAULT NULL
                    AFTER `retry_count`
                    """
                )
            if not _index_exists(cursor, PHOTO_FEATURES_TABLE, "idx_profile_photo_features_retry"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{PHOTO_FEATURES_TABLE}`
                    ADD KEY `idx_profile_photo_features_retry` (`analysis_status`, `retry_count`, `updated_at`)
                    """
                )

        if not _table_exists(cursor, PHOTO_FEATURE_VERSIONS_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{PHOTO_FEATURE_VERSIONS_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_set_version` INT NOT NULL DEFAULT 1,
                  `analysis_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `trigger_reason` VARCHAR(64) DEFAULT NULL,
                  `snapshot_json` JSON NOT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  KEY `idx_profile_photo_feature_versions_profile_created` (`profile_id`, `created_at`),
                  KEY `idx_profile_photo_feature_versions_status` (`analysis_status`, `created_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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

    expected_columns = {
        PHOTO_FEATURES_TABLE: {"retry_count", "last_transition_at"},
        PHOTO_FEATURE_VERSIONS_TABLE: {
            "profile_id",
            "photo_set_version",
            "analysis_status",
            "trigger_reason",
            "snapshot_json",
        },
    }
    expected_indexes = {
        PHOTO_FEATURES_TABLE: {"idx_profile_photo_features_retry"},
        PHOTO_FEATURE_VERSIONS_TABLE: {
            "idx_profile_photo_feature_versions_profile_created",
            "idx_profile_photo_feature_versions_status",
        },
    }

    with conn.cursor() as cursor:
        for table_name, column_names in expected_columns.items():
            if not _table_exists(cursor, table_name):
                issues["missing_tables"].append(table_name)
                continue
            for column_name in column_names:
                if not _column_exists(cursor, table_name, column_name):
                    issues["missing_columns"].append(f"{table_name}.{column_name}")
            for index_name in expected_indexes.get(table_name, set()):
                if not _index_exists(cursor, table_name, index_name):
                    issues["missing_indexes"].append(f"{table_name}.{index_name}")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0015_add_photo_feature_state_and_versions",
    description="Add retry/state fields and version snapshots for photo feature analysis",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
