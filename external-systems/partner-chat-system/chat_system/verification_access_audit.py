"""Access audit logging for sensitive verification data.

This module provides audit logging for access to sensitive fields in the
verification system, ensuring that all access to sensitive data is tracked
and can be reviewed for compliance and security purposes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import pymysql

# Database connection configuration
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"


class AccessAuditLogger:
    """Access audit logger for sensitive verification data"""

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
                autocommit=True
            )
        return self._conn

    def log_access(
        self,
        submission_id: str,
        field_name: str,
        accessor_id: str,
        accessor_role: str,
        access_type: str,  # 'read', 'write', 'decrypt'
        access_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log access to a sensitive field

        Args:
            submission_id: The submission ID
            field_name: The field name being accessed
            accessor_id: The user ID or system ID accessing the field
            accessor_role: The role of the accessor (e.g., 'verification_ops', 'risk_ops')
            access_type: The type of access ('read', 'write', 'decrypt')
            access_reason: Optional reason for access
            metadata: Optional additional metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Create audit log table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verification_sensitive_data_access_audit (
                    audit_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    submission_id VARCHAR(64) COLLATE utf8mb4_unicode_ci NOT NULL,
                    field_name VARCHAR(64) NOT NULL,
                    accessor_id VARCHAR(191) NOT NULL,
                    accessor_role VARCHAR(64) NOT NULL,
                    access_type VARCHAR(32) NOT NULL,
                    access_reason VARCHAR(191),
                    metadata_json LONGTEXT,
                    accessed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_submission (submission_id, accessed_at),
                    INDEX idx_audit_accessor (accessor_id, accessed_at),
                    INDEX idx_audit_field (field_name, accessed_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感数据访问审计日志表'
            """)

            # Insert audit log
            cursor.execute("""
                INSERT INTO verification_sensitive_data_access_audit
                (submission_id, field_name, accessor_id, accessor_role, access_type,
                 access_reason, metadata_json, accessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                submission_id,
                field_name,
                accessor_id,
                accessor_role,
                access_type,
                access_reason,
                json.dumps(metadata) if metadata else None,
                datetime.now()
            ])

        finally:
            cursor.close()

    def query_audit_logs(
        self,
        submission_id: str | None = None,
        accessor_id: str | None = None,
        field_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query audit logs with filters

        Args:
            submission_id: Filter by submission ID
            accessor_id: Filter by accessor ID
            field_name: Filter by field name
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of results

        Returns:
            List of audit log records
        """
        conn = self._get_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        try:
            query = """
                SELECT * FROM verification_sensitive_data_access_audit
                WHERE 1=1
            """
            params = []

            if submission_id:
                query += " AND submission_id = ?"
                params.append(submission_id)

            if accessor_id:
                query += " AND accessor_id = ?"
                params.append(accessor_id)

            if field_name:
                query += " AND field_name = ?"
                params.append(field_name)

            if start_time:
                query += " AND accessed_at >= ?"
                params.append(start_time)

            if end_time:
                query += " AND accessed_at <= ?"
                params.append(end_time)

            query += " ORDER BY accessed_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            results = cursor.fetchall()

            # Parse metadata JSON
            for result in results:
                if result['metadata_json']:
                    try:
                        result['metadata'] = json.loads(result['metadata_json'])
                    except json.JSONDecodeError:
                        result['metadata'] = None
                else:
                    result['metadata'] = None

            return results

        finally:
            cursor.close()

    def close(self):
        """Close database connection"""
        if self._conn and self._conn.open:
            self._conn.close()
            self._conn = None


# Global audit logger instance
_audit_logger = AccessAuditLogger()


def log_sensitive_data_access(
    submission_id: str,
    field_name: str,
    accessor_id: str,
    accessor_role: str,
    access_type: str,
    access_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Log access to a sensitive field (convenience function)

    Args:
        submission_id: The submission ID
        field_name: The field name being accessed
        accessor_id: The user ID or system ID accessing the field
        accessor_role: The role of the accessor
        access_type: The type of access
        access_reason: Optional reason for access
        metadata: Optional additional metadata
    """
    _audit_logger.log_access(
        submission_id=submission_id,
        field_name=field_name,
        accessor_id=accessor_id,
        accessor_role=accessor_role,
        access_type=access_type,
        access_reason=access_reason,
        metadata=metadata,
    )


def query_audit_logs(
    submission_id: str | None = None,
    accessor_id: str | None = None,
    field_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Query audit logs (convenience function)

    Args:
        submission_id: Filter by submission ID
        accessor_id: Filter by accessor ID
        field_name: Filter by field name
        start_time: Filter by start time
        end_time: Filter by end time
        limit: Maximum number of results

    Returns:
        List of audit log records
    """
    return _audit_logger.query_audit_logs(
        submission_id=submission_id,
        accessor_id=accessor_id,
        field_name=field_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


if __name__ == "main":
    # Test audit logging
    print("Testing audit logging...")

    log_sensitive_data_access(
        submission_id="test-submission-001",
        field_name="ocr_extracted_text",
        accessor_id="reviewer-001",
        accessor_role="verification_ops",
        access_type="decrypt",
        access_reason="Manual review",
        metadata={"review_task_id": "task-001"}
    )

    logs = query_audit_logs(submission_id="test-submission-001")
    print(f"Found {len(logs)} audit logs")
    if logs:
        print(f"Latest log: {logs[0]}")

    print("✓ Audit logging test passed")