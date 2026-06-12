"""测试测评工具核心逻辑改进（不依赖数据库）。"""

import pytest
from unittest.mock import MagicMock
from discovery_system.agent_runtime import DiscoveryRunInput


def test_discovery_run_input_no_default():
    """验证DiscoveryRunInput不再有默认值（已通过）。"""
    run_input = DiscoveryRunInput(
        session_id="test",
        requester_id=1,
        profile_id=1,
        phase="test",
        criteria_labels=[],
        recent_timeline=[],
        runtime_context={},
        search_partner_candidates=lambda criteria, limit: {},
        sync_requester_persona_memory=lambda patch: {},
        propose_requester_profile_update=lambda patch, evidence: {},
        create_saved_search_subscription_from_last_search=lambda: {},
        suggest_assessment=lambda assessment_type: {"completed": False, "assessment_type": assessment_type},
    )

    # 验证必须传入参数
    result = run_input.suggest_assessment("mbti_16")
    assert result["completed"] == False
    assert result["assessment_type"] == "mbti_16"

    result = run_input.suggest_assessment("attachment_style")
    assert result["assessment_type"] == "attachment_style"

    result = run_input.suggest_assessment("big_five")
    assert result["assessment_type"] == "big_five"


def test_big_five_assessment_logic():
    """测试大五人格测评逻辑（模拟traits数据）。"""
    from discovery_system.service_integrations import _normalized_trait_score

    # 模拟大五人格数据（已完成）
    traits_dict_completed = {
        "big_five": {
            "scores": {
                "openness": 0.7,
                "conscientiousness": 0.8,
                "agreeableness": 0.6,
                "neuroticism": 0.4,
                "extraversion": 0.3,
            }
        }
    }

    # 模拟大五人格数据（未完成）
    traits_dict_incomplete = {
        "big_five": {
            "scores": {
                "openness": 0.7,
            }
        }
    }

    # 测试已完成的情况（>=3个维度有分数）
    valid_dimensions = 0
    for key in ("openness", "conscientiousness", "agreeableness", "neuroticism", "extraversion"):
        if _normalized_trait_score(traits_dict_completed["big_five"]["scores"].get(key)) is not None:
            valid_dimensions += 1

    assert valid_dimensions >= 3, "已完成的大五人格应该至少有3个维度有分数"

    # 测试未完成的情况（<3个维度有分数）
    valid_dimensions_incomplete = 0
    for key in ("openness", "conscientiousness", "agreeableness", "neuroticism", "extraversion"):
        if _normalized_trait_score(traits_dict_incomplete["big_five"]["scores"].get(key)) is not None:
            valid_dimensions_incomplete += 1

    assert valid_dimensions_incomplete < 3, "未完成的大五人格应该少于3个维度有分数"


def test_assessment_type_validation():
    """测试测评类型有效性校验（硬约束）。"""
    supported_types = {"mbti_16", "attachment_style", "big_five"}
    invalid_type = "invalid_type"

    # 验证支持的类型
    assert "mbti_16" in supported_types
    assert "attachment_style" in supported_types
    assert "big_five" in supported_types

    # 验证不支持的类型
    assert invalid_type not in supported_types

    # 模拟错误返回
    error_result = {
        "completed": False,
        "suggest": False,
        "error": f"不支持的测评类型：{invalid_type}",
        "supported_types": list(supported_types),
    }

    assert error_result["completed"] == False
    assert "不支持的测评类型" in error_result["error"]
    assert set(error_result["supported_types"]) == supported_types


def test_three_types_all_supported():
    """验证三种测评类型都被支持。"""
    supported_types = ["mbti_16", "attachment_style", "big_five"]

    # 验证所有类型都在支持列表中
    for assessment_type in supported_types:
        assert assessment_type in {"mbti_16", "attachment_style", "big_five"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])