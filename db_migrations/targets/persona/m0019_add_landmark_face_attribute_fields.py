"""Extend profile_face_attributes for landmark-derived attributes and metadata."""

from __future__ import annotations

from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import persona_scope


PROFILE_FACE_ATTRIBUTES_TABLE = "profile_face_attributes"


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


_NEW_COLUMNS = {
    "eye_distance_score": "DECIMAL(6,2) DEFAULT NULL",
    "nose_height_score": "DECIMAL(6,2) DEFAULT NULL",
    "nose_width_score": "DECIMAL(6,2) DEFAULT NULL",
    "lip_thickness_score": "DECIMAL(6,2) DEFAULT NULL",
    "lip_width_score": "DECIMAL(6,2) DEFAULT NULL",
    "face_shape_type": "VARCHAR(32) DEFAULT NULL",
    "jawline_definition_score": "DECIMAL(6,2) DEFAULT NULL",
    "forehead_height_score": "DECIMAL(6,2) DEFAULT NULL",
    "chin_prominence_score": "DECIMAL(6,2) DEFAULT NULL",
    "cheekbone_prominence_score": "DECIMAL(6,2) DEFAULT NULL",
    "attribute_source": "VARCHAR(32) DEFAULT NULL",
    "attribute_confidence": "DECIMAL(6,4) DEFAULT NULL",
    "attribute_error_code": "VARCHAR(64) DEFAULT NULL",
    "attribute_error_message": "VARCHAR(255) DEFAULT NULL",
    "analyzed_photo_url": "VARCHAR(512) DEFAULT NULL",
    "analyzed_photo_version": "BIGINT DEFAULT NULL",
}


def _apply(conn: Any, _context: MigrationContext) -> None:
    with conn.cursor() as cursor:
        if not _table_exists(cursor, PROFILE_FACE_ATTRIBUTES_TABLE):
            raise RuntimeError(f"missing required table: {PROFILE_FACE_ATTRIBUTES_TABLE}")
        for column_name, column_type in _NEW_COLUMNS.items():
            if _column_exists(cursor, PROFILE_FACE_ATTRIBUTES_TABLE, column_name):
                continue
            cursor.execute(
                f"ALTER TABLE `{PROFILE_FACE_ATTRIBUTES_TABLE}` ADD COLUMN `{column_name}` {column_type}"
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
        if not _table_exists(cursor, PROFILE_FACE_ATTRIBUTES_TABLE):
            issues["missing_tables"].append(PROFILE_FACE_ATTRIBUTES_TABLE)
            return issues
        for column_name in _NEW_COLUMNS:
            if not _column_exists(cursor, PROFILE_FACE_ATTRIBUTES_TABLE, column_name):
                issues["missing_columns"].append(f"{PROFILE_FACE_ATTRIBUTES_TABLE}.{column_name}")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0019_add_landmark_face_attribute_fields",
    description="Add real landmark attribute columns and metadata to profile_face_attributes",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)
