"""
推荐卡片显示优化后端测试脚本

测试目标：
1. 验证 build_requester_safe_summary() 函数返回的数据格式正确
2. 验证年龄显示为实际年龄（而非年龄段）
3. 验证关系目标映射为中文
4. 验证信息完整（包含学历、职业等）

测试文件：proxy_intro_core.py
测试函数：build_requester_safe_summary()
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from matchmaking_system.proxy_intro_core import build_requester_safe_summary, json_loads


def test_age_display():
    """测试年龄显示：验证显示实际年龄而非年龄段"""
    print("=" * 60)
    print("【测试 1】年龄显示测试")
    print("=" * 60)

    # 测试场景 1: 正常年龄（28岁）
    subscription = {
        "self_profile_json": '{"age": 28, "display_name": "孙木超", "city": "无锡", "job": "程序员", "education": "本科", "relationship_goal": "dating"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 1: 正常年龄（28岁）")
    print(f"   输入: age = 28")
    print(f"   输出: age = {result['age']}")
    print(f"   期望: age = '28岁'")
    assert result['age'] == '28岁', f"❌ 年龄显示错误：期望 '28岁'，实际 '{result['age']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 2: 年龄边界（25岁）
    subscription = {
        "self_profile_json": '{"age": 25, "display_name": "测试用户", "relationship_goal": "marriage"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 2: 年龄边界（25岁）")
    print(f"   输入: age = 25")
    print(f"   输出: age = {result['age']}")
    print(f"   期望: age = '25岁'")
    assert result['age'] == '25岁', f"❌ 年龄显示错误：期望 '25岁'，实际 '{result['age']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 3: 年龄缺失
    subscription = {
        "self_profile_json": '{"display_name": "测试用户"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 3: 年龄缺失")
    print(f"   输入: age = None")
    print(f"   输出: age = {result['age']}")
    print(f"   期望: age = None")
    assert result['age'] is None, f"❌ 年龄显示错误：期望 None，实际 '{result['age']}'"
    print("   ✅ 通过")
    print()

    print("🎉 所有年龄测试通过！")
    print()


def test_relationship_goal_mapping():
    """测试关系目标映射：验证英文映射为中文"""
    print("=" * 60)
    print("【测试 2】关系目标映射测试")
    print("=" * 60)

    # 测试场景 1: dating → 先谈恋爱
    subscription = {
        "self_profile_json": '{"age": 28, "relationship_goal": "dating"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 1: dating → 先谈恋爱")
    print(f"   输入: relationship_goal = 'dating'")
    print(f"   输出: relationship_goal = {result['relationship_goal']}")
    print(f"   期望: relationship_goal = '先谈恋爱'")
    assert result['relationship_goal'] == '先谈恋爱', f"❌ 映射错误：期望 '先谈恋爱'，实际 '{result['relationship_goal']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 2: marriage → 奔着结婚
    subscription = {
        "self_profile_json": '{"age": 30, "relationship_goal": "marriage"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 2: marriage → 奔着结婚")
    print(f"   输入: relationship_goal = 'marriage'")
    print(f"   输出: relationship_goal = {result['relationship_goal']}")
    print(f"   期望: relationship_goal = '奔着结婚'")
    assert result['relationship_goal'] == '奔着结婚', f"❌ 映射错误：期望 '奔着结婚'，实际 '{result['relationship_goal']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 3: friends → 找搭子
    subscription = {
        "self_profile_json": '{"age": 25, "relationship_goal": "friends"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 3: friends → 找搭子")
    print(f"   输入: relationship_goal = 'friends'")
    print(f"   输出: relationship_goal = {result['relationship_goal']}")
    print(f"   期望: relationship_goal = '找搭子'")
    assert result['relationship_goal'] == '找搭子', f"❌ 映射错误：期望 '找搭子'，实际 '{result['relationship_goal']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 4: 关系目标缺失
    subscription = {
        "self_profile_json": '{"age": 28}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 4: 关系目标缺失")
    print(f"   输入: relationship_goal = None")
    print(f"   输出: relationship_goal = {result['relationship_goal']}")
    print(f"   期望: relationship_goal = None")
    assert result['relationship_goal'] is None, f"❌ 映射错误：期望 None，实际 '{result['relationship_goal']}'"
    print("   ✅ 通过")
    print()

    print("🎉 所有关系目标测试通过！")
    print()


def test_summary_text_completeness():
    """测试摘要信息完整性：验证包含年龄、城市、职业、学历、关系目标"""
    print("=" * 60)
    print("【测试 3】摘要信息完整性测试")
    print("=" * 60)

    # 测试场景 1: 完整信息
    subscription = {
        "self_profile_json": '{"age": 28, "display_name": "孙木超", "city": "无锡", "job": "程序员", "education": "本科", "relationship_goal": "dating"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 1: 完整信息")
    print(f"   输入: age=28, city='无锡', job='程序员', education='本科', relationship_goal='dating'")
    print(f"   输出: summary_text = {result['summary_text']}")
    print(f"   期望: summary_text = '28岁；无锡；本科；程序员；先谈恋爱'")
    expected = '28岁；无锡；本科；程序员；先谈恋爱'
    assert result['summary_text'] == expected, f"❌ 拼接错误：期望 '{expected}'，实际 '{result['summary_text']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 2: 部分信息缺失
    subscription = {
        "self_profile_json": '{"age": 30, "display_name": "测试用户", "city": "北京", "relationship_goal": "marriage"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 2: 部分信息缺失（职业、学历缺失）")
    print(f"   输入: age=30, city='北京', relationship_goal='marriage'")
    print(f"   输出: summary_text = {result['summary_text']}")
    print(f"   期望: summary_text = '30岁；北京；奔着结婚'")
    expected = '30岁；北京；奔着结婚'
    assert result['summary_text'] == expected, f"❌ 拼接错误：期望 '{expected}'，实际 '{result['summary_text']}'"
    print("   ✅ 通过")
    print()

    # 测试场景 3: 年龄缺失但有其他信息
    subscription = {
        "self_profile_json": '{"display_name": "测试用户", "city": "上海", "job": "设计师", "education": "硕士"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试场景 3: 年龄缺失但有其他信息")
    print(f"   输入: city='上海', job='设计师', education='硕士'")
    print(f"   输出: summary_text = {result['summary_text']}")
    print(f"   期望: summary_text = '上海；硕士；设计师'")
    expected = '上海；硕士；设计师'
    assert result['summary_text'] == expected, f"❌ 拼接错误：期望 '{expected}'，实际 '{result['summary_text']}'"
    print("   ✅ 通过")
    print()

    print("🎉 所有摘要完整性测试通过！")
    print()


def test_data_structure():
    """测试数据结构：验证返回的数据结构包含所有必要字段"""
    print("=" * 60)
    print("【测试 4】数据结构测试")
    print("=" * 60)

    subscription = {
        "self_profile_json": '{"age": 28, "display_name": "孙木超", "city": "无锡", "job": "程序员", "education": "本科", "relationship_goal": "dating", "avatar_url": "https://example.com/avatar.jpg"}'
    }
    result = build_requester_safe_summary(subscription)

    print("✅ 测试数据结构完整性")
    required_fields = [
        'requester_name',
        'age',
        'age_bracket',
        'city',
        'height_bracket',
        'education',
        'occupation',
        'relationship_goal',
        'relationship_goal_raw',
        'matched_on',
        'subscription_title',
        'avatar_url',
        'summary_text'
    ]

    missing_fields = []
    for field in required_fields:
        if field not in result:
            missing_fields.append(field)
            print(f"   ❌ 缺失字段: {field}")
        else:
            print(f"   ✅ 存在字段: {field} = {result[field]}")

    assert len(missing_fields) == 0, f"❌ 数据结构缺失字段: {missing_fields}"
    print("   ✅ 所有字段都存在")
    print()

    # 验证兼容性字段
    print("✅ 测试兼容性字段")
    print(f"   age = {result['age']}")
    print(f"   age_bracket = {result['age_bracket']}")
    assert result['age'] == result['age_bracket'], "❌ age 和 age_bracket 不一致"
    print("   ✅ age 和 age_bracket 一致（兼容性正确）")
    print()

    # 验证原始值保留
    print("✅ 测试原始值保留")
    print(f"   relationship_goal = {result['relationship_goal']}")
    print(f"   relationship_goal_raw = {result['relationship_goal_raw']}")
    assert result['relationship_goal'] == '先谈恋爱', "❌ 映射值错误"
    assert result['relationship_goal_raw'] == 'dating', "❌ 原始值未保留"
    print("   ✅ 映射值和原始值都正确")
    print()

    print("🎉 所有数据结构测试通过！")
    print()


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("推荐卡片显示优化后端测试")
    print("=" * 60)
    print()

    try:
        test_age_display()
        test_relationship_goal_mapping()
        test_summary_text_completeness()
        test_data_structure()

        print("=" * 60)
        print("🎉 所有测试通过！后端改动验证成功！")
        print("=" * 60)
        print()

        return True
    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ 测试失败: {e}")
        print("=" * 60)
        print()

        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)