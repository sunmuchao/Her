"""Shared schema helpers for persona-memory-sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from outer_system_mysql_schema import quote_mysql_ident, table_exists

from .persona_memory_lib import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PROFILE_TABLE,
    DEFAULT_PUBLIC_VIEW,
    PROFILE_EXTENSION_COLUMNS,
    build_public_profile_view_sql,
    parse_mysql_source,
)


PERSONA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {persona_table} (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(64) DEFAULT NULL,
  profile_id BIGINT DEFAULT NULL,
  self_gender VARCHAR(8) DEFAULT NULL,
  self_age INT DEFAULT NULL,
  self_city VARCHAR(64) DEFAULT NULL,
  self_district VARCHAR(64) DEFAULT NULL,
  self_height INT DEFAULT NULL,
  self_education VARCHAR(32) DEFAULT NULL,
  self_income_wan INT DEFAULT NULL,
  self_job VARCHAR(64) DEFAULT NULL,
  self_life_rhythm VARCHAR(64) DEFAULT NULL,
  self_work_pattern VARCHAR(64) DEFAULT NULL,
  self_expression_style VARCHAR(64) DEFAULT NULL,
  self_marital_status VARCHAR(32) DEFAULT NULL,
  self_has_children TINYINT(1) DEFAULT NULL,
  self_children_count INT DEFAULT NULL,
  self_children_living_with_self TINYINT(1) DEFAULT NULL,
  self_smoking VARCHAR(16) DEFAULT NULL,
  self_drinking VARCHAR(16) DEFAULT NULL,
  self_relationship_goal VARCHAR(32) DEFAULT NULL,
  target_gender VARCHAR(8) DEFAULT NULL,
  target_age_min INT DEFAULT NULL,
  target_age_max INT DEFAULT NULL,
  target_cities TEXT,
  target_height_min INT DEFAULT NULL,
  target_height_max INT DEFAULT NULL,
  target_education_min VARCHAR(32) DEFAULT NULL,
  target_income_min_wan INT DEFAULT NULL,
  target_income_max_wan INT DEFAULT NULL,
  target_marital_statuses TEXT,
  target_marital_status_strength VARCHAR(32) DEFAULT NULL,
  target_accept_partner_children VARCHAR(16) DEFAULT NULL,
  target_accept_partner_children_strength VARCHAR(32) DEFAULT NULL,
  target_accept_long_distance VARCHAR(16) DEFAULT NULL,
  target_location_semantics VARCHAR(128) DEFAULT NULL,
  target_requires_partner_accept_my_children TINYINT(1) DEFAULT NULL,
  target_want_children VARCHAR(16) DEFAULT NULL,
  target_marriage_timeline VARCHAR(32) DEFAULT NULL,
  must_have_tags TEXT,
  must_not_have_tags TEXT,
  preferred_traits TEXT,
  disliked_traits TEXT,
  persona_summary_internal TEXT,
  preference_summary_internal TEXT,
  public_profile_summary_draft TEXT,
  public_preference_summary_draft TEXT,
  last_confirmed_at DATETIME DEFAULT NULL,
  last_inferred_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user_personas_profile_id (profile_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

OBSERVATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {observation_table} (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL,
  persona_id BIGINT DEFAULT NULL,
  field_name VARCHAR(64) NOT NULL,
  field_value TEXT,
  source_type ENUM('explicit','strong_inference','weak_inference') NOT NULL,
  confidence_score INT DEFAULT NULL,
  evidence_text TEXT,
  conversation_ref VARCHAR(128) DEFAULT NULL,
  action_type ENUM('insert','update','skip') NOT NULL DEFAULT 'insert',
  applied_to_persona TINYINT(1) NOT NULL DEFAULT 0,
  applied_to_profile TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_user_persona_observations_user_key (user_key),
  KEY idx_user_persona_observations_persona_id (persona_id),
  KEY idx_user_persona_observations_field_name (field_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

PERSONA_EXTENSION_COLUMNS = {
    "self_life_rhythm": "VARCHAR(64) DEFAULT NULL",
    "self_work_pattern": "VARCHAR(64) DEFAULT NULL",
    "self_expression_style": "VARCHAR(64) DEFAULT NULL",
    "self_children_count": "INT DEFAULT NULL",
    "self_children_living_with_self": "TINYINT(1) DEFAULT NULL",
    "target_marital_status_strength": "VARCHAR(32) DEFAULT NULL",
    "target_accept_partner_children_strength": "VARCHAR(32) DEFAULT NULL",
    "target_location_semantics": "VARCHAR(128) DEFAULT NULL",
    "target_requires_partner_accept_my_children": "TINYINT(1) DEFAULT NULL",
}

PROFILE_ENUM_UPGRADES = {
    "accept_partner_children": {
        "required_literals": ["接受", "不接受", "可协商", "现阶段不太接受", "谨慎可协商", "未知"],
        "ddl": (
            "ENUM('接受','不接受','可协商','现阶段不太接受','谨慎可协商','未知') "
            "DEFAULT NULL COMMENT '是否接受对方已有孩子'"
        ),
    }
}

PROFILE_COLUMN_TYPE_UPGRADES = {
    "accept_long_distance": {
        "expected_type": "varchar(16)",
        "ddl": "VARCHAR(16) DEFAULT NULL COMMENT '是否接受异地或近距离过渡'",
    }
}

PERSONA_REQUIRED_COLUMNS = (
    "id",
    "user_key",
    "display_name",
    "profile_id",
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_life_rhythm",
    "self_work_pattern",
    "self_expression_style",
    "self_marital_status",
    "self_has_children",
    "self_children_count",
    "self_children_living_with_self",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
    "target_gender",
    "target_age_min",
    "target_age_max",
    "target_cities",
    "target_height_min",
    "target_height_max",
    "target_education_min",
    "target_income_min_wan",
    "target_income_max_wan",
    "target_marital_statuses",
    "target_marital_status_strength",
    "target_accept_partner_children",
    "target_accept_partner_children_strength",
    "target_accept_long_distance",
    "target_location_semantics",
    "target_requires_partner_accept_my_children",
    "target_want_children",
    "target_marriage_timeline",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
    "last_confirmed_at",
    "last_inferred_at",
    "created_at",
    "updated_at",
)

OBSERVATION_REQUIRED_COLUMNS = (
    "id",
    "user_key",
    "persona_id",
    "field_name",
    "field_value",
    "source_type",
    "confidence_score",
    "evidence_text",
    "conversation_ref",
    "action_type",
    "applied_to_persona",
    "applied_to_profile",
    "created_at",
)


@dataclass(frozen=True)
class ResolvedPersonaSchemaTarget:
    source: str
    persona_table: str
    observation_table: str
    profile_table: str
    public_view: str


def resolve_persona_schema_target(
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
) -> ResolvedPersonaSchemaTarget:
    source_config = parse_mysql_source(source)
    resolved_profile_table = profile_table or source_config["table"] or DEFAULT_PROFILE_TABLE
    return ResolvedPersonaSchemaTarget(
        source=source_config["source"],
        persona_table=persona_table or DEFAULT_PERSONA_TABLE,
        observation_table=observation_table or DEFAULT_OBSERVATION_TABLE,
        profile_table=resolved_profile_table,
        public_view=public_view or DEFAULT_PUBLIC_VIEW,
    )


def build_persona_scope(
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
) -> str:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
    )
    return (
        "persona:"
        f"{resolved.persona_table}:"
        f"{resolved.observation_table}:"
        f"{resolved.profile_table}:"
        f"{resolved.public_view}"
    )


def ensure_persona_schema(
    mysql_conn: Any,
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
    )
    if not table_exists(mysql_conn, resolved.profile_table):
        raise ValueError(f"Profile table does not exist: {resolved.profile_table}")

    created_columns: list[str] = []
    with mysql_conn.cursor() as cursor:
        cursor.execute(PERSONA_TABLE_SQL.format(persona_table=quote_mysql_ident(resolved.persona_table)))
        cursor.execute(
            OBSERVATION_TABLE_SQL.format(observation_table=quote_mysql_ident(resolved.observation_table))
        )

        cursor.execute(f"SHOW COLUMNS FROM {quote_mysql_ident(resolved.persona_table)}")
        existing_persona_columns = {row["Field"] for row in cursor.fetchall()}
        for column_name, column_type in PERSONA_EXTENSION_COLUMNS.items():
            if column_name in existing_persona_columns:
                continue
            cursor.execute(
                f"ALTER TABLE {quote_mysql_ident(resolved.persona_table)} "
                f"ADD COLUMN {quote_mysql_ident(column_name)} {column_type}"
            )

        cursor.execute(f"SHOW FULL COLUMNS FROM {quote_mysql_ident(resolved.profile_table)}")
        existing_column_rows = {row["Field"]: row for row in cursor.fetchall()}
        existing_columns = set(existing_column_rows)
        for column_name, column_type in PROFILE_EXTENSION_COLUMNS.items():
            if column_name in existing_columns:
                continue
            cursor.execute(
                f"ALTER TABLE {quote_mysql_ident(resolved.profile_table)} "
                f"ADD COLUMN {quote_mysql_ident(column_name)} {column_type}"
            )
            created_columns.append(column_name)

        for column_name, upgrade in PROFILE_ENUM_UPGRADES.items():
            row = existing_column_rows.get(column_name)
            if not row:
                continue
            column_type = str(row.get("Type") or "").lower()
            if not column_type.startswith("enum("):
                continue
            missing_literals = [
                literal for literal in upgrade["required_literals"] if f"'{literal}'" not in str(row.get("Type") or "")
            ]
            if not missing_literals:
                continue
            cursor.execute(
                f"ALTER TABLE {quote_mysql_ident(resolved.profile_table)} "
                f"MODIFY COLUMN {quote_mysql_ident(column_name)} {upgrade['ddl']}"
            )

        for column_name, upgrade in PROFILE_COLUMN_TYPE_UPGRADES.items():
            row = existing_column_rows.get(column_name)
            if not row:
                continue
            column_type = str(row.get("Type") or "").lower()
            if column_type == upgrade["expected_type"]:
                continue
            cursor.execute(
                f"ALTER TABLE {quote_mysql_ident(resolved.profile_table)} "
                f"MODIFY COLUMN {quote_mysql_ident(column_name)} {upgrade['ddl']}"
            )

        cursor.execute(
            build_public_profile_view_sql(
                profile_table=resolved.profile_table,
                view_name=resolved.public_view,
            )
        )

    if commit:
        mysql_conn.commit()
    return {
        "persona_table": resolved.persona_table,
        "observation_table": resolved.observation_table,
        "profile_table": resolved.profile_table,
        "public_view": resolved.public_view,
        "created_profile_columns": created_columns,
    }


def validate_persona_schema(
    mysql_conn: Any,
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
) -> dict[str, list[str]]:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
    )
    issues = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_views": [],
        "incompatible_columns": [],
    }

    if not table_exists(mysql_conn, resolved.persona_table):
        issues["missing_tables"].append(resolved.persona_table)
    else:
        existing = _fetch_columns(mysql_conn, resolved.persona_table)
        for column_name in PERSONA_REQUIRED_COLUMNS:
            if column_name not in existing:
                issues["missing_columns"].append(f"{resolved.persona_table}.{column_name}")

    if not table_exists(mysql_conn, resolved.observation_table):
        issues["missing_tables"].append(resolved.observation_table)
    else:
        existing = _fetch_columns(mysql_conn, resolved.observation_table)
        for column_name in OBSERVATION_REQUIRED_COLUMNS:
            if column_name not in existing:
                issues["missing_columns"].append(f"{resolved.observation_table}.{column_name}")

    if not table_exists(mysql_conn, resolved.profile_table):
        issues["missing_tables"].append(resolved.profile_table)
    else:
        existing_rows = _fetch_column_rows(mysql_conn, resolved.profile_table)
        for column_name in PROFILE_EXTENSION_COLUMNS:
            if column_name not in existing_rows:
                issues["missing_columns"].append(f"{resolved.profile_table}.{column_name}")

        for column_name, upgrade in PROFILE_ENUM_UPGRADES.items():
            row = existing_rows.get(column_name)
            if not row:
                continue
            column_type = str(row.get("Type") or "").lower()
            if not column_type.startswith("enum("):
                issues["incompatible_columns"].append(f"{resolved.profile_table}.{column_name}:expected_enum")
                continue
            missing_literals = [
                literal for literal in upgrade["required_literals"] if f"'{literal}'" not in str(row.get("Type") or "")
            ]
            if missing_literals:
                issues["incompatible_columns"].append(
                    f"{resolved.profile_table}.{column_name}:missing_enum_literals={','.join(missing_literals)}"
                )

        for column_name, upgrade in PROFILE_COLUMN_TYPE_UPGRADES.items():
            row = existing_rows.get(column_name)
            if not row:
                continue
            column_type = str(row.get("Type") or "").lower()
            if column_type != upgrade["expected_type"]:
                issues["incompatible_columns"].append(
                    f"{resolved.profile_table}.{column_name}:expected_type={upgrade['expected_type']}:actual={column_type}"
                )

    if not _view_exists(mysql_conn, resolved.public_view):
        issues["missing_views"].append(resolved.public_view)

    return issues


def _fetch_columns(mysql_conn: Any, table_name: str) -> set[str]:
    return set(_fetch_column_rows(mysql_conn, table_name))


def _fetch_column_rows(mysql_conn: Any, table_name: str) -> dict[str, dict[str, Any]]:
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SHOW FULL COLUMNS FROM {quote_mysql_ident(table_name)}")
        return {row["Field"]: row for row in cursor.fetchall()}


def _view_exists(mysql_conn: Any, view_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND TABLE_TYPE = 'VIEW'
            LIMIT 1
            """,
            (view_name,),
        )
        return cursor.fetchone() is not None


__all__ = [
    "PROFILE_COLUMN_TYPE_UPGRADES",
    "PROFILE_ENUM_UPGRADES",
    "PERSONA_EXTENSION_COLUMNS",
    "build_persona_scope",
    "ensure_persona_schema",
    "resolve_persona_schema_target",
    "validate_persona_schema",
]
