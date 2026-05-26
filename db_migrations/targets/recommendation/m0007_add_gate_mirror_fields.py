"""Add gate mirror columns to profile_recommendations (§13.1.3)."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

PROFILE_RECOMMENDATIONS_GATE_PATCH = _schema.TableDef(
    name="profile_recommendations",
    columns=(
        _schema.ColumnDef("gate_outcome", "VARCHAR(16)"),
        _schema.ColumnDef("gate_reason_codes_json", "LONGTEXT"),
        _schema.ColumnDef("gate_owner_service", "VARCHAR(64)"),
        _schema.ColumnDef("gate_details_ref", "VARCHAR(255)"),
        _schema.ColumnDef("gate_evaluated_at", "DATETIME"),
    ),
    primary_key=("recommendation_id",),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table_columns(mysql_conn, PROFILE_RECOMMENDATIONS_GATE_PATCH, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (PROFILE_RECOMMENDATIONS_GATE_PATCH,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0007_add_gate_mirror_fields",
    description="Add gate_outcome mirror fields to profile recommendations",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
