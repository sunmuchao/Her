"""测试分流写入逻辑（V2修正版）

测试目标：
1. 测试分流函数：split_by_quantifiability
2. 测试可量化字段的判断
3. 测试不可量化字段的判断
"""

from match_domain.session_end_processor import split_by_quantifiability


def test_split_by_quantifiability():
    """测试分流函数"""

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("测试分流函数：split_by_quantifiability")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 测试场景1：只有可量化字段
    print("\n【测试场景1】只有可量化字段")
    summary_data = {
        "mbti_type": "INTJ",
        "smoking": "不抽烟",
        "city": "北京",
    }

    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    print(f"输入: {summary_data}")
    print(f"可量化字段: {quantifiable}")
    print(f"不可量化字段: {non_quantifiable}")

    assert quantifiable == summary_data, "可量化字段应该全部提取"
    assert non_quantifiable == {}, "不可量化字段应该为空"
    print("✅ 测试通过")

    # 测试场景2：只有不可量化字段
    print("\n【测试场景2】只有不可量化字段")
    summary_data = {
        "personality_traits": "性格温柔",
        "values": "重视家庭",
        "partner_expectation": "能理解工作忙碌",
    }

    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    print(f"输入: {summary_data}")
    print(f"可量化字段: {quantifiable}")
    print(f"不可量化字段: {non_quantifiable}")

    assert quantifiable == {}, "可量化字段应该为空"
    assert non_quantifiable == summary_data, "不可量化字段应该全部提取"
    print("✅ 测试通过")

    # 测试场景3：混合字段
    print("\n【测试场景3】混合字段（可量化+不可量化）")
    summary_data = {
        "mbti_type": "INTJ",  # 可量化
        "smoking": "不抽烟",  # 可量化
        "personality_traits": "性格温柔",  # 不可量化
        "values": "重视家庭",  # 不可量化
        "city": "北京",  # 可量化
        "partner_expectation": "能理解工作忙碌",  # 不可量化
    }

    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    print(f"输入: {summary_data}")
    print(f"可量化字段: {quantifiable}")
    print(f"不可量化字段: {non_quantifiable}")

    expected_quantifiable = {
        "mbti_type": "INTJ",
        "smoking": "不抽烟",
        "city": "北京",
    }

    expected_non_quantifiable = {
        "personality_traits": "性格温柔",
        "values": "重视家庭",
        "partner_expectation": "能理解工作忙碌",
    }

    assert quantifiable == expected_quantifiable, "可量化字段应该正确分流"
    assert non_quantifiable == expected_non_quantifiable, "不可量化字段应该正确分流"
    print("✅ 测试通过")

    # 测试场景4：包含空值
    print("\n【测试场景4】包含空值")
    summary_data = {
        "mbti_type": "INTJ",
        "smoking": "",  # 空值
        "personality_traits": "性格温柔",
        "values": "",  # 空值
    }

    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    print(f"输入: {summary_data}")
    print(f"可量化字段: {quantifiable}")
    print(f"不可量化字段: {non_quantifiable}")

    expected_quantifiable = {
        "mbti_type": "INTJ",
    }

    expected_non_quantifiable = {
        "personality_traits": "性格温柔",
    }

    assert quantifiable == expected_quantifiable, "空值不应该出现在结果中"
    assert non_quantifiable == expected_non_quantifiable, "空值不应该出现在结果中"
    print("✅ 测试通过")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("所有测试通过！")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    test_split_by_quantifiability()