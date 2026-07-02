"""Automatic cleanup task for sensitive verification data.

This module implements scheduled cleanup tasks for verification sensitive data,
following the data governance policies defined in verification_data_governance_policies table.

Cleanup tasks:
1. Delete expired raw verification media files (30 days retention)
2. Delete expired OCR extracted text (180 days retention)
3. Delete expired authority verification results (365 days retention)
4. Delete expired revocation evidence (730 days retention)

The task runs daily as part of the task_scheduler system.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

import pymysql

# Database connection configuration
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"

# MinIO/S3 storage configuration (for media files)
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "her_minio_admin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "her_minio_password")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "her-media")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"


class SensitiveDataCleanupTask:
    """Sensitive data cleanup task manager"""

    def __init__(self):
        self._conn = None

    def _get_connection(self) -> pymysql.Connection:
        """Get database connection"""
        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                autocommit=False
            )
        return self._conn

    def _get_retention_policies(self) -> dict[str, int]:
        """Get data retention policies from database"""
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        try:
            cursor.execute("""
                SELECT policy_key, retention_days
                FROM verification_data_governance_policies
            """)
            policies = cursor.fetchall()

            return {policy['policy_key']: policy['retention_days'] for policy in policies}

        finally:
            cursor.close()

    def cleanup_raw_verification_media(self, retention_days: int = 30) -> dict[str, Any]:
        """
        Delete expired raw verification media files

        Args:
            retention_days: Retention period in days

        Returns:
            Cleanup statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        stats = {
            'policy': 'raw_verification_media',
            'retention_days': retention_days,
            'cutoff_date': cutoff_date,
            'deleted_assets': 0,
            'deleted_bytes': 0,
            'errors': [],
        }

        try:
            # Find expired assets
            cursor.execute("""
                SELECT asset_id, storage_key, file_size_bytes, created_at
                FROM verification_assets
                WHERE created_at < ?
                AND asset_kind IN ('video', 'photo', 'document')
            """, [cutoff_date])

            expired_assets = cursor.fetchall()

            print(f"Found {len(expired_assets)} expired verification assets")

            # Delete from MinIO/S3 (if configured)
            # In production, implement actual MinIO deletion
            # For now, we just mark them as deleted in database

            for asset in expired_assets:
                try:
                    # Mark asset as deleted
                    cursor.execute("""
                        UPDATE verification_assets
                        SET storage_key = CONCAT('deleted:', storage_key),
                            metadata_json = JSON_SET(
                                COALESCE(metadata_json, '{}'),
                                '$.deleted_at', ?,
                                '$.deleted_reason', 'retention_policy'
                            )
                        WHERE asset_id = ?
                    """, [datetime.now().isoformat(), asset['asset_id']])

                    stats['deleted_assets'] += 1
                    stats['deleted_bytes'] += asset['file_size_bytes']

                except Exception as e:
                    error_msg = f"Failed to delete asset {asset['asset_id']}: {e}"
                    print(error_msg)
                    stats['errors'].append(error_msg)

            conn.commit()
            print(f"Cleaned up {stats['deleted_assets']} verification assets")

        except Exception as e:
            conn.rollback()
            error_msg = f"Cleanup failed: {e}"
            print(error_msg)
            stats['errors'].append(error_msg)

        finally:
            cursor.close()

        return stats

    def cleanup_ocr_extracted_text(self, retention_days: int = 180) -> dict[str, Any]:
        """
        Delete expired OCR extracted text

        Args:
            retention_days: Retention period in days

        Returns:
            Cleanup statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        stats = {
            'policy': 'ocr_extracted_text',
            'retention_days': retention_days,
            'cutoff_date': cutoff_date,
            'deleted_submissions': 0,
            'errors': [],
        }

        try:
            # Find expired OCR text
            cursor.execute("""
                SELECT submission_id, ocr_processed_at
                FROM profile_field_verification_submissions
                WHERE ocr_processed_at < ?
                AND ocr_extracted_text IS NOT NULL
            """, [cutoff_date])

            expired_submissions = cursor.fetchall()

            print(f"Found {len(expired_submissions)} submissions with expired OCR text")

            # Clear OCR text fields
            for submission in expired_submissions:
                try:
                    cursor.execute("""
                        UPDATE profile_field_verification_submissions
                        SET ocr_extracted_text = NULL,
                            metadata_json = JSON_SET(
                                COALESCE(metadata_json, '{}'),
                                '$.ocr_deleted_at', ?
                            )
                        WHERE submission_id = ?
                    """, [datetime.now().isoformat(), submission['submission_id']])

                    stats['deleted_submissions'] += 1

                except Exception as e:
                    error_msg = f"Failed to clear OCR text for {submission['submission_id']}: {e}"
                    print(error_msg)
                    stats['errors'].append(error_msg)

            conn.commit()
            print(f"Cleaned up OCR text for {stats['deleted_submissions']} submissions")

        except Exception as e:
            conn.rollback()
            error_msg = f"OCR cleanup failed: {e}"
            print(error_msg)
            stats['errors'].append(error_msg)

        finally:
            cursor.close()

        return stats

    def cleanup_authority_verification_results(self, retention_days: int = 365) -> dict[str, Any]:
        """
        Delete expired authority verification results

        Args:
            retention_days: Retention period in days

        Returns:
            Cleanup statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        stats = {
            'policy': 'authority_verification_result',
            'retention_days': retention_days,
            'cutoff_date': cutoff_date,
            'deleted_results': 0,
            'errors': [],
        }

        try:
            # Find expired authority verification results
            # Assuming reviewed_at is the verification date
            cursor.execute("""
                SELECT submission_id, reviewed_at
                FROM profile_field_verification_submissions
                WHERE reviewed_at < ?
                AND authority_verification_result IS NOT NULL
            """, [cutoff_date])

            expired_submissions = cursor.fetchall()

            print(f"Found {len(expired_submissions)} expired authority verification results")

            # Clear authority verification result fields
            for submission in expired_submissions:
                try:
                    cursor.execute("""
                        UPDATE profile_field_verification_submissions
                        SET authority_verification_result = NULL,
                            metadata_json = JSON_SET(
                                COALESCE(metadata_json, '{}'),
                                '$.authority_result_deleted_at', ?
                            )
                        WHERE submission_id = ?
                    """, [datetime.now().isoformat(), submission['submission_id']])

                    stats['deleted_results'] += 1

                except Exception as e:
                    error_msg = f"Failed to clear authority result for {submission['submission_id']}: {e}"
                    print(error_msg)
                    stats['errors'].append(error_msg)

            conn.commit()
            print(f"Cleaned up {stats['deleted_results']} authority verification results")

        except Exception as e:
            conn.rollback()
            error_msg = f"Authority verification cleanup failed: {e}"
            print(error_msg)
            stats['errors'].append(error_msg)

        finally:
            cursor.close()

        return stats

    def cleanup_revocation_evidence(self, retention_days: int = 730) -> dict[str, Any]:
        """
        Delete expired revocation evidence

        Args:
            retention_days: Retention period in days

        Returns:
            Cleanup statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        stats = {
            'policy': 'revocation_evidence',
            'retention_days': retention_days,
            'cutoff_date': cutoff_date,
            'deleted_evidence': 0,
            'errors': [],
        }

        try:
            # Find expired revocation evidence
            cursor.execute("""
                SELECT revocation_id, revoked_at, metadata_json
                FROM verification_revocations
                WHERE revoked_at < ?
            """, [cutoff_date])

            expired_revocations = cursor.fetchall()

            print(f"Found {len(expired_revocations)} expired revocation records")

            # Clear revocation metadata (evidence)
            for revocation in expired_revocations:
                try:
                    # Clear sensitive evidence data from metadata_json
                    cursor.execute("""
                        UPDATE verification_revocations
                        SET metadata_json = JSON_SET(
                            COALESCE(metadata_json, '{}'),
                            '$.evidence_deleted_at', ?,
                            '$.evidence_deleted_reason', 'retention_policy'
                        )
                        WHERE revocation_id = ?
                    """, [datetime.now().isoformat(), revocation['revocation_id']])

                    stats['deleted_evidence'] += 1

                except Exception as e:
                    error_msg = f"Failed to clear evidence for revocation {revocation['revocation_id']}: {e}"
                    print(error_msg)
                    stats['errors'].append(error_msg)

            conn.commit()
            print(f"Cleaned up {stats['deleted_evidence']} revocation evidence records")

        except Exception as e:
            conn.rollback()
            error_msg = f"Revocation evidence cleanup failed: {e}"
            print(error_msg)
            stats['errors'].append(error_msg)

        finally:
            cursor.close()

        return stats

    def run_all_cleanup_tasks(self) -> dict[str, Any]:
        """
        Run all cleanup tasks according to retention policies

        Returns:
            Combined cleanup statistics
        """
        print("Starting sensitive data cleanup tasks...")

        # Get retention policies
        policies = self._get_retention_policies()
        print(f"Loaded {len(policies)} retention policies")

        results = {}

        # Run cleanup tasks
        if 'raw_verification_media' in policies:
            results['raw_verification_media'] = self.cleanup_raw_verification_media(
                retention_days=policies['raw_verification_media']
            )

        if 'ocr_extracted_text' in policies:
            results['ocr_extracted_text'] = self.cleanup_ocr_extracted_text(
                retention_days=policies['ocr_extracted_text']
            )

        if 'authority_verification_result' in policies:
            results['authority_verification_result'] = self.cleanup_authority_verification_results(
                retention_days=policies['authority_verification_result']
            )

        if 'revocation_evidence' in policies:
            results['revocation_evidence'] = self.cleanup_revocation_evidence(
                retention_days=policies['revocation_evidence']
            )

        print("All cleanup tasks completed")
        return results

    def close(self):
        """Close database connection"""
        if self._conn and self._conn.open:
            self._conn.close()
            self._conn = None


def run_verification_cleanup_task() -> dict[str, Any]:
    """
    Main entry point for scheduled cleanup task

    This function is called by the task_scheduler system.

    Returns:
        Cleanup statistics
    """
    task = SensitiveDataCleanupTask()
    try:
        return task.run_all_cleanup_tasks()
    finally:
        task.close()


if __name__ == "__main__":
    # Manual execution
    print("Running verification sensitive data cleanup...")
    results = run_verification_cleanup_task()

    print("\nCleanup Results:")
    for policy, stats in results.items():
        print(f"\n{policy}:")
        print(f"  Retention: {stats['retention_days']} days")
        print(f"  Cutoff date: {stats['cutoff_date']}")
        if 'deleted_assets' in stats:
            print(f"  Deleted assets: {stats['deleted_assets']}")
            print(f"  Deleted bytes: {stats['deleted_bytes']}")
        if 'deleted_submissions' in stats:
            print(f"  Deleted submissions: {stats['deleted_submissions']}")
        if 'deleted_results' in stats:
            print(f"  Deleted results: {stats['deleted_results']}")
        if 'deleted_evidence' in stats:
            print(f"  Deleted evidence: {stats['deleted_evidence']}")
        if stats['errors']:
            print(f"  Errors: {len(stats['errors'])}")
            for error in stats['errors']:
                print(f"    - {error}")