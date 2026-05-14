"""Core types and constants for schema migrations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import outer_system_mysql_schema as _schema


INIT_MODE_ENV = "HER_SCHEMA_INIT_MODE"
DEFAULT_INIT_MODE = "migrate"
VALID_INIT_MODES = frozenset({"migrate", "validate"})
MIGRATION_TABLE_NAME = "schema_migrations"

TargetApplyFn = Callable[[Any, "MigrationContext"], None]
TargetValidateFn = Callable[[Any, "MigrationContext"], dict[str, list[str]]]
ScopeFn = Callable[["MigrationContext"], str]


@dataclass(frozen=True)
class MigrationContext:
    target: str
    config: dict[str, Any]
    source: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MigrationSpec:
    migration_id: str
    description: str
    scope_fn: ScopeFn
    apply_fn: TargetApplyFn
    validate_fn: TargetValidateFn

    def scope_for(self, context: MigrationContext) -> str:
        return self.scope_fn(context)

    def checksum_for(self, context: MigrationContext) -> str:
        payload = f"{context.target}:{self.migration_id}:{self.description}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TargetDefinition:
    env_var: str
    package: str


class SchemaMigrationError(RuntimeError):
    """Raised when an upgrade cannot be applied safely."""


class SchemaValidationError(SchemaMigrationError):
    """Raised when schema validation fails."""

    def __init__(self, target: str, issues: Mapping[str, Sequence[str]]) -> None:
        self.target = target
        self.issues = {key: list(values) for key, values in issues.items() if values}
        message = f"Schema validation failed for {target}: {json.dumps(self.issues, ensure_ascii=False, sort_keys=True)}"
        super().__init__(message)


MIGRATION_TABLE = _schema.TableDef(
    name=MIGRATION_TABLE_NAME,
    columns=(
        _schema.ColumnDef("scope", "VARCHAR(255)", nullable=False),
        _schema.ColumnDef("migration_id", "VARCHAR(64)", nullable=False),
        _schema.ColumnDef("checksum", "VARCHAR(64)", nullable=False),
        _schema.ColumnDef("description", "VARCHAR(255)", nullable=False),
        _schema.ColumnDef("applied_at", "DATETIME", nullable=False),
    ),
    primary_key=("scope", "migration_id"),
    indexes=(
        _schema.IndexDef(("applied_at",), "idx_schema_migrations_applied_at"),
    ),
)


def empty_issues() -> dict[str, list[str]]:
    return {
        "missing_tables": [],
        "missing_columns": [],
        "missing_unique_keys": [],
        "missing_indexes": [],
        "missing_views": [],
        "incompatible_columns": [],
        "missing_migrations": [],
        "checksum_mismatches": [],
        "unexpected_migrations": [],
    }


def merge_issues(target: dict[str, list[str]], incoming: Mapping[str, Sequence[str]]) -> None:
    for key, values in incoming.items():
        bucket = target.setdefault(key, [])
        for value in values:
            text = str(value)
            if text not in bucket:
                bucket.append(text)

