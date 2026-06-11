#!/usr/bin/env python
"""Migrate existing plaintext sensitive data to encrypted format.

This script encrypts sensitive data in the database:
- user_accounts.primary_phone
- user_account_identities.identity_value (phone/wechat types)
- wechat_accounts.openid, unionid

Usage:
    # Check what needs to be migrated (dry run)
    python scripts/migrate_sensitive_data_encryption.py --dry-run

    # Run migration
    python scripts/migrate_sensitive_data_encryption.py

    # Run with specific database
    python scripts/migrate_sensitive_data_encryption.py --dsn mysql://root@127.0.0.1:3307/her_chat

Prerequisites:
    - HER_SENSITIVE_DATA_KEY must be set in environment
    - Database backup recommended before migration
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Bootstrap project path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from external_systems.partner_chat_system.chat_system.sensitive_crypto import (
    SensitiveDataCrypto,
    MissingEncryptionKeyError,
)
from external_systems.partner_chat_system.chat_system.storage import connect_db
from outer_system_mysql_schema import parse_mysql_dsn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Tables and columns to migrate
MIGRATION_TARGETS = [
    {
        "table": "user_accounts",
        "columns": ["primary_phone"],
        "where": "primary_phone IS NOT NULL AND primary_phone != ''",
        "batch_size": 100,
    },
    {
        "table": "user_account_identities",
        "columns": ["identity_value"],
        "where": "identity_type IN ('phone', 'wechat_openid', 'wechat_unionid') AND identity_value IS NOT NULL AND identity_value != ''",
        "batch_size": 100,
        "encrypt_func": "encrypt_identity_value",
    },
    {
        "table": "wechat_accounts",
        "columns": ["openid", "unionid"],
        "where": "openid IS NOT NULL AND openid != ''",
        "batch_size": 100,
    },
]


def is_encrypted(value: str | None) -> bool:
    """Check if value already has encryption prefix."""
    if value is None:
        return False
    return str(value).startswith("enc:")


def encrypt_phone(value: str) -> str:
    """Encrypt phone number."""
    return SensitiveDataCrypto.encrypt_phone(value)


def encrypt_wechat_id(value: str) -> str:
    """Encrypt WeChat ID."""
    return SensitiveDataCrypto.encrypt_wechat_id(value)


def encrypt_identity_value(identity_type: str, value: str) -> str:
    """Encrypt identity value based on type."""
    return SensitiveDataCrypto.encrypt_identity_value(identity_type, value)


def count_plain_rows(conn, table: str, where_clause: str) -> int:
    """Count rows that need migration."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}")
    count = cursor.fetchone()[0]
    return count


def migrate_table(conn, target: dict[str, Any], dry_run: bool = False) -> tuple[int, int]:
    """Migrate a single table. Returns (total_count, migrated_count)."""
    table = target["table"]
    columns = target["columns"]
    where_clause = target["where"]
    batch_size = target.get("batch_size", 100)
    encrypt_func_name = target.get("encrypt_func", "encrypt_phone")

    total_count = count_plain_rows(conn, table, where_clause)
    if total_count == 0:
        logger.info(f"  {table}: No rows need migration")
        return (0, 0)

    logger.info(f"  {table}: Found {total_count} rows to migrate")

    if dry_run:
        return (total_count, 0)

    migrated_count = 0
    cursor = conn.cursor()

    # Process in batches
    while migrated_count < total_count:
        # Fetch batch of plain rows
        if table == "user_account_identities":
            cursor.execute(
                f"""
                SELECT user_id, identity_type, identity_value
                FROM {table}
                WHERE {where_clause} AND identity_value NOT LIKE 'enc:%'
                LIMIT {batch_size}
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                user_id, identity_type, identity_value = row
                encrypted = encrypt_identity_value(identity_type, identity_value)
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET identity_value = ?, updated_at = ?
                    WHERE user_id = ? AND identity_type = ? AND identity_value = ?
                    """,
                    (encrypted, datetime.utcnow(), user_id, identity_type, identity_value),
                )
                migrated_count += 1
        elif table == "wechat_accounts":
            cursor.execute(
                f"""
                SELECT wechat_account_id, openid, unionid
                FROM {table}
                WHERE {where_clause} AND openid NOT LIKE 'enc:%'
                LIMIT {batch_size}
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                wechat_account_id, openid, unionid = row
                encrypted_openid = encrypt_wechat_id(openid)
                encrypted_unionid = encrypt_wechat_id(unionid) if unionid else None
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET openid = ?, unionid = ?, updated_at = ?
                    WHERE wechat_account_id = ?
                    """,
                    (encrypted_openid, encrypted_unionid, datetime.utcnow(), wechat_account_id),
                )
                migrated_count += 1
        else:
            # Generic table migration
            column_list = ", ".join(columns)
            pk_column = "user_id" if "user_id" in columns else f"{table}_id"
            cursor.execute(
                f"""
                SELECT {pk_column}, {column_list}
                FROM {table}
                WHERE {where_clause} AND {columns[0]} NOT LIKE 'enc:%'
                LIMIT {batch_size}
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                pk, value = row[0], row[1]
                encrypted = encrypt_phone(value)
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET {columns[0]} = ?, updated_at = ?
                    WHERE {pk_column} = ?
                    """,
                    (encrypted, datetime.utcnow(), pk),
                )
                migrated_count += 1

        conn.commit()
        logger.info(f"  {table}: Migrated {migrated_count}/{total_count} rows")

    return (total_count, migrated_count)


