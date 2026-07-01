#!/usr/bin/env python3
"""补充测试：验证新增选项的标准化"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from match_domain.onboarding_search import normalize_education

def test_new_education_option():
    """测试新增的学历选项：高中及以下"""
    print("\n=== 测试新增学历选项 ===")

    test_cases = [
        ("高中及以下", "high_school", "高中及以下 -> high_school"),
        ("高中", "high_school", "高中 -> high_school"),
        ("high_school", "high_school", "英文 high_school 保持"),
        ("专科", "college", "专科 -> college"),
        ("本科", "bachelor", "本科 -> bachelor"),
        ("硕士", "master", "硕士 -> master"),
        ("博士", "doctor", "博士 -> doctor"),
    ]

    all_passed = True
    for input_val, expected, desc in test_cases:
        result = normalize_education(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} {desc}: {repr(input_val)} -> {result} (预期 {expected})")
        if result != expected:
            all_passed = False

    if all_passed:
        print("\n✅ 新增学历选项测试通过")
    else:
        print("\n❌ 存在测试失败")

if __name__ == "__main__":
    print("=" * 60)
    print("补充测试：新增选项标准化验证")
    print("=" * 60)
    test_new_education_option()
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)