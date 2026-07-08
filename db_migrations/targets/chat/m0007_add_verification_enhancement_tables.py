"""Add verification enhancement tables and fields.

This migration implements Phase 1.1 of the verification security improvement plan:
1. Create verification_level_weights table
2. Create verification_submission_metadata table (split from metadata_json)
3. Create verification_revocations table
4. Create verification_auto_review_stats and verification_review_latency tables
5. Create verification_data_governance_policies table
6. Add new fields to verification_submissions table
7. Add new fields to profile_field_verification_submissions table
"""

from __future__ import annotations

import outer_system_mysql_schema as _schema

from db_migrations.core import MigrationContext, MigrationSpec
from db_migrations.helpers import default_scope

# 新增的表名集合
NEW_TABLE_NAMES = {
    "verification_level_weights",
    "verification_submission_metadata",
    "verification_revocations",
    "verification_auto_review_stats",
    "verification_review_latency",
    "verification_data_governance_policies",
}

# 需要添加新字段的表名集合
MODIFIED_TABLE_NAMES = {
    "verification_submissions",
    "profile_field_verification_submissions",
}


def _new_tables():
    """获取新增的表定义"""
    return tuple(table for table in _schema.chat_tables() if table.name in NEW_TABLE_NAMES)


def _modified_tables():
    """获取需要修改的表定义"""
    # profile_field_verification_submissions 在 verification_tables() 中
    chat_modified = tuple(table for table in _schema.chat_tables() if table.name in MODIFIED_TABLE_NAMES)
    verification_modified = tuple(table for table in _schema.verification_tables() if table.name in MODIFIED_TABLE_NAMES)
    return chat_modified + verification_modified


def apply(mysql_conn, _context: MigrationContext) -> None:
    """应用迁移"""
    # 1. 创建新表
    new_tables = _new_tables()
    for table in new_tables:
        if not _schema.table_exists(mysql_conn, table.name):
            _schema.ensure_table(mysql_conn, table, prefix=None, config=_context.config)
            print(f"Created table: {table.name}")
        _schema.ensure_table_columns(mysql_conn, table, prefix=None)
        _schema.ensure_unique_keys(mysql_conn, table, prefix=None)
        _schema.ensure_indexes(mysql_conn, table, prefix=None)

    # 1.5. 确保需要修改的表存在（如果不存在则创建）
    modified_tables = _modified_tables()
    for table in modified_tables:
        if not _schema.table_exists(mysql_conn, table.name):
            _schema.ensure_table(mysql_conn, table, prefix=None, config=_context.config)
            print(f"Created missing table: {table.name}")
            _schema.ensure_table_columns(mysql_conn, table, prefix=None)
            _schema.ensure_unique_keys(mysql_conn, table, prefix=None)
            _schema.ensure_indexes(mysql_conn, table, prefix=None)

    # 2. 修改现有表，添加新字段和索引
    for table in modified_tables:
        if _schema.table_exists(mysql_conn, table.name):
            _schema.ensure_table_columns(mysql_conn, table, prefix=None)
            _schema.ensure_indexes(mysql_conn, table, prefix=None)
            print(f"Updated table: {table.name}")

    # 3. 插入初始数据
    # 插入认证等级权重初始数据
    cursor = mysql_conn.cursor()
    cursor.execute("""
        INSERT INTO verification_level_weights
        (level_name, weight, label, expires_after_days, created_at)
        VALUES
        ('offline_verified', 4, '线下核验照片', NULL, NOW()),
        ('live_video_verified', 3, '活体自拍视频认证', 365, NOW()),
        ('human_verified', 2, '真人照片认证', 365, NOW()),
        ('uploaded', 1, '普通上传照片', NULL, NOW())
        ON DUPLICATE KEY UPDATE weight=VALUES(weight), label=VALUES(label)
    """)
    print("Inserted verification_level_weights initial data")

    # 插入敏感数据治理策略初始数据
    cursor.execute("""
        INSERT INTO verification_data_governance_policies
        (policy_key, retention_days, encryption_required, access_scope, created_at, updated_at)
        VALUES
        ('raw_verification_media', 30, 1, 'risk_ops,verification_ops', NOW(), NOW()),
        ('ocr_extracted_text', 180, 1, 'verification_ops', NOW(), NOW()),
        ('authority_verification_result', 365, 1, 'verification_ops,risk_ops', NOW(), NOW()),
        ('revocation_evidence', 730, 1, 'risk_ops,compliance_ops', NOW(), NOW())
        ON DUPLICATE KEY UPDATE retention_days=VALUES(retention_days), access_scope=VALUES(access_scope)
    """)
    print("Inserted verification_data_governance_policies initial data")

    mysql_conn.commit()


def validate(mysql_conn, _context: MigrationContext) -> dict[str, list[str]]:
    """验证迁移"""
    results = {}

    # 验证新表
    new_table_errors = _schema.validate_schema(mysql_conn, _new_tables(), prefix=None)
    if new_table_errors:
        results["new_tables"] = new_table_errors

    # 验证修改的表
    modified_table_errors = _schema.validate_schema(mysql_conn, _modified_tables(), prefix=None)
    if modified_table_errors:
        results["modified_tables"] = modified_table_errors

    # 验证初始数据
    # 检查认证等级权重数据
    cursor = mysql_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM verification_level_weights")
    level_count = cursor.fetchone()[0]
    if level_count != 4:
        results["initial_data"] = [f"Expected 4 level weights, found {level_count}"]

    # 检查敏感数据治理策略数据
    cursor.execute("SELECT COUNT(*) FROM verification_data_governance_policies")
    policy_count = cursor.fetchone()[0]
    if policy_count != 4:
        results["initial_data"] = [f"Expected 4 governance policies, found {policy_count}"]

    return results


MIGRATION = MigrationSpec(
    migration_id="0007_add_verification_enhancement_tables",
    description="Add verification enhancement tables and fields for security improvement",
    scope_fn=default_scope,
    apply_fn=apply,
    validate_fn=validate,
)