"""Normalize legacy recommendation delivery_status values to the current vocabulary."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from db_migrations.helpers import default_scope


def apply(mysql_conn, _context: MigrationContext) -> None:
    updates = [
        """
        UPDATE profile_recommendations
        SET delivery_status = 'suppressed'
        WHERE delivery_status = 'suppressed_low_score'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'delivered'
        WHERE delivery_status = 'already_delivered'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'direct_greet_started'
        WHERE delivery_status = 'direct_greeted'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'review_pending'
        WHERE delivery_status = 'review_deferred'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'suppressed'
        WHERE delivery_status = 'rejected_by_gate'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = CASE
            WHEN user_review_status = 'save' THEN 'saved_by_user'
            ELSE 'review_pending'
        END
        WHERE delivery_status = 'save_only'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'cooled_down'
        WHERE delivery_status = 'review_skipped'
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'escalated_to_case'
        WHERE delivery_status IN ('proxy_intro_in_progress', 'proxy_intro_accepted', 'proxy_intro_handed_off')
        """,
        """
        UPDATE profile_recommendations
        SET delivery_status = 'cooled_down'
        WHERE delivery_status IN ('proxy_intro_declined', 'proxy_intro_timed_out')
        """,
        """
        UPDATE profile_recommendations
        SET active_case_status = NULL
        WHERE active_match_case_id IS NULL
        """,
        """
        UPDATE profile_recommendations AS r
        JOIN match_cases AS c ON c.case_id = r.active_match_case_id
        SET r.active_case_status = c.case_status
        WHERE r.active_match_case_id IS NOT NULL
        """,
    ]
    for statement in updates:
        mysql_conn.cursor().execute(statement)


def validate(_mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return empty_issues()


MIGRATION = MigrationSpec(
    migration_id='0005_normalize_delivery_statuses',
    description='Normalize legacy recommendation delivery_status values',
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
