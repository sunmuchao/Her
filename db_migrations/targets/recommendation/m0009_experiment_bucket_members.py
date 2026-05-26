"""Add experiment_bucket_members for §13.5 phase 4 A/B."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

EXPERIMENT_BUCKET_MEMBERS = _schema.TableDef(
    name="experiment_bucket_members",
    columns=(
        _schema.ColumnDef("profile_id", "BIGINT", nullable=False),
        _schema.ColumnDef("bucket_key", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("updated_by", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("updated_at", "DATETIME", nullable=False),
    ),
    primary_key=("profile_id",),
    indexes=(
        _schema.IndexDef(("bucket_key", "updated_at"), "idx_experiment_bucket_members_bucket"),
    ),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table(mysql_conn, EXPERIMENT_BUCKET_MEMBERS, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(mysql_conn, (EXPERIMENT_BUCKET_MEMBERS,), prefix=None)


MIGRATION = MigrationSpec(
    migration_id="0009_experiment_bucket_members",
    description="Add experiment bucket member mapping for rule A/B",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
