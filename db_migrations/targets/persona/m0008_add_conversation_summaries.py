"""Add conversation summaries table for storing LLM-generated user summaries."""

from __future__ import annotations

from db_migrations.helpers import apply_persona_schema, persona_scope, validate_persona_schema
from db_migrations.core import MigrationSpec


MIGRATION = MigrationSpec(
    migration_id="0008_conversation_summaries_table",
    description="Add conversation summaries table for storing LLM-generated user summaries (personality traits, emotional state, partner expectations) across all conversation types (discovery/chat/assessment)",
    scope_fn=persona_scope,
    apply_fn=apply_persona_schema,
    validate_fn=validate_persona_schema,
)