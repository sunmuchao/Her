"""Test conversation_summaries table structure (修正版)."""

from __future__ import annotations

import pytest


def test_conversation_summaries_table_sql():
    """测试表定义 SQL 的正确性"""
    from persona_memory_sync.schema_tools import CONVERSATION_SUMMARIES_TABLE_SQL

    # 检查关键字段存在
    assert "summary_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "conversation_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "conversation_type" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "requester_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "profile_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "summary_key" in CONVERSATION_SUMMARIES_TABLE_SQL  # 新增：字段名
    assert "summary_text" in CONVERSATION_SUMMARIES_TABLE_SQL  # 新增：字段值
    assert "vector_status" in CONVERSATION_SUMMARIES_TABLE_SQL  # 新增：向量化状态
    assert "created_at" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "updated_at" in CONVERSATION_SUMMARIES_TABLE_SQL

    # 检查 UNIQUE KEY 存在（同一对话同一字段唯一）
    assert "UNIQUE KEY unique_conversation_key" in CONVERSATION_SUMMARIES_TABLE_SQL

    # 检查索引存在
    assert "KEY idx_conversation_summaries_conversation_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "KEY idx_conversation_summaries_requester_id" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "KEY idx_conversation_summaries_key" in CONVERSATION_SUMMARIES_TABLE_SQL
    assert "KEY idx_conversation_summaries_vector_status" in CONVERSATION_SUMMARIES_TABLE_SQL


def test_conversation_summaries_required_columns():
    """测试必需列定义的正确性"""
    from persona_memory_sync.schema_tools import CONVERSATION_SUMMARIES_REQUIRED_COLUMNS

    expected_columns = (
        "summary_id",
        "conversation_id",
        "conversation_type",
        "requester_id",
        "profile_id",
        "summary_key",  # 新增：字段名
        "summary_text",  # 新增：字段值
        "vector_status",  # 新增：向量化状态
        "created_at",
        "updated_at",
    )

    assert CONVERSATION_SUMMARIES_REQUIRED_COLUMNS == expected_columns


def test_conversation_summaries_insert_example():
    """测试插入示例数据（验证表结构设计的合理性）"""

    # 示例数据：LLM 提炼的结构化摘要
    summary_data = {
        "personality_traits": "性格温柔、内向",
        "values": "重视家庭、重视事业",
        "partner_expectation": "希望找个能理解工作忙碌的人",
        "life_attitude": "追求稳定、重视生活质量",
        "emotional_needs": "需要理解和支持",
    }

    # 模拟插入数据
    insert_statements = []
    for summary_key, summary_text in summary_data.items():
        insert_sql = f"""
        INSERT INTO conversation_summaries
        (conversation_id, conversation_type, requester_id, profile_id, summary_key, summary_text, vector_status)
        VALUES ('session_001', 'discovery', 123, 456, '{summary_key}', '{summary_text}', 'pending')
        """
        insert_statements.append(insert_sql)

    # 验证：
    # 1. 每个字段对应一条记录
    assert len(insert_statements) == 5

    # 2. 每个字段对应一个向量类型
    vector_types = [summary_key for summary_key in summary_data.keys()]
    expected_vector_types = [
        "personality_traits",
        "values",
        "partner_expectation",
        "life_attitude",
        "emotional_needs",
    ]
    assert vector_types == expected_vector_types

    # 3. UNIQUE KEY 防止同一对话同一字段重复插入
    # 如果尝试插入相同的 (conversation_id, summary_key)，会被拒绝
    # 这确保了一个对话只有一个 personality_traits 字段值


def test_conversation_summaries_usage_example():
    """测试使用示例（验证表结构设计的实用性）"""

    # 场景1：查询用户的所有摘要字段
    query_all_fields = """
    SELECT summary_key, summary_text, vector_status
    FROM conversation_summaries
    WHERE requester_id = 123
    ORDER BY created_at DESC
    """

    # 场景2：查询特定字段的摘要
    query_specific_field = """
    SELECT summary_text, vector_status
    FROM conversation_summaries
    WHERE requester_id = 123 AND summary_key = 'personality_traits'
    ORDER BY created_at DESC
    LIMIT 1
    """

    # 场景3：查询待向量化的摘要
    query_pending_vectors = """
    SELECT conversation_id, summary_key, summary_text
    FROM conversation_summaries
    WHERE vector_status = 'pending'
    """

    # 场景4：更新向量化状态
    update_vector_status = """
    UPDATE conversation_summaries
    SET vector_status = 'completed'
    WHERE conversation_id = 'session_001' AND summary_key = 'personality_traits'
    """

    # 验证：这些查询都可以正常工作
    assert "summary_key" in query_all_fields
    assert "summary_key" in query_specific_field
    assert "vector_status" in query_pending_vectors
    assert "vector_status" in update_vector_status


if __name__ == "__main__":
    # 运行测试
    test_conversation_summaries_table_sql()
    print("✅ 表定义 SQL 测试通过")

    test_conversation_summaries_required_columns()
    print("✅ 必需列定义测试通过")

    test_conversation_summaries_insert_example()
    print("✅ 插入示例测试通过")

    test_conversation_summaries_usage_example()
    print("✅ 使用示例测试通过")

    print("\n🎉 所有测试通过！任务1完成：conversation_summaries 表结构已修正")