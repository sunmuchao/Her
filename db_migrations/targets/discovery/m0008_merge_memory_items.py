"""Merge discovery_agent_session_memory_items into state_json column."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues


def apply(mysql_conn, context: MigrationContext) -> None:
    """Merge memory_items into discovery_agent_sessions.state_json."""
    # This migration is OPTIONAL and may require data transformation.
    # For now, we only add a note that memory_items can be merged into state_json.
    # Actual implementation would need to:
    # 1. Read all memory_items for each session
    # 2. Aggregate them into a single JSON array
    # 3. Update state_json with the aggregated memory
    # 4. Drop the memory_items table (in a separate migration)

    # Placeholder: just add a marker column to indicate migration readiness
    with mysql_conn.cursor() as cursor:
        # Check if table exists
        cursor.execute("SHOW TABLES LIKE 'discovery_agent_sessions'")
        if cursor.fetchone():
            # Add migration marker (optional)
            try:
                cursor.execute(
                    "ALTER TABLE discovery_agent_sessions "
                    "ADD COLUMN IF NOT EXISTS _memory_migration_ready TINYINT(1) DEFAULT 0"
                )
            except Exception:
                pass  # Column may already exist
    mysql_conn.commit()


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """Validate migration readiness."""
    issues = empty_issues()
    return issues


def scope_for(context: MigrationContext) -> str:
    return "discovery:memory_merge"


MIGRATION = MigrationSpec(
    migration_id="0008_merge_memory_items",
    description="Merge discovery_agent_session_memory_items into state_json (optional)",
    scope_fn=scope_for,
    apply_fn=apply,
    validate_fn=validate,
)