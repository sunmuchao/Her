"""Normalize legacy face side tables to the current schema expected by runtime code."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


PROFILE_FACE_EMBEDDINGS_TABLE = "profile_face_embeddings"
VERIFIED_FACE_ANCHORS_TABLE = "verified_face_anchors"


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


_EMBEDDING_COLUMNS = {
    "embedding_type": "VARCHAR(32) NOT NULL DEFAULT 'primary_face'",
    "photo_set_version": "BIGINT NOT NULL DEFAULT 1",
    "embedding_dim": "INT NOT NULL DEFAULT 0",
    "embedding_json": "JSON DEFAULT NULL",
    "quality_score": "DECIMAL(6,2) DEFAULT NULL",
    "confidence_score": "DECIMAL(6,2) DEFAULT NULL",
    "extractor_version": "VARCHAR(64) DEFAULT NULL",
}

_ANCHOR_COLUMNS = {
    "verification_asset_type": "VARCHAR(32) NOT NULL DEFAULT 'photo'",
    "anchor_source": "VARCHAR(255) DEFAULT NULL",
    "anchor_version": "VARCHAR(64) DEFAULT NULL",
    "quality_score": "DECIMAL(6,2) DEFAULT NULL",
    "confidence_score": "DECIMAL(6,2) DEFAULT NULL",
    "environment_bias_score": "DECIMAL(6,2) DEFAULT NULL",
    "embedding_json": "JSON DEFAULT NULL",
    "metadata_json": "JSON DEFAULT NULL",
    "is_active": "TINYINT(1) NOT NULL DEFAULT 1",
}


def _apply(conn: Any, _context: MigrationContext) -> None:
    with conn.cursor() as cursor:
        if _table_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE):
            for column_name, column_type in _EMBEDDING_COLUMNS.items():
                if not _column_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE, column_name):
                    cursor.execute(
                        f"ALTER TABLE `{PROFILE_FACE_EMBEDDINGS_TABLE}` ADD COLUMN `{column_name}` {column_type}"
                    )
            if _column_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE, "photo_set_version"):
                cursor.execute(
                    f"ALTER TABLE `{PROFILE_FACE_EMBEDDINGS_TABLE}` MODIFY COLUMN `photo_set_version` BIGINT NOT NULL DEFAULT 1"
                )
            cursor.execute(
                f"""
                UPDATE `{PROFILE_FACE_EMBEDDINGS_TABLE}`
                SET `embedding_type` = COALESCE(NULLIF(`embedding_type`, ''), 'primary_face'),
                    `embedding_dim` = CASE
                        WHEN `embedding_dim` IS NULL OR `embedding_dim` = 0 THEN COALESCE(`face_embedding_dimension`, 0)
                        ELSE `embedding_dim`
                    END,
                    `confidence_score` = COALESCE(`confidence_score`, `face_detection_confidence`),
                    `extractor_version` = COALESCE(NULLIF(`extractor_version`, ''), `face_embedding_model`),
                    `embedding_json` = CASE
                        WHEN `embedding_json` IS NULL AND `face_embedding_json` IS NOT NULL THEN CAST(`face_embedding_json` AS JSON)
                        ELSE `embedding_json`
                    END
                """
            )
            if not _index_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE, "uniq_profile_face_embeddings_profile_type"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{PROFILE_FACE_EMBEDDINGS_TABLE}`
                    ADD UNIQUE KEY `uniq_profile_face_embeddings_profile_type` (`profile_id`, `embedding_type`)
                    """
                )
            if not _index_exists(cursor, PROFILE_FACE_EMBEDDINGS_TABLE, "idx_profile_face_embeddings_updated_at"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{PROFILE_FACE_EMBEDDINGS_TABLE}`
                    ADD KEY `idx_profile_face_embeddings_updated_at` (`updated_at`)
                    """
                )

        if _table_exists(cursor, VERIFIED_FACE_ANCHORS_TABLE):
            for column_name, column_type in _ANCHOR_COLUMNS.items():
                if not _column_exists(cursor, VERIFIED_FACE_ANCHORS_TABLE, column_name):
                    cursor.execute(
                        f"ALTER TABLE `{VERIFIED_FACE_ANCHORS_TABLE}` ADD COLUMN `{column_name}` {column_type}"
                    )
            cursor.execute(
                f"""
                UPDATE `{VERIFIED_FACE_ANCHORS_TABLE}`
                SET `verification_asset_type` = COALESCE(NULLIF(`verification_asset_type`, ''), 'photo'),
                    `anchor_source` = COALESCE(NULLIF(`anchor_source`, ''), `video_url`),
                    `anchor_version` = COALESCE(NULLIF(`anchor_version`, ''), CONCAT('legacy-anchor:', `profile_id`, ':', `id`)),
                    `quality_score` = COALESCE(`quality_score`, `video_authenticity_score`),
                    `confidence_score` = COALESCE(`confidence_score`, `liveness_detection_score`),
                    `embedding_json` = CASE
                        WHEN `embedding_json` IS NULL AND `anchor_face_embedding_json` IS NOT NULL THEN CAST(`anchor_face_embedding_json` AS JSON)
                        ELSE `embedding_json`
                    END,
                    `metadata_json` = COALESCE(
                        `metadata_json`,
                        JSON_OBJECT(
                            'verification_case_id', `verification_case_id`,
                            'verification_status', `verification_status`,
                            'verification_level', `verification_level`,
                            'reviewer_id', `reviewer_id`,
                            'review_note', `review_note`,
                            'video_duration_seconds', `video_duration_seconds`
                        )
                    ),
                    `is_active` = COALESCE(`is_active`, 1)
                """
            )
            if not _index_exists(cursor, VERIFIED_FACE_ANCHORS_TABLE, "uniq_verified_face_anchors_profile_version"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{VERIFIED_FACE_ANCHORS_TABLE}`
                    ADD UNIQUE KEY `uniq_verified_face_anchors_profile_version` (`profile_id`, `anchor_version`)
                    """
                )
            if not _index_exists(cursor, VERIFIED_FACE_ANCHORS_TABLE, "idx_verified_face_anchors_profile_active"):
                cursor.execute(
                    f"""
                    ALTER TABLE `{VERIFIED_FACE_ANCHORS_TABLE}`
                    ADD KEY `idx_verified_face_anchors_profile_active` (`profile_id`, `is_active`, `updated_at`)
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
        for table_name, columns, required_indexes in (
            (
                PROFILE_FACE_EMBEDDINGS_TABLE,
                _EMBEDDING_COLUMNS,
                {"uniq_profile_face_embeddings_profile_type", "idx_profile_face_embeddings_updated_at"},
            ),
            (
                VERIFIED_FACE_ANCHORS_TABLE,
                _ANCHOR_COLUMNS,
                {"uniq_verified_face_anchors_profile_version", "idx_verified_face_anchors_profile_active"},
            ),
        ):
            if not _table_exists(cursor, table_name):
                issues["missing_tables"].append(table_name)
                continue
            for column_name in columns:
                if not _column_exists(cursor, table_name, column_name):
                    issues["missing_columns"].append(f"{table_name}.{column_name}")
            for index_name in required_indexes:
                if not _index_exists(cursor, table_name, index_name):
                    issues["missing_indexes"].append(f"{table_name}.{index_name}")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0020_normalize_legacy_face_side_tables",
    description="Normalize legacy profile_face_embeddings and verified_face_anchors tables to the current runtime schema",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