def verify_migration(conn, target: dict[str, Any]) -> tuple[int, int]:
    """Verify migration: count encrypted vs plain rows."""
    table = target["table"]
    where_clause = target["where"]

    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}")
    total = cursor.fetchone()[0]

    if table == "user_account_identities":
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {where_clause} AND identity_value LIKE 'enc:%'"
        )
    else:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {where_clause} AND {target['columns'][0]} LIKE 'enc:%'"
        )
    encrypted_count = cursor.fetchone()[0]

    return (total, encrypted_count)


def main():
    parser = argparse.ArgumentParser(description="Migrate sensitive data to encrypted format")
    parser.add_argument("--dry-run", action="store_true", help="Check without making changes")
    parser.add_argument("--dsn", default=os.environ.get("PARTNER_CHAT_DB"), help="Database DSN")
    parser.add_argument("--verify", action="store_true", help="Verify existing encryption status")
    args = parser.parse_args()

    # Check encryption key
    try:
        if not SensitiveDataCrypto.has_encryption_key():
            if os.environ.get("HER_PRODUCTION_MODE"):
                logger.error("HER_SENSITIVE_DATA_KEY is required for production migration")
                sys.exit(1)
            else:
                logger.warning(
                    "HER_SENSITIVE_DATA_KEY not set. Running in development mode - "
                    "data will be marked but not truly encrypted."
                )
    except MissingEncryptionKeyError as exc:
        logger.error(str(exc))
        sys.exit(1)

    # Connect to database
    if not args.dsn:
        logger.error("Database DSN required (--dsn or PARTNER_CHAT_DB env)")
        sys.exit(1)

    logger.info(f"Connecting to database: {args.dsn}")
    conn = connect_db(args.dsn)

    if args.verify:
        logger.info("Verifying encryption status...")
        for target in MIGRATION_TARGETS:
            total, encrypted = verify_migration(conn, target)
            plain = total - encrypted
            logger.info(
                f"  {target['table']}: total={total}, encrypted={encrypted}, plain={plain}"
            )
        conn.close()
        return

    logger.info("Starting migration...")
    if args.dry_run:
        logger.info("DRY RUN - No changes will be made")

    total_rows = 0
    migrated_rows = 0

    for target in MIGRATION_TARGETS:
        count, migrated = migrate_table(conn, target, dry_run=args.dry_run)
        total_rows += count
        migrated_rows += migrated

    logger.info(f"Migration complete: {migrated_rows}/{total_rows} rows migrated")

    if not args.dry_run:
        # Verify after migration
        logger.info("Verifying post-migration status...")
        for target in MIGRATION_TARGETS:
            total, encrypted = verify_migration(conn, target)
            logger.info(f"  {target['table']}: {encrypted}/{total} rows encrypted")

    conn.close()
    logger.info("Done")


if __name__ == "__main__":
    main()