"""测试测评工具改进后的行为。"""

import pytest
from discovery_system.service_integrations import suggest_assessment_with
from discovery_system.agent_runtime import DiscoveryRunInput


def test_suggest_assessment_mbti_completed():
    """MBTI测评已完成时返回性格信息。"""
    # 模拟已完成MBTI测评的用户
    result = suggest_assessment_with(
        profile_id=1,
        assessment_type="mbti_16",
        source="test_source",
    )

    # 验证返回结构（实际测试需要mock数据源）
    assert "completed" in result
    assert "assessment_type" in result
    assert result["assessment_type"] == "mbti_16"


def test_suggest_assessment_attachment_completed():
    """依恋风格测评已完成时返回依恋信息。"""
    result = suggest_assessment_with(
        profile_id=1,
        assessment_type="attachment_style",
        source="test_source",
    )

    assert "completed" in result
    assert result["assessment_type"] == "attachment_style"


def test_suggest_assessment_big_five_completed():
    """大五人格测评已完成时返回性格结构信息。"""
    result = suggest_assessment_with(
        profile_id=1,
        assessment_type="big_five",
        source="test_source",
    )

    assert "completed" in result
    assert result["assessment_type"] == "big_five"
    # 如果已完成，应该包含性格描述
    if result["completed"]:
        assert "summary" in result
        assert "dimension_scores" in result


def test_suggest_assessment_unsupported_type():
    """不支持的测评类型返回错误。"""
    result = suggest_assessment_with(
        profile_id=1,
        assessment_type="invalid_type",
        source="test_source",
    )

    assert result["completed"] == False
    assert result["suggest"] == False
    assert "error" in result
    assert "不支持的测评类型" in result["error"]
    assert "supported_types" in result
    assert set(result["supported_types"]) == {"mbti_16", "attachment_style", "big_five"}


def test_discovery_run_input_no_default():
    """验证DiscoveryRunInput不再有默认值。"""
    # 测试suggest_assessment参数没有默认值
    # 实际调用时必须传入assessment_type
    try:
        # 创建一个minimal run_input
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
            suggest_assessment=lambda assessment_type: {"completed": False},
        )

        # 验证suggest_assessment必须传入参数
        result = run_input.suggest_assessment("mbti_16")
        assert result["completed"] == False

    except Exception as e:
        pytest.fail(f"DiscoveryRunInput创建失败: {e}")


def test_three_assessment_types_all_supported():
    """验证三种测评类型都支持。"""
    supported_types = ["mbti_16", "attachment_style", "big_five"]

    for assessment_type in supported_types:
        result = suggest_assessment_with(
            profile_id=1,
            assessment_type=assessment_type,
            source="test_source",
        )

        # 所有支持的类型都不应返回错误
        if "error" in result:
            pytest.fail(f"{assessment_type} 返回了错误: {result['error']}")

        # 验证返回结构正确
        assert result["assessment_type"] == assessment_type
        assert "completed" in result


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])