#!/usr/bin/env python3
"""
Phase 4 测试脚本：验证Agent System Prompt增强

测试目标：
1. SOUL.md包含外貌偏好理解指导
2. SOUL.md不包含硬编码参数说明
3. SOUL.md包含Agent决策指导
4. SOUL.md包含推荐理由生成指导
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_soul_file_exists():
    """测试：SOUL.md文件存在"""
    print("=" * 80)
    print("测试 1: SOUL.md文件存在")
    print("=" * 80)

    soul_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"

    if os.path.exists(soul_file):
        print(f"✅ SOUL.md文件存在：{soul_file}")
        return True
    else:
        print(f"❌ SOUL.md文件不存在：{soul_file}")
        return False


def test_no_hardcoded_parameters():
    """测试：不包含硬编码参数说明"""
    print("\n" + "=" * 80)
    print("测试 2: 不包含硬编码参数说明")
    print("=" * 80)

    soul_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"

    with open(soul_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否包含硬编码参数
    hardcoded_params = [
        "beauty_score_min=80",
        "beauty_score_min=75",
        "appearance_match_json",
    ]

    found_hardcoded = []
    for param in hardcoded_params:
        if param in content:
            found_hardcoded.append(param)

    if found_hardcoded:
        print(f"❌ 发现硬编码参数：{found_hardcoded}")
        return False
    else:
        print("✅ 没有发现硬编码参数")
        return True


def test_contains_abstract_parameters():
    """测试：包含抽象化参数"""
    print("\n" + "=" * 80)
    print("测试 3: 包含抽象化参数")
    print("=" * 80)

    soul_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"

    with open(soul_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否包含抽象化参数
    abstract_params = [
        "appearance_level",
        "appearance_description",
        "Agent Native设计",
    ]

    found_abstract = []
    for param in abstract_params:
        if param in content:
            found_abstract.append(param)

    if len(found_abstract) >= 2:
        print(f"✅ 包含抽象化参数：{found_abstract}")
        return True
    else:
        print(f"❌ 缺少抽象化参数，只找到：{found_abstract}")
        return False


def test_contains_preference_understanding_guidance():
    """测试：包含外貌偏好理解指导"""
    print("\n" + "=" * 80)
    print("测试 4: 包含外貌偏好理解指导")
    print("=" * 80)

    soul_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"

    with open(soul_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否包含指导内容
    guidance_keywords = [
        "外貌偏好理解指导",
        "提取关键信息",
        "理解隐含意图",
        "自主决策搜索策略",
    ]

    found_guidance = []
    for keyword in guidance_keywords:
        if keyword in content:
            found_guidance.append(keyword)

    if len(found_guidance) >= 3:
        print(f"✅ 包含外貌偏好理解指导：{found_guidance}")
        return True
    else:
        print(f"❌ 缺少外貌偏好理解指导，只找到：{found_guidance}")
        return False


def test_contains_recommendation_guidance():
    """测试：包含推荐理由生成指导"""
    print("\n" + "=" * 80)
    print("测试 5: 包含推荐理由生成指导")
    print("=" * 80)

    soul_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"

    with open(soul_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否包含推荐指导
    recommendation_keywords = [
        "推荐理由生成指导",
        "查看工具返回的原始数据",
        "根据原始数据判断匹配度",
        "生成推荐理由",
    ]

    found_recommendation = []
    for keyword in recommendation_keywords:
        if keyword in content:
            found_recommendation.append(keyword)

    if len(found_recommendation) >= 2:
        print(f"✅ 包含推荐理由生成指导：{found_recommendation}")
        return True
    else:
        print(f"❌ 缺少推荐理由生成指导，只找到：{found_recommendation}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("Phase 4 测试：Agent System Prompt增强")
    print("=" * 80)

    try:
        results = []
        results.append(test_soul_file_exists())
        results.append(test_no_hardcoded_parameters())
        results.append(test_contains_abstract_parameters())
        results.append(test_contains_preference_understanding_guidance())
        results.append(test_contains_recommendation_guidance())

        if all(results):
            print("\n" + "=" * 80)
            print("✅ Phase 4 所有测试通过！")
            print("=" * 80)

            print("\n【关键成果】")
            print("1. ✅ SOUL.md包含外貌偏好理解指导")
            print("2. ✅ SOUL.md不包含硬编码参数说明")
            print("3. ✅ SOUL.md包含抽象化参数")
            print("4. ✅ SOUL.md包含推荐理由生成指导")

            return 0
        else:
            print("\n❌ 部分测试失败")
            print(f"测试结果：{results}")
            return 1

    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())