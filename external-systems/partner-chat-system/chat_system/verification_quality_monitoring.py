"""Verification quality monitoring dashboard API.

This module provides API endpoints for verification quality monitoring,
including:
1. Auto-review statistics
2. False positive/negative rates
3. Review latency metrics
4. Post-approval revocation rates
"""

from __future__ import annotations

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


def get_verification_quality_metrics(
    start_date: datetime,
    end_date: datetime,
    verification_type: str | None = None,
) -> dict[str, Any]:
    """
    Get verification quality metrics for dashboard

    Args:
        start_date: Start date
        end_date: End date
        verification_type: Verification type filter (optional)

    Returns:
        Quality metrics
    """
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Build query with optional filter
        query = """
            SELECT
                stat_date,
                verification_type,
                SUM(total_auto_reviews) as total_auto_reviews,
                SUM(auto_approved) as auto_approved,
                SUM(auto_resubmission) as auto_resubmission,
                SUM(manual_review) as manual_review,
                SUM(manual_approved_after_auto) as manual_approved_after_auto,
                AVG(false_positive_rate) as avg_false_positive_rate,
                SUM(false_negative_recall_count) as false_negative_recall_count,
                AVG(post_approval_revocation_rate) as avg_post_approval_revocation_rate,
                AVG(avg_auto_review_latency_ms) as avg_auto_review_latency_ms
            FROM verification_auto_review_stats
            WHERE stat_date BETWEEN ? AND ?
        """

        params = [start_date, end_date]

        if verification_type:
            query += " AND verification_type = ?"
            params.append(verification_type)

        query += " GROUP BY stat_date, verification_type ORDER BY stat_date DESC"

        cursor.execute(query, params)
        daily_stats = cursor.fetchall()

        # Calculate summary metrics
        total_auto_reviews = sum(s['total_auto_reviews'] or 0 for s in daily_stats)
        auto_approved = sum(s['auto_approved'] or 0 for s in daily_stats)
        manual_review_total = sum(s['manual_review'] or 0 for s in daily_stats)

        auto_approve_rate = auto_approved / total_auto_reviews if total_auto_reviews > 0 else 0
        false_positive_rate = sum(s['manual_approved_after_auto'] or 0 for s in daily_stats) / manual_review_total if manual_review_total > 0 else 0
        false_negative_recall_count = sum(s['false_negative_recall_count'] or 0 for s in daily_stats)

        avg_latency = sum(s['avg_auto_review_latency_ms'] or 0 for s in daily_stats) / len(daily_stats) if daily_stats else 0

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "summary": {
                "total_submissions": total_auto_reviews,
                "auto_approve_rate": round(auto_approve_rate * 100, 2),
                "false_positive_rate": round(false_positive_rate * 100, 2),
                "false_negative_recall_count": false_negative_recall_count,
                "avg_auto_review_latency_ms": round(avg_latency, 2),
            },
            "daily_stats": daily_stats,
        }

    finally:
        cursor.close()
        conn.close()


def record_review_latency(
    submission_id: str,
    review_type: str,
    decision: str,
) -> None:
    """
    Record review latency for monitoring

    Args:
        submission_id: Submission ID
        review_type: Review type ('auto', 'manual')
        decision: Decision ('approve', 'reject', 'resubmit')
    """
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4',
        autocommit=True
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Get submission submitted_at
        cursor.execute("""
            SELECT submitted_at
            FROM verification_submissions
            WHERE submission_id = ?
        """, [submission_id])

        result = cursor.fetchone()

        if result:
            submitted_at = datetime.fromisoformat(str(result['submitted_at']))
            latency_ms = int((datetime.now() - submitted_at).total_seconds() * 1000)

            # Record latency
            cursor.execute("""
                INSERT INTO verification_review_latency
                (submission_id, review_type, decision, latency_ms, recorded_at)
                VALUES (?, ?, ?, ?, ?)
            """, [submission_id, review_type, decision, latency_ms, datetime.now()])

    finally:
        cursor.close()
        conn.close()


def get_latency_trends(days: int = 7) -> dict[str, Any]:
    """
    Get review latency trends

    Args:
        days: Number of days to analyze

    Returns:
        Latency trend data
    """
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cutoff_date = datetime.now() - timedelta(days=days)

        cursor.execute("""
            SELECT
                DATE(recorded_at) as date,
                review_type,
                COUNT(*) as count,
                AVG(latency_ms) as avg_latency_ms,
                MIN(latency_ms) as min_latency_ms,
                MAX(latency_ms) as max_latency_ms
            FROM verification_review_latency
            WHERE recorded_at >= ?
            GROUP BY DATE(recorded_at), review_type
            ORDER BY date DESC
        """, [cutoff_date])

        trends = cursor.fetchall()

        return {
            "period_days": days,
            "trends": trends,
        }

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # Test quality metrics
    print("Testing verification quality monitoring...")

    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()

    metrics = get_verification_quality_metrics(start_date, end_date)
    print(f"Quality metrics: {metrics['summary']}")

    trends = get_latency_trends(days=7)
    print(f"Latency trends: {len(trends['trends'])} records")

    print("✓ Quality monitoring test passed")