"""Schema migration entry points for Her outer systems."""

from .core import DEFAULT_INIT_MODE, INIT_MODE_ENV, SchemaMigrationError, SchemaValidationError
from .runner import (
    get_migration_status,
    initialize_target_database,
    resolve_init_mode,
    upgrade_target_database,
    validate_target_database,
)

__all__ = [
    "DEFAULT_INIT_MODE",
    "INIT_MODE_ENV",
    "SchemaMigrationError",
    "SchemaValidationError",
    "get_migration_status",
    "initialize_target_database",
    "resolve_init_mode",
    "upgrade_target_database",
    "validate_target_database",
]
