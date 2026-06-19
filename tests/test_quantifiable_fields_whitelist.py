"""Test QUANTIFIABLE_FIELDS whitelist definition."""

from __future__ import annotations

import pytest


def test_quantifiable_fields_import():
    """测试可以正确导入 QUANTIFIABLE_FIELDS"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    assert QUANTIFIABLE_FIELDS is not None
    assert isinstance(QUANTIFIABLE_FIELDS, frozenset)


def test_quantifiable_fields_contains_numeric_ranges():
    """测试白名单包含数值范围字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 数值范围字段
    numeric_fields = ["age", "age_min", "age_max", "height", "height_min", "height_max", "income", "income_min", "income_max"]

    for field in numeric_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_contains_enum_types():
    """测试白名单包含枚举类型字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 枚举类型字段
    enum_fields = ["mbti_type", "personality_type", "marital_status", "relationship_goal", "gender", "sexual_orientation"]

    for field in enum_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_contains_boolean_values():
    """测试白名单包含布尔值字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 布尔值字段
    boolean_fields = ["has_children", "smoking", "drinking", "accept_partner_children", "accept_long_distance"]

    for field in boolean_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_contains_locations():
    """测试白名单包含地理位置字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 地理位置字段
    location_fields = ["cities", "districts", "city", "district"]

    for field in location_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_contains_education():
    """测试白名单包含学历等级字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 学历等级字段
    education_fields = ["education", "education_min"]

    for field in education_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_contains_tags():
    """测试白名单包含标签字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 标签字段
    tag_fields = ["must_have_tags", "must_not_have_tags"]

    for field in tag_fields:
        assert field in QUANTIFIABLE_FIELDS, f"{field} should be in QUANTIFIABLE_FIELDS"


def test_quantifiable_fields_not_contains_subjective_fields():
    """测试白名单不包含主观描述字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 主观描述字段（应该不在白名单中）
    subjective_fields = [
        "personality_traits",  # 性格特质（如"性格温柔"）
        "values",  # 价值观（如"重视家庭"）
        "partner_expectation",  # 择偶期望（如"希望找个温柔的人"）
        "life_attitude",  # 生活态度（如"追求稳定"）
        "emotional_needs",  # 情感需求（如"需要理解和支持"）
    ]

    for field in subjective_fields:
        assert field not in QUANTIFIABLE_FIELDS, f"{field} should NOT be in QUANTIFIABLE_FIELDS (it's subjective)"


def test_quantifiable_fields_not_contains_system_fields():
    """测试白名单不包含系统字段"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 系统字段（应该不在白名单中）
    system_fields = [
        "session_id",
        "requester_id",
        "profile_id",
        "user_key",
        "created_at",
        "updated_at",
    ]

    for field in system_fields:
        assert field not in QUANTIFIABLE_FIELDS, f"{field} should NOT be in QUANTIFIABLE_FIELDS (it's a system field)"


def test_quantifiable_fields_usage_example():
    """测试白名单使用示例"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 示例：用户说的各种信息
    user_data = {
        "age": 28,  # ✅ 可量化 → 在白名单中
        "mbti_type": "INTJ",  # ✅ 可量化 → 在白名单中
        "smoking": False,  # ✅ 可量化 → 在白名单中
        "city": "北京",  # ✅ 可量化 → 在白名单中
        "education": "硕士",  # ✅ 可量化 → 在白名单中
        "personality_traits": "性格温柔",  # ❌ 主观描述 → 不在白名单中
        "values": "重视家庭",  # ❌ 主观描述 → 不在白名单中
    }

    # 分流逻辑：根据是否在白名单中分流
    quantifiable_data = {}
    subjective_data = {}

    for key, value in user_data.items():
        if key in QUANTIFIABLE_FIELDS:
            quantifiable_data[key] = value  # ✅ 写入结构化数据
        else:
            subjective_data[key] = value  # ❌ 不处理，等会话结束后提炼

    # 验证分流结果
    assert "age" in quantifiable_data
    assert "mbti_type" in quantifiable_data
    assert "smoking" in quantifiable_data
    assert "city" in quantifiable_data
    assert "education" in quantifiable_data

    assert "personality_traits" in subjective_data
    assert "values" in subjective_data


def test_quantifiable_fields_total_count():
    """测试白名单字段总数"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS

    # 验证白名单包含的字段总数
    # 根据文档定义，应该包含以下字段：
    # - 数值范围：9个（age, age_min, age_max, height, height_min, height_max, income, income_min, income_max）
    # - 枚举类型：6个（mbti_type, personality_type, marital_status, relationship_goal, gender, sexual_orientation）
    # - 布尔值：5个（has_children, smoking, drinking, accept_partner_children, accept_long_distance）
    # - 地理位置：4个（cities, districts, city, district）
    # - 学历等级：2个（education, education_min）
    # - 标签：2个（must_have_tags, must_not_have_tags）
    # 总计：28个字段

    expected_fields = {
        # 数值范围（9个）
        "age", "age_min", "age_max",
        "height", "height_min", "height_max",
        "income", "income_min", "income_max",
        # 枚举类型（6个）
        "mbti_type", "personality_type",
        "marital_status", "relationship_goal",
        "gender", "sexual_orientation",
        # 布尔值（5个）
        "has_children", "smoking", "drinking",
        "accept_partner_children", "accept_long_distance",
        # 地理位置（4个）
        "cities", "districts", "city", "district",
        # 学历等级（2个）
        "education", "education_min",
        # 标签（2个）
        "must_have_tags", "must_not_have_tags",
    }

    assert QUANTIFIABLE_FIELDS == expected_fields


if __name__ == "__main__":
    # 运行所有测试
    test_quantifiable_fields_import()
    print("✅ 导入测试通过")

    test_quantifiable_fields_contains_numeric_ranges()
    print("✅ 数值范围字段测试通过")

    test_quantifiable_fields_contains_enum_types()
    print("✅ 枚举类型字段测试通过")

    test_quantifiable_fields_contains_boolean_values()
    print("✅ 布尔值字段测试通过")

    test_quantifiable_fields_contains_locations()
    print("✅ 地理位置字段测试通过")

    test_quantifiable_fields_contains_education()
    print("✅ 学历等级字段测试通过")

    test_quantifiable_fields_contains_tags()
    print("✅ 标签字段测试通过")

    test_quantifiable_fields_not_contains_subjective_fields()
    print("✅ 主观描述字段测试通过（不在白名单中）")

    test_quantifiable_fields_not_contains_system_fields()
    print("✅ 系统字段测试通过（不在白名单中）")

    test_quantifiable_fields_usage_example()
    print("✅ 使用示例测试通过")

    test_quantifiable_fields_total_count()
    print("✅ 字段总数测试通过")

    print("\n🎉 所有测试通过！任务2完成：QUANTIFIABLE_FIELDS 白名单已定义")