"""Add rule_config_versions and rule_config_assignments (§13.5)."""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

RULE_CONFIG_VERSIONS = _schema.TableDef(
    name="rule_config_versions",
    columns=(
        _schema.ColumnDef("version_id", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("slice_id", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("params_json", "LONGTEXT", nullable=False),
        _schema.ColumnDef("schema_version", "VARCHAR(32)", nullable=False),
        _schema.ColumnDef("status", "VARCHAR(32)", nullable=False),
        _schema.ColumnDef("created_by", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("created_at", "DATETIME", nullable=False),
    ),
    primary_key=("version_id",),
    indexes=(
        _schema.IndexDef(("slice_id", "status", "created_at"), "idx_rule_config_versions_slice_status"),
    ),
)

RULE_CONFIG_ASSIGNMENTS = _schema.TableDef(
    name="rule_config_assignments",
    columns=(
        _schema.ColumnDef("assignment_id", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("version_id", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("slice_id", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("scope_type", "VARCHAR(64)", nullable=False),
        _schema.ColumnDef("scope_key", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("priority", "INT", nullable=False),
        _schema.ColumnDef("effective_from", "DATETIME"),
        _schema.ColumnDef("effective_until", "DATETIME"),
        _schema.ColumnDef("created_by", "VARCHAR(191)", nullable=False),
        _schema.ColumnDef("created_at", "DATETIME", nullable=False),
    ),
    primary_key=("assignment_id",),
    indexes=(
        _schema.IndexDef(
            ("slice_id", "scope_type", "scope_key", "priority"),
            "idx_rule_config_assignments_scope",
        ),
    ),
    foreign_keys=(
        _schema.ForeignKeyDef(("version_id",), "rule_config_versions", ("version_id",)),
    ),
)


def apply(mysql_conn, _context: MigrationContext) -> None:
    _schema.ensure_table(mysql_conn, RULE_CONFIG_VERSIONS, prefix=None)
    _schema.ensure_table(mysql_conn, RULE_CONFIG_ASSIGNMENTS, prefix=None)


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    return _schema.validate_schema(
        mysql_conn,
        (RULE_CONFIG_VERSIONS, RULE_CONFIG_ASSIGNMENTS),
        prefix=None,
    )


MIGRATION = MigrationSpec(
    migration_id="0008_rule_config_tables",
    description="Add rule config version and assignment tables",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
