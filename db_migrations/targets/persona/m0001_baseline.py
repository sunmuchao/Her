"""Baseline persona schema migration."""

from __future__ import annotations

from db_migrations.helpers import apply_persona_schema, baseline_migration, persona_scope, validate_persona_schema


MIGRATION = baseline_migration(
    description="Baseline persona memory schema",
    scope_fn=persona_scope,
    apply_fn=apply_persona_schema,
    validate_fn=validate_persona_schema,
)
