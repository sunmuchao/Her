"""Expand auth/account phone columns to fit encrypted values."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

_PHONE_COLUMNS = (
    ("user_accounts", "primary_phone", "VARCHAR(255) NULL"),
    ("auth_otp_challenges", "phone", "VARCHAR(255) NOT NULL"),
    ("auth_login_events", "phone", "VARCHAR(255) NULL"),
    ("auth_one_tap_attempts", "verified_phone", "VARCHAR(255) NULL"),
)


def _current_column_type(mysql_conn, table_name: str, column_name: str) -> str | None:
    cursor = mysql_conn.cursor()
    cursor.execute(
        """
        SELECT COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    if isinstance(row, dict):
        return str(row.get("COLUMN_TYPE") or "").strip().lower() or None
    return str(row[0] or "").strip().lower() or None


def apply(mysql_conn, _context: MigrationContext) -> None:
    cursor = mysql_conn.cursor()
    try:
        for table_name, column_name, target_sql in _PHONE_COLUMNS:
            current = _current_column_type(mysql_conn, table_name, column_name)
            if current == "varchar(255)":
                continue
            cursor.execute(f"ALTER TABLE `{table_name}` MODIFY COLUMN `{column_name}` {target_sql}")
        mysql_conn.commit()
    finally:
        cursor.close()


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    issues = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_unique_keys": [],
        "missing_indexes": [],
        "missing_views": [],
        "incompatible_columns": [],
        "missing_migrations": [],
        "checksum_mismatches": [],
        "unexpected_migrations": [],
    }
    for table_name, column_name, _target_sql in _PHONE_COLUMNS:
        current = _current_column_type(mysql_conn, table_name, column_name)
        if current is None:
            issues["missing_columns"].append(f"{table_name}.{column_name}")
        elif current != "varchar(255)":
            issues["incompatible_columns"].append(f"{table_name}.{column_name}:{current}")
    return issues


MIGRATION = MigrationSpec(
    migration_id="0007_expand_encrypted_phone_columns",
    description="Expand encrypted phone columns to varchar(255)",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
