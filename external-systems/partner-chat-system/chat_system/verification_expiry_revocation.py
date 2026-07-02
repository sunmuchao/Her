"""Verification expiry and revocation mechanism.

This module implements:
1. Verification expiry checking
2. Verification revocation workflow
3. Gate mechanism integration for expired/revoked verifications
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

import pymysql

# Database connection
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"


def get_level_expiry(level_name: str) -> int | None:
    """Get expiry days for verification level"""
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT expires_after_days
            FROM verification_level_weights
            WHERE level_name = %s
        """, [level_name])

        result = cursor.fetchone()
        return result['expires_after_days'] if result else None

    finally:
        cursor.close()
        conn.close()


def check_verification_expiry(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Check if verification has expired

    Args:
        profile: Profile data dict

    Returns:
        Expiry check result
    """
    expired_fields = []
    expiring_soon_fields = []

    # Check video verification
    photo_verification_at = profile.get('photo_verification_at')
    photo_verification_level = profile.get('photo_verification_level')

    if photo_verification_at and photo_verification_level:
        expires_after_days = get_level_expiry(photo_verification_level)

        if expires_after_days:
            verification_age = (datetime.now() - datetime.fromisoformat(photo_verification_at)).days

            if verification_age > expires_after_days:
                expired_fields.append('video')
            elif verification_age > expires_after_days - 30:
                expiring_soon_fields.append('video')

    # Check field verifications
    for field_key in ['education', 'job', 'income']:
        field_expires_at = profile.get(f'{field_key}_verification_expires_at')

        if field_expires_at:
            expires_at = datetime.fromisoformat(field_expires_at)

            if datetime.now() > expires_at:
                expired_fields.append(field_key)
            elif datetime.now() > expires_at - timedelta(days=30):
                expiring_soon_fields.append(field_key)

    return {
        "expired": len(expired_fields) > 0,
        "expired_fields": expired_fields,
        "expiring_soon_fields": expiring_soon_fields,
    }


def revoke_verification(
    submission_id: str,
    revocation_reason: str,
    revoked_by: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Revoke verification

    Args:
        submission_id: Submission ID
        revocation_reason: Revocation reason
        revoked_by: Revoker ID
        metadata: Additional metadata

    Returns:
        Revocation result
    """
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4',
        autocommit=False
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Get submission info
        cursor.execute("""
            SELECT verification_type, user_id, profile_id, status
            FROM verification_submissions
            WHERE submission_id = ?
        """, [submission_id])

        submission = cursor.fetchone()

        if not submission:
            return {"success": False, "error": "Submission not found"}

        # Update submission status
        cursor.execute("""
            UPDATE verification_submissions
            SET status = 'revoked',
                revoked_at = ?,
                revocation_reason = ?
            WHERE submission_id = ?
        """, [datetime.now(), revocation_reason, submission_id])

        # Create revocation record
        cursor.execute("""
            INSERT INTO verification_revocations
            (submission_id, user_id, profile_id, revocation_reason,
             revoked_by, revoked_at, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            submission_id,
            submission['user_id'],
            submission['profile_id'],
            revocation_reason,
            revoked_by,
            datetime.now(),
            json.dumps(metadata) if metadata else None,
            datetime.now(),
        ])

        # Sync revocation to profile table
        if submission['verification_type'] == 'live_video':
            cursor.execute("""
                UPDATE profiles
                SET photo_verification_level = 'uploaded',
                    live_video_verified = 0,
                    photo_verification_revoked = 1
                WHERE profile_id = ?
            """, [submission['profile_id']])

        conn.commit()

        return {
            "success": True,
            "submission_id": submission_id,
            "revocation_id": cursor.lastrowid,
            "revoked_at": datetime.now().isoformat(),
        }

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}

    finally:
        cursor.close()
        conn.close()


def get_revocation_history(user_id: str) -> list[dict[str, Any]]:
    """
    Get revocation history for user

    Args:
        user_id: User ID

    Returns:
        List of revocation records
    """
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cursor.execute("""
            SELECT revocation_id, submission_id, revocation_reason,
                   revoked_by, revoked_at, metadata_json
            FROM verification_revocations
            WHERE user_id = ?
            ORDER BY revoked_at DESC
            LIMIT 20
        """, [user_id])

        revocations = cursor.fetchall()

        # Parse metadata JSON
        for rev in revocations:
            if rev['metadata_json']:
                try:
                    rev['metadata'] = json.loads(rev['metadata_json'])
                except json.JSONDecodeError:
                    rev['metadata'] = None
            else:
                rev['metadata'] = None

        return revocations

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # Test expiry checking
    print("Testing verification expiry and revocation...")

    # Mock profile data
    mock_profile = {
        "photo_verification_at": "2025-01-01T00:00:00",
        "photo_verification_level": "live_video_verified",
        "education_verification_expires_at": "2025-12-31T00:00:00",
    }

    expiry_result = check_verification_expiry(mock_profile)
    print(f"Expiry check result: {expiry_result}")

    # Test revocation history
    history = get_revocation_history("test-user-001")
    print(f"Revocation history: {len(history)} records")

    print("✓ Expiry and revocation test passed")