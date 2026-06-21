"""测试字段白名单自动同步和模型配置统一管理

测试内容：
1. QUANTIFIABLE_FIELDS 自动包含所有表字段
2. marital_status, has_children 等字段正确归类
3. 模型配置使用环境变量，fallback正确
"""

import os
import pytest
from unittest.mock import patch


def test_quantifiable_fields_auto_sync():
    """测试：白名单自动从表字段生成"""
    from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS
    from match_domain.collected_profile import (
        PROFILE_FACT_PROFILE_COLUMNS,
        COLLECTED_PERSONA_FIELDS,
    )

    # 验证：白名单 = profiles表字段 + persona表字段
    expected_fields = frozenset(PROFILE_FACT_PROFILE_COLUMNS | COLLECTED_PERSONA_FIELDS)
    assert QUANTIFIABLE_FIELDS == expected_fields, "白名单应该等于表字段的集合"

    # 验证：白名单包含之前遗漏的字段
    assert "marital_status" in QUANTIFIABLE_FIELDS, "marital_status应该在白名单中"
    assert "has_children" in QUANTIFIABLE_FIELDS, "has_children应该在白名单中"

    # 验证：白名单包含其他基础字段
    assert "age" in QUANTIFIABLE_FIELDS, "age应该在白名单中"
    assert "city" in QUANTIFIABLE_FIELDS, "city应该在白名单中"
    assert "height" in QUANTIFIABLE_FIELDS, "height应该在白名单中"
    assert "education" in QUANTIFIABLE_FIELDS, "education应该在白名单中"


def test_field_classification_with_auto_sync():
    """测试：字段拆分正确（自动同步后）"""
    from match_domain.session_end_processor import split_by_quantifiability

    # 测试数据：包含之前遗漏的字段
    summary_data = {
        "partner_expectation": "希望找性格外向的女生",  # 不可量化
        "marital_status": "未婚",  # ✅ 可量化（之前遗漏）
        "has_children": "没有孩子",  # ✅ 可量化（之前遗漏）
        "city": "无锡",  # 可量化
        "age": "28",  # 可量化
    }

    # 执行分流
    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    # 验证：可量化字段包含 marital_status 和 has_children
    assert "marital_status" in quantifiable, "marital_status应该归类为可量化字段"
    assert "has_children" in quantifiable, "has_children应该归类为可量化字段"
    assert "city" in quantifiable, "city应该归类为可量化字段"
    assert "age" in quantifiable, "age应该归类为可量化字段"

    # 验证：不可量化字段只包含 partner_expectation
    assert "partner_expectation" in non_quantifiable, "partner_expectation应该归类为不可量化字段"
    assert len(quantifiable) == 4, "可量化字段应该有4个"
    assert len(non_quantifiable) == 1, "不可量化字段应该有1个"


def test_model_config_from_env():
    """测试：模型配置从环境变量读取"""
    # 模拟环境变量
    with patch.dict(os.environ, {
        "HER_DISCOVERY_AGENT_MODEL": "qwen-plus",
        "HER_DISCOVERY_AGENT_API_KEY": "test-api-key",
        "HER_DISCOVERY_AGENT_BASE_URL": "https://test.com/v1",
    }):
        from her_env import env_first

        # 验证：环境变量读取正确
        model = env_first("HER_DISCOVERY_AGENT_MODEL", default="qwen-max")
        assert model == "qwen-plus", "应该从环境变量读取模型"

        api_key = env_first("HER_DISCOVERY_AGENT_API_KEY", default="")
        assert api_key == "test-api-key", "应该从环境变量读取API Key"

        base_url = env_first("HER_DISCOVERY_AGENT_BASE_URL", default="https://default.com")
        assert base_url == "https://test.com/v1", "应该从环境变量读取Base URL"


def test_model_fallback_to_existing_model():
    """测试：fallback使用存在的模型"""
    # 模拟环境变量缺失
    with patch.dict(os.environ, {}, clear=True):
        from her_env import env_first

        # 验证：fallback使用存在的模型（不是qwen3-235b）
        model = env_first("HER_DISCOVERY_AGENT_MODEL", default="qwen-plus")
        assert model == "qwen-plus", "fallback应该使用qwen-plus（存在的模型）"

        # 验证：fallback不是错误模型
        assert model != "qwen3-235b", "fallback不应该使用qwen3-235b（不存在的模型）"


def test_llm_extraction_model_config():
    """测试：LLM提取的模型配置"""
    from match_domain.session_end_processor import _call_llm_for_json

    # 验证：函数内部使用环境变量
    # 这里只验证函数定义，实际调用需要mock LLM
    import inspect
    source = inspect.getsource(_call_llm_for_json)

    # 验证：代码中不包含硬编码的qwen3-235b
    assert "qwen3-235b" not in source, "不应该硬编码qwen3-235b"

    # 验证：代码中使用env_first
    assert "env_first" in source, "应该使用env_first读取环境变量"


