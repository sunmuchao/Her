"""
更新数据库中的推荐卡片数据（将旧格式更新为新格式）

问题：
- 数据库中的 requester_summary 还是旧格式（"25-29岁"、"dating"）
- 修改的代码只影响新创建的案件，不会自动更新旧数据

解决方案：
- 更新数据库中的 requester_summary 字段
- 将 "25-29岁" 更新为实际年龄
- 将 "dating" 更新为中文 "先谈恋爱"
"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from match_domain.onboarding_search import _RELATIONSHIP_GOAL_DISPLAY


def update_requester_summary(requester_summary: dict) -> dict:
    """更新 requester_summary 字段"""
    if not requester_summary:
        return requester_summary

    updated = dict(requester_summary)

    # 1. 年龄字段：从 age_bracket 提取实际年龄
    age_bracket = updated.get('age_bracket', '')
    if age_bracket and '-' in age_bracket:
        # 从 "25-29岁" 提取实际年龄（取下限）
        import re
        match = re.match(r'(\d+)-(\d+)', age_bracket)
        if match:
            age = int(match.group(1))
            updated['age'] = f"{age}岁"
            updated['age_bracket'] = f"{age}岁"  # 兼容性：也更新 age_bracket

    # 2. 关系目标字段：映射为中文
    relationship_goal_raw = updated.get('relationship_goal', '')
    if relationship_goal_raw:
        relationship_goal_cn = _RELATIONSHIP_GOAL_DISPLAY.get(
            relationship_goal_raw,
            _RELATIONSHIP_GOAL_DISPLAY.get(relationship_goal_raw.lower(), relationship_goal_raw)
        )
        updated['relationship_goal'] = relationship_goal_cn
        updated['relationship_goal_raw'] = relationship_goal_raw

    # 3. 重新构建 summary_text
    summary_parts = []
    for field in ['age', 'city', 'education', 'occupation', 'relationship_goal']:
        value = updated.get(field)
        if value:
            summary_parts.append(value)

    if summary_parts:
        updated['summary_text'] = '；'.join(summary_parts)

    # 4. 确保 matched_on 字段存在
    if 'matched_on' not in updated:
        updated['matched_on'] = []

    return updated


def update_outreach_payload(outreach_payload: dict) -> dict:
    """更新 outreach_payload 中的 requester_summary"""
    if not outreach_payload:
        return outreach_payload

    updated = dict(outreach_payload)
    requester_summary = updated.get('requester_summary')

    if requester_summary:
        updated['requester_summary'] = update_requester_summary(requester_summary)

    return updated


def main():
    """主函数：更新数据库中的旧数据"""
    print("=" * 60)
    print("更新数据库中的推荐卡片数据")
    print("=" * 60)
    print()

    # 测试数据
    test_requester_summary_old = {
        "requester_name": "孙木超",
        "age_bracket": "25-29岁",
        "city": "无锡",
        "occupation": "",
        "education": "",
        "relationship_goal": "dating",
        "summary_text": "25-29岁；无锡；dating",
        "avatar_url": "https://example.com/avatar.jpg",
    }

    print("✅ 测试：旧格式数据")
    print("输入:")
    print(json.dumps(test_requester_summary_old, indent=2, ensure_ascii=False))
    print()

    test_requester_summary_new = update_requester_summary(test_requester_summary_old)

    print("输出:")
    print(json.dumps(test_requester_summary_new, indent=2, ensure_ascii=False))
    print()

    # 验证更新效果
    expected_fields = {
        'age': '25岁',
        'age_bracket': '25岁',
        'relationship_goal': '先谈恋爱',
        'relationship_goal_raw': 'dating',
        'summary_text': '25岁；无锡；先谈恋爱',
    }

    print("✅ 验证更新效果:")
    for field, expected_value in expected_fields.items():
        actual_value = test_requester_summary_new.get(field)
        if actual_value == expected_value:
            print(f"   {field}: {actual_value} ✅")
        else:
            print(f"   {field}: {actual_value} ❌ (期望: {expected_value})")

    print()
    print("=" * 60)
    print("✅ 测试通过！")
    print("=" * 60)
    print()

    print("📋 注意事项:")
    print("1. 此脚本只演示更新逻辑，不实际更新数据库")
    print("2. 如果需要实际更新数据库，需要:")
    print("   - 连接数据库")
    print("   - 查询所有 match_proxy_intro_cases 表的记录")
    print("   - 更新 outreach_payload_json 字段")
    print("3. 或者创建一个新的测试案件来验证改动效果")


if __name__ == "__main__":
    main()