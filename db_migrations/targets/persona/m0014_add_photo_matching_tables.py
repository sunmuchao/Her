"""Add photo-derived matching tables to persona database."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


PHOTO_FEATURES_TABLE = "profile_photo_features"
USER_APPEARANCE_PREFERENCES_TABLE = "user_appearance_preferences"
APPEARANCE_FEEDBACK_EVENTS_TABLE = "appearance_feedback_events"


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
        if not _table_exists(cursor, PHOTO_FEATURES_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{PHOTO_FEATURES_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `primary_photo_id` BIGINT DEFAULT NULL,
                  `photo_set_version` INT NOT NULL DEFAULT 1,
                  `analysis_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `embedding_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `face_score_global` DECIMAL(6,2) DEFAULT NULL,
                  `appearance_score_global` DECIMAL(6,2) DEFAULT NULL,
                  `photo_quality_score` DECIMAL(6,2) DEFAULT NULL,
                  `photo_authenticity_score` DECIMAL(6,2) DEFAULT NULL,
                  `mature_score` DECIMAL(6,2) DEFAULT NULL,
                  `clean_score` DECIMAL(6,2) DEFAULT NULL,
                  `gentle_score` DECIMAL(6,2) DEFAULT NULL,
                  `sunny_score` DECIMAL(6,2) DEFAULT NULL,
                  `stylish_score` DECIMAL(6,2) DEFAULT NULL,
                  `appearance_summary` TEXT,
                  `appearance_tags_json` JSON DEFAULT NULL,
                  `analysis_model` VARCHAR(64) DEFAULT NULL,
                  `embedding_model` VARCHAR(64) DEFAULT NULL,
                  `last_error` VARCHAR(255) DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_profile_photo_features_profile_id` (`profile_id`),
                  KEY `idx_profile_photo_features_status` (`analysis_status`, `embedding_status`),
                  KEY `idx_profile_photo_features_updated_at` (`updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{USER_APPEARANCE_PREFERENCES_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `user_key` VARCHAR(64) NOT NULL,
                  `profile_id` BIGINT DEFAULT NULL,
                  `preference_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `embedding_status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `preferred_mature_score` DECIMAL(6,2) DEFAULT NULL,
                  `preferred_clean_score` DECIMAL(6,2) DEFAULT NULL,
                  `preferred_gentle_score` DECIMAL(6,2) DEFAULT NULL,
                  `preferred_sunny_score` DECIMAL(6,2) DEFAULT NULL,
                  `preferred_stylish_score` DECIMAL(6,2) DEFAULT NULL,
                  `appearance_preference_summary` TEXT,
                  `positive_sample_count` INT NOT NULL DEFAULT 0,
                  `negative_sample_count` INT NOT NULL DEFAULT 0,
                  `last_feedback_at` DATETIME DEFAULT NULL,
                  `last_error` VARCHAR(255) DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_user_appearance_preferences_user_key` (`user_key`),
                  KEY `idx_user_appearance_preferences_status` (`preference_status`, `embedding_status`),
                  KEY `idx_user_appearance_preferences_updated_at` (`updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, APPEARANCE_FEEDBACK_EVENTS_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{APPEARANCE_FEEDBACK_EVENTS_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `user_key` VARCHAR(64) NOT NULL,
                  `profile_id` BIGINT NOT NULL,
                  `candidate_profile_id` BIGINT NOT NULL,
                  `event_type` VARCHAR(64) NOT NULL,
                  `event_weight` DECIMAL(6,2) NOT NULL DEFAULT 0,
                  `scene` VARCHAR(32) NOT NULL DEFAULT 'discovery',
                  `session_id` VARCHAR(64) DEFAULT NULL,
                  `metadata_json` JSON DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  KEY `idx_appearance_feedback_events_user_created` (`user_key`, `created_at`),
                  KEY `idx_appearance_feedback_events_candidate` (`candidate_profile_id`, `created_at`),
                  KEY `idx_appearance_feedback_events_scene` (`scene`, `event_type`)
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
        PHOTO_FEATURES_TABLE: {
            "profile_id",
            "appearance_score_global",
            "photo_quality_score",
            "photo_authenticity_score",
            "appearance_summary",
            "appearance_tags_json",
            "analysis_status",
            "embedding_status",
        },
        USER_APPEARANCE_PREFERENCES_TABLE: {
            "user_key",
            "preferred_mature_score",
            "preferred_clean_score",
            "preferred_gentle_score",
            "preferred_sunny_score",
            "preferred_stylish_score",
            "appearance_preference_summary",
            "positive_sample_count",
            "negative_sample_count",
        },
        APPEARANCE_FEEDBACK_EVENTS_TABLE: {
            "user_key",
            "profile_id",
            "candidate_profile_id",
            "event_type",
            "event_weight",
            "scene",
        },
    }
    expected_indexes = {
        PHOTO_FEATURES_TABLE: {
            "uniq_profile_photo_features_profile_id",
            "idx_profile_photo_features_status",
        },
        USER_APPEARANCE_PREFERENCES_TABLE: {
            "uniq_user_appearance_preferences_user_key",
            "idx_user_appearance_preferences_status",
        },
        APPEARANCE_FEEDBACK_EVENTS_TABLE: {
            "idx_appearance_feedback_events_user_created",
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
    migration_id="0014_add_photo_matching_tables",
    description="Add photo-derived candidate features, user appearance preferences, and appearance feedback event tables",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
