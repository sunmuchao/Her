#!/usr/bin/env python3
"""Migrate data from her_chat to her_auth, her_verification, her_risk.

SAFETY: This script copies data, does NOT delete from source tables.
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
    """Get MySQL connection with password from environment."""
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


def migrate_auth_tables(conn):
    """Migrate authentication tables from her_chat to her_auth."""
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

    print("=== Migrating Auth Tables ===")
    migrated_counts = {}

    for table in auth_tables:
        # Check if source table exists and has data
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚠️  {table}: not found in her_chat, skipping")
                continue

            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            source_count = cursor.fetchone()["cnt"]

            if source_count == 0:
                print(f"  ⚪ {table}: 0 rows, skipping")
                migrated_counts[table] = 0
                continue

        # Migrate data
        try:
            with conn.cursor() as cursor:
                # Get column names
                cursor.execute(f"SHOW COLUMNS FROM her_chat.{table}")
                columns = [row["Field"] for row in cursor.fetchall()]
                columns_str = ", ".join(columns)

                # Copy data
                sql = f"""
                    INSERT INTO her_auth.{table} ({columns_str})
                    SELECT {columns_str} FROM her_chat.{table}
                """
                cursor.execute(sql)
                migrated = cursor.rowcount

                print(f"  ✅ {table}: {migrated} rows migrated")
                migrated_counts[table] = migrated

            conn.commit()
        except Exception as e:
            print(f"  ❌ {table}: migration failed - {e}")
            conn.rollback()
            migrated_counts[table] = 0

    total = sum(migrated_counts.values())
    print(f"\nTotal auth rows migrated: {total}")
    return migrated_counts


def migrate_verification_tables(conn):
    """Migrate verification tables from her_chat to her_verification."""
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

    print("\n=== Migrating Verification Tables ===")
    migrated_counts = {}

    for table in verification_tables:
        # Check if source table exists
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚠️  {table}: not found in her_chat, skipping")
                continue

            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            source_count = cursor.fetchone()["cnt"]

            if source_count == 0:
                print(f"  ⚪ {table}: 0 rows, skipping")
                migrated_counts[table] = 0
                continue

        # Migrate data
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SHOW COLUMNS FROM her_chat.{table}")
                columns = [row["Field"] for row in cursor.fetchall()]
                columns_str = ", ".join(columns)

                sql = f"""
                    INSERT INTO her_verification.{table} ({columns_str})
                    SELECT {columns_str} FROM her_chat.{table}
                """
                cursor.execute(sql)
                migrated = cursor.rowcount

                print(f"  ✅ {table}: {migrated} rows migrated")
                migrated_counts[table] = migrated

            conn.commit()
        except Exception as e:
            print(f"  ❌ {table}: migration failed - {e}")
            conn.rollback()
            migrated_counts[table] = 0

    total = sum(migrated_counts.values())
    print(f"\nTotal verification rows migrated: {total}")
    return migrated_counts


def migrate_risk_tables(conn):
    """Migrate risk tables from her_chat to her_risk."""
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

    print("\n=== Migrating Risk Tables ===")
    migrated_counts = {}

    for table in risk_tables:
        # Check if source table exists
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES FROM her_chat LIKE '{table}'")
            if not cursor.fetchone():
                print(f"  ⚠️  {table}: not found in her_chat, skipping")
                continue

            cursor.execute(f"SELECT COUNT(*) as cnt FROM her_chat.{table}")
            source_count = cursor.fetchone()["cnt"]

            if source_count == 0:
                print(f"  ⚪ {table}: 0 rows, skipping")
                migrated_counts[table] = 0
                continue

        # Migrate data
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SHOW COLUMNS FROM her_chat.{table}")
                columns = [row["Field"] for row in cursor.fetchall()]
                columns_str = ", ".join(columns)

                sql = f"""
                    INSERT INTO her_risk.{table} ({columns_str})
                    SELECT {columns_str} FROM her_chat.{table}
                """
                cursor.execute(sql)
                migrated = cursor.rowcount

                print(f"  ✅ {table}: {migrated} rows migrated")
                migrated_counts[table] = migrated

            conn.commit()
        except Exception as e:
            print(f"  ❌ {table}: migration failed - {e}")
            conn.rollback()
            migrated_counts[table] = 0

    total = sum(migrated_counts.values())
    print(f"\nTotal risk rows migrated: {total}")
    return migrated_counts


def main():
    """Run all migrations."""
    print("=" * 60)
    print("Data Migration: her_chat → her_auth/her_verification/her_risk")
    print("=" * 60)
    print("\n⚠️  SAFETY: This script copies data, does NOT delete source data.\n")

    conn = get_mysql_connection()

    try:
        auth_counts = migrate_auth_tables(conn)
        verification_counts = migrate_verification_tables(conn)
        risk_counts = migrate_risk_tables(conn)

        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)

        auth_total = sum(auth_counts.values())
        verification_total = sum(verification_counts.values())
        risk_total = sum(risk_counts.values())

        print(f"Auth tables: {auth_total} rows")
        print(f"Verification tables: {verification_total} rows")
        print(f"Risk tables: {risk_total} rows")
        print(f"Total migrated: {auth_total + verification_total + risk_total} rows")

        print("\n✅ Migration completed successfully!")
        print("\nNext step: Run cleanup script to remove old tables from her_chat")

        return 0
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())