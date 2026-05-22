"""Add recommendation-side mirror field for the active proxy-intro case status."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

PROFILE_RECOMMENDATIONS_ACTIVE_CASE_STATUS_PATCH = _schema.TableDef(
    name="profile_recommendations",
    columns=(
        _schema.ColumnDef("active_case_status", "VARCHAR(64)"),
    ),
    primary_key=("recommendation_id",),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table_columns(mysql_conn, PROFILE_RECOMMENDATIONS_ACTIVE_CASE_STATUS_PATCH, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (PROFILE_RECOMMENDATIONS_ACTIVE_CASE_STATUS_PATCH,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0004_add_active_case_status",
    description="Add active_case_status mirror field to profile recommendations",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
