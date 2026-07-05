"""Add face attributes, embeddings, verified anchors, consistency, and search job tables."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


PROFILE_FACE_ATTRIBUTES_TABLE = "profile_face_attributes"
PROFILE_FACE_EMBEDDINGS_TABLE = "profile_face_embeddings"
VERIFIED_FACE_ANCHORS_TABLE = "verified_face_anchors"
FACE_CONSISTENCY_SCORES_TABLE = "face_consistency_scores"
REFERENCE_FACE_SEARCH_JOBS_TABLE = "reference_face_search_jobs"


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
        if not _table_exists(cursor, PROFILE_FACE_ATTRIBUTES_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{PROFILE_FACE_ATTRIBUTES_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `primary_photo_id` BIGINT DEFAULT NULL,
                  `face_count` INT NOT NULL DEFAULT 1,
                  `dominant_face_index` INT NOT NULL DEFAULT 0,
                  `eye_size_score` DECIMAL(6,2) DEFAULT NULL,
                  `face_roundness_score` DECIMAL(6,2) DEFAULT NULL,
                  `jaw_definition_score` DECIMAL(6,2) DEFAULT NULL,
                  `smile_intensity_score` DECIMAL(6,2) DEFAULT NULL,
                  `skin_clarity_score` DECIMAL(6,2) DEFAULT NULL,
                  `style_clean_score` DECIMAL(6,2) DEFAULT NULL,
                  `style_gentle_score` DECIMAL(6,2) DEFAULT NULL,
                  `style_sunny_score` DECIMAL(6,2) DEFAULT NULL,
                  `style_stylish_score` DECIMAL(6,2) DEFAULT NULL,
                  `youthfulness_score` DECIMAL(6,2) DEFAULT NULL,
                  `attributes_json` JSON DEFAULT NULL,
                  `extractor_version` VARCHAR(64) DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_profile_face_attributes_profile_id` (`profile_id`),
                  KEY `idx_profile_face_attributes_updated_at` (`updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{PROFILE_FACE_EMBEDDINGS_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `embedding_type` VARCHAR(32) NOT NULL DEFAULT 'primary_face',
                  `photo_set_version` INT NOT NULL DEFAULT 1,
                  `embedding_dim` INT NOT NULL DEFAULT 0,
                  `embedding_json` JSON NOT NULL,
                  `quality_score` DECIMAL(6,2) DEFAULT NULL,
                  `confidence_score` DECIMAL(6,2) DEFAULT NULL,
                  `extractor_version` VARCHAR(64) DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_profile_face_embeddings_profile_type` (`profile_id`, `embedding_type`),
                  KEY `idx_profile_face_embeddings_updated_at` (`updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, VERIFIED_FACE_ANCHORS_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{VERIFIED_FACE_ANCHORS_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `verification_asset_type` VARCHAR(32) NOT NULL DEFAULT 'photo',
                  `anchor_source` VARCHAR(255) DEFAULT NULL,
                  `anchor_version` VARCHAR(64) NOT NULL,
                  `quality_score` DECIMAL(6,2) DEFAULT NULL,
                  `confidence_score` DECIMAL(6,2) DEFAULT NULL,
                  `environment_bias_score` DECIMAL(6,2) DEFAULT NULL,
                  `embedding_json` JSON DEFAULT NULL,
                  `metadata_json` JSON DEFAULT NULL,
                  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_verified_face_anchors_profile_version` (`profile_id`, `anchor_version`),
                  KEY `idx_verified_face_anchors_profile_active` (`profile_id`, `is_active`, `updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, FACE_CONSISTENCY_SCORES_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{FACE_CONSISTENCY_SCORES_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `anchor_id` BIGINT DEFAULT NULL,
                  `consistency_score` DECIMAL(6,2) DEFAULT NULL,
                  `threshold_score` DECIMAL(6,2) DEFAULT NULL,
                  `confidence_weight` DECIMAL(6,2) DEFAULT NULL,
                  `environment_gap_score` DECIMAL(6,2) DEFAULT NULL,
                  `risk_level` VARCHAR(16) DEFAULT NULL,
                  `risk_flags_json` JSON DEFAULT NULL,
                  `detail_json` JSON DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uniq_face_consistency_scores_profile_id` (`profile_id`),
                  KEY `idx_face_consistency_scores_risk_level` (`risk_level`, `updated_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        if not _table_exists(cursor, REFERENCE_FACE_SEARCH_JOBS_TABLE):
            cursor.execute(
                f"""
                CREATE TABLE `{REFERENCE_FACE_SEARCH_JOBS_TABLE}` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `requester_user_key` VARCHAR(64) NOT NULL,
                  `requester_profile_id` BIGINT DEFAULT NULL,
                  `job_type` VARCHAR(32) NOT NULL DEFAULT 'face_similarity',
                  `input_source` VARCHAR(255) DEFAULT NULL,
                  `input_face_embedding_json` JSON DEFAULT NULL,
                  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
                  `result_count` INT NOT NULL DEFAULT 0,
                  `filters_json` JSON DEFAULT NULL,
                  `result_profile_ids_json` JSON DEFAULT NULL,
                  `error_message` VARCHAR(255) DEFAULT NULL,
                  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  KEY `idx_reference_face_search_jobs_requester` (`requester_user_key`, `created_at`),
                  KEY `idx_reference_face_search_jobs_status` (`status`, `updated_at`)
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
        PROFILE_FACE_ATTRIBUTES_TABLE: {
            "profile_id",
            "eye_size_score",
            "face_roundness_score",
            "jaw_definition_score",
            "smile_intensity_score",
            "youthfulness_score",
            "attributes_json",
        },
        PROFILE_FACE_EMBEDDINGS_TABLE: {
            "profile_id",
            "embedding_type",
            "embedding_json",
            "quality_score",
            "confidence_score",
        },
        VERIFIED_FACE_ANCHORS_TABLE: {
            "profile_id",
            "anchor_version",
            "quality_score",
            "confidence_score",
            "environment_bias_score",
            "embedding_json",
        },
        FACE_CONSISTENCY_SCORES_TABLE: {
            "profile_id",
            "consistency_score",
            "threshold_score",
            "confidence_weight",
            "risk_flags_json",
        },
        REFERENCE_FACE_SEARCH_JOBS_TABLE: {
            "requester_user_key",
            "job_type",
            "input_face_embedding_json",
            "status",
            "result_profile_ids_json",
        },
    }
    expected_indexes = {
        PROFILE_FACE_ATTRIBUTES_TABLE: {"uniq_profile_face_attributes_profile_id"},
        PROFILE_FACE_EMBEDDINGS_TABLE: {"uniq_profile_face_embeddings_profile_type"},
        VERIFIED_FACE_ANCHORS_TABLE: {"uniq_verified_face_anchors_profile_version"},
        FACE_CONSISTENCY_SCORES_TABLE: {"uniq_face_consistency_scores_profile_id"},
        REFERENCE_FACE_SEARCH_JOBS_TABLE: {"idx_reference_face_search_jobs_requester"},
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
    migration_id="0016_add_face_anchor_and_search_tables",
    description="Add face attributes, embeddings, verified anchors, consistency, and reference search job tables",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
