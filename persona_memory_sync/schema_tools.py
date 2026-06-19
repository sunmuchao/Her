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
    DEFAULT_CONVERSATION_SUMMARIES_TABLE,
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
  -- 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style（主观描述）
  -- target_gender 已移动到 profiles 表（硬条件）
  target_age_min INT DEFAULT NULL,
  target_age_max INT DEFAULT NULL,
  target_cities TEXT,
  target_cities_adcodes TEXT,  -- 新增：目标城市编码列表（快速范围搜索）
  target_districts_adcodes TEXT,  -- 新增：目标区县编码列表（精准商圈匹配）
  target_height_min INT DEFAULT NULL,
  target_height_max INT DEFAULT NULL,
  target_weight_min INT DEFAULT NULL,  -- 新增：目标体重下限（kg）
  target_weight_max INT DEFAULT NULL,  -- 新增：目标体重上限（kg）
  target_education_min VARCHAR(32) DEFAULT NULL,  -- 保留：学历字符串（兼容）
  target_education_min_code INT DEFAULT NULL,  -- 新增：学历编码（1-专科，2-本科，3-硕士，4-博士）
  target_income_min_wan INT DEFAULT NULL,
  target_income_max_wan INT DEFAULT NULL,
  target_hometown_cities TEXT,  -- 新增：期望对方家乡列表
  target_hometown_cities_adcodes TEXT,  -- 新增：期望对方家乡编码列表（精准匹配）
  target_house_requirement VARCHAR(32) DEFAULT NULL,  -- 新增：对方房产要求
  target_car_requirement VARCHAR(32) DEFAULT NULL,  -- 新增：对方车产要求
  target_marital_statuses TEXT,
  target_marital_status_strength VARCHAR(32) DEFAULT NULL,
  target_accept_partner_children VARCHAR(16) DEFAULT NULL,
  target_accept_partner_children_strength VARCHAR(32) DEFAULT NULL,
  target_accept_long_distance VARCHAR(16) DEFAULT NULL,
  target_location_semantics VARCHAR(128) DEFAULT NULL,
  target_smoke_acceptance VARCHAR(32) DEFAULT NULL,  -- 新增：对方抽烟接受度
  target_drink_acceptance VARCHAR(32) DEFAULT NULL,  -- 新增：对方喝酒接受度
  target_requires_partner_accept_my_children TINYINT(1) DEFAULT NULL,
  target_want_children VARCHAR(16) DEFAULT NULL,
  target_marriage_timeline VARCHAR(32) DEFAULT NULL,
  -- must_have_tags 和 must_not_have_tags 已删除
  -- 不可量化字段已删除：preferred_traits, disliked_traits（性格特质偏好）
  -- 不可量化字段已删除：persona_summary_internal, preference_summary_internal, public_*（文本摘要）
  last_confirmed_at DATETIME DEFAULT NULL,
  last_inferred_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user_personas_profile_id (profile_id),
  KEY idx_target_education_min_code (target_education_min_code),  -- 新增：学历编码索引
  KEY idx_target_cities_adcodes (target_cities_adcodes(100))  -- 新增：城市编码索引（前100字符）
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
  source_channel VARCHAR(64) DEFAULT NULL,
  action_type ENUM('insert','update','skip') NOT NULL DEFAULT 'insert',
  applied_to_persona TINYINT(1) NOT NULL DEFAULT 0,
  applied_to_profile TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_user_persona_observations_user_key (user_key),
  KEY idx_user_persona_observations_persona_id (persona_id),
  KEY idx_user_persona_observations_field_name (field_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

# 新增：对话摘要表（按字段存储LLM提炼的结构化数据）
# 修正版：每个字段单独存储，对应一个向量类型
CONVERSATION_SUMMARIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {conversation_summaries_table} (
  summary_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  conversation_id VARCHAR(191) NOT NULL COMMENT '对话ID（可以是discovery session、chat thread等）',
  conversation_type VARCHAR(32) NOT NULL COMMENT '对话类型（discovery/chat/assessment等）',
  requester_id BIGINT NOT NULL COMMENT '用户ID',
  profile_id BIGINT NOT NULL COMMENT '画像ID',
  summary_key VARCHAR(50) NOT NULL COMMENT '字段名（如 personality_traits、values、partner_expectation）',
  summary_text VARCHAR(500) NOT NULL COMMENT '字段值（如 "性格温柔、内向"、"重视家庭"）',
  vector_status VARCHAR(20) DEFAULT 'pending' COMMENT '向量化状态: pending(待处理), done(已完成), failed(失败), retrying(重试中)',
  retry_count INT DEFAULT 0 COMMENT '重试次数（最多3次）',
  error_message VARCHAR(255) DEFAULT NULL COMMENT '错误信息（向量库写入失败时记录）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  KEY idx_conversation_summaries_conversation_id (conversation_id),
  KEY idx_conversation_summaries_requester_id (requester_id),
  KEY idx_conversation_summaries_profile_id (profile_id),
  KEY idx_conversation_summaries_key (summary_key),
  KEY idx_conversation_summaries_type (conversation_type),
  KEY idx_conversation_summaries_vector_status (vector_status),
  UNIQUE KEY unique_conversation_key (conversation_id, summary_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '对话摘要表（按字段存储），每个字段对应一个向量类型'
"""

PERSONA_EXTENSION_COLUMNS = {
    # 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style
    "target_weight_min": "INT DEFAULT NULL COMMENT '目标体重下限（kg）'",  # 新增
    "target_weight_max": "INT DEFAULT NULL COMMENT '目标体重上限（kg）'",  # 新增
    "target_hometown_cities": "TEXT COMMENT '期望对方家乡列表'",  # 新增
    "target_hometown_cities_adcodes": "TEXT COMMENT '期望对方家乡编码列表'",  # 新增：精准匹配
    "target_house_requirement": "VARCHAR(32) DEFAULT NULL COMMENT '对方房产要求'",  # 新增
    "target_car_requirement": "VARCHAR(32) DEFAULT NULL COMMENT '对方车产要求'",  # 新增
    "target_smoke_acceptance": "VARCHAR(32) DEFAULT NULL COMMENT '对方抽烟接受度'",  # 新增
    "target_drink_acceptance": "VARCHAR(32) DEFAULT NULL COMMENT '对方喝酒接受度'",  # 新增
    "target_cities_adcodes": "TEXT COMMENT '目标城市编码列表'",  # 新增：快速范围搜索
    "target_districts_adcodes": "TEXT COMMENT '目标区县编码列表'",  # 新增：精准商圈匹配
    "target_education_min_code": "INT DEFAULT NULL COMMENT '目标学历下限编码（1-专科，2-本科，3-硕士，4-博士）'",  # 新增：量化学历
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
    # 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style
    # target_gender 已移动到 profiles 表
    "target_age_min",
    "target_age_max",
    "target_cities",
    "target_cities_adcodes",  # 新增：目标城市编码列表
    "target_districts_adcodes",  # 新增：目标区县编码列表
    "target_height_min",
    "target_height_max",
    "target_weight_min",  # 新增：目标体重下限
    "target_weight_max",  # 新增：目标体重上限
    "target_education_min",  # 保留：学历字符串（兼容）
    "target_education_min_code",  # 新增：学历编码
    "target_income_min_wan",
    "target_income_max_wan",
    "target_hometown_cities",  # 新增：期望对方家乡列表
    "target_hometown_cities_adcodes",  # 新增：期望对方家乡编码列表
    "target_house_requirement",  # 新增：对方房产要求
    "target_car_requirement",  # 新增：对方车产要求
    "target_marital_statuses",
    "target_marital_status_strength",
    "target_accept_partner_children",
    "target_accept_partner_children_strength",
    "target_accept_long_distance",
    "target_location_semantics",
    "target_smoke_acceptance",  # 新增：对方抽烟接受度
    "target_drink_acceptance",  # 新增：对方喝酒接受度
    "target_requires_partner_accept_my_children",
    "target_want_children",
    "target_marriage_timeline",
    # must_have_tags 和 must_not_have_tags 已删除
    # 不可量化字段已删除：preferred_traits, disliked_traits
    # 不可量化字段已删除：persona_summary_internal, preference_summary_internal, public_*_draft
    "last_confirmed_at",
    "last_inferred_at",
    "created_at",
    "updated_at",
)

OBSERVATION_EXTENSION_COLUMNS = {
    "source_channel": "VARCHAR(64) DEFAULT NULL",
}

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
    "source_channel",
    "action_type",
    "applied_to_persona",
    "applied_to_profile",
    "created_at",
)

# 新增：conversation_summaries 表的必需列（修正版）
CONVERSATION_SUMMARIES_REQUIRED_COLUMNS = (
    "summary_id",
    "conversation_id",
    "conversation_type",
    "requester_id",
    "profile_id",
    "summary_key",  # 新增：字段名
    "summary_text",  # 新增：字段值（替代原来的 summary）
    "vector_status",  # 新增：向量化状态
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class ResolvedPersonaSchemaTarget:
    source: str
    persona_table: str
    observation_table: str
    profile_table: str
    public_view: str
    conversation_summaries_table: str


def resolve_persona_schema_target(
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
    conversation_summaries_table: str | None = None,
) -> ResolvedPersonaSchemaTarget:
    source_config = parse_mysql_source(source)
    resolved_profile_table = profile_table or source_config["table"] or DEFAULT_PROFILE_TABLE
    return ResolvedPersonaSchemaTarget(
        source=source_config["source"],
        persona_table=persona_table or DEFAULT_PERSONA_TABLE,
        observation_table=observation_table or DEFAULT_OBSERVATION_TABLE,
        profile_table=resolved_profile_table,
        public_view=public_view or DEFAULT_PUBLIC_VIEW,
        conversation_summaries_table=conversation_summaries_table or DEFAULT_CONVERSATION_SUMMARIES_TABLE,
    )


def build_persona_scope(
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
    conversation_summaries_table: str | None = None,
) -> str:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
        conversation_summaries_table=conversation_summaries_table,
    )
    return (
        "persona:"
        f"{resolved.persona_table}:"
        f"{resolved.observation_table}:"
        f"{resolved.profile_table}:"
        f"{resolved.public_view}:"
        f"{resolved.conversation_summaries_table}"
    )


def ensure_persona_schema(
    mysql_conn: Any,
    *,
    source: str | None = None,
    persona_table: str | None = None,
    observation_table: str | None = None,
    profile_table: str | None = None,
    public_view: str | None = None,
    conversation_summaries_table: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
        conversation_summaries_table=conversation_summaries_table,
    )
    if not table_exists(mysql_conn, resolved.profile_table):
        raise ValueError(f"Profile table does not exist: {resolved.profile_table}")

    created_columns: list[str] = []
    with mysql_conn.cursor() as cursor:
        cursor.execute(PERSONA_TABLE_SQL.format(persona_table=quote_mysql_ident(resolved.persona_table)))
        cursor.execute(
            OBSERVATION_TABLE_SQL.format(observation_table=quote_mysql_ident(resolved.observation_table))
        )
        # 新增：创建 conversation_summaries 表
        cursor.execute(
            CONVERSATION_SUMMARIES_TABLE_SQL.format(
                conversation_summaries_table=quote_mysql_ident(resolved.conversation_summaries_table)
            )
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

        cursor.execute(f"SHOW COLUMNS FROM {quote_mysql_ident(resolved.observation_table)}")
        existing_observation_columns = {row["Field"] for row in cursor.fetchall()}
        for column_name, column_type in OBSERVATION_EXTENSION_COLUMNS.items():
            if column_name in existing_observation_columns:
                continue
            cursor.execute(
                f"ALTER TABLE {quote_mysql_ident(resolved.observation_table)} "
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
        "conversation_summaries_table": resolved.conversation_summaries_table,
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
    conversation_summaries_table: str | None = None,
) -> dict[str, list[str]]:
    resolved = resolve_persona_schema_target(
        source=source,
        persona_table=persona_table,
        observation_table=observation_table,
        profile_table=profile_table,
        public_view=public_view,
        conversation_summaries_table=conversation_summaries_table,
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

    # 新增：验证 conversation_summaries 表
    if not table_exists(mysql_conn, resolved.conversation_summaries_table):
        issues["missing_tables"].append(resolved.conversation_summaries_table)
    else:
        existing = _fetch_columns(mysql_conn, resolved.conversation_summaries_table)
        for column_name in CONVERSATION_SUMMARIES_REQUIRED_COLUMNS:
            if column_name not in existing:
                issues["missing_columns"].append(f"{resolved.conversation_summaries_table}.{column_name}")

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
