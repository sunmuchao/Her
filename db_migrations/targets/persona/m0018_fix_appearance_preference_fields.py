"""
修复外貌偏好字段：删除错误的评分偏好字段，新增正确的风格偏好字段

【问题根因】
系统错误地将"评分维度"作为偏好学习维度：
- preferred_mature_score（成熟感评分）
- preferred_clean_score（干净感评分）
- preferred_gentle_score（温柔感评分）
- preferred_sunny_score（阳光感评分）
- preferred_stylish_score（精致感评分）

这些字段是错误的，因为：
1. 颜值评分是"质量维度"，不是"风格维度"
2. 所有人都喜欢颜值高的，这不是个性化偏好
3. 颜值评分已经反映在候选人基础分里，不应重复加分

【正确逻辑】
偏好学习应该基于"风格标签"，而不是"评分维度"：
- preferred_style_tags：偏好的风格标签列表（如["清纯","甜妹","阳光"]）
- preferred_style_weights：每个风格标签的权重
- disliked_style_tags：明确不喜欢的风格标签列表

【改进】
1. 删除错误的评分偏好字段
2. 新增正确的风格偏好字段
3. 保留原有的统计字段和向量状态字段

参考：用户反馈指出"颜值平均分没有意义，因为所有人都喜欢颜值高的"
"""

from __future__ import annotations

from typing import Any

from her_migration_framework import MigrationContext, MigrationSpec, MigrationValidator


PERSONA_DB = "her"
USER_APPEARANCE_PREFERENCES_TABLE = "user_appearance_preferences"


def _table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
        (PERSONA_DB, table_name),
    )
    return int(cursor.fetchone()[0]) > 0


def _column_exists(cursor: Any, table_name: str, column_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (PERSONA_DB, table_name, column_name),
    )
    return int(cursor.fetchone()[0]) > 0


def persona_scope(context: MigrationContext) -> dict[str, Any]:
    return {"dsn": context.get_target_dsn(PERSONA_DB)}


def _apply(conn: Any, _context: MigrationContext) -> dict[str, list[str]]:
    changes: dict[str, list[str]] = {
        "deleted_columns": [],
        "added_columns": [],
    }

    with conn.cursor() as cursor:
        # 确保表存在
        if not _table_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE):
            return changes

        # 1. 删除错误的评分偏好字段
        wrong_columns = [
            "preferred_mature_score",
            "preferred_clean_score",
            "preferred_gentle_score",
            "preferred_sunny_score",
            "preferred_stylish_score",
        ]

        for column_name in wrong_columns:
            if _column_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE, column_name):
                cursor.execute(
                    f"ALTER TABLE `{USER_APPEARANCE_PREFERENCES_TABLE}` DROP COLUMN `{column_name}`"
                )
                changes["deleted_columns"].append(column_name)

        # 2. 新增正确的风格偏好字段
        new_columns = [
            ("preferred_style_tags", "JSON", "COMMENT '偏好的风格标签列表（如[\"清纯\",\"甜妹\",\"阳光\"]）'"),
            ("preferred_style_weights", "JSON", "COMMENT '每个风格标签的权重（如{\"清纯\":3,\"甜妹\":4,\"成熟\":-1}'"),
            ("disliked_style_tags", "JSON", "COMMENT '明确不喜欢的风格标签列表'"),
            ("preferred_style_type", "VARCHAR(32)", "COMMENT '偏好的风格类型'"),
            ("style_preference_summary", "TEXT", "COMMENT '风格偏好总结文本'"),
            ("last_preference_rebuild_at", "DATETIME", "COMMENT '最后偏好重建时间'"),
        ]

        for column_name, column_type, comment in new_columns:
            if not _column_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE, column_name):
                cursor.execute(
                    f"ALTER TABLE `{USER_APPEARANCE_PREFERENCES_TABLE}` ADD COLUMN `{column_name}` {column_type} {comment}"
                )
                changes["added_columns"].append(column_name)

    return changes


def _validate(conn: Any, _context: MigrationContext) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "wrong_columns_remain": [],
        "new_columns_missing": [],
    }

    with conn.cursor() as cursor:
        # 1. 验证错误的评分偏好字段已删除
        wrong_columns = [
            "preferred_mature_score",
            "preferred_clean_score",
            "preferred_gentle_score",
            "preferred_sunny_score",
            "preferred_stylish_score",
        ]

        for column_name in wrong_columns:
            if _column_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE, column_name):
                issues["wrong_columns_remain"].append(column_name)

        # 2. 验证新的风格偏好字段已添加
        new_columns = [
            "preferred_style_tags",
            "preferred_style_weights",
            "disliked_style_tags",
            "preferred_style_type",
            "style_preference_summary",
            "last_preference_rebuild_at",
        ]

        for column_name in new_columns:
            if not _column_exists(cursor, USER_APPEARANCE_PREFERENCES_TABLE, column_name):
                issues["new_columns_missing"].append(column_name)

    return issues


MIGRATION = MigrationSpec(
    migration_id="0018_fix_appearance_preference_fields",
    description="修复外貌偏好字段：删除错误的评分偏好字段，新增正确的风格偏好字段",
    scope_fn=persona_scope,
    apply_fn=_apply,
    validate_fn=_validate,
)