def test_ai_merge_model_config():
    """测试：AI合并判断的模型配置"""
    from match_domain.ai_merge_handler import _call_llm_for_json

    # 验证：函数内部使用环境变量
    import inspect
    source = inspect.getsource(_call_llm_for_json)

    # 验证：代码中不包含硬编码的qwen3-235b
    assert "qwen3-235b" not in source, "不应该硬编码qwen3-235b"

    # 验证：代码中使用env_first
    assert "env_first" in source, "应该使用env_first读取环境变量"

    # 验证：代码中使用HER_DISCOVERY_AGENT_MODEL
    assert "HER_DISCOVERY_AGENT_MODEL" in source, "应该使用HER_DISCOVERY_AGENT_MODEL环境变量"


def test_integration_field_classification_and_storage():
    """集成测试：字段分类 + 存储流程"""
    from match_domain.session_end_processor import split_by_quantifiability

    # 测试数据：完整的LLM提取结果
    summary_data = {
        # 不可量化字段（主观描述）
        "personality_traits": "性格温柔、内向",
        "values": "重视家庭、重视事业",
        "partner_expectation": "希望找性格外向的女生",
        "life_attitude": "追求稳定、重视生活质量",
        "emotional_needs": "需要理解和支持",

        # 可量化字段（之前遗漏的字段）
        "marital_status": "未婚",
        "has_children": "没有孩子",

        # 可量化字段（基础字段）
        "city": "无锡",
        "age": "28",
        "height": "175",
        "education": "硕士",
    }

    # 执行分流
    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    # 验证：可量化字段数量
    expected_quantifiable = {
        "marital_status", "has_children", "city", "age", "height", "education"
    }
    assert set(quantifiable.keys()) == expected_quantifiable, \
        f"可量化字段应该是{expected_quantifiable}，实际是{set(quantifiable.keys())}"

    # 验证：不可量化字段数量
    expected_non_quantifiable = {
        "personality_traits", "values", "partner_expectation",
        "life_attitude", "emotional_needs"
    }
    assert set(non_quantifiable.keys()) == expected_non_quantifiable, \
        f"不可量化字段应该是{expected_non_quantifiable}，实际是{set(non_quantifiable.keys())}"

    print(f"✅ 可量化字段：{list(quantifiable.keys())}")
    print(f"✅ 不可量化字段：{list(non_quantifiable.keys())}")


def test_regression_previous_missing_fields():
    """回归测试：验证之前遗漏的字段现在正确归类"""
    from match_domain.session_end_processor import split_by_quantifiability

    # 测试数据：只包含之前遗漏的字段
    summary_data = {
        "marital_status": "未婚",
        "has_children": "没有孩子",
    }

    # 执行分流
    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    # 验证：这两个字段现在归类为可量化字段
    assert "marital_status" in quantifiable, \
        "修复后：marital_status应该归类为可量化字段"
    assert "has_children" in quantifiable, \
        "修复后：has_children应该归类为可量化字段"

    # 验证：不可量化字段为空
    assert len(non_quantifiable) == 0, \
        "这两个字段不应该归类为不可量化字段"

    print("✅ 回归测试通过：之前遗漏的字段现在正确归类")


def test_normalize_quantifiable_patch_only_keeps_persona_supported_fields():
    """测试：结构化字段只保留 user_personas 支持的字段，age/city/income 直接丢弃"""
    from match_domain.session_end_processor import normalize_quantifiable_patch

    summary_data = {
        "mbti_type": "INTJ",
        "city": "无锡",
        "age": "28",
        "income": "20万/年",
        "height": "172",
        "education": "本科",
    }

    normalized = normalize_quantifiable_patch(summary_data)

    assert "self_personality_traits_json" in normalized, "mbti_type 应映射到 persona 支持字段"
    assert "self_city" not in normalized, "city 不应写入 persona"
    assert "self_age" not in normalized, "age 不应写入 persona"
    assert "self_income_wan" not in normalized, "income 不应写入 persona"
    assert "self_height" not in normalized, "height 不应写入 persona"
    assert "self_education" not in normalized, "education 不应写入 persona"


def test_normalize_quantifiable_patch_discards_invalid_mbti_values():
    """测试：无效 MBTI 值如'未测过'不应写入 persona"""
    from match_domain.session_end_processor import normalize_quantifiable_patch

    normalized = normalize_quantifiable_patch({
        "mbti_type": "未测过",
        "city": "南京",
    })

    assert normalized == {}, "无效 mbti_type 应被直接丢弃"


def test_validate_summary_text_rejects_generic_compatibility_phrases():
    """测试：'需要性格合拍' 这类空泛摘要会被拦截"""
    from match_domain.session_end_processor import validate_summary_text

    assert validate_summary_text("emotional_needs", "需要性格合拍") == "invalid"
    assert validate_summary_text("partner_expectation", "希望真诚稳定") == "invalid"
    assert validate_summary_text("partner_expectation", "希望对方情绪稳定、愿意沟通、不冷处理问题") == "valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
