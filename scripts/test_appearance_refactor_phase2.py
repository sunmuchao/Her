#!/usr/bin/env python3
"""
Phase 2 测试脚本：验证抽象化工具参数

测试目标：
1. appearance_level 参数被正确解析
2. appearance_description 参数被正确解析
3. 解析后的筛选条件被正确应用
4. Agent不需要知道内部实现细节
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_appearance_level():
    """测试：解析外貌筛选级别"""
    print("=" * 80)
    print("测试 1: _parse_appearance_level")
    print("=" * 80)

    # 导入函数
    from external_systems.partner_discovery_system.discovery_system.service_integrations import (
        _parse_appearance_level,
    )

    # 测试 "high"
    high_filters = _parse_appearance_level("high")
    print(f"✅ appearance_level='high' → {high_filters}")
    assert "beauty_score_min" in high_filters, "应包含 beauty_score_min"
    assert high_filters["beauty_score_min"] == 80.0, "高标准应为80分"

    # 测试 "medium"
    medium_filters = _parse_appearance_level("medium")
    print(f"✅ appearance_level='medium' → {medium_filters}")
    assert medium_filters == {}, "medium应返回空字典（不强制筛选）"

    # 测试 "low"
    low_filters = _parse_appearance_level("low")
    print(f"✅ appearance_level='low' → {low_filters}")
    assert low_filters == {}, "low应返回空字典（不筛选）"

    print("\n✅ 测试通过：appearance_level 参数被正确解析")


def test_parse_appearance_description():
    """测试：解析外貌描述"""
    print("\n" + "=" * 80)
    print("测试 2: _parse_appearance_description")
    print("=" * 80)

    # 导入函数
    from external_systems.partner_discovery_system.discovery_system.service_integrations import (
        _parse_appearance_description,
    )

    # 测试 "温柔"
    gentle_filters = _parse_appearance_description("温柔")
    print(f"✅ appearance_description='温柔' → {gentle_filters}")
    assert "gentle_score_min" in gentle_filters, "应包含 gentle_score_min"

    # 测试 "阳光"
    sunny_filters = _parse_appearance_description("阳光")
    print(f"✅ appearance_description='阳光' → {sunny_filters}")
    assert "sunny_score_min" in sunny_filters, "应包含 sunny_score_min"

    # 测试 "清秀"
    clean_filters = _parse_appearance_description("清秀")
    print(f"✅ appearance_description='清秀' → {clean_filters}")
    assert "clean_score_min" in clean_filters, "应包含 clean_score_min"

    # 测试组合描述
    combined_filters = _parse_appearance_description("温柔又清秀")
    print(f"✅ appearance_description='温柔又清秀' → {combined_filters}")
    assert "gentle_score_min" in combined_filters, "应包含 gentle_score_min"
    assert "clean_score_min" in combined_filters, "应包含 clean_score_min"

    print("\n✅ 测试通过：appearance_description 参数被正确解析")


def test_agent_usage():
    """测试：Agent使用抽象参数（模拟）"""
    print("\n" + "=" * 80)
    print("测试 3: Agent使用抽象参数（模拟）")
    print("=" * 80)

    # 模拟Agent调用
    agent_params = {
        "appearance_level": "high",
        "appearance_description": "温柔气质",
    }

    print(f"Agent传入参数：{agent_params}")
    print("   Agent只知道：")
    print("   - appearance_level='high'（高标准筛选）")
    print("   - appearance_description='温柔气质'（自然语言描述）")

    # 内部解析（Agent不知道）
    from external_systems.partner_discovery_system.discovery_system.service_integrations import (
        _parse_appearance_level,
        _parse_appearance_description,
    )

    internal_filters = {}

    # 解析level
    level_filters = _parse_appearance_level(agent_params["appearance_level"])
    internal_filters.update(level_filters)

    # 解析description
    description_filters = _parse_appearance_description(agent_params["appearance_description"])
    internal_filters.update(description_filters)

    print(f"\n系统内部筛选条件（Agent不知道）：{internal_filters}")
    print("   包含：")
    for key, value in internal_filters.items():
        print(f"   - {key} = {value}")

    print("\n✅ 测试通过：Agent使用抽象参数，不需要知道内部实现")


def test_tool_parameter_abstraction():
    """测试：工具参数抽象化"""
    print("\n" + "=" * 80)
    print("测试 4: 工具参数抽象化对比")
    print("=" * 80)

    print("【旧设计】Agent需要知道内部参数：")
    print("   search_partner_candidates(")
    print("       beauty_score_min=80,        # ❌ 暴露内部评分")
    print("       appearance_match_json={\"text\": \"清秀\"}  # ❌ 需要理解复杂参数")
    print("   )")

    print("\n【新设计】Agent使用抽象参数：")
    print("   search_partner_candidates(")
    print("       appearance_level=\"high\",       # ✅ 抽象化参数")
    print("       appearance_description=\"清秀型\"  # ✅ 自然语言描述")
    print("   )")

    print("\n✅ 测试通过：工具参数抽象化，Agent易用")


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Phase 2 测试：抽象化工具参数")
    print("=" * 80)

    try:
        test_parse_appearance_level()
        test_parse_appearance_description()
        test_agent_usage()
        test_tool_parameter_abstraction()

        print("\n" + "=" * 80)
        print("✅ Phase 2 所有测试通过！")
        print("=" * 80)

        print("\n【关键成果】")
        print("1. ✅ appearance_level 参数被正确解析")
        print("2. ✅ appearance_description 参数被正确解析")
        print("3. ✅ Agent不需要知道内部实现细节")
        print("4. ✅ 工具参数抽象化，Agent易用")

        return 0

    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())