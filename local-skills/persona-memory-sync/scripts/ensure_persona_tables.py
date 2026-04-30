#!/usr/bin/env python3

from __future__ import annotations

import argparse

from persona_memory_lib import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PROFILE_TABLE,
    DEFAULT_PUBLIC_VIEW,
    PROFILE_EXTENSION_COLUMNS,
    build_public_profile_view_sql,
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Create persona memory tables and extend profiles for internal/public sync.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--public-view", default=DEFAULT_PUBLIC_VIEW)
    args = parser.parse_args()

    config = parse_mysql_source(args.source)
    profile_table = args.profile_table or config["table"] or DEFAULT_PROFILE_TABLE
    persona_table = args.persona_table
    observation_table = args.observation_table

    conn = mysql_connect(args.source)
    created_columns = []
    try:
        with conn.cursor() as cursor:
            cursor.execute(PERSONA_TABLE_SQL.format(persona_table=quote_mysql_ident(persona_table)))
            cursor.execute(
                OBSERVATION_TABLE_SQL.format(observation_table=quote_mysql_ident(observation_table))
            )

            cursor.execute(f"SHOW COLUMNS FROM {quote_mysql_ident(persona_table)}")
            existing_persona_columns = {row["Field"] for row in cursor.fetchall()}
            for column_name, column_type in PERSONA_EXTENSION_COLUMNS.items():
                if column_name in existing_persona_columns:
                    continue
                cursor.execute(
                    f"ALTER TABLE {quote_mysql_ident(persona_table)} "
                    f"ADD COLUMN {quote_mysql_ident(column_name)} {column_type}"
                )

            cursor.execute(f"SHOW FULL COLUMNS FROM {quote_mysql_ident(profile_table)}")
            existing_column_rows = {row["Field"]: row for row in cursor.fetchall()}
            existing_columns = set(existing_column_rows)
            for column_name, column_type in PROFILE_EXTENSION_COLUMNS.items():
                if column_name in existing_columns:
                    continue
                cursor.execute(
                    f"ALTER TABLE {quote_mysql_ident(profile_table)} "
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
                    f"ALTER TABLE {quote_mysql_ident(profile_table)} "
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
                    f"ALTER TABLE {quote_mysql_ident(profile_table)} "
                    f"MODIFY COLUMN {quote_mysql_ident(column_name)} {upgrade['ddl']}"
                )

            cursor.execute(build_public_profile_view_sql(profile_table=profile_table, view_name=args.public_view))

        conn.commit()
    finally:
        conn.close()

    print(f"persona_table={persona_table}")
    print(f"observation_table={observation_table}")
    print(f"profile_table={profile_table}")
    print(f"public_view={args.public_view}")
    if created_columns:
        print("created_profile_columns=" + ",".join(created_columns))
    else:
        print("created_profile_columns=")


if __name__ == "__main__":
    main()
