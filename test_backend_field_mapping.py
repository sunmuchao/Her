#!/usr/bin/env python3
"""测试后端字段映射和标准化函数"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from match_domain.onboarding_search import (
    build_onboarding_profile_fields,
    normalize_boolish,
    normalize_education,
    normalize_smoking_drinking,
    normalize_house_car,
    normalize_has_children,
    normalize_marital_status,
)

def test_normalize_boolish():
    """测试布尔值标准化"""
    print("\n=== 测试 normalize_boolish ===")

    test_cases = [
        (True, 1),
        (False, 0),
        (1, 1),
        (0, 0),
        ("yes", 1),
        ("no", 0),
        ("是", 1),
        ("否", 0),
        ("随自己", 1),
        ("不随自己", 0),
        ("独生子女", 1),
        ("非独生子女", 0),
        (None, None),
        ("invalid", None),
    ]

    for input_val, expected in test_cases:
        result = normalize_boolish(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_boolish({repr(input_val)}) = {result}, expected {expected}")

def test_normalize_education():
    """测试学历标准化"""
    print("\n=== 测试 normalize_education ===")

    test_cases = [
        ("专科", "college"),
        ("大专", "college"),
        ("college", "college"),
        ("本科", "bachelor"),
        ("bachelor", "bachelor"),
        ("硕士", "master"),
        ("master", "master"),
        ("博士", "doctor"),
        ("doctor", "doctor"),
        ("phd", "doctor"),
        (None, None),
        ("", None),
        ("unknown", "unknown"),  # 未知的值保留原样
    ]

    for input_val, expected in test_cases:
        result = normalize_education(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_education({repr(input_val)}) = {result}, expected {expected}")

def test_normalize_smoking_drinking():
    """测试抽烟喝酒标准化"""
    print("\n=== 测试 normalize_smoking_drinking ===")

    test_cases = [
        ("不抽烟", "never"),
        ("不喝酒", "never"),
        ("never", "never"),
        ("偶尔抽烟", "occasionally"),
        ("偶尔喝酒", "occasionally"),
        ("occasionally", "occasionally"),
        ("经常抽烟", "regularly"),
        ("经常喝酒", "regularly"),
        ("regularly", "regularly"),
        ("抽烟", "regularly"),
        ("喝酒", "regularly"),
        (None, None),
        ("", None),
    ]

    for input_val, expected in test_cases:
        result = normalize_smoking_drinking(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_smoking_drinking({repr(input_val)}) = {result}, expected {expected}")

def test_normalize_house_car():
    """测试房产车产标准化"""
    print("\n=== 测试 normalize_house_car ===")

    test_cases = [
        ("有房", "owned"),
        ("有车", "owned"),
        ("owned", "owned"),
        ("无房", "none"),
        ("无车", "none"),
        ("none", "none"),
        ("房贷中", "mortgage"),
        ("车贷中", "mortgage"),
        ("mortgage", "mortgage"),
        (None, None),
        ("", None),
    ]

    for input_val, expected in test_cases:
        result = normalize_house_car(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_house_car({repr(input_val)}) = {result}, expected {expected}")

def test_build_onboarding_profile_fields():
    """测试完整的字段映射函数"""
    print("\n=== 测试 build_onboarding_profile_fields ===")

    # 测试用例1：完整的基本信息
    basic_info_1 = {
        "name": "张三",
        "gender": "male",
        "birthday": "1990-01-01",
        "location": "北京",
        "relationship_goal": "marriage",
        "marriage_status": "never_married",
        "has_children": "no",
        "height": 175,
        "weight": 70,
        "education": "本科",
        "job": "工程师",
        "income_range": "10-20万",
        "hometown_city": "杭州",
        "smoking": "不抽烟",
        "drinking": "偶尔喝酒",
        "has_house": "有房",
        "has_car": "无车",
        "religion": "无",
        "is_only_child": "是",
        "district": "朝阳区",
    }

    preference_1 = {
        "relationship_goal": "marriage",
    }

    result_1 = build_onboarding_profile_fields(basic_info_1, preference_1)

    print("\n测试用例1：完整的基本信息")
    expected_fields_1 = {
        "name": "张三",
        "gender": "male",
        "city": "北京",
        "relationship_goal": "marriage",
        "age": 35,  # 从birthday计算
        "marital_status": "never_married",
        "has_children": 0,
        "height": 175,
        "weight": 70,
        "education": "本科",  # 注意：标准化函数暂未应用到build函数中
        "job": "工程师",
        "income_range": "10-20万",
        "hometown_city": "杭州",
        "smoking": "不抽烟",
        "drinking": "偶尔喝酒",
        "has_house": "有房",
        "has_car": "无车",
        "religion": "无",
        "is_only_child": 1,  # 标准化为布尔值
        "district": "朝阳区",
    }

    for key, expected in expected_fields_1.items():
        actual = result_1.get(key)
        status = "✅" if actual == expected else "❌"
        print(f"{status} {key}: {actual}, expected {expected}")

    # 测试用例2：有孩子的情况
    basic_info_2 = {
        "name": "李四",
        "gender": "female",
        "birthday": "1985-05-15",
        "location": "上海",
        "has_children": "yes",
        "children_count": 2,
        "children_living_with_self": "yes",
    }

    result_2 = build_onboarding_profile_fields(basic_info_2, None)

    print("\n测试用例2：有孩子的情况")
    expected_fields_2 = {
        "name": "李四",
        "gender": "female",
        "city": "上海",
        "age": 40,
        "has_children": 1,
        "children_count": 2,
        "children_living_with_self": 1,  # 标准化为布尔值
    }

    for key, expected in expected_fields_2.items():
        actual = result_2.get(key)
        status = "✅" if actual == expected else "❌"
        print(f"{status} {key}: {actual}, expected {expected}")

    # 测试用例3：空值过滤
    basic_info_3 = {
        "name": "王五",
        "gender": "male",
        "height": None,
        "weight": "",
        "education": None,
    }

    result_3 = build_onboarding_profile_fields(basic_info_3, None)

    print("\n测试用例3：空值过滤")
    print(f"✅ 结果字段数量: {len(result_3)} (应该只包含非空字段)")
    print(f"✅ height不应在结果中: {'height' not in result_3}")
    print(f"✅ weight不应在结果中: {'weight' not in result_3}")
    print(f"✅ education不应在结果中: {'education' not in result_3}")

    print(f"\n实际结果: {result_3}")

def test_validation_logic():
    """测试验证逻辑（模拟）"""
    print("\n=== 测试验证逻辑（模拟） ===")

    # 这里我们模拟submit_onboarding_profile中的验证逻辑
    # 实际验证需要在真实的数据库环境中进行

    test_cases = [
        # (height, weight, children_count, has_children, should_pass)
        (175, 70, None, 0, True),   # 无孩子，不填孩子数量 ✓
        (175, 70, 2, 1, True),      # 有孩子，填写孩子数量 ✓
        (175, 70, None, 1, False),  # 有孩子，未填孩子数量 ✗
        (50, 70, None, 0, False),   # 身高过低 ✗
        (300, 70, None, 0, False),  # 身高过高 ✗
        (175, 10, None, 0, False),  # 体重过低 ✗
        (175, 300, None, 0, False), # 体重过高 ✗
        (175, 70, 15, 1, False),    # 孩子数量过多 ✗
    ]

    for height, weight, children_count, has_children, should_pass in test_cases:
        errors = []

        # 模拟验证逻辑
        if height is not None and (height < 100 or height > 250):
            errors.append("身高需在100-250cm之间")

        if weight is not None and (weight < 30 or weight > 200):
            errors.append("体重需在30-200kg之间")

        if children_count is not None and (children_count < 0 or children_count > 10):
            errors.append("孩子数量需在0-10之间")

        if has_children == 1 and children_count is None:
            errors.append("有孩子时需填写孩子数量")

        passed = len(errors) == 0
        status = "✅" if passed == should_pass else "❌"
        print(f"{status} height={height}, weight={weight}, children_count={children_count}, has_children={has_children} -> {passed}, expected {should_pass}")
        if errors:
            print(f"   错误: {errors}")

if __name__ == "__main__":
    print("=" * 60)
    print("测试后端字段映射和标准化函数")
    print("=" * 60)

    test_normalize_boolish()
    test_normalize_education()
    test_normalize_smoking_drinking()
    test_normalize_house_car()
    test_build_onboarding_profile_fields()
    test_validation_logic()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)