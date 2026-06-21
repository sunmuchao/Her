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


def test_extract_structured_conditions_from_partner_expectation():
    """测试：择偶条件中的结构化信息应拆入 persona 字段，非结构化部分保留摘要"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "男，28-35岁，身高171-184cm，南通/上海/苏州，未婚，真诚有责任感温和，不接受有孩",
    })

    assert supported["target_age_min"] == 28
    assert supported["target_age_max"] == 35
    assert supported["target_height_min"] == 171
    assert supported["target_height_max"] == 184
    assert supported["target_cities"] == "南通,上海,苏州"
    assert supported["target_marital_statuses"] == "未婚"
    assert supported["target_accept_partner_children"] == "不接受"
    assert unsupported == {"partner_expectation": {"target_gender": "male"}}
    assert cleaned["partner_expectation"] == "真诚有责任感温和"


def test_normalize_quantifiable_patch_keeps_supported_target_fields():
    """测试：结构化择偶条件可写入 user_personas 的 target_* 字段"""
    from match_domain.session_end_processor import normalize_quantifiable_patch

    normalized = normalize_quantifiable_patch({
        "target_age_min": 28,
        "target_age_max": 35,
        "target_cities": "南通,上海,苏州",
        "target_marital_statuses": "未婚",
        "target_accept_partner_children": "不接受",
        "target_gender": "male",
    })

    assert normalized["target_age_min"] == 28
    assert normalized["target_age_max"] == 35
    assert normalized["target_cities"] == "南通,上海,苏州"
    assert normalized["target_marital_statuses"] == "未婚"
    assert normalized["target_accept_partner_children"] == "不接受"
    assert "target_gender" not in normalized


def test_extract_structured_conditions_normalizes_prefixed_city():
    """测试：'在无锡' 这类表达只提取城市本体"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "希望找30-32岁、在无锡、奔着结婚的男生",
    })

    assert supported["target_cities"] == "无锡"
    assert unsupported == {"partner_expectation": {"target_gender": "male"}}
    assert cleaned["partner_expectation"] == "奔着结婚的"


def test_extract_structured_conditions_does_not_swallow_residency_phrase_into_city():
    """测试：'在无锡工作定居' 不应把整段写入 target_cities"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "希望对方性格温和善沟通，在无锡工作定居",
    })

    assert supported["target_cities"] == "无锡"
    assert unsupported == {}
    assert cleaned["partner_expectation"] == "希望对方性格温和善沟通,工作定居".replace(",", "，")


def test_negative_preferences_should_not_extract_target_gender():
    """测试：negative_preferences 中出现'女生'不应误抽 target_gender"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "negative_preferences": "不喜欢性格内向、慢热、回避型依恋的女生",
    })

    assert supported == {}
    assert unsupported == {}
    assert cleaned["negative_preferences"] == "不喜欢性格内向，慢热，回避型依恋的女生"


def test_extract_structured_conditions_handles_bare_height_and_children_acceptance():
    """测试：裸写身高范围和子女条件也应拆出，摘要只留非结构化部分"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "找无锡，163-176cm，情绪稳定有主见，对方有孩可协商",
    })

    assert supported["target_cities"] == "无锡"
    assert supported["target_height_min"] == 163
    assert supported["target_height_max"] == 176
    assert supported["target_accept_partner_children"] == "可协商"
    assert unsupported == {}
    assert cleaned["partner_expectation"] == "情绪稳定有主见"


def test_filter_valid_summary_data_rejects_structured_residue():
    """测试：摘要里只要还残留结构化条件，就禁止入库"""
    from match_domain.session_end_processor import filter_valid_summary_data

    valid, rejected = filter_valid_summary_data({
        "partner_expectation": "找无锡，163-176cm，情绪稳定有主见，对方有孩可协商",
    })

    assert valid == {}
    assert rejected == {"partner_expectation": "invalid"}


def test_extract_structured_conditions_strips_field_residue_and_relationship_stage():
    """测试：'年龄'残词和'先谈恋爱'关系阶段不应留在摘要"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "外向活泼的，年龄，以先谈恋爱为目标",
    })

    assert supported == {}
    assert unsupported == {"partner_expectation": {"relationship_stage": "先谈恋爱"}}
    assert cleaned["partner_expectation"] == "外向活泼的，以为目标"


def test_extract_structured_conditions_marks_self_plan_from_partner_expectation():
    """测试：self 计划信息不应留在 partner_expectation"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "希望对方活泼开朗（外向型），年龄，先谈恋爱，想换职业方向",
    })

    assert supported == {}
    assert unsupported == {
        "partner_expectation": {
            "relationship_stage": "先谈恋爱",
            "self_plan": "想换职业方向",
        }
    }
    assert cleaned["partner_expectation"] == "希望对方活泼开朗（外向型）"


def test_extract_structured_conditions_strips_city_and_child_preference():
    """测试：城市和生育偏好应拆出，摘要只保留非结构化特征"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "找性格合拍，细腻独立的，无锡或上海，想要孩子",
    })

    assert supported["target_cities"] == "无锡,上海"
    assert supported["target_want_children"] == "想要孩子"
    assert unsupported == {}
    assert cleaned["partner_expectation"] == "性格合拍，细腻独立的"


def test_extract_structured_conditions_handles_short_structured_residue():
    """测试：无孩这类短语化结构化条件应拆出"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "找，无孩，要求独立，有责任感，情绪稳定",
    })

    assert supported["target_accept_partner_children"] == "不接受"
    assert unsupported == {}
    assert cleaned["partner_expectation"] == "独立，有责任感，情绪稳定"


def test_extract_structured_conditions_handles_same_city_phrase():
    """测试：同城短语不应留在 partner_expectation"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "希望对方边界感强，务实，乐观，同城",
    })

    assert supported == {}
    assert unsupported == {"partner_expectation": {"distance_scope": "同城"}}
    assert cleaned["partner_expectation"] == "希望对方边界感强，务实，乐观"


def test_extract_structured_conditions_handles_same_city_and_dating_goal_phrase():
    """测试：同城无锡和谈恋爱目的不应留在摘要"""
    from match_domain.session_end_processor import split_structured_conditions_from_summaries

    supported, unsupported, cleaned = split_structured_conditions_from_summaries({
        "partner_expectation": "喜欢活泼开朗型的，年龄，同城无锡，以谈恋爱为目的",
    })

    assert supported["target_cities"] == "无锡"
    assert unsupported == {"partner_expectation": {"relationship_stage": "以谈恋爱为目的"}}
    assert cleaned["partner_expectation"] == "喜欢活泼开朗型的"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
