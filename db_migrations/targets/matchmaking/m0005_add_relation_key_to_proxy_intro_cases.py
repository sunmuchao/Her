"""Schema migration 0005_add_relation_key_to_proxy_intro_cases for matchmaking."""

from __future__ import annotations

import json
from typing import Any

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from db_migrations.helpers import default_scope


def apply(mysql_conn, context: MigrationContext) -> None:
    """添加 relation_key 列到 proxy_intro_cases 表，并为现有数据回填 relation_key"""
    cursor = mysql_conn.cursor()

    # Step 1: 添加 relation_key 列
    cursor.execute("""
        ALTER TABLE proxy_intro_cases
        ADD COLUMN relation_key TEXT
    """)

    # Step 2: 为现有数据回填 relation_key
    # 先尝试从 recommendation 获取
    cursor.execute("""
        SELECT case_id, subscription_id, candidate_id, requester_id
        FROM proxy_intro_cases
        WHERE relation_key IS NULL OR relation_key = ''
    """)
    cases_to_update = cursor.fetchall()

    for row in cases_to_update:
        case_id = row['case_id']
        subscription_id = row['subscription_id']
        candidate_id = row['candidate_id']
        requester_id = row['requester_id']
        relation_key = None

        # 尝试从 recommendation 获取 relation_key
        try:
            cursor.execute("""
                SELECT relation_key
                FROM profile_recommendations
                WHERE subscription_id = %s AND candidate_id = %s
                LIMIT 1
            """, (subscription_id, candidate_id))
            rec_row = cursor.fetchone()
            if rec_row and rec_row.get('relation_key'):
                relation_key = str(rec_row['relation_key']).strip()
        except Exception:
            pass  # 如果 recommendation 查询失败，继续使用兜底逻辑

        # 如果从 recommendation 获取失败，根据 requester 和 candidate 生成
        if not relation_key:
            from match_domain import matchmaking_relation_key
            requester_info = {"source": "her", "self_id": requester_id, "user_key": str(requester_id)}
            candidate_info = {"source": "her", "self_id": candidate_id, "user_key": str(candidate_id)}
            member_low, member_high = sorted([requester_info, candidate_info], key=lambda x: int(x.get("self_id") or 0))
            relation_key = matchmaking_relation_key(member_low, member_high)

        # 更新 case 的 relation_key
        cursor.execute("""
            UPDATE proxy_intro_cases
            SET relation_key = %s
            WHERE case_id = %s
        """, (relation_key, case_id))

    mysql_conn.commit()


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    """验证迁移结果：relation_key 列存在，且所有 case 都有 relation_key"""
    issues = empty_issues()

    cursor = mysql_conn.cursor()

    # 检查 relation_key 列是否存在
    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'proxy_intro_cases'
        AND COLUMN_NAME = 'relation_key'
    """)
    result = cursor.fetchone()
    column_exists = result['cnt'] > 0

    if not column_exists:
        issues["missing_columns"].append("proxy_intro_cases.relation_key")
        # 列不存在，跳过数据检查
        return issues

    # 检查是否存在 relation_key 为空的 case
    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM proxy_intro_cases
        WHERE relation_key IS NULL OR relation_key = ''
    """)
    result = cursor.fetchone()
    empty_count = result['cnt']

    if empty_count > 0:
        issues["incompatible_columns"].append(f"proxy_intro_cases.relation_key: {empty_count} rows have empty values")

    return issues


MIGRATION = MigrationSpec(
    migration_id="0005_add_relation_key_to_proxy_intro_cases",
    description="Add relation_key column to proxy_intro_cases table",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)
