"""Add first-version photo risk scoring service tables."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.helpers import apply_system_schema, default_scope, validate_system_schema
from db_migrations.core import MigrationSpec


PHOTO_RISK_TABLE_NAMES = {
    "photo_risk_assets",
    "photo_risk_score_runs",
    "photo_risk_feature_snapshots",
    "photo_risk_decisions",
    "photo_risk_review_queue",
}


def _photo_risk_tables() -> tuple[_schema.TableDef, ...]:
    return tuple(table for table in _schema.chat_tables() if table.name in PHOTO_RISK_TABLE_NAMES)


MIGRATION = MigrationSpec(
    migration_id="0003_add_photo_risk_service_tables",
    description="Add photo risk scoring service tables",
    scope_fn=default_scope,
    apply_fn=apply_system_schema(_photo_risk_tables()),
    validate_fn=validate_system_schema(_photo_risk_tables()),
)
