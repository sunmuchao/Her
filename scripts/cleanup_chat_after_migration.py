#!/usr/bin/env python3
"""Cleanup script: Remove migrated tables from her_chat.

SAFETY: This script creates backups before deleting.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
except ImportError:
    pass

import pymysql
from pymysql.cursors import DictCursor


def get_mysql_connection():
    """Get MySQL connection."""
    password = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password=password,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def backup_table(conn, table_name):
    """Create backup of table before deletion."""
    backup_table_name = f"{table_name}_backup_{os.urandom(4).hex()}"
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table_name}'")
            if not cursor.fetchone():
                return None

            # Create backup table
            cursor.execute(f"""
                CREATE TABLE her_chat.{backup_table_name}
                AS SELECT * FROM her_chat.{table_name}
            """)
            conn.commit()
            return backup_table_name
    except Exception as e:
        print(f"  ❌ Backup failed for {table_name}: {e}")
        conn.rollback()
        return None


def cleanup_auth_tables(conn):
    """Remove auth tables from her_chat."""
    auth_tables = [
        "user_accounts",
        "user_account_identities",
        "auth_phone_role_bindings",
        "auth_otp_challenges",
        "auth_sessions",
        "auth_login_events",
        "user_onboarding_profiles",
        "wechat_accounts",
        "auth_one_tap_attempts",
    ]

    print("=== Cleaning Up Auth Tables ===")
    deleted_counts = {}
    backup_tables = {}

    for table in auth_tables:
        # Check if table exists
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚪ {table}: not found, skipping")
                continue

            # Get row count before deletion
            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            count_before = cursor.fetchone()["cnt"]

        # Create backup
        backup_name = backup_table(conn, table)
        if backup_name:
            backup_tables[table] = backup_name
            print(f"  📦 {table}: backed up as {backup_name}")

        # Drop table
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE her_chat.{table}")
                conn.commit()
                deleted_counts[table] = count_before
                print(f"  ✅ {table}: deleted ({count_before} rows)")
        except Exception as e:
            print(f"  ❌ {table}: deletion failed - {e}")
            conn.rollback()
            deleted_counts[table] = 0

    total = sum(deleted_counts.values())
    print(f"\nTotal auth rows freed: {total}")
    print(f"Backup tables created: {len(backup_tables)}")
    return deleted_counts, backup_tables


def cleanup_verification_tables(conn):
    """Remove verification tables from her_chat."""
    verification_tables = [
        "verification_submissions",
        "verification_assets",
        "verification_reviews",
        "verification_notifications",
        "verification_level_weights",
        "verification_submission_metadata",
        "verification_revocations",
        "verification_auto_review_stats",
        "verification_review_latency",
        "verification_data_governance_policies",
        "profile_field_verification_submissions",
        "profile_field_verification_reviews",
    ]

    print("\n=== Cleaning Up Verification Tables ===")
    deleted_counts = {}
    backup_tables = {}

    for table in verification_tables:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚪ {table}: not found, skipping")
                continue

            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            count_before = cursor.fetchone()["cnt"]

        backup_name = backup_table(conn, table)
        if backup_name:
            backup_tables[table] = backup_name
            print(f"  📦 {table}: backed up as {backup_name}")

        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE her_chat.{table}")
                conn.commit()
                deleted_counts[table] = count_before
                print(f"  ✅ {table}: deleted ({count_before} rows)")
        except Exception as e:
            print(f"  ❌ {table}: deletion failed - {e}")
            conn.rollback()
            deleted_counts[table] = 0

    total = sum(deleted_counts.values())
    print(f"\nTotal verification rows freed: {total}")
    return deleted_counts, backup_tables


def cleanup_risk_tables(conn):
    """Remove risk tables from her_chat."""
    risk_tables = [
        "chat_member_reports",
        "chat_risk_cases",
        "chat_risk_signals",
        "chat_meeting_feedback",
        "account_moderation_states",
        "chat_risk_appeals",
        "chat_risk_entity_links",
        "chat_risk_account_links",
        "chat_risk_network_profiles",
        "profile_review_cases",
        "profile_review_events",
        "profile_review_case_appeals",
        "photo_risk_assets",
        "photo_risk_score_runs",
        "photo_risk_feature_snapshots",
        "photo_risk_decisions",
        "photo_risk_review_queue",
    ]

    print("\n=== Cleaning Up Risk Tables ===")
    deleted_counts = {}
    backup_tables = {}

    for table in risk_tables:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚪ {table}: not found, skipping")
                continue

            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            count_before = cursor.fetchone()["cnt"]

        backup_name = backup_table(conn, table)
        if backup_name:
            backup_tables[table] = backup_name
            print(f"  📦 {table}: backed up as {backup_name}")

        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE her_chat.{table}")
                conn.commit()
                deleted_counts[table] = count_before
                print(f"  ✅ {table}: deleted ({count_before} rows)")
        except Exception as e:
            print(f"  ❌ {table}: deletion failed - {e}")
            conn.rollback()
            deleted_counts[table] = 0

    total = sum(deleted_counts.values())
    print(f"\nTotal risk rows freed: {total}")
    return deleted_counts, backup_tables


def main():
    """Run cleanup."""
    print("=" * 60)
    print("Cleanup: Remove migrated tables from her_chat")
    print("=" * 60)
    print("\n⚠️  SAFETY: Creating backups before deletion.\n")

    conn = get_mysql_connection()

    try:
        auth_deleted, auth_backups = cleanup_auth_tables(conn)
        verification_deleted, verification_backups = cleanup_verification_tables(conn)
        risk_deleted, risk_backups = cleanup_risk_tables(conn)

        print("\n" + "=" * 60)
        print("Cleanup Summary")
        print("=" * 60)

        auth_total = sum(auth_deleted.values())
        verification_total = sum(verification_deleted.values())
        risk_total = sum(risk_deleted.values())

        print(f"Auth tables deleted: {auth_total} rows")
        print(f"Verification tables deleted: {verification_total} rows")
        print(f"Risk tables deleted: {risk_total} rows")
        print(f"Total freed: {auth_total + verification_total + risk_total} rows")

        total_backups = len(auth_backups) + len(verification_backups) + len(risk_backups)
        print(f"\nBackup tables created: {total_backups}")
        print("  ⚠️  Backup tables will remain in her_chat for safety")
        print("  💡 You can manually delete backup tables later if needed")

        print("\n✅ Cleanup completed successfully!")

        # Show remaining tables in her_chat
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES FROM her_chat")
            remaining = cursor.fetchall()
            print(f"\nRemaining tables in her_chat: {len(remaining)}")
            print("  (Should only be chat-related tables now)")

        return 0
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())